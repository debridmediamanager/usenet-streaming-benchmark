#!/bin/bash
# Run only task-owned builds/workloads. Secrets never appear in arguments/output.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
export BENCH=/home/ben/bench-round13-20261001 CONNS=10 GOMAXPROCS=2
case "${1:-}" in
build)
  bash "$HERE/prep-r13.sh" build
  python3 "$HERE/prep_aiostreams_r13.py" build
  ;;
verify)
  python3 "$HERE/test_r10.py"
  python3 "$HERE/test_r13.py"
  bash -n "$HERE/prep-r13.sh" "$HERE/zen-r13.sh"
  ;;
bootstrap)
  bash "$HERE/prep-r13.sh" bootstrap
  7z x -pdmmbench -y -o"$REPO/corpus" "$REPO/corpus/corpus.7z"
  ;;
smoke|run)
  set -a
  source /home/ben/.config/zurg/bench-account.env
  set +a
  export NNTP_HOST="${BENCH_NNTP_HOST:?}" NNTP_PORT="${BENCH_NNTP_PORT:?}"
  export NNTP_USER="${BENCH_NNTP_USER:?}" NNTP_PASS="${BENCH_NNTP_PASS:?}"
  [[ "$NNTP_HOST" == newswest.frugalusenet.com && "$NNTP_PORT" == 563 ]] || { echo 'Wrong designated provider' >&2; exit 1; }
  mode="$1"
  shift
  if [[ "$mode" == smoke ]]; then
    sudo -n --preserve-env=BENCH,CONNS,GOMAXPROCS,NNTP_HOST,NNTP_PORT,NNTP_USER,NNTP_PASS \
      python3 "$HERE/run_r13.py" --smoke "$@"
  else
    sudo -n --preserve-env=BENCH,CONNS,GOMAXPROCS,NNTP_HOST,NNTP_PORT,NNTP_USER,NNTP_PASS \
      python3 "$HERE/run_r13.py" "$@"
  fi
  ;;
*) echo 'Usage: zen-r13.sh build|verify|bootstrap|smoke|run [--out PATH]' >&2; exit 2 ;;
esac
