#!/usr/bin/env python3
"""Behaviour at a known missing article, with the alignment actually verified.

Round 7's damage phase read a band across the hole and classified what came
back. That is the right test and it rests on an assumption nothing checked: that
the server lays the file out the way the harness thinks it does. If a target
assembles a release differently -- a different file picked out of the release, a
different order, a header the harness did not account for -- then the bytes at
the offset the harness calls "the hole" are ordinary video, they are not zeros,
and the target is credited with a repair it never performed. The published
verdicts happened to be right; nothing in the harness could have told us if they
were not.

So before any verdict, this decodes the 256 KB either side of the hole straight
off NNTP and compares it against what the target serves at those offsets. A
target whose anchors do not match is reported `aligned: false` and every damage
verdict for it is withheld, because none of them mean anything.

Two reads are then taken, because engines answer them differently:

  * a streaming read starting 1 MB before the hole and running past it, which is
    what a player does
  * a direct Range asking only for bytes inside the hole, which is what a seek
    does

and a control band of the same size over intact video, so a slowdown is a
measured ratio rather than an impression.

One thing this deliberately does not decide. Clean bytes at the hole are either
a repair or a fabrication, and one read cannot tell them apart -- both look like
success at t0. `damage_timeline_r7.py` is what separates them, by re-probing
minutes later and watching for the md5 to flip from the zero-fill hash to real
content. This phase reports `served-clean` and says to go and run that.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from metrics_r10 import timed_stream  # noqa: E402
from nntp_r10 import NntpConn, parse_nzb  # noqa: E402
from rawserve_r10 import HOST, PASS, PORT, USER, pick_file  # noqa: E402

ANCHOR = 256 << 10          # bytes either side of the hole to verify alignment
LEAD_IN = 1 << 20           # how far before the hole a streaming read starts
STAT_BATCH = 200


def find_holes(segments, host=HOST, port=PORT, user=USER, password=PASS):
    """Indices of articles the server does not have, by STAT rather than BODY.

    STAT costs a status line instead of a 4 MiB transfer, so scanning a whole
    release is cheap enough to do every run rather than trusting a number
    written down once. That matters: an article that was present when the corpus
    was built can rot, and a phase that assumes the old hole is the only hole
    measures the wrong offset.
    """
    conn = NntpConn(host, port, user, password)
    missing = []
    try:
        for base in range(0, len(segments), STAT_BATCH):
            batch = segments[base:base + STAT_BATCH]
            for _, _, mid in batch:
                conn._cmd("STAT <%s>" % mid.strip("<>"))
            for offset in range(len(batch)):
                code, _ = conn._status()
                if code != 223:
                    missing.append(base + offset)
    finally:
        conn.close()
    return missing


def true_bytes(segments, index, host=HOST, port=PORT, user=USER, password=PASS):
    """Decode one article straight off NNTP. Returns (payload, meta) or (None, err)."""
    conn = NntpConn(host, port, user, password)
    try:
        (payload, meta), = conn.fetch([segments[index][2]])
        return payload, meta
    finally:
        conn.close()


def zero_run(data):
    """Longest run of zero bytes, which is what a zero-fill leaves behind."""
    best = run = 0
    for byte in data:
        if byte:
            run = 0
        else:
            run += 1
            if run > best:
                best = run
    return best


def classify(stream_res, hole_start, hole_end, band_start):
    """What the engine did at the hole, from a read that spans it."""
    if stream_res.get("error") and (stream_res.get("bytes") or 0) == 0:
        return "error-at-hole", stream_res["error"]
    delivered = stream_res.get("bytes") or 0
    reached = band_start + delivered
    # the question is whether the read got past the far edge of the gap. Anything
    # that stopped before that stopped *at* the gap, whether it halted a byte
    # early or halfway through
    if reached < hole_end:
        where = ("before it" if reached <= hole_start
                 else f"{reached - hole_start} bytes into it")
        return "truncated-at-hole", f"stopped {where}, at absolute offset {reached}"
    if stream_res.get("error"):
        return "aborted-past-hole", stream_res["error"]
    requested = stream_res.get("requested")
    if requested and delivered < requested:
        return "truncated-at-hole", f"delivered {delivered} of {requested}"
    return "spans-hole", "the read covered the gap; the body says what is in it"


def probe(url, auth, hole_start, hole_len, size, timeout=600):
    """Both reads plus a control band, with the hole's contents inspected."""
    hole_end = hole_start + hole_len
    band_start = max(0, hole_start - LEAD_IN)
    band_len = LEAD_IN + hole_len + LEAD_IN

    out = {}
    # (a) streaming read across the gap, body kept so the gap can be inspected
    stream = timed_stream(url, auth, band_start, band_len, want_hash=True,
                          timeout=timeout)
    out["streaming"] = {k: stream.get(k) for k in
                        ("http", "bytes", "total_s", "ttfb_s", "error", "md5",
                         "requested", "content_range")}
    verdict, detail = classify(stream, hole_start, hole_end, band_start)
    out["streaming"]["verdict"] = verdict
    out["streaming"]["detail"] = detail

    # (b) direct Range asking only for bytes inside the gap
    direct = timed_stream(url, auth, hole_start, hole_len, want_hash=True,
                          timeout=timeout)
    out["direct"] = {k: direct.get(k) for k in
                     ("http", "bytes", "total_s", "error", "md5", "requested")}

    # (c) control band of the same size over intact video, for the slowdown
    control_start = min(max(0, size - band_len - 1), hole_start + 8 * band_len)
    control = timed_stream(url, auth, control_start, band_len, timeout=timeout)
    out["control"] = {k: control.get(k) for k in
                      ("http", "bytes", "total_s", "MBps", "error")}
    if (control.get("total_s") or 0) > 0 and (stream.get("total_s") or 0) > 0:
        out["slowdown_x"] = round(stream["total_s"] / control["total_s"], 2)
    return out


def inspect_gap(url, auth, hole_start, hole_len, timeout=600):
    """Read exactly the gap and describe the bytes, not just the status code.

    A 206 with the right Content-Length is what both a zero-fill and a repair
    return. The difference is entirely in the body.
    """
    res = timed_stream(url, auth, hole_start, min(hole_len, 4 << 20),
                       want_hash=True, timeout=timeout)
    body = {"http": res.get("http"), "bytes": res.get("bytes"),
            "md5": res.get("md5"), "error": res.get("error")}
    if not res.get("bytes"):
        body["content"] = "no bytes"
        return body
    # re-read the same range keeping the payload, so the zeros can be counted
    import urllib.request
    from metrics_r10 import _request
    try:
        with urllib.request.urlopen(
                _request(url, auth, hole_start,
                         hole_start + min(hole_len, 1 << 20) - 1),
                timeout=timeout) as resp:
            data = resp.read()
    except Exception as exc:
        body["content"] = f"unreadable on re-read: {type(exc).__name__}"
        return body
    zeros = zero_run(data)
    body["zero_run"] = zeros
    body["sampled"] = len(data)
    if zeros == len(data):
        body["content"] = "all zeros"
    elif zeros > len(data) * 0.5:
        body["content"] = f"mostly zeros ({zeros} of {len(data)})"
    else:
        body["content"] = "non-zero"
    return body


def verify_alignment(url, auth, segments, hole_index, part_size, timeout=600):
    """Are the bytes either side of the gap where the harness thinks they are?

    Without this the whole phase is an assumption. A target that assembles the
    release differently serves ordinary video at the offset the harness calls
    the hole, which reads as a flawless repair.
    """
    out = {"anchor_bytes": ANCHOR}
    checks = []
    for label, index in (("pre", hole_index - 1), ("post", hole_index + 1)):
        if index < 0 or index >= len(segments):
            checks.append({"side": label, "skipped": "no article on this side"})
            continue
        payload, meta = true_bytes(segments, index)
        if payload is None:
            checks.append({"side": label, "skipped": f"article unavailable: {meta}"})
            continue
        if label == "pre":
            want = payload[-ANCHOR:]
            offset = index * part_size + len(payload) - len(want)
        else:
            want = payload[:ANCHOR]
            offset = index * part_size
        res = timed_stream(url, auth, offset, len(want), want_hash=True,
                           timeout=timeout)
        got = res.get("md5")
        expect = hashlib.md5(want).hexdigest()
        checks.append({
            "side": label, "offset": offset, "length": len(want),
            "expected_md5": expect, "served_md5": got,
            "match": bool(got) and got == expect,
            "http": res.get("http"), "error": res.get("error"),
        })
    out["checks"] = checks
    graded = [c for c in checks if "match" in c]
    out["aligned"] = bool(graded) and all(c["match"] for c in graded)
    if not graded:
        out["aligned"] = None
        out["note"] = "neither anchor could be checked; alignment is unknown"
    return out


def run(url, auth, nzb, hole_index=None, timeout=600):
    files = parse_nzb(nzb)
    target, name = pick_file(files)
    segments = target["segments"]

    first, meta = true_bytes(segments, 0)
    if first is None:
        raise SystemExit(f"cannot bootstrap: first article unavailable ({meta})")
    part_size = len(first)
    size = meta.get("file_size") or part_size * len(segments)

    if hole_index is None:
        holes = find_holes(segments)
        if not holes:
            raise SystemExit(f"{name}: no missing article found, nothing to measure")
        hole_index = holes[0]
    else:
        holes = [hole_index]

    hole_start = hole_index * part_size
    out = {
        "file": name, "nzb": os.path.basename(nzb), "url": url,
        "articles": len(segments), "part_size": part_size, "size": size,
        "holes_found": holes[:20], "holes_total": len(holes),
        "hole_index": hole_index, "hole_start": hole_start,
        "hole_end": hole_start + part_size, "hole_bytes": part_size,
        "hole_position_pct": round(100.0 * hole_start / size, 2) if size else None,
    }
    out["alignment"] = verify_alignment(url, auth, segments, hole_index, part_size,
                                        timeout)
    if out["alignment"]["aligned"] is False:
        # a verdict taken against the wrong offset is worse than no verdict
        out["verdict"] = "WITHHELD"
        out["why"] = ("the anchors either side of the gap do not match the bytes "
                      "decoded from NNTP, so this target does not lay the file out "
                      "the way this phase assumes and no damage verdict from it "
                      "would mean anything")
        return out

    out.update(probe(url, auth, hole_start, part_size, size, timeout))
    out["gap"] = inspect_gap(url, auth, hole_start, part_size, timeout)

    content = out["gap"].get("content")
    stream_verdict = out["streaming"]["verdict"]
    if stream_verdict in ("truncated-at-hole", "error-at-hole", "aborted-past-hole"):
        out["verdict"] = stream_verdict
    elif content == "all zeros" or (content or "").startswith("mostly zeros"):
        out["verdict"] = "zero-filled"
    elif content == "non-zero":
        out["verdict"] = "served-clean"
        out["why"] = ("clean bytes over a range that is provably absent upstream. "
                      "That is either a repair or a fabrication and one read "
                      "cannot tell them apart: run damage_timeline_r7.py and "
                      "watch whether the md5 flips to real content")
    else:
        out["verdict"] = "no bytes at the gap"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url", help="the target's URL for the damaged release")
    ap.add_argument("nzb", help="the damaged NZB, so the true bytes can be decoded")
    ap.add_argument("--user", help="basic-auth user for the target")
    ap.add_argument("--password", help="basic-auth password for the target")
    ap.add_argument("--hole-index", type=int, default=None,
                    help="skip the STAT scan and use this article index")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    auth = (args.user, args.password) if args.user else None
    print(json.dumps(run(args.url, auth, args.nzb, args.hole_index, args.timeout),
                     indent=1))


if __name__ == "__main__":
    main()
