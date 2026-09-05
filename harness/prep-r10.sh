#!/bin/bash
# Round 10 preparation: an empty library everywhere, then the containers.
#
#   ./harness/prep-r10.sh
#   CONNS=20 ./harness/prep-r10.sh
#
# Rounds 3 through 9 staged the corpus into every target BEFORE the target
# started, so each one loaded its whole library at boot and the import that
# followed found the release already there. That is fine for a round measuring
# throughput and it is fatal for round 10, which splits import out of cold open
# and reports it as a column of its own. An import into a target that already
# holds the release measures nothing and reads as a very fast one.
#
# So the library is reset here rather than in the run: every target starts a
# round 10 with nothing in it, and the first thing that happens to each entry is
# a real import.
#
# Nothing is deleted. State moves aside under a timestamp so rounds 7 and 9 stay
# reproducible from the same host.
set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
BENCH="${BENCH:-/home/ben/bench}"
CONNS="${CONNS:-15}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
KEY="benchbenchbenchbenchbenchbench12"

say () { echo "== $1"; }
die () { echo "!! $1" >&2; exit 1; }

for var in NNTP_HOST NNTP_USER NNTP_PASS; do
  eval "value=\${$var:-}"
  [ -n "$value" ] || die "$var is not set. The round reads the account from the environment"
done
PORT_NNTP="${NNTP_PORT:-563}"

# Move a path aside, keeping this round's predecessors intact.
retire () {
  [ -e "$1" ] || return 0
  mv "$1" "$1.pre-r10-$STAMP"
  echo "   retired $(basename "$1") -> $(basename "$1").pre-r10-$STAMP"
}

# ------------------------------------------------------------------- corpus
say "corpus"
ls "$REPO"/corpus/*.nzb >/dev/null 2>&1 || die "corpus not extracted: 7z x -pdmmbench corpus/corpus.7z"
python3 "$HERE/corpus_r10.py" derive >/dev/null || die "negative-tier derivation failed"
mkdir -p "$BENCH/r10-nzbs"
cp -f "$REPO"/corpus/*.nzb "$BENCH/r10-nzbs/"
[ -d "$REPO/corpus/derived" ] && cp -f "$REPO"/corpus/derived/*.nzb "$BENCH/r10-nzbs/" 2>/dev/null || true
echo "   $BENCH/r10-nzbs: $(ls "$BENCH"/r10-nzbs | wc -l) nzbs"

# The ceiling's launch command runs from $BENCH, so its two files live there.
say "ceiling"
cp -f "$HERE/rawserve_r10.py" "$HERE/nntp_r10.py" "$BENCH/"
echo "   rawserve_r10.py and nntp_r10.py staged in $BENCH"

# -------------------------------------------------------------------- zurg
# The watched directory IS the import, so it has to start empty, and data/
# carries the parsed library that would otherwise survive the reset.
say "zurg"
retire "$BENCH/zurgrun/nzbs"
retire "$BENCH/zurgrun/data"
mkdir -p "$BENCH/zurgrun/nzbs"

# ---------------------------------------------------------------- altmount
# Three places, and the third one is not under its config directory: it moves
# each NZB it is handed into /tmp/.altmount-queue and reads it back from there.
say "altmount"
retire "$BENCH/altmount/cfg/altmount.db"
retire "$BENCH/altmount/cfg/metadata"
retire "$BENCH/altmount/cfg/.nzbs"
retire "/tmp/.altmount-queue"

# A target whose default port is held by something that is not ours has to
# move, because stop() frees a port by killing whatever listens on it. The
# registry reads the same R10_PORTS, and the config has to agree with it or the
# server comes up somewhere the run does not look.
python3 - "$BENCH/altmount/config.yaml" <<'PY'
import os, re, sys
moved = dict(
    (item.split("=")[0].strip(), item.split("=")[1].strip())
    for item in os.environ.get("R10_PORTS", "").split(",") if "=" in item)
port = moved.get("altmount")
if not port:
    sys.exit(0)
path = sys.argv[1]
text = open(path).read()
text = re.sub(r"(?m)^(webdav:\n(?:.*\n)*?\s*port: )\d+", r"\g<1>" + port, text, count=1)
text = re.sub(r"http://localhost:\d+", f"http://localhost:{port}", text)
open(path, "w").write(text)
if not re.search(r"(?m)^\s*port: %s\s*$" % port, open(path).read()):
    sys.exit(f"   altmount: port {port} NOT SET in {path}")
print(f"   altmount moved to :{port} (its default is held by something else here)")
PY

# --------------------------------------------------------------- decypharr
say "decypharr"
retire "$BENCH/decyrun/db"
retire "$BENCH/decyrun/usenet"
retire "$BENCH/decyrun/downloads"
retire "$BENCH/decyrun/streams"
mkdir -p "$BENCH/decyrun/downloads" "$BENCH/decyrun/streams"

# --------------------------------------------------------------- containers
say "containers"
docker rm -f infinidysk-r10 nzbdav-r10 >/dev/null 2>&1 || true
retire "$BENCH/infinidysk/config-r10"
retire "$BENCH/nzbdav-og/config-r10"
mkdir -p "$BENCH/infinidysk/config-r10" "$BENCH/nzbdav-og/config-r10"
mkdir -p "$BENCH/r10-nzbs-mount"
cp -f "$BENCH"/r10-nzbs/*.nzb "$BENCH/r10-nzbs-mount/"

IMG_ID="${INFINIDYSK_IMAGE:-$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -m1 '^infinidysk:r7-')}"
IMG_ND="${NZBDAV_IMAGE:-$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -m1 '^nzbdav:r7-')}"
[ -n "$IMG_ID" ] || die "no infinidysk image built. prep-r7.sh builds it from $BENCH/src"
[ -n "$IMG_ND" ] || die "no nzbdav image built. prep-r7.sh builds it from $BENCH/src"

# nzbdav-og keeps its provider settings in the database rather than the
# environment, so a fresh config directory has no account in it at all. The
# master db is the reseed source and carries the parity value already.
[ -f "$BENCH/nzbdav-og/config/db.sqlite" ] || die "no master db to reseed nzbdav-og from"
cp -f "$BENCH/nzbdav-og/config/db.sqlite" "$BENCH/nzbdav-og/config-r10/db.sqlite"
python3 - "$BENCH/nzbdav-og/config-r10/db.sqlite" "$NNTP_HOST" "$NNTP_USER" "$NNTP_PASS" "$CONNS" <<'PY'
import json, sqlite3, sys
path, host, user, password, conns = sys.argv[1:5] + [int(sys.argv[5])]
db = sqlite3.connect(path)
row = db.execute("select ConfigValue from ConfigItems "
                 "where ConfigName='usenet.providers'").fetchone()
cfg = json.loads(row[0])
for provider in cfg["Providers"]:
    provider["Host"] = host
    provider["User"] = user
    provider["Pass"] = password
    provider["MaxConnections"] = conns
db.execute("update ConfigItems set ConfigValue=? where ConfigName='usenet.providers'",
           (json.dumps(cfg),))
db.execute("insert into ConfigItems (ConfigName, ConfigValue) "
           "values ('usenet.max-download-connections', ?) on conflict(ConfigName) "
           "do update set ConfigValue=excluded.ConfigValue", (str(conns),))
db.commit()
# Read the committed rows back. An upsert against a column with no unique index
# writes nothing and says so to nobody, and the provider loop does nothing at
# all if the JSON key is not "Providers" -- both used to report parity anyway.
row = db.execute("select ConfigValue from ConfigItems "
                 "where ConfigName='usenet.providers'").fetchone()
got = [(p.get("MaxConnections"), p.get("Host")) for p in json.loads(row[0])["Providers"]]
row = db.execute("select ConfigValue from ConfigItems "
                 "where ConfigName='usenet.max-download-connections'").fetchone()
download = row[0] if row else None
# The library has to be empty for an import to be an import. These are the
# tables that make a release visible again after a reseed.
for table in ("DavItems", "QueueItems", "HistoryItems"):
    try:
        db.execute(f"delete from {table}")
    except sqlite3.Error:
        pass
db.commit()
db.close()
if set(x[0] for x in got) != {conns} or str(download) != str(conns):
    sys.exit(f"   nzbdav-og PARITY NOT SET: providers={got} "
             f"max-download-connections={download!r}")
print(f"   nzbdav-og: MaxConnections={conns} max-download-connections={conns} "
      f"host={got[0][1]} (library emptied)")
PY

PROVIDERS="{\"Providers\":[{\"ProviderId\":\"11111111-2222-3333-4444-555555555555\",\"Type\":1,\"Host\":\"$NNTP_HOST\",\"Port\":$PORT_NNTP,\"UseSsl\":true,\"SkipTlsVerification\":false,\"User\":\"$NNTP_USER\",\"Pass\":\"$NNTP_PASS\",\"MaxConnections\":$CONNS,\"MaxTransferConnections\":$CONNS,\"Priority\":0,\"StorageGroup\":\"\",\"BytesUsedOffset\":0,\"BytesUsedResetAt\":0}]}"

docker run -d --name infinidysk-r10 --network host --restart no \
  -v "$BENCH/infinidysk/config-r10:/config" \
  -v "$BENCH/r10-nzbs-mount:/nzbs:ro" \
  -e PORT=3001 \
  -e ASPNETCORE_URLS=http://127.0.0.1:8092 \
  -e BACKEND_URL=http://127.0.0.1:8092 \
  -e CONFIG_PATH=/config \
  -e LOG_LEVEL=warning \
  -e NZBDAV_CONFIG__USENET__PROVIDERS="$PROVIDERS" \
  -e NZBDAV_CONFIG__USENET__MAX_DOWNLOAD_CONNECTIONS=$CONNS \
  -e NZBDAV_CONFIG__USENET__MAX_QUEUE_CONNECTIONS=$CONNS \
  -e NZBDAV_CONFIG__USENET__QUEUE_PIPELINING__ENABLED=true \
  -e NZBDAV_CONFIG__USENET__QUEUE_PIPELINING__DEPTH=4 \
  -e NZBDAV_CONFIG__REPAIR__ENABLE=true \
  -e NZBDAV_CONFIG__REPAIR__PAR2_ENABLED=true \
  -e NZBDAV_CONFIG__WEBDAV__USER=usenet \
  -e NZBDAV_CONFIG__WEBDAV__PASS=usenet \
  -e NZBDAV_CONFIG__API__KEY="$KEY" \
  -e NZBDAV_CONFIG__API__COMPLETED_DOWNLOADS_DIR=/completed \
  "$IMG_ID" >/dev/null
echo "   infinidysk-r10 on $IMG_ID (MaxConnections=$CONNS)"

docker run -d --name nzbdav-r10 --network host --restart no \
  -v "$BENCH/nzbdav-og/config-r10:/config" \
  -v "$BENCH/r10-nzbs-mount:/nzbs" \
  -e PORT=3002 \
  -e CONFIG_PATH=/config \
  -e BACKEND_URL=http://127.0.0.1:8093 \
  -e ASPNETCORE_URLS=http://127.0.0.1:8093 \
  -e WEBDAV_USER=usenet \
  -e WEBDAV_PASSWORD=usenet \
  -e LOG_LEVEL=warning \
  "$IMG_ND" >/dev/null
echo "   nzbdav-r10 on $IMG_ND"

sleep 25
for port in 8092 8093; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$port/health" || echo fail)
  echo "   :$port health -> $code"
  case "$code" in 2*|3*|4*) ;; *) die "container on :$port never answered" ;; esac
done
docker stop infinidysk-r10 nzbdav-r10 >/dev/null
echo "   both stopped. The run starts one target at a time"

# ------------------------------------------------------------------- parity
# Configuration has been wrong before, which is why round 9 checked live
# sockets. This is the cheaper half: what the files say, before the run.
say "parity ($CONNS connections)"
python3 - "$BENCH" "$CONNS" <<'PY'
import json, re, sys
bench, conns = sys.argv[1], int(sys.argv[2])
bad = []

text = open(f"{bench}/zurgrun/config.yml").read()
if not re.search(r"(?m)^\s*connections: %d\s*$" % conns, text):
    bad.append("zurg connections")
if not re.search(r"(?m)^\s*enable_repair: true\s*$", text):
    bad.append("zurg enable_repair")

text = open(f"{bench}/altmount/config.yaml").read()
if set(int(x) for x in re.findall(r"max_connections: (\d+)", text)) - {conns}:
    bad.append("altmount max_connections")

cfg = json.load(open(f"{bench}/decyrun/config.json"))
found = {cfg["usenet"]["max_connections"], cfg["usenet"]["processing_max_connections"]}
found |= {p["max_connections"] for p in cfg["usenet"]["providers"]}
if found != {conns}:
    bad.append(f"decypharr connections {sorted(found)}")

print("   " + ("PARITY NOT SET: " + ", ".join(bad) if bad
               else f"zurg, altmount and decypharr all at {conns}"))
sys.exit(1 if bad else 0)
PY

echo
echo "== ready. Nothing holds a library; every import in the run is a real one."
