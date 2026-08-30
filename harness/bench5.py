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
        "url": f"http://127.0.0.1:8092/content/uncategorized/ToyStory5/{MKV}",
        "ready": "http://127.0.0.1:8092/health",
        "kind": "docker",
        "container": "infinidysk",
        "auth": AUTH,
    },
    "nzbdav-og": {
        "port": 8093,
        "url": f"http://127.0.0.1:8093/content/uncategorized/ToyStory5/{MKV}",
        "ready": "http://127.0.0.1:8093/health",
        "kind": "docker",
        "container": "nzbdav-og",
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


def pid_on(port):
    out = sh(f"lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null")
    return int(out.split()[0]) if out else None


def container_pids(name):
    out = sh(f"docker top {name} -eo pid 2>/dev/null | tail -n +2")
    return [int(x) for x in out.split() if x.isdigit()]


def pids_for(name):
    """Every PID whose CPU and RSS belong to this target."""
    s = SPEC[name]
    if s["kind"] == "docker":
        return container_pids(s["container"])
    pid = pid_on(s["port"])
    return [pid] if pid else []


PROD_ZURG_PID = sh("systemctl show -p MainPID --value zurg.service") or "0"


def nntp_sockets():
    """NNTP sockets belonging to a bench target.

    zen runs a production zurg.service against the same news account and keeps
    a couple of sockets warm at idle, so a plain count never reaches zero and
    every stop() burned its full 40s wait. Exclude that one PID; anything else
    on :563 is a target we are still waiting on.
    """
    out = sh("ss -tnp 2>/dev/null | grep ':563'")
    n = 0
    for line in out.splitlines():
        if not line.strip():
            continue
        if "pid=" + PROD_ZURG_PID + "," in line:
            continue
        n += 1
    return n


def stop(name):
    s = SPEC[name]
    if s["kind"] == "docker":
        sh(f"docker stop {s['container']} >/dev/null 2>&1")
    else:
        pid = pid_on(s["port"])
        if pid:
            sh(f"kill {pid}")
    for _ in range(40):
        if not pid_on(s["port"]):
            break
        time.sleep(1)
    # the account is only free once the sockets are actually gone
    for _ in range(40):
        if nntp_sockets() == 0:
            break
        time.sleep(1)
    time.sleep(2)


def stop_all():
    for n in ALL:
        stop(n)


def start(name):
    s = SPEC[name]
    if s["kind"] == "docker":
        sh(f"docker start {s['container']} >/dev/null 2>&1")
    else:
        spawn(s["start"])
    for _ in range(90):
        time.sleep(1)
        code = sh(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 3 {s['ready']}")
        if code and code not in ("000",):
            break
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
