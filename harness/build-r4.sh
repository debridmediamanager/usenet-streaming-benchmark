#!/bin/bash
# Round-4 builds: every target from its repo main HEAD.
set -u
OUT=/home/ben/bench/src/out
CACHE=/home/ben/bench/src/gomodcache
mkdir -p "$OUT" "$CACHE"

ZCOMMIT=$(cd /home/ben/zurgcode && git rev-parse --short=8 HEAD)
DCOMMIT=$(cd /home/ben/bench/src/decypharr-git && git rev-parse --short=8 HEAD)
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "=== zurg $ZCOMMIT ==="
docker run --rm \
  -v /home/ben/zurgcode:/src -v "$OUT":/out -v "$CACHE":/go/pkg/mod \
  -w /src golang:1.26-alpine sh -c "
    apk add --no-cache git gcc musl-dev bash >/dev/null 2>&1
    CGO_ENABLED=0 go build -trimpath -buildvcs=false -ldflags \"-s -w \
      -X github.com/debridmediamanager/zurg/internal/version.BuiltAt=$STAMP \
      -X github.com/debridmediamanager/zurg/internal/version.GitCommit=$ZCOMMIT \
      -X github.com/debridmediamanager/zurg/internal/version.Version=main-$ZCOMMIT\" \
      -o /out/zurg-r4 ./cmd/zurg && chown 1000:1000 /out/zurg-r4 && echo ZURG_OK
  " 2>&1 | tail -20

echo "=== decypharr $DCOMMIT ==="
docker run --rm \
  -v /home/ben/bench/src/decypharr-git:/src -v "$OUT":/out -v "$CACHE":/go/pkg/mod \
  -w /src golang:1.26-alpine sh -c "
    apk add --no-cache git gcc g++ musl-dev libc-dev fuse-dev >/dev/null 2>&1
    CGO_ENABLED=1 go build -trimpath -buildvcs=false -ldflags \"-s -w \
      -X github.com/sirrobot01/decypharr/pkg/version.Version=main-$DCOMMIT \
      -X github.com/sirrobot01/decypharr/pkg/version.Channel=main\" \
      -o /out/decypharr-r4 . && chown 1000:1000 /out/decypharr-r4 && echo DECY_OK
  " 2>&1 | tail -20

ls -la "$OUT"
echo "BUILD_SCRIPT_DONE"
