# Round 10, the harness

**Nothing here has been run.** This document describes a harness change, not a
round. There are no measurements in it and there is no results directory for it
yet. Every number in this repository still comes from rounds 3 through 9 and
none of those has been touched.

What this adds is the machinery for a round 10, in two halves: measurements the
earlier rounds could not take, and targets they did not include.

## Why

Rounds 3 through 9 answered one question well: which of five mounts should back
a media library, measured under an isolation rule strict enough that the answer
means something. Read against a wider field, three things in the method were
doing less work than they appeared to.

**There was no ceiling.** Every absolute MB/s was published with nothing to read
it against, so no round could say how much of the link was available that
evening. A target moving 36 MB/s on a night the transport could do 38 is a very
different result from the same 36 on a night it could do 90, and nothing in the
repository could separate them.

**Nothing in the corpus was supposed to fail.** With success as the only correct
answer, no run could catch a target answering a request it cannot satisfy: a
zero fill dressed as a 206, a stream that stops mid body with the status line
already sent, or a built in failure clip served as valid media with a 200. All
three score as success against a corpus where success is the only option.

**Medians were taken over whatever each target survived.** Import time scales
with post size, so a target that fails the large entries is credited with the
fast medians of the small ones it served, and failing more can make a target
look quicker.

## What the measurements now cover

| Added | What it catches that the old column could not |
|---|---|
| `raw` transport ceiling | how much headroom the link had, so an absolute rate means something |
| p05 windowed rate | a stall inside a read. A mean of 54 MB/s can contain a second at zero, and the player stops during it |
| seek profile at 1/25/50/75/95% plus a backward seek | whether seek cost climbs with offset, and what a jump backwards costs once read ahead is working forwards |
| full seek split from seek TTFB | a target that answers a Range instantly and then feeds the body slowly. The second column is the one a player waits through |
| playback simulation at a target bitrate | whether a stream sustains 25 Mbps for thirty seconds without draining a buffer. Nothing bitrate relative was measured before |
| CPU shape: cores p95, worst second, steady share | ten CPU seconds spent as a steady half core, or as one core pinned for ten. The totals are equal and the box does not feel equal |
| memory drift and after idle footprint | accumulation across a run, which a peak cannot show, and how much of it comes back when the work stops |
| peak taken over a stated number of reads | a run wide peak rewards failing early. A target that died on the large entries had fewer chances to spike |
| import time split from cold open | where the wait actually goes, and the only honest way to compare an addon against a mount |
| byte identity consensus across targets | a fast target serving the wrong bytes. Round 7 hashed the behaviour releases only, all five agreed, so the check never had a chance to find anything |
| damage alignment verification | a target that lays the file out differently, whose ordinary video at the assumed hole offset reads as a flawless repair |
| streaming read split from a direct Range into the hole | engines that answer a player and a seek differently at the same gap |
| negative corpus tier with expected outcomes | bytes returned for a range that is provably absent upstream |
| population fixed medians with `n` | a target flattered by its own failures |
| measured noise floor | which differences a single pass can actually resolve. "Provider throughput drifts" is true and it is not a number |

### The negative tier is derived, not hunted

Three of the five negative entries are built deterministically from NZBs this
repository already ships, so the tier is reproducible by anyone with the corpus
rather than requiring a hunt for adversarial posts:

```bash
python3 harness/corpus_r10.py derive
```

- `dead-post` rewrites every message id to one that cannot exist. Verified
  against the real corpus: 1010 ids rewritten, zero overlap with the originals.
- `incomplete-archive-set` removes one volume of a multi volume set. Verified:
  exactly one file removed, `pp_Sb.part03.rar`, and the remaining 931 segments
  untouched.
- `damaged-severe` removes two thirds of the content articles and leaves the
  PAR2 volumes intact, so it is an entry about damage past what recovery data
  can fix rather than an entry about missing recovery data. Verified: 527 of
  1577 content articles kept, 85 of 85 PAR2 segments intact.

Two more belong in the tier and cannot be derived, because no transformation of
a healthy post produces them: a genuinely compressed archive, and one encrypted
with no password available. They are registered as `needs_real_post` so a run
reports them as not collected. An absent entry that is silently omitted lets the
tier look complete when it is not.

## What the field now covers

Five targets became ten. The additions and the reason for each:

| Target | Serving | Why it is here |
|---|---|---|
| `raw` | HTTP Range | the ceiling. Not a competitor and never ranked as one |
| `nzbdavex` | WebDAV | the other fork of nzbdav. The original and InfiniDysk were both measured and this one was not, so the family had a hole in it |
| `stremthru` | WebDAV | the only addition directly comparable to the incumbents. Its `newz` store is its own engine and it answers WebDAV at `/v0/webdav/newz/` and a SABnzbd API at `/v0/sabnzbd/api`, so it runs the identical import and serve path |
| `aiostreams` | HTTP Range | the largest project in the field by a wide margin, and the author of the competing benchmark, which is exactly why an independent number for it is worth having |
| `streamnzb` | HTTP Range | measured once in the 18 August six way round and dropped before this repository existed, so it has never appeared in a published round |
| `comet` | HTTP Range | registered and disabled by default. See below |

### Two corrections worth recording

**AIOStreams is not a WebDAV server.** The June pull request titled "built in
WebDAV server for the native usenet library" reads as though it were, and it is
not: there is no `PROPFIND` anywhere in the tree. It is measured on the HTTP
Range path and must not be ranked against the mounts on import time.

**UsenetStreamer is not an engine.** It is a search and indexer front end that
hands streaming to NZBDav. Its own health checks describe an archive as playable
when "the archive format is supported by NZBDav". Benchmarking it would
re-measure nzbdav with a search layer in front and report the result under a
second name, so it is deliberately not in the field.

### Comet is off by default

It has no import API at all. A release can only be offered to it by standing up
a Stremio addon of your own and pointing its discovery source at it. Worse, its
engine materialises archives past the item boundary with no exposed idle signal
to drain against, and under sustained load it deadlocks its own SQLite database
at its shipped defaults. Enable it to reproduce that. Expect a finding rather
than a row.

## Mounts and addons must not be ranked together

An addon walks discovery, import and link minting in a path a mount never
touches. A single cold open number puts every addon behind by however long its
import takes and calls it slowness.

So `import_s` and `open_s` are recorded separately, and the composite
`click_to_byte_s` is the only one of the three that compares across serving
modes. `targets_r10.SERVE_MODE` says which family a row belongs to, and
`targets_r10.comparable()` is what a table should be built from.

## Verified against upstream, and not

Every adapter records its provenance in `targets_r10.TARGETS[...]["verified"]`.

- `upstream` means the endpoints were read out of that project's own
  repository. Eight of the ten are in this state.
- `shakedown` means they are written from documentation and have not yet
  survived a run. **`nzbdavex` and `aiostreams` are in this state.**
  `python3 harness/run_r10.py --list` prints the current set.

The native and discovery import paths, which is to say `streamnzb`, `comet` and
`aiostreams`, return an explicit "not implemented yet" from `import_entry`
rather than a row of zeros. A first round has to close those before those
targets produce numbers.

## Tests

The harness had none before this. `harness/test_r10.py` runs offline with no
provider, no corpus and no network:

```bash
python3 harness/test_r10.py
```

It covers the yEnc decoder against a reference encoder written from the spec
(all 256 byte values, escapes, dot unstuffing, CRC), the `raw` baseline's range
arithmetic (spanning articles, the short final article, suffix ranges, a range
past EOF), the windowed rate and percentile maths, the CPU shape and memory
drift statistics, the negative tier derivations, the expectation matrix, the
damage classification, the registry invariants, and the population fixed
medians and consensus logic.

Two of those tests exist because they caught real bugs while this was being
written: the damage classifier used a fixed byte slack that misread a complete
read as a truncation, and `raw`'s handler had to be checked against reads that
span three articles and end inside a short final one.

## Running it

```bash
# what would run, and what is not ready
python3 harness/run_r10.py --list

# build the negative tier from the published corpus
python3 harness/corpus_r10.py derive

# the ceiling, on its own, against one NZB
python3 harness/rawserve_r10.py corpus/ToyStory5.nzb 8099 --conns 15

# a narrow pass while the new adapters are still being shaken down
python3 harness/run_r10.py --targets raw,zurg,stremthru --entries plain-video

# the whole field
python3 harness/run_r10.py --tag r10
```

Credentials come from the environment so a real run never edits a file:
`NNTP_HOST`, `NNTP_PORT`, `NNTP_USER`, `NNTP_PASS`.

## Before a round 10 is published

1. Shake down `nzbdavex` and `stremthru` on one entry and confirm the import and
   serve paths, then move them to `upstream`.
2. Implement the native import path for `streamnzb`, and for `aiostreams` if it
   is to be in the round.
3. Run the noise floor first, as two identical passes, and publish the number.
   It is what licenses every claim about a gap between two targets.
4. Confirm connection parity from live sockets, as round 9 did. The registry
   normalises the budget by configuration and configuration has been wrong
   before.
5. Keep `raw` out of every ranking. It is a denominator.
