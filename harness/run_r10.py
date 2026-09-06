#!/usr/bin/env python3
"""Round 10: one target at a time, every phase, the whole field.

The isolation rule is unchanged and still the basis of the comparison: every
target keeps a pool of NNTP sockets warm, so two running at once oversubscribe
the account and skew both. This delegates that to `bench5.start`/`stop` rather
than reimplementing it -- those carry the SIGTERM-then-SIGKILL escalation, the
process-tree walk that catches a forked rclone, and the socket drain that turns
a wedged target into a crashed run instead of a contaminated measurement. Those
were learned the hard way and are not worth learning twice.

What is new is around them: the ceiling, the phases in metrics_r10, the shape
sampling in procmon_r10, the negative tier, and a field of ten rather than five.

Order rotates by repetition, so drift over an evening cannot favour whoever
always goes first.

Run:
    python3 run_r10.py --list
    python3 run_r10.py --targets raw,zurg,stremthru --entries plain-video
    python3 run_r10.py                       # the default field, every entry
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corpus_r10 as corpus          # noqa: E402
import damage_r10 as damage          # noqa: E402
import expect_r10 as expect          # noqa: E402
import procmon_r10 as procmon        # noqa: E402
import report_r10 as report          # noqa: E402
import targets_r10 as registry       # noqa: E402
from metrics_r10 import (complete, head_size, measure_integrity,  # noqa: E402
                         measure_playback, measure_seeks, timed_stream)

BENCH = registry.BENCH
IMPORT_POLL_S = 5
IMPORT_BUDGET_S = 900
SEQ_BYTES = 256 << 20
SEQ_BYTES_MAX = 2 << 30      # never read more than this to chase windows
SEQ_BUDGET_MS = 30_000
P05_TARGET_S = 12            # seconds of transfer a percentile wants under it


# --------------------------------------------------------------------------
# lifecycle, borrowed from bench5 so the drain logic has one home
# --------------------------------------------------------------------------
def load_lifecycle():
    """Import bench5 and point it at the round-10 field.

    bench5 keys everything off a module-level SPEC, so the registry is projected
    into that shape rather than bench5 being rewritten: rounds 3 through 9 are
    reproducible only while bench5 keeps behaving exactly as it did.
    """
    import bench5
    spec = {}
    for name in registry.TARGETS:
        target = registry.TARGETS[name]
        entry = {
            "port": target["port"],
            "url": target.get("url", ""),
            "ready": target.get("ready", ""),
            "kind": target["kind"],
            "auth": target.get("auth"),
        }
        if target["kind"] == "docker":
            entry["container"] = target.get("container", name)
        else:
            entry["start"] = target.get("start", "")
        spec[name] = entry
    bench5.SPEC = spec
    bench5.ALL = list(spec)
    return bench5


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------
def multipart(field, nzb_path):
    """One file part under a given field name.

    The field name is the whole reason this takes an argument. Six targets speak
    something SABnzbd-shaped and three spellings of the field are in use across
    them, so `registry.import_style` carries it per target rather than one call
    guessing on everyone's behalf.
    """
    boundary = "----r10bench"
    with open(nzb_path, "rb") as handle:
        payload = handle.read()
    name = os.path.basename(nzb_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
        f"Content-Type: application/x-nzb\r\n\r\n").encode()
    body += payload + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def post(url, body, content_type, timeout=300):
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, resp.read().decode("utf-8", "replace")[:400]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:160]


def refused(text):
    """A body that says no while the status line says yes.

    decypharr answers HTTP 200 with {"status": false, "error": "No files
    uploaded"} when the field name is wrong, so a status-code check imports
    nothing and then waits fifteen minutes for a release that was never queued.
    """
    flat = text.replace(" ", "")
    return '"status":false' in flat or "No files uploaded" in text


def sab_addfile(api_url, nzb_path, field="nzbfile", api_key=registry.API_KEY,
                category=None):
    """SABnzbd-shaped import, under whichever field name this target wants.

    A category is sent only when the target asks for one. The category decides
    where the release is filed, and the .NET family serves WebDAV under
    /content/<category>/ -- so an invented default of "bench" files every
    release somewhere the run does not look, and a successful import reads as a
    release that never appeared.
    """
    body, content_type = multipart(field, nzb_path)
    params = {"mode": "addfile", "apikey": api_key, "output": "json"}
    if category:
        params["cat"] = category
    query = urllib.parse.urlencode(params)
    ok, text = post(f"{api_url}?{query}", body, content_type)
    if not ok:
        return False, text
    if refused(text):
        return False, text[:200]
    return True, text[:200]


def drop_in(directory, nzb_path):
    """zurg imports by watching a directory, so the copy is the import.

    Never overwrite: a re-import of an entry already present would restart a
    load that is the thing being timed.
    """
    os.makedirs(directory, exist_ok=True)
    dest = os.path.join(directory, os.path.basename(nzb_path))
    if not os.path.exists(dest):
        shutil.copyfile(nzb_path, dest)
    return True, f"present at {dest}"


def hand_path(api_url, nzb_path, api_key=registry.API_KEY):
    """altmount is handed a path, and it MOVES the file rather than copying it.

    Its log records "Moved NZB to persistent storage" and the corpus file is
    gone from where it was. So it gets a throwaway copy, and the copy keeps the
    ORIGINAL filename because altmount names the release after the file it was
    handed: a uniquified filename produced a release called
    "am-import-1788277768923-ToyStory5Damaged" that no stem match could find,
    and six repair passes recorded "no release" for that reason alone. The
    directory is what gets uniquified.
    """
    scratch = os.path.join("/tmp", f"am-import-{int(time.time() * 1000)}")
    os.makedirs(scratch, exist_ok=True)
    throwaway = os.path.join(scratch, os.path.basename(nzb_path))
    shutil.copyfile(nzb_path, throwaway)
    body = json.dumps({"file_path": throwaway}).encode()
    ok, text = post(f"{api_url}?apikey={api_key}", body, "application/json")
    return ok and not refused(text), text[:200]


def deliver(target, nzb_path):
    """Hand one NZB to one target, its own way. Returns (accepted, detail)."""
    spec = registry.TARGETS[target]
    style = spec.get("import_style")
    if style == registry.DROP_DIR:
        return drop_in(spec["drop_dir"].format(bench=BENCH), nzb_path)
    if style == registry.PATH_JSON:
        return hand_path(spec["import_api"], nzb_path)
    if style in (registry.SAB_NZBFILE, registry.SAB_NAME, registry.SAB_STD):
        api = spec.get("sab_api") or f"http://127.0.0.1:{spec['port']}/api"
        return sab_addfile(api, nzb_path, field=registry.FIELD[style],
                           category=spec.get("category"))
    return False, f"no import style registered for {target}"


def propfind(url, auth, depth="1", timeout=240):
    cmd = ["curl", "-s", "--max-time", str(timeout), "-X", "PROPFIND",
           "-H", f"Depth: {depth}"]
    if auth:
        cmd += ["-u", f"{auth[0]}:{auth[1]}"]
    cmd.append(url)
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout + 30)
    except Exception:
        return ""


def children(url, auth):
    """Absolute child URLs one level under url, by the round-7 rules.

    Two traps, both already paid for: zurg answers PROPFIND with hrefs under a
    different prefix than the URL asked for, so a self-reference is not caught by
    comparing strings; and it answers PROPFIND on a file by returning that file
    as a child of itself, which makes every file look like a directory.
    """
    xml = propfind(url, auth)
    base = url if url.endswith("/") else url + "/"
    base_depth = len([p for p in urllib.parse.urlparse(base).path.split("/") if p])
    out = []
    for href in re.findall(r"<[Dd]:href>([^<]*)</[Dd]:href>", xml):
        absolute = urllib.parse.urljoin(base, href)
        if absolute.rstrip("/") == base.rstrip("/"):
            continue
        depth = len([p for p in urllib.parse.urlparse(absolute).path.split("/") if p])
        if depth <= base_depth:
            continue
        leaf = urllib.parse.unquote(absolute.rstrip("/").rsplit("/", 1)[-1])
        parent = urllib.parse.unquote(base.rstrip("/").rsplit("/", 1)[-1])
        if leaf == parent:
            continue
        out.append(absolute.rstrip("/"))
    return sorted(set(out))


VIDEO = re.compile(r"\.(mkv|mp4|avi|ts|m2ts)$", re.I)


def largest_video(url, auth, depth=0):
    """The release's feature file, not the first video in the listing.

    A target that preserves an archive's internal structure lists `Sample/`
    first, and a large ranged read of a 9 MB sample clip is a correct 416 that
    reads as a broken target.
    """
    best, best_size = None, -1
    for child in children(url, auth):
        leaf = urllib.parse.unquote(child.rsplit("/", 1)[-1])
        if VIDEO.search(leaf):
            if "sample" in leaf.lower():
                continue
            size = head_size(child, auth) or 0
            if size > best_size:
                best, best_size = child, size
        elif depth < 2:
            nested, nested_size = largest_video(child, auth, depth + 1)
            if nested and nested_size > best_size:
                best, best_size = nested, nested_size
    return best, best_size


def wait_for_release(target, stem, auth, budget=IMPORT_BUDGET_S):
    """Poll the listing for the release by name, never by 'whatever appeared'.

    A fixed sleep after an import is a guess about connection count, and picking
    whatever is new picks an unrelated release that finished loading late.
    """
    root = registry.TARGETS[target].get("root")
    if not root:
        return None, None, "target has no WebDAV root"
    deadline = time.time() + budget
    wanted = stem.lower()
    while time.time() < deadline:
        for child in children(root, auth):
            leaf = urllib.parse.unquote(child.rsplit("/", 1)[-1]).lower()
            if wanted in leaf or leaf in wanted:
                video, size = largest_video(child, auth)
                if video:
                    return video, size, None
        time.sleep(IMPORT_POLL_S)
    return None, None, f"release {stem} never appeared within {budget}s"


def import_entry(target, entry, nzb_path, auth):
    """Import one corpus entry and resolve a playable URL. Returns (url, size, meta)."""
    spec = registry.TARGETS[target]
    mode = spec["import_mode"]
    meta = {"import_mode": mode}
    started = time.time()

    if mode == registry.NONE:
        # the ceiling is started against one NZB and serves it at a fixed path
        url = spec["url"]
        size = head_size(url, auth)
        meta["import_s"] = round(time.time() - started, 3)
        return url, size, meta

    if mode == registry.SAB:
        ok, detail = deliver(target, nzb_path)
        meta["import_style"] = spec.get("import_style")
        meta["import_accepted"] = ok
        meta["import_detail"] = detail
        if not ok:
            meta["import_s"] = None
            return None, None, meta
        stem = os.path.splitext(os.path.basename(nzb_path))[0]
        url, size, error = wait_for_release(target, stem, auth)
        meta["import_s"] = round(time.time() - started, 3)
        if error:
            meta["error"] = error
        return url, size, meta

    # native and discovery modes need a per-target resolver, and none of them
    # has survived a run yet -- see targets_r10.TARGETS[...]["verified"]
    meta["import_s"] = None
    meta["error"] = (f"{mode} import for {target} is not implemented yet; this "
                     f"adapter is marked shakedown in the registry")
    return None, None, meta


# --------------------------------------------------------------------------
# phases
# --------------------------------------------------------------------------
def longer_read_for_p05(result, size, offset,
                        floor=SEQ_BYTES, ceiling=SEQ_BYTES_MAX):
    """How long the sequential read should have been, or None if it was fine.

    A fixed read length stops characterising anything once the link is quick.
    256 MB at 77 MB/s is three complete one-second windows, and a percentile
    needs five, so on the faster host the three fastest targets were precisely
    the ones that could not report a p05 -- the stall column went missing where
    it would have been most interesting.

    Only a read that finished on its own is worth extending. One stopped by the
    time budget is already as long as the budget allows, and a slow target has
    all the windows it needs anyway.
    """
    if result.get("p05_MBps") is not None:
        return None
    if result.get("truncated_by_budget") or result.get("error"):
        return None
    rate = result.get("MBps")
    if not rate or not size:
        return None
    want = int(rate * 1e6 * P05_TARGET_S)
    want = min(max(want, floor), ceiling, max(0, size - offset))
    return want if want > (result.get("bytes") or 0) else None


def measure_entry(target, url, size, auth, life, pids_fn):
    """Every read shape for one target-entry pair, with the process sampled throughout."""
    out = {}
    sampler = procmon.Sampler(pids_fn).start()

    cold = timed_stream(url, auth, 0, 1 << 20)
    out["cold_open_s"] = cold.get("total_s")
    out["cold_ttfb_s"] = cold.get("ttfb_s")
    out["cold_http"] = cold.get("http")
    out["cold_complete"] = complete(cold, 1 << 20)

    seq_off = min(int(size * 0.30), max(0, size - SEQ_BYTES)) if size else 0
    seq = timed_stream(url, auth, seq_off, SEQ_BYTES, max_ms=SEQ_BUDGET_MS)
    longer = longer_read_for_p05(seq, size, seq_off)
    if longer:
        retry = timed_stream(url, auth, seq_off, longer, max_ms=SEQ_BUDGET_MS)
        if retry.get("p05_MBps") is not None or (retry.get("windows") or 0) > (
                seq.get("windows") or 0):
            retry["lengthened_to"] = longer
            seq = retry
    out["seq_lengthened_to"] = seq.get("lengthened_to")
    out["MBps"] = seq.get("MBps")
    out["p05_MBps"] = seq.get("p05_MBps")
    out["p05_skipped"] = seq.get("p05_skipped")
    out["seq_bytes"] = seq.get("bytes")
    out["seq_windows"] = seq.get("windows")

    if size:
        out["seeks"] = measure_seeks(url, size, auth)
        out["playback"] = measure_playback(url, size, auth)
        out["integrity"] = measure_integrity(url, size, auth)

    shape = sampler.stop()
    delivered = (seq.get("bytes") or 0) + (cold.get("bytes") or 0)
    out["shape"] = procmon.summarise(sampler.samples, sampler.cpu_total_s,
                                     delivered or None)
    out["rss_peak_MB"] = shape.get("rss_peak_MB")
    return out


def start_for_entry(life, target, nzb, conns):
    """Start a target, filling in whatever its launch command needs.

    The ceiling is the reason this exists. `rawserve_r10.py` serves one NZB per
    process, so it has to be restarted per entry with that entry's file, where
    every other target is started once and imported into repeatedly.
    """
    spec = registry.TARGETS[target]
    start = spec.get("start")
    if spec["kind"] != "docker" and start:
        # every placeholder, not just {nzb}. Filling in only the ceiling's left
        # the other four native targets running `cd {bench}/zurgrun` literally,
        # so nothing started and the run recorded "never became ready" -- a
        # target that was never launched, reported as a target that would not
        # come up
        life.SPEC[target]["start"] = start.format(
            bench=BENCH, nzb=nzb or "", conns=conns)
    return life.start(target)


def run_target(target, entries, life, reps_tag, memory, conns):
    """Every entry against one target, inside that target's time budget.

    Everything is enabled by default, which makes failure isolation the whole
    job here: a target that wedges, deadlocks or never becomes ready has to cost
    its own rows and nothing else. Its remaining entries are recorded with the
    reason rather than dropped, so a short column in the report says why it is
    short.
    """
    spec = registry.TARGETS[target]
    auth = spec.get("auth")
    per_entry_restart = spec["import_mode"] == registry.NONE
    deadline = time.time() + registry.budget(target)
    rows = []
    started = False

    def pids_fn():
        try:
            return life.pids_for(target)
        except Exception:
            return []

    def abandon(remaining, reason):
        for pending in remaining:
            rows.append({"target": target, "entry": pending["id"],
                         "tier": pending.get("tier"),
                         "expect": pending.get("expect"), "tag": reps_tag,
                         "skipped": reason,
                         **expect.score(pending, {"error": reason}, None)})

    try:
        if not per_entry_restart:
            start_for_entry(life, target, None, conns)
            started = True
            memory.idle_rss_MB = procmon.sample_idle(
                pids_fn, seconds=5).get("idle_rss_MB")

        for ix, entry in enumerate(entries):
            if time.time() > deadline:
                abandon(entries[ix:], f"target budget of "
                                      f"{registry.budget(target)}s exhausted")
                break

            nzb = corpus.resolve(entry)
            row = {"target": target, "entry": entry["id"],
                   "tier": entry.get("tier"), "expect": entry.get("expect"),
                   "tag": reps_tag}
            if entry.get("needs_real_post") or not nzb or not os.path.exists(nzb):
                row.update(expect.score(entry, {}, None))
                row["skipped"] = "no post available for this entry"
                rows.append(row)
                continue

            try:
                if per_entry_restart:
                    if started:
                        life.stop(target)
                    start_for_entry(life, target, nzb, conns)
                    started = True
                    if memory.idle_rss_MB is None:
                        memory.idle_rss_MB = procmon.sample_idle(
                            pids_fn, seconds=5).get("idle_rss_MB")

                url, size, meta = import_entry(target, entry, nzb, auth)
                row.update(meta)
                row["url"] = url
                row["size"] = size
                if not url:
                    row.update(expect.score(
                        entry, {"http": None, "bytes": 0,
                                "error": meta.get("error")}, None))
                    rows.append(row)
                    continue

                measured = measure_entry(target, url, size, auth, life, pids_fn)
                row.update(measured)
                memory.record(measured.get("rss_peak_MB"))

                # the damaged entry gets the alignment-verified phase in the same
                # pass, on the URL already resolved, so the whole round stays one
                # command instead of a second script that has to re-find it
                if entry["id"] == "damaged-partial":
                    try:
                        row["damage"] = damage.run(url, auth, nzb)
                    except Exception as exc:
                        row["damage"] = {"error":
                                         f"{type(exc).__name__}: {exc}"[:200]}
                row.update(expect.score(
                    entry, {"http": measured.get("cold_http"),
                            "bytes": measured.get("seq_bytes"),
                            "accept_ranges": "bytes", "error": None},
                    measured.get("seq_bytes")))
            except Exception as exc:
                # one entry blowing up is a row, not the end of the target
                row["error"] = f"{type(exc).__name__}: {exc}"[:200]
                row.update(expect.score(entry, {"error": row["error"]}, None))

            rows.append(row)
            print(json.dumps({k: row.get(k) for k in
                              ("target", "entry", "outcome", "MBps", "p05_MBps",
                               "cold_open_s", "import_s")}), flush=True)

        if started:
            # what it still holds once the work stops, before it is killed
            time.sleep(20)
            memory.after_idle_MB = (procmon.rss_kb(pids_fn()) // 1024) or None
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"[:200]
        done = {r["entry"] for r in rows}
        abandon([e for e in entries if e["id"] not in done], reason)
        print(f"!! {target} abandoned: {reason}", flush=True)
    finally:
        try:
            life.stop(target)
        except Exception as exc:
            # a target that will not let go of the account contaminates whoever
            # runs next, so this is loud rather than swallowed
            print(f"!! {target} did not release the account: {exc}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", "--targets", dest="only", default="",
                    help="run exactly these, comma separated. Default is all of them")
    ap.add_argument("--disable", default="",
                    help="run everything except these, comma separated")
    ap.add_argument("--entries", default="",
                    help="corpus entries to use. Default is all of them")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--conns", type=int,
                    default=int(os.environ.get("CONNS", "15")),
                    help="connection budget, which must match every target's config")
    ap.add_argument("--tag", default="r10")
    ap.add_argument("--out", default=None)
    ap.add_argument("--derive", action="store_true",
                    help="build the negative tier from the corpus before running")
    ap.add_argument("--list", action="store_true",
                    help="print the field and the corpus, run nothing")
    args = ap.parse_args()

    names = registry.enabled(
        only=[t for t in args.only.split(",") if t] or None,
        disable=[t for t in args.disable.split(",") if t] or None)
    if not names:
        raise SystemExit("nothing left to run: every target was filtered out")

    if args.derive:
        built = corpus.derive_all()
        print(f"derived {len(built)} negative-tier entries", flush=True)

    wanted = [e for e in args.entries.split(",") if e]
    unknown = [e for e in wanted if e not in corpus.BY_ID]
    if unknown:
        raise SystemExit(f"unknown corpus entries: {', '.join(unknown)}")
    entries = [corpus.BY_ID[e] for e in wanted] if wanted else corpus.ENTRIES

    if args.list:
        print(json.dumps({
            "registered": registry.summary(),
            "running": names,
            "disabled": [n for n in registry.DEFAULT if n not in names],
            "shakedown": registry.needs_shakedown(names),
            "corpus": [{"id": e["id"], "tier": e.get("tier"),
                        "expect": e.get("expect"),
                        "available": bool(corpus.resolve(e)
                                          and os.path.exists(corpus.resolve(e)))}
                       for e in entries],
        }, indent=1))
        return

    life = load_lifecycle()
    # only the field, never everything registered: stop() frees a port by
    # killing whatever holds it, and a target that is not in this run may share
    # its default port with something on this host that is nobody's target
    for name in names:
        life.stop(name)
    rows, memories = [], {}
    for rep in range(args.reps):
        order = names[rep % len(names):] + names[:rep % len(names)]
        for target in order:
            memory = memories.setdefault(target, procmon.RunMemory())
            rows.extend(run_target(target, entries, life, f"{args.tag}.{rep}",
                                   memory, args.conns))

    out = {
        "tag": args.tag,
        "field": names,
        "disabled": [n for n in registry.DEFAULT if n not in names],
        "connections": args.conns,
        "rows": rows,
        "memory": {t: m.summary() for t, m in memories.items()},
        "capability": expect.tally(rows),
        "throughput": report.headline(rows, "MBps", names),
        "cold_open": report.headline(rows, "cold_open_s", names),
        "consensus": report.consensus(
            [{"target": r["target"], "entry": r["entry"], "offset": s["offset"],
              "md5": s.get("md5")}
             for r in rows for s in (r.get("integrity") or [])],
            exclude=lambda t, e: t == "raw" and e not in ("plain-video",
                                                          "damaged-partial")),
        "shakedown": registry.needs_shakedown(names),
    }
    path = args.out or os.path.join(BENCH, f"results_{args.tag}.json")
    with open(path, "w") as handle:
        json.dump(out, handle, indent=1)
    print(f"\nwrote {path}", flush=True)
    print(report.render_headline(out["throughput"], "Sequential throughput",
                                 unit=" MB/s", lower_is_better=False))


if __name__ == "__main__":
    main()
