#!/bin/bash
# Round-6 prep: install the r6 builds, point every target at the designated
# bench news server, give each target its own copy of the 5-NZB corpus, and
# create the two container targets on their r6 images.
#
# The news host is set once here for every target, so all five read the same
# backbone server. Which server that is changes nothing about layout, but it
# does change STAT latency, and round 6 measured that separately because
# AltMount's import check is sensitive to it. See results/round6/statlat.txt.
set -eu
BENCH=/home/ben/bench
OUT=$BENCH/src/out
CORPUS="ToyStory5.nzb ToyStory5Damaged.nzb Obfuscated.nzb FatherBrown.nzb Bosch.S01.nzb"
HOST=news.news-provider.example
IC=$(cd $BENCH/src/infinidysk-git && git rev-parse --short=8 HEAD)
NC=$(cd $BENCH/src/nzbdav-git && git rev-parse --short=8 HEAD)

echo "== binaries =="
cp -f $BENCH/zurgrun/zurg $BENCH/zurgrun/zurg.r5.bak 2>/dev/null || true
cp -f $OUT/zurg-r6 $BENCH/zurgrun/zurg
cp -f $BENCH/altmount/altmount-cli-linux-amd64 $BENCH/altmount/altmount-cli.r5.bak 2>/dev/null || true
cp -f $OUT/altmount-r6 $BENCH/altmount/altmount-cli-linux-amd64
cp -f $BENCH/decypharr $BENCH/decypharr.r5.bak 2>/dev/null || true
cp -f $OUT/decypharr-r6 $BENCH/decypharr
chmod +x $BENCH/zurgrun/zurg $BENCH/altmount/altmount-cli-linux-amd64 $BENCH/decypharr
for b in "$BENCH/zurgrun/zurg --version" "$BENCH/decypharr --version"; do
  echo "-- $b"; timeout 20 $b 2>&1 | head -3 || true
done

echo "== corpus per target =="
for t in zurg altmount infinidysk nzbdav-og decypharr; do
  mkdir -p $BENCH/r6-nzbs/$t
  for n in $CORPUS; do cp -f $BENCH/nzbs/$n $BENCH/r6-nzbs/$t/$n; done
  echo "   $t: $(ls $BENCH/r6-nzbs/$t | wc -l) nzbs"
done

echo "== news host -> $HOST =="
sed -i "s/news\.news-provider\.example/$HOST/g" $BENCH/zurgrun/config.yml
sed -i "s/news\.news-provider\.example/$HOST/g" $BENCH/altmount/config.yaml
sed -i "s/news\.news-provider\.example/$HOST/g" $BENCH/decyrun/config.json
grep -h "$HOST" $BENCH/zurgrun/config.yml $BENCH/altmount/config.yaml $BENCH/decyrun/config.json | sed 's/^ */   /'

echo "== container targets =="
mkdir -p $BENCH/infinidysk/config-r6 $BENCH/nzbdav-og/config-r6
docker rm -f infinidysk-r6 nzbdav-r6 >/dev/null 2>&1 || true

docker run -d --name infinidysk-r6 --network host --restart no \
  -v $BENCH/infinidysk/config-r6:/config \
  -v $BENCH/r6-nzbs/infinidysk:/nzbs:ro \
  -e PORT=3001 \
  -e ASPNETCORE_URLS=http://127.0.0.1:8092 \
  -e BACKEND_URL=http://127.0.0.1:8092 \
  -e CONFIG_PATH=/config \
  -e LOG_LEVEL=warning \
  -e NZBDAV_CONFIG__USENET__PROVIDERS="{\"Providers\":[{\"ProviderId\":\"11111111-2222-3333-4444-555555555555\",\"Type\":1,\"Host\":\"$HOST\",\"Port\":563,\"UseSsl\":true,\"SkipTlsVerification\":false,\"User\":\"YOUR_USENET_USERNAME\",\"Pass\":\"YOUR_USENET_PASSWORD\",\"MaxConnections\":50,\"MaxTransferConnections\":20,\"Priority\":0,\"StorageGroup\":\"\",\"BytesUsedOffset\":0,\"BytesUsedResetAt\":0}]}" \
  -e NZBDAV_CONFIG__USENET__QUEUE_PIPELINING__ENABLED=true \
  -e NZBDAV_CONFIG__USENET__QUEUE_PIPELINING__DEPTH=4 \
  -e NZBDAV_CONFIG__REPAIR__ENABLE=true \
  -e NZBDAV_CONFIG__REPAIR__PAR2_ENABLED=true \
  -e NZBDAV_CONFIG__WEBDAV__USER=usenet \
  -e NZBDAV_CONFIG__WEBDAV__PASS=usenet \
  -e NZBDAV_CONFIG__API__KEY=benchbenchbenchbenchbenchbench12 \
  -e NZBDAV_CONFIG__API__COMPLETED_DOWNLOADS_DIR=/completed \
  infinidysk:r6-$IC >/dev/null
echo "   infinidysk-r6 on infinidysk:r6-$IC"

docker run -d --name nzbdav-r6 --network host --restart no \
  -v $BENCH/nzbdav-og/config-r6:/config \
  -v $BENCH/r6-nzbs/nzbdav-og:/nzbs \
  -e PORT=3002 \
  -e CONFIG_PATH=/config \
  -e BACKEND_URL=http://127.0.0.1:8093 \
  -e ASPNETCORE_URLS=http://127.0.0.1:8093 \
  -e WEBDAV_USER=usenet \
  -e WEBDAV_PASSWORD=usenet \
  -e LOG_LEVEL=warning \
  nzbdav:r6-$NC >/dev/null
echo "   nzbdav-r6 on nzbdav:r6-$NC"

sleep 25
for p in 8092 8093; do
  echo -n "   :$p health -> "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 http://127.0.0.1:$p/health || echo fail
done
docker stop infinidysk-r6 nzbdav-r6 >/dev/null
echo "PREP_R6_DONE"
