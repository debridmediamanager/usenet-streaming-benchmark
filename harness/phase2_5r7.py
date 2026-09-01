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


SCRUB_OFFS = [int(x * 1e9) for x in (0.55, 1.30, 1.80, 2.60, 2.90, 3.60, 5.00, 5.90)]


def run(name):
    r = {"target": name}
    pids = start(name)

    # cold open: 1 MB at an untouched offset, first read after start
    ttfb, tot, size, code = timed_range(name, 3_500_000_000, 1 << 20)
    r["cold_open_s"] = round(tot, 3) if tot else None
    r["cold_open_http"] = code

    # ttfb on a large read
    ttfb, tot, size, code = timed_range(name, 4_200_000_000, 64 << 20)
    r["ttfb_s"] = round(ttfb, 3) if ttfb else None
    r["big_read_MBps"] = round(size / tot / 1e6, 2) if tot else 0

    # warm re-read of the exact same range
    ttfb2, tot2, size2, _ = timed_range(name, 4_200_000_000, 64 << 20)
    r["warm_reread_s"] = round(tot2, 3) if tot2 else None

    # scrub: 8 x 2 MB at scattered offsets
    times = []
    for off in SCRUB_OFFS:
        _, tot, size, code = timed_range(name, off, 2 << 20)
        if tot and size:
            times.append(tot)
    r["scrub_median_s"] = round(statistics.median(times), 3) if times else None
    r["scrub_n"] = len(times)

    # ffprobe over HTTP
    r["ffprobe_s"], r["ffprobe_duration"] = ffprobe(name)

    r["rss_MB"] = rss_mb(pids_for(name))
    stop(name)
    print(json.dumps(r), flush=True)
    return r


if __name__ == "__main__":
    targets = sys.argv[1].split(",") if len(sys.argv) > 1 else ALL
    stop_all()
    out = [run(n) for n in targets]
    with open(f"{BENCH}/results_latency_r7.json", "w") as f:
        json.dump(out, f, indent=1)
