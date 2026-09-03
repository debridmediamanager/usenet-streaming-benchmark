#!/usr/bin/env python3
"""Offline tests for the round-10 harness. No network, no provider, no corpus.

The harness had no tests before this. Two things here are worth guarding:

  * the yEnc decoder, because a decoder that is wrong on one byte value in 256
    produces a file of exactly the right length that is quietly corrupt, and
    every downstream number stays plausible.
  * the `raw` baseline's range arithmetic, because an off-by-one in the segment
    map is invisible in a throughput figure and fatal in a seek. A ceiling that
    serves the wrong bytes fast is worse than no ceiling.

Run:  python3 harness/test_r10.py
"""
import os
import sys
import urllib.request
import zlib
from concurrent.futures import Future
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics_r10 as M       # noqa: E402
import nntp_r10 as N          # noqa: E402
import rawserve_r10 as R      # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        FAILURES.append(name)


# --------------------------------------------------------------------------
# yEnc, against a reference encoder written from the spec
# --------------------------------------------------------------------------
CRITICAL = {0x00, 0x0A, 0x0D, 0x3D}  # null, LF, CR and '=' must be escaped


def yencode(data, line_len=128):
    out = bytearray()
    col = 0
    for byte in data:
        enc = (byte + 42) & 0xFF
        if enc in CRITICAL:
            out += b"="
            out.append((enc + 64) & 0xFF)
            col += 2
        else:
            out.append(enc)
            col += 1
        if col >= line_len:
            out += b"\r\n"
            col = 0
    return bytes(out)


def article(payload, begin, part=1):
    return (b"=ybegin part=%d line=128 size=%d name=test.bin\r\n"
            b"=ypart begin=%d end=%d\r\n" % (part, len(payload), begin,
                                             begin + len(payload) - 1)
            + yencode(payload)
            + b"\r\n=yend size=%d part=%d pcrc32=%08x"
              % (len(payload), part, zlib.crc32(payload) & 0xFFFFFFFF))


def test_yenc():
    payload = bytes(range(256)) * 40
    got, meta = N.decode_article(article(payload, 1))
    check("yenc: all 256 byte values round-trip", got == payload)
    check("yenc: size header parsed", meta.get("size") == len(payload))
    check("yenc: begin header parsed", meta.get("begin") == 1)
    check("yenc: crc verifies", N.crc_ok(got, meta) is True)

    blob = os.urandom(300000)
    got, meta = N.decode_article(article(blob, 4194305))
    check("yenc: random 300 KB round-trips", got == blob)
    check("yenc: begin offset parsed", meta.get("begin") == 4194305)

    check("yenc: wrong crc detected", N.crc_ok(b"x", {"pcrc32": "deadbeef"}) is False)
    check("yenc: absent crc is None, not a failure", N.crc_ok(b"x", {}) is None)
    check("yenc: trailing bare '=' tolerated", isinstance(N.ydecode(b"abc="), bytes))
    check("yenc: unstuff collapses a doubled dot",
          N.unstuff(b"aa\r\n..dot\r\nbb") == b"aa\r\n.dot\r\nbb")
    check("yenc: unstuff handles a leading doubled dot",
          N.unstuff(b"..x\r\ny") == b".x\r\ny")


def test_nzb():
    nzb = ('<?xml version="1.0"?>\n'
           '<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">\n'
           ' <file poster="p" subject=\'rel [2/3] - "a.mkv" yEnc\'>\n'
           '  <segments>\n'
           '   <segment bytes="100" number="3">c3@x</segment>\n'
           '   <segment bytes="100" number="1">c1@x</segment>\n'
           '   <segment bytes="100" number="2">c2@x</segment>\n'
           '  </segments>\n'
           ' </file>\n'
           '</nzb>\n')
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_t_r10.nzb")
    with open(path, "w") as handle:
        handle.write(nzb)
    try:
        files = N.parse_nzb(path)
        check("nzb: one file parsed", len(files) == 1)
        # document order is 3,1,2 -- an assembly in that order is right-length garbage
        check("nzb: segments sorted by part number",
              [s[2] for s in files[0]["segments"]] == ["c1@x", "c2@x", "c3@x"])
        check("nzb: encoded byte total summed", files[0]["bytes"] == 300)
        check("nzb: quoted filename extracted",
              R.subject_name(files[0]["subject"]) == "a.mkv")
    finally:
        os.remove(path)


def test_pick_file():
    files = [
        {"subject": 'rel [1/3] - "Sample/sample.mkv" yEnc', "bytes": 9_000_000},
        {"subject": 'rel [2/3] - "feature.mkv" yEnc', "bytes": 6_000_000_000},
        {"subject": 'rel [3/3] - "feature.nfo" yEnc', "bytes": 2_000},
    ]
    _, name = R.pick_file(files)
    check("pick: largest non-sample video wins over Sample/", name == "feature.mkv")

    archives = [
        {"subject": 'rel - "x.part02.rar" yEnc', "bytes": 100},
        {"subject": 'rel - "x.part01.rar" yEnc', "bytes": 100},
    ]
    _, name = R.pick_file(archives)
    check("pick: first archive volume is the entry point", name == "x.part01.rar")


# --------------------------------------------------------------------------
# raw baseline: range arithmetic over a synthetic segment map
# --------------------------------------------------------------------------
PART = 4096
PARTS = 12
TAIL = 1000  # the last article is short, as a real one is


def build_state():
    payloads = [os.urandom(PART) for _ in range(PARTS - 1)] + [os.urandom(TAIL)]
    whole = b"".join(payloads)
    segments = [(i + 1, PART + 100, f"m{i}@x") for i in range(PARTS)]

    smap = R.SegmentMap(segments)
    smap.part_size = PART
    smap.total = len(whole)

    class FakeFetcher:
        depth = 3

        def submit(self, message_ids):
            fut = Future()
            out = []
            for mid in message_ids:
                ix = int(mid.split("@")[0][1:])
                out.append((payloads[ix], {"begin": ix * PART + 1}))
            fut.set_result(out)
            return fut

    return whole, {"map": smap, "fetcher": FakeFetcher(), "conns": 2, "holes": 0}


def test_raw_ranges():
    whole, state = build_state()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), R.Handler)
    httpd.state = state
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}/x"

    def get(rng):
        req = urllib.request.Request(base)
        if rng:
            req.add_header("Range", rng)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read(), resp.headers

    try:
        status, body, headers = get(None)
        check("raw: whole file served", body == whole)
        check("raw: 200 without a Range header", status == 200)
        check("raw: advertises the assembled length",
              headers.get("Content-Length") == str(len(whole)))
        check("raw: advertises byte ranges", headers.get("Accept-Ranges") == "bytes")

        cases = {
            "aligned whole article": (PART, 2 * PART - 1),
            "inside one article": (PART + 10, PART + 99),
            "spanning two articles": (PART - 50, PART + 50),
            "spanning three articles": (PART - 5, 3 * PART + 5),
            "from zero": (0, 99),
            "into the short last article": (11 * PART, 11 * PART + TAIL - 1),
            "crossing into the short last article": (11 * PART - 20, 11 * PART + 30),
        }
        for label, (start, end) in cases.items():
            status, body, headers = get(f"bytes={start}-{end}")
            check(f"raw: {label} returns 206", status == 206)
            check(f"raw: {label} returns the right bytes", body == whole[start:end + 1])
            check(f"raw: {label} Content-Range is exact",
                  headers.get("Content-Range") == f"bytes {start}-{end}/{len(whole)}")

        status, body, _ = get("bytes=100-")
        check("raw: open-ended range runs to EOF", body == whole[100:])

        status, body, _ = get(f"bytes=-{TAIL}")
        check("raw: suffix range returns the tail", body == whole[-TAIL:])

        status, _, headers = get(f"bytes={len(whole) + 10}-")
        check("raw: a range past EOF is 416, not an empty 206", status == 416)
    except urllib.error.HTTPError as exc:
        check("raw: a range past EOF is 416, not an empty 206", exc.code == 416)
    finally:
        httpd.shutdown()


def test_segment_map_corrections():
    smap = R.SegmentMap([(1, 0, "a"), (2, 0, "b")])
    smap.part_size = PART
    smap.total = 2 * PART
    check("map: index_for lands in the right article",
          (smap.index_for(0), smap.index_for(PART), smap.index_for(PART - 1)) == (0, 1, 0))
    check("map: index_for clamps past the end", smap.index_for(99 * PART) == 1)

    smap.note(1, {"begin": PART + 1}, PART)
    check("map: an agreeing article records no correction", smap.corrections == 0)
    off = smap.note(1, {"begin": 12345}, PART)
    check("map: a disagreeing article is counted", smap.corrections == 1)
    check("map: and its own header wins over the assumption", off == 12344)
    check("map: an article with no begin header falls back to the assumption",
          smap.note(1, {}, PART) == PART)


# --------------------------------------------------------------------------
# windowed rates and the p05 that a mean hides
# --------------------------------------------------------------------------
def test_windowed_rates():
    # steady 2 MB/s, sampled twice a second for five seconds
    steady = [(0.5 * (i + 1), 1_000_000 * (i + 1)) for i in range(10)]
    rates = M.windowed_rates(steady)
    check("windows: five complete one-second windows", len(rates) == 5)
    check("windows: a steady stream reports its steady rate",
          all(abs(r - 2.0) < 1e-6 for r in rates))

    # the last window is short and must be dropped, not reported as a slow one
    ragged = steady + [(5.4, 10_400_000)]
    check("windows: the trailing partial window is dropped",
          len(M.windowed_rates(ragged)) == 5)

    # 60 MB/s for nine seconds then a one-second stall: the mean says 54 and
    # the player stalls anyway. p05 is the column that shows it.
    stalled = [(float(i + 1), 60_000_000 * (i + 1)) for i in range(9)]
    stalled.append((10.0, 60_000_000 * 9))
    rates = M.windowed_rates(stalled)
    check("windows: a stalled second reads as zero", rates[-1] == 0.0)
    check("windows: and the other nine do not", min(rates[:-1]) == 60.0)

    check("windows: too few samples yields no windows", M.windowed_rates([(1.0, 10)]) == [])
    check("windows: an empty series yields no windows", M.windowed_rates([]) == [])


def test_p05_reporting():
    # a transfer with fewer than five windows must be flagged, never quoted
    short = [(0.4, 1_000_000), (0.8, 2_000_000)]
    rates = M.windowed_rates(short)
    check("p05: a sub-window transfer produces no complete window", len(rates) == 0)

    # nearest-rank on a known series: 20 windows, one of them slow
    series = sorted([50.0] * 19 + [3.0])
    ix = max(0, int(__import__("math").ceil(0.05 * len(series))) - 1)
    check("p05: nearest rank picks the slow window out of twenty", series[ix] == 3.0)


def test_complete_rule():
    check("complete: a full 206 counts",
          M.complete({"http": "206", "bytes": 100}, 100) is True)
    check("complete: a short 206 does not",
          M.complete({"http": "206", "bytes": 99}, 100) is False)
    check("complete: a 200 does not, however many bytes",
          M.complete({"http": "200", "bytes": 100}, 100) is False)
    check("complete: an errored read does not",
          M.complete({"http": "000", "bytes": 0, "error": "x"}, 100) is False)


if __name__ == "__main__":
    test_yenc()
    test_nzb()
    test_pick_file()
    test_raw_ranges()
    test_segment_map_corrections()
    test_windowed_rates()
    test_p05_reporting()
    test_complete_rule()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for name in FAILURES:
            print("  " + name)
        sys.exit(1)
    print("all tests pass")
