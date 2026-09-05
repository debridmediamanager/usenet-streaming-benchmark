#!/usr/bin/env python3
"""Connection parity, read from the sockets a round actually held.

Every round states a connection budget and every round's configuration has been
capable of lying about it. Round 6 streamed on 50 connections while its config
read 20, because in three of five servers the provider pool and the read budget
are separate settings and "unset" means "the whole pool". Round 9 stopped
trusting the files and counted sockets instead. This is that count, as a script
rather than as a shell pipeline retyped each round.

It answers two questions a config cannot:

  * did each target actually hold the budget it was given
  * was anything else on the account while a target was being measured

The second one matters more. A foreign consumer -- another instance, a
production service on the same box -- does not announce itself in any result
file, and its bytes come out of the same account.

Input is what `sock-sample-r10.sh` writes beside the results:

    sockets.tsv       timestamp, state, pid       one row per socket per sample
    sockets-pids.tsv  pid, comm, cwd              one row per pid, resolved live

A pid is gone by the time a round ends, so the owner map has to be collected
during the run. That is the whole reason it is a separate file.

Usage:
    python3 harness/parity_r10.py results/round10
    python3 harness/parity_r10.py results/round10 --production /home/ben/zurg
"""
import argparse
import collections
import json
import os
import sys

# processes that share the news account and are nobody's target. Anything else
# holding a socket while a target is measured is either that target or a
# contaminant, and the report says which
PRODUCTION_CWDS = ("/home/ben/zurg", "/home/ben/zurg-stremio")


def load_owners(path):
    owners = {}
    if not os.path.exists(path):
        return owners
    with open(path) as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                owners[parts[0]] = {"comm": parts[1], "cwd": parts[2]}
    return owners


def load_samples(path):
    samples = collections.OrderedDict()
    with open(path) as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3 or parts[0] == "sampler-done":
                continue
            stamp, state, pid = parts[0], parts[1], parts[2]
            samples.setdefault(stamp, []).append((state, pid))
    return samples


def is_production(pid, owners, production):
    cwd = (owners.get(pid) or {}).get("cwd", "")
    return any(cwd == root or cwd.startswith(root + "/") for root in production)


def census(results_dir, production=PRODUCTION_CWDS, established_only=True,
           since=None, until=None):
    """`since`/`until` are ISO stamps bounding the round being published.

    The census file is append-only and outlives any one attempt at a round, so
    an abandoned run's sockets sit in it alongside the published one's. Counting
    both reports peaks from a configuration that was never published.
    """
    samples = load_samples(os.path.join(results_dir, "sockets.tsv"))
    owners = load_owners(os.path.join(results_dir, "sockets-pids.tsv"))
    if since or until:
        samples = collections.OrderedDict(
            (stamp, rows) for stamp, rows in samples.items()
            if (not since or stamp >= since) and (not until or stamp <= until))

    per_pid_max = collections.Counter()
    concurrent_foreign = 0
    windows = []
    for stamp, sockets in samples.items():
        counts = collections.Counter()
        for state, pid in sockets:
            if established_only and state != "ESTAB":
                continue
            counts[pid] += 1
        bench = {p: n for p, n in counts.items() if not is_production(p, owners, production)}
        foreign = {p: n for p, n in counts.items() if is_production(p, owners, production)}
        for pid, count in counts.items():
            per_pid_max[pid] = max(per_pid_max[pid], count)
        if len(bench) > 1:
            # two targets holding the account at once is the one rule the whole
            # comparison rests on
            concurrent_foreign += 1
        windows.append({"at": stamp, "bench": sum(bench.values()),
                        "foreign": sum(foreign.values()),
                        "bench_pids": len(bench)})

    targets, others = [], []
    for pid, peak in sorted(per_pid_max.items(), key=lambda kv: -kv[1]):
        row = {"pid": pid, "peak_sockets": peak,
               "comm": (owners.get(pid) or {}).get("comm", "?"),
               "cwd": (owners.get(pid) or {}).get("cwd", "?")}
        (others if is_production(pid, owners, production) else targets).append(row)

    return {
        "samples": len(samples),
        "window": ([next(iter(samples)), list(samples)[-1]] if samples else None),
        "targets": targets,
        "production": others,
        "samples_with_two_targets_live": concurrent_foreign,
        "isolation_held": concurrent_foreign == 0,
        "windows": windows,
    }


def render(report, budget=None):
    out = ["### Connection parity, from live sockets", "",
           f"{report['samples']} samples, one every five seconds.", ""]
    if report.get("window"):
        out += [f"Window: {report['window'][0]} to {report['window'][1]}.", ""]
    out.append("| pid | process | working directory | peak sockets |")
    out.append("|---|---|---|---|")
    for row in report["targets"]:
        out.append(f"| {row['pid']} | {row['comm']} | {row['cwd']} "
                   f"| {row['peak_sockets']} |")
    out.append("")
    if budget:
        over = [r for r in report["targets"] if r["peak_sockets"] > budget]
        under = [r for r in report["targets"] if r["peak_sockets"] < budget]
        out.append(f"Budget was {budget}. "
                   + (f"{len(over)} held more than that; " if over else "None held more; ")
                   + (f"{len(under)} never filled it."
                      if under else "every one of them filled it."))
        out.append("")
    if report["production"]:
        out.append("Sharing the account throughout, and not part of the field:")
        out.append("")
        for row in report["production"]:
            out.append(f"- `{row['comm']}` in `{row['cwd']}`, "
                       f"up to {row['peak_sockets']} sockets")
        out.append("")
    out.append("**Isolation: " + ("held" if report["isolation_held"] else
               f"BROKEN in {report['samples_with_two_targets_live']} samples")
               + ".** " + ("No sample caught two targets holding the account at "
                           "once." if report["isolation_held"] else
                           "Two targets held the account simultaneously, so the "
                           "rows either side of those samples are not isolated "
                           "measurements."))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir")
    ap.add_argument("--budget", type=int, default=int(os.environ.get("CONNS", "15")))
    ap.add_argument("--production", action="append", default=None,
                    help="a working directory whose sockets are not a target's")
    ap.add_argument("--since", help="ignore samples before this ISO stamp, so an "
                                    "abandoned attempt does not enter the census")
    ap.add_argument("--until")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = census(args.results_dir,
                    production=tuple(args.production or PRODUCTION_CWDS),
                    since=args.since, until=args.until)
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print(render(report, args.budget))
    return 0 if report["isolation_held"] else 1


if __name__ == "__main__":
    sys.exit(main())
