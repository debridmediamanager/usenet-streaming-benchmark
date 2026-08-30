#!/usr/bin/env python3
"""Is AltMount's truncation a cold-start effect?

A: fresh start -> immediate 256 MB read.
B: fresh start -> 8 MB warm-up read -> 256 MB read.
Same offsets in both arms, alternating, so the offset cannot explain a split.
"""
import json
import subprocess
import sys

sys.path.insert(0, "/home/ben/bench")
import bench5 as B  # noqa: E402

URL = B.SPEC["altmount"]["url"]
BIG = 256 << 20
WARM = 8 << 20
OFFSETS = [1_200_000_000, 2_200_000_000, 3_200_000_000, 4_200_000_000]


def read(off, length, timeout=600):
    p = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "--max-time", str(timeout),
         "-u", "usenet:usenet",
         "-H", f"Range: bytes={off}-{off + length - 1}",
         "-w", "%{http_code} %{size_download} %{time_total}", URL],
        capture_output=True, text=True, timeout=timeout + 60)
    code, got, t = (p.stdout.split() + ["?", "0", "0"])[:3]
    return p.returncode, code, int(got), float(t)


B.stop_all()
out = []
for off in OFFSETS:
    for arm in ("cold", "warmed"):
        B.start("altmount")
        if arm == "warmed":
            read(off - 100_000_000, WARM)
        rc, code, got, t = read(off, BIG)
        rec = {"arm": arm, "offset": off, "curl_exit": rc, "http": code,
               "got_MB": round(got / (1 << 20), 1), "complete": got == BIG,
               "s": round(t, 2)}
        out.append(rec)
        print(json.dumps(rec), flush=True)
        B.stop("altmount")

with open("/home/ben/bench/results_amcold.json", "w") as f:
    json.dump(out, f, indent=1)

for arm in ("cold", "warmed"):
    rows = [r for r in out if r["arm"] == arm]
    print(f"{arm:7s}: {sum(1 for r in rows if r['complete'])}/{len(rows)} complete")
