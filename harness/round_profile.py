#!/usr/bin/env python3
"""Which round the round 13 harness is running: its host, account and pins.

The harness refuses any provider but the round's designated one and any working
directory but the round's own, so those are data here rather than literals in
every script. ROUND selects the profile (default r13, which reproduces round 13
on zen exactly). `python3 round_profile.py env` prints shell exports for the
shell scripts; no secret is part of a profile.
"""
import json
import os
from pathlib import Path
import shlex
import sys

REPO = Path(__file__).resolve().parent.parent

PROFILES = {
    # the account a round may dial, and only that one: a wrong host is a
    # production account being borrowed, which the one-IP rule forbids
    "r13": {"tag": "r13-20261001", "bench": "/home/ben/bench-round13-20261001",
            "host": "newswest.frugalusenet.com", "port": 563, "cpus": 2,
            "manifest": "config/round13-existing.json", "where": "zen"},
    "r14": {"tag": "r14-20261102", "bench": "/root/bench-round14",
            "host": "news.bulknews.eu", "port": 563, "cpus": 4,
            "manifest": "config/round14-existing.json", "where": "Hetzner ccx23"},
}

ROUND = os.environ.get("ROUND", "r13")
if ROUND not in PROFILES:
    raise SystemExit(f"Unknown ROUND={ROUND!r}; known: {', '.join(PROFILES)}")
P = PROFILES[ROUND]
TAG, BENCH, HOST, PORT, CPUS = P["tag"], P["bench"], P["host"], P["port"], P["cpus"]
# ROUND_PIN: a second pin file for a rerun of part of the field after the round
# (config/round14-zurg-rerun.json), so the round's own pins stay as published
MANIFEST = os.environ.get("ROUND_PIN") or P["manifest"]
SOURCES = json.loads((REPO / MANIFEST).read_text())


def revision(name):
    return SOURCES[name]["revision"]


def image(name):
    """docker tag of a built target: <name>:<round>-<12 hex of its revision>"""
    repo = {"nzbdav-og": "nzbdav"}.get(name, name)
    return f"{repo}:{ROUND}-{revision(name)[:12]}"


def container(name):
    repo = {"nzbdav-og": "nzbdav"}.get(name, name)
    return f"{repo}-{TAG}"


def check_provider(host, port):
    if host != HOST or int(port) != PORT:
        raise SystemExit(f"Round {ROUND} may dial only {HOST}:{PORT} TLS, not {host}:{port}")


def check_bench(path):
    path = Path(path)
    if path != Path(BENCH) or path.is_symlink():
        raise SystemExit(f"Round {ROUND} requires BENCH={BENCH} (not a symlink), not {path}")
    return path


def shell():
    rows = {"ROUND": ROUND, "ROUND_TAG": TAG, "ROUND_BENCH": BENCH,
            "ROUND_HOST": HOST, "ROUND_PORT": PORT, "ROUND_CPUS": CPUS,
            "ROUND_MANIFEST": str(REPO / MANIFEST)}
    for name in SOURCES:
        key = name.upper().replace("-", "_")
        rows[f"REV_{key}"] = revision(name)
        rows[f"IMG_{key}"] = image(name)
        rows[f"CTR_{key}"] = container(name)
    return "".join(f"export {k}={shlex.quote(str(v))}\n" for k, v in rows.items())


if __name__ == "__main__":
    if sys.argv[1:] != ["env"]:
        raise SystemExit("usage: round_profile.py env")
    sys.stdout.write(shell())
