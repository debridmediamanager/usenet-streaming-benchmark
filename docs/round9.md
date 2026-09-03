# Round 9. The same five servers on 15 connections

Measured on 3 September 2026, on zen. Round 9 is round 7 run again with one variable changed: every target gets exactly 15 NNTP connections instead of 20. The binaries and container images are the identical round 7 builds from each repository main HEAD of 1 September 2026, the news server is the same, the corpus is the same, repair stays enabled everywhere the feature exists, and the connection budget is set in both knobs on the three targets where the provider pool and the read budget are separate settings. Read the README for the round 7 report and the method; nothing in the method changed. Round 8 is a different experiment, the round 7 configuration on dedicated Hetzner hardware, so its numbers do not compare to these: round 9 runs on the same two shared cores as round 7 and compares only to round 7.

The point of the round is connection scaling. Round 7 established that throughput scales close to linearly with the connection count when a server is connection-bound. This round measures which of the five actually are.

## Throughput at 15 connections

256 MB cold reads. Six repetitions. Rotating order. Offsets from 1.5 GB to 5.5 GB in 0.8 GB steps. Same as round 7.

| | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|
| Mean MB/s | **33.98** | 22.14 | 19.22 | 17.11 | 9.26 |
| Median MB/s | **33.16** | 23.04 | 18.45 | 16.92 | 9.46 |
| Slowest to fastest | 31.1-38.5 | 17.9-27.2 | 9.2-29.1 | 16.0-18.5 | 6.3-12.5 |
| Wait before data arrives | **0.36 s** | 3.47 s | 0.99 s | 5.09 s | 5.62 s |
| CPU seconds per GB | **9.5** | 12.6 | 53.0 | 58.1 | 29.0 |
| Peak RSS | 374 MB | 307 MB | 1003 MB | 578 MB | 51 MB |
| Reads that finished | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 |

Per repetition, in MB/s.

| rep | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|
| 0 | 31.82 | 18.52 | 9.18 | 15.96 | 8.39 |
| 1 | 34.51 | 27.17 | 15.40 | 16.86 | 10.99 |
| 2 | 38.50 | 17.91 | 15.93 | 16.98 | 10.53 |
| 3 | 31.09 | 23.05 | 20.97 | 16.42 | 6.83 |
| 4 | 36.16 | 23.02 | 24.75 | 18.53 | 6.29 |
| 5 | 31.79 | 23.17 | 29.10 | 17.93 | 12.51 |

Source is `results/round9/results_six7.json` and `results/round9/six7.log`. The file names inside `results/round9/` keep the names the round 7 harness scripts give them, and this round ran the round 7 scripts as they were on the day, without the issue #1 harness changes that landed afterwards.

## What losing a quarter of the connections cost each server

| | round 7 mean, 20 conns | round 9 mean, 15 conns | change |
|---|---|---|---|
| zurg | 36.54 | 33.98 | **-7%** |
| AltMount | 30.38 | 22.14 | **-27%** |
| InfiniDysk | 19.18 | 19.22 | 0% |
| nzbdav | 17.66 | 17.11 | -3% |
| decypharr | 8.28 | 9.26 | +12% |

The cut is 25% of the budget and the five answers to it are the finding of the round.

AltMount is the one target that scales with the count. Its 27% drop tracks the 25% cut almost exactly, which means at 20 connections it was connection-bound and nothing else was in the way. Give it more connections and it will go faster. That is a compliment to its reader and it is also the whole explanation of its round 7 second place. It is the same fact round 8 found from the other side: AltMount's speed comes from parallel fetch aggression, so on four dedicated cores with connection headroom it bursts past zurg, and on a tight budget it pays the full cut.

zurg lost 7% on a 25% cut. It was not connection-bound at 20 and it is barely connection-bound at 15. Per connection held it moved 1.83 MB/s in round 7 and 2.27 MB/s in round 9, the highest of the five in both rounds. The gap to second place widens from 1.20x at 20 connections to 1.53x at 15, which is the practical reading of this table: the tighter the account, the more the reader efficiency matters.

InfiniDysk, nzbdav and decypharr did not move. Whatever bounds them, it is not the connection count at these budgets. For InfiniDysk this is consistent with its own tuner's curve, which puts its knee well above 20. decypharr's +12% is rep noise on a target whose repetitions span 3.1 to 13.9 MB/s across both rounds, not an improvement, and its own read budget default is 15 anyway.

Ranking is unchanged from round 7 in every column.

## Latency at 15 connections

| | zurg | InfiniDysk | AltMount | nzbdav | decypharr |
|---|---|---|---|---|---|
| Cold open, first MB | **0.319 s** | 1.114 s | 2.962 s | 6.556 s | 6.411 s |
| Time to first byte | 0.298 s | **0.054 s** | 0.989 s | 1.489 s | 4.322 s |
| Large sequential read | 20.74 MB/s | **41.84 MB/s** | 15.88 MB/s | 8.93 MB/s | 6.89 MB/s |
| Warm re-read | 0.064 s | 0.403 s | 2.343 s | 5.040 s | **0.058 s** |
| Scrub, median of 8 | **0.647 s** | 1.408 s | 0.703 s | 2.320 s | 5.020 s |
| Full ffprobe | **2.17 s** | 5.39 s | 12.25 s | 3.57 s | 9.36 s |
| RSS | 424 MB | 782 MB | 463 MB | 393 MB | 43 MB |

Latency is round trips, not bandwidth, so the connection cut moves these numbers less than run to run variance does. The cold open ordering is the same as round 7. Twenty times separates the fastest cold open from the slowest.

Source is `results/round9/results_latency_r7.json`.

## Behaviour phases: identical verdicts to round 7

The damaged article, obfuscated release and multi-volume RAR phases produced the same verdict for every target as round 7, at the lower connection count.

- **Damaged article.** zurg serves zero-fill at first probe and real repaired bytes by the 4 minute mark of the timeline, with the md5 flipping from the zero-fill hash to real content. AltMount and InfiniDysk still serve zero-fill at the 8 minute mark. nzbdav answers 404 for the file. decypharr's probe stalls and returns no bytes. Repair remains a one server feature. Source `results/round9/results_damage_timeline_r7.json`.
- **Obfuscated release.** Same as round 7 per target, including decypharr never listing the release at all.
- **Multi-volume RAR.** All five serve the full 321905886 byte file and all five returned the same md5 `79d1e148021c44ce018c9c47eb504d39` for the same 16 MB range. Byte identity holds at 15 connections. All five also reported the same ffprobe duration of 6206.752 seconds for the throughput file. Source `results/round9/results_reprobe_r7_damage_obfuscated_rar.json`.

## What 15 connections newly broke: imports

Streaming survived the cut better than importing did.

**AltMount silently dropped two of the five corpus releases.** Its importer runs a fast-fail segment availability check before accepting an NZB, and at 15 connections that check hit its deadline on the two largest releases and gave up: `Import stopped because segment availability was inconclusive ... context deadline exceeded`, 8 segments unverified on the 35 GB remux and 196 on the season pack. The release is not queued for retry. It is gone, with one WARN line to show for it, and it was still absent from the listing two and a half hours later. Round 7 lost one release to the same check at 20 connections. The tighter the budget, the more it drops, and a user who imports a large release on a modest account will not know until they go looking.

**InfiniDysk imports far slower at 15 connections.** At its settle cap during the seed pass it had listed 1 of 5 releases with 4 still queued. The queue did drain and every release was eventually served correctly, but the seed pass for all five targets took 55 minutes against round 7's 15.

**decypharr** never listed the obfuscated release, in either round.

zurg and nzbdav imported all five releases without incident in both rounds.

Source `results/round9/results_tree_r9_seed.json`.

## Connection parity was verified from live sockets

The socket count every target actually held was sampled from `ss -tnp` every 5 seconds for the whole run and filtered to the process under test. Maximum concurrent established sockets during the throughput phase:

| | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|
| Max sockets held | 17 | 15 | 15 | 16 | 14 |
| Sockets moving bytes | 15 | 15 | 15 | 15 | 13-14 |

Two honest footnotes. zurg's socket count reads 16 to 17, not 15. A per-socket byte accounting probe after the round showed exactly 15 of those sockets moving article data while the extra held 42 bytes of keep-alive traffic over 20 seconds: it is the startup account verification connection, held idle outside the pool's accounting. Fetch concurrency is semaphore-limited to 15, so the read comparison is fair, but the idle socket does occupy a slot against a provider account cap and zurg should fold it back into the pool. Second, decypharr does not fill its budget: both its knobs were set and verified at 15 and it peaked at 13 to 14 by its own scheduling.

Source `results/round9/results_parity_r9.json`.

## Why this round exists

Round 6 accidentally proved that an unequal connection budget measures the budget and nothing else, and round 7 fixed it by pinning every target to 20. Fifteen is the other interesting point: it is a common allowance on entry tiers and shared accounts, and it is decypharr's own per-file default. The answer is that below 20 connections the field spreads out rather than compressing. The efficient reader keeps nearly all of its speed, the connection-bound reader gives up a quarter, and two of the five were never using their budget in the first place.
