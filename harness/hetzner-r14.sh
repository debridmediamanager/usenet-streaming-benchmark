#!/bin/bash
# Round 14 on a Hetzner ccx23 attached to the benchmark account's reserved IP.
#
#   harness/hetzner-r14.sh up          provision, install, copy the harness and the account
#   harness/hetzner-r14.sh census      is the corpus on this provider as built? (gate)
#   harness/hetzner-r14.sh build       pinned sources from config/round14-existing.json
#   harness/hetzner-r14.sh verify      the harness's own tests, on the box
#   harness/hetzner-r14.sh smoke       plain-video on every target -> results/round14/preflight
#   harness/hetzner-r14.sh run         noise_a, noise_b, main -> results/round14
#   harness/hetzner-r14.sh aio-nocache AIOStreams' main pass again with its disk segment
#                                      cache off, beside raw -> results/round14/aiostreams-nocache
#   harness/hetzner-r14.sh status      the last step's state and log tail
#   harness/hetzner-r14.sh collect     pull results/round14 back
#   harness/hetzner-r14.sh down        delete the server, keep and verify the IP
#
# A round runs for hours and an ssh session from a laptop does not, so every
# remote step runs as a transient systemd unit that outlives the session, and
# `status` reads it with a fresh connection. Phases instead of one trap-guarded
# script means nothing tears the box down by itself: run `down` when finished.
#
# The account (NNTP_USER, NNTP_PASS) is read here from the environment and
# written on the box only, mode 600, through ssh stdin; it never appears in a
# command line, and it dies with the box.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
NAME="${HETZNER_NAME:-bench-round14}"
TYPE="${HETZNER_TYPE:-ccx23}"
IMAGE="${HETZNER_IMAGE:-ubuntu-24.04}"
LOCATION="${HETZNER_LOCATION:-nbg1}"
SSH_KEY="${HETZNER_SSH_KEY:-$(hcloud ssh-key list -o noheader -o columns=name | head -1)}"
REMOTE=/root/usenet-streaming-benchmark
. "$HERE/hetzner-box.sh"

attach () {
  local want assignee
  SERVER_ID=$(hcloud server describe "$NAME" -o format='{{.ID}}' 2>/dev/null) || box_die "no server $NAME; run up"
  read -r RESERVED_IP_ID want assignee <<<"$(hcloud primary-ip describe "$RESERVED_IP" -o format='{{.ID}} {{.IP}} {{.AssigneeID}}')"
  [ "$assignee" = "$SERVER_ID" ] || box_die "$NAME is not on the reserved IP $want"
  IP=$want
}

# run one step on the box as a unit that survives this ssh session
remote_step () {
  local step="$1" cmd="$2"
  # two steps that dial the account at once would share its connections and
  # measure each other; a build or a test run dials nothing and may overlap
  local dialing='r14-census.service|r14-smoke.service|r14-run.service|r14-aio-nocache.service'
  ssh_to "systemctl is-active --quiet 'r14-$step' && { echo 'r14-$step is still running'; exit 1; }
          case '$step' in census|smoke|run|aio-nocache)
            systemctl list-units 'r14-*' --state=active --no-legend | grep -Eq '$dialing' \
              && { echo 'a step that dials the account is still running:'; systemctl list-units 'r14-*' --no-legend; exit 1; };;
          esac
          systemd-run --unit 'r14-$step' --collect -p WorkingDirectory=$REMOTE \
            -p StandardOutput=append:/root/r14-$step.log -p StandardError=append:/root/r14-$step.log \
            bash -euc 'set -a; . /root/.bench-account.env; set +a
                       export ROUND=r14 BENCH=/root/bench-round14 CONNS=10 GOMAXPROCS=4
                       echo \"== $step start \$(date -u +%FT%TZ)\"
                       $cmd
                       echo \"== $step done \$(date -u +%FT%TZ)\"'
          echo 'started r14-$step; follow with: harness/hetzner-r14.sh status'"
}

case "${1:-}" in
up)
  [ -n "${NNTP_USER:-}" ] && [ -n "${NNTP_PASS:-}" ] || box_die "set NNTP_USER and NNTP_PASS"
  [ -f "$REPO/config/round14-existing.json" ] || box_die "config/round14-existing.json is missing"
  box_provision
  box_say "INSTALL dependencies"
  # libstdc++6: AltMount links it through gopar-turbo; missing, it surfaces
  # much later as a target that never became ready.
  ssh_to 'export DEBIAN_FRONTEND=noninteractive
          apt-get update -qq >/dev/null && apt-get install -y -qq p7zip-full curl ffmpeg lsof rsync git jq \
            fuse3 libstdc++6 iproute2 >/dev/null
          curl -fsSL https://get.docker.com | sh >/dev/null 2>&1
          docker version --format "   docker {{.Server.Version}}"; python3 -V'
  box_say "COPY harness"
  rsync -a --exclude .git --exclude results "$REPO/" "root@$IP:$REMOTE/"
  # %q: the file is sourced, and a password may hold $, quotes or spaces
  printf 'NNTP_HOST=%q\nNNTP_PORT=%q\nNNTP_USER=%q\nNNTP_PASS=%q\n' \
    news.bulknews.eu 563 "$NNTP_USER" "$NNTP_PASS" \
    | ssh_to 'umask 077; cat > /root/.bench-account.env'
  box_say "UP: $NAME at $IP. Next: harness/hetzner-r14.sh census"
  ;;
census)  attach; remote_step census "7z x -pdmmbench -y -ocorpus corpus/corpus.7z >/dev/null
                                     mkdir -p results/round14
                                     python3 harness/census_r14.py corpus results/round14/corpus-census.json" ;;
build)
  attach
  # zurg's repository is private, so the box cannot clone it. Its pinned
  # revision goes over as a bundle and becomes the checkout prep-r13.sh
  # verifies (exact revision, clean tree) like any other source.
  rev=$(python3 -c "import json;print(json.load(open('$REPO/config/round14-existing.json'))['zurg']['revision'])")
  src="${ZURG_SRC:-$REPO/../zurg}"
  git -C "$src" cat-file -e "$rev^{commit}" || box_die "$src does not have zurg $rev; git fetch there"
  # bundled from a throwaway repo, so the local checkout's refs are never touched
  tmp=$(mktemp -d); git init -q --bare "$tmp/pin.git"
  git -C "$tmp/pin.git" fetch -q "$src" "+refs/remotes/origin/*:refs/remotes/origin/*"
  git -C "$tmp/pin.git" branch bench-r14-pin "$rev"
  git -C "$tmp/pin.git" bundle create "$tmp/zurg.bundle" bench-r14-pin 2>/dev/null
  rsync -a "$tmp/zurg.bundle" "root@$IP:/root/zurg.bundle"; rm -rf "$tmp"
  ssh_to "[ -d /root/bench-round14/src/zurg ] || { mkdir -p /root/bench-round14/src
          git clone -q -b bench-r14-pin /root/zurg.bundle /root/bench-round14/src/zurg; }
          git -C /root/bench-round14/src/zurg rev-parse HEAD"
  remote_step build "bash harness/prep-r13.sh build
                                    python3 harness/prep_aiostreams_r13.py build
                                    bash harness/prep-r13.sh bootstrap" ;;
verify)  attach; remote_step verify "python3 harness/test_r10.py; python3 harness/test_r13.py; python3 harness/test_hetzner.py" ;;
smoke)   attach; remote_step smoke "python3 harness/run_r13.py --smoke --out results/round14/preflight" ;;
run)     attach; remote_step run "python3 harness/run_r13.py --out results/round14" ;;
aio-nocache)
  # Rounds 13 and 14 gave only AIOStreams a disk cache large enough to hold a
  # release, and three corpus entries share one release's articles. This reruns
  # its main pass with that cache at 0, AltMount's and InfiniDysk's setting.
  attach; remote_step aio-nocache "[ -f corpus/ToyStory5.nzb ] || 7z x -pdmmbench -y -ocorpus corpus/corpus.7z >/dev/null
    export AIOSTREAMS_SEGMENT_DISK_CACHE_BYTES=0
    python3 harness/run_r13.py --targets raw,aiostreams --main-only --out results/round14/aiostreams-nocache" ;;
status)
  attach
  ssh_to 'systemctl list-units "r14-*" --all --no-legend || true
          for f in $(ls -t /root/r14-*.log 2>/dev/null | head -1); do echo "-- $f"; tail -n "${LINES:-25}" "$f"; done'
  ;;
collect)
  attach
  mkdir -p "$REPO/results/round14"
  rsync -a "root@$IP:$REMOTE/results/round14/" "$REPO/results/round14/"
  rsync -a "root@$IP:/root/r14-*.log" "$REPO/results/round14/logs/" 2>/dev/null || true
  echo "   $(find "$REPO/results/round14" -type f | wc -l) files in results/round14"
  ;;
down)
  attach
  trap box_teardown EXIT
  ;;
*) sed -n 2,13p "$0" >&2; exit 2 ;;
esac
