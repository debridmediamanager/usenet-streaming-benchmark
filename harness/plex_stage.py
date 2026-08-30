#!/usr/bin/env python3
"""Stage the Plex TV corpus (Bosch S01, 10 x 1080p H.264 mkv) into every server.

One server at a time, same isolation rule as bench5. Records the WebDAV path and
advertised size of every episode so the later symlink farm and Plex library see
an identical tree whichever backend is mounted underneath.
"""
import json
import re
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, "/home/ben/bench")
from bench5 import SPEC, start, stop, stop_all, curl_auth  # noqa: E402
from corpus5b import ROOT, listing, walk, leaf, import_nzb, head_size  # noqa: E402

NZB = "Bosch.S01.nzb"
STEM = "Bosch.S01"
EP = re.compile(r"S01E(\d\d)", re.I)
TARGETS = ["zurg", "decypharr", "altmount", "infinidysk", "nzbdav-og"]


def episodes(name):
    """{episode number: (absolute url, size)} for the Bosch release on `name`."""
    found = {}
    for top in listing(name, ROOT[name]):
        if STEM.lower().replace(".", "") not in leaf(top).lower().replace(".", ""):
            continue
        files, _ = walk(name, top)
        for f in files:
            if not f.lower().endswith(".mkv"):
                continue
            m = EP.search(leaf(f))
            if m:
                found[int(m.group(1))] = f
    return found


def main():
    targets = sys.argv[1:] or TARGETS
    out = {}
    stop_all()
    for name in targets:
        rec = {"target": name}
        t0 = time.time()
        start(name)
        eps = episodes(name)
        if len(eps) < 10:
            rec["import"] = import_nzb(name, NZB)[:200]
            deadline = time.time() + 900
            while time.time() < deadline:
                eps = episodes(name)
                if len(eps) >= 10:
                    break
                time.sleep(20)
        rec["episodes_found"] = len(eps)
        rec["stage_s"] = round(time.time() - t0, 1)
        rec["files"] = {}
        for n in sorted(eps):
            url = eps[n]
            rec["files"][n] = {
                "url": url,
                "path": urllib.parse.unquote(url.split(ROOT[name], 1)[-1])
                if ROOT[name] in url else url,
                "size": head_size(name, url),
            }
        stop(name)
        out[name] = rec
        print(json.dumps(rec, indent=1), flush=True)
        json.dump(out, open("/home/ben/bench/results_plex_stage.json", "w"), indent=1)
    print("STAGE_DONE")


if __name__ == "__main__":
    main()
