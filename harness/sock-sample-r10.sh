#!/bin/bash
# Per-target NNTP socket census for the whole round, sampled every 5 s.
#
# Configuration has been wrong before, which is why parity is confirmed from
# live sockets and not from what the config files claim. Round 9 established
# the method: sample continuously for the whole run, then take per-pid ESTAB
# maxima inside each phase window, separating bench pids from production ones
# by their working directory.
#
# That last part has to happen HERE. A pid is gone by the time the run ends, so
# a census that records only pid numbers cannot be classified afterwards -- the
# owner has to be resolved while the process still exists.
#
#   sockets.tsv       timestamp, state, pid          one row per socket
#   sockets-pids.tsv  pid, comm, cwd                 one row per pid, once
out_dir=${OUT:-$HOME/usenet-streaming-benchmark/results/round10}
out=${SOCKETS_OUT:-$out_dir/sockets.tsv}
owners=${SOCKET_OWNERS_OUT:-$out_dir/sockets-pids.tsv}
mkdir -p "$(dirname "$out")"
: >> "$out"
: >> "$owners"

declare -A seen
while read -r pid _; do
  [ -n "$pid" ] && seen["$pid"]=1
done < "$owners"

# Sample until told to stop, rather than while a particular process exists.
# Keying the loop on "is the chain running" meant starting the sampler during
# the prep phase -- before the chain exists -- exited it immediately, and the
# census for that round was empty when it came time to prove parity.
stop=${SOCKETS_STOP_FILE:-$HOME/stop-sock-sampler}
rm -f "$stop"
while [ ! -f "$stop" ]; do
  now=$(date -u +%FT%TZ)
  ss -tnp 2>/dev/null | awk -v t="$now" '
    $5 ~ /:563$/ {
      pid = "?"
      if (match($0, /pid=[0-9]+/)) pid = substr($0, RSTART + 4, RLENGTH - 4)
      print t "\t" $1 "\t" pid
    }' >> "$out"

  # resolve any pid not seen before, while it is still alive
  for pid in $(awk -v t="$now" '$1 == t {print $3}' "$out" | sort -u); do
    [ "$pid" = "?" ] && continue
    [ -n "${seen[$pid]:-}" ] && continue
    seen["$pid"]=1
    comm=$(cat "/proc/$pid/comm" 2>/dev/null || echo unknown)
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || echo unknown)
    printf '%s\t%s\t%s\n' "$pid" "$comm" "$cwd" >> "$owners"
  done

  sleep 5
done

echo "sampler-done	$(date -u +%FT%TZ)	-" >> "$out"
