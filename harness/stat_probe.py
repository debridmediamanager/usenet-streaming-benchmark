#!/usr/bin/env python3
"""STAT a sample of an NZB's articles to prove the release is still on the server."""
import random
import re
import ssl
import sys
import socket

HOST, PORT = "news.news-provider.example", 563
USER, PASS = "YOUR_USENET_USERNAME", "YOUR_USENET_PASSWORD"

nzb = open(sys.argv[1], encoding="utf-8", errors="replace").read()

files = re.findall(r'<file[^>]*subject="([^"]*)".*?</file>', nzb, re.S)
blocks = re.findall(r'<file[^>]*subject="([^"]*)"(.*?)</file>', nzb, re.S)

sock = socket.create_connection((HOST, PORT), timeout=30)
sock = ssl.create_default_context().wrap_socket(sock, server_hostname=HOST)
f = sock.makefile("rwb")


def cmd(c):
    f.write((c + "\r\n").encode())
    f.flush()
    return f.readline().decode(errors="replace").strip()


print("greet:", f.readline().decode(errors="replace").strip())
print("user:", cmd(f"AUTHINFO USER {USER}"))
print("pass:", cmd(f"AUTHINFO PASS {PASS}"))

random.seed(4)
total_ok = total = 0
for subj, body in blocks:
    name = re.sub(r".*&quot;(.*)&quot;.*", r"\1", subj)
    ids = re.findall(r"<segment[^>]*>([^<]+)</segment>", body)
    if not ids:
        continue
    # first, middle and last article of every file
    sample = [ids[0], ids[len(ids) // 2], ids[-1]]
    ok = sum(1 for mid in sample if cmd(f"STAT <{mid}>").startswith("223"))
    total_ok += ok
    total += len(sample)
    print(f"  {ok}/{len(sample)}  {len(ids):5d} arts  {name[:70]}")

print(f"TOTAL {total_ok}/{total} sampled articles present")
cmd("QUIT")
