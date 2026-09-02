#!/usr/bin/env python3
"""Latency phase for all five targets, same isolation rule as bench5.

Four shapes of read, each on a freshly started server so nothing is warm:
  cold open   - first 1 MB from a fresh start; the press-play number
  ttfb        - time to first byte on a large sequential read
  scrub       - median of 8 x 2 MB reads at scattered offsets
  ffprobe     - full container analysis over HTTP
Also records warm re-read (same 64 MB range twice) and peak RSS.
"""
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, "/home/ben/bench")
from bench5 import SPEC, ALL, BENCH, start, stop, stop_all, curl_auth, pids_for, rss_mb, cpu_ticks, HZ  # noqa: E402


def timed_range(name, off, length, timeout=600):
    cmd = (["curl", "-s", "-o", "/dev/null", "--max-time", str(timeout)]
           + curl_auth(name)
           + ["-H", f"Range: bytes={off}-{off + length - 1}",
              "-w", "%{time_starttransfer} %{time_total} %{size_download} %{http_code}",
              SPEC[name]["url"]])
    try:
        out = subprocess.check_output(cmd, text=True, timeout=timeout + 60).split()
    except Exception as e:
        return None, None, 0, str(e)[:60]
    return float(out[0]), float(out[1]), int(out[2]), out[3]


def auth_url(name):
    a = SPEC[name]["auth"]
    u = SPEC[name]["url"]
    if not a:
        return u
    return u.replace("http://", f"http://{a[0]}:{a[1]}@", 1)


def ffprobe(name, timeout=900):
    t0 = time.time()
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", auth_url(name)],
            capture_output=True, text=True, timeout=timeout)
        dur = out.stdout.strip()
    except Exception as e:
        return round(time.time() - t0, 2), f"ERR {str(e)[:40]}"
    return round(time.time() - t0, 2), dur or "none"


# Every pass must read bytes that no earlier pass touched. One target keeps an
# on-disk segment cache which is enabled by default, and against fixed offsets
# its TTFB fell 2.310s -> 0.096s and its big read rose 5.62 -> 74.95 MB/s
# between pass 1 and pass 2. That is the cache being measured and not the
# server. SHIFT moves every offset in this pass into untouched territory. The
# file is 6.6 GB so the scrub points stay inside it.
PASS_IX = int(os.environ.get("PASS_IX", "0"))
SHIFT = PASS_IX * 90_000_000        # 90 MB per pass, far past any read-ahead
COLD_OFF = 3_500_000_000 + SHIFT
BIG_OFF = 4_200_000_000 + SHIFT
SCRUB_OFFS = [int(x * 1e9) + SHIFT for x in (0.55, 1.30, 1.80, 2.60, 2.90, 3.60, 5.00, 5.90)]


def complete(code, size, length):
    # A read is only trustworthy when the server returned 206 for the whole
    # requested range: a partial body or a non-206 reply can finish fast while
    # proving nothing, so those must not flatter the latency numbers.
    return code == "206" and size == length


def run(name):
    r = {"target": name}
    # Each independent read shape runs on its OWN freshly started server so a
    # later shape never inherits the cache or runtime state an earlier one left
    # behind (one target keeps an on-disk segment cache). The extra restarts
    # make the phase slower; that is the correct trade for not measuring a warm
    # cache as if it were cold. RSS is sampled per group and the peak kept, so
    # it is not tied to one arbitrary shape.
    rss_peak = 0

    # (a) cold open: 1 MB at an untouched offset, first read after a fresh start
    start(name)
    ttfb, tot, size, code = timed_range(name, COLD_OFF, 1 << 20)
    r["cold_open_s"] = round(tot, 3) if tot else None
    r["cold_open_http"] = code
    r["cold_open_complete"] = complete(code, size, 1 << 20)
    rss_peak = max(rss_peak, rss_mb(pids_for(name)))
    stop(name)

    # (b) big read then warm re-read, on the SAME instance. The warm re-read is
    # deliberately warm - it re-reads the exact same 64 MB range to measure
    # caching - so no restart may fall between the two.
    start(name)
    ttfb, tot, size, code = timed_range(name, BIG_OFF, 64 << 20)
    r["ttfb_s"] = round(ttfb, 3) if ttfb else None
    r["big_read_MBps"] = round(size / tot / 1e6, 2) if tot else 0
    r["big_read_http"] = code
    r["big_read_complete"] = complete(code, size, 64 << 20)
    ttfb2, tot2, size2, code2 = timed_range(name, BIG_OFF, 64 << 20)
    r["warm_reread_s"] = round(tot2, 3) if tot2 else None
    r["warm_http"] = code2
    r["warm_complete"] = complete(code2, size2, 64 << 20)
    rss_peak = max(rss_peak, rss_mb(pids_for(name)))
    stop(name)

    # (c) scrub: 8 x 2 MB at scattered offsets, fresh server. Only a full 206
    # sample counts toward the median; a short or non-206 reply is dropped so a
    # truncated read cannot masquerade as a fast seek. scrub_attempted records
    # how many were tried, making the drop rate visible.
    start(name)
    times = []
    attempted = 0
    for off in SCRUB_OFFS:
        attempted += 1
        _, tot, size, code = timed_range(name, off, 2 << 20)
        if complete(code, size, 2 << 20):
            times.append(tot)
    r["scrub_median_s"] = round(statistics.median(times), 3) if times else None
    r["scrub_n"] = len(times)
    r["scrub_attempted"] = attempted
    rss_peak = max(rss_peak, rss_mb(pids_for(name)))
    stop(name)

    # (d) ffprobe over HTTP, fresh server; sample RSS here too
    start(name)
    r["ffprobe_s"], r["ffprobe_duration"] = ffprobe(name)
    rss_peak = max(rss_peak, rss_mb(pids_for(name)))
    stop(name)

    r["rss_MB"] = rss_peak
    print(json.dumps(r), flush=True)
    return r


if __name__ == "__main__":
    targets = sys.argv[1].split(",") if len(sys.argv) > 1 else ALL
    stop_all()
    out = [run(n) for n in targets]
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    suffix = f"_{tag}" if tag else ""
    with open(f"{BENCH}/results_latency_r7{suffix}.json", "w") as f:
        json.dump(out, f, indent=1)
