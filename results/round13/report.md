# Round 13: reviewed filesystem targets on zen

Connection allowance: at most 10 per application; actual peaks are in connection-gate.json.

### Sequential throughput

Median over 5 shared-population entries. `n` counts the entries this target served in that population. `own` covers every entry the target served and can hide failures.

| target | n | median | own | gap |
|---|---|---|---|---|
| zurg | 5/5 | 37.99 MB/s | 37.99 MB/s | 0.0 |
| raw | 5/5 | 24.34 MB/s | 24.34 MB/s | 0.0 |
| aiostreams | 5/5 | 19.8 MB/s | 19.8 MB/s | 0.0 |
| decypharr | 4/5 | 18.755 MB/s | 18.755 MB/s | 0.0 |
| altmount | 5/5 | 17.23 MB/s | 17.23 MB/s | 0.0 |
| nzbdav-og | 5/5 | 14.26 MB/s | 14.26 MB/s | 0.0 |
| infinidysk | 5/5 | 5.5 MB/s | 5.5 MB/s | 0.0 |
### Cold open

Median over 5 shared-population entries. `n` counts the entries this target served in that population. `own` covers every entry the target served and can hide failures.

| target | n | median | own | gap |
|---|---|---|---|---|
| zurg | 5/5 | 0.0167 s | 0.0167 s | 0.0 |
| altmount | 5/5 | 0.2087 s | 0.2087 s | 0.0 |
| aiostreams | 5/5 | 0.3568 s | 0.3568 s | 0.0 |
| decypharr | 4/5 | 1.0212 s | 1.0212 s | 0.0 |
| raw | 5/5 | 1.2882 s | 1.2882 s | 0.0 |
| infinidysk | 5/5 | 1.9061 s | 1.9061 s | 0.0 |
| nzbdav-og | 5/5 | 2.0404 s | 2.0404 s | 0.0 |
### Resources

Periodic samples cover startup, import and every read. CPU and physical block I/O are normalized by delivered sequential GiB; state disk is allocated growth in each target's explicit state directories. `raw` is the transport ceiling and is shown as context, not ranked as software.

| target | CPU s/GiB | CPU p95 cores | peak RSS MiB | disk read MiB/GiB | disk write MiB/GiB | state delta MiB |
|---|---|---|---|---|---|---|
| aiostreams | 20.43 | 0.31 | 812 | 770.04 | 624.55 | 2930.86 |
| altmount | 24.45 | 0.21 | 1036 | 239.58 | 4.58 | 6.16 |
| decypharr | 27.02 | 0.12 | 60 | 73.95 | 2245.18 | 1.2 |
| infinidysk | 351.54 | 0.21 | 616 | 4572.25 | 133.91 | 11.06 |
| nzbdav-og | 137.33 | 0.5 | 452 | 708.14 | 73.69 | 5.61 |
| raw | 47.79 | 0.62 | 537 | 3.63 | 0.09 | 0.0 |
| zurg | 34.03 | 0.45 | 1038 | 121.3 | 3053.36 | 519.01 |

- CPU seconds/GiB (lower is better): 1. aiostreams < 2. altmount < 3. decypharr < 4. zurg < 5. nzbdav-og < 6. infinidysk
- CPU p95 cores (lower is better): 1. decypharr < 2 (tie). altmount, infinidysk < 4. aiostreams < 5. zurg < 6. nzbdav-og
- peak RSS (lower is better): 1. decypharr < 2. nzbdav-og < 3. infinidysk < 4. aiostreams < 5. altmount < 6. zurg
- disk reads/GiB (lower is better): 1. decypharr < 2. zurg < 3. altmount < 4. nzbdav-og < 5. aiostreams < 6. infinidysk
- disk writes/GiB (lower is better): 1. altmount < 2. nzbdav-og < 3. infinidysk < 4. aiostreams < 5. decypharr < 6. zurg
- state growth (lower is better): 1. decypharr < 2. nzbdav-og < 3. altmount < 4. infinidysk < 5. zurg < 6. aiostreams
### Byte-identity cross-check

The same ranges hashed by every target and compared against each other, since a fast target serving the wrong bytes is not fast. Consensus is the hash at least two targets agree on; a row here is one to investigate.

95 of 95 target-range pairs matched consensus

No target disagreed with consensus on any range.

## Clean-start noise floor

```json
{
  "comparable": 7,
  "whole_run_median_shift_pct": 40.9,
  "per_entry_median_pct": 40.9,
  "per_entry_worst_pct": 67.8,
  "per_entry": {
    "plain-video": 67.8
  },
  "resolves_differences_above_pct": 67.8,
  "note": "a difference between two targets smaller than the worst per-entry swing here is not resolved by one pass"
}
```

## Capability

```json
{
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
    "refused": 3,
    "WRONGLY SERVED": 0,
    "skipped": 2,
    "graded": 8,
    "correct": 7,
    "correct_pct": 88
  },
  "aiostreams": {
    "pass": 5,
    "FAIL": 0,
    "refused": 1,
    "WRONGLY SERVED": 2,
    "skipped": 2,
    "graded": 8,
    "correct": 6,
    "correct_pct": 75
  },
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
  }
}
```
