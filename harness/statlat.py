#!/usr/bin/env python3
"""STAT round-trip latency, per host.

altmount refused two releases with 'context deadline exceeded' on its fast-fail
STAT check. Those releases STAT clean, so the question is whether the server
this round moved to answers STAT slower than the one earlier rounds used --
a property of the bench setup, not of altmount. Measured rather than assumed.
"""
import re, socket, ssl, statistics as st, sys, time

USER, PASS = "YOUR_USENET_USERNAME", "YOUR_USENET_PASSWORD"
NZB = "/home/ben/bench/nzbs/Bosch.S01.nzb"
xml = open(NZB, encoding="utf-8", errors="replace").read()
ids = re.findall(r"<segment[^>]*>([^<]+)</segment>", xml)[:60]

for host in sys.argv[1:]:
    try:
        t0 = time.time()
        s = ssl.create_default_context().wrap_socket(
            socket.create_connection((host, 563), timeout=30), server_hostname=host)
        f = s.makefile("rwb")
        f.readline()

        def cmd(c):
            f.write((c + "\r\n").encode()); f.flush()
            return f.readline().decode(errors="replace").strip()

        connect_s = time.time() - t0
        t1 = time.time()
        a = cmd(f"AUTHINFO USER {USER}")
        b = cmd(f"AUTHINFO PASS {PASS}")
        auth_s = time.time() - t1
        if not b.startswith("281"):
            print(f"{host:34} AUTH FAILED {a} | {b}"); continue
        lat = []
        ok = 0
        for mid in ids:
            t2 = time.time()
            r = cmd(f"STAT <{mid}>")
            lat.append((time.time() - t2) * 1000)
            ok += r.startswith("223")
        cmd("QUIT")
        print(f"{host:34} connect {connect_s*1000:6.0f}ms  auth {auth_s*1000:6.0f}ms  "
              f"STAT n={len(lat)} ok={ok}  median {st.median(lat):6.1f}ms  "
              f"mean {st.mean(lat):6.1f}ms  p90 {sorted(lat)[int(len(lat)*0.9)]:6.1f}ms  "
              f"max {max(lat):6.1f}ms")
    except Exception as e:
        print(f"{host:34} ERROR {str(e)[:90]}")
