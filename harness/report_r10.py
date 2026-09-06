#!/usr/bin/env python3
"""Turning round-10 measurements into numbers that can be quoted.

Three corrections to how rounds 3 through 9 reported.

**Medians were taken over whatever each target survived.** A target that fails
the large entries is otherwise credited with the fast medians of the small ones
it did serve, and import time scales with post size, so failing more can make a
target look quicker. Every headline median here is taken over one fixed
population -- the entries at least `SHARED_THRESHOLD` of the field served -- and
a target that missed one of them shows it as `n`. The strict intersection is
deliberately not used: it is defined by the weakest engine in the field, so one
broken target collapses the population for everybody and the set moves between
runs. Each target's own-set median is published alongside, with the gap between
the two, rather than hidden.

**Byte identity was asserted, not established.** Round 7 hashed the behaviour
releases, all five agreed, and the check therefore never had a chance to find
anything; the throughput reads went to /dev/null and were never hashed at all.
Here every target hashes the same ranges and the hashes are compared against
each other, with the consensus being whatever at least two targets agree on. A
fast target serving the wrong bytes is not fast.

**Run-to-run noise was described and never measured.** "Provider throughput
drifts" is true and it is not a number, so nothing said which differences a
round could actually resolve. `noise_floor` compares two identical passes and
reports the spread, which is what licenses a claim about a gap between two
targets or refuses it.
"""
import json
import statistics

SHARED_THRESHOLD = 0.90


# --------------------------------------------------------------------------
# population-fixed medians
# --------------------------------------------------------------------------
def shared_population(rows, targets=None, threshold=SHARED_THRESHOLD):
    """Entries that at least `threshold` of the field served.

    Returns (entries, detail). `detail` carries the served counts so a report can
    say why an entry is in or out rather than presenting the set as given.
    """
    targets = sorted(set(targets or [r["target"] for r in rows]))
    # the negative tier is scored on outcome, never on rate, so it has no place
    # in a population the medians are taken over
    rows = [r for r in rows if r.get("tier") != "negative"]
    entries = sorted({r["entry"] for r in rows})
    detail = {}
    keep = []
    for entry in entries:
        served = {r["target"] for r in rows
                  if r["entry"] == entry and r.get("served")}
        share = len(served) / len(targets) if targets else 0
        detail[entry] = {"served_by": len(served), "of": len(targets),
                         "share": round(share, 3), "in_population": share >= threshold}
        if share >= threshold:
            keep.append(entry)
    return keep, detail


def _values(rows, target, field, entries=None):
    """Performance values from the entries a target was supposed to serve.

    A row from the negative tier never counts, even when the target served it.
    Those entries are unservable by construction, so whatever came back is not
    a delivery of the content: on the first full round, zurg answered a release
    stripped of two thirds of its articles at 45.58 MB/s by zero-filling the
    gaps, and counting that lifted its throughput median. A target must not be
    credited for the speed of serving silence.
    """
    out = []
    for row in rows:
        if row["target"] != target or not row.get("served"):
            continue
        if row.get("tier") == "negative":
            continue
        if entries is not None and row["entry"] not in entries:
            continue
        value = row.get(field)
        if value is not None:
            out.append(value)
    return out


def headline(rows, field, targets=None, threshold=SHARED_THRESHOLD):
    """Per-target median of `field` over one fixed population, with n and the gap.

    `own_median` is the same statistic over whatever that target served. When the
    two disagree the target is being flattered or punished by its own failures,
    and `gap_pct` is how much.
    """
    targets = sorted(set(targets or [r["target"] for r in rows]))
    population, detail = shared_population(rows, targets, threshold)
    out = {"field": field, "population": population,
           "population_size": len(population), "population_detail": detail,
           "threshold": threshold, "targets": {}}
    for target in targets:
        shared = _values(rows, target, field, population)
        own = _values(rows, target, field)
        row = {"n": len(shared), "of": len(population)}
        if shared:
            row["median"] = round(statistics.median(shared), 4)
        if own:
            row["own_median"] = round(statistics.median(own), 4)
            row["own_n"] = len(own)
        if row.get("median") and row.get("own_median"):
            row["gap_pct"] = round(
                100.0 * (row["own_median"] - row["median"]) / row["median"], 1)
        if shared and len(shared) < len(population):
            row["incomplete"] = (f"missed {len(population) - len(shared)} of the "
                                 f"shared population")
        out["targets"][target] = row
    return out


# --------------------------------------------------------------------------
# byte-identity consensus
# --------------------------------------------------------------------------
def consensus(rows, exclude=None):
    """Compare the same ranges across targets. Consensus is what >= 2 agree on.

    `exclude` is a callable (target, entry) -> bool for rows that cannot be a
    valid reference. The ceiling is the case that needs it: for an archived post
    `raw` serves the outer volume stream rather than the assembled inner file, so
    its hash is legitimately different and counting it as a dissent would report
    every archive entry as a disagreement.
    """
    groups = {}
    for row in rows:
        if row.get("md5") is None:
            continue
        if exclude and exclude(row["target"], row["entry"]):
            continue
        groups.setdefault((row["entry"], row["offset"]), []).append(row)

    verdicts = []
    per_pair = {}
    for (entry, offset), members in sorted(groups.items()):
        counts = {}
        for row in members:
            counts[row["md5"]] = counts.get(row["md5"], 0) + 1
        best, best_n = None, 0
        for digest, count in counts.items():
            if count > best_n or (count == best_n and best and digest < best):
                best, best_n = digest, count
        agreed = best if best_n >= 2 else None
        for row in members:
            bucket = per_pair.setdefault((row["target"], entry),
                                         {"agree": 0, "differ": 0})
            if agreed is None:
                continue
            if row["md5"] == agreed:
                bucket["agree"] += 1
            else:
                bucket["differ"] += 1
        verdicts.append({
            "entry": entry, "offset": offset, "consensus": agreed,
            "distinct_hashes": len(counts), "compared": len(members),
            "unresolved": agreed is None,
        })

    differing = [{"target": t, "entry": e, **v}
                 for (t, e), v in sorted(per_pair.items()) if v["differ"]]
    total = sum(v["agree"] + v["differ"] for v in per_pair.values())
    matched = sum(v["agree"] for v in per_pair.values())
    return {
        "ranges": verdicts,
        "differing": differing,
        "pairs_compared": total,
        "pairs_matched": matched,
        "summary": (f"{matched} of {total} target-range pairs matched consensus"
                    if total else "nothing to compare"),
    }


# --------------------------------------------------------------------------
# noise floor
# --------------------------------------------------------------------------
def noise_floor(pass_a, pass_b, field="MBps"):
    """Spread between two identical passes, which is what a difference must beat.

    Reported per entry and for the run as a whole. Without it a report can say
    "provider throughput drifts" and still print a 12% gap as if it meant
    something.
    """
    index_a = {(r["target"], r["entry"]): r.get(field) for r in pass_a}
    index_b = {(r["target"], r["entry"]): r.get(field) for r in pass_b}
    deltas = []
    per_entry = {}
    for key, first in index_a.items():
        second = index_b.get(key)
        if not first or not second:
            continue
        change = 100.0 * abs(second - first) / first
        deltas.append(change)
        per_entry.setdefault(key[1], []).append(change)
    if not deltas:
        return {"comparable": 0,
                "note": "the two passes share no target-entry pair"}
    medians_a = [v for v in index_a.values() if v]
    medians_b = [v for v in index_b.values() if v]
    run_shift = None
    if medians_a and medians_b:
        first, second = statistics.median(medians_a), statistics.median(medians_b)
        run_shift = round(100.0 * abs(second - first) / first, 1)
    return {
        "comparable": len(deltas),
        "whole_run_median_shift_pct": run_shift,
        "per_entry_median_pct": round(statistics.median(deltas), 1),
        "per_entry_worst_pct": round(max(deltas), 1),
        "per_entry": {e: round(max(v), 1) for e, v in sorted(per_entry.items())},
        "resolves_differences_above_pct": round(max(deltas), 1),
        "note": ("a difference between two targets smaller than the worst "
                 "per-entry swing here is not resolved by one pass"),
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _cell(value):
    return "-" if value is None else str(value)


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(out)


def render_headline(result, label, unit="", lower_is_better=True):
    lines = [f"### {label}", ""]
    lines.append(f"Median over the {result['population_size']} entries at least "
                 f"{int(result['threshold'] * 100)}% of the field served. `n` is how "
                 f"many of those the target itself served; `own` is its median over "
                 f"everything it served, which is the flattering number when the two "
                 f"differ.")
    lines.append("")
    rows = []
    ordered = sorted(result["targets"].items(),
                     key=lambda kv: (kv[1].get("median") is None,
                                     kv[1].get("median") if lower_is_better
                                     else -(kv[1].get("median") or 0)))
    for name, row in ordered:
        rows.append([name,
                     f"{row['n']}/{row['of']}",
                     _cell(row.get("median")) + unit,
                     _cell(row.get("own_median")) + unit,
                     _cell(row.get("gap_pct")) + ("%" if row.get("gap_pct") else "")])
    lines.append(table(["target", "n", "median", "own", "gap"], rows))
    return "\n".join(lines)


def render_consensus(result):
    lines = ["### Byte-identity cross-check", "",
             "The same ranges hashed by every target and compared against each "
             "other, since a fast target serving the wrong bytes is not fast. "
             "Consensus is the hash at least two targets agree on; a row here is "
             "one to investigate.", "", result["summary"], ""]
    if not result["differing"]:
        lines.append("No target disagreed with consensus on any range.")
        return "\n".join(lines)
    rows = [[d["entry"], d["target"], d["agree"], d["differ"]]
            for d in result["differing"]]
    lines.append(table(["entry", "target", "agree", "differ"], rows))
    unresolved = [r for r in result["ranges"] if r["unresolved"]]
    if unresolved:
        lines.append("")
        lines.append(f"{len(unresolved)} ranges had no two targets agreeing, so "
                     f"they carry no consensus and prove nothing either way.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    data = json.load(open(sys.argv[1]))
    field = sys.argv[2] if len(sys.argv) > 2 else "MBps"
    print(render_headline(headline(data, field), field))
