# Round 10

Field: raw, zurg, altmount, infinidysk, nzbdav-og, decypharr

Connections: 10

Disabled for this run: nzbdavex, stremthru, aiostreams, streamnzb, comet

### Sequential throughput

Median over the 5 entries at least 90% of the field served. `n` is how many of those the target itself served; `own` is its median over everything it served, which is the flattering number when the two differ.

| target | n | median | own | gap |
|---|---|---|---|---|
| zurg | 5/5 | 99.18 MB/s | 99.18 MB/s | 0.0 |
| raw | 5/5 | 78.16 MB/s | 78.16 MB/s | 0.0 |
| nzbdav-og | 5/5 | 74.0 MB/s | 74.0 MB/s | 0.0 |
| infinidysk | 5/5 | 67.97 MB/s | 67.97 MB/s | 0.0 |
| altmount | 5/5 | 51.41 MB/s | 51.41 MB/s | 0.0 |
| decypharr | 4/5 | 3.485 MB/s | 3.485 MB/s | 0.0 |

### Cold open

Median over the 5 entries at least 90% of the field served. `n` is how many of those the target itself served; `own` is its median over everything it served, which is the flattering number when the two differ.

| target | n | median | own | gap |
|---|---|---|---|---|
| zurg | 5/5 | 0.1246 s | 0.1246 s | 0.0 |
| altmount | 5/5 | 0.2958 s | 0.2958 s | 0.0 |
| nzbdav-og | 5/5 | 0.3519 s | 0.3519 s | 0.0 |
| raw | 5/5 | 0.5445 s | 0.5445 s | 0.0 |
| infinidysk | 5/5 | 1.0548 s | 1.0548 s | 0.0 |
| decypharr | 4/5 | 2.1274 s | 2.1274 s | 0.0 |

### Byte-identity cross-check

The same ranges hashed by every target and compared against each other, since a fast target serving the wrong bytes is not fast. Consensus is the hash at least two targets agree on; a row here is one to investigate.

78 of 78 target-range pairs matched consensus

No target disagreed with consensus on any range.

### Noise floor

Two identical passes, nothing changed but the clock. A difference between two targets smaller than the worst swing here is not resolved by one pass.

- whole-run median shift: 3.2%
- worst per-entry swing: 7.3%

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
