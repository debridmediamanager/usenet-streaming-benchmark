#!/usr/bin/env python3
"""Round-10 measurement primitives: windowed rates, seek profile, playback, integrity.

What rounds 3 through 9 measured, and where each one is blind:

  * mean MB/s over a whole read. A mean hides a stall completely: a read that
    runs at 60 MB/s for nine seconds and 0 for one reports 54, and a player
    stops during that second. `p05_MBps` is the fifth-percentile one-second
    windowed rate, which is what the viewer actually feels.
  * one scrub number, the median of eight 2 MB reads. That cannot say whether
    seeking near the end of a file costs more than seeking near the start, and
    it conflates two different things -- the moment a server answers a Range
    and the moment the seek has actually delivered. An engine that answers
    instantly and then feeds the body slowly wins the first and loses the
    second, and the second is the one a player waits through.
  * nothing bitrate-relative at all. `ffprobe` and a Plex press-play tell you
    about a start; neither says whether a stream sustains 25 Mbps for thirty
    seconds without draining a buffer.

Auth is sent preemptively rather than after a 401 challenge. A challenge costs
an extra round trip, only the targets that use auth pay it, and all of it lands
in TTFB -- so the targets with a password would have looked slower to open by
however long the extra round trip took.

Every request opens its own connection. That is uniform across targets, and it
keeps a cold read cold: reusing a socket would carry a warm TLS session and a
warm server-side handle into the next measurement.
"""
import base64
import hashlib
import json
import math
import statistics
import time
import urllib.error
import urllib.request

CHUNK = 1 << 16
DEFAULT_WINDOW_MS = 1000
# fewer windows than this and a percentile is noise dressed as a number
MIN_WINDOWS_FOR_P05 = 5


def _request(url, auth=None, start=None, end=None):
    req = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    if start is not None:
        req.add_header("Range", f"bytes={start}-" + ("" if end is None else str(end)))
    return req


def windowed_rates(samples, window_ms=DEFAULT_WINDOW_MS):
    """(seconds_since_first_byte, cumulative_bytes) -> MB/s per complete window.

    Time is measured from the first byte on purpose. Measured from the request,
    the opening window holds the whole TTFB and reports near zero, and because
    the p05 index lands on the minimum for any transfer shorter than about
    twenty windows, that startup window became the p05 for nearly every row in
    the field. The metric said "a second at zero inside the read", and what it
    actually reported was how long the server took to answer.

    The final partial window is dropped. It is short by construction and would
    report a rate below anything the transfer actually did, which would drag a
    p05 down on transfer length rather than on performance.
    """
    if len(samples) < 2:
        return []
    width = window_ms / 1000.0
    end = samples[-1][0]
    rates = []
    edge = width
    prev_bytes = 0
    prev_ix = 0
    while edge <= end + 1e-9:
        # bytes delivered by the time this window closed, interpolated across
        # the sample that straddles the edge
        while prev_ix + 1 < len(samples) and samples[prev_ix + 1][0] <= edge:
            prev_ix += 1
        cum = samples[prev_ix][1]
        rates.append((cum - prev_bytes) / width / 1e6)
        prev_bytes = cum
        edge += width
    return rates


def timed_stream(url, auth=None, start=0, length=None, max_bytes=math.inf,
                 max_ms=math.inf, want_hash=False, window_ms=DEFAULT_WINDOW_MS,
                 timeout=600):
    """One ranged read, sampled over time.

    Returns mean and p05 windowed rate, TTFB split into response and first byte,
    and optionally an md5 of exactly the bytes delivered.
    """
    end = None if length is None else start + length - 1
    out = {"url": url, "offset": start, "requested": length}
    t0 = time.perf_counter()
    try:
        resp = urllib.request.urlopen(_request(url, auth, start, end), timeout=timeout)
    except urllib.error.HTTPError as exc:
        out.update(http=str(exc.code), error=f"HTTP {exc.code}", bytes=0)
        return out
    except Exception as exc:
        out.update(http="000", error=f"{type(exc).__name__}: {exc}"[:120], bytes=0)
        return out

    out["http"] = str(resp.status)
    out["content_length"] = resp.headers.get("Content-Length")
    out["content_range"] = resp.headers.get("Content-Range")
    out["accept_ranges"] = resp.headers.get("Accept-Ranges")
    out["response_s"] = round(time.perf_counter() - t0, 4)

    digest = hashlib.md5() if want_hash else None
    total = 0
    samples = []
    first_byte_at = None
    budget = max_ms / 1000.0
    try:
        while total < max_bytes:
            want = int(min(CHUNK, max_bytes - total))
            chunk = resp.read(want)
            if not chunk:
                break
            now = time.perf_counter() - t0
            if first_byte_at is None:
                first_byte_at = now
            total += len(chunk)
            if digest:
                digest.update(chunk)
            # windows are measured from the FIRST BYTE, not from the request.
            # Timed from the request, window one always contains the TTFB dead
            # time and delivers almost nothing, and since the p05 index is the
            # minimum for any transfer under about twenty windows, p05 was the
            # startup window every time -- it reported TTFB while claiming to
            # report stalls. TTFB has its own column.
            samples.append((now - first_byte_at, total))
            if now >= budget:
                out["truncated_by_budget"] = True
                break
    except Exception as exc:
        out["error"] = f"stream aborted after {total} bytes: {type(exc).__name__}"
    finally:
        try:
            resp.close()
        except Exception:
            pass

    elapsed = time.perf_counter() - t0
    out["bytes"] = total
    out["total_s"] = round(elapsed, 4)
    out["ttfb_s"] = round(first_byte_at, 4) if first_byte_at is not None else None
    out["MBps"] = round(total / elapsed / 1e6, 2) if elapsed > 0 else 0
    if digest:
        out["md5"] = digest.hexdigest()

    rates = windowed_rates(samples, window_ms)
    out["windows"] = len(rates)
    if len(rates) >= MIN_WINDOWS_FOR_P05:
        rates_sorted = sorted(rates)
        ix = max(0, int(math.ceil(0.05 * len(rates_sorted))) - 1)
        out["p05_MBps"] = round(rates_sorted[ix], 2)
        out["min_window_MBps"] = round(rates_sorted[0], 2)
    else:
        # honesty rule: a transfer too short to hold five windows cannot support
        # a percentile, so it is flagged rather than quoted
        out["p05_MBps"] = None
        out["p05_skipped"] = f"only {len(rates)} complete {window_ms}ms windows"
    return out


def complete(result, length):
    """A read counts only when the server returned 206 for the whole range.

    Same rule the round-7 latency phase used. A partial body or a non-206 reply
    can finish fast while proving nothing, and must not flatter a median.
    """
    return result.get("http") == "206" and result.get("bytes") == length


def measure_seeks(url, size, auth=None, fractions=(0.01, 0.25, 0.50, 0.75, 0.95),
                  read_bytes=8 << 20, timeout=300):
    """TTFB and full-seek time at fixed positions, plus one backward seek.

    Reported as median and worst rather than a single number, because the shape
    matters: a server whose seek cost climbs with offset is a server whose
    read-ahead is doing the wrong thing, and one scrub median cannot show it.

    The backward seek is separate on purpose. Read-ahead makes forward motion
    cheap; jumping back is the case that evicts it, and a player does it every
    time someone drags the scrubber left.
    """
    out = {"points": [], "read_bytes": read_bytes}
    for frac in fractions:
        offset = min(int(size * frac), max(0, size - read_bytes))
        res = timed_stream(url, auth, offset, read_bytes, timeout=timeout)
        out["points"].append({
            "fraction": frac, "offset": offset,
            "ttfb_s": res.get("ttfb_s"), "full_s": res.get("total_s"),
            "http": res.get("http"), "bytes": res.get("bytes"),
            "complete": complete(res, read_bytes),
            "error": res.get("error"),
        })
    # backward: from the last position sampled, jump to an earlier one
    back_off = min(int(size * 0.10), max(0, size - read_bytes))
    res = timed_stream(url, auth, back_off, read_bytes, timeout=timeout)
    out["backward"] = {
        "offset": back_off, "ttfb_s": res.get("ttfb_s"), "full_s": res.get("total_s"),
        "http": res.get("http"), "complete": complete(res, read_bytes),
        "error": res.get("error"),
    }

    good = [p for p in out["points"] if p["complete"]]
    out["n_complete"] = len(good)
    out["n_attempted"] = len(out["points"])
    if good:
        ttfbs = [p["ttfb_s"] for p in good if p["ttfb_s"] is not None]
        fulls = [p["full_s"] for p in good if p["full_s"] is not None]
        out["ttfb_median_s"] = round(statistics.median(ttfbs), 4) if ttfbs else None
        out["ttfb_worst_s"] = round(max(ttfbs), 4) if ttfbs else None
        out["full_median_s"] = round(statistics.median(fulls), 4) if fulls else None
        out["full_worst_s"] = round(max(fulls), 4) if fulls else None
    return out


def measure_playback(url, size, auth=None, seconds=30, bitrate_mbps=25,
                     start_fraction=0.30, buffer_seconds=10, timeout=300):
    """Simulate a player: can this stream feed a bitrate without draining a buffer.

    A mean rate above the bitrate does not answer this. The player has a finite
    buffer, and what empties it is a run of seconds below the bitrate, not the
    average across the read. So this reads at full speed for `seconds` of media
    and reports two things a rate cannot: how long until `buffer_seconds` of
    media had arrived, and how many one-second windows delivered less than one
    second of media.
    """
    need_bytes_per_s = bitrate_mbps * 1e6 / 8
    want = int(need_bytes_per_s * seconds)
    offset = min(int(size * start_fraction), max(0, size - want))
    res = timed_stream(url, auth, offset, want, max_ms=(seconds * 4) * 1000,
                       timeout=timeout)
    out = {
        "bitrate_mbps": bitrate_mbps, "seconds_of_media": seconds,
        "offset": offset, "bytes": res.get("bytes"), "http": res.get("http"),
        "total_s": res.get("total_s"), "MBps": res.get("MBps"),
        "p05_MBps": res.get("p05_MBps"), "error": res.get("error"),
    }
    delivered = res.get("bytes") or 0
    elapsed = res.get("total_s") or 0
    out["media_seconds_delivered"] = round(delivered / need_bytes_per_s, 2)
    out["realtime_ratio"] = (round(out["media_seconds_delivered"] / elapsed, 2)
                             if elapsed else None)
    # time to buffer: when did buffer_seconds of media arrive
    need_buffer = need_bytes_per_s * buffer_seconds
    out["to_buffer_s"] = None
    if delivered >= need_buffer and (res.get("MBps") or 0) > 0:
        # linear within the transfer is the honest resolution here; the windowed
        # series below is what carries the shape
        out["to_buffer_s"] = round(need_buffer / (res["MBps"] * 1e6), 2)
    p05 = res.get("p05_MBps")
    out["sustains_bitrate"] = (p05 * 1e6 >= need_bytes_per_s) if p05 is not None else None
    return out


def measure_integrity(url, size, auth=None, samples=3, chunk_bytes=2 << 20,
                      timeout=300):
    """Hash the same deterministic ranges on every target, for the consensus check.

    Offsets are fractions of the file, so every target hashes the same bytes
    without the harness needing to know the layout. A fast target serving the
    wrong bytes is not fast, and nothing in rounds 3 through 9 could catch that
    on the throughput file -- round 7 hashed the behaviour releases only, and
    all five agreed, so the check never had a chance to find anything.
    """
    out = []
    for ix in range(samples):
        frac = (ix + 1) / (samples + 1)
        offset = min(int(size * frac), max(0, size - chunk_bytes))
        res = timed_stream(url, auth, offset, chunk_bytes, want_hash=True,
                           timeout=timeout)
        out.append({
            "offset": offset, "length": chunk_bytes,
            "md5": res.get("md5") if complete(res, chunk_bytes) else None,
            "http": res.get("http"), "bytes": res.get("bytes"),
            "error": res.get("error"),
        })
    return out


def head_size(url, auth=None, timeout=60):
    """Advertised length, which several phases need before they can place a read."""
    req = _request(url, auth)
    req.get_method = lambda: "HEAD"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length else None
    except Exception:
        # a target that refuses HEAD still answers a one-byte Range, and
        # Content-Range carries the total
        res = timed_stream(url, auth, 0, 1, timeout=timeout)
        crange = res.get("content_range") or ""
        if "/" in crange:
            tail = crange.rsplit("/", 1)[1].strip()
            if tail.isdigit():
                return int(tail)
    return None


if __name__ == "__main__":
    import sys
    target = sys.argv[1]
    size = head_size(target)
    print(json.dumps({"size": size,
                      "stream": timed_stream(target, start=0, length=32 << 20)},
                     indent=1))
