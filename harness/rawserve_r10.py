#!/usr/bin/env python3
"""The `raw` transport ceiling: this harness pulling articles with no application in the way.

Every absolute MB/s in rounds 3 through 9 was published without a ceiling to read
it against, so none of them can say how much of the link was available that
evening. A target moving 36 MB/s on a night when the transport could only do 38
is a very different result from the same 36 on a night it could do 90, and
nothing in the repository could tell those apart.

`raw` is not a competitor and must never be ranked against one. It fetches the
same articles from the same account over the same TLS, decodes them and serves
them over HTTP with Range support, so the identical measurement code drives it.
What it produces is the number every other row is a fraction of.

Two things it deliberately does not do, both of which would make it a worse
ceiling:

  * It does not open archives. For a RAR or 7z release it serves the outer
    volume stream, because unpacking is exactly the work the applications are
    being compared on and a baseline that did it would be one of them.
  * It does not cache. A warm re-read from `raw` is another cold fetch, so the
    ceiling stays a transport number rather than becoming a memory number.

Usage:
    python3 rawserve_r10.py corpus/ToyStory5.nzb 8099 [--conns 15] [--depth 4]

Credentials come from the environment when set, so a real run never edits this
file: NNTP_HOST, NNTP_PORT, NNTP_USER, NNTP_PASS.
"""
import argparse
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nntp_r10 import NntpConn, parse_nzb  # noqa: E402

HOST = os.environ.get("NNTP_HOST", "news.news-provider.example")
PORT = int(os.environ.get("NNTP_PORT", "563"))
USER = os.environ.get("NNTP_USER", "YOUR_USENET_USERNAME")
PASS = os.environ.get("NNTP_PASS", "YOUR_USENET_PASSWORD")

VIDEO = re.compile(r"\.(mkv|mp4|avi|ts|m2ts)\b", re.I)
# volume 1 of a set is the entry point; a bare .rar or .7z or .001 opens the stream
ARCHIVE = re.compile(r"(\.part0*1\.rar|\.rar|\.7z|\.001)(\"|\s|$)", re.I)


def subject_name(subject):
    """The quoted filename inside an NZB subject, or the whole subject if unquoted."""
    match = re.search(r'"([^"]+)"', subject)
    return match.group(1) if match else subject.strip()


def pick_file(files):
    """The release's entry-point file, by the same rule the rest of the harness uses.

    The largest non-sample video, or failing that the first archive volume. The
    first video in a listing is not the release: a server that preserves an
    archive's internal structure lists `Sample/` first, and a ranged read of a
    9 MB sample clip is a correct 416 that reads as a broken target.
    """
    named = [(f, subject_name(f["subject"])) for f in files]
    videos = [(f, n) for f, n in named
              if VIDEO.search(n) and "sample" not in n.lower()]
    if videos:
        return max(videos, key=lambda fn: fn[0]["bytes"])
    archives = [(f, n) for f, n in named if ARCHIVE.search(n)]
    if archives:
        return min(archives, key=lambda fn: fn[1].lower())
    return max(named, key=lambda fn: fn[0]["bytes"])


class SegmentMap:
    """Where each article's decoded bytes land in the assembled file.

    The `bytes` attribute in an NZB is the *encoded* size and overstates the
    decoded one by roughly 2-3%, so it cannot be used for offsets: a map built
    from it drifts further out of true with every part and a seek 4 GB in lands
    in the wrong article entirely. The true offsets live in each article's own
    `=ypart begin=`, which costs a fetch to read.

    So the map is built lazily and verified. A uniform part size is assumed from
    the first article, which is what every single-poster release actually looks
    like, and every article that is fetched reports its own `begin`. A
    disagreement is corrected from the article rather than trusted from the
    assumption, and counted, so a release the assumption does not fit says so in
    the results instead of quietly serving shifted bytes.
    """

    def __init__(self, segments):
        self.segments = segments
        self.part_size = None
        self.total = None
        self.corrections = 0
        self.lock = threading.Lock()

    def bootstrap(self, conn):
        (payload, meta), = conn.fetch([self.segments[0][2]])
        if payload is None:
            raise RuntimeError(f"first article unavailable: {meta}")
        self.part_size = len(payload)
        self.total = meta.get("size") or self.part_size * len(self.segments)
        return payload, meta

    def index_for(self, offset):
        if not self.part_size:
            raise RuntimeError("segment map not bootstrapped")
        return min(offset // self.part_size, len(self.segments) - 1)

    def note(self, index, meta, length):
        """Record an article's declared position; count any disagreement."""
        declared = meta.get("begin")
        if declared is None:
            return index * self.part_size
        expected = index * self.part_size + 1  # =ypart begin is 1-based
        if declared != expected:
            with self.lock:
                self.corrections += 1
        return declared - 1


class Fetcher:
    """A pool of authenticated connections, each pipelining a batch of articles.

    Both halves matter for a ceiling. One connection with a deep pipeline does
    not saturate a 15-connection account, and fifteen connections issuing one
    command each pay a round trip per article. The applications under test all
    do both, so a baseline that did neither would sit below the things it is
    meant to bound and every one of them would look like it had beaten the
    transport.
    """

    def __init__(self, conns, depth):
        self.depth = depth
        self.local = threading.local()
        self.pool = ThreadPoolExecutor(max_workers=conns)
        self.opened = []
        self.lock = threading.Lock()

    def _conn(self):
        conn = getattr(self.local, "conn", None)
        if conn is None:
            conn = NntpConn(HOST, PORT, USER, PASS)
            self.local.conn = conn
            with self.lock:
                self.opened.append(conn)
        return conn

    def fetch_batch(self, message_ids):
        return self._conn().fetch(message_ids)

    def submit(self, message_ids):
        return self.pool.submit(self.fetch_batch, message_ids)

    def close(self):
        self.pool.shutdown(wait=False)
        with self.lock:
            for conn in self.opened:
                conn.close()
            self.opened = []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "raw-r10"

    def log_message(self, *args):
        pass  # the harness reads timings, not an access log

    def _range(self, size):
        header = self.headers.get("Range", "")
        match = re.match(r"bytes=(\d*)-(\d*)", header.strip())
        if not match:
            return 0, size - 1, False
        start, end = match.group(1), match.group(2)
        if not start:                       # suffix range: last N bytes
            length = int(end or 0)
            return max(0, size - length), size - 1, True
        start = int(start)
        end = int(end) if end else size - 1
        return start, min(end, size - 1), True

    def do_HEAD(self):
        state = self.server.state
        self.send_response(200)
        self.send_header("Content-Length", str(state["map"].total))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "video/x-matroska")
        self.end_headers()

    def do_GET(self):
        state = self.server.state
        smap, fetcher = state["map"], state["fetcher"]
        total = smap.total
        start, end, partial = self._range(total)
        if start >= total:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{total}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        length = end - start + 1
        self.send_response(206 if partial else 200)
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "video/x-matroska")
        self.end_headers()

        first = smap.index_for(start)
        segments = smap.segments
        # bound the read-ahead so a client that stops reading cannot make this
        # process hold the whole release in memory
        window = max(2, state["conns"] * 2)
        pending, next_ix, written = [], first, 0
        try:
            while written < length:
                while len(pending) < window and next_ix < len(segments):
                    batch = segments[next_ix:next_ix + fetcher.depth]
                    pending.append((next_ix, fetcher.submit([s[2] for s in batch])))
                    next_ix += len(batch)
                if not pending:
                    break
                base_ix, future = pending.pop(0)
                for offset, (payload, meta) in enumerate(future.result()):
                    if written >= length:
                        break
                    index = base_ix + offset
                    if payload is None:
                        # a dead article is a hole, not a crash. Zero-fill keeps
                        # every later offset correct, and the damage phase is
                        # where that behaviour is measured rather than papered over.
                        payload = b"\x00" * (smap.part_size or 0)
                        state["holes"] += 1
                        abs_start = index * (smap.part_size or 0)
                    else:
                        abs_start = smap.note(index, meta, len(payload))
                    abs_end = abs_start + len(payload)
                    if abs_end <= start:
                        continue
                    lo = max(0, start - abs_start)
                    hi = len(payload) - max(0, abs_end - (end + 1))
                    if hi <= lo:
                        continue
                    chunk = payload[lo:hi]
                    self.wfile.write(chunk)
                    written += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("nzb")
    ap.add_argument("port", type=int)
    ap.add_argument("--conns", type=int, default=int(os.environ.get("CONNS", "15")),
                    help="connections, which must match every other target's budget")
    ap.add_argument("--depth", type=int, default=4, help="articles pipelined per request")
    args = ap.parse_args()

    files = parse_nzb(args.nzb)
    if not files:
        sys.exit(f"no files in {args.nzb}")
    target, name = pick_file(files)
    smap = SegmentMap(target["segments"])
    fetcher = Fetcher(args.conns, args.depth)
    boot = NntpConn(HOST, PORT, USER, PASS)
    try:
        smap.bootstrap(boot)
    finally:
        boot.close()

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    httpd.state = {"map": smap, "fetcher": fetcher, "conns": args.conns, "holes": 0}
    print(f"raw: serving {name} ({smap.total} bytes, {len(smap.segments)} articles, "
          f"part {smap.part_size}) on 127.0.0.1:{args.port} "
          f"with {args.conns} connections x depth {args.depth}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        fetcher.close()
        if smap.corrections:
            print(f"raw: {smap.corrections} articles disagreed with the uniform "
                  f"part-size assumption and were corrected from their own headers",
                  flush=True)


if __name__ == "__main__":
    main()
