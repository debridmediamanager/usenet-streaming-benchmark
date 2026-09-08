# Round 11, the round 10 harness on current builds

Measured 7 and 8 September 2026. Six targets, ten corpus entries, 10 NNTP
connections each, on a freshly provisioned Hetzner CCX23 with four dedicated
cores. Raw output in [`results/round11/`](../results/round11/).

This is the first round run on the round 10 harness, and the first round in
which every target was built from its own upstream `main` on the day. Rounds 3
through 9 measured five mounts on two shared cores with a fixed method. This one
adds a transport ceiling to read the rates against, a windowed p05 that shows
what a stream does mid playback rather than on average, a negative tier of
releases that are supposed to fail, and a byte identity check across every
target.

## The short version

zurg leads both headline columns. It moves 99.18 MB/s where the field median is
74 and the ceiling is 78.16, and it opens a file in 0.1246 s against the next
best 0.2958. The run to run noise floor is 7.3%, so those gaps are real.

The more interesting result is that the mean rate is the least useful column in
the table. Under it, AltMount holds a respectable 51.41 MB/s mean and a **p05 of
0.20 MB/s**, which is a stall a viewer sees. NZBDav-og is fourth on the mean and
first by a distance on the floor, at 43.25. If the question is whether a stream
plays without buffering, the ranking inverts.

Three of six targets answered every graded entry correctly. AltMount and
decypharr each served a release they should have refused.

## Field and versions

Every target built from upstream `main` on 7 September 2026.

| Target | Commit | Language | Serving |
|---|---|---|---|
| `raw` | this harness | Python | the transport ceiling, not a competitor |
| zurg | `c88ae981` | Go | WebDAV |
| AltMount | `b9213522` | Go | WebDAV |
| InfiniDysk | `581833f8` | C# | WebDAV |
| NZBDav-og | `0c7d8e21` | C# | WebDAV |
| decypharr | `0dd1cbbd` | Go | WebDAV |

decypharr is the one target whose commit is unchanged from round 9. zurg moved
230 commits.

`nzbdavex`, `stremthru`, `aiostreams`, `streamnzb` and `comet` are registered in
the harness and were disabled for this round. Three of them have adapters that
have never survived a run, and shaking them down inside a round that is also
changing the hardware and the builds would have produced a field nobody could
read.

## Sequential throughput

Median over the five entries at least all but one of the field served. `n` is
how many of those the target itself served.

| target | n | median MB/s |
|---|---|---|
| **zurg** | 5/5 | **99.18** |
| `raw` (ceiling) | 5/5 | 78.16 |
| NZBDav-og | 5/5 | 74.00 |
| InfiniDysk | 5/5 | 67.97 |
| AltMount | 5/5 | 51.41 |
| decypharr | 4/5 | 3.49 |

Per entry, which is where the shape lives:

| target | plain-video | damaged-partial | obfuscated | rar-stored | season-pack |
|---|---|---|---|---|---|
| `raw` | 85.49 | 87.36 | 78.16 | 23.89 | 14.43 |
| zurg | 99.18 | 115.95 | 111.64 | **15.09** | **11.62** |
| AltMount | 48.17 | 76.83 | 53.35 | **51.41** | 15.53 |
| InfiniDysk | 67.97 | 70.82 | 75.69 | 19.97 | 13.41 |
| NZBDav-og | 76.85 | 76.12 | 74.00 | 9.87 | 12.52 |
| decypharr | 5.52 | 0.91 | FAIL | 4.12 | 2.85 |

Three targets read faster than the ceiling on ordinary content. That is a fact
about the ceiling rather than about them. `raw` is a single threaded Python
reader, so at the fast end it bounds nothing and should be read as a floor.

**The stored RAR entry reverses the table.** AltMount serves it at 51.41 MB/s,
more than twice the ceiling and more than three times zurg, which comes fourth
of five at 15.09. Every other entry has zurg at or near the top. Whatever
AltMount does when walking a stored multi volume set, it is doing it better than
anyone else in the field, and that is the single clearest thing this round has
to say to the other five projects.

**The season pack flattens everybody.** The spread across the whole field is
11.62 to 15.53, decypharr aside, against a ceiling of 14.43. Nothing here is
reader bound. This entry measures the account and the news server.

## Cold open

Time to the first megabyte, median over the same population.

| target | n | median s |
|---|---|---|
| **zurg** | 5/5 | **0.1246** |
| AltMount | 5/5 | 0.2958 |
| NZBDav-og | 5/5 | 0.3519 |
| `raw` | 5/5 | 0.5445 |
| InfiniDysk | 5/5 | 1.0548 |
| decypharr | 4/5 | 2.1274 |

zurg opened two entries in under 3 ms, which is a cache hit rather than a fetch,
and its slowest cold open in the round was 0.2922 s. InfiniDysk is the opposite
shape: over a second on three of five entries, and 2.65 s at worst.

## The stall floor, which is the column that matters for playback

p05 is the fifth percentile of the one second windowed rate, measured from the
first byte rather than from the request, so it is a stall in delivery and not
the TTFB. A mean of 50 MB/s can contain a second at zero, and the player stops
during that second.

| target | median p05 MB/s | worst |
|---|---|---|
| **NZBDav-og** | **43.25** | 4.59 |
| zurg | 15.73 | 2.36 |
| InfiniDysk | 12.58 | 0.26 |
| `raw` | 8.48 | 0.00 |
| decypharr | 0.53 | 0.00 |
| AltMount | 0.20 | 0.20 |

NZBDav-og is the steadiest reader in the field by a factor of nearly three, and
it is fourth on the mean. AltMount is the inverse. Its 48.17 MB/s mean on plain
video sits on top of a 0.20 MB/s floor, so the bytes arrive in bursts with long
gaps between them. On the mean it looks like a mid table reader. On the floor it
is the least playable thing here.

Every target except NZBDav-og recorded a p05 of 0.00 on the season pack.

## Import time

Recorded separately from cold open, because an import is work a mount does once
and a viewer never waits through it twice.

| target | median s | worst s |
|---|---|---|
| `raw` | 0.00 | 0.03 |
| AltMount | 5.05 | 10.05 |
| NZBDav-og | 5.91 | 6.05 |
| zurg | 10.83 | 20.09 |
| decypharr | 13.28 | 105.91 |
| InfiniDysk | 15.13 | 20.18 |

zurg is a middling importer and the slowest of the three fast readers.
decypharr took 105.91 s on the season pack, and the one core entry it failed
it failed by import rather than by serving: it spent its entire 900 s import
budget on the obfuscated release and never got a URL to read. AltMount failed
the same way on the season pack in the first attempt at this round.

## Byte identity

**78 of 78 target range pairs matched consensus. No target disagreed with any
other on any range.**

This is the check that mattered most going in. The round 10 run on this same
hardware class was discarded because zurg served a healthy stored RAR release
with every byte displaced by exactly 8,092,431, at the correct size, with an
HTTP 206 and nothing logged. It was invisible to every check except hashing the
same ranges through a second implementation.

That fault was fixed in zurg `c25edcbe` on 6 September. The cause was not the
parallel volume walk that the original investigation suspected. An unreadable
first volume header sent the volume skipping shortcut down a path that treated
the full sized final volume as movie data, and head synthesis then shortened the
first fragment by the same amount, which preserved the total size while
displacing every later read. This round re-ran the same check on the same class
of host and found nothing.

## Capability, on releases that are supposed to fail

Five negative entries, three of which are derived deterministically from the
published corpus. Two need a real post that has not been collected and are
reported as skipped rather than quietly omitted.

| target | correct | what it got wrong |
|---|---|---|
| zurg | 8/8 | nothing |
| InfiniDysk | 8/8 | nothing |
| NZBDav-og | 8/8 | nothing |
| `raw` | 7/8 | served an incomplete archive set |
| AltMount | 7/8 | served a release stripped of two thirds of its articles |
| decypharr | 6/8 | served an incomplete archive set, failed one core entry |

AltMount returned 112 MB/s of content for `damaged-severe` in the first attempt
at this round and served it again here. The entry keeps 527 of 1577 content
articles and leaves the PAR2 volumes intact, so it is a release that cannot be
recovered rather than one that is merely damaged. Answering it with a 206 and a
full length body means zero filling the holes and calling it media.

`raw` failing one is expected and is not a mark against anything. The ceiling
has no archive logic at all, which is the point of it.

## Noise floor

Two identical passes over one entry, with every target reset between them,
before anything else in the round runs.

- whole run median shift: **3.2%**
- worst per entry swing: **7.3%**

Per target, on `plain-video`: zurg 0.6%, InfiniDysk 2.1%, `raw` 3.2%, NZBDav-og
4.3%, decypharr 6.1%, AltMount 7.3%.

A difference smaller than 7.3% is not resolved by one pass. Every gap quoted
above is larger, except the 74.00 to 67.97 between NZBDav-og and InfiniDysk,
which is 8.9% and therefore only just resolved.

## Limitations

- **One host, one evening, one account.** The host reorders the field. Round 8
  and the discarded round 10 both established that moving from two shared cores
  to four dedicated ones leaves the most CPU efficient target roughly flat and
  nearly triples the least efficient one. Nothing here transfers to a different
  machine.
- **The ceiling bounds nothing at the fast end.** `raw` is single threaded
  Python. Three targets beat it. Read it as a floor for what the link had
  available, not as a limit.
- **Fast targets read a 2 GiB cap, slow ones read a 30 s budget.** The
  sequential read stops at whichever comes first, so a target reading 2 GiB at
  99 MB/s is sampled for about 21 s where decypharr is sampled for 30. Both
  numbers are one honest read of one range with nothing re-read, but the
  sampling windows are not identical, and a longer window amortises startup a
  little more.
- **p05 needs five complete windows.** Entries that finish too quickly to hold
  five report no p05 rather than a quoted one. `raw` and AltMount have a p05 on
  two of the five entries, everyone else on three.
- **Five registered targets did not run.** The field is not the whole field.
- **decypharr is measured on an unchanged commit.** Its numbers moved because
  the harness and the hardware changed, not because the project did.

## What had to be fixed before this round was worth running

Four defects in the harness were found by running it, each now carrying a test.
Two of them would have produced a published round that was wrong rather than a
round that failed.

- **The population bar was unanimity.** Headline medians are taken over the
  entries most of the field served, at a threshold of 90%. On a six target field
  that rounds to six of six, which is the strict intersection the code documents
  itself as avoiding. In the discarded round 10 run every core entry was served
  by five of six with a different target failing each one, so the population came
  out empty and both headline tables printed a column of dashes over `0/0` with
  nothing saying why. The bar is now floored at all but one.
- **The sequential read was re-taken warm.** The harness read 256 MB and, if
  that held too few windows to compute a p05, re-read the same offset longer and
  kept the second result. The first read had already pulled those bytes through
  the target. It fed back on itself, since the quicker a target was the likelier
  the retry fired, and the retry then made it quicker still. zurg measured 51.6
  and 55.8 MB/s on the two passes where it did not fire and 141.2 on the one
  where it did, same host, same entry, same connection budget. The read is now
  planned from the file size before any byte is read, and taken once. **This
  moved the noise floor from 58.7% to 7.3%**, which shows how much of that
  "provider noise" was this code.
- **A target served where nobody was watching.** Configs carry the port the host
  they came from needed. AltMount had been moved to `:8181` on the build host
  and arrived on a clean machine where the registry still watched `:8081`. The
  readiness probe timed out, the stop routine freed a port nothing was listening
  on so the old process survived it, the next prep moved that survivor's
  database out from under it, and it logged `disk I/O error` every five seconds
  while every later start failed to bind. AltMount was reported as "never became
  ready" for a whole pass.
- **The wrong two container images were shipped.** The cloud runner selected the
  first two images matching either .NET project by name, which can be two tags
  of the same project.

AltMount also could not be built at all until its build recipe was corrected. It
now requires Go 1.27, and it pulls in `gopar-turbo`, which ships a prebuilt
archive compiled against glibc, so linking it under musl fails on an undefined
`__memcpy_chk` whether the final link is static or not. It also renamed its
module from `javi11` to `kipsilabs`, and a linker `-X` against a symbol that no
longer exists is silently ignored, so the binary would have carried no version
while the manifest claimed the commit.

The temptation when fixing the Go version was to put every Go target on the
newest toolchain so that none could be said to have had a better compiler. That
is wrong and the round does not do it. Built on 1.27, decypharr prints
`sonic/ast only supports (go1.17~1.26) ... will fallback to encoding/json` at
startup, because bytedance/sonic gates its assembly fast path on the Go version
it was compiled with. A toolchain bump silently drops that target onto the
standard library and the round then reports a slowdown the project never
shipped. Each target builds on the toolchain its own `go.mod` asks for.

## Reproducing it

```bash
CONNS=10 BENCH_SOURCE=you@buildhost ./harness/hetzner-round.sh \
  --out "$PWD/results/round11"
```

The account comes from `NNTP_HOST`, `NNTP_PORT`, `NNTP_USER` and `NNTP_PASS` in
the environment and is never written to disk. The runner provisions the machine,
installs dependencies, copies the built targets from a host that already has
them, rewrites every config for the new machine at the stated connection count,
runs the whole suite, collects the results and destroys the server from a trap
that fires on every exit path, then verifies that neither the server nor its
primary IPs survived.

Raw output keeps the harness filenames it was written with, inside
[`results/round11/`](../results/round11/), the same way round 9 did.
