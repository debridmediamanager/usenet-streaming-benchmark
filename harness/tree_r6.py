#!/usr/bin/env python3
"""Round 6: what each server puts on the filesystem.

Same isolation rule as every earlier round -- exactly one target holds the news
account at a time, imports included -- but the measurement is different. Each
target starts from an empty library, is given the identical five NZBs, and is
then mounted read-only over rclone so `tree` can record the namespace it built.

Two things make the dump comparable across five servers that each expose a
different WebDAV shape:

  * the mount is the server's own WebDAV root, discovered by PROPFIND at run
    time rather than hardcoded, so the dump starts where the server's namespace
    starts and nothing is cropped by a guess;
  * rclone flags are identical for all five and the VFS cache is off, so what
    `tree` walks is the server's listing and not a cache of one.

Where a server ships its own mount (zurg's rclone mount, decypharr's dfs) that
mount is dumped as well, since that is what its users actually see.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse

BENCH = "/home/ben/bench"
RUN = f"{BENCH}/r6"
MNT = f"{BENCH}/r6mnt"
RCLONE = f"{BENCH}/bin/rclone"
AUTH = ("usenet", "usenet")
API_KEY = "benchbenchbenchbenchbenchbench12"

# The corpus is a file rather than a literal so the run and the report always
# name the same five releases. Every entry is a release that STAT-probed clean
# against the news account first; packing shape is deliberately varied.
CORPUS_FILE = f"{RUN}/corpus.txt"
CORPUS = [l.strip() for l in open(CORPUS_FILE) if l.strip() and not l.startswith("#")]

SPEC = {
    "zurg": {
        "kind": "native", "port": 9998, "auth": None,
        "start": f"cd {BENCH}/zurgrun && nohup ./zurg > zurg.r6.log 2>&1 &",
        "ready": "http://localhost:9998/dav/",
        "namespace": "http://localhost:9998/dav/",
        "content": "http://localhost:9998/dav/all/",
        "native_mount": f"{BENCH}/zmnt",
    },
    "altmount": {
        "kind": "native", "port": 8081, "auth": AUTH,
        "start": (f"cd {BENCH}/altmount && nohup ./altmount-cli-linux-amd64 serve "
                  f"--config ./config.yaml > altmount.r6.out 2>&1 &"),
        "ready": "http://localhost:8081/webdav/",
        "namespace": "http://localhost:8081/webdav/",
        "content": "http://localhost:8081/webdav/complete/",
        "native_mount": None,
    },
    "infinidysk": {
        "kind": "docker", "port": 8092, "auth": AUTH, "container": "infinidysk-r6",
        "ready": "http://127.0.0.1:8092/health",
        "namespace": "http://127.0.0.1:8092/",
        "content": "http://127.0.0.1:8092/content/uncategorized/",
        "native_mount": None,
    },
    "nzbdav-og": {
        "kind": "docker", "port": 8093, "auth": AUTH, "container": "nzbdav-r6",
        "ready": "http://127.0.0.1:8093/health",
        "namespace": "http://127.0.0.1:8093/",
        "content": "http://127.0.0.1:8093/content/uncategorized/",
        "native_mount": None,
    },
    "decypharr": {
        "kind": "native", "port": 8282, "auth": None,
        "start": (f"cd {BENCH}/decyrun && nohup {BENCH}/decypharr "
                  f"--config {BENCH}/decyrun/ > decypharr.r6.log 2>&1 &"),
        "ready": "http://localhost:8282/webdav/",
        "namespace": "http://localhost:8282/webdav/",
        "content": "http://localhost:8282/webdav/__all__/",
        "native_mount": f"{BENCH}/dmnt",
    },
}
ORDER = ["zurg", "altmount", "infinidysk", "nzbdav-og", "decypharr"]


def sh(cmd, timeout=900):
    try:
        p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                           timeout=timeout)
        return p.stdout.strip()
    except Exception as e:
        return f"ERR {str(e)[:120]}"


def spawn(cmd):
    subprocess.run(["bash", "-c", cmd], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def curl_auth(name):
    a = SPEC[name]["auth"]
    return ["-u", f"{a[0]}:{a[1]}"] if a else []


def pid_on(port):
    out = sh(f"lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null")
    return int(out.split()[0]) if out else None


PROD_ZURG_PID = sh("systemctl show -p MainPID --value zurg.service") or "0"


def nntp_sockets():
    """Sockets on :563 that belong to a bench target.

    zen runs a production zurg.service on the same account and keeps a couple
    warm at idle, so a plain count never reaches zero. Exclude that one PID.
    """
    out = sh("ss -tnp 2>/dev/null | grep ':563'")
    return sum(1 for line in out.splitlines()
               if line.strip() and f"pid={PROD_ZURG_PID}," not in line)


def stop(name):
    s = SPEC[name]
    if s["kind"] == "docker":
        sh(f"docker stop {s['container']} >/dev/null 2>&1", timeout=120)
    else:
        pid = pid_on(s["port"])
        if pid:
            sh(f"kill {pid}")
    for _ in range(60):
        if not pid_on(s["port"]):
            break
        time.sleep(1)
    for _ in range(60):
        if nntp_sockets() == 0:
            break
        time.sleep(1)
    time.sleep(2)


def stop_all():
    for n in ORDER:
        stop(n)


def api_ready(name):
    """True once the server will actually answer work, not merely a socket.

    'Any HTTP code that is not 000' is not readiness. infinidysk and nzbdav run
    53 EF migrations the first time they see an empty database, and while that
    runs the API answers an EMPTY body with no status line -- which the old
    check treated as up, so every upload was fired into a port that was not
    listening yet and came back blank. Both were then measured as publishing
    nothing. Ask the endpoint that does the work instead.
    """
    s = SPEC[name]
    if name in ("infinidysk", "nzbdav-og"):
        r = sh(f"curl -s --max-time 10 "
               f"'http://127.0.0.1:{s['port']}/api?mode=queue&apikey={API_KEY}'")
        return '"status":true' in r.replace(" ", "") or '"queue"' in r
    # The three Go targets have no migration step, so a listening port that
    # answers anything is genuinely ready. Probing the CONTENT path instead is
    # wrong: on an empty library it does not exist yet, so altmount reported
    # not-ready for the full 600s timeout and then worked fine anyway.
    if pid_on(s["port"]) is None:
        return False
    code = sh(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "
              + " ".join(curl_auth(name)) + f" {s['namespace']}")
    return bool(code) and code != "000"


def start(name, cap=600):
    s = SPEC[name]
    if s["kind"] == "docker":
        sh(f"docker start {s['container']} >/dev/null 2>&1", timeout=120)
    else:
        spawn(s["start"])
    t0 = time.time()
    ready = False
    while time.time() - t0 < cap:
        time.sleep(2)
        if api_ready(name):
            ready = True
            break
    time.sleep(6)
    return {"ready": ready, "ready_s": round(time.time() - t0)}


# ---------------------------------------------------------------- reset

def stage_corpus(name):
    """Fresh copy of every NZB for this target, before every run.

    Not a one-time setup step: altmount *moves* the file it imports out to its
    own queue storage, so a second run against the same directory imports
    nothing and reports "File does not exist" for all five. Staging per run
    also keeps a re-run of one target identical to its first run.
    """
    d = f"{BENCH}/r6-nzbs/{name}"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    for n in CORPUS:
        for src_dir in ("nzbs", "tvnzbs", "newnzbs"):
            src = f"{BENCH}/{src_dir}/{n}"
            if os.path.exists(src):
                shutil.copy2(src, f"{d}/{n}")
                break
    return sorted(os.listdir(d))


def reset(name):
    """Empty library, provider config kept."""
    if name == "zurg":
        for d in ("data", "nzbs", "dump"):
            shutil.rmtree(f"{BENCH}/zurgrun/{d}", ignore_errors=True)
            os.makedirs(f"{BENCH}/zurgrun/{d}", exist_ok=True)
        return "data/ nzbs/ dump/ emptied"
    if name == "altmount":
        cfg = f"{BENCH}/altmount/cfg"
        for f in os.listdir(cfg):
            if f.startswith("altmount.db"):
                os.remove(f"{cfg}/{f}")
        for d in ("metadata", ".nzbs"):
            shutil.rmtree(f"{cfg}/{d}", ignore_errors=True)
            os.makedirs(f"{cfg}/{d}", exist_ok=True)
        return "altmount.db metadata/ .nzbs/ removed"
    if name == "decypharr":
        for d in ("db", "usenet", "streams", "downloads", "logs"):
            shutil.rmtree(f"{BENCH}/decyrun/{d}", ignore_errors=True)
            os.makedirs(f"{BENCH}/decyrun/{d}", exist_ok=True)
        shutil.rmtree(f"{BENCH}/dfscache", ignore_errors=True)
        os.makedirs(f"{BENCH}/dfscache", exist_ok=True)
        return "db/ usenet/ streams/ downloads/ dfscache/ emptied"
    if name == "infinidysk":
        # every setting arrives by environment variable, so an empty dir is a
        # clean library rather than an unconfigured server
        shutil.rmtree(f"{BENCH}/infinidysk/config-r6", ignore_errors=True)
        os.makedirs(f"{BENCH}/infinidysk/config-r6", exist_ok=True)
        return "config-r6/ recreated empty (provider comes from env)"
    if name == "nzbdav-og":
        # settings live in the same sqlite file as the library, so the library
        # tables are cleared and ConfigItems is kept
        src = f"{BENCH}/nzbdav-og/config/db.sqlite"
        dst_dir = f"{BENCH}/nzbdav-og/config-r6"
        shutil.rmtree(dst_dir, ignore_errors=True)
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, f"{dst_dir}/db.sqlite")
        c = sqlite3.connect(f"{dst_dir}/db.sqlite")
        for t in ("HistoryItems", "NzbNames", "QueueItems", "QueueNzbContents",
                  "DavNzbFiles", "DavRarFiles", "DavMultipartFiles",
                  "BlobCleanupItems", "DavCleanupItems", "HistoryCleanupItems",
                  "NzbBlobCleanupItems", "HealthCheckResults", "HealthCheckStats"):
            try:
                c.execute(f"delete from {t}")
            except Exception:
                pass
        # keep only the five fixed system rows: /, /nzbs, /content, ...
        c.execute("delete from DavItems where Id not like '00000000-0000-0000-0000-%'")
        row = c.execute("select ConfigValue from ConfigItems "
                        "where ConfigName='usenet.providers'").fetchone()
        if row:
            c.execute("update ConfigItems set ConfigValue=? "
                      "where ConfigName='usenet.providers'",
                      (row[0].replace("news.news-provider.example",
                                      "news.news-provider.example"),))
        c.commit()
        n = c.execute("select count(*) from DavItems").fetchone()[0]
        c.close()
        return f"config-r6/db.sqlite reseeded, {n} system DavItems kept"
    return "?"


# ---------------------------------------------------------------- import

# Resolved after start() by asking the server, never assumed. Two candidates
# exist and which one works is not guessable: the configured key arrives by
# environment variable, while a fresh database also mints its own api.key row.
# On infinidysk the environment wins and the database row answers 401 -- and a
# rejected upload comes back with an EMPTY body, which a status-code check reads
# as success. So the key is probed against an authenticated endpoint first.
API_KEYS = {}

DB_FOR = {
    "infinidysk": f"{BENCH}/infinidysk/config-r6/db.sqlite",
    "nzbdav-og": f"{BENCH}/nzbdav-og/config-r6/db.sqlite",
}


def db_api_key(name):
    db = DB_FOR.get(name)
    if not db or not os.path.exists(db):
        return None
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = c.execute("select ConfigValue from ConfigItems "
                        "where ConfigName='api.key'").fetchone()
        c.close()
        return row[0] if row else None
    except Exception:
        return None


def resolve_api_key(name):
    """Whichever candidate key the server actually accepts."""
    if name not in ("infinidysk", "nzbdav-og"):
        API_KEYS[name] = API_KEY
        return {"key": API_KEY, "source": "configured"}
    port = SPEC[name]["port"]
    for src, key in (("configured", API_KEY), ("database", db_api_key(name))):
        if not key:
            continue
        r = sh(f"curl -s --max-time 30 "
               f"'http://127.0.0.1:{port}/api?mode=queue&apikey={key}'")
        if r and '"status":false' not in r.replace(" ", "") \
                and "Incorrect" not in r and "Unauthorized" not in r:
            API_KEYS[name] = key
            return {"key": key, "source": src, "probe": r[:120]}
    API_KEYS[name] = API_KEY
    return {"key": API_KEY, "source": "fallback-configured", "probe": r[:160]}


def import_nzb(name, nzb):
    src = f"{BENCH}/r6-nzbs/{name}/{nzb}"
    key = API_KEYS.get(name, API_KEY)
    t0 = time.time()
    if name == "zurg":
        r = sh(f"cp -f {src} {BENCH}/zurgrun/nzbs/{nzb} && echo dropped")
    elif name == "altmount":
        r = sh(f"curl -s --max-time 300 -X POST "
               f"'http://localhost:8081/api/import/file?apikey={key}' "
               f"-H 'Content-Type: application/json' "
               f"-d '{{\"file_path\":\"{src}\"}}'")
    elif name in ("infinidysk", "nzbdav-og"):
        port = 8092 if name == "infinidysk" else 8093
        r = sh(f"curl -s --max-time 300 -X POST "
               f"'http://127.0.0.1:{port}/api?mode=addfile&apikey={key}' "
               f"-F 'nzbFile=@{src}'")
    elif name == "decypharr":
        # one SAB mock at /sabnzbd/api, upload field is `name`. A wrong field
        # answers {"status": false} with HTTP 200, so check the body.
        r = sh(f"curl -s --max-time 300 -X POST 'http://localhost:8282/sabnzbd/api"
               f"?mode=addfile&apikey={key}&cat=tv' -F 'name=@{src}'")
    else:
        r = "?"
    flat = r.replace(" ", "")
    failed = (not r) or '"status":false' in flat or "Incorrect" in r \
        or "Unauthorized" in r or "No files uploaded" in r \
        or '"error":{' in flat or "VALIDATION_ERROR" in r
    return {"nzb": nzb, "response": r[:300], "accepted": not failed,
            "s": round(time.time() - t0, 2)}


# ---------------------------------------------------------------- listing

def propfind(name, url, depth="1", timeout=300):
    cmd = (["curl", "-s", "--max-time", str(timeout), "-X", "PROPFIND",
            "-H", f"Depth: {depth}"] + curl_auth(name) + [url])
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout + 30)
    except Exception:
        return ""


def children(name, url):
    xml = propfind(name, url)
    base = url if url.endswith("/") else url + "/"
    nd = len([x for x in urllib.parse.urlparse(base).path.split("/") if x])
    out = []
    for h in re.findall(r"<[Dd]:href>([^<]*)</[Dd]:href>", xml):
        a = urllib.parse.urljoin(base, h)
        if len([x for x in urllib.parse.urlparse(a).path.split("/") if x]) <= nd:
            continue
        out.append(urllib.parse.unquote(a.rstrip("/").rsplit("/", 1)[-1]))
    return sorted(set(out))


# Root choice is fixed per target rather than discovered. Pass A discovered it
# and got a different DEPTH per server -- two targets were dumped at their whole
# namespace and two at just their content directory, which makes the entry
# counts incomparable. `content` is where an imported release lands on each
# server (the same roots earlier rounds compared); `namespace` is the top of the
# server's WebDAV, listed one level deep so "what else does it publish" is a
# separate, cheap observation rather than a confound in the tree.


def settle(name, root, cap=1500, quiet=90):
    """Wait until the listing under root stops changing."""
    t0 = time.time()
    last, stable_since = None, time.time()
    while time.time() - t0 < cap:
        now = children(name, root)
        if now != last:
            last, stable_since = now, time.time()
        elif last and time.time() - stable_since >= quiet:
            break
        time.sleep(10)
    return {"settle_s": round(time.time() - t0), "root_entries": last or []}


# ---------------------------------------------------------------- mount

def umount(path):
    sh(f"fusermount3 -uz {path} 2>/dev/null; fusermount -uz {path} 2>/dev/null; true")
    time.sleep(1)


def mount(name, url):
    umount(MNT)
    os.makedirs(MNT, exist_ok=True)
    a = SPEC[name]["auth"]
    auth = ""
    if a:
        obs = sh(f"{RCLONE} obscure {a[1]}")
        auth = f"--webdav-user={a[0]} --webdav-pass={obs}"
    cmd = (f"{RCLONE} mount :webdav: {MNT} --webdav-url='{url}' "
           f"--webdav-vendor=other {auth} --read-only "
           f"--vfs-cache-mode=off --buffer-size=32M "
           f"--dir-cache-time=10s --attr-timeout=1s --timeout=10m "
           f"--daemon --log-file={BENCH}/r6-rclone.log --log-level=INFO "
           f"</dev/null >/dev/null 2>&1")
    sh(cmd, timeout=120)
    for _ in range(60):
        if sh(f"mountpoint -q {MNT} && echo yes") == "yes":
            return True
        time.sleep(1)
    return False


VIDEO_RE = re.compile(r"\.(mkv|mp4|avi|ts|m4v)$", re.I)


def videos_from_tree(tree_json, mount):
    """Largest non-sample video under each top-level release, from the dump.

    Reads the tree that was just captured rather than walking the mount a
    second time: over WebDAV a blanket walk costs minutes, and re-walking could
    also disagree with the dump the report quotes.
    """
    try:
        with open(tree_json) as fh:
            doc = json.load(fh)
    except Exception:
        return {}
    root = next((n for n in doc if n.get("type") == "directory"), None)
    if root is None:
        return {}
    out = {}

    def walk(node, rel, top):
        for c in node.get("contents", []) or []:
            nm = c.get("name", "")
            path = f"{rel}/{nm}" if rel else nm
            if c.get("type") == "directory":
                walk(c, path, top or nm)
            elif VIDEO_RE.search(nm) and not re.search(r"sample", nm, re.I):
                sz = c.get("size") or 0
                key = top or nm
                if key not in out or sz > out[key][1]:
                    out[key] = (os.path.join(mount, path), sz)

    walk(root, "", None)
    return out


def read_probe(path, tree_json, mb=8):
    """Read real bytes out of the mount, once per release.

    dd through the mount rather than curl at the WebDAV URL: the filesystem is
    what a player opens, and it is the layer the whole round is about.
    """
    res = []
    vids = videos_from_tree(tree_json, path)
    if not vids:
        return res
    for rel, (fp, sz) in vids.items():
        skip = 100 if sz > (108 << 20) else 0
        t0 = time.time()
        out = sh(f"timeout 600 dd if='{fp}' bs=1M skip={skip} count={mb} 2>/dev/null "
                 f"| tee /tmp/r6probe.bin | wc -c", timeout=660)
        dt = round(time.time() - t0, 2)
        try:
            got = int(out.strip().splitlines()[-1])
        except Exception:
            got = 0
        allz = None
        if got:
            with open("/tmp/r6probe.bin", "rb") as fh:
                allz = True
                while chunk := fh.read(1 << 20):
                    if any(chunk):
                        allz = False
                        break
        res.append({
            "release": rel,
            "file": os.path.relpath(fp, path),
            "file_bytes": sz,
            "offset_MB": skip,
            "asked_MB": mb,
            "got_bytes": got,
            "complete": got == mb << 20,
            "all_zero": allz,
            "s": dt,
            "MBps": round(got / dt / 1e6, 2) if dt and got else 0,
        })
    return res


def tree_dump(path, tag, outdir):
    """Human dump for the report, JSON dump for the tally."""
    res = {"path": path}
    human = sh(f"timeout 1200 tree -a -h -F --dirsfirst --charset=ascii '{path}'",
               timeout=1300)
    with open(f"{outdir}/tree.{tag}.txt", "w") as f:
        f.write(human + "\n")
    res["lines"] = len(human.splitlines())
    j = sh(f"timeout 1200 tree -a -J -s --dirsfirst '{path}'", timeout=1300)
    try:
        parsed = json.loads(j)
        with open(f"{outdir}/tree.{tag}.json", "w") as f:
            json.dump(parsed, f)
        res["json_ok"] = True
    except Exception as e:
        res["json_ok"] = False
        res["json_error"] = str(e)[:120]
    tail = human.strip().splitlines()[-1:] or [""]
    res["tree_report"] = tail[0]
    return res


# ---------------------------------------------------------------- run

def run_one(name, outdir):
    rec = {"target": name, "started_utc": time.strftime("%FT%TZ", time.gmtime())}
    stop_all()
    rec["reset"] = reset(name)
    rec["staged"] = stage_corpus(name)
    rec["start"] = start(name)
    rec["up"] = pid_on(SPEC[name]["port"]) is not None or SPEC[name]["kind"] == "docker"
    rec["api_key"] = resolve_api_key(name)
    root = SPEC[name]["content"]
    rec["dav_root"] = root
    rec["namespace_root"] = SPEC[name]["namespace"]
    rec["namespace_before"] = children(name, SPEC[name]["namespace"])
    rec["root_before"] = children(name, root)
    rec["imports"] = [import_nzb(name, n) for n in CORPUS]
    rec.update(settle(name, root))
    rec["namespace_after"] = children(name, SPEC[name]["namespace"])
    rec["mounted"] = mount(name, root)
    if rec["mounted"]:
        rec["tree"] = tree_dump(MNT, name, outdir)
        rec["reads"] = read_probe(MNT, f"{outdir}/tree.{name}.json")
        umount(MNT)
    nm = SPEC[name]["native_mount"]
    if nm and sh(f"mountpoint -q {nm} && echo yes") == "yes":
        rec["native_tree"] = tree_dump(nm, f"{name}.native", outdir)
        rec["native_reads"] = read_probe(nm, f"{outdir}/tree.{name}.native.json")
    rec["finished_utc"] = time.strftime("%FT%TZ", time.gmtime())
    stop(name)
    return rec


def main():
    targets = sys.argv[1].split(",") if len(sys.argv) > 1 else ORDER
    os.makedirs(RUN, exist_ok=True)
    out = []
    for name in targets:
        print(f"=== {name} {time.strftime('%FT%TZ', time.gmtime())}", flush=True)
        try:
            rec = run_one(name, RUN)
        except Exception as e:
            rec = {"target": name, "fatal": str(e)[:300]}
        out.append(rec)
        print(json.dumps({k: v for k, v in rec.items()
                          if k not in ("root_before",)})[:1500], flush=True)
        with open(f"{RUN}/results_tree_r6.json", "w") as f:
            json.dump(out, f, indent=1)
    stop_all()
    print("TREE_R6_DONE", flush=True)


if __name__ == "__main__":
    main()
