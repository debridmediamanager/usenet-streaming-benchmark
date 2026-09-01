#!/usr/bin/env python3
"""Damage-repair timeline: does a server rebuild the missing span in background?
Runs after corpus5b damage phase imported ToyStory5Damaged everywhere.
Per target: start, read the 4 MB hole at t0, +2, +4, +6, +8 minutes while the
server STAYS UP (zurg repaired by t+4 in round 4; InfiniDysk now has repairs on).
"""
import json, sys, time
sys.path.insert(0, "/home/ben/bench")
from bench5 import SPEC, start, stop, stop_all  # noqa: E402
from reprobe_r7 import pick_video, wait_for_release
from corpus5b import ROOT, walk, leaf, probe, head_size, TESTS  # noqa: E402
TARGETS = ["zurg", "decypharr", "altmount", "infinidysk", "nzbdav-og"]
def main():
    cfg = TESTS["damage"]
    out = []
    stop_all()
    for name in TARGETS:
        rec = {"target": name, "reads": []}
        start(name)
        # One listing 6 s after start read "still loading" as "never imported".
        rel, _, waited = wait_for_release(name, cfg["stem"])
        vid = None
        if rel:
            rec["listed_after_s"] = waited
            files, _ = walk(name, rel)
            # Not the first video: a damaged release carrying Sample/ lists the
            # 9 MB clip first on servers that keep the archive's structure, so
            # the 4 MB read at 80 MB would probe the sample and 416.
            vid = pick_video(name, files)
        else:
            rec["absent_after_s"] = waited
        rec["video"] = leaf(vid) if vid else None
        if not vid:
            rec["error"] = "release or video not found"
            stop(name); out.append(rec); continue
        rec["content_length"] = head_size(name, vid)
        t0 = time.time()
        for i in range(5):
            r = probe(name, vid, cfg["off"], cfg["len"])
            r["t"] = round((time.time() - t0) / 60, 2)
            rec["reads"].append(r)
            print(json.dumps({"target": name, **r})[:400], flush=True)
            if i < 4:
                time.sleep(120)
        stop(name)
        out.append(rec)
        json.dump(out, open("/home/ben/bench/results_damage_timeline_r7.json", "w"), indent=1)
    print("TIMELINE_DONE")
if __name__ == "__main__":
    main()
