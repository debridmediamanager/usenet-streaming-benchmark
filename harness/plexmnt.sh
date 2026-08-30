#!/bin/bash
# Mount one bench server's WebDAV at /mnt/benchplex/raw, then rebuild the
# symlink farm at /mnt/benchplex/tv so Plex always sees the same paths.
#
# Identical rclone flags for every backend, and vfs caching off on purpose:
# a disk cache would hide exactly the cold-open differences being measured.
set -u
RCLONE=/home/ben/bench/bin/rclone
RAW=/mnt/benchplex/raw
TV=/mnt/benchplex/tv
SHOW="$TV/Bosch (2014)/Season 01"
LOG=/home/ben/bench/plexmnt.log

case "${1:-}" in
  zurg)       URL="http://localhost:9998/dav/all/";                  U=""; P="" ;;
  decypharr)  URL="http://localhost:8282/webdav/__all__/";           U=""; P="" ;;
  altmount)   URL="http://localhost:8081/webdav/complete/";          U="usenet"; P="usenet" ;;
  infinidysk) URL="http://127.0.0.1:8092/content/uncategorized/";    U="usenet"; P="usenet" ;;
  nzbdav-og)  URL="http://127.0.0.1:8093/content/uncategorized/";    U="usenet"; P="usenet" ;;
  umount)     fusermount3 -uz "$RAW" 2>/dev/null; sleep 1; echo "unmounted"; exit 0 ;;
  *) echo "usage: $0 <zurg|decypharr|altmount|infinidysk|nzbdav-og|umount>"; exit 2 ;;
esac

fusermount3 -uz "$RAW" 2>/dev/null; sleep 1
AUTH=""
[ -n "$U" ] && AUTH="--webdav-user=$U --webdav-pass=$($RCLONE obscure $P)"

# shellcheck disable=SC2086
$RCLONE mount :webdav: "$RAW" \
  --webdav-url="$URL" --webdav-vendor=other $AUTH \
  --allow-other --read-only \
  --vfs-cache-mode=off --buffer-size=32M \
  --dir-cache-time=30s --attr-timeout=1s \
  --daemon --log-file="$LOG" --log-level=INFO </dev/null >/dev/null 2>&1

for _ in $(seq 40); do
  mountpoint -q "$RAW" && break
  sleep 1
done
mountpoint -q "$RAW" || { echo "MOUNT FAILED for $1"; exit 1; }

# find the ten episodes wherever this backend chose to put them
# Locate the release directory first, then look only inside it. A blanket
# find over $RAW walks every release in the library, and the virtualised RAR
# sets in there make that take minutes over WebDAV.
REL=$(find "$RAW" -maxdepth 1 -iname '*Bosch*' -print -quit 2>/dev/null)
mapfile -t EPS < <(find "$REL" -maxdepth 3 -iname '*S01E*.mkv' 2>/dev/null | sort)
echo "mounted $1 -> $RAW  (${#EPS[@]} episode files)"
[ "${#EPS[@]}" -eq 0 ] && { echo "NO EPISODES VISIBLE"; exit 1; }

rm -rf "$TV"/*
mkdir -p "$SHOW"
for f in "${EPS[@]}"; do
  n=$(basename "$f" | grep -oiP 'S01E\K\d\d' | head -1)
  [ -z "$n" ] && continue
  ln -sfn "$f" "$SHOW/Bosch - S01E$n.mkv"
done
ls -la "$SHOW" | head -13
