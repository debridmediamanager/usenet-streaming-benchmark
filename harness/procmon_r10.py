#!/usr/bin/env python3
"""CPU shape and memory shape: what a total and a peak cannot say.

Rounds 3 through 9 reported one CPU number, `cpu_s_per_GB`, and one memory
number, peak RSS. Both are the right headline and neither is the whole result.

CPU. Ten CPU-seconds is a steady half core for twenty seconds or one core
pinned for ten, and those cost a shared box very differently -- the second makes
everything else on the machine stutter while the average looks calm. So this
also reports the level the process sustains (p95 of per-second core usage), its
worst single second, and how much of the time it sits near its own peak.

Memory. A single peak rewards failing early: a target that died on the large
reads never had the chance to spike. So a run records the per-read peaks, the
count they were taken over, the drift between the start of a run and the end,
and what the process is still holding once the work stops. Drift is the one
that catches a leak; a peak never will.

Both are bounded below by the sample interval. A spike shorter than one second
is averaged away, so these understate burstiness and never overstate it -- and
a read that finished in fewer than MIN_SHAPE_SAMPLES samples carries no shape at
all rather than a shape computed from two points.

Linux /proc is the primary source. Container processes are visible there too
when the daemon shares the host kernel, which is the case on the hosts this
harness runs on; `docker stats` is the fallback for a daemon inside a VM, where
/proc on this host knows nothing about them.
"""
import json
import os
import statistics
import subprocess
import threading
import time

HZ = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
MIN_SHAPE_SAMPLES = 4
DEFAULT_INTERVAL = 1.0


def cpu_ticks(pids):
    """utime + stime across a process set, in clock ticks."""
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as handle:
                parts = handle.read().rsplit(")", 1)[1].split()
            total += int(parts[11]) + int(parts[12])
        except Exception:
            pass
    return total


def rss_kb(pids):
    """Resident set across a process set, in KiB."""
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/status") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1])
                        break
        except Exception:
            pass
    return total


def docker_stats(container):
    """(cpu_percent, rss_bytes) from the daemon, for a container /proc cannot see."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}} {{.MemUsage}}",
             container],
            capture_output=True, text=True, timeout=30).stdout.strip()
        cpu_txt, mem_txt = out.split(" ", 1)
        cpu = float(cpu_txt.rstrip("%"))
        used = mem_txt.split("/")[0].strip()
        unit = used.lstrip("0123456789.").strip()
        value = float(used[:len(used) - len(unit)])
        scale = {"B": 1, "KiB": 1 << 10, "MiB": 1 << 20, "GiB": 1 << 30,
                 "KB": 1e3, "MB": 1e6, "GB": 1e9}.get(unit, 1)
        return cpu, value * scale
    except Exception:
        return None, None


class Sampler:
    """Samples a process set on a fixed interval until stopped.

    `pids_fn` is re-evaluated every tick rather than captured once: a target
    that forks a helper mid-read (zurg forks rclone) would otherwise have that
    child's CPU and memory counted as zero, and the comparison would not be
    measuring the same thing on both sides.
    """

    def __init__(self, pids_fn, interval=DEFAULT_INTERVAL,
                 cpu_fn=cpu_ticks, rss_fn=rss_kb):
        self.pids_fn = pids_fn
        self.interval = interval
        self.cpu_fn = cpu_fn
        self.rss_fn = rss_fn
        self.samples = []          # (elapsed_s, cores_this_tick, rss_kb)
        self._stop = threading.Event()
        self._thread = None
        self.cpu_total_s = 0.0

    def _run(self):
        t0 = time.perf_counter()
        pids = self.pids_fn()
        last_ticks = self.cpu_fn(pids)
        first_ticks = last_ticks
        last_t = t0
        while not self._stop.wait(self.interval):
            now = time.perf_counter()
            pids = self.pids_fn()
            ticks = self.cpu_fn(pids)
            span = now - last_t
            # a process set that shrank (a restart mid-window) can read as
            # negative; clamp rather than report a negative core count
            cores = max(0.0, (ticks - last_ticks) / HZ / span) if span > 0 else 0.0
            self.samples.append((round(now - t0, 3), round(cores, 4), self.rss_fn(pids)))
            last_ticks, last_t = ticks, now
        self.cpu_total_s = max(0.0, (last_ticks - first_ticks) / HZ)

    def start(self):
        self._stop.clear()
        self.samples = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 3)
        return self.summary()

    def summary(self, bytes_delivered=None):
        return summarise(self.samples, self.cpu_total_s, bytes_delivered,
                         self.interval)


def summarise(samples, cpu_total_s, bytes_delivered=None,
              interval=DEFAULT_INTERVAL):
    """Turn a sample series into the shape columns.

    `steady` is the share of sampled seconds at or above half the p95 level. A
    high value is an engine that hums; a low one with a tall `cores_max` burns
    the same CPU in bursts against an idle baseline, which is what makes a box
    feel busy while the averages look calm.
    """
    out = {
        "samples": len(samples),
        "sample_interval_s": interval,
        "cpu_s": round(cpu_total_s, 2),
    }
    if bytes_delivered:
        gib = bytes_delivered / (1 << 30)
        out["cpu_s_per_GiB"] = round(cpu_total_s / gib, 2) if gib else None

    rss = [s[2] for s in samples if s[2]]
    if rss:
        out["rss_peak_MB"] = round(max(rss) / 1024)
        out["rss_median_MB"] = round(statistics.median(rss) / 1024)
        out["rss_final_MB"] = round(rss[-1] / 1024)

    cores = [s[1] for s in samples]
    if len(cores) < MIN_SHAPE_SAMPLES:
        # a read this short cannot support a shape; say so rather than compute
        # a p95 from two points and print it beside numbers taken from thirty
        out["shape_skipped"] = (f"{len(cores)} samples, need {MIN_SHAPE_SAMPLES}")
        return out

    ordered = sorted(cores)
    ix = max(0, int(round(0.95 * len(ordered))) - 1)
    p95 = ordered[ix]
    out["cores_p95"] = round(p95, 2)
    out["cores_max"] = round(max(cores), 2)
    out["cores_median"] = round(statistics.median(cores), 2)
    threshold = p95 / 2.0
    out["steady_pct"] = round(
        100.0 * sum(1 for c in cores if c >= threshold) / len(cores))
    return out


class RunMemory:
    """Accumulates per-read memory peaks across a whole run, for drift.

    Every application here holds more memory the longer it runs. A run-wide peak
    states the high-water mark and hides that entirely; drift states how much of
    the peak was accumulation rather than the cost of any single read.

    Measured with no idle gap between reads, which is the harshest case:
    applications that release memory on idle never get the chance to. That is
    why `after_idle_MB` is recorded separately -- it is where that memory goes
    back, and without it drift alone would read as a leak in an engine that
    simply has not been given a quiet moment.
    """

    def __init__(self):
        self.peaks = []
        self.idle_rss_MB = None
        self.after_idle_MB = None

    def record(self, peak_MB):
        if peak_MB:
            self.peaks.append(peak_MB)

    def summary(self):
        out = {"reads": len(self.peaks)}
        if self.idle_rss_MB is not None:
            out["idle_rss_MB"] = self.idle_rss_MB
        if not self.peaks:
            return out
        out["rss_per_read_MB"] = round(statistics.median(self.peaks))
        out["rss_peak_MB"] = max(self.peaks)
        out["peak_over_reads"] = len(self.peaks)
        third = len(self.peaks) // 3
        if third >= 1:
            first = statistics.median(self.peaks[:third])
            last = statistics.median(self.peaks[-third:])
            out["drift_MB"] = round(last - first)
        else:
            out["drift_skipped"] = f"{len(self.peaks)} reads, need 3"
        if self.after_idle_MB is not None:
            out["after_idle_MB"] = self.after_idle_MB
        return out


def sample_idle(pids_fn, seconds=5.0, interval=DEFAULT_INTERVAL,
                cpu_fn=cpu_ticks, rss_fn=rss_kb):
    """Footprint and background CPU of a started-but-idle target.

    Two phases need it. Idle RSS is the number that says what an application
    costs to merely have running, and the idle CPU rate is what the read must be
    charged net of -- the .NET targets run background services and pay startup
    on every restart, and all of it landed in the read before round 7 subtracted
    it.
    """
    sampler = Sampler(pids_fn, interval, cpu_fn, rss_fn).start()
    time.sleep(seconds)
    summary = sampler.stop()
    summary["idle_cpu_cores"] = summary.get("cores_median", 0.0)
    summary["idle_rss_MB"] = summary.get("rss_peak_MB")
    return summary


if __name__ == "__main__":
    import sys
    pid_list = [int(x) for x in sys.argv[1:]] or [os.getpid()]
    monitor = Sampler(lambda: pid_list, interval=0.5).start()
    time.sleep(5)
    print(json.dumps(monitor.stop(), indent=1))
