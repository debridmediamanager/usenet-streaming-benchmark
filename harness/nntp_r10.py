#!/usr/bin/env python3
"""Minimal NZB parser, yEnc decoder and pipelined NNTP client.

Two round-10 phases need to fetch articles without a server in the middle:

  * the `raw` transport ceiling (rawserve_r10.py), which is the whole point of
    having a baseline -- an absolute MB/s figure says nothing about how much
    headroom the link had that evening unless something measures the link with
    no application in the path.
  * the damage phase (damage_r10.py), which verifies that the bytes either side
    of a known hole are where the server claims they are. Without the true
    bytes to compare against, a server that lays a file out differently is
    indistinguishable from one that repaired the gap.

stdlib only, like the rest of this harness, and Python 3.10 compatible: zen
runs 3.10.12 and `nntplib` is gone from 3.13, so rolling the protocol here is
the portable choice as well as the controllable one.
"""
import re
import socket
import ssl
import xml.etree.ElementTree as ET
import zlib

# yEnc: every data byte is (value - 42) mod 256, and an escaped byte (preceded
# by '=') is a further -64. Building both as a translate table keeps the decoder
# in C for the common case; a 4 MiB article decoded byte-at-a-time in Python is
# slower than the network and would make the ceiling measure this file.
_YDEC = bytes((b - 42) & 0xFF for b in range(256))

NZB_NS = "{http://www.newzbin.com/DTD/2003/nzb}"


def ydecode(data):
    """Decode a yEnc payload. Escapes are rare, so the no-escape path is one memcpy."""
    if b"=" not in data:
        return data.translate(_YDEC)
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        j = data.find(b"=", i)
        if j < 0:
            out += data[i:].translate(_YDEC)
            break
        out += data[i:j].translate(_YDEC)
        if j + 1 >= n:
            # a payload ending on a bare '=' is malformed; drop it rather than
            # index past the end and turn a bad article into a crash
            break
        out.append((data[j + 1] - 106) & 0xFF)  # -42 and -64 folded together
        i = j + 2
    return bytes(out)


def unstuff(body):
    """Undo NNTP dot-stuffing. A line that began with '.' was sent as '..'."""
    if body.startswith(b".."):
        body = body[1:]
    return body.replace(b"\r\n..", b"\r\n.")


def decode_article(body):
    """Raw BODY bytes -> (payload, meta). Meta carries begin/end/crc when present.

    yEnc frames the payload between '=ybegin'/'=ypart' headers and a '=yend'
    trailer, and the harness needs those headers: `begin` is what says where
    this part lands in the assembled file, and without it a missing article
    shifts every later byte and the file silently becomes garbage rather than
    short.
    """
    body = unstuff(body)
    meta = {}
    lines = body.split(b"\r\n")
    start, end = 0, len(lines)
    for ix, line in enumerate(lines):
        if line.startswith(b"=ybegin"):
            head = _ykv(line)
            # `size` means two different things in a multipart article: on
            # =ybegin it is the size of the whole FILE, on =yend it is the size
            # of this PART. Both land in the same key and the trailer wins, so
            # a reader that wants the file size has to be handed it separately
            # -- the ceiling served a 6.6 GB release as a 4 MiB one for exactly
            # this reason, and a 256 MB read of it is a correct 416.
            if "size" in head:
                meta["file_size"] = head["size"]
            meta.update(head)
            start = ix + 1
        elif line.startswith(b"=ypart"):
            meta.update(_ykv(line))
            start = ix + 1
        elif line.startswith(b"=yend"):
            meta.update(_ykv(line))
            end = ix
            break
    payload = ydecode(b"".join(lines[start:end]))
    return payload, meta


def _ykv(line):
    out = {}
    for key, val in re.findall(rb"(\w+)=(\S+)", line):
        name = key.decode()
        if name in ("part", "total", "line", "size", "begin", "end"):
            try:
                out[name] = int(val)
            except ValueError:
                pass
        elif name in ("pcrc32", "crc32"):
            out[name] = val.decode().lower().zfill(8)
    return out


def crc_ok(payload, meta):
    """True when the article carried a part CRC and the payload matches it.

    Returns None when the poster supplied no CRC, which is not a failure: a
    missing checksum is common and must not be reported as corruption.
    """
    want = meta.get("pcrc32") or meta.get("crc32")
    if not want:
        return None
    return format(zlib.crc32(payload) & 0xFFFFFFFF, "08x") == want


def parse_nzb(path):
    """NZB -> [{subject, poster, segments: [(number, bytes, message_id)], bytes}].

    Segment order inside a file is by part number, not document order: posters
    do not guarantee the latter, and an out-of-order assembly produces a file
    that is the right length and entirely wrong.
    """
    root = ET.parse(path).getroot()
    els = root.findall(f"{NZB_NS}file") or root.findall("file")
    files = []
    for fel in els:
        seg_parent = fel.find(f"{NZB_NS}segments")
        if seg_parent is None:
            seg_parent = fel.find("segments")
        segs = []
        for sel in (list(seg_parent) if seg_parent is not None else []):
            mid = (sel.text or "").strip()
            if not mid:
                continue
            segs.append((int(sel.get("number", "0")), int(sel.get("bytes", "0")), mid))
        segs.sort(key=lambda s: s[0])
        files.append({
            "subject": fel.get("subject", ""),
            "poster": fel.get("poster", ""),
            "segments": segs,
            "bytes": sum(s[1] for s in segs),
        })
    return files


class NntpError(RuntimeError):
    pass


class NntpConn:
    """One authenticated NNTP-over-TLS connection with request pipelining.

    Pipelining is not a nicety here. The applications under test all pipeline,
    so a serial baseline would report a ceiling below several of the things it
    is supposed to be the ceiling for, and every one of them would look like it
    had beaten the transport.
    """

    def __init__(self, host, port, user, password, timeout=60):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        if port == 563:
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(self.sock, server_hostname=host)
        self.sock.settimeout(timeout)
        # a bytearray, and never re-scanned from the start: see _read_body
        self.buf = bytearray()
        code, _ = self._status()
        if code not in (200, 201):
            raise NntpError(f"greeting {code}")
        self._cmd(f"AUTHINFO USER {user}")
        code, text = self._status()
        if code == 381:
            self._cmd(f"AUTHINFO PASS {password}")
            code, text = self._status()
        if code != 281:
            raise NntpError(f"auth {code} {text}")

    def _cmd(self, line):
        self.sock.sendall(line.encode() + b"\r\n")

    def _readline(self):
        while True:
            ix = self.buf.find(b"\r\n")
            if ix >= 0:
                break
            chunk = self.sock.recv(65536)
            if not chunk:
                raise NntpError("connection closed")
            self.buf += chunk
        line = bytes(self.buf[:ix])
        del self.buf[:ix + 2]
        return line

    def _status(self):
        line = self._readline()
        try:
            return int(line[:3]), line[4:].decode("latin-1")
        except ValueError:
            raise NntpError(f"bad status line {line[:80]!r}")

    def _read_body(self):
        """Read a multi-line block up to the terminating '.' line.

        Scanning only what has just arrived is the whole point. Searching the
        accumulated buffer from the start on every recv, and rebuilding it with
        `buf = buf + chunk`, is quadratic in the article size: this corpus posts
        4 MiB articles and TLS hands them over in ~16 KB records, so a single
        article cost a few hundred MB of scanning and copying -- under the GIL,
        which is where fifteen connections stop being fifteen. The ceiling read
        at 0.99 MB/s and could not bound anything.

        The overlap matters: the terminator can straddle two chunks, so the
        search restarts four bytes behind what was already scanned.
        """
        scanned = 0
        while True:
            ix = self.buf.find(b"\r\n.\r\n", max(0, scanned - 4))
            if ix >= 0:
                break
            scanned = len(self.buf)
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise NntpError("connection closed mid-body")
            self.buf += chunk
        block = bytes(self.buf[:ix])
        del self.buf[:ix + 5]
        return block

    def fetch(self, message_ids):
        """Pipelined BODY. Returns a list aligned with message_ids.

        Each element is (payload, meta) or (None, error_string). A dead article
        answers 430 and is reported, never raised: a hole is a measurement, and
        the phase that cares about holes is half the reason this client exists.
        """
        ids = list(message_ids)
        for mid in ids:
            self._cmd("BODY <%s>" % mid.strip("<>"))
        out = []
        for _ in ids:
            code, text = self._status()
            if code != 222:
                out.append((None, f"{code} {text}"))
                continue
            try:
                out.append(decode_article(self._read_body()))
            except NntpError as exc:
                out.append((None, str(exc)))
        return out

    def close(self):
        try:
            self._cmd("QUIT")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
