#!/bin/bash
# Round 10, the whole suite, one command.
#
#   ./chain10.sh                        every target, every entry
#   ./chain10.sh --disable comet        everything except comet
#   ./chain10.sh --only raw,zurg        just those two
#   CONNS=20 ./chain10.sh               a different connection budget
#
# Every flag is passed straight through to run_r10.py, so --entries, --reps and
# --tag work here too.
#
# Order is not arbitrary. The corpus has to exist before the negative tier can
# be derived from it, the noise floor has to be measured before any difference
# between two targets can be called real, and the main pass has to finish before
# there is anything to report on.
#
# One target is alive at a time throughout. bench5.start/stop enforces it and
# every phase below routes through that.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
CONNS="${CONNS:-15}"
TAG="${TAG:-r10}"
OUT="${OUT:-$REPO/results/round10}"

say () { echo "=== $1 $(date -u +%FT%TZ) ==="; }
die () { echo "!! $1" >&2; exit 1; }

mkdir -p "$OUT"

# ---------------------------------------------------------------- corpus
say "CORPUS check"
if ! ls "$REPO"/corpus/*.nzb >/dev/null 2>&1; then
  say "extracting corpus"
  command -v 7z >/dev/null || die "7z not found, and corpus/*.nzb is not extracted"
  7z x -pdmmbench -y -o"$REPO/corpus" "$REPO/corpus/corpus.7z" >/dev/null \
    || die "corpus extraction failed"
fi

say "DERIVE negative tier"
python3 "$HERE/corpus_r10.py" derive > "$OUT/derived.json" 2>&1 \
  || die "negative-tier derivation failed, see $OUT/derived.json"

# ---------------------------------------------------------------- field
say "FIELD"
python3 "$HERE/run_r10.py" --list "$@" > "$OUT/field.json" 2>&1 \
  || die "target selection failed, see $OUT/field.json"
python3 - "$OUT/field.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print("  running:  " + ", ".join(data["running"]))
if data["disabled"]:
    print("  disabled: " + ", ".join(data["disabled"]))
if data["shakedown"]:
    print("  UNPROVEN: " + ", ".join(data["shakedown"])
          + "  (adapters that have not survived a run)")
missing = [e["id"] for e in data["corpus"] if not e["available"]]
if missing:
    print("  no post:  " + ", ".join(missing))
PY

# ---------------------------------------------------------- noise floor
# Two identical passes over one entry, before anything else. Without this the
# report can say "provider throughput drifts" and still print a 12% gap as if
# it meant something.
say "NOISE FLOOR pass A"
python3 "$HERE/run_r10.py" --entries plain-video --conns "$CONNS" \
  --tag "${TAG}-noise-a" --out "$OUT/noise_a.json" "$@" \
  > "$OUT/noise_a.log" 2>&1 || say "noise pass A failed, see $OUT/noise_a.log"

say "NOISE FLOOR pass B"
python3 "$HERE/run_r10.py" --entries plain-video --conns "$CONNS" \
  --tag "${TAG}-noise-b" --out "$OUT/noise_b.json" "$@" \
  > "$OUT/noise_b.log" 2>&1 || say "noise pass B failed, see $OUT/noise_b.log"

# ------------------------------------------------------------- main pass
say "MAIN PASS start"
python3 "$HERE/run_r10.py" --conns "$CONNS" --tag "$TAG" \
  --out "$OUT/results_${TAG}.json" "$@" \
  > "$OUT/run_${TAG}.log" 2>&1 || say "main pass exited non-zero, see the log"
say "MAIN PASS done"

# ---------------------------------------------------------------- report
say "REPORT"
R10_HARNESS="$HERE" python3 - "$OUT/results_${TAG}.json" "$OUT/noise_a.json" \
         "$OUT/noise_b.json" "$OUT/report.md" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["R10_HARNESS"])
import report_r10 as report

main = json.load(open(sys.argv[1]))
rows = main["rows"]
parts = ["# Round 10", "",
         "Field: " + ", ".join(main["field"]),
         "", f"Connections: {main['connections']}", ""]
if main.get("disabled"):
    parts += ["Disabled for this run: " + ", ".join(main["disabled"]), ""]

parts.append(report.render_headline(main["throughput"], "Sequential throughput",
                                    unit=" MB/s", lower_is_better=False))
parts.append("")
parts.append(report.render_headline(main["cold_open"], "Cold open",
                                    unit=" s", lower_is_better=True))
parts.append("")
parts.append(report.render_consensus(main["consensus"]))
parts.append("")

try:
    a = json.load(open(sys.argv[2]))["rows"]
    b = json.load(open(sys.argv[3]))["rows"]
    floor = report.noise_floor(a, b)
    parts += ["### Noise floor", "",
              "Two identical passes, nothing changed but the clock. A difference "
              "between two targets smaller than the worst swing here is not "
              "resolved by one pass.", "",
              f"- whole-run median shift: {floor.get('whole_run_median_shift_pct')}%",
              f"- worst per-entry swing: {floor.get('per_entry_worst_pct')}%", ""]
except Exception as exc:
    parts += ["### Noise floor", "",
              f"Not measured this run: {type(exc).__name__}.", ""]

parts += ["### Capability", "",
          "```", json.dumps(main["capability"], indent=1), "```", ""]
if main.get("shakedown"):
    parts += ["### Unproven adapters", "",
              "These have not survived a run and their rows are suspect until "
              "they have: " + ", ".join(main["shakedown"]) + ".", ""]

open(sys.argv[4], "w").write("\n".join(parts))
print(f"wrote {sys.argv[4]}")
PY

say "ROUND 10 DONE"
echo
echo "  results:  $OUT/results_${TAG}.json"
echo "  report:   $OUT/report.md"
echo "  logs:     $OUT/*.log"
