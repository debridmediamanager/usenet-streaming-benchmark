#!/bin/bash
# wait for the throughput run to land all 30 rows, then run the latency phase
cd /home/ben/bench
while pgrep -f "bench5.py six4" >/dev/null; do sleep 15; done
echo "=== six4 finished $(date -u +%FT%TZ) ==="
date -u +%FT%TZ > latency_r4.start
python3 phase2_5r4.py zurg,decypharr,altmount,infinidysk,nzbdav-og > latency_r4.log 2>&1
echo "=== latency finished $(date -u +%FT%TZ) ==="
