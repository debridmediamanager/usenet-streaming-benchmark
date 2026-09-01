#!/usr/bin/env python3
"""What each server publishes once par2 is set aside.

par2 is identified two ways, because that is the whole point: by extension for
the named releases, and by exact byte size for the obfuscated one, where the
parity volumes carry hash names. Sizes come from the corpus XML, not guesswork.
"""
import json, os, re

SRC = os.path.expanduser("/home/ben/bench/r6")
ORDER = ["zurg", "nzbdav-og", "infinidysk", "decypharr", "altmount"]
LABEL = {"zurg":"zurg","nzbdav-og":"nzbdav","infinidysk":"InfiniDysk",
         "decypharr":"decypharr","altmount":"AltMount"}

# byte sizes of the five par2 files, from the NZB XML (same in both releases)
PAR2_BYTES = {4664, 34617664+0, 0}
PAR2_APPROX = [4664, 34.62e6, 69.24e6, 103.86e6, 138.48e6]
VIDEO = re.compile(r"\.(mkv|mp4|avi|ts|m4v)$", re.I)

def is_par2(name, size):
    if name.lower().endswith(".par2"):
        return True
    if VIDEO.search(name) or name.lower().endswith((".jpg",".jpeg",".png",".url",".nfo")):
        return False
    if size:
        for p in PAR2_APPROX:
            if abs(size - p) / max(p, 1) < 0.06:  # decoded files run ~3% under the NZB byte totals (yEnc overhead)
                return True
    return False

def flatten(node, prefix="", out=None):
    out = [] if out is None else out
    for c in node.get("contents", []) or []:
        nm = c.get("name",""); path = f"{prefix}/{nm}" if prefix else nm
        out.append({"path":path,"name":nm,"type":c.get("type"),"size":c.get("size")})
        if c.get("type")=="directory": flatten(c, path, out)
    return out

def load(t):
    doc = json.load(open(f"{SRC}/tree.{t}.json"))
    root = next(n for n in doc if n.get("type")=="directory")
    return flatten(root)

def kind(name):
    if VIDEO.search(name):
        return "sample" if re.search(r"sample", name, re.I) else "media"
    if name.lower().endswith((".jpg",".jpeg",".png")): return "thumbnail"
    if name.lower().endswith(".nfo"): return "nfo"
    if name.lower().endswith(".url"): return "advert"
    return "other"

rows = {}
for t in ORDER:
    ents = load(t)
    files = [e for e in ents if e["type"]=="file"]
    par2 = [e for e in files if is_par2(e["name"], e["size"])]
    keep = [e for e in files if e not in par2]
    counts = {}
    for e in keep:
        counts[kind(e["name"])] = counts.get(kind(e["name"]),0)+1
    rows[t] = {"all":len(files), "par2":len(par2), "keep":len(keep), "c":counts,
               "names":{e["path"] for e in keep}}

print("The corpus contains, excluding par2: 14 media + 3 thumbnails + 1 sample + 1 nfo + 2 adverts = 21\n")
h=f"{'server':12} {'published':>10} {'par2':>6} {'non-par2':>9} | {'media':>6} {'thumb':>6} {'sample':>7} {'nfo':>4} {'advert':>7}"
print(h); print("-"*len(h))
for t in ORDER:
    r=rows[t]; c=r["c"]
    print(f"{LABEL[t]:12} {r['all']:>10} {r['par2']:>6} {r['keep']:>9} | "
          f"{c.get('media',0):>4}/14 {c.get('thumbnail',0):>4}/3 {c.get('sample',0):>5}/1 "
          f"{c.get('nfo',0):>2}/1 {c.get('advert',0):>5}/2")

print("\nAgainst zurg's set (which is the complete non-par2 corpus):")
base = rows["zurg"]["names"]
for t in ORDER[1:]:
    miss = sorted(base - rows[t]["names"])
    extra = sorted(rows[t]["names"] - base)
    print(f"\n  {LABEL[t]}: missing {len(miss)}, extra {len(extra)}")
    for m in miss: print(f"     - {m}")
    for x in extra: print(f"     + {x}")
