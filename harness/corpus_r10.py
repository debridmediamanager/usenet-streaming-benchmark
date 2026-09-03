#!/usr/bin/env python3
"""Corpus registry with tiers and an expected outcome per entry.

Every corpus entry in rounds 3 through 9 was supposed to work. That is a real
blind spot rather than a gap in coverage: with nothing in the set that ought to
fail, no run could catch a target that answers a request it cannot actually
satisfy -- emitting bytes that are provably not the media, a zero-fill dressed
as a 206, or a built-in "sorry" clip served with a 200. Those all score as
success against a corpus where success is the only correct answer.

So each entry now carries `expect`, and the report scores four outcomes rather
than pass or fail:

    expect serve, served        -> pass
    expect serve, not served    -> FAIL          (a capability gap)
    expect reject, not served   -> refused       (the right answer)
    expect reject, served       -> WRONGLY SERVED (worse than failing)

The negative-tier entries are *derived* from the corpus already published, not
hunted for. Three of them can be built deterministically from an NZB this
repository ships, which means anyone can reproduce the tier without going and
finding adversarial posts of their own, and the derivation is exact rather than
a description of one:

    dead-post              every message id rewritten to one that cannot exist
    incomplete-archive-set one volume of a multi-volume set removed
    damaged-severe         a fixed fraction of content articles removed

Two more belong in the tier and cannot be derived, because no transformation of
a healthy post produces them: a genuinely compressed (not stored) archive, and
an encrypted archive whose password nobody has. They are registered here as
`needs_real_post` so a run reports them as not collected rather than quietly
omitting them, which would let the tier look complete when it is not.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(os.path.dirname(HERE), "corpus")
DERIVED = os.path.join(CORPUS, "derived")
NS = "http://www.newzbin.com/DTD/2003/nzb"

# tiers, in the order a run should attempt them: cheap sanity first, then the
# real comparison, then the entries whose only job is to be refused
TIERS = ("smoke", "core", "negative", "failure", "stress")

ENTRIES = [
    {
        "id": "plain-video",
        "tier": "core",
        "expect": "serve",
        "nzb": "ToyStory5.nzb",
        "why": "the throughput and latency file: a direct video, no archive layer",
    },
    {
        "id": "damaged-partial",
        "tier": "failure",
        "expect": "serve",
        "nzb": "ToyStory5Damaged.nzb",
        "why": ("one article of 1669 unreachable. A server is expected to serve the "
                "rest; what it does at the hole is the damage phase's subject, not "
                "a pass or fail on its own"),
    },
    {
        "id": "obfuscated",
        "tier": "core",
        "expect": "serve",
        "nzb": "Obfuscated.nzb",
        "why": "hash filenames and no extensions: classification by content, not by name",
    },
    {
        "id": "rar-stored",
        "tier": "core",
        "expect": "serve",
        "nzb": "FatherBrown.nzb",
        "why": "multi-volume stored RAR, streamable without unpacking",
    },
    {
        "id": "season-pack",
        "tier": "stress",
        "expect": "serve",
        "nzb": "Bosch.S01.nzb",
        "why": "24 GB across 20 files: import cost and directory shape at scale",
    },
    {
        "id": "dead-post",
        "tier": "negative",
        "expect": "reject",
        "derive": {"op": "dead_post", "from": "FatherBrown.nzb"},
        "why": ("no article exists. Serving anything at all means the engine "
                "invented it, and a 206 here is the clearest possible failure"),
    },
    {
        "id": "incomplete-archive-set",
        "tier": "negative",
        "expect": "reject",
        "derive": {"op": "drop_volume", "from": "FatherBrown.nzb", "volume": 3},
        "why": ("a volume of the set is absent, so the inner file cannot be "
                "reconstructed. An engine that streams past the gap is producing "
                "bytes that are not the media"),
    },
    {
        "id": "damaged-severe",
        "tier": "negative",
        "expect": "reject",
        "derive": {"op": "decimate", "from": "ToyStory5.nzb", "keep_every": 3},
        "why": ("two thirds of the content articles removed, far past what PAR2 "
                "could repair. Refusing is correct; a long clean-looking read is not"),
    },
    {
        "id": "compressed-archive",
        "tier": "negative",
        "expect": "reject",
        "needs_real_post": True,
        "why": ("a genuinely compressed RAR cannot be streamed without full "
                "extraction. No transformation of a stored archive produces one, "
                "so this needs a real post and is reported as not collected until "
                "there is one"),
    },
    {
        "id": "encrypted-no-password",
        "tier": "negative",
        "expect": "reject",
        "needs_real_post": True,
        "why": ("header-encrypted with no password available. Same reason: it has "
                "to be posted that way"),
    },
]

BY_ID = {e["id"]: e for e in ENTRIES}


# --------------------------------------------------------------------------
# derivation
# --------------------------------------------------------------------------
def _load(path):
    ET.register_namespace("", NS)
    return ET.parse(path)


def _files(root):
    return root.findall(f"{{{NS}}}file") or root.findall("file")


def _segments(fel):
    parent = fel.find(f"{{{NS}}}segments")
    if parent is None:
        parent = fel.find("segments")
    return parent, (list(parent) if parent is not None else [])


def _subject(fel):
    return fel.get("subject", "")


def op_dead_post(tree, **_):
    """Rewrite every message id so no article can be found.

    The ids stay well formed and stay unique -- a malformed id would be refused
    by the server's parser and would test the parser rather than the engine.
    The digest is of the original id, so the transformation is deterministic and
    two people deriving this entry get byte-identical NZBs.
    """
    root = tree.getroot()
    touched = 0
    for fel in _files(root):
        _, segs = _segments(fel)
        for sel in segs:
            original = (sel.text or "").strip()
            token = hashlib.sha256(original.encode()).hexdigest()[:24]
            sel.text = f"{token}@dead.invalid"
            touched += 1
    return {"segments_rewritten": touched}


def op_drop_volume(tree, volume=3, **_):
    """Remove one volume of a multi-volume archive, leaving the set unsatisfiable."""
    root = tree.getroot()
    pattern = re.compile(r"\.(?:part0*%d\.rar|r0*%d)\b" % (volume, volume - 1), re.I)
    removed = []
    for fel in list(_files(root)):
        if pattern.search(_subject(fel)):
            root.remove(fel)
            removed.append(_subject(fel)[:80])
    if not removed:
        raise SystemExit(
            f"no volume {volume} found; subjects are:\n  "
            + "\n  ".join(_subject(f)[:100] for f in _files(root)))
    return {"files_removed": removed}


def op_decimate(tree, keep_every=3, **_):
    """Remove all but every Nth article from the content files.

    PAR2 volumes are left alone. Removing them too would make this an entry
    about missing recovery data; leaving them makes it an entry about damage far
    past what recovery data can fix, which is the case worth scoring.
    """
    root = tree.getroot()
    dropped = kept = 0
    for fel in _files(root):
        if ".par2" in _subject(fel).lower():
            continue
        parent, segs = _segments(fel)
        for ix, sel in enumerate(segs):
            if ix % keep_every:
                parent.remove(sel)
                dropped += 1
            else:
                kept += 1
    return {"segments_dropped": dropped, "segments_kept": kept}


OPS = {"dead_post": op_dead_post, "drop_volume": op_drop_volume,
       "decimate": op_decimate}


def derive(entry, corpus_dir=CORPUS, out_dir=DERIVED):
    """Build one derived NZB. Returns its path and what the transformation did."""
    spec = entry.get("derive")
    if not spec:
        return None, {"skipped": "not a derived entry"}
    source = os.path.join(corpus_dir, spec["from"])
    if not os.path.exists(source):
        raise SystemExit(f"{source} not found. Extract the corpus first: "
                         f"7z x -pdmmbench {corpus_dir}/corpus.7z -o{corpus_dir}")
    tree = _load(source)
    params = {k: v for k, v in spec.items() if k not in ("op", "from")}
    detail = OPS[spec["op"]](tree, **params)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{entry['id']}.nzb")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    with open(path, "rb") as handle:
        detail["sha256"] = hashlib.sha256(handle.read()).hexdigest()[:16]
    detail["source"] = spec["from"]
    detail["op"] = spec["op"]
    return path, detail


def derive_all(corpus_dir=CORPUS, out_dir=DERIVED):
    out = {}
    for entry in ENTRIES:
        if entry.get("derive"):
            path, detail = derive(entry, corpus_dir, out_dir)
            detail["path"] = os.path.relpath(path, os.path.dirname(HERE))
            out[entry["id"]] = detail
    return out


def resolve(entry, corpus_dir=CORPUS, out_dir=DERIVED):
    """Path to an entry's NZB, or None when it has no post yet."""
    if entry.get("needs_real_post"):
        return None
    if entry.get("derive"):
        return os.path.join(out_dir, f"{entry['id']}.nzb")
    return os.path.join(corpus_dir, entry["nzb"])


def manifest(corpus_dir=CORPUS, out_dir=DERIVED):
    rows = []
    for entry in ENTRIES:
        row = copy.deepcopy(entry)
        path = resolve(entry, corpus_dir, out_dir)
        row["path"] = os.path.relpath(path, os.path.dirname(HERE)) if path else None
        row["available"] = bool(path and os.path.exists(path))
        rows.append(row)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("derive", "list"))
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--out", default=DERIVED)
    args = ap.parse_args()
    if args.command == "derive":
        print(json.dumps(derive_all(args.corpus, args.out), indent=1))
    else:
        print(json.dumps(manifest(args.corpus, args.out), indent=1))
