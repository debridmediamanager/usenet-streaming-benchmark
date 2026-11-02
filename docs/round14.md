# Round 14: the round 13 field on dedicated cores and a new account

Measured **1–2 November 2026** on a fresh Hetzner ccx23 (four dedicated vCPUs,
16 GB, nbg1). Sources were pinned to upstream main heads on 1 November. The
same seven targets as round 13 (six streaming applications and the raw NNTP
transport control), the same corpus and the same ten-connection allowance,
on a different host **and** a different news provider. Read
[Limits on conclusions](#limits-on-conclusions) before comparing it with
any earlier round.

## Findings

- **zurg is last on sustained reads.** Its sequential median is 47.78 MB/s
  against 54.87–60.58 for the other five applications, and its p05 stall floor
  is 6.3 MB/s where AltMount, InfiniDysk, NZBDav-og and decypharr hold
  40–44. The clean-start noise floor this round is 9.1%, so the gap to the
  field (about 16% below the six applications' median of 57.22) is resolved by
  this pass. On
  round 13's shared two-core host zurg had the highest observed median; on
  four dedicated cores the field overtakes it.
- **zurg still opens fastest.** Cold-open median 2.5 ms and first byte under
  1 ms, ahead of AIOStreams (5.2 ms) and AltMount (53.1 ms).
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

## Rates and latency

Medians over the five positive entries, MB/s and seconds. The worst per-entry
clean-start swing between the two noise passes was 9.1%: a difference smaller
than that is not resolved by one pass.

| Target | Sequential | p05 stall floor | Cold open | Seek first byte |
|---|---|---|---|---|
| NZBDav-og | 60.58 | 43.76 | 0.2007 | 0.713 |
| raw | 59.55 | — | 0.5497 | 1.948 |
| InfiniDysk | 57.73 | 44.10 | 0.1532 | 0.614 |
| AltMount | 57.37 | 39.73 | 0.0531 | 0.145 |
| decypharr | 57.07 | 43.13 | 0.6454 | 1.040 |
| AIOStreams | 54.87 | 8.39 | 0.0052 | 0.004 |
| zurg | 47.78 | 6.34 | 0.0025 | 0.617 |

**AIOStreams' rates on three entries are its cache, not the network.**
`plain-video`, `damaged-partial` and `obfuscated` are the same 1,662 articles
under three names (1,661 for the damaged one), imported in that order, and
AIOStreams keeps an 8 GB segment cache on disk: it read them at 54.87, 179.02
and 1,938.07 MB/s. The median above is its uncached `plain-video` value, but
its position in the table owes something to the repetition. Round 13 shows the
same rise (19.8, 39.6, 58.0). The next harness should give those entries
distinct posts or reset a target's cache between entries.

InfiniDysk read the stored RAR entry at 2.27 MB/s against 27.88–56.90 for the
rest, which pulls its row down on that one shape.

## Resource cost

Normalized by delivered sequential GiB. Lower is better throughout; `raw` is
the transport control and is not ranked.

| Target | CPU s/GiB | CPU p95 cores | Peak RSS MiB | Disk write MiB/GiB | State growth MiB |
|---|---|---|---|---|---|
| decypharr | 4.84 | 0.16 | 214 | 1297.71 | 1.34 |
| AltMount | 6.20 | 0.18 | 1064 | 1.41 | 6.28 |
| AIOStreams | 7.10 | 0.36 | 773 | 543.44 | 4671.82 |
| zurg | 10.75 | 0.27 | 1061 | 21.11 | 101.73 |
| InfiniDysk | 21.70 | 0.27 | 930 | 25.09 | 20.96 |
| NZBDav-og | 27.36 | 0.77 | 442 | 18.59 | 5.87 |

decypharr's disk writes are consistent with its new sparse per-stream disk
cache, which upstream no longer caps at 256 MiB (source reading, not measured
per file).

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
- AIOStreams' cache inflates three of its five entries (above).
- Two real-post prerequisites unavailable; compression and passwordless
  encrypted RAR behaviour remain unmeasured.
- Socket sampling every second; no claim about sub-second transient sockets.
- Configuration is round 13's source-informed review plus the settings above,
  not a corpus-tuned optimum. Images depend on mutable base/compiler tags.
