#!/usr/bin/env python3
"""Byte-identity phase: prove every target serves the SAME bytes, not just the same runtime.

The throughput phase (bench5.py) writes every response to /dev/null and never
hashes anything, so the only cross-target equality it can show is timing. That
is why issue #8 is right: the README's "byte identity was verified" claim has
no evidence behind it for the throughput file -- equal ffprobe duration is not
equal bytes, and two servers can each stream 256 MB in the same wall time while
handing back different content.

So this phase does its own hashed read: the SAME fixed byte range from every
target, written to a temp file (not /dev/null) and md5'd, then compared. Same
isolation rule as every other phase -- one server alive at a time.
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, "/home/ben/bench")
from bench5 import SPEC, ALL, BENCH, start, stop, stop_all, curl_auth  # noqa: E402

# A fixed range shared by all targets: whatever byte identity means, it is only
# meaningful if every target is asked for the identical offset and length.
OFFSET = 2_000_000_000
LENGTH = 16 << 20  # 16 MiB


def read_range(name, tmp, off=OFFSET, length=LENGTH, timeout=900):
    """Fetch [off, off+length) from the target's throughput URL and md5 the bytes.

    Metadata comes back through curl's -w exactly like corpus5b.probe(): the
    body goes to a real file so it can be hashed, not to /dev/null.
    """
    cmd = (["curl", "-s", "-o", tmp, "--max-time", str(timeout)] + curl_auth(name)
           + ["-H", f"Range: bytes={off}-{off + length - 1}",
              "-w", "%{http_code} %{size_download} %{time_total}", SPEC[name]["url"]])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
        parts = (p.stdout.split() + ["?", "0", "0"])[:3]
        http, got, t = parts[0], int(parts[1]), float(parts[2])
    except Exception as e:
        return {"target": name, "http": "ERR", "bytes": 0, "asked": length,
                "complete": False, "md5": None, "s": 0, "error": str(e)[:120]}
    md5 = None
    if got:
        h = hashlib.md5()
        with open(tmp, "rb") as f:
            while c := f.read(1 << 20):
                h.update(c)
        md5 = h.hexdigest()
    return {"target": name, "http": http, "bytes": got, "asked": length,
            "complete": http == "206" and got == length, "md5": md5,
            "s": round(t, 2)}


def main():
    targets = sys.argv[1].split(",") if len(sys.argv) > 1 else ALL
    tmp = f"/tmp/byteid_r7_{os.getpid()}.bin"
    out = []
    stop_all()
    for name in targets:
        start(name)
        rec = read_range(name, tmp)
        stop(name)
        out.append(rec)
        print(json.dumps(rec), flush=True)
    # identity holds only if every target that actually served the full range
    # returned one and the same md5; a target that never delivered is not a vote
    complete = {r["target"]: r["md5"] for r in out if r["complete"]}
    summary = {"summary": True, "identical": bool(complete) and len(set(complete.values())) == 1,
               "md5s": complete, "offset": OFFSET, "length": LENGTH}
    out.append(summary)
    print(json.dumps(summary), flush=True)
    with open(f"{BENCH}/results_byteid.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
