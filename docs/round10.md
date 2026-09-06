# Round 10, the first run of the round 10 harness

Measured 6 September 2026 against `newswest`, with repair switched on wherever
the feature exists, on two hosts at once:

| run | host | cores | connections |
|---|---|---|---|
| zen | 2 shared cores, 7.6 GB | shared | 15 |
| hetzner | Hetzner CCX23, 16 GB | 4 dedicated | 10 |

Both ran the **same binaries and the same container images**, moved across
rather than rebuilt. Round 8 compared zen against a CCX23 by building every
target from current main on the day, so a host comparison and a software change
arrived together and could not be separated. Here they can.

The two runs overlapped in time and therefore shared the news account: 15 + 10
connections, plus 8 held by two production consumers on zen, against a measured
ceiling near 300. That is far from starvation, but the benchmark's isolation
rule exists because concurrent readers can contend, so each run is a possible
confound for the other and neither is a clean solo measurement.

Six targets: the five mounts rounds 3 through 9 measured, plus `raw`, which is
this harness pulling the same articles with no application in the middle. The
five additions the harness registers -- nzbdavex, stremthru, aiostreams,
streamnzb and comet -- are **not in this round**. Three of them are not built on
this host and three have no import adapter written, so they are switched off
explicitly rather than left to fail as rows of zeros.

## What this round is

Round 9 and everything before it measured throughput, cold open and a damage
case over a corpus where success was the only correct answer. This is the first
round with the measurements described in
[docs/round10-harness.md](round10-harness.md): a transport reference, a p05
windowed rate, seek and playback profiles, CPU shape, memory drift, byte
identity across targets, alignment-verified damage, a corpus tier that is
supposed to fail, population-fixed medians, and a measured noise floor.

It is also the first round whose harness had ever been run at all. That turned
out to matter more than anything else about it, and the second half of this
document is about what running it found.

## Limitations, before the numbers

**`p05_MBps` is not usable in either run.** The windowed-rate clock started at
the request while the samples start at the first byte, so the opening window
always held the TTFB and delivered almost nothing -- and because the percentile
index lands on the minimum window for any transfer shorter than about twenty
windows, that startup window *was* the p05 for nearly every row. It is why
targets streaming at 20 to 77 MB/s all reported 0.00 to 0.07. The column was
advertised as catching a second at zero inside a read and it reported how long
the server took to answer, which `ttfb_s` already carries. Fixed after these
runs started; the per-sample series is not persisted, so it cannot be recomputed
from the results here and must be re-measured. Every other column is unaffected.

**On the faster host the sequential read is too short to hold a percentile at
all.** 256 MB at 77 MB/s is three complete one-second windows, below the
five-window bar, so the three fastest targets decline to report p05 rather than
quoting one. That refusal is the harness working correctly; the read length
needs to scale with the link.

**`raw` is a floor on zen and very nearly a ceiling on Hetzner.** It was built
to say how much of the link was available, so an absolute MB/s could be read as
a fraction of what the transport could do that evening. Whether it can do that
job turns out to depend on the box.

On zen it cannot. It is a pure-Python reader on two shared cores, and after
three rounds of optimisation -- a quadratic socket read made linear, an
unbounded read-ahead bounded, a decoder that stopped building 33 000 line
objects per article -- it still sits pinned near one core while serving less
than the fastest target. Every number it produces there is a lower bound on the
transport and an upper bound on nothing.

On four dedicated cores the same code reaches 63.5 MB/s and bounds every target
except altmount. That is a materially better denominator, and it is the clearest
argument for running future rounds on dedicated hardware.

It is excluded from every ranking on both hosts, as it always was. Its other
value does not depend on speed: it fetches and decodes the same articles with
none of the same code, so agreement with it is evidence a target served the
right bytes rather than plausible ones.

**Cold open is warm for a target that prefetches during import.** Round 10
splits import out as a column of its own and measures cold open immediately
after it. A target that pulls the first articles while importing has them in
hand when the cold read arrives. zurg's 2.7 ms is that, not a disk cache and
not a trick; it is the honest consequence of asking the two questions
separately, and it is why `click_to_byte_s` is the only column that compares
across targets that import differently.

**The shared-median column is empty at this field size.** An entry enters the
population only if at least 90% of the field served it, which with six targets
means all six. Any single failure on an entry removes that entry from every
target's median. The `own` column and its `n` are what carry the comparison
here, and the gap between them is reported rather than hidden.

**The negative tier costs about fifteen minutes per SAB-family target.** A post
whose message ids cannot exist never appears in a listing, so the import poll
waits out its full 900 s budget before recording the refusal. That is correct
and it is the dominant time cost of the round.

## Method notes specific to this round

**Every target starts each pass with an empty library.** Rounds 3 through 9
staged the corpus into each target before it started, so every one of them
loaded its library at boot and the import that followed found the release
already there. With import reported separately that is no longer acceptable, so
state is reset before each of the three passes and every import in this round is
a real one.

That reset is not optional, and the first attempt at this round proved it: with
libraries and disk caches left warm between the two noise passes, infinidysk
served 18.33 MB/s on the first and 112.51 MB/s on the second -- three times the
transport reference, off its own segment cache -- while its import fell from
20.68 s to 0.58 s because there was nothing left to import. A noise floor built
from that pair reported a worst swing of 514% and licensed no comparison at all.

**Connection parity is read from sockets, not from configuration.** A census
samples every `:563` socket every five seconds for the whole round and resolves
each pid's process and working directory while the process still exists, since
a pid is gone by the time a round ends. See
[`harness/parity_r10.py`](../harness/parity_r10.py).

**Two other consumers share this news account** and are visible in that census
throughout: a production zurg and a second unrelated one, four sockets each.
They are not part of the field and are excluded by working directory. They are
also the reason the harness's drain check had to learn to ask who owns a socket
rather than naming the one process it expected to find.
