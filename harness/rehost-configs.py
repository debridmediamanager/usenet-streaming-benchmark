#!/usr/bin/env python3
"""Point a set of target configs at a new machine, at a stated connection budget.

Configs carry absolute paths and a connection count. Copied to another host they
name directories that do not exist there, and a target that cannot open its
database or its cache directory does not fail loudly -- it comes up and behaves
differently, which is the worst of the three outcomes.

The connection budget is rewritten here too, because it is the one number the
whole comparison rests on and it lives in a different place in every config.

    CONNS=10 python3 harness/rehost-configs.py /root/bench

Run it after copying the built targets across and before prep. It asserts what
it wrote rather than trusting the substitution: a regex that matches nothing
changes nothing and says so to nobody, which is how a round gets announced at a
budget it never ran at.
"""
import json
import os
import re
import sys


def rewrite_zurg(path, bench, conns):
    text = open(path).read()
    text = re.sub(r"connections: \d+", f"connections: {conns}", text)
    text = re.sub(r"enable_repair: \w+", "enable_repair: true", text)
    text = re.sub(r"(?m)^(\s*(?:mount_path|rclone_binary):\s*).*$",
                  lambda m: m.group(1) + _repath(m.group(0).split(":", 1)[1].strip(), bench),
                  text)
    open(path, "w").write(text)
    found = open(path).read()
    problems = []
    if not re.search(r"(?m)^\s*connections: %d\s*$" % conns, found):
        problems.append(f"connections: {conns}")
    if not re.search(r"(?m)^\s*enable_repair: true\s*$", found):
        problems.append("enable_repair: true")
    return problems


def rewrite_altmount(path, bench, conns, port=None):
    text = open(path).read()
    text = re.sub(r"max_connections: \d+", f"max_connections: {conns}", text)
    text = re.sub(r"max_connections_for_health_checks: \d+",
                  f"max_connections_for_health_checks: {conns}", text)
    text = re.sub(r"(/[\w./-]*?)/bench/", lambda m: bench.rstrip("/") + "/", text)
    if port:
        text = re.sub(r"(?m)^(\s*)port: \d+", r"\g<1>port: " + str(port), text, count=1)
        text = re.sub(r"localhost:\d+", f"localhost:{port}", text)
    open(path, "w").write(text)
    found = open(path).read()
    problems = []
    if set(int(x) for x in re.findall(r"max_connections: (\d+)", found)) - {conns}:
        problems.append("altmount max_connections")
    if "/bench/" in found and bench.rstrip("/") not in found:
        problems.append("altmount paths still point elsewhere")
    return problems


def rewrite_decypharr(path, bench, conns):
    cfg = json.load(open(path))
    usenet = cfg.setdefault("usenet", {})
    usenet["max_connections"] = conns
    usenet["processing_max_connections"] = conns
    for provider in usenet.get("providers", []):
        provider["max_connections"] = conns
    for key in ("download_folder",):
        if key in cfg:
            cfg[key] = _repath(cfg[key], bench)
    if "disk_buffer_path" in usenet:
        usenet["disk_buffer_path"] = _repath(usenet["disk_buffer_path"], bench)
    mount = cfg.setdefault("mount", {})
    if "mount_path" in mount:
        mount["mount_path"] = _repath(mount["mount_path"], bench)
    dfs = mount.setdefault("dfs", {})
    if "cache_dir" in dfs:
        dfs["cache_dir"] = _repath(dfs["cache_dir"], bench)
    # whoever runs the round owns the mount
    dfs["uid"] = os.getuid()
    dfs["gid"] = os.getgid()
    json.dump(cfg, open(path, "w"), indent=1)

    found = json.load(open(path))
    got = {found["usenet"]["max_connections"],
           found["usenet"]["processing_max_connections"]}
    got |= {p["max_connections"] for p in found["usenet"].get("providers", [])}
    return [] if got == {conns} else [f"decypharr connections {sorted(got)}"]


def _repath(value, bench):
    """Move a path that lives under some .../bench/ to this host's bench root."""
    marker = "/bench/"
    if marker in value:
        return bench.rstrip("/") + "/" + value.split(marker, 1)[1]
    return value


def main():
    bench = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BENCH", "/root/bench")
    conns = int(os.environ.get("CONNS", "15"))
    port = os.environ.get("ALTMOUNT_PORT")

    problems = []
    plan = (
        (os.path.join(bench, "zurgrun", "config.yml"),
         lambda p: rewrite_zurg(p, bench, conns)),
        (os.path.join(bench, "altmount", "config.yaml"),
         lambda p: rewrite_altmount(p, bench, conns, port)),
        (os.path.join(bench, "decyrun", "config.json"),
         lambda p: rewrite_decypharr(p, bench, conns)),
    )
    for path, rewrite in plan:
        if not os.path.exists(path):
            problems.append(f"missing config: {path}")
            continue
        problems.extend(rewrite(path))

    if problems:
        print("   REHOST FAILED: " + "; ".join(problems))
        return 1
    print(f"   zurg, altmount and decypharr rehosted to {bench} at {conns} connections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
