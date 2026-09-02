#!/bin/bash
# Round 7, run in one chain. Every target holds 20 NNTP connections to
# news.news-provider.example and repair is on wherever the feature exists, so
# for the first time the five differ only in the software.
#
# One server alive at a time throughout -- bench5.start/stop enforces it and
# every phase below routes through that. Order is fixed: the library has to
# exist before it can be read, throughput has to run before the behaviour
# phases add duplicate releases to the listings.
cd /home/ben/bench
T=zurg,decypharr,altmount,infinidysk,nzbdav-og
say () { echo "=== $1 $(date -u +%FT%TZ) ==="; }

say "TREE/SEED start"
python3 tree_r7.py > r7/tree_r7.log 2>&1
say "TREE/SEED done"

say "THROUGHPUT start"
python3 bench5.py six7 256 1500000000 0.8 6 $T > six7.log 2>&1
say "THROUGHPUT done"

say "BYTEID start"
python3 byteid_r7.py $T > byteid.log 2>&1
say "BYTEID done"

say "LATENCY start"
python3 phase2_5r7.py $T > latency_r7.log 2>&1
say "LATENCY done"

for phase in damage obfuscated rar; do
  say "$phase start"
  python3 corpus5b.py $phase $T > ${phase}.r7.log 2>&1
  say "$phase done"
done

say "REPROBE start"
python3 reprobe_r7.py > reprobe_r7.log 2>&1
say "REPROBE done"

say "TIMELINE start"
python3 damage_timeline_r7.py > damage_timeline_r7.log 2>&1
say "ROUND 7 DONE"
