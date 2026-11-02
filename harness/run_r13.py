#!/usr/bin/env python3
"""Rounds 13+: reviewed filesystem targets, ten connections, on the round's own host (ROUND)."""
import argparse
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIELD = ["raw", "zurg", "altmount", "infinidysk", "nzbdav-og", "decypharr", "aiostreams"]
PORTS = {"raw": 18099, "zurg": 19998, "altmount": 18081,
         "infinidysk": 18092, "nzbdav-og": 18093, "decypharr": 18282,
         "aiostreams": 13000}
sys.path.insert(0, str(HERE))
import round_profile as profile
CONTAINERS = {name: profile.container(name) for name in ("infinidysk", "nzbdav-og", "aiostreams")}
os.environ.setdefault("BENCH", profile.BENCH)
os.environ.setdefault("R10_PORTS", ",".join(f"{name}={port}" for name, port in PORTS.items()))
os.environ["CONNS"] = "10"
os.environ["GOMAXPROCS"] = str(profile.CPUS)
import run_r10 as runner
import targets_r10 as registry


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def check_counts(counts, budget=10):
    """Count a whole application, including all children and auxiliary pools."""
    active = {name: count for name, count in counts.items() if count}
    if any(count > budget for count in active.values()):
        raise RuntimeError(f"NNTP connection budget exceeded: {active}, cap={budget}")
    if len(active) > 1:
        raise RuntimeError(f"Concurrent benchmark NNTP consumers: {active}")


class SocketGate:
    """Fail closed on sampled oversubscription; keep raw census and zero samples."""
    def __init__(self, life, out, interval=1.0):
        self.life, self.out, self.interval = life, Path(out), interval
        self.stop_event = threading.Event()
        self.failure = None
        self.peaks = collections.Counter()
        self.samples = 0
        self.owners = set()
        self.thread = None
        self.provider_ips = {row[4][0] for row in socket.getaddrinfo(
            os.environ["NNTP_HOST"], int(os.environ.get("NNTP_PORT", "563")),
            type=socket.SOCK_STREAM)}

    def sample(self):
        pid_targets = {}
        for name in FIELD:
            for pid in self.life.pids_for(name):
                pid_targets[pid] = name
        text = subprocess.check_output(["ss", "-Htnp"], text=True)
        counts = collections.Counter()
        stamp = utc()
        with (self.out / "sockets.tsv").open("a") as sockets, \
                (self.out / "sockets-pids.tsv").open("a") as owners:
            for line in text.splitlines():
                fields = line.split()
                if len(fields) < 5 or not fields[4].endswith(":563"):
                    continue
                pids = {int(pid) for pid in re.findall(r"pid=(\d+)", line)}
                pid = next(iter(pids), None)
                name = next((pid_targets[p] for p in pids if p in pid_targets), None)
                # Native startup can authenticate before binding its HTTP port.
                if name is None and pid is not None:
                    try:
                        cwd = os.readlink(f"/proc/{pid}/cwd")
                    except OSError:
                        cwd = "unknown"
                    for target, directory in (("raw", ""), ("zurg", "zurgrun"),
                                              ("altmount", "altmount"),
                                              ("decypharr", "decyrun")):
                        root = os.path.join(registry.BENCH, directory).rstrip("/")
                        if cwd == root or (directory and cwd.startswith(root + "/")):
                            name = target
                            break
                sockets.write(f"{stamp}\t{fields[0]}\t{pid if pid is not None else '?'}\n")
                if pid is not None and pid not in self.owners:
                    self.owners.add(pid)
                    try:
                        comm = Path(f"/proc/{pid}/comm").read_text().strip()
                        cwd = os.readlink(f"/proc/{pid}/cwd")
                    except OSError:
                        comm, cwd = "unknown", "unknown"
                    if name and registry.TARGETS[name]["kind"] == "docker":
                        cwd = os.path.join(registry.BENCH, name)
                    owners.write(f"{pid}\t{comm}\t{cwd}\n")
                if fields[0] == "ESTAB":
                    if name:
                        counts[name] += 1
                    elif fields[4].rsplit(":", 1)[0].strip("[]") in self.provider_ips:
                        counts["unowned-provider-consumer"] += 1
        with (self.out / "connection-samples.jsonl").open("a") as handle:
            handle.write(json.dumps({"at": stamp, "counts": dict(counts)}) + "\n")
        self.samples += 1
        for name, count in counts.items():
            self.peaks[name] = max(self.peaks[name], count)
        check_counts(counts)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.sample()
            except Exception as exc:
                self.failure = f"{type(exc).__name__}: {exc}"
                os.kill(os.getpid(), signal.SIGINT)
                return
            self.stop_event.wait(self.interval)

    def __enter__(self):
        self.sample()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_event.set()
        self.thread.join()
        dump(self.out / "connection-gate.json", {"budget": 10,
             "sample_interval_s": self.interval, "samples": self.samples,
             "peaks": dict(self.peaks), "failure": self.failure,
             "sampling_limit": "Sub-interval transient sockets are not observed."})
        if self.failure:
            raise RuntimeError(self.failure)


def install_truth(out):
    """Acquire provider truth before targets run; never an eleventh live socket."""
    damage = runner.damage
    nzb = runner.corpus.resolve(runner.corpus.BY_ID["damaged-partial"])
    files = damage.parse_nzb(nzb)
    target, _ = damage.pick_file(files)
    segments = target["segments"]
    holes = damage.find_holes(segments)
    if not holes:
        raise RuntimeError("Damaged corpus no longer contains a missing article")
    recorded = {}
    for index in sorted({0, holes[0] - 1, holes[0] + 1}):
        if 0 <= index < len(segments):
            recorded[index] = damage.true_bytes(segments, index)
    dump(Path(out) / "damage-oracle.json", {"at": utc(),
         "nzb_sha256": hashlib.sha256(Path(nzb).read_bytes()).hexdigest(),
         "holes": holes, "articles": {str(index): {
             "decoded_bytes": len(payload) if payload is not None else None,
             "sha256": hashlib.sha256(payload).hexdigest() if payload is not None else None,
             "meta": {k: v for k, v in meta.items() if k != "name"} if isinstance(meta, dict) else meta
             } for index, (payload, meta) in recorded.items()}})

    def cached_true(items, index, *args, **kwargs):
        if items != segments or index not in recorded:
            raise RuntimeError("Damage oracle requested unrecorded provider bytes")
        return recorded[index]

    def cached_holes(items, *args, **kwargs):
        if items != segments:
            raise RuntimeError("Damage oracle requested an unrecorded release")
        return list(holes)

    damage.true_bytes, damage.find_holes = cached_true, cached_holes


def lifecycle():
    for name, container in CONTAINERS.items():
        if registry.TARGETS[name]["kind"] == "docker":
            registry.TARGETS[name]["container"] = container
    registry.TARGETS["altmount"]["state_paths"] = [
        "{bench}/altmount/cfg", "{bench}/altmount/tmp"]
    registry.TARGETS["raw"]["start"] = (
        "cd {bench} && nohup python3 rawserve_r10.py {nzb} "
        f"{registry.TARGETS['raw']['port']} "
        "--conns {conns} > raw.log 2>&1 &")
    life = runner.load_lifecycle()
    life.SPEC = {name: life.SPEC[name] for name in FIELD}
    life.ALL = list(FIELD)
    start = life.start

    def checked_start(name):
        pids = start(name)
        if name not in ("raw", "aiostreams"):
            subprocess.run([sys.executable, str(HERE / "readback_r13.py"), name], check=True)
        elif name == "aiostreams":
            subprocess.run([sys.executable, str(HERE / "prep_aiostreams_r13.py"), "validate"], check=True)
        return pids

    life.start = checked_start
    return life


def assert_owned_ports(life):
    for name in FIELD:
        for pid in life.pids_on(registry.TARGETS[name]["port"]):
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError as exc:
                raise RuntimeError(f"Cannot establish ownership of {name} listener {pid}") from exc
            owned = cwd == registry.BENCH or cwd.startswith(registry.BENCH + "/")
            if registry.TARGETS[name]["kind"] == "docker":
                owned = pid in life.container_pids(registry.TARGETS[name]["container"])
            if not owned:
                raise RuntimeError(f"Refusing to stop foreign listener: {name} pid={pid} cwd={cwd}")


def pass_run(names, entries, life, tag, path):
    rows, memories = [], {}
    for target in names:
        memory = memories.setdefault(target, runner.procmon.RunMemory())
        rows.extend(runner.run_target(target, entries, life, tag, memory, 10))
        # run_target logs a failed drain; do not let the next target inherit it.
        life.stop(target)
    data = {"tag": tag, "field": names, "connections": 10, "rows": rows,
            "memory": {name: memory.summary() for name, memory in memories.items()},
            "capability": runner.expect.tally(rows),
            "throughput": runner.report.headline(rows, "MBps", names),
            "cold_open": runner.report.headline(rows, "cold_open_s", names),
            "consensus": runner.report.consensus([
                {"target": row["target"], "entry": row["entry"],
                 "offset": item["offset"], "md5": item.get("md5")}
                for row in rows for item in (row.get("integrity") or [])],
                exclude=lambda name, entry: name == "raw" and entry not in (
                    "plain-video", "damaged-partial")),
            "shakedown": registry.needs_shakedown(names)}
    dump(path, data)
    return data


def select_field(spec):
    """--targets a,b: a subset of FIELD, kept in FIELD's order so rotation still applies."""
    if not spec:
        return list(FIELD)
    wanted = [name.strip() for name in spec.split(",") if name.strip()]
    unknown = sorted(set(wanted) - set(FIELD))
    if unknown or not wanted:
        raise SystemExit(f"Unknown or empty --targets {unknown or spec!r}; known: {', '.join(FIELD)}")
    return [name for name in FIELD if name in wanted]


def reset():
    subprocess.run(["bash", str(HERE / "prep-r13.sh"), "reset"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Plain-video path on every target, not a published round")
    parser.add_argument("--out", default=str(REPO / "results" / f"round{profile.ROUND[1:]}"))
    parser.add_argument("--targets", help="comma-separated subset of the field, e.g. raw,aiostreams")
    parser.add_argument("--main-only", action="store_true",
                        help="only the main pass: a rerun of part of a round, not a round")
    args = parser.parse_args()
    FIELD[:] = select_field(args.targets)
    if os.geteuid() != 0:
        raise SystemExit("Run as root: Docker /proc accounting and socket ownership must be visible")
    profile.check_provider(os.environ.get("NNTP_HOST"), os.environ.get("NNTP_PORT", "563"))
    profile.check_bench(registry.BENCH)
    if not os.environ.get("NNTP_USER") or not os.environ.get("NNTP_PASS"):
        raise SystemExit("Load the designated bench-account.env before running")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "connection-samples.jsonl").exists():
        raise SystemExit("Output already contains a run; choose a fresh directory")
    life = lifecycle()
    assert_owned_ports(life)
    life.stop_all()
    runner.corpus.derive_all()
    main_data = None
    try:
        # Oracle acquisition runs with all software stopped and is outside timings.
        if not args.smoke:
            install_truth(out)
        with SocketGate(life, out) as gate:
            phases = [("smoke", FIELD, [runner.corpus.BY_ID["plain-video"]])] if args.smoke else \
                [("main", FIELD[3:] + FIELD[:3], runner.corpus.ENTRIES)] if args.main_only else [
                ("noise_a", FIELD[1:] + FIELD[:1], [runner.corpus.BY_ID["plain-video"]]),
                ("noise_b", FIELD[2:] + FIELD[:2], [runner.corpus.BY_ID["plain-video"]]),
                ("main", FIELD[3:] + FIELD[:3], runner.corpus.ENTRIES)]
            windows = {}
            for phase, names, entries in phases:
                life.stop_all()
                print(f"=== RESET {phase} {utc()} ===", flush=True)
                reset()
                windows[phase] = {"start": utc()}
                print(f"=== {phase.upper()} start {utc()} ===", flush=True)
                main_data = pass_run(names, entries, life, f"{profile.ROUND}-{phase}", out / f"{phase}.json")
                windows[phase]["end"] = utc()
                dump(out / "windows.json", windows)
                print(f"=== {phase.upper()} done {utc()} ===", flush=True)
    finally:
        life.stop_all()
    underfilled = {name: gate.peaks.get(name, 0) for name in FIELD if gate.peaks.get(name, 0) < 10}
    if underfilled:
        print(f"Ten-connection allowance; targets using fewer sockets: {underfilled}", flush=True)
    if args.smoke:
        failed = [row["target"] for row in main_data["rows"] if not row.get("served")]
        if failed or main_data["consensus"]["differing"]:
            raise RuntimeError(f"Filesystem smoke failed: targets={failed}, byte disagreements={main_data['consensus']['differing']}")
        print(f"Filesystem smoke passed: all seven targets served matching sampled bytes; live socket peaks={dict(gate.peaks)}; cap=10", flush=True)
    if not args.smoke and not args.main_only:
        report = runner.report
        a, b = (json.loads((out / f"{phase}.json").read_text()) for phase in ("noise_a", "noise_b"))
        text = [f"# Round {profile.ROUND[1:]}: reviewed filesystem targets on {profile.P['where']}", "", "Connection allowance: at most 10 per application; actual peaks are in connection-gate.json.", "",
                report.render_headline(main_data["throughput"], "Sequential throughput", unit=" MB/s", lower_is_better=False),
                report.render_headline(main_data["cold_open"], "Cold open", unit=" s", lower_is_better=True),
                report.render_resources(main_data["memory"]),
                report.render_consensus(main_data["consensus"]), "", "## Clean-start noise floor", "",
                "```json", json.dumps(report.noise_floor(a["rows"], b["rows"]), indent=2), "```", "",
                "## Capability", "", "```json", json.dumps(main_data["capability"], indent=2), "```", ""]
        (out / "report.md").write_text("\n".join(text))


if __name__ == "__main__":
    main()
