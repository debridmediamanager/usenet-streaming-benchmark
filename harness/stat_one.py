#!/usr/bin/env python3
"""Deep STAT of one file inside an NZB: is it really damaged, or was it misjudged?"""
import re
import socket
import ssl
import sys

HOST, PORT, USER, PASS = "news.news-provider.example", 563, "YOUR_USENET_USERNAME", "YOUR_USENET_PASSWORD"
nzb = open(sys.argv[1], encoding="utf-8", errors="replace").read()
want = sys.argv[2]
n_probe = int(sys.argv[3]) if len(sys.argv) > 3 else 60

target = None
for subj, body in re.findall(r'<file[^>]*subject="([^"]*)"(.*?)</file>', nzb, re.S):
    if want.lower() in subj.lower():
        target = (subj, body)
        break
if not target:
    print("no such file in nzb"); sys.exit(1)

ids = re.findall(r"<segment[^>]*>([^<]+)</segment>", target[1])
name = re.sub(r".*&quot;(.*)&quot;.*", r"\\1", target[0])
print("file:", name[:80])
print(f"segments: {len(ids)}")

step = max(1, len(ids) // n_probe)
sample = ids[::step][:n_probe]
# the first few matter most: that is what a fast-fail check looks at
sample = ids[:8] + sample

s = ssl.create_default_context().wrap_socket(
    socket.create_connection((HOST, PORT), timeout=30), server_hostname=HOST)
f = s.makefile("rwb")


def cmd(c):
    f.write((c + "\r\n").encode()); f.flush()
    return f.readline().decode(errors="replace").strip()


f.readline()
cmd(f"AUTHINFO USER {USER}")
cmd(f"AUTHINFO PASS {PASS}")

bad = []
for i, mid in enumerate(sample):
    r = cmd(f"STAT <{mid}>")
    if not r.startswith("223"):
        bad.append((i, mid, r))
print(f"probed {len(sample)} segments (first 8 + every {step}th): "
      f"{len(sample) - len(bad)} present, {len(bad)} missing")
for b in bad[:10]:
    print("   MISSING", b)

# and prove the first segment actually has a body
r = cmd(f"BODY <{ids[0]}>")
print("BODY on segment 1:", r[:60])
if r.startswith("222"):
    n = 0
    while True:
        line = f.readline()
        if line in (b".\r\n", b".\n", b""):
            break
        n += len(line)
    print(f"  first segment body: {n} bytes")
cmd("QUIT")
