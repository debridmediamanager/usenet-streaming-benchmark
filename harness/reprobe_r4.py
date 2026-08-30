#!/usr/bin/env python3
"""Re-probe the three behaviour releases, selecting them BY NAME.

corpus5b picks the release under test as "whatever appeared in the listing
during the import". That is wrong whenever a server is still loading its
library when the baseline listing is taken: a late-arriving unrelated release
looks new and gets probed instead. It put zurg's damage and rar runs on the
Obfuscated release.

Here the release is chosen by an exact stem match, preferring the original
directory over any " (N)" duplicate a re-import created, and nothing is
imported at all.
"""
import json
import sys
import time

sys.path.insert(0, "/home/ben/bench")
from bench5 import start, stop, stop_all  # noqa: E402
from corpus5b import ROOT, listing, walk, leaf, probe, head_size, TESTS  # noqa: E402
import re

TARGETS = ["zurg", "decypharr", "altmount", "infinidysk", "nzbdav-og"]


def pick_release(name, stem):
    """Exact stem directory if present, else the lowest-numbered duplicate."""
    tops = listing(name, ROOT[name])
    exact, dupes = None, []
    for t in tops:
        lf = leaf(t)
        if lf.lower() == stem.lower():
            exact = t
        elif re.fullmatch(re.escape(stem) + r" \(\d+\)", lf, re.I):
            dupes.append(t)
    return exact or (sorted(dupes)[0] if dupes else None), [leaf(t) for t in tops]


def main():
    out = []
    stop_all()
    for phase, cfg in TESTS.items():
        for name in TARGETS:
            rec = {"phase": phase, "target": name}
            start(name)
            time.sleep(6)
            rel, tops = pick_release(name, cfg["stem"])
            rec["chosen_dir"] = leaf(rel) if rel else None
            rec["all_dirs"] = tops
            if rel:
                files, subdirs = walk(name, rel)
                rec["files"] = [leaf(f) for f in files]
                rec["subdirs"] = [leaf(d) for d in subdirs]
                vid = next((f for f in files
                            if re.search(r"\.(mkv|mp4|avi|ts|m4v)$", leaf(f), re.I)), None)
                rec["video"] = leaf(vid) if vid else None
                if vid:
                    rec["content_length"] = head_size(name, vid)
                    rec["probe"] = probe(name, vid, cfg["off"], cfg["len"])
            stop(name)
            out.append(rec)
            print(json.dumps(rec)[:900], flush=True)
            json.dump(out, open("/home/ben/bench/results_reprobe_r4.json", "w"), indent=1)
    print("REPROBE_DONE")


if __name__ == "__main__":
    main()
