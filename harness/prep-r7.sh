#!/bin/bash
# Round-7 prep: install the r7 builds, point every target at the designated
# bench news server, give every target the SAME NNTP connection budget, enable
# repair everywhere the feature exists, and create the two container targets.
#
# CONNECTION PARITY IS THE POINT OF THIS SCRIPT.
#
# Round 6 ran with three different effective budgets and it was invisible in the
# config files, because in three of the five the provider pool cap and the read
# budget are separate knobs:
#
#   zurg        connections: 20                       -> pool 20, reads 20
#   altmount    max_connections: 20                   -> pool 20, reads 20
#   infinidysk  MaxConnections: 50                    -> pool 50, reads 50
#               (max-download-connections unset = "auto" = TotalPooledConnections)
#   decypharr   providers[].max_connections: 20       -> pool 20
#               usenet.max_connections: 15            -> reads 15 per file
#   nzbdav-og   providers[].MaxConnections: 20        -> pool 20
#               usenet.max-download-connections: 15   -> reads 15
#
# infinidysk's own connection tuner measures ~25 MB/s at 20 connections and
# ~44 MB/s at 40 on this account, so the count is worth more than any difference
# between these programs. Every target gets exactly $CONNS here, set in both
# knobs where two exist.
set -eu
BENCH=/home/ben/bench
OUT=$BENCH/src/out
CORPUS="ToyStory5.nzb ToyStory5Damaged.nzb Obfuscated.nzb FatherBrown.nzb MandaloriaREMUX.nzb Bosch.S01.nzb"
HOST=news.news-provider.example
CONNS=${CONNS:-20}
IC=$(cd $BENCH/src/infinidysk-git && git rev-parse --short=8 HEAD)
NC=$(cd $BENCH/src/nzbdav-git && git rev-parse --short=8 HEAD)

echo "== parity: $CONNS NNTP connections per target, host $HOST =="

echo "== binaries =="
cp -f $BENCH/zurgrun/zurg $BENCH/zurgrun/zurg.r6.bak 2>/dev/null || true
cp -f $OUT/zurg-r7 $BENCH/zurgrun/zurg
cp -f $BENCH/altmount/altmount-cli-linux-amd64 $BENCH/altmount/altmount-cli.r6.bak 2>/dev/null || true
cp -f $OUT/altmount-r7 $BENCH/altmount/altmount-cli-linux-amd64
cp -f $BENCH/decypharr $BENCH/decypharr.r6.bak 2>/dev/null || true
cp -f $OUT/decypharr-r7 $BENCH/decypharr
chmod +x $BENCH/zurgrun/zurg $BENCH/altmount/altmount-cli-linux-amd64 $BENCH/decypharr
echo "-- decypharr --version"; timeout 20 $BENCH/decypharr --version 2>&1 | head -3 || true

echo "== corpus per target =="
for t in zurg altmount infinidysk nzbdav-og decypharr; do
  mkdir -p $BENCH/r7-nzbs/$t
  for n in $CORPUS; do cp -f $BENCH/nzbs/$n $BENCH/r7-nzbs/$t/$n; done
  echo "   $t: $(ls $BENCH/r7-nzbs/$t | wc -l) nzbs"
done

# corpus5b.py imports from its OWN staging dirs, not from r7-nzbs, and it hands
# each server a host path rather than the container mount. Round 5 lost
# altmount's whole damage result to this: am-nzbs held 3 of the corpus, so the
# import answered "File does not exist: .../am-nzbs/ToyStory5Damaged.nzb" and the
# phase had to be re-run by hand. Stage all four dirs every round.
echo "== corpus5b staging dirs =="
for d in am-nzbs id-nzbs og-nzbs zurgrun/nzbs; do
  mkdir -p $BENCH/$d
  for n in $CORPUS; do cp -f $BENCH/nzbs/$n $BENCH/$d/$n; done
  echo "   $d: $(ls $BENCH/$d | wc -l) nzbs"
done

# ---------------------------------------------------------------- zurg
# One knob, already the parity value. enable_repair was already true.
python3 - "$BENCH/zurgrun/config.yml" "$HOST" "$CONNS" <<'PY'
import re, sys
p, host, conns = sys.argv[1], sys.argv[2], int(sys.argv[3])
s = open(p).read()
s = re.sub(r'host: news[a-z0-9.-]*', f'host: {host}', s)
s = re.sub(r'connections: \d+', f'connections: {conns}', s)
s = re.sub(r'enable_repair: \w+', 'enable_repair: true', s)
open(p, 'w').write(s)
print("   zurg: connections=%d enable_repair=true" % conns)
PY

# ---------------------------------------------------------------- altmount
# Provider cap is the only connection knob. Repair lives UNDER health, so
# health.enabled must be true or the repair block is never reached.
python3 - "$BENCH/altmount/config.yaml" "$HOST" "$CONNS" <<'PY'
import re, sys
p, host, conns = sys.argv[1], sys.argv[2], int(sys.argv[3])
s = open(p).read()
s = re.sub(r"host: 'news[a-z0-9.-]*'", f"host: '{host}'", s)
s = re.sub(r'max_connections: \d+', f'max_connections: {conns}', s)
s = re.sub(r'health:\n  enabled: false',
           "health:\n  enabled: true\n  max_connections_for_health_checks: %d\n"
           "  check_interval_seconds: 60\n  repair:\n    enabled: true" % conns, s)
open(p, 'w').write(s)
print("   altmount: max_connections=%d health.enabled=true health.repair.enabled=true" % conns)
PY

# ---------------------------------------------------------------- decypharr
# Two knobs: providers[].max_connections is the socket pool, usenet.max_connections
# is the per-streaming-file read budget (its default is 15, which is why round 6
# read on 15 of its 20). Repair defaults to source "arr"; there are no arrs here,
# so it must be "managed" to run at all.
python3 - "$BENCH/decyrun/config.json" "$HOST" "$CONNS" <<'PY'
import json, sys
p, host, conns = sys.argv[1], sys.argv[2], int(sys.argv[3])
c = json.load(open(p))
u = c["usenet"]
for prov in u["providers"]:
    prov["host"] = host
    prov["max_connections"] = conns
u["max_connections"] = conns
u["processing_max_connections"] = conns
c["repair"] = {
    "enabled": True,
    "source": "managed",
    # A duration, not a nightly cron. The default recheck is 168h and the usual
    # schedule is a 3am sweep, so "repair: enabled" would be nominal here -- the
    # damage timeline watches for 8 minutes and nothing would ever fire in it.
    "schedule": "5m",
    "workers": 5,
    "nntp_connection_percent": 20,
    "strategy": "per_entry",
    "recheck_interval": "1m",
    "auto_repair": True,
}
json.dump(c, open(p, "w"), indent=2)
print("   decypharr: provider=%d usenet.max_connections=%d processing=%d repair.enabled=true source=managed"
      % (conns, conns, conns))
PY

# ---------------------------------------------------------------- nzbdav-og
# Master db is the reseed source, so the parity value is set there, not in the
# per-round copy. No repair feature exists: its Par2 code only deobfuscates names.
python3 - "$BENCH/nzbdav-og/config/db.sqlite" "$HOST" "$CONNS" <<'PY'
import json, sqlite3, sys
p, host, conns = sys.argv[1], sys.argv[2], int(sys.argv[3])
c = sqlite3.connect(p)
row = c.execute("select ConfigValue from ConfigItems where ConfigName='usenet.providers'").fetchone()
cfg = json.loads(row[0])
for prov in cfg["Providers"]:
    prov["Host"] = host
    prov["MaxConnections"] = conns
c.execute("update ConfigItems set ConfigValue=? where ConfigName='usenet.providers'", (json.dumps(cfg),))
c.execute("insert into ConfigItems (ConfigName, ConfigValue) values ('usenet.max-download-connections', ?) "
          "on conflict(ConfigName) do update set ConfigValue=excluded.ConfigValue", (str(conns),))
c.commit(); c.close()
print("   nzbdav-og: provider MaxConnections=%d max-download-connections=%d (no repair feature)" % (conns, conns))
PY

# ---------------------------------------------------------------- containers
echo "== container targets =="
mkdir -p $BENCH/infinidysk/config-r7 $BENCH/nzbdav-og/config-r7
docker rm -f infinidysk-r7 nzbdav-r7 >/dev/null 2>&1 || true

# MaxConnections is what sizes the pool (UsenetStreamingClient reads it, not
# MaxTransferConnections), and max-download-connections is pinned rather than
# left to "auto" -- auto resolves to TotalPooledConnections, which is how round 6
# ended up streaming on 50.
docker run -d --name infinidysk-r7 --network host --restart no \
  -v $BENCH/infinidysk/config-r7:/config \
  -v $BENCH/r7-nzbs/infinidysk:/nzbs:ro \
  -e PORT=3001 \
  -e ASPNETCORE_URLS=http://127.0.0.1:8092 \
  -e BACKEND_URL=http://127.0.0.1:8092 \
  -e CONFIG_PATH=/config \
  -e LOG_LEVEL=warning \
  -e NZBDAV_CONFIG__USENET__PROVIDERS="{\"Providers\":[{\"ProviderId\":\"11111111-2222-3333-4444-555555555555\",\"Type\":1,\"Host\":\"$HOST\",\"Port\":563,\"UseSsl\":true,\"SkipTlsVerification\":false,\"User\":\"YOUR_USENET_USERNAME\",\"Pass\":\"YOUR_USENET_PASSWORD\",\"MaxConnections\":$CONNS,\"MaxTransferConnections\":$CONNS,\"Priority\":0,\"StorageGroup\":\"\",\"BytesUsedOffset\":0,\"BytesUsedResetAt\":0}]}" \
  -e NZBDAV_CONFIG__USENET__MAX_DOWNLOAD_CONNECTIONS=$CONNS \
  -e NZBDAV_CONFIG__USENET__MAX_QUEUE_CONNECTIONS=$CONNS \
  -e NZBDAV_CONFIG__USENET__QUEUE_PIPELINING__ENABLED=true \
  -e NZBDAV_CONFIG__USENET__QUEUE_PIPELINING__DEPTH=4 \
  -e NZBDAV_CONFIG__REPAIR__ENABLE=true \
  -e NZBDAV_CONFIG__REPAIR__PAR2_ENABLED=true \
  -e NZBDAV_CONFIG__WEBDAV__USER=usenet \
  -e NZBDAV_CONFIG__WEBDAV__PASS=usenet \
  -e NZBDAV_CONFIG__API__KEY=benchbenchbenchbenchbenchbench12 \
  -e NZBDAV_CONFIG__API__COMPLETED_DOWNLOADS_DIR=/completed \
  infinidysk:r7-$IC >/dev/null
echo "   infinidysk-r7 on infinidysk:r7-$IC (MaxConnections=$CONNS, MaxTransferConnections=$CONNS)"

docker run -d --name nzbdav-r7 --network host --restart no \
  -v $BENCH/nzbdav-og/config-r7:/config \
  -v $BENCH/r7-nzbs/nzbdav-og:/nzbs \
  -e PORT=3002 \
  -e CONFIG_PATH=/config \
  -e BACKEND_URL=http://127.0.0.1:8093 \
  -e ASPNETCORE_URLS=http://127.0.0.1:8093 \
  -e WEBDAV_USER=usenet \
  -e WEBDAV_PASSWORD=usenet \
  -e LOG_LEVEL=warning \
  nzbdav:r7-$NC >/dev/null
echo "   nzbdav-r7 on nzbdav:r7-$NC"

sleep 25
for p in 8092 8093; do
  echo -n "   :$p health -> "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 http://127.0.0.1:$p/health || echo fail
done
docker stop infinidysk-r7 nzbdav-r7 >/dev/null
echo "PREP_R7_DONE"
