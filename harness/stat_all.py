#!/usr/bin/env python3
"""STAT every article in an NZB. Sampling cannot disprove 'one article missing'."""
import re
import socket
import ssl
import sys

HOST, PORT = "news.news-provider.example", 563
USER, PASS = "YOUR_USENET_USERNAME", "YOUR_USENET_PASSWORD"

nzb = open(sys.argv[1], encoding="utf-8", errors="replace").read()
blocks = re.findall(r'<file[^>]*subject="([^"]*)"(.*?)</file>', nzb, re.S)

s = ssl.create_default_context().wrap_socket(
    socket.create_connection((HOST, PORT), timeout=30), server_hostname=HOST)
f = s.makefile("rwb")


def cmd(c):
    f.write((c + "\r\n").encode()); f.flush()
    return f.readline().decode(errors="replace").strip()


f.readline()
cmd(f"AUTHINFO USER {USER}")
cmd(f"AUTHINFO PASS {PASS}")

grand_ok = grand_tot = 0
for subj, body in blocks:
    name = re.sub(r".*&quot;(.*)&quot;.*", r"\1", subj)
    ids = re.findall(r"<segment[^>]*>([^<]+)</segment>", body)
    missing = []
    for i, mid in enumerate(ids):
        if not cmd(f"STAT <{mid}>").startswith("223"):
            missing.append(i + 1)
    grand_ok += len(ids) - len(missing)
    grand_tot += len(ids)
    flag = f"  MISSING at {missing[:6]}" if missing else ""
    print(f"  {len(ids) - len(missing):5d}/{len(ids):<5d} {name[:52]}{flag}", flush=True)

print(f"TOTAL {grand_ok}/{grand_tot} articles present, {grand_tot - grand_ok} missing")
cmd("QUIT")
