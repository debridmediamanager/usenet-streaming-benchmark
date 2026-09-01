#!/usr/bin/env python3
"""Per-rep table + per-target stats, target list taken from the data."""
import collections
import json
import statistics
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/home/ben/bench/six1.log"
if path.endswith(".json"):
    # The line-by-line parse must not run first: the harness writes indent=1
    # JSON, whose "  {" lines pass the startswith filter and crash json.loads
    # before this branch was ever reached.
    rows = json.load(open(path))
else:
    rows = [json.loads(l) for l in open(path) if l.strip().startswith("{")]

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
    elif "error" in r:
        # A curl timeout/failure carries no MBps, so it used to drop out of the
        # stats entirely: a target erroring on 2 of 6 reads printed its mean
        # over the 4 survivors and "6/6"-shaped completion of 4/4 -- the read
        # that never came back scored the same as a read never attempted.
        # It gets no rate (there is none to average), but it does get counted.
        d[r["target"]]["ok"].append(0)
        d[r["target"]]["err"].append(1)

# Column stays off for clean data so the usual table is byte-identical.
anyerr = any(v["err"] for v in d.values())
print("%-12s %2s %7s %7s %7s %7s %8s %8s %7s %9s%s"
      % ("target", "n", "mean", "median", "min", "max", "ttfb", "cpuS/GB", "RSS",
         "complete", " %6s" % "errors" if anyerr else ""))
# A target whose every read errored has no mean to sort on; park it last.
for k, v in sorted(d.items(),
                   key=lambda x: -statistics.mean(x[1]["mbps"]) if x[1]["mbps"] else float("inf")):
    m = v["mbps"]
    tail = " %6d" % len(v["err"]) if anyerr else ""
    if not m:
        print("%-12s %2d %7s %7s %7s %7s %8s %8s %7s %5d/%-3d%s"
              % (k, 0, "-", "-", "-", "-", "-", "-", "-", 0, len(v["ok"]), tail))
        continue
    print("%-12s %2d %7.2f %7.2f %7.2f %7.2f %8.2f %8.1f %7.0f %5d/%-3d%s"
          % (k, len(m), statistics.mean(m), statistics.median(m), min(m), max(m),
             statistics.mean(v["ttfb"]), statistics.mean(v["cpu"]),
             statistics.mean(v["rss"]), sum(v["ok"]), len(v["ok"]), tail))
