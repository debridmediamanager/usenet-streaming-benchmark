#!/bin/bash
# Round-7 builds: every target from its repo main HEAD as of 2026-09-01.
# Go targets build in a container; the two .NET targets build their own image.
#
# decypharr builds on bookworm, not alpine: it needs cgo for its FUSE mount and
# an alpine build links against musl, which zen's glibc answers with "No such
# file or directory". Round 4 hit that trap and round 6 needed a second script
# to undo it; here it is one step.
set -u
BENCH=/home/ben/bench
OUT=$BENCH/src/out
CACHE=$BENCH/src/gomodcache
CACHE_GLIBC=$BENCH/src/gomodcache-glibc
mkdir -p "$OUT" "$CACHE" "$CACHE_GLIBC"
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
MANIFEST=$BENCH/results_r7_versions.json

# mtime reference for the artifact check below. Each build here is non-fatal on
# purpose (one broken target must not cost the other four), but the manifest
# used to be written from the freshly pinned SHAs whether or not anything came
# out of the containers. A failed build leaves the PREVIOUS round's binary at
# the same $OUT/<name>-r7 path, so the bench ran a stale binary under a manifest
# claiming the new commit -- a wrong result that reads as a clean one. Every
# artifact must therefore be newer than this file before the manifest is written.
START_REF=$(mktemp)
trap 'rm -f "$START_REF"' EXIT

pin () {  # dir -> checkout origin/main, echo short sha
  cd "$1" || return 1
  git fetch --quiet origin
  git checkout --quiet --detach origin/main
  git rev-parse --short=8 HEAD
}

ZC=$(pin /home/ben/zurgcode)
AC=$(pin $BENCH/src/altmount-git)
DC=$(pin $BENCH/src/decypharr-git)
IC=$(pin $BENCH/src/infinidysk-git)
NC=$(pin $BENCH/src/nzbdav-git)
echo "PINNED zurg=$ZC altmount=$AC decypharr=$DC infinidysk=$IC nzbdav=$NC"

echo "=== zurg $ZC ==="
docker run --rm -v /home/ben/zurgcode:/src -v "$OUT":/out -v "$CACHE":/go/pkg/mod \
  -w /src golang:1.26-alpine sh -c "
    apk add --no-cache git gcc musl-dev bash >/dev/null 2>&1
    CGO_ENABLED=0 go build -trimpath -buildvcs=false -ldflags \"-s -w \
      -X github.com/debridmediamanager/zurg/internal/version.BuiltAt=$STAMP \
      -X github.com/debridmediamanager/zurg/internal/version.GitCommit=$ZC \
      -X github.com/debridmediamanager/zurg/internal/version.Version=main-$ZC\" \
      -o /out/zurg-r7 ./cmd/zurg && chown 1000:1000 /out/zurg-r7 && echo ZURG_OK
  " 2>&1 | tail -6

echo "=== altmount $AC ==="
docker run --rm -v $BENCH/src/altmount-git:/src -v "$OUT":/out -v "$CACHE":/go/pkg/mod \
  -w /src golang:1.26-alpine sh -c "
    apk add --no-cache gcc g++ musl-dev >/dev/null 2>&1
    CGO_ENABLED=1 go build -trimpath -tags=cli \
      -ldflags=\"-s -w -X 'github.com/javi11/altmount/internal/version.Version=main-$AC' -X 'github.com/javi11/altmount/internal/version.GitCommit=$AC' -X 'github.com/javi11/altmount/internal/version.Timestamp=$STAMP' -extldflags '-static'\" \
      -o /out/altmount-r7 ./cmd/altmount/main.go && chown 1000:1000 /out/altmount-r7 && echo ALT_OK
  " 2>&1 | tail -6

echo "=== decypharr $DC (bookworm/glibc) ==="
docker run --rm -v $BENCH/src/decypharr-git:/src -v "$OUT":/out \
  -v "$CACHE_GLIBC":/go/pkg/mod -w /src golang:1.26-bookworm sh -c "
    apt-get update -qq >/dev/null 2>&1
    apt-get install -y -qq gcc g++ libfuse-dev libfuse3-dev pkg-config >/dev/null 2>&1
    CGO_ENABLED=1 go build -trimpath -buildvcs=false -ldflags '-s -w \
      -X github.com/sirrobot01/decypharr/pkg/version.Version=main-$DC \
      -X github.com/sirrobot01/decypharr/pkg/version.Channel=main' \
      -o /out/decypharr-r7 . && chown 1000:1000 /out/decypharr-r7 && echo DECY_OK
  " 2>&1 | tail -6
file "$OUT/decypharr-r7" 2>/dev/null

echo "=== infinidysk $IC ==="
docker build -q -t infinidysk:r7-$IC $BENCH/src/infinidysk-git 2>&1 | tail -4 && echo INFI_OK

echo "=== nzbdav $NC ==="
docker build -q -t nzbdav:r7-$NC $BENCH/src/nzbdav-git 2>&1 | tail -4 && echo NZBDAV_OK

# ---------------------------------------------------------------- verify
# Nothing above fails the script, so this is the only thing standing between a
# broken build and a manifest that lies about what the round ran.
echo "=== verify artifacts ==="
FAILED=""
for b in zurg altmount decypharr; do
  f=$OUT/$b-r7
  if [ -f "$f" ] && [ "$f" -nt "$START_REF" ]; then
    echo "   ok   $b -> $f"
  else
    echo "   FAIL $b -> $f (missing, or not rebuilt by this run: last round's binary)"
    FAILED="$FAILED $b"
  fi
done
# The two images carry the commit in the tag, so existence IS freshness: a stale
# image from an earlier round sits under a different tag and cannot answer here.
for img in "infinidysk:r7-$IC" "nzbdav:r7-$NC"; do
  if docker image inspect "$img" >/dev/null 2>&1; then
    echo "   ok   $img"
  else
    echo "   FAIL $img (no such image)"
    FAILED="$FAILED $img"
  fi
done
if [ -n "$FAILED" ]; then
  echo "BUILD_R7_FAILED:$FAILED"
  echo "manifest NOT written -- $MANIFEST still describes the previous build"
  exit 1
fi

cat > "$MANIFEST" <<JSON
{
 "round": 7,
 "built_at": "$STAMP",
 "commits": {
  "zurg": "$ZC",
  "altmount": "$AC",
  "decypharr": "$DC",
  "infinidysk": "$IC",
  "nzbdav-og": "$NC"
 },
 "images": {
  "infinidysk": "infinidysk:r7-$IC",
  "nzbdav-og": "nzbdav:r7-$NC"
 },
 "parity": {
  "nntp_connections_per_target": 20,
  "news_host": "news.news-provider.example",
  "repair": "enabled on every target that has the feature (nzbdav-og has none)"
 }
}
JSON
ls -la "$OUT"/*-r7 2>/dev/null
cat "$MANIFEST"
echo "BUILD_R7_DONE"
