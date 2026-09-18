# Round 12: current mounts, exact 10-connection parity

Measured 18 September 2026. Five Usenet mounts and the raw transport control,
on a fresh Hetzner `ccx23` in `nbg1`: four dedicated x86 cores, 16 GiB RAM,
160 GiB local disk and Ubuntu 24.04. Every target was reset to empty state and
started alone. Raw output is in [`results/round12/`](../results/round12/).

## Short version

There is no defensible throughput winner. The observed order is NZBDav-og
68.55, AltMount 64.14, InfiniDysk 62.28, zurg 61.29 and decypharr 4.65 MB/s,
but the clean-start repeat's worst swing is 165.8%. The first four are tied at
the resolution of this run; only decypharr's last place is resolved.

zurg wins cold open at 3.1 ms, is effectively tied with AltMount for the
fastest import, and is one of three targets to answer all eight graded entries
correctly. It loses the resource comparison: fourth of five in CPU per
delivered GiB and physical writes, last in peak RSS and retained state. Its
observed sequential rate is fourth, but calling that a real loss would ignore
the measured provider noise. Its most useful playback result is second place
on the p05 floor, well behind NZBDav-og.

The shape explains much of that split. zurg writes 3.42 GiB for each sequential
GiB the harness receives and reaches 1.37 GiB RSS, while opening already
published files almost instantly. That is consistent with archive/cache
materialisation moving work ahead of range serving. The same design buys
latency and costs memory, writes and retained state. This is an inference from
the measured shape, not a claim from the implementations' names.

## Fairness and the parallel-run gate

The mount and Stremio suites were provisioned and prepared in parallel on two
identical, separate VMs. Their publishable measurement windows were then
serialized because a direct gate proved that parallel measurement was unfair:

| 512 MiB raw read, 10 connections each | mount VM MB/s | Stremio VM MB/s |
|---|---:|---:|
| isolated pass 1 | 52.42 | 63.77 |
| isolated pass 2 | 42.48 | 59.54 |
| concurrent | 30.99 | 30.31 |

The concurrent aggregate was 61.30 MB/s, versus 109.10 MB/s from the two
isolated medians. Separate VMs isolated CPU, memory and disk, but not the shared
account's bandwidth cap. Running the final phases simultaneously would have
ranked account throttling, so only setup and the gate overlapped. The exact
machine-readable record is
[`environment.json`](../results/round12/environment.json).

Connection parity is measured, not inferred from configuration. A five-second
socket census covered the whole 3 h 38 min main window. Every software target
peaked at exactly 10 established connections, none exceeded 10, the raw reader
also peaked at 10 for every per-entry process, and no sample caught two targets
using the account at once. The benchmark's one-socket truth verifier is recorded
separately and excluded. See
[`parity.md`](../results/round12/parity.md).

Every target used the same live account, corpus, 10-connection allowance,
repair setting where the product has one, empty initial state, VM class and
measurement code. Target order rotated between the two noise passes and the
main pass.

## Exact revisions

These were upstream `main` heads when the two VMs were provisioned, built with
the toolchain each repository requests rather than one common compiler that
would silently change some targets' fast paths.

| Target | Revision | Language | Interface |
|---|---|---|---|
| zurg | `1b0c2dbf` | Go | WebDAV |
| AltMount | `757e5d93` | Go | WebDAV |
| InfiniDysk | `7b0c7e6e` | C# | WebDAV |
| NZBDav-og | `0c7d8e21` | C# | WebDAV |
| decypharr | `0dd1cbbd` | Go | WebDAV |

The run is pinned because `main` moved while it was executing. A late audit
found three later heads: zurg `63aa505a` changed watchlists, acquisition,
dashboard, torrent and `.strm` handling; AltMount `363939ae` added its
persistent NZB store to metadata backups; InfiniDysk `68f4d2b6` changed health
history APIs and UI. None touches the NNTP reader or range-serving paths
measured here. decypharr and NZBDav-og were still at their measured heads. The
report therefore keeps the exact tested binaries instead of rebuilding one
competitor midway through a round.

The disabled registrations were not silently failed rows. NZBDavEx still has
an unproven mount adapter. StremThru, AIOStreams, StreamNZB and Comet were
tested in the sibling Stremio-addon suite, where their actual discovery and
play interfaces can be compared; forcing those products into a WebDAV table
would measure wrappers rather than the products.

## Every metric, ranked

`raw` is shown elsewhere as a transport control and is not ranked as software.
For metrics with incomplete rows, `n` is the number contributing to the median
out of the five positive entries. The observed order is preserved even where
the noise pass says it is a statistical tie.

| Metric | Direction | Ranking |
|---|---|---|
| Correct graded outcomes | higher | 1 (tie). zurg, InfiniDysk, NZBDav-og 8/8; 4. AltMount 7/8; 5. decypharr 6/8 |
| Sequential throughput | higher | 1. NZBDav-og 68.55; 2. AltMount 64.14; 3. InfiniDysk 62.28; 4. zurg 61.29; 5. decypharr 4.65 MB/s (4/5) |
| p05 one-second floor | higher | 1. NZBDav-og 57.27 (4/5); 2. zurg 16.29; 3. InfiniDysk 5.01; 4. AltMount 2.65; 5. decypharr 0.53 MB/s (4/5) |
| Import | lower | 1. AltMount 5.058; 2. zurg 5.059; 3. NZBDav-og 5.979; 4. decypharr 10.755 s (4/5); 5. InfiniDysk 15.171 s |
| Cold open | lower | 1. zurg 0.0031; 2. AltMount 0.1918; 3. NZBDav-og 0.4358; 4. InfiniDysk 0.9733; 5. decypharr 2.0668 s (4/5) |
| Cold TTFB | lower | 1. zurg 0.0020; 2. AltMount 0.0025; 3. NZBDav-og 0.3103; 4. InfiniDysk 0.5102; 5. decypharr 2.0661 s (4/5) |
| Median seek TTFB | lower | 1. AltMount 0.3262; 2. zurg 0.5284; 3. InfiniDysk 0.6187; 4. NZBDav-og 0.7597; 5. decypharr 2.4204 s (4/5) |
| Median of each entry's worst seek | lower | 1. AltMount 0.3938; 2. NZBDav-og 0.8862; 3. zurg 0.9255; 4. InfiniDysk 1.2836; 5. decypharr 3.1936 s (4/5) |
| 30-second playback read | higher | 1. AltMount 51.12; 2. NZBDav-og 46.18; 3. InfiniDysk 30.61; 4. zurg 28.34; 5. decypharr 5.15 MB/s (4/5) |
| Time to a 30-second buffer | lower | 1. AltMount 0.61; 2. NZBDav-og 0.68; 3. InfiniDysk 1.02; 4. zurg 1.10; 5. decypharr 6.09 s (4/5) |
| Playback real-time ratio | higher | 1. AltMount 16.36×; 2. NZBDav-og 14.78×; 3. InfiniDysk 9.80×; 4. zurg 9.07×; 5. decypharr 1.65× (4/5) |
| CPU seconds/delivered GiB | lower | 1. AltMount 10.76; 2. NZBDav-og 58.26; 3. InfiniDysk 58.56; 4. zurg 83.64; 5. decypharr 249.84 |
| p95 CPU cores | lower | 1. AltMount 0.32; 2. decypharr 0.42; 3. zurg 0.77; 4. InfiniDysk 1.14; 5. NZBDav-og 1.53 |
| Peak RSS | lower | 1. decypharr 89; 2. NZBDav-og 496; 3. AltMount 770; 4. InfiniDysk 1,172; 5. zurg 1,365 MB |
| Physical reads/delivered GiB | lower | 1 (tie). zurg, AltMount, InfiniDysk 0.00; 4. NZBDav-og 0.16; 5. decypharr 0.40 MB |
| Physical writes/delivered GiB | lower | 1. AltMount 0.96; 2. InfiniDysk 15.44; 3. NZBDav-og 19.97; 4. zurg 3,415.73; 5. decypharr 5,421.54 MB |
| Retained state growth | lower | 1. decypharr 1.29; 2. AltMount 2.17; 3. NZBDav-og 5.88; 4. InfiniDysk 10.51; 5. zurg 524.86 MB |

The 1 ms import gap and 0.5 ms cold-TTFB gap between zurg and AltMount are
observed orders, not meaningful product separations. Likewise, the throughput
order among the first four is inside the measured provider swing. Correctness,
resource counters and categorical outcomes are not licensed by the throughput
noise floor and stand on their own measurements.

## Sequential throughput, per entry

MB/s. The median alone hides the archive-shaped entries.

| Target | plain video | damaged partial | obfuscated | stored RAR | season pack | median |
|---|---:|---:|---:|---:|---:|---:|
| `raw` control | 92.61 | 81.59 | 79.61 | 7.48 | 7.80 | 79.61 |
| zurg | 83.30 | 86.13 | 61.29 | 6.78 | 9.49 | 61.29 |
| AltMount | 87.27 | 64.14 | 106.62 | 14.10 | 11.33 | 64.14 |
| InfiniDysk | 62.28 | 75.57 | 72.46 | 14.31 | 10.83 | 62.28 |
| NZBDav-og | 68.55 | 74.23 | 75.51 | 9.05 | 13.74 | 68.55 |
| decypharr | 5.43 | 6.16 | FAIL | 3.86 | 3.15 | 4.65 (4/5) |

`raw` is a single-process Python reader, so applications beating it on an entry
does not mean they exceeded the link. It is a reproducible transport context,
not a hardware ceiling at the fast end.

## Stall floor and playback shape

p05 is the fifth percentile of complete one-second windows after the first
window. It measures delivery stalls rather than request latency. A short read
that does not contain ten eligible windows reports no p05 instead of inventing
one.

| Target | median p05 MB/s | n | worst measured MB/s |
|---|---:|---:|---:|
| NZBDav-og | 57.27 | 4/5 | 5.78 |
| zurg | 16.29 | 5/5 | 0.00 |
| InfiniDysk | 5.01 | 5/5 | 4.19 |
| AltMount | 2.65 | 5/5 | 0.00 |
| decypharr | 0.53 | 4/5 | 0.00 |
| `raw` control | 22.23 | 4/5 | 0.00 |

NZBDav-og has the strongest observed sustained-delivery shape. zurg is second
on the median but still records a zero floor on both small archive entries, so
the rank does not mean it is stall-free. The repeat pass shows p05 itself is
volatile: zurg moved from 12.50 to 23.97 MB/s and NZBDav-og from 35.15 to 59.98
on the same entry. Treat the order as observed, not universal.

## Correctness and failure behaviour

Every one of 78 comparable target/range pairs matched byte consensus. That
protects the speed tables from a fast wrong-byte implementation.

| Target | Correct | Positive failures | Negative mistakes |
|---|---:|---|---|
| zurg | 8/8 | 0 | 0 |
| InfiniDysk | 8/8 | 0 | 0 |
| NZBDav-og | 8/8 | 0 | 0 |
| AltMount | 7/8 | 0 | served the severely damaged release |
| decypharr | 6/8 | obfuscated import timed out | served the incomplete archive set |

The negative tier is part of the rank: a quick 206 for unrecoverable bytes is
not successful playback. Two further negative fixtures were unavailable on the
provider and are explicitly skipped for every target, leaving eight graded
entries.

The single-article damaged entry exposes a policy difference rather than a
total order. zurg, AltMount and InfiniDysk span the hole with zero-filled bytes;
NZBDav-og and decypharr stop at the hole; the raw reader also stops. All agree
on the bytes before and after it. A player may prefer continuity or an explicit
failure, so this categorical result is reported and not converted into points.

Correct refusal can also be slow. zurg took about 15 minutes to decide each of
the dead post and incomplete archive set, as did AltMount, InfiniDysk and
NZBDav-og. decypharr rejected one dead post immediately but was less correct
overall. Correctness is ranked before rejection latency so failure-fast cannot
win by serving the wrong thing.

## CPU, memory and disk

One-second process-tree samples cover startup, imports, truth checks and every
read. CPU and physical block I/O are normalized by the sequential GiB actually
delivered; retained state is allocated growth in explicit per-target state
paths. Container helpers and replacement processes are included.

| Target | CPU s/GiB | p95 cores | peak RSS MB | read MB/GiB | write MB/GiB | state Δ MB |
|---|---:|---:|---:|---:|---:|---:|
| AltMount | 10.76 | 0.32 | 770 | 0.00 | 0.96 | 2.17 |
| decypharr | 249.84 | 0.42 | 89 | 0.40 | 5,421.54 | 1.29 |
| InfiniDysk | 58.56 | 1.14 | 1,172 | 0.00 | 15.44 | 10.51 |
| NZBDav-og | 58.26 | 1.53 | 496 | 0.16 | 19.97 | 5.88 |
| zurg | 83.64 | 0.77 | 1,365 | 0.00 | 3,415.73 | 524.86 |

Zero physical reads means the kernel reported no block-device reads attributed
to those process trees during the phase; it does not mean the programs never
read their own memory or files. Physical writes include transient data, which
is why zurg wrote about 21.1 GB during the phase while retaining only 524.86 MB.

## Noise and what the round can resolve

Two clean-state passes changed only the clock. On `plain-video`:

| Target | pass A MB/s | pass B MB/s | change |
|---|---:|---:|---:|
| decypharr | 6.43 | 6.90 | 7.3% |
| NZBDav-og | 58.65 | 73.60 | 25.5% |
| zurg | 50.42 | 68.81 | 36.5% |
| `raw` | 33.69 | 67.15 | 99.3% |
| AltMount | 29.22 | 77.68 | 165.8% |
| InfiniDysk | failed | 69.51 | correctness transition, not noise |

The whole-run median moved 105.3%. InfiniDysk's failed/pass transition is
kept as a real outcome change and excluded from numeric noise; the harness now
has a checked-in real fixture proving that a failed numeric rate must not
inflate the noise floor. The top software medians differ by only 11.8%, so the
round cannot distinguish them on sequential rate. decypharr is more than 13×
behind zurg and remains a resolved last place even under the worst swing.

## Why zurg wins and loses

- It wins cold access because the serving path has already made the selected
  file immediately addressable: 3.1 ms cold open and 2.0 ms TTFB are the best
  observed values.
- It ties the correctness lead. It serves all five positive entries, refuses
  all three graded negatives and matches every byte-identity range.
- It is second on observed p05 and second on median seek TTFB, so its successful
  reads are responsive, but its two zero-floor archive rows prevent a
  stall-free claim.
- It appears fourth on mean throughput and the 30-second playback probe. The
  provider repeat is far noisier than the gaps among the top four, so the
  sequential placement is not a resolved software loss.
- It loses resource efficiency because the fast serving path is purchased with
  local work: highest RSS and retained state, fourth-place CPU/GiB and
  fourth-place write amplification. AltMount gets the opposite trade: best CPU
  and disk efficiency and the fastest short playback probe, but one incorrect
  negative outcome.
- Its damaged-partial policy is continuity by zero fill. NZBDav-og and
  decypharr surface the gap by truncating. This is a product tradeoff, not a
  speed win.

## Reproducing it

Build every target from a recorded upstream head, then run from an empty state:

```bash
ROUND=12 PARITY_CONNS=10 ./harness/build-r7.sh
CONNS=10 TAG=r12 OUT="$PWD/results/round12" \
  ./harness/chain10.sh \
  --only raw,zurg,altmount,infinidysk,nzbdav-og,decypharr
```

The credentials are supplied as `NNTP_HOST`, `NNTP_PORT`, `NNTP_USER` and
`NNTP_PASS`; tracked files contain placeholders only. On Hetzner, the existing
runner provisions a fresh VM and has a teardown trap:

```bash
CONNS=10 HETZNER_TYPE=ccx23 HETZNER_LOCATION=nbg1 \
  BENCH_SOURCE=you@build-host \
  ./harness/hetzner-round.sh --out "$PWD/results/round12"
```

For a paired run, first repeat the 512 MiB raw range twice on each VM alone and
once concurrently at the final connection budget. Overlap publishable windows
only if both concurrent rates stay inside the isolated noise floor. A separate
VM is not sufficient evidence when both use one provider account.

After the run, gate the exact main-pass timestamps:

```bash
python3 harness/parity_r10.py results/round12 --budget 10 \
  --since MAIN_START_UTC --until MAIN_END_UTC \
  --harness-root /root/usenet-streaming-benchmark \
  --expect-exact --aggregate-cwd /home/ben/bench
python3 harness/test_r10.py
```

The raw target restarts for each entry, so `--aggregate-cwd` intentionally
groups only those benchmark reader processes. Every application remains a
strict per-process check.

## Harness changes proven before publishing

- Resource sampling now follows the full process tree, survives helper
  replacement, records physical I/O and allocated state, and samples the whole
  phase rather than a single read.
- The connection gate parses the remote peer port, samples automatically for
  every phase and can require an exact peak. Tests cover 9, 10 and 11 sockets,
  missing samples and raw-reader aggregation.
- Numeric rates from failed or truncated rows no longer count as provider
  noise. The real InfiniDysk failed/pass pair is the regression fixture and
  failed before the correction.
- Reports derive their round title from the recorded tag and preserve ties
  instead of assigning arbitrary ranks to equal counters.

## Limitations

- One provider account, one location and one evening. The unusually wide
  throughput noise prevents a winner claim among the four fast readers.
- Fast readers stop at a 2 GiB cap; slow readers stop at 30 seconds. Both are a
  single cold range read, but their observation windows differ.
- Phase p95 CPU includes idle polling and correct negative-entry timeouts. It
  describes the whole product phase a user caused; total CPU/GiB is the less
  timeout-sensitive efficiency comparison.
- The two unavailable negative posts are skipped rather than approximated.
- Latest means the recorded heads at provisioning. Three upstream branches
  advanced during the run; their later unrelated deltas are disclosed above.
- This is the mount/WebDAV question. End-to-end Stremio discovery and playback
  are measured separately and should not be averaged into these rows.
