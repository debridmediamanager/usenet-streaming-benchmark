### Connection parity, from live sockets

2,083 samples, one every five seconds.

Window: 2026-09-18T04:02:23Z to 2026-09-18T07:39:46Z.

| process | instances | peak sockets per instance |
|---|---:|---:|
| raw reader (`python3`) | 6 | 10 |
| zurg | 1 | 10 |
| AltMount | 1 | 10 |
| InfiniDysk | 2 | 10 |
| NZBDav-og | 2 | 10 |
| decypharr | 1 | 10 |

The raw reader restarts once per entry, which is why it has multiple process
instances. Its per-entry processes are aggregated by benchmark working
directory before applying the budget. The benchmark's separate damage verifier
opened at most one socket and is excluded from competitor parity.

Budget was 10. No target held more, and every target filled it.

**Isolation held:** no sample caught two targets holding the account at once.
Exact parity held: every software target peaked at 10 connections.
