#!/usr/bin/env python3
"""Round 14's per-metric tables and the all-metrics table, from the raw results.

    python3 harness/tables_r14.py > /tmp/tables.md

AIOStreams' figures come from its rerun without the disk cache
(results/round14/aiostreams-nocache), everything else from the main pass.

Latency counts only reads that could not have been served from memory. Each
target reads every entry in one process, and `damaged-partial` and `obfuscated`
are `plain-video`'s articles under other names, read after it: their cold open
(the first MiB) and their seeks hit offsets `plain-video` had just fetched. A
seek inside the range the entry's own sequential read had just covered is the
same thing within one entry. Both are left out of the latency tables.
"""
import json
from pathlib import Path
import statistics as st
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report_r10 as rep  # noqa: E402

RESULTS = HERE.parent / "results" / "round14"
POSITIVE = ("plain-video", "damaged-partial", "obfuscated", "rar-stored", "season-pack")
# entries no earlier entry in the pass shares articles with
FRESH = ("plain-video", "rar-stored", "season-pack")
NAMES = {"zurg": "zurg", "altmount": "AltMount", "infinidysk": "InfiniDysk", "nzbdav-og": "NZBDav-og",
         "decypharr": "decypharr", "aiostreams": "AIOStreams", "raw": "raw"}
APPS = ["nzbdav-og", "infinidysk", "altmount", "decypharr", "aiostreams", "zurg"]


def fresh_seeks(row):
    """First-byte times of the seeks that land outside the entry's own sequential read."""
    lo = row["seq_offset"]
    hi = lo + (row.get("seq_bytes") or 0)
    return [p["ttfb_s"] for p in row["seeks"]["points"]
            if p["ttfb_s"] is not None and not lo <= p["offset"] < hi]


def load():
    main = json.loads((RESULTS / "main.json").read_text())
    rerun = json.loads((RESULTS / "aiostreams-nocache" / "main.json").read_text())
    return main, rerun


def build(main, rerun):
    src = lambda t: rerun if t == "aiostreams" else main  # noqa: E731
    rows = lambda t, entries: [r for r in src(t)["rows"] if r["target"] == t and r["entry"] in entries]  # noqa: E731

    def med(t, f, entries=POSITIVE):
        v = [x for x in (f(r) for r in rows(t, entries)) if x is not None]
        return st.median(v) if v else None

    def resources(d):
        out = {}
        for line in rep.render_resources(d["memory"]).splitlines():
            c = [x.strip() for x in line.strip("|").split("|")]
            if len(c) == 7 and c[0] in NAMES:
                out[c[0]] = [float(x) for x in c[1:]]
        return out

    ra, rb = resources(main), resources(rerun)
    res = lambda t, i: (rb if t == "aiostreams" else ra)[t][i]  # noqa: E731
    seek_points = lambda t: [s for r in rows(t, FRESH) for s in fresh_seeks(r)]  # noqa: E731

    metrics = [  # key, title, short, unit, higher is better, value, format, note, note after
        ("seq", "Sequential throughput", "Throughput", "MB/s", True,
         lambda t: med(t, lambda r: r.get("MBps")), "{:.2f}",
         "Median over the five entries that should play. The worst clean-start swing between the two noise "
         "passes was 9.1%, so a difference smaller than that is not resolved by one pass: the top four are "
         "within it of each other, and so are zurg and AIOStreams. Each read is 1.6 GB or the rest of the "
         "file, more than any target's memory cache holds.",
         "InfiniDysk read the stored RAR entry at 2.27 MB/s against 27.88–56.90 for the rest, which pulls "
         "its median down on that one shape."),
        ("p05", "Stall floor", "Stall floor", "MB/s", True,
         lambda t: med(t, lambda r: r.get("p05_MBps")), "{:.2f}",
         "The 5th percentile of one-second windows during the sequential read, median over the entries "
         "that should play: how far the stream dips.", ""),
        ("cold", "Cold open", "Cold open", "ms", False,
         lambda t: 1000 * med(t, lambda r: r.get("cold_open_s"), FRESH), "{:.1f}",
         "Time to read the first MiB of a file just after its import, median over the three entries whose "
         "articles no earlier entry had read (`plain-video`, `rar-stored`, `season-pack`). A target that "
         "fetches the start of a file while importing it answers from memory here, which is a real "
         "advantage to a player.", ""),
        ("seek", "Seek, first byte", "Seek", "ms", False,
         lambda t: 1000 * st.median(seek_points(t)), "{:.0f}",
         "Time to the first byte of a jump to 1%, 25%, 50%, 75% and 95% of the file, counting only jumps "
         "to data the target had not read before: the three entries above, and only points outside the "
         "range the entry's own sequential read had just covered. That leaves 6–11 points per target, so "
         "neighbours within about a factor of two are not separated.", ""),
        ("imp", "Import", "Import", "s", False,
         lambda t: med(t, lambda r: r.get("import_s")), "{:.1f}",
         "From handing over the NZB to the file being listed. The harness checks the listing every 5 "
         "seconds, so about 5 s means \"listed by the first check\", and every median here is that: this "
         "does not separate the targets.", ""),
        ("cap", "Registered expectations met", "Expectations", "of 8", True,
         lambda t: src(t)["capability"][t]["correct"], "{:d}",
         "Five entries that should play and three that should be refused (see the matrix above); two more "
         "need real posts and were skipped for every target.", ""),
        ("cpu", "CPU time", "CPU", "s per GiB", False, lambda t: res(t, 0), "{:.2f}",
         "CPU seconds over startup, import and every read, per GiB delivered.", ""),
        ("cpu95", "CPU, 95th percentile", "CPU p95", "cores", False, lambda t: res(t, 1), "{:.2f}",
         "The 95th percentile of sampled CPU use.", ""),
        ("rss", "Peak memory", "Memory", "MiB RSS", False, lambda t: res(t, 2), "{:.0f}", "", ""),
        ("dr", "Disk reads", "Disk reads", "MiB per GiB", False, lambda t: res(t, 3), "{:.2f}",
         "Physical block reads per GiB delivered.", ""),
        ("dw", "Disk writes", "Disk writes", "MiB per GiB", False, lambda t: res(t, 4), "{:.2f}",
         "Physical block writes per GiB delivered.",
         "decypharr's writes are consistent with its new sparse per-stream disk cache, which upstream no "
         "longer caps at 256 MiB (source reading, not measured per file)."),
        ("st", "State growth", "State", "MiB", False, lambda t: res(t, 5), "{:.2f}",
         "Allocated growth of the target's own state directories over the pass.", ""),
    ]

    out = ["## Results by metric", "",
           "One table per metric, best first. AIOStreams' figures in every table are from its rerun without "
           "the disk cache (below); everything else is the main pass. `raw` reads the articles with no "
           "application in the way and is shown under the speed tables as the network ceiling, not ranked. "
           "Rebuild these tables with [`tables_r14.py`](../harness/tables_r14.py).", ""]
    summary = {}
    for key, title, _short, unit, higher, get, fmt, note, after in metrics:
        shown = {t: fmt.format(get(t)) for t in APPS}
        order = sorted(APPS, key=lambda t: -float(shown[t]) if higher else float(shown[t]))
        out += [f"### {title}", "", f"**{'Higher' if higher else 'Lower'} is better.** {note}".rstrip(), "",
                f"| Rank | Target | {unit} |", "|---|---|---|"]
        rank, prev = 0, None
        for i, t in enumerate(order):
            if shown[t] != prev:
                rank, prev = i + 1, shown[t]
            out.append(f"| {rank} | {NAMES[t]} | {shown[t]} |")
            summary.setdefault(t, {})[key] = (shown[t], rank)
        if key in ("seq", "cold", "seek"):
            out.append(f"| — | raw, network ceiling | {fmt.format(get('raw'))} |")
        out.append("")
        if after:
            out += [after, ""]
    final = ["## All metrics", "",
             "Every metric from the tables above, with each target's rank in that metric in brackets. "
             "↑ higher is better, ↓ lower is better. AIOStreams' figures are from its rerun without the disk "
             "cache; cold open and seek count only data the target had not read before.", "",
             "| Target | " + " | ".join(f"{m[2]} {'↑' if m[4] else '↓'} ({m[3]})" for m in metrics) + " |",
             "|---|" + "---|" * len(metrics)]
    for t in APPS:
        final.append(f"| {NAMES[t]} | " + " | ".join(f"{summary[t][m[0]][0]} ({summary[t][m[0]][1]})"
                                                    for m in metrics) + " |")
    return "\n".join(out), "\n".join(final)


if __name__ == "__main__":
    body, final = build(*load())
    print(body)
    print("<!-- all-metrics -->")
    print(final)
