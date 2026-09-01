#!/usr/bin/env python3
"""Isolated N-way benchmark: exactly one server holds the NNTP account at a time.

Extends bench2.py from an A/B pair to the five Usenet-streaming servers. The
isolation rule is the same and is not optional: every target keeps ~20 NNTP
sockets warm, so two running together oversubscribe a 20-connection account and
skew both. Each rep starts one target, reads, and stops it before the next.

Order rotates by rep (a Latin-square-ish shift) so drift over the run cannot
favour whoever always goes first. Every target reads the identical byte range.
"""
import json
import os
import subprocess
import sys
import time

HZ = os.sysconf("SC_CLK_TCK")
BENCH = "/home/ben/bench"
AUTH = ("usenet", "usenet")

SNZB_TOKEN = "YOUR_STREAMNZB_STREAM_TOKEN"
SNZB_URL = (f"http://127.0.0.1:7000/{SNZB_TOKEN}/play/stream:default:movie:tt29355505:0")

MKV = "Toy.Story.5.2026.1080p.AMZN.WEB-DL.DDP5.1.H.264-KyoGo.mkv"

SPEC = {
    "zurg": {
        "port": 9998,
        "url": f"http://localhost:9998/dav/all/ToyStory5/{MKV}",
        "ready": "http://localhost:9998/dav/all/",
        "kind": "native",
        "start": f"cd {BENCH}/zurgrun && nohup ./zurg > zurg.log 2>&1 &",
        "auth": None,
    },
    "decypharr": {
        "port": 8282,
        "url": "http://localhost:8282/webdav/__all__/ToyStory5/ToyStory5.mkv",
        "ready": "http://localhost:8282/webdav/__all__/",
        "kind": "native",
        "start": f"cd {BENCH}/decyrun && nohup {BENCH}/decypharr --config {BENCH}/decyrun/ > decypharr.log 2>&1 &",
        "auth": None,
    },
    "altmount": {
        "port": 8081,
        "url": f"http://localhost:8081/webdav/complete/ToyStory5/{MKV}",
        "ready": "http://localhost:8081/webdav/",
        "kind": "native",
        "start": f"cd {BENCH}/altmount && nohup ./altmount-cli-linux-amd64 serve --config ./config.yaml > altmount.out 2>&1 &",
        "auth": AUTH,
    },
    "infinidysk": {
        "port": 8092,
        "url": "http://127.0.0.1:8092/content/uncategorized/ToyStory5/ToyStory5.mkv",
        "ready": "http://127.0.0.1:8092/health",
        "kind": "docker",
        "container": "infinidysk-r7",
        "auth": AUTH,
    },
    "nzbdav-og": {
        "port": 8093,
        "url": f"http://127.0.0.1:8093/content/uncategorized/ToyStory5/{MKV}",
        "ready": "http://127.0.0.1:8093/health",
        "kind": "docker",
        "container": "nzbdav-r7",
        "auth": AUTH,
    },
    "streamnzb": {
        "port": 7000,
        "url": SNZB_URL,
        "ready": f"http://127.0.0.1:7000/{SNZB_TOKEN}/manifest.json",
        "kind": "native",
        "start": f"{BENCH}/streamnzbrun/start.sh",
        "auth": None,
    },
}

ALL = list(SPEC)


def sh(cmd):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).stdout.strip()


def spawn(cmd):
    subprocess.run(["bash", "-c", cmd], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pids_on(port):
    """Every listener on the port, not just the first one lsof happens to print."""
    out = sh(f"lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null")
    return sorted({int(x) for x in out.split() if x.isdigit()})


def pid_on(port):
    """One listener, which is all stop()'s SIGTERM needs; accounting wants pids_on."""
    pids = pids_on(port)
    return pids[0] if pids else None


def container_pids(name):
    out = sh(f"docker top {name} -eo pid 2>/dev/null | tail -n +2")
    return [int(x) for x in out.split() if x.isdigit()]


def _children():
    """ppid -> [pid], read straight from /proc. Linux only, like the rest of this."""
    kids = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as f:
                # comm may hold spaces and parens, so split after the last ')':
                # the remaining fields are state, ppid, pgrp, ...
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except Exception:
            continue
        kids.setdefault(ppid, []).append(int(entry))
    return kids


def proc_tree(roots):
    """The roots plus every descendant.

    zurg forks rclone (rclone_enabled in its config) and that child's CPU and
    RSS were invisible, while docker targets were charged for every process in
    the container — the two sides of the comparison were not measuring the same
    thing. Also what stop() must SIGKILL: killing the parent alone orphans the
    child, which goes on holding NNTP sockets.
    """
    kids = _children()
    seen, out, stack = set(), [], list(roots)
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        stack.extend(kids.get(pid, []))
    return out


def pids_for(name):
    """Every PID whose CPU and RSS belong to this target."""
    s = SPEC[name]
    if s["kind"] == "docker":
        return container_pids(s["container"])
    return proc_tree(pids_on(s["port"]))


PROD_ZURG_PID = sh("systemctl show -p MainPID --value zurg.service") or "0"


def nntp_lines():
    """NNTP sockets belonging to a bench target, as their raw `ss` lines.

    zen runs a production zurg.service against the same news account and keeps
    a couple of sockets warm at idle, so a plain count never reaches zero and
    every stop() burned its full 40s wait. Exclude that one PID; anything else
    on :563 is a target we are still waiting on.

    Matched on the peer address field ending in :563, not `grep ':563'`, which
    also matched an ephemeral local port like :56312 and burned the whole drain
    wait on a target that had already let go.
    """
    lines = []
    for line in sh("ss -tnp 2>/dev/null").splitlines():
        parts = line.split()
        # State Recv-Q Send-Q Local:Port Peer:Port [Process]
        if len(parts) < 5 or parts[0] == "State":
            continue
        if not parts[4].endswith(":563"):
            continue
        if "pid=" + PROD_ZURG_PID + "," in line:
            continue
        lines.append(line.strip())
    return lines


def nntp_sockets():
    return len(nntp_lines())


def stop(name, budget=90):
    """Stop a target and prove it let go of the port and the news account.

    Both waits used to fall through on timeout, so a wedged target kept its ~20
    NNTP sockets while the next target was measured — the one rule the whole
    benchmark rests on, broken silently. Now SIGTERM gets 20s before the process
    tree takes a SIGKILL, and anything still holding on at the end of the budget
    raises: a crashed run is honest, a contaminated measurement is not.
    """
    s = SPEC[name]
    deadline = time.time() + budget
    if s["kind"] == "docker":
        sh(f"docker stop {s['container']} >/dev/null 2>&1")
    else:
        for pid in pids_on(s["port"]):
            sh(f"kill {pid} 2>/dev/null")
    termed = time.time()
    # docker stop escalates to SIGKILL on its own; native targets need us to
    escalated = s["kind"] == "docker"
    while time.time() < deadline:
        if not pids_on(s["port"]):
            break
        if not escalated and time.time() - termed > 20:
            # the whole tree, not the listener: an orphaned rclone child keeps
            # its NNTP sockets and the next target starts contaminated
            for pid in proc_tree(pids_on(s["port"])):
                sh(f"kill -9 {pid} 2>/dev/null")
            escalated = True
        time.sleep(1)
    # the account is only free once the sockets are actually gone
    while time.time() < deadline:
        if nntp_sockets() == 0:
            break
        time.sleep(1)
    left, still = nntp_lines(), pids_on(s["port"])
    if still or left:
        raise RuntimeError(
            f"{name} still holds the account after {budget}s: "
            f"port {s['port']} listeners {still}, {len(left)} NNTP sockets\n"
            + "\n".join(left[:10]))
    time.sleep(2)


def stop_all():
    for n in ALL:
        stop(n)


def http_code(name, url):
    cmd = (["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "3"]
           + curl_auth(name) + [url])
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip() or "000"
    except Exception:
        return "000"


def start(name):
    s = SPEC[name]
    if s["kind"] == "docker":
        sh(f"docker start {s['container']} >/dev/null 2>&1")
    else:
        spawn(s["start"])
    code = "000"
    for _ in range(90):
        time.sleep(1)
        # 5xx is not ready: zurg answers 503 for as long as its library is
        # loading, and that load used to leak into the first measured TTFB by a
        # different amount per target. 401/404 do count — the server is
        # answering. Auth goes with the probe so altmount's 401 stays a real
        # answer rather than an ambiguous one.
        code = http_code(name, s["ready"])
        if code != "000" and not code.startswith("5"):
            break
    else:
        # measuring a target that never came up yields garbage shaped like data
        raise RuntimeError(f"{name} never became ready at {s['ready']}, last code {code}")
    time.sleep(4)
    return pids_for(name)


def cpu_ticks(pids):
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as f:
                parts = f.read().rsplit(")", 1)[1].split()
            total += int(parts[11]) + int(parts[12])
        except Exception:
            pass
    return total


def rss_mb(pids):
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1])
                        break
        except Exception:
            pass
    return round(total / 1024)


def curl_auth(name):
    a = SPEC[name]["auth"]
    return ["-u", f"{a[0]}:{a[1]}"] if a else []


def measure(name, pids, off, length, timeout=900):
    c0 = cpu_ticks(pids)
    r0 = rss_mb(pids)
    cmd = (["curl", "-s", "-o", "/dev/null", "--max-time", str(timeout)]
           + curl_auth(name)
           + ["-H", f"Range: bytes={off}-{off + length - 1}",
              "-w", "%{time_starttransfer} %{time_total} %{size_download} %{http_code}",
              SPEC[name]["url"]])
    try:
        out = subprocess.check_output(cmd, text=True, timeout=timeout + 60)
    except Exception as e:
        return {"target": name, "offset": off, "error": str(e)[:100]}
    c1 = cpu_ticks(pids)
    r1 = rss_mb(pids)
    ttfb, total, size, code = out.split()
    size, total = int(size), float(total)
    return {
        "target": name, "offset": off, "bytes": size, "http": code,
        "ttfb_s": round(float(ttfb), 3), "total_s": round(total, 3),
        "MBps": round(size / total / 1e6, 2) if total else 0,
        "cpu_s": round((c1 - c0) / HZ, 2),
        "cpu_s_per_GB": round(((c1 - c0) / HZ) / (size / 1e9), 1) if size else 0,
        "rss_MB": max(r0, r1),
    }


def main(tag, size_mb, base_off, gap_gb, reps, targets=None):
    targets = targets or ALL
    extra = reps % len(targets)
    if extra:
        # the order shifts one slot per rep, so a rep count that is not a
        # multiple of the target count leaves the first `extra` targets going
        # first once more than the rest (round 7: 6 reps over 5 targets, zurg
        # first twice). The rotation is deterministic and published results
        # depend on it, so surface the imbalance rather than correct it.
        print(f"WARN: {reps} reps over {len(targets)} targets — extra first-slot turn for "
              + ", ".join(targets[:extra]), flush=True)
    length = size_mb << 20
    results = []
    stop_all()
    for i in range(reps):
        off = base_off + i * int(gap_gb * 1e9)
        order = targets[i % len(targets):] + targets[:i % len(targets)]
        for name in order:
            pids = start(name)
            r = measure(name, pids, off, length)
            r["rep"] = i
            r["tag"] = tag
            stop(name)
            results.append(r)
            print(json.dumps(r), flush=True)
        with open(f"{BENCH}/results_{tag}.json", "w") as f:
            json.dump(results, f, indent=1)
    return results


if __name__ == "__main__":
    tgts = sys.argv[6].split(",") if len(sys.argv) > 6 else None
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), tgts)
