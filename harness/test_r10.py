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
import math
import os
import sys
import threading
import time
import urllib.request
import zlib
from concurrent.futures import Future
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corpus_r10 as C        # noqa: E402
import damage_r10 as D        # noqa: E402
import expect_r10 as X        # noqa: E402
import metrics_r10 as M       # noqa: E402
import nntp_r10 as N          # noqa: E402
import procmon_r10 as P       # noqa: E402
import rawserve_r10 as R      # noqa: E402
import targets_r10 as T       # noqa: E402

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
    ix = max(0, int(math.ceil(0.05 * len(series))) - 1)
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


# --------------------------------------------------------------------------
# CPU shape and memory drift
# --------------------------------------------------------------------------
def samples(cores, rss_kb=200_000):
    return [(float(i), c, rss_kb) for i, c in enumerate(cores)]


def test_cpu_shape():
    hum = P.summarise(samples([0.5] * 10), cpu_total_s=5.0)
    check("shape: a steady engine reports its level as p95", hum["cores_p95"] == 0.5)
    check("shape: and sits at its peak the whole time", hum["steady_pct"] == 100)

    # same CPU total, spent in one spike: the average is calm and the box is not
    burst = P.summarise(samples([0.0] * 9 + [2.0]), cpu_total_s=2.0)
    check("shape: a bursty engine's worst second is visible", burst["cores_max"] == 2.0)
    check("shape: and its steady share is low", burst["steady_pct"] == 10)
    check("shape: two engines with the same total have different shapes",
          hum["cpu_s"] != burst["cpu_s"] or hum["steady_pct"] != burst["steady_pct"])

    short = P.summarise(samples([1.0, 1.0]), cpu_total_s=2.0)
    check("shape: a read too short for a shape is skipped, not computed",
          "shape_skipped" in short and "cores_p95" not in short)

    per_gib = P.summarise(samples([1.0] * 10), cpu_total_s=10.0,
                          bytes_delivered=2 * (1 << 30))
    check("shape: cpu per GiB divides by delivered bytes",
          per_gib["cpu_s_per_GiB"] == 5.0)

    # a target that restarts mid-window makes the tick counter go backwards;
    # a negative core count would be printed as fact, so it is clamped
    shrinking = {"n": 0}

    def falling_ticks(_pids):
        shrinking["n"] += 1
        return max(0, 1000 - shrinking["n"] * 100)

    monitor = P.Sampler(lambda: [1], interval=0.05, cpu_fn=falling_ticks,
                        rss_fn=lambda p: 1000)
    monitor.start()
    time.sleep(0.35)
    out = monitor.stop()
    check("shape: a restart mid-window never reports negative cores",
          all(c >= 0 for _, c, _ in monitor.samples))
    check("shape: nor negative total cpu", out["cpu_s"] >= 0)


def test_memory_drift():
    mem = P.RunMemory()
    for peak in [100, 110, 120, 130, 140, 150, 160, 170, 190]:
        mem.record(peak)
    mem.idle_rss_MB = 40
    mem.after_idle_MB = 95
    out = mem.summary()
    check("memory: per-read figure is the median of the peaks",
          out["rss_per_read_MB"] == 140)
    check("memory: run peak is the high-water mark", out["rss_peak_MB"] == 190)
    check("memory: the peak states how many reads it was taken over",
          out["peak_over_reads"] == 9)
    check("memory: drift is the last third minus the first", out["drift_MB"] == 60)
    check("memory: idle footprint is carried", out["idle_rss_MB"] == 40)
    check("memory: what it gives back on idle is carried",
          out["after_idle_MB"] == 95)

    thin = P.RunMemory()
    thin.record(100)
    thin.record(200)
    check("memory: too few reads for a drift is skipped, not computed",
          "drift_skipped" in thin.summary())

    flat = P.RunMemory()
    for peak in [500, 500, 500, 500, 500, 500]:
        flat.record(peak)
    check("memory: an engine that holds steady drifts by zero",
          flat.summary()["drift_MB"] == 0)


def test_sampler_uses_live_pid_set():
    # the pid set is re-read every tick, so a helper forked mid-read is counted
    calls = {"n": 0}

    def pids():
        calls["n"] += 1
        return [1, 2] if calls["n"] > 1 else [1]

    monitor = P.Sampler(pids, interval=0.05, cpu_fn=lambda p: len(p) * 100,
                        rss_fn=lambda p: len(p) * 1000)
    monitor.start()
    time.sleep(0.4)
    out = monitor.stop()
    check("sampler: re-reads the process set every tick", calls["n"] > 2)
    check("sampler: counts a process that appeared mid-read",
          out.get("rss_peak_MB", 0) >= 1)


# --------------------------------------------------------------------------
# the negative tier: derivation must be exact and deterministic
# --------------------------------------------------------------------------
SAMPLE_NZB = """<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">
 <file poster="p" subject='rel [1/4] - "x.part01.rar" yEnc'>
  <segments>
   <segment bytes="10" number="1">a1@x</segment>
   <segment bytes="10" number="2">a2@x</segment>
   <segment bytes="10" number="3">a3@x</segment>
   <segment bytes="10" number="4">a4@x</segment>
   <segment bytes="10" number="5">a5@x</segment>
   <segment bytes="10" number="6">a6@x</segment>
  </segments>
 </file>
 <file poster="p" subject='rel [2/4] - "x.part02.rar" yEnc'>
  <segments><segment bytes="10" number="1">b1@x</segment></segments>
 </file>
 <file poster="p" subject='rel [3/4] - "x.part03.rar" yEnc'>
  <segments><segment bytes="10" number="1">c1@x</segment></segments>
 </file>
 <file poster="p" subject='rel [4/4] - "x.vol00+01.par2" yEnc'>
  <segments><segment bytes="10" number="1">d1@x</segment></segments>
 </file>
</nzb>
"""


def write_sample(tmpdir, name="FatherBrown.nzb"):
    os.makedirs(tmpdir, exist_ok=True)
    path = os.path.join(tmpdir, name)
    with open(path, "w") as handle:
        handle.write(SAMPLE_NZB)
    return path


def test_corpus_derivation():
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="r10corpus")
    out = os.path.join(tmp, "derived")
    try:
        write_sample(tmp)
        write_sample(tmp, "ToyStory5.nzb")

        # dead post: every id rewritten, none of the originals survive
        path, detail = C.derive(C.BY_ID["dead-post"], tmp, out)
        files = N.parse_nzb(path)
        ids = [s[2] for f in files for s in f["segments"]]
        check("negative: dead-post rewrites every message id",
              detail["segments_rewritten"] == 9 and len(ids) == 9)
        check("negative: no original id survives",
              not any(i.endswith("@x") for i in ids))
        check("negative: every rewritten id is unique", len(set(ids)) == 9)

        # determinism: two people deriving this get identical bytes
        path2, detail2 = C.derive(C.BY_ID["dead-post"], tmp,
                                  os.path.join(tmp, "derived2"))
        check("negative: derivation is deterministic",
              detail["sha256"] == detail2["sha256"])

        # incomplete set: volume 3 gone, the rest intact
        path, detail = C.derive(C.BY_ID["incomplete-archive-set"], tmp, out)
        subs = [f["subject"] for f in N.parse_nzb(path)]
        check("negative: incomplete-set removes exactly one volume",
              len(detail["files_removed"]) == 1)
        check("negative: and it is the named one",
              not any("part03" in s for s in subs))
        check("negative: the other volumes stay",
              sum("part0" in s for s in subs) == 2)
        check("negative: the par2 file stays", any(".par2" in s for s in subs))

        # decimate: keep every third content article, leave par2 alone
        path, detail = C.derive(C.BY_ID["damaged-severe"], tmp, out)
        files = N.parse_nzb(path)
        by_sub = {f["subject"]: f for f in files}
        big = next(f for s, f in by_sub.items() if "part01" in s)
        par2 = next(f for s, f in by_sub.items() if ".par2" in s)
        check("negative: decimate keeps every third article",
              len(big["segments"]) == 2)
        # 6 + 1 + 1 content articles, keeping indices 0 and 3 of the first file
        # and index 0 of each single-article file; the par2 file is untouched
        check("negative: and reports what it dropped",
              detail["segments_dropped"] == 4 and detail["segments_kept"] == 4)
        check("negative: par2 volumes are left intact", len(par2["segments"]) == 1)

        # a missing volume is a loud failure, not a silently unchanged file
        broken = dict(C.BY_ID["incomplete-archive-set"])
        broken["derive"] = {"op": "drop_volume", "from": "FatherBrown.nzb",
                            "volume": 9}
        try:
            C.derive(broken, tmp, out)
            check("negative: an absent volume raises rather than no-ops", False)
        except SystemExit:
            check("negative: an absent volume raises rather than no-ops", True)

        rows = C.manifest(tmp, out)
        need_post = [r for r in rows if r.get("needs_real_post")]
        check("negative: entries needing a real post are registered, not omitted",
              len(need_post) == 2)
        check("negative: and are marked unavailable rather than missing",
              all(r["available"] is False for r in need_post))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# expectation scoring
# --------------------------------------------------------------------------
def test_judge_served():
    good = {"http": "206", "bytes": 16 << 20, "accept_ranges": "bytes"}
    served, _ = X.judge_served(good, 16 << 20)
    check("judge: a full 206 of real size counts as served", served is True)

    clip = {"http": "200", "bytes": 420_000, "accept_ranges": "none"}
    served, reason = X.judge_served(clip, 16 << 20)
    check("judge: a status clip is not served", served is False)
    check("judge: and says why it was rejected", "accept-ranges" in reason)

    tiny = {"http": "206", "bytes": 100_000, "accept_ranges": "bytes"}
    served, reason = X.judge_served(tiny, 16 << 20)
    check("judge: a sliver below the absolute floor is not served", served is False)
    check("judge: and names the floor", "floor" in reason)

    short = {"http": "206", "bytes": 8 << 20, "accept_ranges": "bytes"}
    served, reason = X.judge_served(short, 16 << 20)
    check("judge: half the requested range is not served", served is False)

    missing = {"http": "404", "bytes": 0}
    served, reason = X.judge_served(missing, 16 << 20)
    check("judge: a 404 is not served", served is False)
    check("judge: and is distinguishable from a clip", "404" in reason)

    aborted = {"http": "206", "bytes": 0, "error": "stream aborted after 0 bytes"}
    served, reason = X.judge_served(aborted, 16 << 20)
    check("judge: a truncated stream is not served", served is False)


def test_expect_matrix():
    want_serve = {"id": "e", "tier": "core", "expect": "serve"}
    want_reject = {"id": "n", "tier": "negative", "expect": "reject"}
    ok = {"http": "206", "bytes": 16 << 20, "accept_ranges": "bytes"}
    no = {"http": "404", "bytes": 0}

    check("expect: should serve and did -> pass",
          X.score(want_serve, ok, 16 << 20)["outcome"] == X.PASS)
    check("expect: should serve and did not -> FAIL",
          X.score(want_serve, no, 16 << 20)["outcome"] == X.FAIL)
    check("expect: should refuse and did -> refused",
          X.score(want_reject, no, 16 << 20)["outcome"] == X.REFUSED)
    check("expect: should refuse and served anyway -> WRONGLY SERVED",
          X.score(want_reject, ok, 16 << 20)["outcome"] == X.WRONGLY_SERVED)

    skipped = X.score({"id": "z", "expect": "reject", "needs_real_post": True},
                      no, 16 << 20)
    check("expect: an entry with no post is skipped, not scored as a refusal",
          skipped["outcome"] is None)


def test_tally():
    rows = [
        {"target": "a", "entry": "1", "outcome": X.PASS},
        {"target": "a", "entry": "2", "outcome": X.REFUSED},
        {"target": "a", "entry": "3", "outcome": X.FAIL},
        # b differs from a on exactly one entry: it served what a refused
        {"target": "b", "entry": "1", "outcome": X.PASS},
        {"target": "b", "entry": "2", "outcome": X.WRONGLY_SERVED},
        {"target": "b", "entry": "3", "outcome": X.FAIL},
        {"target": "b", "entry": "4", "outcome": None},
    ]
    out = X.tally(rows)
    check("tally: correct counts pass and refused together",
          out["a"]["correct"] == 2 and out["a"]["graded"] == 3)
    check("tally: a wrongly served entry is counted on its own",
          out["b"][X.WRONGLY_SERVED] == 1)
    check("tally: and is never folded into the correct count",
          out["b"]["correct"] == 1)
    check("tally: a skipped entry does not grade",
          out["b"]["skipped"] == 1 and out["b"]["graded"] == 3)
    check("tally: refusing correctly beats serving wrongly",
          out["a"]["correct_pct"] > out["b"]["correct_pct"])

    grid = X.matrix(rows)
    check("matrix: one row per entry, one column per target",
          grid["1"]["a"] == X.PASS and grid["1"]["b"] == X.PASS)


# --------------------------------------------------------------------------
# damage classification
# --------------------------------------------------------------------------
def test_zero_run():
    check("damage: a clean buffer has no zero run", D.zero_run(b"\x01\x02\x03") == 0)
    check("damage: an all-zero buffer runs its whole length",
          D.zero_run(b"\x00" * 500) == 500)
    check("damage: the longest run wins, not the first",
          D.zero_run(b"\x00\x01" + b"\x00" * 9 + b"\x01") == 9)
    check("damage: zeros inside real video do not read as a fill",
          D.zero_run(bytes([0, 1, 0, 2, 0, 3])) == 1)


def test_damage_classification():
    hole_start, hole_len = 1000, 100
    hole_end = hole_start + hole_len
    band_start = 0

    truncated = {"bytes": 900, "requested": 1200}
    verdict, _ = D.classify(truncated, hole_start, hole_end, band_start)
    check("damage: a read that stops before the gap is a truncation",
          verdict == "truncated-at-hole")

    errored = {"bytes": 0, "error": "stream aborted after 0 bytes"}
    verdict, _ = D.classify(errored, hole_start, hole_end, band_start)
    check("damage: no bytes at all is an error at the hole",
          verdict == "error-at-hole")

    spanned = {"bytes": 1200, "requested": 1200}
    verdict, _ = D.classify(spanned, hole_start, hole_end, band_start)
    check("damage: a complete read spans the gap and defers to the body",
          verdict == "spans-hole")

    partial = {"bytes": 1150, "requested": 1200}
    verdict, _ = D.classify(partial, hole_start, hole_end, band_start)
    check("damage: a read that got past the gap but fell short is truncated",
          verdict == "truncated-at-hole")

    late = {"bytes": 1150, "requested": 1200, "error": "reset"}
    verdict, _ = D.classify(late, hole_start, hole_end, band_start)
    check("damage: an error after the gap is not an error at it",
          verdict == "aborted-past-hole")


# --------------------------------------------------------------------------
# the target registry
# --------------------------------------------------------------------------
def test_registry():
    required = ("kind", "role", "serve_mode", "import_mode", "port", "verified")
    missing = {n: [k for k in required if k not in s]
               for n, s in T.TARGETS.items()}
    check("targets: every entry carries the keys a run needs",
          not any(missing.values()))
    check("targets: serve modes are one of the two families",
          all(s["serve_mode"] in (T.WEBDAV, T.HTTP_RANGE)
              for s in T.TARGETS.values()))

    ports = [s["port"] for s in T.TARGETS.values()]
    check("targets: no two targets share a port", len(ports) == len(set(ports)))

    check("targets: the default field is all registered",
          all(n in T.TARGETS for n in T.DEFAULT))
    check("targets: comet is off by default, so a round does not hang on it",
          "comet" not in T.enabled())
    check("targets: but it is still registered rather than deleted",
          "comet" in T.TARGETS)

    check("targets: raw is a ceiling, not a competitor",
          T.TARGETS["raw"]["role"] == "ceiling")
    check("targets: and it is the only one",
          [n for n, s in T.TARGETS.items() if s["role"] == "ceiling"] == ["raw"])

    # a table must never rank a mount against an addon on import
    mounts = T.comparable(T.DEFAULT, T.WEBDAV)
    addons = T.comparable(T.DEFAULT, T.HTTP_RANGE)
    check("targets: the two families do not overlap",
          not (set(mounts) & set(addons)))
    check("targets: and together they are the whole field",
          sorted(mounts + addons) == sorted(T.enabled(T.DEFAULT))
          or set(mounts + addons) == set(T.DEFAULT))
    check("targets: stremthru is measured as a mount, since it serves WebDAV",
          "stremthru" in mounts)
    check("targets: aiostreams is measured as an addon, since it has no PROPFIND",
          "aiostreams" in addons)

    shakedown = T.needs_shakedown()
    check("targets: unproven adapters are declared rather than assumed",
          set(shakedown) == {"nzbdavex", "aiostreams"})
    check("targets: every shakedown target says what is unproven about it",
          all(T.TARGETS[n].get("note") for n in shakedown))


if __name__ == "__main__":
    test_yenc()
    test_nzb()
    test_pick_file()
    test_raw_ranges()
    test_segment_map_corrections()
    test_windowed_rates()
    test_p05_reporting()
    test_complete_rule()
    test_cpu_shape()
    test_memory_drift()
    test_sampler_uses_live_pid_set()
    test_corpus_derivation()
    test_judge_served()
    test_expect_matrix()
    test_tally()
    test_zero_run()
    test_damage_classification()
    test_registry()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for name in FAILURES:
            print("  " + name)
        sys.exit(1)
    print("all tests pass")
