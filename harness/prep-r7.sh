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
# re.sub that matches nothing returns the string unchanged and says so to
# nobody, and the print below used to run either way -- a config whose shape
# drifted was ANNOUNCED as parity-set while still carrying the old value.
# Assert against the bytes now on disk, not against the intent.
chk = open(p).read()
missing = []
if not re.search(r'(?m)^\s*connections: %d\s*$' % conns, chk):
    missing.append("connections: %d" % conns)
if not re.search(r'(?m)^\s*enable_repair: true\s*$', chk):
    missing.append("enable_repair: true")
if missing:
    print("   zurg: PARITY NOT SET in %s -- expected %s" % (p, ", ".join(missing)))
    print("   found: %s" % [l.rstrip() for l in chk.splitlines()
                            if re.search(r'connections|enable_repair|host:', l)])
    sys.exit(1)
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
# The health substitution is a LITERAL 'health:\n  enabled: false'. A config
# that already carries 'enabled: true' (a re-run, or a hand edit) matches
# nothing, so the repair block is never inserted -- and the old print announced
# repair anyway. Verify the health block on disk really holds both toggles.
chk = open(p).read()
missing = []
if not re.search(r'(?m)^\s*max_connections: %d\s*$' % conns, chk):
    missing.append("max_connections: %d" % conns)
hb = re.search(r'(?m)^health:\n(?P<b>(?:[ \t].*\n|\n)*)', chk)
hbody = hb.group("b") if hb else ""
if not re.search(r'(?m)^ {2}enabled: true\s*$', hbody):
    missing.append("health.enabled: true")
rb = re.search(r'(?m)^ {2}repair:\n(?P<b>(?:[ \t]{3,}.*\n|\n)*)', hbody)
if not (rb and re.search(r'(?m)^\s+enabled: true\s*$', rb.group("b"))):
    missing.append("health.repair.enabled: true")
if missing:
    print("   altmount: PARITY NOT SET in %s -- expected %s" % (p, ", ".join(missing)))
    print("   found health block: %r" % (hbody[:400] or "<no health: block>"))
    print("   found: %s" % [l.rstrip() for l in chk.splitlines()
                            if re.search(r'max_connections|host:', l)])
    sys.exit(1)
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
# Re-parse rather than trust the dict just written: an unexpected config shape
# (no "usenet", providers renamed) would raise above, but a partially applied
# edit would not, and every other target's print used to be unconditional too.
chk = json.load(open(p))
cu = chk.get("usenet", {})
got = {
    "usenet.max_connections": cu.get("max_connections"),
    "usenet.processing_max_connections": cu.get("processing_max_connections"),
    "providers[].max_connections": [x.get("max_connections") for x in cu.get("providers", [])],
    "repair.enabled": chk.get("repair", {}).get("enabled"),
}
ok = (got["usenet.max_connections"] == conns
      and got["usenet.processing_max_connections"] == conns
      and got["providers[].max_connections"]
      and set(got["providers[].max_connections"]) == {conns}
      and got["repair.enabled"] is True)
if not ok:
    print("   decypharr: PARITY NOT SET in %s" % p)
    print("   expected every connection value == %d and repair.enabled True, found %s"
          % (conns, got))
    sys.exit(1)
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
c.commit()
# Re-query the committed rows. The upsert silently writes nothing useful if
# ConfigName has no unique index, and the provider loop silently does nothing
# if the JSON key is not "Providers" -- both used to print parity regardless.
row = c.execute("select ConfigValue from ConfigItems where ConfigName='usenet.providers'").fetchone()
got_p = [x.get("MaxConnections") for x in json.loads(row[0])["Providers"]] if row else []
row = c.execute("select ConfigValue from ConfigItems "
                "where ConfigName='usenet.max-download-connections'").fetchone()
got_d = row[0] if row else None
c.close()
if not got_p or set(got_p) != {conns} or str(got_d) != str(conns):
    print("   nzbdav-og: PARITY NOT SET in %s" % p)
    print("   expected MaxConnections %d on every provider and "
          "max-download-connections %d, found providers=%s max-download-connections=%r"
          % (conns, conns, got_p, got_d))
    sys.exit(1)
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

# ---------------------------------------------------------------- verify
# The README told the reader to run five commands by hand "before trusting a
# run". Round 6 was invalidated because nobody did. Those five checks, in code,
# on every prep: every value re-read from disk or from `docker inspect` (which
# answers on a stopped container) rather than from what this script believes it
# wrote.
echo "== verify parity =="
python3 - "$BENCH" "$CONNS" infinidysk-r7 <<'PY'
import json, re, sqlite3, subprocess, sys

bench, conns, ictr = sys.argv[1], int(sys.argv[2]), sys.argv[3]
bad = []


def report(target, ok, detail):
    print("   %-11s %-4s %s" % (target, "OK" if ok else "FAIL", detail))
    if not ok:
        bad.append(target)


# zurg -- one knob, pool and reads both
s = open(f"{bench}/zurgrun/config.yml").read()
v = [int(x) for x in re.findall(r'(?m)^\s*connections: (\d+)\s*$', s)]
rep = sorted(set(re.findall(r'(?m)^\s*enable_repair: (\w+)\s*$', s)))
report("zurg", bool(v) and set(v) == {conns} and rep == ["true"],
       "connections=%s enable_repair=%s" % (v, rep))

# altmount -- provider cap is the only connection knob; repair sits under health
s = open(f"{bench}/altmount/config.yaml").read()
v = [int(x) for x in re.findall(r'(?m)^\s*max_connections: (\d+)\s*$', s)]
hb = re.search(r'(?m)^health:\n(?P<b>(?:[ \t].*\n|\n)*)', s)
hbody = hb.group("b") if hb else ""
henab = bool(re.search(r'(?m)^ {2}enabled: true\s*$', hbody))
rb = re.search(r'(?m)^ {2}repair:\n(?P<b>(?:[ \t]{3,}.*\n|\n)*)', hbody)
renab = bool(rb and re.search(r'(?m)^\s+enabled: true\s*$', rb.group("b")))
report("altmount", bool(v) and set(v) == {conns} and henab and renab,
       "max_connections=%s health.enabled=%s health.repair.enabled=%s"
       % (v, henab, renab))

# decypharr -- socket pool and per-file read budget are separate knobs
c = json.load(open(f"{bench}/decyrun/config.json"))
u = c.get("usenet", {})
pv = [x.get("max_connections") for x in u.get("providers", [])]
report("decypharr",
       bool(pv) and set(pv) == {conns} and u.get("max_connections") == conns
       and u.get("processing_max_connections") == conns
       and c.get("repair", {}).get("enabled") is True,
       "providers=%s usenet.max_connections=%s processing=%s repair.enabled=%s"
       % (pv, u.get("max_connections"), u.get("processing_max_connections"),
          c.get("repair", {}).get("enabled")))

# infinidysk -- every setting arrives by environment variable, so the container
# definition IS the config; nothing on disk to read.
env = {}
try:
    raw = subprocess.run(["docker", "inspect", ictr, "--format", "{{json .Config.Env}}"],
                         capture_output=True, text=True, timeout=60, check=True).stdout
    env = dict(x.split("=", 1) for x in json.loads(raw) if "=" in x)
except Exception as exc:
    print("   infinidysk  docker inspect %s failed: %s" % (ictr, str(exc)[:160]))
prov = json.loads(env.get("NZBDAV_CONFIG__USENET__PROVIDERS", '{"Providers":[]}'))
pv = [(x.get("MaxConnections"), x.get("MaxTransferConnections"))
      for x in prov.get("Providers", [])]
dl = env.get("NZBDAV_CONFIG__USENET__MAX_DOWNLOAD_CONNECTIONS")
report("infinidysk", bool(pv) and set(pv) == {(conns, conns)} and str(dl) == str(conns),
       "providers(Max,MaxTransfer)=%s max-download-connections=%s" % (pv, dl))

# nzbdav-og -- the master db, because that is the reseed source tree_r7.py
# copies into the per-round config dir; the container carries no connection env.
db = sqlite3.connect(f"file:{bench}/nzbdav-og/config/db.sqlite?mode=ro", uri=True)
row = db.execute("select ConfigValue from ConfigItems "
                 "where ConfigName='usenet.providers'").fetchone()
pv = [x.get("MaxConnections") for x in json.loads(row[0])["Providers"]] if row else []
row = db.execute("select ConfigValue from ConfigItems "
                 "where ConfigName='usenet.max-download-connections'").fetchone()
dl = row[0] if row else None
db.close()
report("nzbdav-og", bool(pv) and set(pv) == {conns} and str(dl) == str(conns),
       "provider MaxConnections=%s max-download-connections=%s" % (pv, dl))

if bad:
    print("   PARITY VERIFICATION FAILED: %s -- do not run the round" % ", ".join(bad))
    sys.exit(1)
print("   all five targets verified at %d NNTP connections" % conns)
PY

echo "PREP_R7_DONE"
