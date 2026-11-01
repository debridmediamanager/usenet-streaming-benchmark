#!/bin/bash
# Run a round on a freshly provisioned Hetzner box, then destroy it.
#
#   ./harness/hetzner-round.sh                       # a full round at CONNS
#   CONNS=15 ./harness/hetzner-round.sh
#   ./harness/hetzner-round.sh --type ccx33
#   ./harness/hetzner-round.sh --selftest            # provision + tear down only
#   ./harness/hetzner-round.sh --keep                # leave the box up, deliberately
#
# The teardown runs from a trap, so an error, a failed run, a Ctrl-C or a
# dropped connection still destroys the server. Doing this by hand works right
# up until the run crashes at 04:00 and the box bills until somebody notices.
#
# The box borrows the benchmark account's reserved Primary IPv4 and gets no
# IPv6 (harness/hetzner-box.sh): a Usenet account is only ever used from one
# public IP, so teardown deletes the server, never that IP, and verifies both.

# Credentials come from the environment and nothing here is written to disk:
#   NNTP_HOST NNTP_PORT NNTP_USER NNTP_PASS   the news account
#   BENCH_SOURCE                              host holding built targets, e.g. me@buildbox
# hcloud must already be configured (`hcloud context list`).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"

TYPE="${HETZNER_TYPE:-ccx23}"
IMAGE="${HETZNER_IMAGE:-ubuntu-24.04}"
LOCATION="${HETZNER_LOCATION:-nbg1}"
SSH_KEY="${HETZNER_SSH_KEY:-}"
CONNS="${CONNS:-15}"
SOURCE="${BENCH_SOURCE:-}"
NAME="${HETZNER_NAME:-bench-round-$(date -u +%Y%m%d-%H%M%S)}"
OUT="${OUT:-$REPO/results/round-hetzner-$(date -u +%Y%m%d-%H%M%S)}"
KEEP=""
SELFTEST=""

while [ $# -gt 0 ]; do
  case "$1" in
    --type) TYPE="$2"; shift 2 ;;
    --conns) CONNS="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    # the smallest type in the same family as the real one: shared-vCPU types
    # are not offered in every location, and a self-test that cannot provision
    # tests nothing
    --selftest) SELFTEST=1; TYPE="${HETZNER_SELFTEST_TYPE:-ccx13}"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

. "$HERE/hetzner-box.sh"
say () { box_say "$@"; }
die () { box_die "$@"; }

command -v hcloud >/dev/null || die "hcloud is not installed"
hcloud context list >/dev/null 2>&1 || die "hcloud has no configured context"

if [ -z "$SSH_KEY" ]; then
  SSH_KEY=$(hcloud ssh-key list -o noheader -o columns=name | head -1)
  [ -n "$SSH_KEY" ] || die "no ssh key registered with hcloud, and none given"
fi

trap box_teardown EXIT INT TERM
box_provision

if [ -n "$SELFTEST" ]; then
  say "SELFTEST: provisioned, reachable, and about to be destroyed"
  ssh_to 'echo "   remote says: $(hostname), $(nproc) cores"'
  exit 0
fi

# --------------------------------------------------------------------- deps
# libstdc++6 is not optional. AltMount links it through the C++ in
# gopar-turbo, and on this image a missing shared library surfaces much
# later as a target that never became ready, rather than as a missing package.
say "INSTALL dependencies"
ssh_to 'export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq >/dev/null 2>&1
        apt-get install -y -qq p7zip-full curl ffmpeg lsof rsync git jq fuse3 \
                              libstdc++6 >/dev/null 2>&1
        curl -fsSL https://get.docker.com | sh >/dev/null 2>&1
        python3 -V' || die "dependency install failed"

say "COPY harness"
rsync -a --exclude .git --exclude results "$REPO/" "root@$IP:/root/usenet-streaming-benchmark/"

# ------------------------------------------------------------------- targets
# The built targets come from a host that already has them, so the round
# measures the same binaries as the round it is being compared with. Building
# from current main on the day makes a host comparison and a software change
# arrive together, which is what made round 8 impossible to read.
[ -n "$SOURCE" ] || die "BENCH_SOURCE is not set: no host to take built targets from"
say "COPY targets from $SOURCE"
ssh_to "mkdir -p /root/bench/{zurgrun,altmount,decyrun,infinidysk,nzbdav-og/config,bin}"
ssh "$SOURCE" "tar -C \$HOME/bench -cf - \
    zurgrun/zurg zurgrun/config.yml \
    altmount/altmount-cli-linux-amd64 altmount/config.yaml \
    decypharr decyrun/config.json nzbdav-og/config/db.sqlite bin/rclone" \
  | ssh_to "tar -C /root/bench -xf -"
# prep-r10.sh starts the two .NET targets from the newest `infinidysk:r7-*` and
# `nzbdav:r7-*` on the box, so those are the two tags that have to arrive. Taking
# "the first two lines matching either name" instead can send two tags of the
# SAME project: a build host carries r5, r6 and r7 tags of both, and which two
# come out first is decided by build order. The round then dies on the far side
# with "no infinidysk image built", after the provisioning and the copy have
# already been paid for. Resolve each by name here and assert both before
# anything crosses the wire.
IMG_ID=$(ssh "$SOURCE" "docker images --format '{{.Repository}}:{{.Tag}}' | grep -m1 '^infinidysk:r7-'")
IMG_ND=$(ssh "$SOURCE" "docker images --format '{{.Repository}}:{{.Tag}}' | grep -m1 '^nzbdav:r7-'")
[ -n "$IMG_ID" ] || die "$SOURCE has no infinidysk:r7-* image. build-r7.sh has not run there"
[ -n "$IMG_ND" ] || die "$SOURCE has no nzbdav:r7-* image. build-r7.sh has not run there"
echo "   $IMG_ID and $IMG_ND"
ssh "$SOURCE" "docker save '$IMG_ID' '$IMG_ND' | gzip -1" \
  | ssh_to 'gunzip | docker load' >/dev/null
ssh_to 'chmod +x /root/bench/zurgrun/zurg /root/bench/decypharr \
                 /root/bench/altmount/altmount-cli-linux-amd64 /root/bench/bin/rclone 2>/dev/null
        docker images --format "   image {{.Repository}}:{{.Tag}}"'

say "REWRITE configs for this host at $CONNS connections"
ssh_to "CONNS=$CONNS python3 /root/usenet-streaming-benchmark/harness/rehost-configs.py /root/bench" \
  || die "config rewrite failed"

# ----------------------------------------------------------------------- run
say "RUN the round"
ssh_to "cd /root/usenet-streaming-benchmark && \
        NNTP_HOST='${NNTP_HOST:?}' NNTP_PORT='${NNTP_PORT:-563}' \
        NNTP_USER='${NNTP_USER:?}' NNTP_PASS='${NNTP_PASS:?}' \
        BENCH=/root/bench CONNS=$CONNS \
        ./harness/chain10.sh ${R10_ARGS:-}" || echo "!! the round exited non-zero; results are still collected"

# ------------------------------------------------------------------- results
# Before teardown, always. The results exist only on that disk, and the disk is
# about to stop existing.
say "COLLECT results into $OUT"
mkdir -p "$OUT"
if ! rsync -a "root@$IP:/root/usenet-streaming-benchmark/results/round10/" "$OUT/"; then
  # Keep the machine. Destroying it here would throw away the only copy of a
  # run that has just cost hours, to save a few cents -- and `die` alone would
  # do exactly that, because the teardown trap fires on the way out.
  KEEP=1
  die "could not collect results. The server is DELIBERATELY left up at $IP so
    the run is not lost. Collect by hand, then: hcloud server delete $NAME"
fi
echo "   $(find "$OUT" -type f | wc -l) files collected"

say "DONE"
