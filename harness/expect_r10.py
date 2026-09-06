#!/usr/bin/env python3
"""Scoring an entry against what it was supposed to do, not against its status code.

Two failures look exactly like success to a status-code check, and both are
real. The first is an engine that answers a request it cannot satisfy: a 206
with the right Content-Length, then zeros, or a stream that stops partway with
the status line already sent. The second is an engine that answers a failure
with a short piece of valid media -- a built-in clip saying "could not prepare
this release" -- which is a 200, is genuinely video, and is not the film.

So `served` is a judgement rather than a status code, and it is deliberately
hard to earn:

  * a 206 for the whole requested range, and
  * enough bytes to be the media rather than a message, by both an absolute
    floor and a fraction of what was asked for, and
  * a route that accepts ranges, because a stream that cannot be seeked is a
    message with a play button

Everything that fails those is reported with which one it failed, never as a
bare false: "wrongly served" and "the server refused" are opposite results and
must never collapse into the same cell.
"""
import json
import hashlib

# A failure clip is on the order of a few hundred KB. A real ranged read in this
# harness asks for megabytes, so an absolute floor separates them without
# needing to decode anything.
MIN_SERVED_BYTES = 4 << 20
# and a fraction, so a large request answered with a sliver is caught too
MIN_SERVED_FRACTION = 0.90

PASS = "pass"                       # expect serve, served
FAIL = "FAIL"                       # expect serve, did not serve
REFUSED = "refused"                 # expect reject, did not serve
WRONGLY_SERVED = "WRONGLY SERVED"   # expect reject, served anyway

OUTCOMES = (PASS, FAIL, REFUSED, WRONGLY_SERVED)


def judge_served(observed, requested=None):
    """Did the target actually serve the media? Returns (bool, reason).

    The reason is the point. An engine that returned 404 and one that returned a
    420 KB apology video both did not serve, and a run that cannot tell them
    apart cannot tell a clean refusal from a fabricated success.
    """
    if observed.get("error") and not observed.get("bytes"):
        return False, f"error: {observed['error']}"[:120]

    http = str(observed.get("http") or "")
    got = observed.get("bytes") or 0
    want = requested if requested is not None else observed.get("requested")

    if http.startswith("4") or http.startswith("5"):
        return False, f"HTTP {http}"
    if http not in ("206", "200"):
        return False, f"HTTP {http}"

    accept = (observed.get("accept_ranges") or "").strip().lower()
    if accept == "none":
        # valid media over a route that refuses to seek is a message, not a stream
        return False, "accept-ranges: none, so this is a status clip not a stream"

    if got < MIN_SERVED_BYTES:
        return False, (f"{got} bytes is below the {MIN_SERVED_BYTES} floor, "
                       "which is a message rather than media")
    if want and got < want * MIN_SERVED_FRACTION:
        return False, f"delivered {got} of {want} requested"
    if http == "200" and want and got < want:
        return False, f"200 with {got} of {want}, so the range was ignored and short"
    return True, f"{got} bytes over HTTP {http}"


def score(entry, observed, requested=None):
    """Apply the expectation matrix to one target-entry pair."""
    if entry.get("needs_real_post"):
        return {"outcome": None, "skipped": "no post for this entry yet",
                "entry": entry["id"], "expect": entry["expect"]}

    served, reason = judge_served(observed, requested)
    expect = entry.get("expect", "serve")
    if expect == "serve":
        outcome = PASS if served else FAIL
    else:
        outcome = WRONGLY_SERVED if served else REFUSED
    return {
        "entry": entry["id"], "tier": entry.get("tier"), "expect": expect,
        "served": served, "reason": reason, "outcome": outcome,
        "http": observed.get("http"), "bytes": observed.get("bytes"),
    }


_ZERO_MD5 = {}


def zero_md5(length):
    """md5 of `length` zero bytes, memoised. Small set of lengths in practice."""
    if length not in _ZERO_MD5:
        _ZERO_MD5[length] = hashlib.md5(b"\x00" * length).hexdigest()
    return _ZERO_MD5[length]


def zero_filled(integrity):
    """How many sampled blocks came back as silence, and how many were checked.

    Serving is not one behaviour. On a release stripped of two thirds of its
    content articles, one mount answered with the ORIGINAL full size and filled
    the gaps with zeros, while another reported a third of the size -- matching
    the surviving articles to the decimal -- and served real bytes for all of
    it. Both scored WRONGLY SERVED, and they are not the same failure: the
    second is short and honest, the first asserts bytes it does not have.

    A block of silence is identified by hash rather than by reading a rate,
    because a fast row is exactly what zero-fill looks like from the outside.
    """
    checked = filled = 0
    for sample in integrity or []:
        digest, length = sample.get("md5"), sample.get("bytes")
        if not digest or not length:
            continue
        checked += 1
        if digest == zero_md5(length):
            filled += 1
    return {"samples_checked": checked, "samples_zero_filled": filled,
            "zero_fill": bool(filled)}


def tally(rows):
    """Per-target counts, with the two that matter kept separate.

    `wrongly_served` is reported on its own and never folded into a pass rate. A
    target that refuses everything scores worse than one that serves everything
    on a naive count, and better on this one, which is the correct ordering: a
    refusal costs a viewer a title, a fabricated success costs them their trust
    in every other title.
    """
    out = {}
    for row in rows:
        target = row.get("target")
        bucket = out.setdefault(target, {k: 0 for k in OUTCOMES})
        bucket.setdefault("skipped", 0)
        outcome = row.get("outcome")
        # A row the run abandoned is not a verdict. A negative entry dropped
        # because the target exhausted its time budget scored as REFUSED, which
        # credits it for correctly rejecting content it never attempted --
        # infinidysk was credited with a refusal it never made on the first
        # full round, having simply run out of time.
        if outcome is None or row.get("skipped"):
            bucket["skipped"] += 1
        else:
            bucket[outcome] += 1
    for bucket in out.values():
        graded = sum(bucket[k] for k in OUTCOMES)
        bucket["graded"] = graded
        bucket["correct"] = bucket[PASS] + bucket[REFUSED]
        bucket["correct_pct"] = (round(100.0 * bucket["correct"] / graded)
                                 if graded else None)
    return out


def matrix(rows, entry_order=None, target_order=None):
    """rows -> {entry: {target: outcome}}, for the capability table."""
    grid = {}
    for row in rows:
        grid.setdefault(row["entry"], {})[row["target"]] = row.get("outcome")
    if entry_order:
        grid = {e: grid.get(e, {}) for e in entry_order if e in grid}
    if target_order:
        grid = {e: {t: cols.get(t) for t in target_order} for e, cols in grid.items()}
    return grid


if __name__ == "__main__":
    import sys
    data = json.load(open(sys.argv[1]))
    print(json.dumps(tally(data), indent=1))
