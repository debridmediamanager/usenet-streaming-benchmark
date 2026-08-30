#!/bin/bash
# Round-4 behaviour phases: damaged article, obfuscated release, multi-volume RAR.
cd /home/ben/bench
T=zurg,decypharr,altmount,infinidysk,nzbdav-og
for phase in damage obfuscated rar; do
  echo "=== $phase start $(date -u +%FT%TZ) ==="
  python3 corpus5b.py $phase $T > ${phase}.r4.log 2>&1
  echo "=== $phase done  $(date -u +%FT%TZ) ==="
done
echo "=== BEHAVIOUR PHASES DONE $(date -u +%FT%TZ) ==="
