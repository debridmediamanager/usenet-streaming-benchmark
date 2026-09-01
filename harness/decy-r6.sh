#!/bin/bash
# decypharr needs cgo for its FUSE mount, and an alpine build links against
# musl -- which zen's glibc answers with "No such file or directory", the same
# trap the round-4 build hit. Build it on bookworm instead.
set -eu
BENCH=/home/ben/bench
DC=$(cd $BENCH/src/decypharr-git && git rev-parse --short=8 HEAD)
docker run --rm -v $BENCH/src/decypharr-git:/src -v $BENCH/src/out:/out \
  -v $BENCH/src/gomodcache-glibc:/go/pkg/mod -w /src golang:1.26-bookworm sh -c "
    apt-get update -qq >/dev/null 2>&1
    apt-get install -y -qq gcc g++ libfuse-dev libfuse3-dev pkg-config >/dev/null 2>&1
    CGO_ENABLED=1 go build -trimpath -buildvcs=false -ldflags '-s -w \
      -X github.com/sirrobot01/decypharr/pkg/version.Version=main-$DC \
      -X github.com/sirrobot01/decypharr/pkg/version.Channel=main' \
      -o /out/decypharr-r6 . && chown 1000:1000 /out/decypharr-r6 && echo DECY_GLIBC_OK
  " 2>&1 | tail -6
cp -f $BENCH/src/out/decypharr-r6 $BENCH/decypharr
chmod +x $BENCH/decypharr
file $BENCH/decypharr
$BENCH/decypharr --version 2>&1 | head -3 || true
echo "DECY_R6_DONE"
