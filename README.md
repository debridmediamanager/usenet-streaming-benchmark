# Usenet streaming benchmark

Five servers that stream Usenet content on demand. All measured on 30 August 2026. One host. One news account. One server running at a time.

The targets are zurg and AltMount and InfiniDysk and nzbdav and decypharr. Every one of them was built from its repository main HEAD on the day of the run. The harness that produced every number here is in `harness/`. The raw output is in `results/`.

## Versions

Each target was built from main rather than from a release tag. The point was to measure what the projects are today and not what they last shipped.

| | version under test | source |
|---|---|---|
| **zurg** | `b834f902` | private repository, source access is sponsor-only |
| **AltMount** | `3ed4c479` | `javi11/altmount` |
| **InfiniDysk** | image `dev-260830.0121`, commit `5e89125a` | `infinidysk/infinidysk` |
| **nzbdav** | `794948be` | `nzbdav-dev/nzbdav` |
| **decypharr** | `0dd1cbbd` | `sirrobot01/decypharr` |
| Host | zen, 2 cores, 7.6 GB RAM | |

Two caveats belong here rather than in a footnote.

The InfiniDysk image was one commit behind main when the run started. That commit was a user interface fix and touches nothing on the streaming path.

nzbdav main has had no commit since 27 May 2026. Its published `pre-release` image is that same commit. Nothing about nzbdav changed between rounds.

streamnzb was dropped from this round. Its public repository has main at v4.11.0 while the binary it ships is v5.14.0-abaee98. That commit is on no public branch and there are no GitHub releases. There was no verifiable latest main to test so it was excluded rather than guessed at.

## Method

The isolation rule is the whole basis of the comparison. Every target keeps a pool of NNTP sockets warm. Two running at once oversubscribe the account and skew both. So `bench5.py` starts one target and reads and stops it before the next one starts. It also waits for that target's sockets to drain before continuing.

Order rotates by repetition. Provider throughput drifts over an evening. Rotating the order means drift cannot favour whoever always goes first.

Byte offsets were chosen so that no read overlapped any read from an earlier round. Every measurement here is genuinely cold. On-disk segment caches were cleared before the run for the one target that keeps them.

The host runs a production zurg against the same news account. It holds about 2 idle sockets. `bench5.py` excludes that process id from its drain check so a stop does not wait forever on sockets that will never close. During measurement the target under test held between 9 and 23 sockets against those 2.

Byte identity was verified two ways. All five servers reported the same ffprobe duration of 6206.752 seconds for the throughput file. All five reported byte-identical sizes for all ten episodes of the Plex corpus. The one exception is described below and it is a missing file rather than a wrong size.

## Throughput

256 MB cold reads. Six repetitions. Rotating order. Offsets from 1.5 GB to 5.5 GB in 0.8 GB steps.

| | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|
| Mean MB/s | **48.42** | 36.65 | 25.58 | 18.51 | 12.94 |
| Median MB/s | 49.09 | 36.65 | 25.56 | 18.46 | 13.24 |
| Min to max | 43.28-52.03 | 33.95-39.35 | 23.98-27.09 | 17.71-19.03 | 8.66-16.31 |
| **Reads completed** | **6 of 6** | **2 of 6** | 6 of 6 | 6 of 6 | 6 of 6 |
| Mean TTFB, s | **0.85** | 2.89 | 1.50 | 3.81 | 3.61 |
| CPU seconds per GB | 7.6 | **7.5** | 36.1 | 61.7 | 24.4 |
| RSS, MB | 353 | 172 | 466 | 559 | **51** |

The AltMount mean is computed over the two reads that finished. Four of six did not.

Per repetition in MB/s. `FAILED` is a read that did not deliver the bytes it promised.

| rep | offset | zurg | AltMount | InfiniDysk | nzbdav | decypharr |
|---|---|---|---|---|---|---|
| 0 | 1.5 GB | 49.35 | FAILED | 24.89 | 18.44 | 8.66 |
| 1 | 2.3 GB | 52.03 | FAILED | 27.09 | 19.03 | 10.35 |
| 2 | 3.1 GB | 50.56 | FAILED | 24.59 | 18.41 | 15.81 |
| 3 | 3.9 GB | 43.28 | 39.35 | 23.98 | 17.71 | 12.39 |
| 4 | 4.7 GB | 46.46 | FAILED | 26.23 | 18.49 | 16.31 |
| 5 | 5.5 GB | 48.83 | 33.95 | 26.71 | 19.00 | 14.09 |

Source is `results/round4/results_six4.json` and `results/round4/six4.log`.

## Latency

What pressing play and seeking and scanning actually feel like. Each shape runs against a freshly started server so nothing is warm.

| seconds, lower is better | zurg | InfiniDysk | AltMount | decypharr | nzbdav |
|---|---|---|---|---|---|
| Cold open, first MB | **0.301** | 1.328 | 1.722 | 3.496 | 5.299 |
| Time to first byte | **0.350** | 1.122 | 0.436 | 2.479 | 2.366 |
| Scrub, median of 8 x 2 MB | **0.396** | 0.604 | 0.493 | 2.499 | 2.302 |
| Warm re-read, 64 MB | 0.098 | 4.977 | 1.548 | **0.065** | 6.637 |
| ffprobe over HTTP | **1.33** | 2.72 | 2.70 | 4.09 | 3.82 |
| Large read MB/s | 24.20 | 14.55 | **24.38** | 17.73 | 9.10 |
| RSS, MB | 437 | 949 | 225 | **53** | 439 |

Cold open is the number that matters when someone presses play. The gap there is 4.4x between first and second place.

Three of the five are slower re-reading a range than reading it the first time. That is what a missing cache looks like. It costs on every Plex rescan.

Source is `results/round4/results_latency_r4.json`.

## Plex press play and next episode

This is the part a viewer actually experiences. The measurement runs through the real Plex web application driven over the Chrome DevTools Protocol. It is not a synthetic HTTP read.

Two numbers per repetition. `press play` is from clicking an episode's Play control to the first rendered frame. `next episode` is from clicking the player's Next control to the first rendered frame of the following episode.

Each repetition uses an untouched pair of episodes so nothing is ever served warm. Four pairs were used. E01 to E02 then E03 to E04 then E05 to E06 then E09 to E10.

| seconds, lower is better | zurg | AltMount | nzbdav | decypharr | InfiniDysk |
|---|---|---|---|---|---|
| Press play, mean | **3.43** | 4.37 | 5.49 | 5.52 | 5.83 |
| Press play, median | **3.36** | 4.54 | 5.24 | 5.56 | 5.55 |
| Press play, min to max | 3.22-3.76 | 3.36-5.02 | 4.82-6.64 | 4.68-6.32 | 5.18-7.04 |
| Next episode, mean | **4.19** | 5.26 | 5.94 | 5.57 | 5.92 |
| Next episode, median | **3.93** | 4.51 | 5.56 | 5.06 | 5.68 |
| Next episode, min to max | 2.42-6.49 | 4.24-7.76 | 4.45-8.20 | 3.61-8.04 | 5.22-7.10 |
| Repetitions completed | 4 of 4 | 4 of 4 | 4 of 4 | 3 of 4 | 4 of 4 |

Every repetition on every server direct-streamed the video. Plex reported `video=copy audio=transcode` in every one of the 19 completed repetitions and for both episodes in each. The video was never re-encoded. So these numbers measure the backend and not the transcoder. The constant audio transcode cost is present in every cell and cancels out of the comparison.

The one decypharr repetition that is missing was a harness fault and not a server fault. The episode row had not refreshed from Resume back to Play in time.

Source is `results/round4/plex_ttp_*.json`.

## Damaged article and obfuscated release and multi-volume RAR

Three behaviour phases run from `corpus5b.py` through `chain3.sh`. They ask what a server does when the content is not clean.

- **damage** reads 4 MB at offset 80 MB of a release where one article is gone from the server. The question is whether the server repairs the hole or zero-fills it or truncates or refuses the file.
- **obfuscated** reads 8 MB at offset 400 MB of a fully obfuscated release. The question is whether the server can identify the video at all when every filename is a hash.
- **rar** reads 16 MB at offset 100 MB inside a multi-volume RAR set. The question is whether the server can stream out of the archive without extracting it.

`reprobe_r4.py` re-runs the same probes and selects the release by name. Use that one. See the harness gotchas below for why.

### Damaged article

One article of 1669 is gone from the news server. That is roughly 40 seconds of
film. The read is 4 MB at offset 80 MB and it lands on the hole. Every server was
read once immediately and then again every two minutes.

| | first read | then what |
|---|---|---|
| **zurg** | silence in 0.01 s | **Repairs it.** The span came back real at the four minute re-read. PAR2 rebuilt it in the background while reads were still being served |
| AltMount | silence in 0.01 s | Zero-fills permanently. Byte-identical silence at 2 and 4 and 6 and 8 minutes |
| InfiniDysk | silence in 0.97 s | Zero-fills permanently. Same md5 at every re-read |
| decypharr | HTTP 206 with zero bytes in 4.70 s | Never recovers. Still zero bytes at 8 minutes |
| nzbdav | HTTP 404 in 6.73 s | Refuses the whole file |

zurg is the only one of the five that rebuilds the missing span. The others route
around the damage or give up.

A single read at t0 cannot tell repair apart from permanent zero-fill. Both answer
silence. Only the re-read separates them. The md5 `b5cfa9d6c8febd618f91ac2843d50a1c`
is the md5 of 4 MB of zeros. It appears on three servers at t0 and stays on two of
them forever.

Source is `results/round4/results_rar_damage_r4.json`.

### Obfuscated release

Every filename in the release is a hash. The read is 8 MB at offset 400 MB.

| | result | MB/s |
|---|---|---|
| **zurg** | 206 with all 8 MB | **10.97** |
| AltMount | 206 with all 8 MB | 4.20 |
| InfiniDysk | 206 with all 8 MB | 1.24 |
| nzbdav | 206 with all 8 MB | 0.56 |
| decypharr | release absent from the listing | n/a |

Four of five identify the video behind the hashed names and stream it. decypharr
never imported the release at all.

Source is `results/round4/results_reprobe_r4.json`.

### Multi-volume RAR

A 13 part RAR set with obfuscated volume names. The read is 16 MB at offset 100 MB
inside the archive. No extraction.

| | result | MB/s | preserves archive structure |
|---|---|---|---|
| **zurg** | 206 with all 16 MB | **9.13** | yes, including `Sample/` |
| decypharr | 206 with all 16 MB | 7.19 | no, flattened to one concatenated name |
| nzbdav | 206 with all 16 MB | 3.70 | yes |
| InfiniDysk | 206 with all 16 MB | 3.14 | yes |
| AltMount | release directory empty | n/a | n/a |

The four that serve it all advertise the same content length of 321905886 bytes.
That is the byte identity check for this phase.

Source is `results/round4/results_rar_damage_r4.json`.

## Findings

**zurg leads on every speed measurement in this round.** 48.42 MB/s mean throughput with 6 of 6 reads complete. 0.301 s cold open. 3.43 s to press play through Plex and 4.19 s to the next episode. Its CPU cost of 7.6 seconds per GB is within noise of the cheapest.

**One server truncates its first long read after a restart.** The response is an HTTP 206 carrying the full Content-Length. The socket then closes partway through. curl exits 18 and 95.6 MB of the promised 256 MB arrive. Four of six reads in the throughput run failed this way. A dedicated probe in `results/round4/results_amcold.json` isolates the cause. Three of four cold reads completed. Four of four completed when an 8 MB warm-up read preceded the large one. The first read after every restart is the one at risk.

**One server silently discarded a healthy episode at import.** Importing a ten episode season it imported nine. Its log recorded `Skipping file due to early fast-fail segment check error` against episode 7. The other four servers imported all ten and agreed byte for byte on every size including that episode. A direct NNTP probe of episode 7 found all 68 sampled articles present. That sample included the first 8 articles which are exactly what a fast-fail check would look at. Its first segment returned 739244 bytes of real body. The file was not damaged. Nothing warned that it had been dropped. It simply was not in the listing.

**The same server removed a second healthy release, and this one was measured exhaustively.** The multi-volume RAR release is served by the other four. On this one its directory is empty. Its own health API records the file as `corrupted` with `missing_articles: 1` of `total_articles: 848`. Every one of the 1010 articles in that NZB was then checked individually with NNTP STAT. All 1010 are present. Zero are missing. The detection is a false positive and the cost of it is the whole release rather than one span.

**One server never imported the obfuscated release at all.** It is absent from the listing rather than present and broken.

The full per episode size table is in `results/round4/results_plex_stage.json`.

## Corpus

`corpus/corpus.7z` holds the five NZBs the run used. It is a 7-Zip archive with encrypted headers. The password is `dmmbench`.

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
| `harness/stat_probe.py` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/stat_one.py` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/plex/plex_ttp3.py` | `YOUR_PLEX_HOST`, `YOUR_PLEX_TOKEN`, `YOUR_PLEX_MACHINE_IDENTIFIER` |
| `harness/bench5.py` | `YOUR_STREAMNZB_STREAM_TOKEN`, needed only if you re-enable that target |

The provider hostname is `news.news-provider.example` everywhere. Replace it with your own.

Paths are absolute and assume the layout the run used. `BENCH` in `bench5.py` and the paths in `plexmnt.sh` and `chain3.sh` will need to match wherever you put this.

### Run the phases

```bash
# throughput: tag, MB per read, base offset, gap in GB, reps, targets
python3 bench5.py six4 256 1500000000 0.8 6 zurg,decypharr,altmount,infinidysk,nzbdav-og

# latency: cold open, TTFB, scrub, warm re-read, ffprobe
python3 phase2_5r4.py zurg,decypharr,altmount,infinidysk,nzbdav-og

# behaviour: damage, obfuscated, rar
./chain3.sh
python3 reprobe_r4.py          # re-probe selecting the release by name

# the truncation probe, cold arm against warmed arm
python3 amcold.py

# is this NZB still retrievable
python3 stat_probe.py corpus/Bosch.S01.nzb
python3 stat_one.py corpus/Bosch.S01.nzb S01E07 60
python3 stat_all.py corpus/FatherBrown.nzb   # every article, no sampling

# summaries
python3 summary6.py six4.log
```

### Run the Plex phase

The Plex phase measures a real browser. It needs a Chrome started with `--remote-debugging-port` and reachable at the address in `plex_ttp3.py`.

```bash
./plexmnt.sh zurg              # mount one backend, rebuild the symlink farm
./plex_all.sh                  # switch backend, remount and measure, per server
python3 plex_summary.py .      # tabulate
```

`plexmnt.sh` mounts whichever backend is under test at one fixed path and rebuilds a symlink farm above it. Plex therefore sees identical paths whichever server is underneath. That is what lets one library section serve all five backends without a rescan. rclone VFS caching is off on purpose. A disk cache would hide exactly the cold open differences being measured.

## Harness gotchas

Every item here is a bug that produced a wrong number before it was found. They are the most reusable part of this repository.

**Plex media transitions need a trusted click.** A synthetic `element.click()` starts the first episode. The Next control then does nothing at all. It is present and enabled and inert. Switching media requires user activation. Playwright's `.click()` goes through the DevTools Input domain and counts. A JavaScript click does not.

**Playing from an episode's details page builds a one item play queue.** Next is then present and enabled and useless. Play from the season page's episode row instead. That queues the whole season.

**The Plex web player survives a hash change and a full reload and its own close button.** The overlay it leaves behind swallows pointer events so the next repetition cannot click anything. Every repetition needs a fresh page.

**An episode with a resume offset offers Resume and not Play.** Resuming starts mid file. That is not a cold open. Scrobble then unscrobble each episode first to clear the offset.

**A page closed mid playback strands a Plex session.** That session loses its Session id and `terminate` cannot touch it. Only a stopped timeline posted as that player clears it. The harness must also read the session that is playing rather than the first session listed. Otherwise a stale paused session reports the wrong episode and the correctness check passes on the wrong thing.

**`rclone mount --daemon` holds the ssh channel open.** Mounting on a remote host over ssh hangs the caller forever on a mount that actually succeeded. Use `ssh -n` and redirect on the remote side.

**A blanket `find` over the WebDAV mount walks every release.** With virtualised RAR sets in the library that takes minutes. Locate the release directory first and search only inside it. This took one step from several minutes to 0.01 seconds.

**`corpus5b.py` picks the release under test as whatever appeared in the listing during the import.** That is wrong whenever a server is still loading its library when the baseline listing is taken. A late arriving unrelated release looks new and gets probed instead. Use `reprobe_r4.py` which selects by name.

**decypharr's SABnzbd mock is at `/sabnzbd/api` and the upload field is `name`.** A wrong field returns HTTP 200 with `{"status": false, "error": "No files uploaded"}`. A status code check treats that as success and then waits for an import that never happened.

## Limitations

Read these before quoting any number.

- Single host with 2 cores. A larger box would move the ceiling and might reorder the CPU-bound targets.
- Single interleaved run. Cross-run comparison is not valid because provider throughput drifts.
- One news account and one provider. Results on a different backbone may differ.
- The Plex numbers include an audio transcode in every case because the corpus is E-AC-3 and the browser cannot decode it. The video was direct-streamed every time.
- The Plex phase used four episode pairs rather than five. Episode 7 was skipped because one server had not imported it.
- zurg is the author's own project. Every number here is reproducible from this repository against your own account. Do that rather than taking this at face value.

## Layout

```
harness/          the benchmark scripts
harness/plex/     the Plex phase, which runs where the browser is
config/           the server configs used, credentials replaced
corpus/           the NZB corpus and its manifest
results/round4/   this round
results/round3/   the previous round, for comparison
```
