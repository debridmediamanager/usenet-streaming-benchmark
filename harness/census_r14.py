#!/usr/bin/env python3
"""Is the corpus on the round's provider? Answer before any target runs.

A round's expectations assume the provider holds every article of the four
complete posts and all but the one deliberately unreachable article of the
damaged one. A new provider is a new backbone, and a takedown or a retention
gap there would turn "serve" into "missing" for every target alike, and read
as the field failing. So: STAT every article, and BODY-decode the first,
middle and last article of every file with its CRC, because STAT has answered
223 for articles BODY then refused on two providers this harness has used.

    NNTP_HOST NNTP_PORT NNTP_USER NNTP_PASS python3 census_r14.py CORPUS_DIR OUT.json

One connection, pipelined: the census is not a measurement and needs no more.
"""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nntp_r10 as nntp
import round_profile as profile

# entry -> missing articles it is built to have; anything else is the provider
EXPECTED_MISSING = {"ToyStory5.nzb": 0, "ToyStory5Damaged.nzb": 1, "Obfuscated.nzb": 0,
                    "FatherBrown.nzb": 0, "Bosch.S01.nzb": 0}


def stat_all(conn, ids, batch=200):
    missing = []
    for at in range(0, len(ids), batch):
        chunk = ids[at:at + batch]
        for mid in chunk:
            conn._cmd("STAT <%s>" % mid.strip("<>"))
        for mid in chunk:
            code, _ = conn._status()
            if code != 223:
                missing.append(mid)
    return missing


def probes(files):
    for f in files:
        segs = f["segments"]
        for ix in sorted({0, len(segs) // 2, len(segs) - 1}):
            if segs:
                yield segs[ix][2]


def verdict(name, stat_missing, body_failed):
    want = EXPECTED_MISSING[name]
    ok = len(stat_missing) == want and not body_failed
    return {"ok": ok, "expected_missing": want, "stat_missing": len(stat_missing),
            "body_failed": len(body_failed)}


def main():
    corpus, out = Path(sys.argv[1]), Path(sys.argv[2])
    host, port = os.environ["NNTP_HOST"], int(os.environ.get("NNTP_PORT", "563"))
    profile.check_provider(host, port)
    conn = nntp.NntpConn(host, port, os.environ["NNTP_USER"], os.environ["NNTP_PASS"])
    report = {"provider_round": profile.ROUND, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "entries": {}}
    try:
        for name in EXPECTED_MISSING:
            files = nntp.parse_nzb(str(corpus / name))
            ids = [s[2] for f in files for s in f["segments"]]
            t0 = time.monotonic()
            missing = stat_all(conn, ids)
            body_failed = []
            for mid in probes(files):
                if mid in missing:
                    continue  # the deliberate hole is STAT's to report
                (payload, meta), = conn.fetch([mid])
                if payload is None or nntp.crc_ok(payload, meta) is False:
                    body_failed.append(mid)
            row = verdict(name, missing, body_failed)
            row.update(articles=len(ids), seconds=round(time.monotonic() - t0, 1))
            report["entries"][name] = row
            print(f"{name:24s} {len(ids) - len(missing):6d}/{len(ids):<6d} body-failed {len(body_failed)} "
                  f"{'ok' if row['ok'] else 'NOT AS BUILT'}", flush=True)
    finally:
        conn.close()
    report["ok"] = all(r["ok"] for r in report["entries"].values())
    out.write_text(json.dumps(report, indent=2) + "\n")
    if not report["ok"]:
        raise SystemExit("The corpus is not on this provider as built; the round would measure the backbone")


if __name__ == "__main__":
    main()
