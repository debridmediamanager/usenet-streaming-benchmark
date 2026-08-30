#!/usr/bin/env python3
"""Awkward-release phase, corrected.

Two fixes over the first cut: hrefs are resolved to absolute URLs (zurg returns
them relative, everyone else absolute-path), and the release under test is
picked by name rather than "first video in the listing" — otherwise an already
imported release from an earlier run gets probed instead.

Isolation is unchanged: one server alive at a time, imports included.
"""
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, "/home/ben/bench")
from bench5 import SPEC, ALL, BENCH, start, stop, stop_all, curl_auth  # noqa: E402

API_KEY = "benchbenchbenchbenchbenchbench12"

ROOT = {
    "zurg": "http://localhost:9998/dav/all/",
    "decypharr": "http://localhost:8282/webdav/__all__/",
    "altmount": "http://localhost:8081/webdav/complete/",
    "infinidysk": "http://127.0.0.1:8092/content/uncategorized/",
    "nzbdav-og": "http://127.0.0.1:8093/content/uncategorized/",
}

WEBDAV = list(ROOT)

TESTS = {
    # article 21 of 1662 has a corrupted message-id -> server answers 430
    "damage": {"nzb": "ToyStory5Damaged.nzb", "stem": "ToyStory5Damaged",
               "off": 83886080, "len": 4194304},
    "obfuscated": {"nzb": "Obfuscated.nzb", "stem": "Obfuscated",
                   "off": 400 << 20, "len": 8 << 20},
    "rar": {"nzb": "FatherBrown.nzb", "stem": "FatherBrown",
            "off": 100 << 20, "len": 16 << 20},
}


def sh(cmd, timeout=900):
    try:
        return subprocess.run(["bash", "-c", cmd], capture_output=True,
                              text=True, timeout=timeout).stdout.strip()
    except Exception as e:
        return f"ERR {str(e)[:80]}"


def listing(name, url):
    """Absolute child URLs one level under url."""
    cmd = (["curl", "-s", "--max-time", "240", "-X", "PROPFIND", "-H", "Depth: 1"]
           + curl_auth(name) + [url])
    try:
        xml = subprocess.check_output(cmd, text=True, timeout=300)
    except Exception:
        return []
    base = url if url.endswith("/") else url + "/"
    ndepth = len([x for x in urllib.parse.urlparse(base).path.split("/") if x])
    out = []
    for h in re.findall(r"<[Dd]:href>([^<]*)</[Dd]:href>", xml):
        absu = urllib.parse.urljoin(base, h)
        if absu.rstrip("/") == base.rstrip("/"):
            continue
        # A self-reference can come back with a different prefix than the URL
        # asked for -- zurg answers PROPFIND with hrefs under /all/ rather than
        # /dav/all/ -- so identity is not enough. Only something strictly
        # deeper than the collection is a child of it.
        hdepth = len([x for x in urllib.parse.urlparse(absu).path.split("/") if x])
        if hdepth <= ndepth:
            continue
        # zurg also answers PROPFIND on a FILE path by returning that file as a
        # child of itself (.../a.mkv/ -> .../a.mkv/a.mkv), which would make every
        # file look like a directory. A child never repeats its parent's name.
        if (urllib.parse.unquote(absu.rstrip("/").rsplit("/", 1)[-1])
                == urllib.parse.unquote(base.rstrip("/").rsplit("/", 1)[-1])):
            continue
        out.append(absu.rstrip("/"))
    return sorted(set(out))


def leaf(u):
    return urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1])


def walk(name, url, depth=3):
    """(files, dirs) under url. A child that has children is a directory."""
    base = url if url.endswith("/") else url + "/"
    files, dirs = [], []
    for k in listing(name, base):
        sub = listing(name, k + "/") if depth > 1 else []
        if sub:
            dirs.append(k)
            f2, d2 = walk(name, k, depth - 1)
            files += f2
            dirs += d2
        else:
            files.append(k)
    return files, dirs


def import_nzb(name, nzb):
    if name == "zurg":
        sh(f"cp -n {BENCH}/nzbs/{nzb} {BENCH}/zurgrun/nzbs/{nzb}")
        time.sleep(30)
        return "present in nzbs/"
    if name == "altmount":
        r = sh(f"curl -s -X POST 'http://localhost:8081/api/import/file?apikey={API_KEY}' "
               f"-H 'Content-Type: application/json' "
               f"-d '{{\"file_path\":\"{BENCH}/am-nzbs/{nzb}\"}}'")
        time.sleep(55)
        return r[:250]
    if name in ("infinidysk", "nzbdav-og"):
        port, d = ((8092, "id-nzbs") if name == "infinidysk" else (8093, "og-nzbs"))
        r = sh(f"curl -s -X POST 'http://127.0.0.1:{port}/api?mode=addfile&apikey={API_KEY}' "
               f"-F 'nzbFile=@{BENCH}/{d}/{nzb}'")
        time.sleep(55)
        h = sh(f"curl -s 'http://127.0.0.1:{port}/api?mode=history&apikey={API_KEY}'")
        return (r[:120] + " || HIST " + h[:700])
    if name == "decypharr":
        # main-0dd1cbbd: one SAB mock at /sabnzbd/api, upload field is `name`.
        # A wrong field answers {"status": false, "error": "No files uploaded"}
        # with HTTP 200, so check the body, not the status code.
        r = sh(f"curl -s --max-time 300 -X POST 'http://localhost:8282/sabnzbd/api"
               f"?mode=addfile&apikey={API_KEY}&cat=tv' "
               f"-F 'name=@{BENCH}/nzbs/{nzb}'")
        if '"status": false' in r or "No files uploaded" in r:
            return f"decypharr refused the upload: {r[:200]}"
        time.sleep(55)
        return r[:250]
    return "?"


def probe(name, url, off, length, timeout=900):
    tmp = "/tmp/corpus_probe.bin"
    cmd = (["curl", "-s", "-o", tmp, "--max-time", str(timeout)] + curl_auth(name)
           + ["-H", f"Range: bytes={off}-{off + length - 1}",
              "-w", "%{http_code} %{size_download} %{time_total}", url])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
        parts = (p.stdout.split() + ["?", "0", "0"])[:3]
        code, got, t = parts[0], int(parts[1]), float(parts[2])
        rc = p.returncode
    except Exception as e:
        return {"probe_error": str(e)[:120]}
    md5 = allz = None
    if got:
        h = hashlib.md5()
        allz = True
        with open(tmp, "rb") as f:
            while c := f.read(1 << 20):
                h.update(c)
                if allz and any(c):
                    allz = False
        md5, = (h.hexdigest(),)
    return {"curl_exit": rc, "http": code, "bytes": got, "asked": length,
            "complete": got == length, "s": round(t, 2),
            "MBps": round(got / t / 1e6, 2) if t and got else 0,
            "md5": md5, "all_zero": allz}


def head_size(name, url):
    out = sh("curl -s -I --max-time 120 " + " ".join(curl_auth(name)) + f" '{url}'")
    m = re.search(r"[Cc]ontent-[Ll]ength:\s*(\d+)", out)
    return int(m.group(1)) if m else None


def run(test, targets):
    cfg = TESTS[test]
    stop_all()
    out = []
    for name in targets:
        rec = {"target": name, "test": test}
        start(name)
        before = listing(name, ROOT[name])
        rec["import"] = import_nzb(name, cfg["nzb"])
        after = listing(name, ROOT[name])
        new = [u for u in after if u not in before]
        rec["new_entries"] = [leaf(u) for u in new]
        rec["listing"] = [leaf(u) for u in after]

        # the release under test: something new, else a name match on the stem
        cands = new or [u for u in after if cfg["stem"].lower() in leaf(u).lower()]
        rec["release_dir"] = [leaf(u) for u in cands]

        files, subdirs = [], []
        for c in cands:
            f, d = walk(name, c)
            files += f
            subdirs += d
        rec["files"] = [leaf(f) for f in files]
        rec["file_paths"] = [urllib.parse.unquote(f.split(ROOT[name], 1)[-1])
                             if ROOT[name] in f else f for f in files]
        rec["subdirs"] = [urllib.parse.unquote(d.split(ROOT[name], 1)[-1])
                          if ROOT[name] in d else d for d in subdirs]

        vid = next((f for f in files
                    if re.search(r"\.(mkv|mp4|avi|ts|m4v)$", leaf(f), re.I)), None)
        rec["probed_url"] = vid
        if vid:
            rec["content_length"] = head_size(name, vid)
            rec["probe"] = probe(name, vid, cfg["off"], cfg["len"])
        out.append(rec)
        print(json.dumps(rec)[:1800], flush=True)
        stop(name)
        with open(f"{BENCH}/results_{test}.json", "w") as f:
            json.dump(out, f, indent=1)
    with open(f"{BENCH}/results_{test}.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2].split(",") if len(sys.argv) > 2 else WEBDAV)
