# Usenet streaming benchmark

Servers that stream Usenet content on demand, measured against a real news
account rather than described. One host, one account, one server running at a
time, every target on the same connection count and with repair switched on
wherever the feature exists.

This file is the index. Every round keeps its own report and its own raw output,
and nothing is edited after the fact: where a later round contradicts an earlier
one, both stay up and the later one says so.

## Latest

**[Round 9, fifteen connections](docs/round9.md)**, measured 3 September 2026.
Five targets at 15 NNTP connections instead of round 7's 20, on the same host,
corpus and builds, to find which of them are actually connection bound. Raw
output in [`results/round9/`](results/round9/).

The short version: AltMount lost 27% to a 25% cut, which is the whole
explanation of its round 7 second place, and zurg lost 7%. The tighter the
account, the more reader efficiency matters.

## Every round

Newest first.

| Round | Date | What it measured | Report | Raw output |
|---|---|---|---|---|
| **10** | not run | A harness change, not a round. Adds a transport ceiling, a p05 windowed rate, seek and playback profiles, CPU shape, memory drift, cross-target byte identity, alignment-verified damage, a corpus tier that is supposed to fail, and five more targets | [docs/round10-harness.md](docs/round10-harness.md) | none yet |
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

**zurg is the author's own project.** Every number here is reproducible from
this repository against your own account. Do that rather than taking it at face
value.

## Running a benchmark

### Round 10, the current harness

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

Targets can also be switched off persistently in
[`config/targets-r10.json`](config/targets-r10.json); a command line flag beats
whatever is in there. `./harness/run_r10.py --list` prints what would run, what
is switched off, and which adapters have not survived a run yet.

`python3 harness/test_r10.py` runs the harness's own tests offline, with no
provider, no corpus and no network.

**Nothing in this repository has been measured with it yet.** Two of its
adapters are unproven. See [docs/round10-harness.md](docs/round10-harness.md).

### Rounds 7 and 9

Those used the earlier per-round scripts, which are preserved unchanged so the
published numbers stay reproducible. The commands are in
[docs/round9.md](docs/round9.md).

### Prerequisites

- a Usenet account with at least 15 connections, 20 to reproduce round 7
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

The provider hostname is `news.news-provider.example` everywhere. Replace it
with your own. The round 10 scripts read `NNTP_HOST`, `NNTP_PORT`, `NNTP_USER`
and `NNTP_PASS` from the environment when they are set, so a run of those needs
no file edited at all.

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
docs/round9.md           round 9, the latest published round
docs/round7.md           round 7, with the round 8 summary
docs/round4.md           round 4
docs/round10-harness.md  what round 10 adds and what is not ready
results/round9/          round 9 raw output
results/round8-hetzner/  round 8 raw output
results/round7/          round 7 raw output
results/round4/          round 4 raw output
results/round3/          round 3 raw output
```
