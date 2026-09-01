#!/usr/bin/env python3
"""Turn the round-6 tree dumps into the report's numbers.

Every server is scored against the NZB's own contents, not against the other
servers, so an omission they all share still reads as an omission. The ground
truth below comes from parsing the corpus XML, not from any server's output.
"""
import json
import os
import re
import sys
from collections import Counter

RUN = sys.argv[1] if len(sys.argv) > 1 else "/home/ben/bench/r6"
TARGETS = ["zurg", "altmount", "infinidysk", "nzbdav-og", "decypharr"]
LABEL = {"zurg": "zurg", "altmount": "AltMount", "infinidysk": "InfiniDysk",
         "nzbdav-og": "nzbdav", "decypharr": "decypharr"}

# What each release really is, from the NZB XML.
TRUTH = {
    "ToyStory5": {
        "packing": "plain", "nzb_files": 7, "articles": 1662, "bytes": 7164735989,
        "media": ["Toy.Story.5.2026.1080p.AMZN.WEB-DL.DDP5.1.H.264-KyoGo.mkv"],
        "media_n": 1},
    "Obfuscated": {
        "packing": "obfuscated", "nzb_files": 7, "articles": 1662, "bytes": 7164735989,
        "media": ["Toy.Story.5.2026.1080p.AMZN.WEB-DL.DDP5.1.H.264-KyoGo.mkv"],
        "media_n": 1},
    "FatherBrown": {
        "packing": "rar", "nzb_files": 17, "articles": 1010, "bytes": 394141285,
        "media": ["father.brown.2013.s02e05.hdtv.x264-tla.mp4"], "media_n": 1},
    "MandaloriaREMUX": {
        "packing": "plain", "nzb_files": 9, "articles": 9514, "bytes": 41128806912,
        "media": ["The.Mandalorian.and.Grogu.2026.iNTERNAL.BluRay.1080p.MULTi."
                  "REMUX.AVC.DTS-HD.MA.7.1-Aisha.mkv"], "media_n": 1},
    "Bosch.S01": {
        "packing": "plain", "nzb_files": 20, "articles": 32850, "bytes": 24290014587,
        "media": [f"Bosch.S01E{i:02d}.2015.1080p.Amazon.WEB-DL.AVC.DDP.5.1-DBTV.mkv"
                  for i in range(1, 11)], "media_n": 10},
}
RELEASES = list(TRUTH)

VIDEO = re.compile(r"\.(mkv|mp4|avi|ts|m4v)$", re.I)
PAR2 = re.compile(r"\.par2$", re.I)
ARCHIVE = re.compile(r"(\.part\d+\.rar|\.rar|\.r\d\d|\.7z|\.zip)$", re.I)
URLJUNK = re.compile(r"\.(url|nfo|sfv|txt)$", re.I)
IMAGE = re.compile(r"\.(jpg|jpeg|png|webp)$", re.I)
SAMPLE = re.compile(r"sample", re.I)
# a hash-named leftover: long, no extension the tools recognise
HASHY = re.compile(r"^[A-Za-z0-9_+-]{20,}$")


def flatten(node, prefix="", out=None, depth=0):
    out = [] if out is None else out
    for c in node.get("contents", []) or []:
        name = c.get("name", "")
        path = f"{prefix}/{name}" if prefix else name
        out.append({"path": path, "name": name, "type": c.get("type", "?"),
                    "size": c.get("size"), "depth": depth + 1})
        if c.get("type") == "directory":
            flatten(c, path, out, depth + 1)
    return out


def load(tag):
    f = os.path.join(RUN, f"tree.{tag}.json")
    if not os.path.exists(f):
        return None
    try:
        doc = json.load(open(f))
    except Exception:
        return None
    root = next((n for n in doc if n.get("type") == "directory"), None)
    return flatten(root) if root else None


def classify(name):
    if VIDEO.search(name):
        return "sample" if SAMPLE.search(name) else "video"
    if PAR2.search(name):
        return "par2"
    if ARCHIVE.search(name):
        return "archive"
    if IMAGE.search(name):
        return "image"
    if URLJUNK.search(name):
        return "junk"
    if HASHY.match(name):
        return "hash-named"
    return "other"


def per_release(entries, rel):
    """Everything published under the top-level directory for this release."""
    sub = [e for e in entries if e["path"] == rel or e["path"].startswith(rel + "/")]
    if not sub:
        return None
    files = [e for e in sub if e["type"] == "file"]
    dirs = [e for e in sub if e["type"] == "directory"]
    cls = Counter(classify(e["name"]) for e in files)
    vids = [e for e in files if classify(e["name"]) == "video"]
    truth = TRUTH[rel]
    original = [v for v in vids if v["name"] in truth["media"]]
    empty_dirs = []
    for d in dirs:
        if not any(e["path"].startswith(d["path"] + "/") for e in sub):
            empty_dirs.append(d["path"])
    # a filename welded out of its parent directory's name
    welded = [v["name"] for v in vids
              if any(v["name"].startswith(p) and v["name"] != p
                     for p in [d["name"] for d in dirs] + [rel])
              and v["name"] not in truth["media"]]
    return {
        "present": True,
        "files": len(files),
        "dirs": len(dirs),
        "max_depth": max([e["depth"] for e in sub], default=0),
        "videos": [v["name"] for v in vids],
        "video_n": len(vids),
        "expected_video_n": truth["media_n"],
        "original_names": len(original),
        "names_preserved": len(original) == truth["media_n"],
        "renamed": [v["name"] for v in vids if v["name"] not in truth["media"]],
        "welded_names": welded,
        "empty_dirs": empty_dirs,
        "classes": dict(cls),
    }


def main():
    res = json.load(open(os.path.join(RUN, "results_tree_r6.json")))
    by = {r["target"]: r for r in res}
    out = {"targets": [], "releases": RELEASES, "truth": TRUTH}
    for t in TARGETS:
        entries = load(t)
        r = by.get(t, {})
        reads = {x.get("release"): x for x in (r.get("reads") or [])}
        rec = {
            "target": t, "label": LABEL[t],
            "dav_root": r.get("dav_root"),
            "namespace": r.get("namespace_after") or r.get("namespace_before") or [],
            "settle_s": r.get("settle_s"),
            "ready_s": (r.get("start") or {}).get("ready_s"),
            "imports_accepted": sum(1 for i in r.get("imports", []) if i.get("accepted")),
            "imports_total": len(r.get("imports", [])),
            "refused": [{"nzb": i["nzb"], "why": i["response"][:220]}
                        for i in r.get("imports", []) if not i.get("accepted")],
            "tree_report": (r.get("tree") or {}).get("tree_report"),
            "native_tree_report": (r.get("native_tree") or {}).get("tree_report"),
            "entries_total": len(entries) if entries else 0,
            "releases": {},
        }
        for rel in RELEASES:
            d = per_release(entries, rel) if entries else None
            if d is None:
                d = {"present": False}
            rd = reads.get(rel)
            d["read"] = ({"bytes": rd.get("got_bytes"), "complete": rd.get("complete"),
                          "all_zero": rd.get("all_zero"), "MBps": rd.get("MBps"),
                          "file": rd.get("file")} if rd else None)
            rec["releases"][rel] = d
        rec["published"] = sum(1 for rel in RELEASES if rec["releases"][rel]["present"])
        rec["served"] = sum(1 for rel in RELEASES
                            if (rec["releases"][rel].get("read") or {}).get("complete"))
        out["targets"].append(rec)
    json.dump(out, open(os.path.join(RUN, "report_data.json"), "w"), indent=1)

    w = f"{'server':12} {'imp':>7} {'pub':>5} {'served':>7} {'entries':>8} {'settle':>7}  tree"
    print(w); print("-" * len(w))
    for t in out["targets"]:
        print(f"{t['label']:12} {t['imports_accepted']}/{t['imports_total']:<5} "
              f"{t['published']}/5{'':<1} {t['served']}/5{'':<3} {t['entries_total']:>8} "
              f"{str(t['settle_s'])+'s':>7}  {t['tree_report']}")
    print()
    hdr = f"{'release':17} " + " ".join(f"{LABEL[t]:>11}" for t in TARGETS)
    print(hdr); print("-" * len(hdr))
    for rel in RELEASES:
        row = f"{rel:17} "
        for t in TARGETS:
            d = next(x for x in out["targets"] if x["target"] == t)["releases"][rel]
            if not d["present"]:
                cell = "absent"
            else:
                cell = f"{d['video_n']}v/{d['files']}f"
                if not d["names_preserved"]:
                    cell += "*"
            row += f"{cell:>11} "
        print(row)
    print("\n* media filename differs from the name in the NZB")


if __name__ == "__main__":
    main()
