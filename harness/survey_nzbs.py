#!/usr/bin/env python3
"""Shape + retrievability of every candidate NZB, so the corpus is picked on
measurement rather than on filename.

Shape comes from the XML. Retrievability comes from STATing the first, middle
and last article of every file over one connection -- enough to separate a live
release from a rotted one, and cheap enough to run over a dozen candidates.
A candidate that samples clean is then re-checked in full by stat_all.py.
"""
import glob
import json
import os
import re
import socket
import ssl
import sys
import time

HOST, PORT = "news.news-provider.example", 563
USER, PASS = "YOUR_USENET_USERNAME", "YOUR_USENET_PASSWORD"

ARCHIVE = re.compile(r"\.(part\d+\.rar|rar|r\d\d|7z|7z\.\d+|zip|00\d)$", re.I)
PAR2 = re.compile(r"\.par2$", re.I)
VIDEO = re.compile(r"\.(mkv|mp4|avi|ts|m4v)$", re.I)


def connect():
    s = ssl.create_default_context().wrap_socket(
        socket.create_connection((HOST, PORT), timeout=40), server_hostname=HOST)
    f = s.makefile("rwb")
    f.readline()

    def cmd(c):
        f.write((c + "\r\n").encode())
        f.flush()
        return f.readline().decode(errors="replace").strip()

    r1 = cmd(f"AUTHINFO USER {USER}")
    r2 = cmd(f"AUTHINFO PASS {PASS}")
    if not r2.startswith("281"):
        raise SystemExit(f"auth failed: {r1} | {r2}")
    return s, cmd


def shape(path):
    xml = open(path, encoding="utf-8", errors="replace").read()
    blocks = re.findall(r'<file[^>]*subject="([^"]*)"(.*?)</file>', xml, re.S)
    files = []
    for subj, body in blocks:
        m = re.search(r"&quot;(.*?)&quot;", subj) or re.search(r'"(.*?)"', subj)
        name = m.group(1) if m else subj.strip()[:80]
        ids = re.findall(r"<segment[^>]*>([^<]+)</segment>", body)
        size = sum(int(b) for b in re.findall(r'bytes="(\d+)"', body))
        files.append({"name": name, "ids": ids, "bytes": size})
    n_arch = sum(1 for f in files if ARCHIVE.search(f["name"]))
    n_par2 = sum(1 for f in files if PAR2.search(f["name"]))
    n_vid = sum(1 for f in files if VIDEO.search(f["name"]))
    named = sum(1 for f in files if os.path.splitext(f["name"])[1])
    if any(re.search(r"\.7z", f["name"], re.I) for f in files):
        packing = "7z"
    elif n_arch:
        packing = "rar"
    elif named == 0:
        packing = "obfuscated (no extensions)"
    else:
        packing = "plain"
    return {
        "nzb": os.path.basename(path), "path": path,
        "files": len(files), "articles": sum(len(f["ids"]) for f in files),
        "bytes": sum(f["bytes"] for f in files),
        "packing": packing, "archive_files": n_arch,
        "par2_files": n_par2, "video_files": n_vid,
        "_files": files,
    }


def probe(cmd, s):
    ok = tot = 0
    bad = []
    for f in s["_files"]:
        ids = f["ids"]
        if not ids:
            continue
        for mid in (ids[0], ids[len(ids) // 2], ids[-1]):
            tot += 1
            if cmd(f"STAT <{mid}>").startswith("223"):
                ok += 1
            else:
                bad.append(f["name"][:50])
    return ok, tot, sorted(set(bad))


if __name__ == "__main__":
    paths = []
    for d in sys.argv[1:]:
        paths += sorted(glob.glob(os.path.join(d, "*.nzb")))
    seen, uniq = set(), []
    for p in paths:
        b = os.path.basename(p)
        if b not in seen:
            seen.add(b)
            uniq.append(p)
    sock, cmd = connect()
    out = []
    for p in uniq:
        s = shape(p)
        t0 = time.time()
        ok, tot, bad = probe(cmd, s)
        s.pop("_files")
        s["sampled_ok"] = ok
        s["sampled"] = tot
        s["pct"] = round(100 * ok / tot, 1) if tot else 0
        s["missing_in"] = bad[:6]
        s["probe_s"] = round(time.time() - t0, 1)
        out.append(s)
        print(f"{s['pct']:6.1f}%  {ok:4d}/{tot:<4d}  {s['packing']:26} "
              f"{s['files']:3d}f {s['articles']:6d}a {s['bytes']/1e9:7.2f}GB  "
              f"{s['nzb']}", flush=True)
    cmd("QUIT")
    with open("/home/ben/bench/r6/nzb_survey.json", "w") as f:
        json.dump(out, f, indent=1)
