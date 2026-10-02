#!/bin/bash
# Isolated round13 builds/reset. No service starts during build/reset/bootstrap.
set -euo pipefail
umask 077
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
export BENCH="${BENCH:-/home/ben/bench-round13-20261001}"
[[ "$BENCH" == /home/ben/bench-round13-20261001 && ! -L "$BENCH" ]] || { echo 'Unsafe BENCH' >&2; exit 1; }
[[ "${CONNS:-10}" == 10 ]] || { echo 'CONNS must be 10' >&2; exit 1; }
mkdir -p "$BENCH/src/out"
MANIFEST="$REPO/config/round13-existing.json"
case "${1:-}" in
build)
  # Each source checkout belongs exclusively to this task. Fail rather than replace dirty sources.
  python3 - "$MANIFEST" "$BENCH" <<'PY'
import json, pathlib, subprocess, sys
manifest, bench = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2])
for name, spec in manifest.items():
    dest = bench / 'src' / name
    if dest.exists():
        if subprocess.check_output(['git', '-C', str(dest), 'status', '--porcelain']).strip():
            raise SystemExit(f'Dirty isolated source: {name}')
    else:
        subprocess.run(['git', 'clone', spec['url'], str(dest)], check=True)
    subprocess.run(['git', '-C', str(dest), 'fetch', 'origin', spec['revision']], check=True)
    subprocess.run(['git', '-C', str(dest), 'checkout', '--detach', spec['revision']], check=True)
    subprocess.run(['git', '-C', str(dest), 'submodule', 'update', '--init', '--recursive'], check=True)
    got = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
    assert got == spec['revision']
PY
  # Debian bookworm yields glibc 2.36 binaries usable on zen; never copy Alpine CGO binaries.
  docker run --rm --name build-go-r13-20261001 -e GOMAXPROCS=2 \
    -v "$BENCH/src:/src" -w /src golang:1.26-bookworm bash -euc '
      apt-get update && apt-get install -y --no-install-recommends libfuse-dev libfuse3-dev pkg-config
      cd /src/zurg
      CGO_ENABLED=1 go build -p 2 -trimpath -buildvcs=false -ldflags="-X github.com/debridmediamanager/zurg/internal/version.GitCommit=998e661b92c840f6b9c8e152c5c9b17d1ba338c6 -X github.com/debridmediamanager/zurg/internal/version.Version=main-998e661b" -o /src/out/zurg-r13 ./cmd/zurg
      cd /src/decypharr
      CGO_ENABLED=1 go build -p 2 -trimpath -buildvcs=false -ldflags="-s -w -X github.com/sirrobot01/decypharr/pkg/version.Version=main-0dd1cbbd -X github.com/sirrobot01/decypharr/pkg/version.Channel=main" -o /src/out/decypharr-r13 .'
  # CLI embeds the real frontend (upstream cli build convention).
  docker run --rm --name build-alt-frontend-r13-20261001 \
    -v "$BENCH/src/altmount:/app" -w /app/frontend node:24-bookworm \
    bash -euc 'npm ci && APP_VERSION=main-b82b22c8 GIT_COMMIT=b82b22c8 npm run build'
  docker run --rm --name build-alt-go-r13-20261001 -e GOMAXPROCS=2 \
    -v "$BENCH/src:/src" -w /src/altmount golang:1.27-bookworm \
    bash -euc 'CGO_ENABLED=1 go build -p 2 -trimpath -buildvcs=false -tags=cli -ldflags="-s -w -X github.com/kipsilabs/altmount/internal/version.Version=main-b82b22c8 -X github.com/kipsilabs/altmount/internal/version.GitCommit=b82b22c85ce6f8f8f6ccba1985fe0835cade8d07" -o /src/out/altmount-r13 ./cmd/altmount'
  docker build --build-arg NZBDAV_VERSION=main-31c837fa --build-arg NZBDAV_COMMIT_SHA=31c837fa08c04495de2a2201813199b5dce0326e \
    -t infinidysk:r13-31c837fa08c0 "$BENCH/src/infinidysk"
  docker build --build-arg NZBDAV_VERSION=main-0c7d8e21 -t nzbdav:r13-0c7d8e215e06 "$BENCH/src/nzbdav-og"
  ;;
bootstrap)
  # Official migrate-only mode exits BEFORE creating NNTP clients or listening.
  # No credentials passed, no network, and never copies a production database.
  [[ ! -e "$BENCH/nzbdav-og/master/db.sqlite" ]] || { echo 'Master already exists; refusing overwrite' >&2; exit 1; }
  mkdir -p "$BENCH/nzbdav-og/master"
  docker run --rm --name nzbdav-bootstrap-r13-20261001 --network none \
    -v "$BENCH/nzbdav-og/master:/config" -e CONFIG_PATH=/config -e LOG_LEVEL=warning \
    --workdir /app/backend --entrypoint /app/backend/NzbWebDAV \
    nzbdav:r13-0c7d8e215e06 --db-migration
  ;;
reset)
  # Main lifecycle stops binary targets first. Refuse a reset if a task process remains.
  python3 - "$BENCH" <<'PY'
from pathlib import Path
import os, sys
root = sys.argv[1]
me = os.getpid()
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name) == me: continue
    try:
        exe = str((p / 'exe').resolve())
        cmd = (p / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
    except (FileNotFoundError, PermissionError, ProcessLookupError): continue
    if exe.startswith(root + '/') and any(n in exe for n in ('zurg', 'altmount', 'decypharr')):
        raise SystemExit(f'Target process still alive: {p.name}; stop through orchestration first')
PY
  for name in infinidysk-r13-20261001 nzbdav-r13-20261001; do
    if docker inspect "$name" >/dev/null 2>&1; then
      owned="$(docker inspect --format '{{ index .Config.Labels "benchmark.round" }}' "$name")"
      [[ "$owned" == r13-20261001 ]] || { echo "Unowned container $name" >&2; exit 1; }
      docker rm -f "$name" >/dev/null
    fi
  done
  STAMP="$(date -u +%Y%m%dT%H%M%S)-$$"
  mkdir -p "$BENCH/retired/$STAMP"
  for relative in zurgrun/data zurgrun/nzbs altmount/cfg altmount/tmp decyrun infinidysk/config-r10 nzbdav-og/config-r10; do
    if [[ -e "$BENCH/$relative" ]]; then
      mkdir -p "$BENCH/retired/$STAMP/$(dirname "$relative")"
      mv "$BENCH/$relative" "$BENCH/retired/$STAMP/$relative"
    fi
  done
  mkdir -p "$BENCH/zurgrun/nzbs" "$BENCH/altmount/cfg" "$BENCH/altmount/tmp" \
    "$BENCH/decyrun/downloads" "$BENCH/decyrun/streams" \
    "$BENCH/infinidysk/config-r10" "$BENCH/nzbdav-og/config-r10" "$BENCH/r10-nzbs-mount"
  install -m755 "$BENCH/src/out/zurg-r13" "$BENCH/zurgrun/zurg"
  install -m755 "$BENCH/src/out/decypharr-r13" "$BENCH/decypharr"
  # os.TempDir() is used by current AltMount persistent queue: never touch global /tmp.
  cat > "$BENCH/altmount/altmount-cli-linux-amd64" <<'SH'
#!/bin/bash
set -eu
export TMPDIR=/home/ben/bench-round13-20261001/altmount/tmp
export GOMAXPROCS=2
exec /home/ben/bench-round13-20261001/src/out/altmount-r13 "$@"
SH
  chmod 755 "$BENCH/altmount/altmount-cli-linux-amd64"
  python3 "$HERE/config_r13.py" render
  [[ -f "$BENCH/nzbdav-og/master/db.sqlite" ]] || { echo 'Run bootstrap first' >&2; exit 1; }
  # SQLite backup API is safe even if WAL was used by migration.
  python3 - "$BENCH" <<'PY'
import sqlite3, sys
from pathlib import Path
root = Path(sys.argv[1])
src = sqlite3.connect(f'file:{root}/nzbdav-og/master/db.sqlite?mode=ro', uri=True)
dst = sqlite3.connect(str(root / 'nzbdav-og/config-r10/db.sqlite'))
src.backup(dst)
dst.close(); src.close()
PY
  python3 "$HERE/config_r13.py" seed
  # Stage only corpus inputs, never pre-import any target library.
  python3 "$HERE/corpus_r10.py" derive
  cp "$REPO"/corpus/*.nzb "$BENCH/r10-nzbs-mount/"
  cp "$REPO"/corpus/derived/*.nzb "$BENCH/r10-nzbs-mount/"
  cp "$HERE/rawserve_r10.py" "$HERE/nntp_r10.py" "$BENCH/"
  docker create --name infinidysk-r13-20261001 --label benchmark.round=r13-20261001 --network host --restart no \
    --label com.centurylinklabs.watchtower.enable=false \
    -v "$BENCH/infinidysk/config-r10:/config" -v "$BENCH/r10-nzbs-mount:/nzbs:ro" \
    --env-file "$BENCH/infinidysk/r13.env" infinidysk:r13-31c837fa08c0 >/dev/null
  docker create --name nzbdav-r13-20261001 --label benchmark.round=r13-20261001 --network host --restart no \
    --label com.centurylinklabs.watchtower.enable=false \
    -v "$BENCH/nzbdav-og/config-r10:/config" -v "$BENCH/r10-nzbs-mount:/nzbs:ro" \
    -e PORT=18095 -e CONFIG_PATH=/config -e ASPNETCORE_URLS=http://127.0.0.1:18093 \
    -e BACKEND_URL=http://127.0.0.1:18093 -e FRONTEND_BACKEND_API_KEY=benchbenchbenchbenchbenchbench12 \
    -e WEBDAV_USER=usenet -e WEBDAV_PASSWORD=usenet -e LOG_LEVEL=warning -e DOTNET_PROCESSOR_COUNT=2 \
    -e DOTNET_GCHeapHardLimit=60000000 nzbdav:r13-0c7d8e215e06 >/dev/null
  python3 "$HERE/prep_aiostreams_r13.py" prepare
  echo 'Reset complete: empty target libraries/cache, three stopped task-owned containers; nothing started'
  ;;
validate)
  python3 "$HERE/readback_r13.py" "${2:?Specify one currently running target}"
  ;;
*) echo 'Usage: prep-r13.sh build|bootstrap|reset|validate TARGET' >&2; exit 2 ;;
esac
