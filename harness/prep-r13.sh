#!/bin/bash
# Isolated round13 builds/reset. No service starts during build/reset/bootstrap.
set -euo pipefail
umask 077
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
# ROUND (round_profile.py) fixes the working directory, revisions, image tags and CPU count
eval "$(python3 "$HERE/round_profile.py" env)"
export BENCH="${BENCH:-$ROUND_BENCH}"
[[ "$BENCH" == "$ROUND_BENCH" && ! -L "$BENCH" ]] || { echo 'Unsafe BENCH' >&2; exit 1; }
[[ "${CONNS:-10}" == 10 ]] || { echo 'CONNS must be 10' >&2; exit 1; }
mkdir -p "$BENCH/src/out"
MANIFEST="$ROUND_MANIFEST"
case "${1:-}" in
build)
  # Each source checkout belongs exclusively to this task. Fail rather than replace dirty sources.
  python3 - "$MANIFEST" "$BENCH" <<'PY'
import json, pathlib, subprocess, sys
manifest, bench = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2])
for name, spec in manifest.items():
    if name == 'aiostreams':
        continue
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
  # The Go image is the one each module's own go.mod asks for (round 13: zurg
  # and decypharr 1.26, AltMount 1.27). Debian bookworm yields glibc 2.36
  # binaries; never copy Alpine CGO binaries.
  goimg () { echo "golang:$(awk '/^go /{split($2,v,"."); print v[1]"."v[2]; exit}' "$BENCH/src/$1/go.mod")-bookworm"; }
  docker run --rm --name "build-zurg-$ROUND_TAG" -e GOMAXPROCS="$ROUND_CPUS" \
    -v "$BENCH/src:/src" -w /src/zurg "$(goimg zurg)" bash -euc "
      apt-get update && apt-get install -y --no-install-recommends libfuse-dev libfuse3-dev pkg-config
      CGO_ENABLED=1 go build -p $ROUND_CPUS -trimpath -buildvcs=false -ldflags='-X github.com/debridmediamanager/zurg/internal/version.GitCommit=$REV_ZURG -X github.com/debridmediamanager/zurg/internal/version.Version=main-${REV_ZURG:0:8}' -o /src/out/zurg-$ROUND ./cmd/zurg"
  docker run --rm --name "build-decypharr-$ROUND_TAG" -e GOMAXPROCS="$ROUND_CPUS" \
    -v "$BENCH/src:/src" -w /src/decypharr "$(goimg decypharr)" bash -euc "
      apt-get update && apt-get install -y --no-install-recommends libfuse-dev libfuse3-dev pkg-config
      CGO_ENABLED=1 go build -p $ROUND_CPUS -trimpath -buildvcs=false -ldflags='-s -w -X github.com/sirrobot01/decypharr/pkg/version.Version=main-${REV_DECYPHARR:0:8} -X github.com/sirrobot01/decypharr/pkg/version.Channel=main' -o /src/out/decypharr-$ROUND ."
  # CLI embeds the real frontend (upstream cli build convention).
  docker run --rm --name "build-alt-frontend-$ROUND_TAG" \
    -v "$BENCH/src/altmount:/app" -w /app/frontend node:24-bookworm \
    bash -euc "npm ci && APP_VERSION=main-${REV_ALTMOUNT:0:8} GIT_COMMIT=${REV_ALTMOUNT:0:8} npm run build"
  docker run --rm --name "build-alt-go-$ROUND_TAG" -e GOMAXPROCS="$ROUND_CPUS" \
    -v "$BENCH/src:/src" -w /src/altmount "$(goimg altmount)" \
    bash -euc "CGO_ENABLED=1 go build -p $ROUND_CPUS -trimpath -buildvcs=false -tags=cli -ldflags='-s -w -X github.com/kipsilabs/altmount/internal/version.Version=main-${REV_ALTMOUNT:0:8} -X github.com/kipsilabs/altmount/internal/version.GitCommit=$REV_ALTMOUNT' -o /src/out/altmount-$ROUND ./cmd/altmount"
  docker build --build-arg NZBDAV_VERSION="main-${REV_INFINIDYSK:0:8}" --build-arg NZBDAV_COMMIT_SHA="$REV_INFINIDYSK" \
    -t "$IMG_INFINIDYSK" "$BENCH/src/infinidysk"
  docker build --build-arg NZBDAV_VERSION="main-${REV_NZBDAV_OG:0:8}" -t "$IMG_NZBDAV_OG" "$BENCH/src/nzbdav-og"
  ;;
bootstrap)
  # Official migrate-only mode exits BEFORE creating NNTP clients or listening.
  # No credentials passed, no network, and never copies a production database.
  [[ ! -e "$BENCH/nzbdav-og/master/db.sqlite" ]] || { echo 'Master already exists; refusing overwrite' >&2; exit 1; }
  mkdir -p "$BENCH/nzbdav-og/master"
  docker run --rm --name "nzbdav-bootstrap-$ROUND_TAG" --network none \
    -v "$BENCH/nzbdav-og/master:/config" -e CONFIG_PATH=/config -e LOG_LEVEL=warning \
    --workdir /app/backend --entrypoint /app/backend/NzbWebDAV \
    "$IMG_NZBDAV_OG" --db-migration
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
  for name in "$CTR_INFINIDYSK" "$CTR_NZBDAV_OG"; do
    if docker inspect "$name" >/dev/null 2>&1; then
      owned="$(docker inspect --format '{{ index .Config.Labels "benchmark.round" }}' "$name")"
      [[ "$owned" == "$ROUND_TAG" ]] || { echo "Unowned container $name" >&2; exit 1; }
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
  install -m755 "$BENCH/src/out/zurg-$ROUND" "$BENCH/zurgrun/zurg"
  install -m755 "$BENCH/src/out/decypharr-$ROUND" "$BENCH/decypharr"
  # os.TempDir() is used by current AltMount persistent queue: never touch global /tmp.
  cat > "$BENCH/altmount/altmount-cli-linux-amd64" <<SH
#!/bin/bash
set -eu
export TMPDIR=$BENCH/altmount/tmp
export GOMAXPROCS=$ROUND_CPUS
exec $BENCH/src/out/altmount-$ROUND "\$@"
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
  docker create --name "$CTR_INFINIDYSK" --label benchmark.round="$ROUND_TAG" --network host --restart no \
    --label com.centurylinklabs.watchtower.enable=false \
    -v "$BENCH/infinidysk/config-r10:/config" -v "$BENCH/r10-nzbs-mount:/nzbs:ro" \
    --env-file "$BENCH/infinidysk/r13.env" "$IMG_INFINIDYSK" >/dev/null
  docker create --name "$CTR_NZBDAV_OG" --label benchmark.round="$ROUND_TAG" --network host --restart no \
    --label com.centurylinklabs.watchtower.enable=false \
    -v "$BENCH/nzbdav-og/config-r10:/config" -v "$BENCH/r10-nzbs-mount:/nzbs:ro" \
    -e PORT=18095 -e CONFIG_PATH=/config -e ASPNETCORE_URLS=http://127.0.0.1:18093 \
    -e BACKEND_URL=http://127.0.0.1:18093 -e FRONTEND_BACKEND_API_KEY=benchbenchbenchbenchbenchbench12 \
    -e WEBDAV_USER=usenet -e WEBDAV_PASSWORD=usenet -e LOG_LEVEL=warning -e DOTNET_PROCESSOR_COUNT="$ROUND_CPUS" \
    -e DOTNET_GCHeapHardLimit=60000000 "$IMG_NZBDAV_OG" >/dev/null
  python3 "$HERE/prep_aiostreams_r13.py" prepare
  echo 'Reset complete: empty target libraries/cache, three stopped task-owned containers; nothing started'
  ;;
validate)
  python3 "$HERE/readback_r13.py" "${2:?Specify one currently running target}"
  ;;
*) echo 'Usage: prep-r13.sh build|bootstrap|reset|validate TARGET' >&2; exit 2 ;;
esac
