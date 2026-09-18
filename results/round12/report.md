# Round 12

Field: raw, zurg, altmount, infinidysk, nzbdav-og, decypharr

Connections: 10

Disabled for this run: nzbdavex, stremthru, aiostreams, streamnzb, comet

### Sequential throughput

Median over the 5 entries at least 90% of the field served. `n` is how many of those the target itself served; `own` is its median over everything it served, which is the flattering number when the two differ.

| target | n | median | own | gap |
|---|---|---|---|---|
| raw | 5/5 | 79.61 MB/s | 79.61 MB/s | 0.0 |
| nzbdav-og | 5/5 | 68.55 MB/s | 68.55 MB/s | 0.0 |
| altmount | 5/5 | 64.14 MB/s | 64.14 MB/s | 0.0 |
| infinidysk | 5/5 | 62.28 MB/s | 62.28 MB/s | 0.0 |
| zurg | 5/5 | 61.29 MB/s | 61.29 MB/s | 0.0 |
| decypharr | 4/5 | 4.645 MB/s | 4.645 MB/s | 0.0 |

### Cold open

Median over the 5 entries at least 90% of the field served. `n` is how many of those the target itself served; `own` is its median over everything it served, which is the flattering number when the two differ.

| target | n | median | own | gap |
|---|---|---|---|---|
| zurg | 5/5 | 0.0031 s | 0.0031 s | 0.0 |
| altmount | 5/5 | 0.1918 s | 0.1918 s | 0.0 |
| nzbdav-og | 5/5 | 0.4358 s | 0.4358 s | 0.0 |
| raw | 5/5 | 0.6537 s | 0.6537 s | 0.0 |
| infinidysk | 5/5 | 0.9733 s | 0.9733 s | 0.0 |
| decypharr | 4/5 | 2.0668 s | 2.0668 s | 0.0 |

### Resources

One-second samples cover startup, import and every read. CPU and physical block I/O are normalized by delivered sequential GiB; state disk is allocated growth in each target's explicit state directories. `raw` is the transport ceiling and is shown as context, not ranked as software.

| target | CPU s/GiB | CPU p95 cores | peak RSS MB | disk read MB/GiB | disk write MB/GiB | state delta MB |
|---|---|---|---|---|---|---|
| altmount | 10.76 | 0.32 | 770 | 0.0 | 0.96 | 2.17 |
| decypharr | 249.84 | 0.42 | 89 | 0.4 | 5421.54 | 1.29 |
| infinidysk | 58.56 | 1.14 | 1172 | 0.0 | 15.44 | 10.51 |
| nzbdav-og | 58.26 | 1.53 | 496 | 0.16 | 19.97 | 5.88 |
| raw | 24.7 | 1.23 | 491 | 0.02 | 0.01 | 0.0 |
| zurg | 83.64 | 0.77 | 1365 | 0.0 | 3415.73 | 524.86 |

- CPU seconds/GiB (lower is better): 1. altmount < 2. nzbdav-og < 3. infinidysk < 4. zurg < 5. decypharr
- CPU p95 cores (lower is better): 1. altmount < 2. decypharr < 3. zurg < 4. infinidysk < 5. nzbdav-og
- peak RSS (lower is better): 1. decypharr < 2. nzbdav-og < 3. altmount < 4. infinidysk < 5. zurg
- disk reads/GiB (lower is better): 1 (tie). altmount, infinidysk, zurg < 4. nzbdav-og < 5. decypharr
- disk writes/GiB (lower is better): 1. altmount < 2. infinidysk < 3. nzbdav-og < 4. zurg < 5. decypharr
- state growth (lower is better): 1. decypharr < 2. altmount < 3. nzbdav-og < 4. infinidysk < 5. zurg

### Byte-identity cross-check

The same ranges hashed by every target and compared against each other, since a fast target serving the wrong bytes is not fast. Consensus is the hash at least two targets agree on; a row here is one to investigate.

78 of 78 target-range pairs matched consensus

No target disagreed with consensus on any range.

### Noise floor

Two identical passes, nothing changed but the clock. A difference between two targets smaller than the worst swing here is not resolved by one pass.

- whole-run median shift: 105.3%
- worst per-entry swing: 165.8%

### Capability

```
{
 "raw": {
  "pass": 5,
  "FAIL": 0,
  "refused": 2,
  "WRONGLY SERVED": 1,
  "skipped": 2,
  "graded": 8,
  "correct": 7,
  "correct_pct": 88
 },
 "zurg": {
  "pass": 5,
  "FAIL": 0,
  "refused": 3,
  "WRONGLY SERVED": 0,
  "skipped": 2,
  "graded": 8,
  "correct": 8,
  "correct_pct": 100
 },
 "altmount": {
  "pass": 5,
  "FAIL": 0,
  "refused": 2,
  "WRONGLY SERVED": 1,
  "skipped": 2,
  "graded": 8,
  "correct": 7,
  "correct_pct": 88
 },
 "infinidysk": {
  "pass": 5,
  "FAIL": 0,
  "refused": 3,
  "WRONGLY SERVED": 0,
  "skipped": 2,
  "graded": 8,
  "correct": 8,
  "correct_pct": 100
 },
 "nzbdav-og": {
  "pass": 5,
  "FAIL": 0,
  "refused": 3,
  "WRONGLY SERVED": 0,
  "skipped": 2,
  "graded": 8,
  "correct": 8,
  "correct_pct": 100
 },
 "decypharr": {
  "pass": 4,
  "FAIL": 1,
  "refused": 2,
  "WRONGLY SERVED": 1,
  "skipped": 2,
  "graded": 8,
  "correct": 6,
  "correct_pct": 75
 }
}
```
