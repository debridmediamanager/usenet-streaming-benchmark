# Round 8 — independent run on Hetzner dedicated hardware

Measured 2 September 2026 on a Hetzner Cloud **CCX23** (4 dedicated vCPU, 16 GB RAM, 160 GB disk) in Nuremberg (nbg1), provisioned fresh for this run and destroyed after. The same isolation rules as round 7: one server holds the news account at a time, every target on 20 NNTP connections, repair enabled wherever the feature exists.

This run used the corrected harness from the `harness-fixes` branch (the round-7 harness bugs fixed), built every target from **current main** on the day of the run, and streamed the same corpus from the same news account as round 7.

## Not comparable to round 7 in absolute terms

Round 7 ran on zen — 2 shared cores, 7.6 GB. This ran on 4 **dedicated** cores. The README's own caveat ("a larger box would move the ceiling and might reorder the CPU-bound targets") applies, and here it did: on the faster box AltMount edged past zurg on raw throughput, and the CPU-bound targets moved. What carries across is the **relative** comparison under identical conditions and the **behavioural** findings, which reproduced independently.

## Versions under test

| target | commit | vs round 7 |
|---|---|---|
| zurg | `8491572d` | moved (was 3d9fbcc4) |
| AltMount | `e85fa318` | moved (was 7ab04352) |
| InfiniDysk | `412fc698` | moved (was cd9b1205) |
| decypharr | `0dd1cbbd` | unchanged |
| nzbdav | `794948be` | unchanged |

## Headline results

**Throughput (256 MB cold reads, 6 reps, rotating order), MB/s**

| | AltMount | zurg | nzbdav | InfiniDysk | decypharr |
|---|---|---|---|---|---|
| mean | 63.3 | 58.5 | 44.3 | 27.0 | 4.6 |
| CPU s/GB | 5.1 | 6.0 | 36.2 | 31.3 | 18.4 |
| reads complete | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |

AltMount and zurg lead and are close; both spend ~1/6th the CPU per GB of InfiniDysk and nzbdav. decypharr is an order of magnitude slower, same as every prior round.

**Damaged article — does the server rebuild the missing span?** (read the hole, re-read every 2 min for 8 min)

- **zurg — repairs it.** Silence at t0, real bytes by t+2, held through t+8. The only one.
- AltMount, InfiniDysk — zero-fill permanently, with repair enabled.
- nzbdav — 404, refuses the whole file (no repair feature).
- decypharr — 206 with zero bytes throughout, with repair enabled and a schedule that fires.

This is the same result as round 7, reproduced independently on different hardware.

**Obfuscated release** — zurg and AltMount serve the video with a clean listing (no leftover hashed blobs); InfiniDysk and nzbdav serve it but leave 5 raw hashed blobs in the listing; decypharr never imported it. All five that served returned the same md5.

**Multi-volume RAR** — all five serve the same 16 MB md5 (`79d1e148…`, identical to round 7). zurg and nzbdav preserve the archive's directory structure; InfiniDysk and AltMount flatten it (AltMount also emits a stray `8-FatherBrown.mp4`); decypharr flattens to one concatenated name.

## Files

The raw per-phase JSON and logs are alongside this note. Byte identity across all five targets is confirmed by the matching md5s in the RAR and obfuscated phases. The news host is replaced with `news.news-provider.example` throughout, as in the rest of the repo.
