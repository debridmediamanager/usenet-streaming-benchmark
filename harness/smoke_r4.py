#!/usr/bin/env python3
"""Round-4 smoke: every target starts, lists its root, and serves 1 MB."""
import json
import subprocess
import sys
import time

sys.path.insert(0, "/home/ben/bench")
from bench5 import SPEC, start, stop, stop_all, curl_auth, measure, pids_for  # noqa

TARGETS = ["zurg", "decypharr", "altmount", "infinidysk", "nzbdav-og"]
OFF = 1_500_000_000

stop_all()
out = []
for name in TARGETS:
    t0 = time.time()
    pids = start(name)
    boot = round(time.time() - t0, 1)
    # give a freshly-reset zurg time to import its nzbs/ dir
    grace = 180 if name == "zurg" else 20
    root = SPEC[name]["ready"]
    listing = ""
    for _ in range(grace // 10):
        listing = subprocess.run(
            ["curl", "-s", "--max-time", "60", "-X", "PROPFIND", "-H", "Depth: 1"]
            + curl_auth(name) + [SPEC[name].get("root", root)],
            capture_output=True, text=True).stdout
        if "ToyStory5" in listing or "Toy.Story" in listing:
            break
        time.sleep(10)
    r = measure(name, pids, OFF, 1 << 20, timeout=180)
    r["boot_s"] = boot
    r["sees_corpus"] = ("ToyStory5" in listing or "Toy.Story" in listing)
    r["listing_bytes"] = len(listing)
    stop(name)
    out.append(r)
    print(json.dumps(r), flush=True)

json.dump(out, open("/home/ben/bench/results_smoke_r4.json", "w"), indent=1)
print("SMOKE_DONE")
