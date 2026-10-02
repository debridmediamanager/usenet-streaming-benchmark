# Round 13: current zurg main and AIOStreams native filesystem

Measured **2 October 2026**, on the isolated zen targets. Sources were pinned to
upstream main heads at provisioning on 1 October. Seven targets: six streaming
applications and the raw NNTP transport control. This is **not** a rerun on round
12's dedicated four-core Hetzner machine.

## Findings

- **AIOStreams' native filesystem works in this matrix.** Its own SAB upload,
  WebDAV `PROPFIND`, media tree and HTTP ranges served all five positive shapes.
  No Stremio response resolver, `.strm` wrapper or external streaming shim was used.
- **Every target reached 10 NNTP sockets in the measured main window.** Across
  5,106 sampled censuses, no target exceeded 10 and no two consumers overlapped.
  AIOStreams naturally used only eight during the plain-video smoke; no dummy
  connections were added to fill the allowance.
- **zurg had the highest observed sequential median, 37.99 MB/s**, and the lowest
  observed cold-open median, 16.7 ms. The clean-start rate swing was **67.8%**;
  this shared host and one corpus pass do not support an overall speed ranking.
- **zurg, InfiniDysk and NZBDav-og met all eight registered availability/refusal
  expectations.** This is not eight proofs of intact playback: at the known
  damaged article, five targets returned zeros and two stopped at the hole.
- **AIOStreams met six of eight expectations.** It admitted the incomplete
  archive and severely damaged release. AltMount admitted the severely damaged
  release; decypharr never exposed the obfuscated release within the import budget.
- **95/95 compared positive target-range hashes matched consensus.** These
  sampled ranges are not full-file verification and do not certify the missing
  article or the admitted negative cases.

Raw measurements: [`results/round13/`](../results/round13/). The mechanically
rendered tables are [`report.md`](../results/round13/report.md); interpretation
and units below take precedence over its generic ranking captions.

## Field and exact versions

| Target | Pinned source revision | Build/runtime evidence |
|---|---|---|
| [zurg](https://github.com/debridmediamanager/zurg/tree/998e661b92c840f6b9c8e152c5c9b17d1ba338c6) | `998e661b92c840f6b9c8e152c5c9b17d1ba338c6` | binary embeds Go 1.26.7 |
| [AltMount](https://github.com/javi11/altmount/tree/b82b22c85ce6f8f8f6ccba1985fe0835cade8d07) | `b82b22c85ce6f8f8f6ccba1985fe0835cade8d07` | binary embeds Go 1.27.1 |
| [InfiniDysk](https://github.com/infinidysk/infinidysk/tree/31c837fa08c04495de2a2201813199b5dce0326e) | `31c837fa08c04495de2a2201813199b5dce0326e` | official Dockerfile; rapidyenc submodule built |
| [NZBDav-og](https://github.com/nzbdav-dev/nzbdav/tree/0c7d8e215e0602fa4bfb3fa358ee46cecc6ba76d) | `0c7d8e215e0602fa4bfb3fa358ee46cecc6ba76d` | original upstream, official Dockerfile |
| [decypharr](https://github.com/sirrobot01/decypharr/tree/0dd1cbbd6e4680000097db0141f7106e02d21b8d) | `0dd1cbbd6e4680000097db0141f7106e02d21b8d` | binary embeds Go 1.26.7 |
| [AIOStreams](https://github.com/Viren070/AIOStreams/tree/f815290e8775981cbdde22e0fff7fc1d5d8657cb) | `f815290e8775981cbdde22e0fff7fc1d5d8657cb` | official Dockerfile; Node 24.14.0 |
| raw | this repository's `rawserve_r10.py` | Python 3.10.12; transport control, not archive extraction |

Binary SHA-256s, Docker image IDs and rapidyenc's exact revision are in
[`build.json`](../results/round13/build.json). No competitor source was patched.
The AIOStreams native AES export loaded; no encrypted-release result is inferred
from that binding check. Base/compiler tags and apt repositories were not locked
to immutable digests, so rebuilding pinned sources need not reproduce image IDs.

## Configuration review before measurements

The full source-backed review, including file/line references, is
[`config/round13-review.json`](../config/round13-review.json). Renderers are
[`config_r13.py`](../harness/config_r13.py) and
[`prep_aiostreams_r13.py`](../harness/prep_aiostreams_r13.py). These are informed
settings for this two-core, 7.6-GiB host, **not an experimentally established
global optimum**. Invalid setup/readback was corrected in discarded preflight;
performance settings stayed frozen across both noise passes and the main pass.

### Shared constraints

One enabled `newswest.frugalusenet.com:563` provider per application, verified TLS,
maximum 10 physical connections including import, health and repair activity.
Go and .NET processor counts were two. Native correctness features stayed on
where implemented; no imaginary PAR2 toggles, provider-test secondary engines or
integration-driven background work were introduced. Different cache designs
retain their actual memory, I/O and disk costs rather than pretending identical
megabyte settings produce identical behavior.

### zurg

Ten-slot shared pool, warm floor two **inside** that pool, pipeline depth four,
Linux socket receive autotuning. Decoded cache 256 MiB, mmap segment metadata,
512-MiB disk patch cache, soft 1,024-MiB memory ceiling. Repair enabled; five-second
NZB watch retained. Media integrations, automatic ffprobe analysis and managed
rclone mounting were off because the harness reads actual WebDAV directly.
Dashboard `/config` verifies exposed configuration, while rendered provider
settings and the socket census cover pool knobs absent from that API.

### AltMount

Provider cap 10, warm floor two, BODY in-flight budget 10 and STAT in-flight budget
100: request budgets are **not** extra connection pools. Prefetch 60 retains the
upstream 96-MB ceiling; two import workers and two concurrent imports suit this
host. Memory cache 256 MiB, disk segment cache off, soft memory ceiling 1,024 MiB.

Current `par2_repair.enabled` was explicitly true: `health.repair` is not the
PAR2 switch. Repair uses the same pool, one job, a 256-MiB solver and native mmap
spill, ratio ceiling 1.0 rather than the default 2% restriction. Health interval
60 seconds; unrelated Arr/rclone/SAB integrations off. `TMPDIR` isolates its
otherwise global temporary queue. Explicit loopback CORS origins avoid the
upstream wildcard-plus-credentials startup panic.

`GET /api/config` readback checks the exposed projection. The CLI accepts
`max_concurrent_imports: 2`, but `ImportAPIResponse` omits it; the valid input was
retained, not removed to silence validation. The
[real captured response](../fixtures/round13-altmount-effective-config.json)
records API fields and the unexposed configured cap separately.

### InfiniDysk

Provider, transfer and global download/queue caps 10 on the same underlying pool;
warm floor two. Queue and streaming pipelining enabled at depth/batch four,
40 article buffers, 256-MiB in-flight article budget, native 32-MiB shared-stream
rings and two queue workers. Disk segment cache off; managed heap ceiling
`0x60000000` (1.5 GiB), with native allocations outside it.

Repair/PAR2 enabled: 256-MiB solver, two fetchers, source-supported 200-GB release
and 64-missing-slice bounds rather than restrictive defaults. Native lazy RAR and
its eager fallbacks remain. Health has one worker/two concurrent checks; no Arr
or indexer integrations. Effective ENV-backed keys were checked through
`POST /api/get-config`; the rapidyenc submodule was initialized and compiled.

### NZBDav-og

Original upstream provider cap 10, global download cap 10, default 40 article
buffers and streaming priority 80. No configurable pipeline/cache/warm controls
were invented. Two .NET processors and a 1.5-GiB managed heap limit.

This revision has no PAR2 payload reconstruction setting. Parsing PAR2 names is
not repair. A fresh migration-only database was created with networking disabled;
each pass restored that private empty master through SQLite backup, preserving
its five seeded root rows. Parameterized provider/config upserts, integrity and
empty-library checks preceded startup. Effective API values were read back.

### decypharr

Provider cap 10; streaming and processing limits 10 are scheduling bounds, not
additive pools. Repair's two shared STAT workers use the same provider pool.
Read-ahead 32 MB, aggregate buffer budget 256 MB, native per-stream disk cache
semantics retained, idle two minutes. Socket read/write overrides zero preserve
Linux autotuning. Managed repair source, two workers, five-minute schedule and
one-minute recheck; no nonexistent PAR2 recovery toggle or Arr-only repair source.

`GET /api/config` omits false Go booleans. Readback interprets known omitted
`use_auth`/`disable_webdav` as false but still rejects an oversized provider pool;
its [real response fixture](../fixtures/round13-decypharr-effective-config.json)
drives that boundary test.

### AIOStreams native filesystem

Native read-only WebDAV and SAB upload enabled; FUSE/NFS off. One provider with
`maxConnections: 10`, depth four. Custom profile: 40 command slots, prefetch 20,
inspection concurrency four, census shadow 12, streaming priority 0.8. These
admissions share ten sockets. Prefetch is twice the connection count rather than
blindly using the high profile's 64. Its high-profile 8-GB disk segment cache
remains, and its retained disk/write cost is charged to AIOStreams.

CRC verification, strict damage policy, native Matroska hole padding and lazy
archive resolution remain enabled. Census work stays enabled without an
import-blocking verification budget; periodic library rechecks are off. PAR2
filename recovery is **not Reed-Solomon payload reconstruction**. The dashboard
provider-test endpoint, which creates a separate engine, was never invoked.

SAB multipart field `nzbfile`, API key `usenet:usenet`, no category; Basic-authenticated
`/webdav/usenet/content/` holds the actual media tree. Private env/image validation
was supplemented by real import, `PROPFIND` and range reads, not just health.
Whole SQLite/NZB/cache state was reset between complete passes.

## Connection fairness and execution

Host: Intel Pentium G4400T at 2.90 GHz, two physical/logical cores, 7.6 GiB RAM,
Linux 5.15.0-190-generic. All application and traffic workloads ran on zen.
Management relaying did not move tests elsewhere. Its regular `zurg.service`
remained active with PID 2487464; only task-owned ports, processes and containers
were started/stopped. Unrelated workloads were not paused.

Preflight was discarded when setup failed or heavy unrelated CPU/memory pressure
was observed. A task-only scheduler waited for 120 seconds of low observed CPU
and memory pressure before the final smoke. That start condition does **not**
make a shared host dedicated or guarantee that later contention stayed low.

| Phase | UTC start | UTC end |
|---|---|---|
| Noise A | 01:10:25 | 01:28:59 |
| Noise B | 01:29:54 | 01:51:17 |
| Main | 01:53:53 | 06:24:18 |

All dates are 2 October 2026. Fresh libraries and caches per pass; one target at a
time; order rotates. Main order: InfiniDysk, NZBDav-og, decypharr, AIOStreams, raw,
zurg, AltMount. The damaged-release truth scan and three decoded article anchors
were acquired serially with competitors stopped, then reused from memory: no
live eleventh oracle socket during application measurements.

[`connection-gate.json`](../results/round13/connection-gate.json) records 5,106
samples, including zero-consumer intervals; 4,342 lie in the main window. Main
peaks were **10 for every target**, no unknown local newswest consumer, overlap or
oversubscription. Process trees/container cgroups include auxiliary activity.
Source pool bounds and rendered/read-back configuration complement the census.
The nominal one-second sleep includes collection overhead: actual whole-run
median timestamp gap **3 seconds**, maximum **15 seconds**. Sub-sample transient
connections and consumers on other hosts remain unobserved; this is not a
continuous packet-level proof of global account exclusivity.

## Availability/refusal matrix

`pass` means the registered positive serving heuristic passed; `refused` means
the negative heuristic did not obtain a qualifying payload within its budget.
A 900-second import timeout is not evidence of an immediate explicit rejection.
`WRONGLY SERVED` means admitted contrary to the registered negative expectation,
not an independently proven corrupt full movie. Raw is not an archive consumer.

| Shape | zurg | AltMount | InfiniDysk | NZBDav-og | decypharr | AIOStreams | raw |
|---|---|---|---|---|---|---|---|
| Plain video | pass | pass | pass | pass | pass | pass | pass |
| One missing article | pass | pass | pass | pass | pass | pass | pass |
| Obfuscated | pass | pass | pass | pass | FAIL | pass | pass |
| Stored RAR | pass | pass | pass | pass | pass | pass | outer bytes |
| Season pack | pass | pass | pass | pass | pass | pass | outer bytes |
| Dead post | refused | refused | refused | refused | refused | refused | refused |
| Incomplete archive | refused | refused | refused | refused | refused | WRONGLY SERVED | outer bytes |
| Severe damage | refused | WRONGLY SERVED | refused | refused | refused | WRONGLY SERVED | refused |
| Correct registered expectations | 8/8 | 7/8 | 8/8 | 8/8 | 7/8 | 6/8 | 7/8 transport-only |

The three negative inputs are deterministic derivations of checked-in NZBs:
rewrite message IDs, remove one archive volume, or keep every third data article
while preserving parity entries. Compressed archives and encrypted releases
without a password have **no real post available**: two explicitly uncollected
rows per target, not passes or refusals. All 70 registered rows are retained.

Notable observations: decypharr's obfuscated import timed out at 904.301 seconds.
AIOStreams exposed a 291,906,039-byte media file from the incomplete archive and
admitted the severely damaged MKV. AltMount's severe-damage file advertised
**2,204,974,941 bytes**, versus the intact file's **6,608,994,141**. Its 56.3-MB/s
negative-case rate is not credited as successful intact streaming.

### Known damaged article: the important qualification

The real provider STAT scan found one hole, article index 20 of 1,576. It spans
83,886,080–88,080,384 bytes (half-open), **1.27%** into the 6,608,994,141-byte file.
All seven matched the trusted decoded pre/post anchors. Control reads beyond the
hole returned complete 6-MiB ranges.

| Target | Observed hole-path verdict |
|---|---|
| zurg | zero-filled |
| AltMount | zero-filled |
| InfiniDysk | zero-filled |
| NZBDav-og | truncated-at-hole |
| decypharr | truncated-at-hole |
| AIOStreams | zero-filled |
| raw | zero-filled |

The five zero-filled responses returned the 4-MiB zero-buffer hash
`b5cfa9d6c8febd618f91ac2843d50a1c`; direct sampled content was all zeros. There is
**no demonstrated parity reconstruction at this hole**, even where repair was
enabled. These observations do not establish why native repair did not replace
those bytes or certify later repair behavior. Five positive `pass` marks must
not be quoted as five intact-file correctness proofs.

The old damage control mistakenly used yEnc's part trailer `size` as the whole
file length, selecting offset zero and an impossible hole percentage. This round
uses header `file_size`, captured in a
[real article metadata fixture](../fixtures/round13-damage-first-article.json).
The regression uses the actual damaged NZB from the recorded corpus: it failed
against unfixed code and passes with a control beyond the hole and inside EOF.
Historical reports were not rewritten.

## Rates and latency: descriptive, not an overall ranking

Fixed shared population: five positive entries, each served by at least six of
seven targets. decypharr's four-entry median is incomplete. Rates use decimal
MB/s. Cold open is a 1-MiB offset-zero HTTP read; sequential throughput is one
bounded read from 30% into a large file, planned at 30% of size with a 256-MiB
floor, 2-GiB ceiling and 30-second budget checked between reads.

| Target | Positive n | Sequential median MB/s | Cold median s | Import median s | Median p05 MB/s (n) |
|---|---|---|---|---|---|
| zurg | 5/5 | 37.99 | 0.0167 | 5.202 | 4.04 (5) |
| AltMount | 5/5 | 17.23 | 0.2087 | 10.440 | 0 (5) |
| InfiniDysk | 5/5 | 5.50 | 1.9061 | 36.913 | 0 (5) |
| NZBDav-og | 5/5 | 14.26 | 2.0404 | 13.281 | 3.42 (5) |
| decypharr | 4/5 | 18.755 | 1.0212 | 61.786 | 0 (4) |
| AIOStreams | 5/5 | 19.80 | 0.3568 | 6.044 | 0 (5) |
| raw | 5/5 | 24.34 | 1.2882 | 0.004 | 0.495 (4) |

A zero p05 reflects stalled complete one-second windows; a missing floor is not
converted to zero. Import polling is five seconds and some native queues/watchers
also use five-second intervals, so these timings are quantized. Two successful
plain-video clean-start passes yielded a whole-run median shift of 40.9% and a
worst per-entry swing of 67.8%. This is only one noise shape and does not bound
archive-specific, seek, CPU or memory variability throughout the later main pass.

### Seeks and synthetic playback

Five forward 8-MiB reads at 1%, 25%, 50%, 75%, 95%, then an 8-MiB backward read at
10%. Seek latency below is the median of each positive entry's forward median.
Playback is **HTTP throughput, not a real Plex/Stremio player**: fetch 30 seconds
at a fixed assumed 25 Mbit/s (93,750,000 bytes) from 30% in. Buffer time is a linear
estimate for a **10-second** buffer, not observed client startup.

| Target | Forward seeks complete | Backward complete | Seek median TTFB s | Estimated 10-s buffer s | Full playback payload faster than real time |
|---|---|---|---|---|---|
| zurg | 25/25 | 5/5 | 0.7158 | 1.39 | 5/5 |
| AltMount | 25/25 | 5/5 | 1.5813 | 1.66 | 4/5 |
| InfiniDysk | 25/25 | 5/5 | 1.4033 | 5.04 | 5/5 |
| NZBDav-og | 25/25 | 5/5 | 2.3851 | 3.10 | 5/5 |
| decypharr | 20/20 | 4/4 | 0.7183 | 1.25 | 4/4 |
| AIOStreams | 25/25 | 5/5 | 0.1393 | 0.65 | 5/5 |
| raw | 25/25 | 5/5 | 1.5919 | 1.70 | 4/5 |

These are successful positive rows only. Fast delivery of one bounded payload
is not proof that a player sustains its bitrate across stalls or a damaged hole.

## Resource cost

Whole application process trees include startup, import, reads and negative-case
waiting. Resource legacy `*_MB` fields are **MiB**, not decimal MB; normalized
GiB is 2^30 bytes. CPU is consumed processor seconds, not elapsed time. Physical
process block I/O is separate from retained allocated state.

| Target | CPU s/GiB | p95 cores | Peak RSS MiB | Read MiB/GiB | Write MiB/GiB | State growth MiB |
|---|---|---|---|---|---|---|
| zurg | 34.03 | 0.45 | 1038 | 121.30 | 3053.36 | 519.01 |
| AltMount | 24.45 | 0.21 | 1036 | 239.58 | 4.58 | 6.16 |
| InfiniDysk | 351.54 | 0.21 | 616 | 4572.25 | 133.91 | 11.06 |
| NZBDav-og | 137.33 | 0.50 | 452 | 708.14 | 73.69 | 5.61 |
| decypharr | 27.02 | 0.12 | 60 | 73.95 | 2245.18 | 1.20 |
| AIOStreams | 20.43 | 0.31 | 812 | 770.04 | 624.55 | 2930.86 |
| raw | 47.79 | 0.62 | 537 | 3.63 | 0.09 | 0 |

The denominator is all delivered sequential bytes, including admitted negative
payloads for AIOStreams, AltMount and raw. It is **not cost per verified intact
GiB**; comparing those normalized numbers as correctness-adjusted efficiency
would reward bad admissions. Every target got the same allowance, not identical
cache semantics. AIOStreams' retained 2,930.86 MiB is an actual cost of its enabled
disk cache. zurg's observed 3,053.36 MiB/GiB writes are not hidden by its rate lead.
Sampling can miss short RSS/CPU bursts; I/O includes shared-host paging effects.

## Reproducing the round

The task-specific scripts intentionally guard the original isolated BENCH path
and ports rather than touching shared services. On the designated zen checkout,
with the account file exporting `BENCH_NNTP_HOST/PORT/USER/PASS`:

```bash
bash harness/zen-r13.sh build
bash harness/zen-r13.sh bootstrap
bash harness/zen-r13.sh verify
bash harness/zen-r13.sh smoke --out results/new-round13-smoke
bash harness/zen-r13.sh run --out results/new-round13
```

Do not reuse a directory containing a prior socket census. Build uses the pinned
sources; each measured pass resets only task-owned state. `verify` runs the
existing offline harness checks and six connection/config/real-corpus regressions.
For a different host, adapt explicit guarded paths/ports/account loading first;
no live credentials or private runtime configurations are published.

## Limits on conclusions

- Shared two-core host, different hardware from round 12, uncontrolled production
  and remote-account consumers; no cross-round absolute-rate claim.
- One full pass, one plain-video noise shape, 67.8% worst measured rate swing.
  An initial quiet window is not ongoing host isolation. No global speed winner.
- Registered serving/refusal heuristics, not full-file validation or real-client
  playback. Consensus uses three deterministic 2-MiB slices where available and
  at least two agreeing targets, excluding raw's outer archive bytes.
- The damaged hole remained zero-filled or truncated. PAR2 configuration being
  enabled is not evidence that payload reconstruction occurred.
- Two real-post prerequisites unavailable; compression and passwordless encrypted
  RAR behavior remain unmeasured. They are recorded, not fabricated or scored.
- Socket sampling has 3-second median/15-second maximum observed gaps. No claim
  about unseen transient sockets or account consumers on other machines.
- Configuration review is source-informed, not a corpus-tuned global optimum.
  Images depend on mutable base/compiler tags despite exact source pins.
