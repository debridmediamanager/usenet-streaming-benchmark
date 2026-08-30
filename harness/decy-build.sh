#!/bin/sh
set -e
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq gcc g++ libfuse-dev libfuse3-dev pkg-config >/dev/null 2>&1
cd /src
CGO_ENABLED=1 go build -trimpath -buildvcs=false \
  -ldflags="-s -w -X github.com/sirrobot01/decypharr/pkg/version.Version=main-0dd1cbbd -X github.com/sirrobot01/decypharr/pkg/version.Channel=main" \
  -o /out/decypharr-r4 .
chown 1000:1000 /out/decypharr-r4
echo DECY_GLIBC_OK
