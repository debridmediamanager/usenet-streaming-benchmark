# Round 14: the round 13 field on dedicated cores and a new account

Measured **1–2 November 2026** on a fresh Hetzner ccx23 (four dedicated vCPUs,
16 GB, nbg1). Sources were pinned to upstream main heads on 1 November. The
same seven targets as round 13 (six streaming applications and the raw NNTP
transport control), the same corpus and the same ten-connection allowance,
on a different host **and** a different news provider. Read
[Limits on conclusions](#limits-on-conclusions) before comparing it with
any earlier round.

## Findings

- **zurg and AIOStreams trail on sustained reads.** zurg's sequential median is
  47.78 MB/s and AIOStreams', rerun without the disk cache only it had been
  given, 48.66, against 57.07–60.58 for the other four applications. The
  clean-start noise floor this round is 9.1%, so that gap is resolved by this
  pass and the 1.8% between zurg and AIOStreams is not. zurg's p05 stall floor
  is 6.3 MB/s where AltMount, InfiniDysk, NZBDav-og and decypharr hold 40–44.
  On round 13's shared two-core host zurg had the highest observed median; on
  four dedicated cores the field overtakes it.
- **Rounds 13 and 14 gave AIOStreams a cache advantage, and this report removes
  it.** Our configuration review kept AIOStreams' 8 GB on-disk segment cache
  while AltMount's and InfiniDysk's disk segment caches were off, and three
  corpus entries share one release's articles, so only AIOStreams could serve
  the second and third from disk. Its main pass was rerun with that cache off
  (see [below](#aiostreams-without-the-disk-cache)); the rerun's numbers are the
  ones in this report's tables.
- **zurg opens fastest; AltMount seeks fastest.** Counting only data a target
  had not read before, zurg's cold open is 2.5 ms against AltMount's 24.3 and
  AIOStreams' 79.3, and AltMount's seeks reach a first byte in 175 ms against
  219–586 for the rest (zurg 517).
- **zurg served an incomplete archive set as zeros.** With one RAR volume of the
  set absent, zurg logged that the volume set was incomplete and then listed the
  inner file at its declared 321,905,886 bytes anyway. Every sampled range past
  the gap is the MD5 of 2 MiB of zeros. Round 13's zurg refused the same entry.
  decypharr and AIOStreams served it too, at 291,906,039 bytes and with
  non-zero bytes in the sampled ranges.
- **InfiniDysk and NZBDav-og met all eight registered expectations.** zurg,
  AltMount and decypharr met seven, AIOStreams six.
- **104/104 compared target-range hashes matched consensus.** Sampled ranges,
  not full-file verification; the negative entries' zeros above are the
  per-entry check, not a consensus disagreement.
- **The corpus is on the new provider exactly as built.** Before any target ran,
  every article of the five posts was STAT-checked and the first, middle and last
  article of every file BODY-decoded with its CRC: 38,846 articles, the one
  deliberately unreachable article the only one missing
  ([`corpus-census.json`](../results/round14/corpus-census.json)).

Raw measurements: [`results/round14/`](../results/round14/). The mechanically
rendered tables are [`report.md`](../results/round14/report.md); the
interpretation below takes precedence over its generic ranking captions.

## Field and exact versions

| Target | Pinned source revision | Build/runtime evidence |
|---|---|---|
| zurg | `e4fac5cbdf3b9b8983f939029849c20960810d71` | binary embeds Go 1.27.3 |
| [AltMount](https://github.com/javi11/altmount/tree/76d7468f9458a0f7f5860e6e9db657b0e72d25be) | `76d7468f9458a0f7f5860e6e9db657b0e72d25be` | binary embeds Go 1.27.3 |
| [InfiniDysk](https://github.com/infinidysk/infinidysk/tree/afa599d255bc9c0751a4b3ceccaf2d91d75382e1) | `afa599d255bc9c0751a4b3ceccaf2d91d75382e1` | official Dockerfile; rapidyenc `81b6ed33` |
| [NZBDav-og](https://github.com/nzbdav-dev/nzbdav/tree/0c7d8e215e0602fa4bfb3fa358ee46cecc6ba76d) | `0c7d8e215e0602fa4bfb3fa358ee46cecc6ba76d` | unchanged since round 13; official Dockerfile |
| [decypharr](https://github.com/sirrobot01/decypharr/tree/917cfa24d51fa98d98aa01864d8c7371401d56d0) | `917cfa24d51fa98d98aa01864d8c7371401d56d0` | binary embeds Go 1.26.10 |
| [AIOStreams](https://github.com/Viren070/AIOStreams/tree/0b56aa18782fd1aab47f23609839de681bcc1122) | `0b56aa18782fd1aab47f23609839de681bcc1122` | official Dockerfile; Node 24.22.2 |
| raw | this repository's `rawserve_r10.py` | Python 3.12.3; transport control, not archive extraction |

zurg's repository is private; its revision is exact and its binary hash is in
[`build.json`](../results/round14/build.json) with every other binary hash and
image ID. No competitor source was patched. Each Go target is built in the
`golang:<version>-bookworm` image its own `go.mod` asks for.

## Configuration: round 13's review, plus what upstream added since

Every setting from round 13's source-backed review
([`config/round13-review.json`](../config/round13-review.json)) was re-checked
against the new revisions. Every key still exists with its meaning, with one
rename. Where upstream added a setting that changes connections, repair or
outbound traffic, round 14 sets it, and nothing else:

| Target | Setting | Round 14 | Why |
|---|---|---|---|
| decypharr | `usenet.disk_buffer_path` → `usenet.disk_path` | same path | renamed upstream; the old key is ignored, and an empty `disk_path` means memory-only streaming |
| decypharr | `usenet.body_pipeline_depth` (new, default 2, max 4) | 4 | the depth every other pipelining target in the field runs |
| decypharr | `hearsay.disabled` (new, default on) | true | a public gossip network that publishes the hash and completeness of every imported NZB |
| InfiniDysk | `repair.read-hold-minutes` (new, default 15) | 0 | a broken file now waits 15 minutes after any read before repair may replace it; round 13 had no wait |
| AIOStreams | `MEDIA_INFO_PROBE` (new) | false | an ffprobe pass over the same engine; its defaults never fire on SAB+WebDAV, set so a moved default cannot add reads |

zurg's settings are unchanged; its new DMM placement runs only with `rex_url` or
`magic.placement`, neither set. Go and .NET processor counts are four, the
host's cores; everything else is round 13's, including the memory ceilings.

decypharr rewrites its own config file on first start (it adds generated
secrets and drops unknown keys), so readback now compares each target's API
against the configuration as rendered, not against the file the target may
have rewritten.

Behaviour that changed upstream with no setting to restore round 13's, and that
touches the damage entries: InfiniDysk now fails playback of eligible video past
5 missing segments or 1% of bytes; AIOStreams fails an entry whose first article
is missing and rejects articles whose yEnc part number disagrees with the NZB;
a failed AltMount PAR2 repair now leaves a degraded file playable instead of
marking it corrupted.

## Host, account and execution

Hetzner ccx23 (four dedicated vCPUs, 16 GB), Ubuntu 24.04, kernel
6.8.0-139-generic, Docker 29.9.2, in nbg1. Nothing else ran on it; it was
created for this round and deleted after it.

The account is a block account used for nothing but this benchmark, on
`news.bulknews.eu:563` TLS. A Usenet account is only ever used from one public
IP, so the box borrows a reserved Hetzner Primary IPv4 that outlives it, gets
no IPv6, and checks its own egress before anything dials
([`hetzner-box.sh`](../harness/hetzner-box.sh)). The phases ran through
[`hetzner-r14.sh`](../harness/hetzner-r14.sh).

| Phase | UTC start | UTC end |
|---|---|---|
| Corpus census | 1 Nov 22:35 | 1 Nov 23:15 |
| Smoke (final) | 1 Nov 23:31 | 1 Nov 23:41 |
| Noise A | 1 Nov 23:42 | 1 Nov 23:52 |
| Noise B | 1 Nov 23:52 | 2 Nov 00:02 |
| Main | 2 Nov 00:02 | 2 Nov 03:19 |

The first smoke was discarded and is kept as
[`preflight-discarded-1/`](../results/round14/preflight-discarded-1/): the
harness built sources under a `umask 077` meant for secret configuration, and
the two .NET images, which start their frontend as a non-root user, could not
read it. The build now runs under `umask 022` and asserts the image's user can
read its frontend.

Fresh libraries and caches per pass; one target at a time; order rotates. Main
order: InfiniDysk, NZBDav-og, decypharr, AIOStreams, raw, zurg, AltMount. The
damaged release's truth bytes were acquired with every target stopped.

[`connection-gate.json`](../results/round14/connection-gate.json) records
10,806 samples, 9,790 in the main window, at a median gap of one second and a
maximum of two. Main peaks were **10 for every target**, with no overlap, no
oversubscription and no unowned consumer of the provider on the box.

## Availability/refusal matrix

`pass` means the registered positive serving heuristic passed; `refused` means
the negative heuristic got no qualifying payload within its budget; `WRONGLY
SERVED` means a negative entry returned a qualifying payload.

| Entry | zurg | AltMount | InfiniDysk | NZBDav-og | decypharr | AIOStreams | raw |
|---|---|---|---|---|---|---|---|
| plain-video | pass | pass | pass | pass | pass | pass | pass |
| damaged-partial | pass | pass | pass | pass | pass | pass | pass |
| obfuscated | pass | pass | pass | pass | pass | pass | pass |
| rar-stored | pass | pass | pass | pass | pass | pass | pass |
| season-pack | pass | pass | pass | pass | pass | pass | pass |
| dead-post | refused | refused | refused | refused | refused | refused | refused |
| incomplete-archive-set | **WRONGLY SERVED** (zeros) | refused | refused | refused | WRONGLY SERVED | WRONGLY SERVED | WRONGLY SERVED |
| damaged-severe | refused | WRONGLY SERVED | refused | refused | refused | WRONGLY SERVED | refused |
| expectations met | 7/8 | 7/8 | 8/8 | 8/8 | 7/8 | 6/8 | 7/8 |

`compressed-archive` and `encrypted-no-password` still need real posts and were
skipped for every target, as in round 13.

### The known damaged article

At the one unreachable article of `damaged-partial`, zurg, AltMount, InfiniDysk
and AIOStreams returned zeros for the whole article; NZBDav-og and decypharr
stopped at the hole (HTTP 404). None reconstructed it. Repair is enabled
wherever the feature exists; enabled is not evidence that it ran.

## Results by metric

One table per metric, best first. AIOStreams' figures in every table are from its rerun without the disk cache (below); everything else is the main pass. `raw` reads the articles with no application in the way and is shown under the speed tables as the network ceiling, not ranked. Rebuild these tables with [`tables_r14.py`](../harness/tables_r14.py).

### Sequential throughput

**Higher is better.** Median over the five entries that should play. The worst clean-start swing between the two noise passes was 9.1%, so a difference smaller than that is not resolved by one pass: the top four are within it of each other, and so are zurg and AIOStreams. Each read is 1.6 GB or the rest of the file, more than any target's memory cache holds.

| Rank | Target | MB/s |
|---|---|---|
| 1 | NZBDav-og | 60.58 |
| 2 | InfiniDysk | 57.73 |
| 3 | AltMount | 57.37 |
| 4 | decypharr | 57.07 |
| 5 | AIOStreams | 48.66 |
| 6 | zurg | 47.78 |
| — | raw, network ceiling | 59.55 |

InfiniDysk read the stored RAR entry at 2.27 MB/s against 27.88–56.90 for the rest, which pulls its median down on that one shape.

### Stall floor

**Higher is better.** The 5th percentile of one-second windows during the sequential read, median over the entries that should play: how far the stream dips.

| Rank | Target | MB/s |
|---|---|---|
| 1 | InfiniDysk | 44.10 |
| 2 | NZBDav-og | 43.76 |
| 3 | decypharr | 43.13 |
| 4 | AltMount | 39.72 |
| 5 | AIOStreams | 13.00 |
| 6 | zurg | 6.33 |

### Cold open

**Lower is better.** Time to read the first MiB of a file just after its import, median over the three entries whose articles no earlier entry had read (`plain-video`, `rar-stored`, `season-pack`). A target that fetches the start of a file while importing it answers from memory here, which is a real advantage to a player.

| Rank | Target | ms |
|---|---|---|
| 1 | zurg | 2.5 |
| 2 | AltMount | 24.3 |
| 3 | AIOStreams | 79.3 |
| 4 | InfiniDysk | 155.3 |
| 5 | NZBDav-og | 197.1 |
| 6 | decypharr | 452.7 |
| — | raw, network ceiling | 226.3 |

### Seek, first byte

**Lower is better.** Time to the first byte of a jump to 1%, 25%, 50%, 75% and 95% of the file, counting only jumps to data the target had not read before: the three entries above, and only points outside the range the entry's own sequential read had just covered. That leaves 6–11 points per target, so neighbours within about a factor of two are not separated.

| Rank | Target | ms |
|---|---|---|
| 1 | AltMount | 175 |
| 2 | NZBDav-og | 219 |
| 3 | decypharr | 232 |
| 4 | zurg | 517 |
| 5 | InfiniDysk | 574 |
| 6 | AIOStreams | 586 |
| — | raw, network ceiling | 1820 |

### Import

**Lower is better.** From handing over the NZB to the file being listed. The harness checks the listing every 5 seconds, so about 5 s means "listed by the first check", and every median here is that: this does not separate the targets.

| Rank | Target | s |
|---|---|---|
| 1 | AltMount | 5.0 |
| 1 | decypharr | 5.0 |
| 1 | zurg | 5.0 |
| 4 | InfiniDysk | 5.1 |
| 4 | AIOStreams | 5.1 |
| 6 | NZBDav-og | 5.7 |

### Registered expectations met

**Higher is better.** Five entries that should play and three that should be refused (see the matrix above); two more need real posts and were skipped for every target.

| Rank | Target | of 8 |
|---|---|---|
| 1 | NZBDav-og | 8 |
| 1 | InfiniDysk | 8 |
| 3 | AltMount | 7 |
| 3 | decypharr | 7 |
| 3 | zurg | 7 |
| 6 | AIOStreams | 6 |

### CPU time

**Lower is better.** CPU seconds over startup, import and every read, per GiB delivered.

| Rank | Target | s per GiB |
|---|---|---|
| 1 | decypharr | 4.84 |
| 2 | AltMount | 6.20 |
| 3 | zurg | 10.75 |
| 4 | AIOStreams | 17.55 |
| 5 | InfiniDysk | 21.70 |
| 6 | NZBDav-og | 27.36 |

### CPU, 95th percentile

**Lower is better.** The 95th percentile of sampled CPU use.

| Rank | Target | cores |
|---|---|---|
| 1 | decypharr | 0.16 |
| 2 | AltMount | 0.18 |
| 3 | InfiniDysk | 0.27 |
| 3 | zurg | 0.27 |
| 5 | AIOStreams | 0.56 |
| 6 | NZBDav-og | 0.77 |

### Peak memory

**Lower is better.**

| Rank | Target | MiB RSS |
|---|---|---|
| 1 | decypharr | 214 |
| 2 | NZBDav-og | 442 |
| 3 | AIOStreams | 547 |
| 4 | InfiniDysk | 930 |
| 5 | zurg | 1061 |
| 6 | AltMount | 1064 |

### Disk reads

**Lower is better.** Physical block reads per GiB delivered, counted from before each target started.

| Rank | Target | MiB per GiB |
|---|---|---|
| 1 | NZBDav-og | 0.00 |
| 1 | InfiniDysk | 0.00 |
| 3 | AltMount | 0.04 |
| 4 | decypharr | 0.05 |
| 5 | AIOStreams | 0.21 |
| 6 | zurg | 10.16 |

zurg's 55.76 MiB fell outside its read windows, every one of which measured 0.0 MiB, and matches its own 82 MB binary paging in at start: on zen a build of the same commit read 61 MiB before it was serving with its binary out of the page cache and 0 MiB with it in. zurg started last but one in the main pass, after decypharr and AIOStreams had written about 13 GB on this 16 GB host, and read 8.5 and 3.5 MiB in the noise passes. Rounds after 14 count reads from the moment a target is ready.

### Disk writes

**Lower is better.** Physical block writes per GiB delivered.

| Rank | Target | MiB per GiB |
|---|---|---|
| 1 | AltMount | 1.41 |
| 2 | NZBDav-og | 18.59 |
| 3 | zurg | 21.11 |
| 4 | InfiniDysk | 25.09 |
| 5 | AIOStreams | 28.08 |
| 6 | decypharr | 1297.71 |

decypharr's writes are consistent with its new sparse per-stream disk cache, which upstream no longer caps at 256 MiB (source reading, not measured per file).

### State growth

**Lower is better.** Allocated growth of the target's own state directories over the pass.

| Rank | Target | MiB |
|---|---|---|
| 1 | decypharr | 1.34 |
| 2 | NZBDav-og | 5.87 |
| 3 | AltMount | 6.28 |
| 4 | InfiniDysk | 20.96 |
| 5 | zurg | 101.73 |
| 6 | AIOStreams | 188.32 |

zurg keeps an on-disk article cache by default (`data/bytecache/articles`, capped at 512 MiB): the first and last 8 MiB of every file it serves, the first and last article of every file it reads, and archive structure, so a probe or library scan after a restart does not fetch them again. Its state directories also hold the article index (`data/nzb-index`) and the NZBs dropped into `nzbs/`. The pass records only the total, not how it splits between them.

## AIOStreams without the disk cache

Each target starts once per pass and reads every entry in turn, so its caches
stay warm from one entry to the next; nothing is cleared between entries, by
design. That only matters where the corpus repeats itself: `plain-video`,
`damaged-partial` and `obfuscated` are the same 1,662 articles under three
names (1,661 for the damaged one), read in that order. Only a cache keyed by
article and larger than the 7 GB release can serve the second and third
without the network, and rounds 13 and 14 configured exactly one:

| Target | Cache as configured in rounds 13 and 14 |
|---|---|
| AIOStreams | 8 GB segment cache on disk, keyed by message id (the "high" profile's size) |
| AltMount | disk segment cache off; 256 MiB in memory |
| InfiniDysk | segment cache off |
| zurg | 256 MiB decoded cache in memory |
| decypharr | 256 MB in memory and per-stream disk buffers |
| NZBDav-og | none configurable |

With it, AIOStreams read the three at 54.87, 179.02 and 1,938.07 MB/s; round 13
shows the same rise (19.8, 39.6, 58.0). So AIOStreams' main pass was rerun on
2 November, 06:59–07:27 UTC, with `USENET_SEGMENT_DISK_CACHE_BYTES=0`
(AIOStreams documents 0 as disabled, and the engine then gets no cache path),
everything else unchanged, beside `raw` as the same-window network ceiling.
The image was rebuilt from the same pinned revision on a fresh box
([`build.json`](../results/round14/aiostreams-nocache/build.json)); raw output in
[`aiostreams-nocache/`](../results/round14/aiostreams-nocache/).

| Entry | AIOStreams, 8 GB cache | AIOStreams, cache off | raw, main pass | raw, rerun window |
|---|---|---|---|---|
| plain-video | 54.87 | 54.96 | 59.55 | 59.22 |
| damaged-partial | 179.02 | 50.94 | 60.78 | 59.04 |
| obfuscated | 1,938.07 | 48.66 | 57.26 | 60.26 |
| rar-stored | 30.77 | 32.99 | 56.90 | 43.76 |
| season-pack | 40.90 | 41.08 | 60.27 | 54.11 |
| **median** | **54.87** | **48.66** | **59.55** | **59.04** |

The network was the same in both windows (raw's median 0.9% apart). The three
entries whose articles had not been read before moved by under 8%; the two
that repeat `plain-video`'s articles fell to the network rate, and the median
fell 11%. Outcomes did
not change (six of eight expectations, the same two wrongly served), the
socket gate saw 10 and 10 and nothing else, and every compared range matched
consensus. The stall floor rose (8.39 to 13.00 MB/s) and cold open went from
5.2 to 8.7 ms on the round's five entries. It
also cost more without the cache: 17.55 CPU seconds per GiB against 7.10,
since a cache hit is cheap, while peak memory fell from 773 to 547 MiB and
state growth from 4,671.82 to 188.32 MiB. The rerun has no noise pass of its own;
the round's 9.1% applies.

Turning the disk cache off did not take AIOStreams' memory out of the picture.
Its seeks into `damaged-partial` and `obfuscated` still answered in 7 and 6 ms,
where every other target paid full price again (zurg 624 and 652 ms, NZBDav-og
713 and 791), because those offsets of those articles had just been fetched
for `plain-video`. The latency tables above therefore count only data a target
had not read before; the sequential reads, at 1.6 GB, are past any memory cache.

A corpus that repeats articles rewards whichever target is given the largest
cache. The next round should give those entries distinct posts, so every
target can keep the cache it would ship with and every entry still reads from
the network.

## Reproducing the round

From a checkout with `hcloud` configured, a reserved Primary IPv4 named
`bench-usenet-owner` (or `HETZNER_PRIMARY_IP`) that belongs to the account,
and the account in the environment:

```bash
export NNTP_USER=... NNTP_PASS=...
harness/hetzner-r14.sh up        # provision on the reserved IP, install, copy
harness/hetzner-r14.sh census    # the corpus must be on the provider as built
harness/hetzner-r14.sh build     # pinned sources, then nzbdav's migration-only bootstrap
harness/hetzner-r14.sh verify
harness/hetzner-r14.sh smoke
harness/hetzner-r14.sh run
harness/hetzner-r14.sh collect
harness/hetzner-r14.sh down      # deletes the server, never the IP
```

`ROUND` (in [`round_profile.py`](../harness/round_profile.py)) fixes the
working directory, the one provider the harness may dial, the pins and the
CPU count; `ROUND=r13` still reproduces round 13 on zen. zurg's source is
private and travels to the box as a git bundle of the pinned revision.

## Limits on conclusions

- **Different host and different provider from every earlier round.** Round 13
  ran on a shared two-core host against another provider, round 12 on a ccx23
  with a different account. No cross-round absolute-rate claim; the field reorders by
  host on identical binaries (round 10 measured this).
- One full pass, one plain-video noise shape, a 9.1% worst measured swing.
- Registered serving/refusal heuristics, not full-file validation or real-client
  playback. Consensus uses three deterministic 2-MiB slices where available.
- AIOStreams' numbers are from a rerun of its main pass without its disk cache
  (above), not from the same window as the rest of the field; raw in the same
  window bounds the difference in network conditions at 0.9%.
- Two real-post prerequisites unavailable; compression and passwordless
  encrypted RAR behaviour remain unmeasured.
- Socket sampling every second; no claim about sub-second transient sockets.
- Configuration is round 13's source-informed review plus the settings above,
  not a corpus-tuned optimum. Images depend on mutable base/compiler tags.

## All metrics

Every metric from the tables above, with each target's rank in that metric in brackets. ↑ higher is better, ↓ lower is better. AIOStreams' figures are from its rerun without the disk cache; cold open and seek count only data the target had not read before.

| Target | Throughput ↑ (MB/s) | Stall floor ↑ (MB/s) | Cold open ↓ (ms) | Seek ↓ (ms) | Import ↓ (s) | Expectations ↑ (of 8) | CPU ↓ (s per GiB) | CPU p95 ↓ (cores) | Memory ↓ (MiB RSS) | Disk reads ↓ (MiB per GiB) | Disk writes ↓ (MiB per GiB) | State ↓ (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NZBDav-og | 60.58 (1) | 43.76 (2) | 197.1 (5) | 219 (2) | 5.7 (6) | 8 (1) | 27.36 (6) | 0.77 (6) | 442 (2) | 0.00 (1) | 18.59 (2) | 5.87 (2) |
| InfiniDysk | 57.73 (2) | 44.10 (1) | 155.3 (4) | 574 (5) | 5.1 (4) | 8 (1) | 21.70 (5) | 0.27 (3) | 930 (4) | 0.00 (1) | 25.09 (4) | 20.96 (4) |
| AltMount | 57.37 (3) | 39.72 (4) | 24.3 (2) | 175 (1) | 5.0 (1) | 7 (3) | 6.20 (2) | 0.18 (2) | 1064 (6) | 0.04 (3) | 1.41 (1) | 6.28 (3) |
| decypharr | 57.07 (4) | 43.13 (3) | 452.7 (6) | 232 (3) | 5.0 (1) | 7 (3) | 4.84 (1) | 0.16 (1) | 214 (1) | 0.05 (4) | 1297.71 (6) | 1.34 (1) |
| AIOStreams | 48.66 (5) | 13.00 (5) | 79.3 (3) | 586 (6) | 5.1 (4) | 6 (6) | 17.55 (4) | 0.56 (5) | 547 (3) | 0.21 (5) | 28.08 (5) | 188.32 (6) |
| zurg | 47.78 (6) | 6.33 (6) | 2.5 (1) | 517 (4) | 5.0 (1) | 7 (3) | 10.75 (3) | 0.27 (3) | 1061 (5) | 10.16 (6) | 21.11 (3) | 101.73 (5) |
