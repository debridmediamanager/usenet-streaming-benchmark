#!/usr/bin/env python3
"""The round-10 field: what is measured, how each one is driven, and what it is.

Rounds 3 through 9 measured five targets, all of them mounts. That is the right
field for the question "what should back a Plex library" and it is not the whole
field: four of the most used projects that stream Usenet on demand answer over
HTTP Range as Stremio addons instead, and none of them had ever been in a round
here.

Adding them raises a comparison problem that has to be handled rather than
ignored. An addon walks discovery, import and link-minting in a path a mount
never touches, so a single cold-open number puts them behind by however long
their import takes and calls it slowness. Every target therefore records
`import_s` and `open_s` separately, and the composite `click_to_byte_s` is the
only one of the three that compares across serving modes. `SERVE_MODE` says
which family a row belongs to so a report never silently ranks across them.

Provenance of every endpoint below is recorded in `verified`. `upstream` means
it was read out of that project's own repository; `shakedown` means it is
written from its documentation and has not yet survived a run, which is a state
this file says out loud rather than letting a first round discover it as a row
of zeros.

Two projects that look like they belong here and do not:

  * UsenetStreamer (Sanket9225, 380 stars) is a search and indexer front end
    that hands streaming to NZBDav -- its own health checks describe an archive
    as playable when "the archive format is supported by NZBDav". Benchmarking
    it would re-measure nzbdav with a search layer in front, and report the
    result under a second name.
  * Usenet-Ultimate (DSmart33) has not been pushed since 2026-05-26.
"""
import json
import os

BENCH = os.environ.get("BENCH", "/home/ben/bench")
AUTH = ("usenet", "usenet")
API_KEY = "benchbenchbenchbenchbenchbench12"

# how a target hands over bytes. Rows from different families are comparable on
# click_to_byte_s and on throughput; they are not comparable on import alone
WEBDAV = "webdav"
HTTP_RANGE = "http-range"

# how a release gets into a target
SAB = "sabnzbd"          # SABnzbd-compatible: the same import path for six of these
NATIVE_API = "native"    # its own upload endpoint
DISCOVERY = "discovery"  # no import at all; it must be offered a release to find
NONE = "none"            # nothing to import, the URL is the release

# ...and the wire shape it wants, which is a separate question from the family
# above. "SABnzbd-compatible" describes six of these targets and no two of them
# agree on how the file arrives: one watches a directory, one is handed a path
# and moves the file off it, and the three spellings of the multipart field name
# below are all in live use. A generic addfile POST is accepted by exactly one
# of the six. Round 7 carried this per target as a chain of `if name ==` and it
# is registry data here, so a target cannot be added without answering it.
DROP_DIR = "drop-dir"        # a watched directory: the copy is the import
PATH_JSON = "path-json"      # handed a path, and it moves the file off it
SAB_NZBFILE = "sab-nzbfile"  # multipart `nzbFile`, the .NET family
SAB_NAME = "sab-name"        # multipart `name`, decypharr's mock
SAB_STD = "sab-std"          # multipart `nzbfile`, SABnzbd's own spelling

FIELD = {SAB_NZBFILE: "nzbFile", SAB_NAME: "name", SAB_STD: "nzbfile"}

TARGETS = {
    # ---------------------------------------------------------------- ceiling
    "raw": {
        "kind": "native",
        "role": "ceiling",
        "serve_mode": HTTP_RANGE,
        "import_mode": NONE,
        "port": 8099,
        "language": "Python (this harness)",
        "url": "http://127.0.0.1:8099/stream",
        "ready": "http://127.0.0.1:8099/stream",
        "start": ("cd {bench} && nohup python3 rawserve_r10.py {nzb} 8099 "
                  "--conns {conns} > raw.log 2>&1 &"),
        "auth": None,
        "state_paths": [],
        "verified": "upstream",
        "note": ("not a competitor and never ranked as one. It is this harness "
                 "pulling the same articles with no application in the middle, so "
                 "every other row can be read as a fraction of the link that was "
                 "actually available. It opens no archives on purpose"),
    },

    # ------------------------------------------------------- existing five
    "zurg": {
        "import_style": DROP_DIR,
        "drop_dir": "{bench}/zurgrun/nzbs",
        "kind": "native", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 9998, "language": "Go",
        "url": "http://localhost:9998/dav/all/{release}/{file}",
        "root": "http://localhost:9998/dav/all/",
        "ready": "http://localhost:9998/dav/all/",
        "start": "cd {bench}/zurgrun && nohup ./zurg > zurg.log 2>&1 &",
        "auth": None, "verified": "upstream",
        "state_paths": ["{bench}/zurgrun/data", "{bench}/zurgrun/nzbs"],
        "note": "the author's own project",
    },
    "altmount": {
        "import_style": PATH_JSON,
        "import_api": "http://localhost:8081/api/import/file",
        "kind": "native", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 8081, "language": "Go",
        "url": "http://localhost:8081/webdav/complete/{release}/{file}",
        "root": "http://localhost:8081/webdav/complete/",
        "ready": "http://localhost:8081/webdav/",
        "start": ("cd {bench}/altmount && nohup ./altmount-cli-linux-amd64 serve "
                  "--config ./config.yaml > altmount.out 2>&1 &"),
        "auth": AUTH, "verified": "upstream",
        "state_paths": ["{bench}/altmount/cfg", "/tmp/.altmount-queue"],
    },
    "decypharr": {
        "import_style": SAB_NAME,
        "category": "tv",
        "kind": "native", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 8282, "language": "Go",
        "url": "http://localhost:8282/webdav/__all__/{release}/{file}",
        "root": "http://localhost:8282/webdav/__all__/",
        "ready": "http://localhost:8282/webdav/__all__/",
        "sab_api": "http://localhost:8282/sabnzbd/api",
        "start": ("cd {bench}/decyrun && nohup {bench}/decypharr "
                  "--config {bench}/decyrun/ > decypharr.log 2>&1 &"),
        "auth": None, "verified": "upstream",
        "state_paths": ["{bench}/decyrun/db", "{bench}/decyrun/usenet",
                        "{bench}/decyrun/downloads", "{bench}/decyrun/streams",
                        "{bench}/dfscache"],
        "note": "its SABnzbd mock upload field is `name`, not `nzbfile`",
    },
    "infinidysk": {
        "import_style": SAB_NZBFILE,
        "kind": "docker", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 8092, "language": "C# (.NET)",
        "container": "infinidysk-r10",
        "url": "http://127.0.0.1:8092/content/uncategorized/{release}/{file}",
        "root": "http://127.0.0.1:8092/content/uncategorized/",
        "ready": "http://127.0.0.1:8092/health",
        "auth": AUTH, "verified": "upstream",
        "state_paths": ["{bench}/infinidysk/config-r10"],
    },
    "nzbdav-og": {
        "import_style": SAB_NZBFILE,
        "kind": "docker", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 8093, "language": "C# (.NET)",
        "container": "nzbdav-r10",
        "url": "http://127.0.0.1:8093/content/uncategorized/{release}/{file}",
        "root": "http://127.0.0.1:8093/content/uncategorized/",
        "ready": "http://127.0.0.1:8093/health",
        "auth": AUTH, "verified": "upstream",
        "state_paths": ["{bench}/nzbdav-og/config-r10"],
    },

    # ------------------------------------------------------------ new targets
    "nzbdavex": {
        "import_style": SAB_NZBFILE,
        "kind": "docker", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 8094, "language": "C# (.NET)",
        "container": "nzbdavex-r10",
        "repo": "qooode/nzbdavex",
        "url": "http://127.0.0.1:8094/content/uncategorized/{release}/{file}",
        "root": "http://127.0.0.1:8094/content/uncategorized/",
        "ready": "http://127.0.0.1:8094/health",
        "auth": AUTH, "verified": "shakedown",
        "note": ("the other fork of nzbdav. Rounds 3-9 covered the original and "
                 "InfiniDysk and left this one out, so the family was measured "
                 "with a hole in it. Same .NET base, so the same import and serve "
                 "paths: it needs `--db-migration` before it will serve, and PORT "
                 "is the web UI's port while the backend takes ASPNETCORE_URLS -- "
                 "point both at one port and whichever starts first wins. "
                 "Upstream has not been pushed since 2026-06-23; check it is "
                 "still alive before spending a round on it"),
    },
    "stremthru": {
        "import_style": SAB_STD,
        "kind": "native", "role": "target", "serve_mode": WEBDAV,
        "import_mode": SAB, "port": 8484, "language": "Go",
        "repo": "MunifTanjim/stremthru",
        "url": "http://127.0.0.1:8484/v0/webdav/newz/{release}/{file}",
        "root": "http://127.0.0.1:8484/v0/webdav/newz/",
        "ready": "http://127.0.0.1:8484/v0/webdav/newz/",
        "sab_api": "http://127.0.0.1:8484/v0/sabnzbd/api",
        "start": ("cd {bench}/stremthru && nohup ./stremthru > stremthru.log 2>&1 &"),
        "auth": AUTH, "verified": "upstream",
        "note": ("the one addition that is directly comparable to the mounts: its "
                 "`newz` store is its own usenet engine and it answers WebDAV at "
                 "/v0/webdav/newz/ as well as a SABnzbd API at /v0/sabnzbd/api, so "
                 "it runs through the identical import and serve path as the five "
                 "incumbents. Build with the sqlite_fts5 tag or a migration "
                 "creates an fts5 table the binary cannot open; the dash frontend "
                 "must be built before the Go build embeds it"),
    },
    "aiostreams": {
        "import_style": SAB_STD,
        "kind": "native", "role": "target", "serve_mode": HTTP_RANGE,
        "import_mode": SAB, "port": 3000, "language": "TypeScript",
        "repo": "Viren070/AIOStreams",
        "root": "http://127.0.0.1:3000/api/v1/builtins/library/",
        "sab_api": "http://127.0.0.1:3000/api/sabnzbd/api",
        "ready": "http://127.0.0.1:3000/api/v1/status",
        "start": ("cd {bench}/aiostreams && DATABASE_URI=sqlite://./data/db.sqlite "
                  "nohup node dist/server/src/index.js > aiostreams.log 2>&1 &"),
        "auth": None, "verified": "shakedown",
        "note": ("the largest project in the field by a wide margin and the "
                 "author of the competing benchmark, which is the reason an "
                 "independent number for it is worth having. It is NOT a WebDAV "
                 "server: there is no PROPFIND anywhere in the tree, so it is "
                 "measured on the HTTP-Range path and must not be ranked against "
                 "the mounts on import. Its data directory comes from DATABASE_URI "
                 "and nothing else, so leave that unset and it writes into the "
                 "clone and keeps the library between runs"),
    },
    "streamnzb": {
        "kind": "native", "role": "target", "serve_mode": HTTP_RANGE,
        "import_mode": NATIVE_API, "port": 7000, "language": "Go",
        "repo": "Gaisberg/streamnzb",
        "play_api": "http://127.0.0.1:7000/api/play/nzb",
        "ready": "http://127.0.0.1:7000/",
        "start": "{bench}/streamnzbrun/start.sh",
        "auth": None, "verified": "upstream",
        "note": ("measured once in the 18 August six-way round and then dropped "
                 "before the repository existed, so it has never appeared in a "
                 "published round. Disable the bundled NNTP proxy or it binds a "
                 "privileged port and dies at boot with a misleading error, and "
                 "raise the playback timeout well above its 5s default or a "
                 "multi-volume RAR fails outright. Stored archives only, by "
                 "design, so the negative tier is expected to fail here and that "
                 "is not a defect"),
    },
    "comet": {
        "kind": "docker", "role": "target", "serve_mode": HTTP_RANGE,
        "import_mode": DISCOVERY, "port": 8085, "language": "Python + Rust",
        "repo": "g0ldyy/comet", "branch": "feat/usenet",
        "container": "comet-r10",
        "ready": "http://127.0.0.1:8085/health",
        "auth": None, "verified": "shakedown",
        "budget_s": 1800,
        "note": ("enabled like everything else, but expect a finding rather than "
                 "a row. It has no import API at all -- a release can only be "
                 "offered to it by standing up a Stremio addon of your own and "
                 "pointing its discovery at it -- and its engine materialises "
                 "archives past the harness's item boundary with no exposed idle "
                 "signal to drain against. Under sustained load it deadlocks its "
                 "own SQLite at its shipped defaults. `--disable comet` if you "
                 "want the run to stop paying for that"),
    },
}

def _port_overrides():
    """R10_PORTS="altmount=8181,zurg=9998" -- a port moved for one round.

    A default port can be held by something that is not ours. On a shared host
    that is a hazard rather than a nuisance: stop() frees a port by killing
    whatever listens on it, so a round that assumed the port was free would kill
    a stranger's process to make room for its own, and the first sign of it
    would be somebody else's work gone. Moving the target is the cheap half of
    the fix; the other half is that the drain check now asks who owns a socket
    rather than assuming everything on :563 is a target.
    """
    out = {}
    for item in os.environ.get("R10_PORTS", "").split(","):
        if not item.strip():
            continue
        name, _, port = item.partition("=")
        name, port = name.strip(), port.strip()
        if name not in TARGETS or not port.isdigit():
            raise SystemExit(f"R10_PORTS: cannot move {item.strip()!r}. "
                             f"Registered: {', '.join(TARGETS)}")
        out[name] = int(port)
    return out


def _move_ports():
    """Rewrite the port and every URL that carries it, together.

    Separately is how a target ends up started on one port and measured on
    another, which reads as a server that will not answer.
    """
    for name, port in _port_overrides().items():
        spec = TARGETS[name]
        was = str(spec["port"])
        spec["port"] = port
        spec["moved_from"] = int(was)
        for key in ("url", "root", "ready", "sab_api", "import_api", "play_api",
                    "start"):
            if isinstance(spec.get(key), str):
                spec[key] = spec[key].replace(f":{was}", f":{port}")


_move_ports()


# every registered target, in a stable order. A round measures all of them
# unless something is switched off explicitly
DEFAULT = ["raw", "zurg", "altmount", "infinidysk", "nzbdav-og", "nzbdavex",
           "decypharr", "stremthru", "aiostreams", "streamnzb", "comet"]

# how long one target may spend on the whole corpus before the run gives up on
# it and moves to the next. Everything is enabled by default, so a target that
# wedges must cost its own rows and not the round
DEFAULT_BUDGET_S = 3600

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "config", "targets-r10.json")

MOUNTS = [n for n, t in TARGETS.items() if t["serve_mode"] == WEBDAV]
ADDONS = [n for n, t in TARGETS.items() if t["serve_mode"] == HTTP_RANGE]


def load_config(path=CONFIG):
    """Persistent enable/disable, so a preference outlives one command line.

    Absent or unreadable means everything is on, which is the default this whole
    file is built around: a target is measured unless somebody said not to.
    """
    try:
        with open(path) as handle:
            return json.load(handle)
    except Exception:
        return {}


def enabled(names=None, disable=None, only=None, config=None):
    """The targets to run.

    Everything registered is on by default. Three ways to narrow it, in order of
    precedence, so an explicit flag always beats a stored preference:

        only     run exactly these and nothing else   (--only / --targets)
        disable  run everything except these          (--disable)
        config   the same two keys, from config/targets-r10.json

    A name that is not registered is an error rather than a silent no-op. A
    round that quietly measured nine targets because one was misspelled would
    publish a field that never existed.
    """
    config = load_config() if config is None else config
    pool = list(names or DEFAULT)

    if only is None:
        only = config.get("only")
    if disable is None:
        disable = config.get("disabled")

    unknown = [n for n in list(only or []) + list(disable or []) + pool
               if n not in TARGETS]
    if unknown:
        raise SystemExit(f"unknown target(s): {', '.join(sorted(set(unknown)))}. "
                         f"Registered: {', '.join(TARGETS)}")

    if only:
        return [n for n in pool if n in set(only)]
    if disable:
        return [n for n in pool if n not in set(disable)]
    return pool


def budget(name):
    """Seconds one target may spend before the run abandons it and moves on."""
    return TARGETS[name].get("budget_s", DEFAULT_BUDGET_S)


def comparable(names, mode):
    """Only the targets that serve the same way, for a table that must not mix them."""
    return [n for n in names if TARGETS[n]["serve_mode"] == mode]


def needs_shakedown(names=None):
    """Targets whose endpoints have not yet survived a run."""
    return [n for n in (names or DEFAULT)
            if TARGETS[n].get("verified") == "shakedown"]


def summary():
    rows = []
    for name in TARGETS:
        spec = TARGETS[name]
        rows.append({
            "target": name, "role": spec["role"], "serve": spec["serve_mode"],
            "import": spec["import_mode"], "language": spec.get("language"),
            "repo": spec.get("repo"), "verified": spec.get("verified"),
            "budget_s": budget(name),
        })
    return rows


if __name__ == "__main__":
    print(json.dumps({"registered": summary(), "enabled": enabled()}, indent=1))
