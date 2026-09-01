#!/bin/bash
# Fix the round-6 corpus: one copy per target (several targets consume or move
# the NZB they import, so a shared directory would leave later targets short)
# and one corpus.txt that the run and the report both read.
set -eu
BENCH=/home/ben/bench
mkdir -p $BENCH/r6
: > $BENCH/r6/corpus.txt
for t in zurg altmount infinidysk nzbdav-og decypharr; do
  rm -rf $BENCH/r6-nzbs/$t
  mkdir -p $BENCH/r6-nzbs/$t
done
for n in "$@"; do
  src=""
  for d in nzbs tvnzbs newnzbs og-nzbs id-nzbs am-nzbs; do
    [ -f "$BENCH/$d/$n" ] && { src="$BENCH/$d/$n"; break; }
  done
  [ -n "$src" ] || { echo "MISSING $n"; exit 1; }
  for t in zurg altmount infinidysk nzbdav-og decypharr; do
    cp -f "$src" "$BENCH/r6-nzbs/$t/$n"
  done
  echo "$n" >> $BENCH/r6/corpus.txt
  echo "  $n <- $src  ($(stat -c%s "$src") bytes)"
done
echo "-- corpus.txt --"; cat $BENCH/r6/corpus.txt
for t in zurg altmount infinidysk nzbdav-og decypharr; do
  echo "  $t: $(ls $BENCH/r6-nzbs/$t | tr '\n' ' ')"
done
