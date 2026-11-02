# Usenet streaming benchmark

Servers that stream Usenet content on demand, measured against a real news
account rather than described. One host, one account, one server running at a
time, every target on the same connection count and with repair switched on
wherever the feature exists.

This file is the index. Every round keeps its own report and its own raw output,
and nothing is edited after the fact: where a later round contradicts an earlier
one, both stay up and the later one says so.

## Latest

**[Round 14, the round 13 field on dedicated cores and a new account](docs/round14.md)**,
measured 1–2 November 2026. Six streaming applications plus raw on a fresh
four-core Hetzner ccx23, sources pinned to upstream main that day, round 13's
reviewed configurations plus the settings upstream has added since. Every
target reached the ten-connection allowance with no sampled overlap or
oversubscription, and the corpus was checked article by article on the new
provider before any target ran. Raw output: [`results/round14/`](results/round14/).

zurg and AIOStreams trail on sustained reads (47.78 and 48.66 MB/s against
57.07–60.58; zurg's stall floor is 6.3 MB/s against 40–44 for four of the
others), and zurg is first on cold open (2.5 ms). AIOStreams' figures come from
a rerun without the 8 GB disk cache that rounds 13 and 14 had given it alone,
which let it serve the corpus's repeated articles from disk. It also served an incomplete archive set as zeros, an entry round 13's
zurg refused. InfiniDysk and NZBDav-og met eight of eight registered
expectations. A new host and a new provider mean no cross-round rate
comparison; read the round's limits before quoting it.

## Every round

Newest first.

| Round | Date | What it measured | Report | Raw output |
|---|---|---|---|---|
| **14** | 1–2 Nov 2026 | The round 13 field and harness on a dedicated four-core Hetzner ccx23 and a benchmark-only account, with a per-article corpus census first. Rates, stall floor, latency, damage/negative outcomes, sampled byte identity, CPU, RSS, I/O and state | [docs/round14.md](docs/round14.md) | [results/round14/](results/round14/) |
| **13** | 2 Oct 2026 | Latest-at-provisioning sources, including AIOStreams native filesystem, with reviewed configurations and a ten-connection allowance on shared two-core zen. Rates, latency, damage/negative outcomes, sampled byte identity, CPU, RSS, I/O and state | [docs/round13.md](docs/round13.md) | [results/round13/](results/round13/) |
| **12** | 18 Sep 2026 | Five current mounts plus raw at exact 10-connection parity on dedicated Hetzner cores. Throughput, p05 floor, import, seek/playback probes, byte identity, negative outcomes, CPU, RSS, physical I/O and state growth | [docs/round12.md](docs/round12.md) | [results/round12/](results/round12/) |
| **11** | 7-8 Sep 2026 | Six targets at 10 connections on four dedicated cores, every one built from upstream main on the day. Throughput, cold open, stall floor, import, byte identity and a negative tier | [docs/round11.md](docs/round11.md) | [results/round11/](results/round11/) |
| **10** | run, not published | The harness this round 11 uses. Run on 6 September and discarded, because a target was found serving a healthy release with every byte displaced and a field measured against a reader that returns the wrong bytes measures nothing. Fixed in zurg `c25edcbe`, and round 11 re-ran the check that caught it | [docs/round10-harness.md](docs/round10-harness.md) | none |
| **9** | 3 Sep 2026 | Five targets at 15 connections. Which of them scale with the connection count | [docs/round9.md](docs/round9.md) | [results/round9/](results/round9/) |
| **8** | 2 Sep 2026 | The round 7 configuration again on four dedicated Hetzner cores, to separate the software from the two shared cores it ran on | [inside docs/round7.md](docs/round7.md) | [results/round8-hetzner/](results/round8-hetzner/) |
| **7** | 1 Sep 2026 | Five targets at 20 connections, repair on everywhere the feature exists. The baseline round 9 compares against | [docs/round7.md](docs/round7.md) | [results/round7/](results/round7/) |
| **4** | 30 Aug 2026 | Five targets, including the Plex press-play phase driven through the real web app | [docs/round4.md](docs/round4.md) | [results/round4/](results/round4/) |
| **3** | Aug 2026 | The first five-way pass. Superseded by round 4 and kept for the record | no report | [results/round3/](results/round3/) |

Rounds 1 and 2 were a two-way A/B that predates this repository and are not
published here.

## What the numbers can and cannot say

Read a round's own Limitations section before quoting anything from it. Three
things are true of all of them:

- **One target runs at a time.** Every target keeps a pool of NNTP sockets warm,
  so two running together oversubscribe the account and skew both. The harness
  stops a target and waits for its sockets to drain before starting the next,
  and raises rather than continuing if one will not let go.
- **Order rotates.** Provider throughput drifts over an evening, so whoever goes
  first must not always be the same target.
- **Cross-round comparison is usually invalid.** Different days, sometimes
  different provider servers. Where two rounds are compared, the round that does
  it says why that is allowed.

Separate VMs do not isolate a shared provider account. Before overlapping this
suite with another Usenet benchmark, read the same 512 MiB raw range twice on
each VM alone and once on both VMs at the same time, with the final connection
budget active. Overlap measurement windows only if each concurrent median stays
within the measured noise floor of its isolated median. A connection count can
be exactly right while an account-level bandwidth cap still halves both runs.

**zurg is the author's own project.** Every number here is reproducible from
this repository against your own account. Do that rather than taking it at face
value.

## Running a benchmark

### Round 14

[`hetzner-r14.sh`](harness/hetzner-r14.sh) runs the round 13 harness in phases
on a fresh Hetzner box that borrows a reserved Primary IPv4, so the account is
only ever seen from one IP; the box gets no IPv6. A corpus census gates the
round on the provider holding every article as built. See
[the round's reproduction steps](docs/round14.md#reproducing-the-round).

Each remote step starts a systemd unit on the box and returns; wait for
`harness/hetzner-r14.sh status` to show it finished before the next one.

```bash
harness/hetzner-r14.sh up         # NNTP_USER and NNTP_PASS in the environment
harness/hetzner-r14.sh census
harness/hetzner-r14.sh build
harness/hetzner-r14.sh verify
harness/hetzner-r14.sh smoke
harness/hetzner-r14.sh run
harness/hetzner-r14.sh collect
harness/hetzner-r14.sh down       # deletes the server, never the IP
```

### Round 13

[`zen-r13.sh`](harness/zen-r13.sh) builds the pinned sources, bootstraps private
empty state and runs the reviewed seven-target field. It is deliberately guarded
to this round's isolated zen paths and ports; see
[the configuration review and reproduction instructions](docs/round13.md).

```bash
bash harness/zen-r13.sh verify
bash harness/zen-r13.sh smoke --out results/new-round13-smoke
bash harness/zen-r13.sh run --out results/new-round13
```

Use a fresh output directory. The live gate enforces a ceiling, not an artificial
minimum: naturally unused sockets are not padded. Source pool limits complement
the census; sampled evidence cannot prove unseen sub-interval transients.

### Round 10, the shared harness

One command runs the whole suite. Every target is measured unless you switch one
off.

```bash
./harness/chain10.sh                     # everything
./harness/chain10.sh --disable comet     # everything except comet
./harness/chain10.sh --only raw,zurg     # just those two
CONNS=20 ./harness/chain10.sh            # a different connection budget
```

It extracts the corpus if it is not already, derives the negative tier, measures
a noise floor as two identical passes, runs every phase over every target, and
writes a report. Results land in `results/round10/`.

Before publishing, gate the main-pass socket window rather than trusting the
configuration files. The raw ceiling restarts once per entry, so its processes
are deliberately aggregated; every application process remains individually
strict:

```bash
python3 harness/parity_r10.py results/round10 --budget 10 \
  --since MAIN_PASS_START_UTC --until MAIN_PASS_END_UTC \
  --harness-root /root/usenet-streaming-benchmark \
  --expect-exact --aggregate-cwd /home/ben/bench
```

`--harness-root` is the path recorded by the remote sampler, even after results
are copied home; it separates the one-socket truth verifier from competitors.

Targets can also be switched off persistently in
[`config/targets-r10.json`](config/targets-r10.json); a command line flag beats
whatever is in there. `./harness/run_r10.py --list` prints what would run, what
is switched off, and which adapters have not survived a run yet.

`python3 harness/test_r10.py` runs the harness's own tests offline, with no
provider, no corpus and no network.

Rounds 11 and 12 were measured with this harness. Some registered adapters are
still unproven and are never included merely because they appear in the
registry. See [docs/round10-harness.md](docs/round10-harness.md).

### Rounds 7 and 9

Those used the earlier per-round scripts, which are preserved unchanged so the
published numbers stay reproducible. The commands are in
[docs/round9.md](docs/round9.md).

### Prerequisites

- a Usenet account with at least 10 connections, 20 to reproduce round 7
- Python 3.10 or newer, `curl`, `ffprobe`, `7z`
- Docker for the container targets
- `rclone` and, for the Plex phase only, `playwright` and a Chrome reachable
  over the DevTools Protocol

### Credentials

Every credential in this repository is a placeholder and nothing here is live.

| file | placeholder |
|---|---|
| `config/zurgrun/config.yml` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `config/decyrun/config.json` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `config/altmount/config.yaml` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `config/infinidysk.env.json` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/prep-r7.sh` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/stat_probe.py` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/stat_one.py` | `YOUR_USENET_USERNAME`, `YOUR_USENET_PASSWORD` |
| `harness/bench5.py` | `YOUR_STREAMNZB_STREAM_TOKEN`, needed only if you re-enable that target |
| `harness/plex/plex_ttp3.py` | `YOUR_PLEX_HOST`, `YOUR_PLEX_TOKEN`, `YOUR_PLEX_MACHINE_IDENTIFIER` |

Older configurations use `news.news-provider.example`; replace it with your own.
The round 10 scripts read `NNTP_HOST`, `NNTP_PORT`, `NNTP_USER` and `NNTP_PASS`
from the environment. Rounds 13 and 14 accept only their round's provider
(`round_profile.py`: round 13 `newswest.frugalusenet.com:563`, round 14
`news.bulknews.eu:563`); rendered credentials are never checked in.

Paths in the older scripts are absolute and assume the layout the runs used.
`BENCH` in `bench5.py` and the paths in `plexmnt.sh` and `chain7.sh` need to
match wherever you put this.

## Corpus

`corpus/corpus.7z` holds the NZBs the runs used. It is a 7-Zip archive with
encrypted headers. The password is `dmmbench`.

The password is not access control. The password is published right here. The
archive exists so release names and message ids stay out of search indexes and
automated scrapers. Anyone who wants the corpus can have it.

`rar` was not available on the build host so 7-Zip with `-mhe=on` was used
instead. Extract with `7z x -pdmmbench corpus.7z`.

| NZB | files | articles | approx bytes | sha256 prefix |
|---|---|---|---|---|
| ToyStory5.nzb | 7 | 1669 | 7164735989 | `9add0ee889f54187` |
| ToyStory5Damaged.nzb | 7 | 1669 | 7164735989 | `90b9bdccb56a8f91` |
| Obfuscated.nzb | 7 | 1669 | 7164735989 | `6794d1464e7cb28c` |
| FatherBrown.nzb | 17 | 1027 | 394141285 | `55ed581204b3d83b` |
| Bosch.S01.nzb | 20 | 32870 | 24290014587 | `c9b60371473825b0` |

`corpus/manifest.json` carries the same table in machine readable form.
`stat_probe.py` will tell you whether a given NZB is still retrievable from your
provider before you waste a run on it.

Round 10 adds a negative tier of entries that are supposed to be refused,
derived deterministically from the NZBs above with
`python3 harness/corpus_r10.py derive`, so it needs no posts you do not already
have.

Provider spool quality is not uniform and it decides what the damage phase can
even claim. On the account round 9 used, a sample of the twelve most damaged
releases in a production library found 61.5 percent of content articles dead
against 6.0 percent on a different backbone. Every NZB in this corpus was
checked as fully retrievable before the run. Four other candidates were rejected
for this reason and are not in the corpus.

## Harness gotchas

**`corpus5b.py` picks the release under test as whatever appeared in the listing
during the import.** That is wrong whenever a server is still loading its
library when the baseline listing is taken. A late arriving unrelated release
looks new and gets probed instead. Use `reprobe_r7.py` which selects by name.

**The first video in a listing is not the release.** A server that preserves an
archive's internal structure lists `Sample/` before the feature. Selecting the
first video picks a 9.1 MB sample clip and a large ranged read of it is a
correct 416. Select the largest non-sample video.

**A single read cannot tell repair from permanent zero-fill.** Both answer
silence at t0. Only a re-read minutes later separates them.

**Sampling cannot disprove "one article missing".** One server removed a whole
release claiming 1 missing of 848. `stat_all.py` checked every article and found
1010 of 1010 present. Use it and not the 3 per file sampler whenever a server
blames the content.

**A fixed sleep after an import is a guess about connection count.** At 20
connections some targets need far longer than 55 seconds to publish a release.
Poll for the release or for the queue to drain.

**decypharr's SABnzbd mock is at `/sabnzbd/api` and the upload field is
`name`.** A wrong field returns HTTP 200 with `{"status": false, "error": "No
files uploaded"}`. A status code check treats that as success and then waits for
an import that never happened.

**`rclone mount --daemon` over ssh never returns.** It holds the ssh channel's
stdout open. Use `ssh -n` and redirect on the remote side.

## Layout

```
harness/                 the benchmark scripts, one set per round
harness/chain10.sh       round 10, the whole suite in one command
harness/*_r10.py         the round 10 harness, which has not been run yet
harness/test_r10.py      its offline tests, no provider or corpus needed
harness/plex/            the Plex phase, which runs where the browser is
config/                  the server configs used, credentials replaced
config/targets-r10.json  which targets a round 10 measures
corpus/                  the NZB corpus and its manifest
docs/round12.md          round 12, the latest published round
docs/round7.md           round 7, with the round 8 summary
docs/round4.md           round 4
docs/round10-harness.md  what round 10 adds and what is not ready
results/round12/         round 12 raw output
results/round9/          round 9 raw output
results/round8-hetzner/  round 8 raw output
results/round7/          round 7 raw output
results/round4/          round 4 raw output
results/round3/          round 3 raw output
```

---

This benchmark is published by zurg's developer. zurg is one of the servers it measures, so run it against your own account before you trust it.

**More from DMM:** [Debrid Media Manager](https://debridmediamanager.com/) · [zurg](https://zurg.debridmediamanager.com/) · [rex](https://rex.debridmediamanager.com/) · [Docs](https://notes.debridmediamanager.com/) · [Sponsor](https://gatekeeper.debridmediamanager.com/) · [Discord](https://discord.com/invite/7u4YjMThXP) · [Reddit](https://www.reddit.com/r/debridmediamanager/)
