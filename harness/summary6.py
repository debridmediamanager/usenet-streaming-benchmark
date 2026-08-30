#!/usr/bin/env python3
"""Per-rep table + per-target stats, target list taken from the data."""
import collections
import json
import statistics
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/home/ben/bench/six1.log"
rows = [json.loads(l) for l in open(path) if l.strip().startswith("{")]
if path.endswith(".json"):
    rows = json.load(open(path))

errs = [r for r in rows if "error" in r or r.get("http") not in (None, "206")]
if errs:
    print("!!! non-206 / errored measurements:")
    for e in errs:
        print("   ", json.dumps(e)[:220])
    print()

order, seen = [], set()
for r in rows:
    if r["target"] not in seen:
        seen.add(r["target"])
        order.append(r["target"])

by = collections.defaultdict(dict)
for r in rows:
    if "MBps" in r:
        by[r["rep"]][r["target"]] = r["MBps"]

print("per-rep MB/s")
print("%-5s %s" % ("rep", " ".join("%11s" % t for t in order)))
for rep in sorted(by):
    print("%-5d %s" % (rep, " ".join(
        "%11s" % ("%.2f" % by[rep][t] if t in by[rep] else "-") for t in order)))

print()
d = collections.defaultdict(lambda: collections.defaultdict(list))
asked = max((r.get("bytes", 0) for r in rows), default=0)
for r in rows:
    if "MBps" in r:
        d[r["target"]]["mbps"].append(r["MBps"])
        d[r["target"]]["ttfb"].append(r["ttfb_s"])
        d[r["target"]]["cpu"].append(r["cpu_s_per_GB"])
        d[r["target"]]["rss"].append(r["rss_MB"])
        d[r["target"]]["ok"].append(1 if (r.get("http") == "206" and r.get("bytes") == asked) else 0)

print("%-12s %2s %7s %7s %7s %7s %8s %8s %7s %9s"
      % ("target", "n", "mean", "median", "min", "max", "ttfb", "cpuS/GB", "RSS", "complete"))
for k, v in sorted(d.items(), key=lambda x: -statistics.mean(x[1]["mbps"])):
    m = v["mbps"]
    print("%-12s %2d %7.2f %7.2f %7.2f %7.2f %8.2f %8.1f %7.0f %5d/%-3d"
          % (k, len(m), statistics.mean(m), statistics.median(m), min(m), max(m),
             statistics.mean(v["ttfb"]), statistics.mean(v["cpu"]),
             statistics.mean(v["rss"]), sum(v["ok"]), len(v["ok"])))
