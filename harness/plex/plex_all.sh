#!/bin/bash
# Round-4 Plex phase. zen switches the backing server and remounts; the
# measurement runs here, because the CDP tunnel to the Windows browser is local.
#
# Every ssh uses -n and redirects on the remote side: rclone --daemon otherwise
# keeps the ssh channel's stdout open and ssh never returns, so the driver
# stalls forever on a mount that actually succeeded.
set -u
SCRATCH="$(cd "$(dirname "$0")" && pwd)"
PAIRS="1-2,3-4,5-6,9-10"     # E07/E08 skipped: altmount never imported E07

for S in zurg decypharr altmount infinidysk nzbdav-og; do
  echo "===== $S  $(date -u +%FT%TZ) ====="
  ssh -n user@benchhost "cd ~/bench && python3 -c '
import sys; sys.path.insert(0, \"/home/ben/bench\")
from bench5 import stop_all, start
stop_all(); print(\"started\", start(\"$S\"))
' > /tmp/startsrv.out 2>&1 < /dev/null; cat /tmp/startsrv.out" || { echo "$S: start failed"; continue; }
  sleep 8
  ssh -n user@benchhost "cd ~/bench && ./plexmnt.sh $S > /tmp/plexmnt.out 2>&1 < /dev/null; tail -3 /tmp/plexmnt.out" \
      || { echo "$S: mount failed"; continue; }
  sleep 5
  python3 "$SCRATCH/plex_ttp3.py" --server "$S" --section 4 --season 19757 \
      --pairs "$PAIRS" --out "$SCRATCH/plex_ttp_$S.json" 2>&1 | tail -6
  ssh -n user@benchhost "cd ~/bench && ./plexmnt.sh umount" >/dev/null 2>&1
done
echo "===== PLEX PHASE DONE $(date -u +%FT%TZ) ====="
