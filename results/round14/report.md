# Round 14: reviewed filesystem targets on Hetzner ccx23

Connection allowance: at most 10 per application; actual peaks are in connection-gate.json.

### Sequential throughput

Median over 5 shared-population entries. `n` counts the entries this target served in that population. `own` covers every entry the target served and can hide failures.

| target | n | median | own | gap |
|---|---|---|---|---|
| nzbdav-og | 5/5 | 60.58 MB/s | 60.58 MB/s | 0.0 |
| raw | 5/5 | 59.55 MB/s | 59.55 MB/s | 0.0 |
| infinidysk | 5/5 | 57.73 MB/s | 57.73 MB/s | 0.0 |
| altmount | 5/5 | 57.37 MB/s | 57.37 MB/s | 0.0 |
| decypharr | 5/5 | 57.07 MB/s | 57.07 MB/s | 0.0 |
| aiostreams | 5/5 | 54.87 MB/s | 54.87 MB/s | 0.0 |
| zurg | 5/5 | 47.78 MB/s | 47.78 MB/s | 0.0 |
### Cold open

Median over 5 shared-population entries. `n` counts the entries this target served in that population. `own` covers every entry the target served and can hide failures.

| target | n | median | own | gap |
|---|---|---|---|---|
| zurg | 5/5 | 0.0025 s | 0.0025 s | 0.0 |
| aiostreams | 5/5 | 0.0052 s | 0.0052 s | 0.0 |
| altmount | 5/5 | 0.0531 s | 0.0531 s | 0.0 |
| infinidysk | 5/5 | 0.1532 s | 0.1532 s | 0.0 |
| nzbdav-og | 5/5 | 0.2007 s | 0.2007 s | 0.0 |
| raw | 5/5 | 0.5497 s | 0.5497 s | 0.0 |
| decypharr | 5/5 | 0.6454 s | 0.6454 s | 0.0 |
### Resources

Periodic samples cover startup, import and every read. CPU and physical block I/O are normalized by delivered sequential GiB; state disk is allocated growth in each target's explicit state directories. `raw` is the transport ceiling and is shown as context, not ranked as software.

| target | CPU s/GiB | CPU p95 cores | peak RSS MiB | disk read MiB/GiB | disk write MiB/GiB | state delta MiB |
|---|---|---|---|---|---|---|
| aiostreams | 7.1 | 0.36 | 773 | 0.0 | 543.44 | 4671.82 |
| altmount | 6.2 | 0.18 | 1064 | 0.04 | 1.41 | 6.28 |
| decypharr | 4.84 | 0.16 | 214 | 0.05 | 1297.71 | 1.34 |
| infinidysk | 21.7 | 0.27 | 930 | 0.0 | 25.09 | 20.96 |
| nzbdav-og | 27.36 | 0.77 | 442 | 0.0 | 18.59 | 5.87 |
| raw | 16.57 | 0.72 | 488 | 0.01 | 0.01 | 0.0 |
| zurg | 10.75 | 0.27 | 1061 | 10.16 | 21.11 | 101.73 |

- CPU seconds/GiB (lower is better): 1. decypharr < 2. altmount < 3. aiostreams < 4. zurg < 5. infinidysk < 6. nzbdav-og
- CPU p95 cores (lower is better): 1. decypharr < 2. altmount < 3 (tie). infinidysk, zurg < 5. aiostreams < 6. nzbdav-og
- peak RSS (lower is better): 1. decypharr < 2. nzbdav-og < 3. aiostreams < 4. infinidysk < 5. zurg < 6. altmount
- disk reads/GiB (lower is better): 1 (tie). aiostreams, infinidysk, nzbdav-og < 4. altmount < 5. decypharr < 6. zurg
- disk writes/GiB (lower is better): 1. altmount < 2. nzbdav-og < 3. zurg < 4. infinidysk < 5. aiostreams < 6. decypharr
- state growth (lower is better): 1. decypharr < 2. nzbdav-og < 3. altmount < 4. infinidysk < 5. zurg < 6. aiostreams
### Byte-identity cross-check

The same ranges hashed by every target and compared against each other, since a fast target serving the wrong bytes is not fast. Consensus is the hash at least two targets agree on; a row here is one to investigate.

104 of 104 target-range pairs matched consensus

No target disagreed with consensus on any range.

## Clean-start noise floor

```json
{
  "comparable": 7,
  "whole_run_median_shift_pct": 0.2,
  "per_entry_median_pct": 1.2,
  "per_entry_worst_pct": 9.1,
  "per_entry": {
    "plain-video": 9.1
  },
  "resolves_differences_above_pct": 9.1,
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
    "pass": 5,
    "FAIL": 0,
    "refused": 2,
    "WRONGLY SERVED": 1,
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
    "refused": 2,
    "WRONGLY SERVED": 1,
    "skipped": 2,
    "graded": 8,
    "correct": 7,
    "correct_pct": 88
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
