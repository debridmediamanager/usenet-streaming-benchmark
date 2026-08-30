#!/usr/bin/env python3
"""Per-server Plex press-play and next-episode summary."""
import glob
import json
import os
import statistics
import sys

d = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
order = ["zurg", "altmount", "infinidysk", "nzbdav-og", "decypharr"]
rows = {}
for f in glob.glob(os.path.join(d, "plex_ttp_*.json")):
    name = os.path.basename(f)[len("plex_ttp_"):-len(".json")]
    rows[name] = json.load(open(f))

print("%-12s %-5s %-9s %-9s %-8s %-8s %s"
      % ("server", "reps", "press", "next", "p_med", "n_med", "decision / notes"))
for s in [x for x in order if x in rows] + [x for x in rows if x not in order]:
    rs = rows[s]
    pp = [r["press_play_s"] for r in rs if r.get("press_play_s") is not None]
    nx = [r["next_ep_s"] for r in rs if r.get("next_ep_s") is not None]
    bad = [r for r in rs if r.get("error") or r.get("ep1_correct") is False
           or (r.get("next_ep_s") is not None and r.get("ep2_correct") is False)]
    dec = {r.get("ep1_decision") for r in rs if r.get("ep1_decision")}
    note = ",".join(sorted(x for x in dec if x))
    if bad:
        note += f"  [{len(bad)}/{len(rs)} suspect]"
    print("%-12s %-5s %-9s %-9s %-8s %-8s %s" % (
        s, f"{len(pp)}/{len(rs)}",
        f"{statistics.mean(pp):.2f}" if pp else "-",
        f"{statistics.mean(nx):.2f}" if nx else "-",
        f"{statistics.median(pp):.2f}" if pp else "-",
        f"{statistics.median(nx):.2f}" if nx else "-",
        note))

print()
print("per-rep detail (press / next, seconds)")
hdr = [x for x in order if x in rows] + [x for x in rows if x not in order]
print("%-8s %s" % ("pair", " ".join("%20s" % h for h in hdr)))
maxreps = max((len(v) for v in rows.values()), default=0)
for i in range(maxreps):
    cells = []
    label = ""
    for h in hdr:
        rs = rows[h]
        if i < len(rs):
            r = rs[i]
            label = f'{r["ep1"]}->{r["ep2"]}'
            pp = r.get("press_play_s")
            nx = r.get("next_ep_s")
            cells.append("%20s" % (f"{pp if pp is not None else '-'} / {nx if nx is not None else '-'}"))
        else:
            cells.append("%20s" % "-")
    print("%-8s %s" % (label or i, " ".join(cells)))
