# Usenet streaming benchmark

Five servers that stream Usenet content on demand. This round was measured on 1 September 2026. One host. One news account. One server running at a time. Every target on the same connection count and with repair switched on wherever the feature exists.

The targets are zurg and AltMount and InfiniDysk and nzbdav and decypharr. Every one of them was built from its repository main HEAD on the day of the run. The harness that produced every number here is in `harness/`. The raw output is in `results/`.

Round 4 of 30 August 2026 is kept in `results/round4/` and its report is in `docs/round4.md`. Read the section on what changed before comparing the two.

A second run on dedicated hardware (round 8, 2 September 2026) is summarised in the next section and kept in `results/round8-hetzner/`.

## Round 8 — a second run on dedicated hardware

Round 7 ran on zen: two shared cores. To see whether the findings hold on a different machine, the whole suite was run again on a **Hetzner CCX23** — four dedicated vCPU, 16 GB — provisioned for the run and destroyed after it. Same isolation rules, same 20 connections per target, same corpus and same news account, every target rebuilt from current main on the day. Raw output is in `results/round8-hetzner/`.

Absolute numbers do not carry across the two runs. A bigger box moves the ceiling, and the caveat this README already makes — that a larger machine can reorder the CPU-bound targets — came true, and reordered the top two as well. What carries across is the head-to-head under identical conditions and the behaviour, which reproduced.

**Throughput, 256 MB cold reads, six repetitions, rotating order, MB/s**

| | AltMount | zurg | nzbdav | InfiniDysk | decypharr |
|---|---|---|---|---|---|
| Mean | **63.3** | 58.5 | 44.3 | 27.0 | 4.6 |
| Slowest to fastest | 48.0-82.2 | 53.3-64.7 | 38.6-46.6 | 25.2-28.6 | 3.5-6.8 |
| CPU seconds per GB | 5.1 | 6.0 | 36.2 | 31.3 | 18.4 |
| Reads that finished | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 |

### Where zurg does not lead, and why

This is the point of running on more than one box.

- **Raw throughput went to AltMount** — 63.3 MB/s mean against zurg's 58.5, and a peak of 82.2 against 64.7. On zen's two shared cores round 7 had zurg ahead, 36.5 against 30.4. Give the fetchers four dedicated cores and an account with far more connection headroom than 20 uses, and AltMount's more aggressive parallel fetch bursts higher. It is a peak-against-consistency trade: AltMount ran 48 to 82 across the six reps, zurg ran a tight 53 to 65, so zurg keeps the highest floor — 53.3 slowest read against AltMount's 48.0 — and the lowest cold open and time to first byte. On this workload the peak belongs to AltMount and the predictability to zurg.
- **CPU per GB also went to AltMount**, but barely: 5.1 against 6.0, and both are roughly six times leaner than InfiniDysk and nzbdav at 31 and 36.
- **The fastest time to first byte was InfiniDysk**, 0.02 s against zurg's 0.28 s, because InfiniDysk serves the first byte out of segments it cached during import. zurg still wins the fuller cold open — the first megabyte, which is what a viewer feels on pressing play — at 0.38 s.
- One 64 MB sequential read and the scrub median went to nzbdav and InfiniDysk. Treat those two as noise rather than quote them. The latency phase is a single pass, and one sample of zurg at 25 MB/s against a six-rep throughput mean of 58.5 is a measurement artefact, not a ceiling. A multi-pass latency run — the `PASS_IX` shift now in `phase2_5r7.py` — would settle it.

### What reproduced

zurg is still the only one of the five that rebuilds a damaged article: silence at t0, real bytes by t+2 minutes, held through t+8, while AltMount and InfiniDysk zero-filled, nzbdav refused the file, and decypharr served zero bytes — all with repair enabled wherever the feature exists. zurg and AltMount still produced the only clean obfuscated listings, and zurg and nzbdav the only structure-preserving RAR output. Every server that served a range returned the same md5, on this box as on zen.

### Harness changes made in response to issue #1

The review in issue #1 was largely correct. Beyond the container-name and control fixes already reflected in round 8, the following landed after round 8 and apply to the next run:

- Throughput now has a dedicated byte-identity phase (`byteid_r7.py`) that hashes the same 16 MB range from every target and compares md5s, so identity is proven rather than inferred from an equal ffprobe duration.
- Each throughput read records the observed peak concurrent `:563` socket count, so "20 connections" is a measured number rather than only a configured cap.
- CPU per read subtracts an idle baseline sampled while the server is up but not reading, so a target's background services and per-restart startup are not charged to the read. The raw figure is kept alongside.
- RSS is sampled during the transfer and the peak kept, rather than the larger of a before and after snapshot.
- The latency phase validates every read for a 206 and the full byte count, drops short scrub samples, and runs each read shape on a freshly started server. The warm re-read still pairs with its big read on the same instance so the warm cache is real.
- `prep-r7.sh` writes a runtime-identity artifact (image digests, container env, binary sha256, effective settings, pinned commits) so numbers are tied to the measured process, and it accepts `SEGMENT_CACHE_OFF=1` to run InfiniDysk with its segment cache disabled for a separate cache-off comparison.

Still open: the .NET JIT cost on a first read is only partly addressed by the idle baseline, and the cache-off comparison needs a run to produce numbers.

The detailed round-7 run — full method, latency, the behaviour phases and the round-4 comparison — follows.

## What changed in this round

Two things, and both of them make the comparison harder for zurg rather than easier.

**Every target now gets exactly 20 NNTP connections.** Round 4 did not verify this and round 6 was measurably wrong about it. In three of the five servers the provider connection cap and the read budget are separate settings, so a config that says 20 in the obvious place can still be reading on 15 or on 50.

| | provider pool | read budget | what round 6 actually ran |
|---|---|---|---|
| zurg | `connections` | same | 20 |
| AltMount | `max_connections` | same | 20 |
| InfiniDysk | `MaxConnections` | `usenet.max-download-connections` | **50**, because the read budget was unset and unset means auto, and auto resolves to the pool total |
| decypharr | `providers[].max_connections` | `usenet.max_connections` | 20 pool but **15** per streaming file |
| nzbdav | `providers[].MaxConnections` | `usenet.max-download-connections` | 20 pool but **15** reading |

That matters more than any difference between these programs. InfiniDysk ships a connection tuner and on this account it measures about 25 MB/s at 20 connections and about 44 MB/s at 40. Throughput scales close to linearly with the count. A benchmark that lets one target hold 50 while the others hold 20 is measuring the connection count.

**Repair is now enabled on every target that has the feature.** In round 4 AltMount and decypharr ran with repair off, so "only zurg repaired the damage" was partly a statement about configuration. This round enables it everywhere and gives decypharr a schedule that can actually fire inside the measurement window, because its defaults are a nightly sweep with a 168 hour recheck interval and nothing would ever have run.

| | repair in this round | how |
|---|---|---|
| zurg | on | `enable_repair: true` |
| InfiniDysk | on, with PAR2 | `REPAIR__ENABLE`, `REPAIR__PAR2_ENABLED` |
| AltMount | on | repair is nested under `health`, so `health.enabled` must be true as well |
| decypharr | on | `repair.enabled` with `source: managed`, a 5 minute schedule and a 1 minute recheck |
| nzbdav | no such feature | its PAR2 code only recovers obfuscated filenames |

## Versions

Each target was built from main rather than from a release tag. The point was to measure what the projects are today and not what they last shipped.

| | version under test | source |
|---|---|---|
| **zurg** | `3d9fbcc4` | private repository, source access is sponsor-only |
| **AltMount** | `7ab04352` | `javi11/altmount` |
| **InfiniDysk** | `cd9b1205` | `infinidysk/infinidysk` |
| **nzbdav** | `794948be` | `nzbdav-dev/nzbdav` |
| **decypharr** | `0dd1cbbd` | `sirrobot01/decypharr` |
| Host | zen, 2 cores, 7.6 GB RAM | |

nzbdav main has had no commit since 27 May 2026 and its published `pre-release` image is that same commit. Nothing about nzbdav changed between rounds.

`results/round7/results_r7_versions.json` carries the same table plus the build timestamp.

## Method

The isolation rule is the whole basis of the comparison. Every target keeps a pool of NNTP sockets warm. Two running at once oversubscribe the account and skew both. So `bench5.py` starts one target and reads and stops it before the next one starts. It also waits for that target's sockets to drain before continuing.

Order rotates by repetition. Provider throughput drifts over an evening. Rotating the order means drift cannot favour whoever always goes first.

Byte offsets were chosen so that no read overlapped any read from an earlier round. Every measurement here is genuinely cold.

The host runs a production zurg against the same account but against a different server of that provider. Connection caps on this provider are per server, so it contends with nothing here. `bench5.py` excludes that process id from its drain check so a stop does not wait forever on sockets that will never close.

Byte identity was verified on the behaviour releases, not on the throughput file. The throughput reads all go to `/dev/null` and are never hashed, so what is established there is the same ffprobe duration of 6206.752 seconds across all five, which is weaker than a hash. On the RAR release all five returned the same md5 `79d1e148021c44ce018c9c47eb504d39` for the same 16 MB range and advertised the same content length of 321905886 bytes, and on the obfuscated release all five returned the same md5 for the same 8 MB range. Hashing the throughput reads as well is a todo.

## Throughput

256 MB cold reads. Six repetitions. Rotating order. Offsets from 1.5 GB to 5.5 GB in 0.8 GB steps.

| | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|
| Mean MB/s | **36.54** | 30.38 | 19.18 | 17.66 | 8.28 |
| Median MB/s | **37.70** | 28.55 | 19.20 | 17.74 | 8.83 |
| Slowest to fastest | 20.5-47.1 | 27.0-36.5 | 13.1-26.4 | 15.5-19.2 | 3.1-13.9 |
| Wait before data arrives | **0.63 s** | 3.33 s | 1.44 s | 4.92 s | 5.24 s |
| CPU seconds per GB | **8.8** | 9.7 | 48.4 | 60.6 | 31.0 |
| RSS, coarse (see note) | 360 MB | 272 MB | 540 MB | 546 MB | 50 MB |
| Reads that finished | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 |

The RSS row is not a true peak. `bench5.py` samples RSS once before and once after each read and keeps the larger of the two, and the table means those per-rep values. It undercounts a peak that lands mid-read: InfiniDysk's largest single sample was 641 MB against the 540 reported. Read it as a rough footprint, not a maximum. Sampling during the transfer is the fix and is a todo.

Per repetition, in MB/s. The first repetition is not representative of anything and is included because leaving it out would be dishonest.

| rep | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|
| 0 | 20.50 | 33.96 | 13.71 | 15.46 | 9.31 |
| 1 | 35.81 | 27.62 | 21.99 | 17.68 | 3.14 |
| 2 | 47.08 | 27.04 | 16.40 | 18.54 | 9.32 |
| 3 | 36.30 | 28.91 | 13.11 | 19.16 | 5.68 |
| 4 | 40.44 | 36.53 | 23.52 | 17.34 | 8.35 |
| 5 | 39.10 | 28.19 | 26.38 | 17.80 | 13.86 |

Every target finished every read this round. Round 4 had one target truncating four of six.

The CPU spread is wider than the throughput spread and gets less attention than it deserves. InfiniDysk and nzbdav spend 48 and 61 CPU seconds per GB against zurg's 8.8, for less than half the throughput. On a two core box that is a real ceiling.

Source is `results/round7/results_six7.json` and `results/round7/six7.log`.

## Latency

| | zurg | InfiniDysk | AltMount | nzbdav | decypharr |
|---|---|---|---|---|---|
| Cold open, first MB | **0.55 s** | 0.777 s | 2.591 s | 4.983 s | 5.413 s |
| Time to first byte | 0.257 s | **0.077 s** | 2.616 s | 1.409 s | 3.647 s |
| Large sequential read | 21.03 MB/s | 19.03 MB/s | **22.48 MB/s** | 8.54 MB/s | 12.70 MB/s |
| Warm re-read | 0.079 s | 0.496 s | 1.533 s | 6.48 s | **0.068 s** |
| Scrub, median of 8 | 0.801 s | **0.492 s** | 0.521 s | 2.187 s | 3.768 s |
| Full ffprobe | **2.42 s** | 4.00 s | 6.92 s | 4.69 s | 10.60 s |
| RSS | 475 MB | 856 MB | 228 MB | 479 MB | 51 MB |

Nine point eight times separates the fastest cold open from the slowest. That is the number a viewer feels when they press play.

InfiniDysk is much closer here than it is on throughput, and that is coherent rather than contradictory. Latency is one round trip. Sustained throughput is where a connection budget shows up, and this round took its budget down from an effective 50 to the same 20 as everyone else.

An earlier version of this section called nzbdav's 6.48 s warm re-read an anomaly for being slower than its 4.98 s cold open. That comparison was wrong: the cold open reads 1 MiB and the warm re-read reads 64 MiB, so they are not comparable. Against the correct baseline, nzbdav's first 64 MiB read at 8.54 MB/s took about 7.86 s, so the 6.48 s warm re-read was in fact faster. There is no anomaly. The single-pass caveat below still applies.

These latency numbers are a single pass per target. The phase starts each server once and runs cold open, large read, warm re-read, scrub and ffprobe in sequence, so later shapes inherit cache from earlier ones, and the reads do not assert a 206 or a byte count. Read the table as n=1 and lightly validated. A multi-pass mode with per-pass offset shifting is in `phase2_5r7.py`; per-shape server restarts and completeness checks are a todo.

Source is `results/round7/results_latency_r7.json`.

## Damaged article and obfuscated release and multi-volume RAR

Three behaviour phases run from `corpus5b.py` through `chain7.sh`. They ask what a server does when the content is not clean.

- **damage** reads 4 MB at offset 80 MB of a release where one article is gone from the server. The question is whether the server repairs the hole or zero-fills it or truncates or refuses the file.
- **obfuscated** reads 8 MB at offset 400 MB of a fully obfuscated release. The question is whether the server can identify the video at all when every filename is a hash.
- **rar** reads 16 MB at offset 100 MB inside a multi-volume RAR set. The question is whether the server can stream out of the archive without extracting it.

**Use `reprobe_r7.py` and not the phase output.** It re-runs the same probes, selects the release by exact name and selects the largest non-sample video inside it. The phase output picks whatever appeared in the listing during the import and picks the first video it finds, and both of those produced wrong numbers in this round. See the harness corrections below.

### Damaged article

One article of 1669 is gone from the news server. That is roughly 40 seconds of film. The read is 4 MB at offset 80 MB and it lands on the hole. Every server was read once immediately and then again every two minutes for eight minutes, staying up throughout.

| | first read | t+2 | t+4 | t+6 | t+8 | verdict |
|---|---|---|---|---|---|---|
| **zurg** | silence | silence | **real** | **real** | **real** | **Served real bytes from t+4 on**, consistent with a background rebuild of the span while reads were still being served |
| AltMount | silence | silence | silence | silence | silence | Did not repair inside the window, with repair enabled |
| InfiniDysk | silence | silence | silence | silence | silence | Did not repair inside the window, with repair and PAR2 enabled |
| decypharr | 206 with zero bytes | same | same | same | same | Did not repair inside the window, with repair enabled and a schedule that fires |
| nzbdav | HTTP 404 | 404 | 404 | 404 | 404 | Refuses the whole file. It has no repair feature |

zurg is the only one of the five that rebuilt the missing span inside the window. The defensible claim here is exactly that, an eight-minute observation at 20 connections with repair enabled where the feature exists. It is not proof that the others can never repair, only that they did not here. The harness records no repair-job state or logs, so a longer window or a different provider could read differently. What it does show is that under an identical eight minutes only zurg served real bytes back.

This is the same result round 4 reported and it is now a much stronger claim. In round 4 two of the four others had repair switched off, so the finding was partly about configuration. This round they were switched on, decypharr was given a schedule that fires inside the window, and all five held the same 20 connections. Nothing else repaired.

A single read at t0 cannot tell repair apart from permanent zero-fill. Both answer silence. Only the re-read separates them.

Source is `results/round7/results_damage_timeline_r7.json`.

### Obfuscated release

Every filename in the release is a hash. The read is 8 MB at offset 400 MB.

| | serves the video | how the listing looks |
|---|---|---|
| **zurg** | 206 with all 8 MB | **clean.** The real filename and a thumbnail and nothing else |
| AltMount | 206 with all 8 MB | real filename, plus a duplicate `..._1.mkv` |
| InfiniDysk | 206 with all 8 MB | names the file after the NZB rather than the content, and leaves 5 raw hashed blobs visible |
| nzbdav | 206 with all 8 MB | recovers the real filename but leaves 5 raw hashed blobs visible |
| decypharr | release absent from the listing | never imported it |

Four of five identify the video behind the hashed names and stream it. decypharr never imported the release at all, and that has now reproduced in every round it has been tried in.

Only zurg produces a listing a media server can scan without tripping over the leftovers.

Source is `results/round7/results_reprobe_r7.json`.

### Multi-volume RAR

A 13 part RAR set with obfuscated volume names. The read is 16 MB at offset 100 MB inside the archive. No extraction.

All five serve it. All five return the same md5 for the same range. The difference is entirely in how they present it.

| | result | preserves the archive's structure |
|---|---|---|
| **zurg** | 206 with all 16 MB | **yes, completely.** Nested release directory, `Sample/`, the `.nfo` and both `.url` files |
| nzbdav | 206 with all 16 MB | yes, except the `.nfo` is missing |
| InfiniDysk | 206 with all 16 MB | no, flattened to `FatherBrown.mp4` |
| AltMount | 206 with all 16 MB | no, flattened, and it emits a stray `8-FatherBrown.mp4` alongside |
| decypharr | 206 with all 16 MB | no, flattened to one concatenated name `Father.Brown.2013.S02E05.HDTV.x264-TLAfather.brown.2013.s02e05.hdtv.x264-tla.mp4` |

The reference for this is what SABnzbd would have written to disk. It decompresses archives including nested ones, it hides PAR2 files, and the filenames are the ones inside the archive. No server here shows a PAR2 file, so all five meet that part. On the rest, zurg's output is the one that matches.

Source is `results/round7/results_reprobe_r7_rar.json`.

## Findings

**zurg leads on throughput and on cold open and on CPU cost, at equal connections.** 36.54 MB/s mean with 6 of 6 reads complete, a 0.55 s cold open, and 8.8 CPU seconds per GB. The margins are narrower than round 4 reported, and part of that is real improvement by others rather than any change in zurg.

**zurg is the only one of five that repairs a damaged release, and this round proves it properly.** Repair was enabled on every target that has the feature and the other three still zero-filled or refused for the full eight minutes.

**Connection budgets were not equal in earlier rounds and nobody had checked.** One target was reading on an effective 50 connections while two were reading on 15. Anyone repeating this work should set both settings on every target and verify them after the servers start rather than trusting the config file.

**decypharr never imports the obfuscated release.** Absent from the listing rather than present and broken. It has reproduced every time.

**Presentation differs more than throughput does.** Three of five flatten a RAR release's internal structure, two leave undeobfuscated blobs in the listing, and one emits duplicate video files that would make a media server import the same episode twice.

## Harness corrections

Three bugs in this harness each produced a wrong number before being caught in this round. Two of them produced numbers that were wrong against zurg. They are listed here because a benchmark that hides its own errors is not worth reading.

**Settle declared the library complete while imports were still running.** It waited for the WebDAV listing to stop changing for 90 seconds. At 20 connections InfiniDysk publishes one release and then takes longer than that to fetch the next release's first segments, so the detector called the library finished with 1 of 5 releases in it and the read that followed returned 0 bytes. Round 6 never saw this because it ran that target on 50 connections where the gaps were short. Settle now also requires the import queue to have drained.

**The behaviour phases slept a fixed 55 seconds after an import.** That is a guess about connection count wearing a timer's clothes. It now polls for the release to appear or for the queue to drain, and reports how long that took, which is a useful number in itself. Actual import waits this round were 10 to 20 seconds.

**Release and file selection picked the wrong thing twice.** The phase output picks whatever appeared in the listing during the import, so a late arriving unrelated release gets probed instead. And the re-probe picked the first video in the listing, which on a server that preserves `Sample/` is a 9.1 MB sample clip. A 16 MB read at offset 100 MB of a 9.1 MB file is a correct HTTP 416 and it reads as a server failure. Round 4 documented this trap in prose and no code ever implemented it. `reprobe_r7.py` now selects the release by exact name and the largest non-sample video inside it.

## Not measured in this round

**Plex press play and next episode.** Round 4 measured these through the real Plex web app over the DevTools Protocol. The browser host was unavailable when this round ran. The round 4 numbers are in `results/round4/plex_ttp_*.json` and they are not comparable to this round because the provider server differs.

**Import and directory structure as a scored phase.** The tree phase needs a clean re-run under the corrected settle. Its raw per target listings are in `results/round7/` and the RAR and obfuscated structure findings above are taken from those listings, which are sound. What is not yet sound is import timing and completeness.

## Corpus

`corpus/corpus.7z` holds the NZBs the run used. It is a 7-Zip archive with encrypted headers. The password is `dmmbench`.

The password is not access control. The password is published right here. The archive exists so release names and message ids stay out of search indexes and automated scrapers. Anyone who wants the corpus can have it.

`rar` was not available on the build host so 7-Zip with `-mhe=on` was used instead. Extract with `7z x -pdmmbench corpus.7z`.

| NZB | files | articles | approx bytes | sha256 prefix |
|---|---|---|---|---|
| ToyStory5.nzb | 7 | 1669 | 7164735989 | `9add0ee889f54187` |
| ToyStory5Damaged.nzb | 7 | 1669 | 7164735989 | `90b9bdccb56a8f91` |
| Obfuscated.nzb | 7 | 1669 | 7164735989 | `6794d1464e7cb28c` |
| FatherBrown.nzb | 17 | 1027 | 394141285 | `55ed581204b3d83b` |
| Bosch.S01.nzb | 20 | 32870 | 24290014587 | `c9b60371473825b0` |

`corpus/manifest.json` carries the same table in machine readable form. `stat_probe.py` will tell you whether a given NZB is still retrievable from your provider before you waste a run on it.

Provider spool quality is not uniform and it decides what the damage phase can even claim. On the account this round used, a sample of the twelve most damaged releases in a production library found 61.5 percent of content articles dead against 6.0 percent on a different backbone. Every NZB in this corpus was checked as fully retrievable before the run. Four other candidates were rejected for this reason and are not in the corpus.

## Reproducing this

### Prerequisites

- a Usenet account with at least 20 connections
- Python 3 with `playwright` for the Plex phase only
- `rclone`, `ffprobe`, `curl`, `7z`
- Docker for the InfiniDysk and nzbdav targets
- a Plex server and a Chrome reachable over the DevTools Protocol for the Plex phase

### Fill in the placeholders

Every credential in this repository is a placeholder. Nothing here is live. Replace these before running anything.

| file | placeholder |
|---|---|
| `config/zurgrun/config.yml` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `config/decyrun/config.json` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `config/altmount/config.yaml` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `config/infinidysk.env.json` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/prep-r7.sh` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/stat_probe.py` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/stat_one.py` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/plex/plex_ttp3.py` | `YOUR_PLEX_HOST`, `YOUR_PLEX_TOKEN`, `YOUR_PLEX_MACHINE_IDENTIFIER` |
| `harness/bench5.py` | `YOUR_STREAMNZB_STREAM_TOKEN`, needed only if you re-enable that target |

The provider hostname is `news.news-provider.example` everywhere. Replace it with your own.

Paths are absolute and assume the layout the run used. `BENCH` in `bench5.py` and the paths in `plexmnt.sh` and `chain7.sh` will need to match wherever you put this.

### Run the phases

```bash
# build every target from its main HEAD and record the commits
./build-r7.sh

# install the builds, set 20 connections everywhere, enable repair, create containers
./prep-r7.sh

# the whole round in order
./chain7.sh
```

Or one phase at a time.

```bash
# throughput: tag, MB per read, base offset, gap in GB, reps, targets
python3 bench5.py six7 256 1500000000 0.8 6 zurg,decypharr,altmount,infinidysk,nzbdav-og

# latency: cold open, TTFB, scrub, warm re-read, ffprobe
python3 phase2_5r7.py zurg,decypharr,altmount,infinidysk,nzbdav-og

# a repeated latency pass: PASS_IX shifts every offset into untouched bytes and
# the tag names the output file. Without the shift a second pass measures a
# target's on-disk segment cache rather than the server.
PASS_IX=1 python3 phase2_5r7.py zurg,decypharr,altmount,infinidysk,nzbdav-og c2

# behaviour: damage, obfuscated, rar
python3 corpus5b.py damage zurg,decypharr,altmount,infinidysk,nzbdav-og

# re-probe selecting the release by name and the largest non-sample video. use this one
python3 reprobe_r7.py
python3 reprobe_r7.py rar      # a single phase

# does a server rebuild the hole while it stays up
python3 damage_timeline_r7.py

# is this NZB still retrievable
python3 stat_probe.py corpus/Bosch.S01.nzb
```

### Verify the connection parity before trusting a run

This is the step that round 6 skipped and it invalidated a whole round. `prep-r7.sh` now runs these checks itself, re-reading every value from disk and from `docker inspect`, and refuses to finish on a mismatch. The commands below remain for checking by hand. After `prep-r7.sh`, both settings should read 20 on every target.

```bash
grep connections zurgrun/config.yml
grep max_connections altmount/config.yaml
python3 -c "import json;u=json.load(open('decyrun/config.json'))['usenet'];print(u['max_connections'],u['processing_max_connections'],[p['max_connections'] for p in u['providers']])"
docker inspect infinidysk-r7 --format '{{json .Config.Env}}' | tr ',' '\n' | grep -i connection
sqlite3 nzbdav-og/config/db.sqlite "select * from ConfigItems where ConfigName like 'usenet%'"
```

## Harness gotchas

**`corpus5b.py` picks the release under test as whatever appeared in the listing during the import.** That is wrong whenever a server is still loading its library when the baseline listing is taken. A late arriving unrelated release looks new and gets probed instead. Use `reprobe_r7.py` which selects by name.

**The first video in a listing is not the release.** A server that preserves an archive's internal structure lists `Sample/` before the feature. Selecting the first video picks a 9.1 MB sample clip and a large ranged read of it is a correct 416. Select the largest non-sample video.

**A single read cannot tell repair from permanent zero-fill.** Both answer silence at t0. Only a re-read minutes later separates them.

**Sampling cannot disprove "one article missing".** One server removed a whole release claiming 1 missing of 848. `stat_all.py` checked every article and found 1010 of 1010 present. Use it and not the 3 per file sampler whenever a server blames the content.

**A fixed sleep after an import is a guess about connection count.** At 20 connections some targets need far longer than 55 seconds to publish a release. Poll for the release or for the queue to drain.

**decypharr's SABnzbd mock is at `/sabnzbd/api` and the upload field is `name`.** A wrong field returns HTTP 200 with `{"status": false, "error": "No files uploaded"}`. A status code check treats that as success and then waits for an import that never happened.

**`rclone mount --daemon` over ssh never returns.** It holds the ssh channel's stdout open. Use `ssh -n` and redirect on the remote side.

## Limitations

Read these before quoting any number.

- Single host with 2 cores. A larger box would move the ceiling and might reorder the CPU-bound targets. The host also runs Plex and Jellyfin and a game server, which is constant background load across all rounds.
- Single interleaved run. Cross-round comparison is not valid because provider throughput drifts and because this round used a different server of the same provider than round 4 did.
- One news account and one provider. Results on a different backbone may differ. This provider's spool is measurably weaker than others available, which bounds what the damage phase can claim.
- No Plex measurements in this round.
- zurg is the author's own project. Every number here is reproducible from this repository against your own account. Do that rather than taking this at face value.

## Layout

```
harness/          the benchmark scripts
harness/plex/     the Plex phase, which runs where the browser is
config/           the server configs used, credentials replaced
corpus/           the NZB corpus and its manifest
results/round8-hetzner/  the dedicated-hardware run (round 8)
results/round7/   this round
results/round4/   the previous published round
results/round3/   the round before that
docs/round4.md    the round 4 report
```
