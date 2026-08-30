#!/usr/bin/env python3
"""Plex time-to-play, measured through the real Plex web app over CDP.

Per repetition, two numbers:
  press_play_s  clicking an episode's Play  -> its first rendered frame
  next_ep_s     clicking the player's Next  -> first frame of the next episode

Four things this had to get right, each of which silently produced a wrong
number before it was fixed:

* Clicks must be TRUSTED. A synthetic element.click() starts the first episode
  but the Next control does nothing at all: switching media needs user
  activation. Playwright's .click() goes through CDP Input, which counts.
* Playback starts from the SEASON page, using the episode row's own Play
  button. An episode's details page builds a one-item play queue, and then Next
  is present, enabled and inert.
* Every repetition runs in a FRESH PAGE. Plex's player survives a hash change,
  a full reload and its own close button, and the overlay it leaves behind eats
  pointer events.
* Each episode is marked watched then unwatched first, so the row says Play
  rather than Resume. A Resume starts mid-file and is not a cold open.

Repetitions use disjoint episode pairs, so nothing is ever served warm, and the
backing server is not restarted mid-run: that would drop the rclone mount under
Plex and mark the library unavailable.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

PLEX = "http://YOUR_PLEX_HOST:32400"
TOKEN = "YOUR_PLEX_TOKEN"
MID = "YOUR_PLEX_MACHINE_IDENTIFIER"
WEB = "https://app.plex.tv/desktop"
CDP = "http://127.0.0.1:9226"

LABEL_JS = """() => {
  const c = document.querySelector('[data-testid=playerControlsContainer]');
  return c ? (c.innerText || '').replace(/\\s+/g, ' ').slice(0, 90) : '';
}"""


def api(path, parse=True, **params):
    params["X-Plex-Token"] = TOKEN
    raw = urllib.request.urlopen(
        f"{PLEX}{path}?{urllib.parse.urlencode(params)}", timeout=30).read()
    return ET.fromstring(raw) if parse else raw


def log(*a, **kw):
    print(*a, flush=True)


def sessions():
    return api("/status/sessions")


def session_info():
    """The session that is playing right now.

    Closing a page mid-playback strands a PAUSED session that has lost its
    Session id and cannot be terminated. Taking the first Video in the list
    would then report a stale episode and silently invalidate the check.
    """
    vids = list(sessions().iter("Video"))
    live = [v for v in vids
            if (v.find("Player") is not None
                and v.find("Player").get("state") == "playing")]
    for v in (live or vids):
        ts = v.find("TranscodeSession")
        dec = "direct play"
        if ts is not None:
            dec = f"video={ts.get('videoDecision','?')} audio={ts.get('audioDecision','?')}"
        return v.get("ratingKey"), dec
    return None, None


def clear_sessions(budget=25):
    """Terminate, and fall back to a timeline stop.

    A session whose page has gone away loses its Session id, and then terminate
    cannot touch it; only a stopped timeline posted as that player clears it.
    """
    end = time.time() + budget
    while time.time() < end:
        x = sessions()
        if x.get("size") == "0":
            return True
        for v in x.iter("Video"):
            s, pl = v.find("Session"), v.find("Player")
            cid = pl.get("machineIdentifier") if pl is not None else "bench"
            if s is not None and s.get("id"):
                try:
                    api("/status/sessions/terminate", parse=False,
                        sessionId=s.get("id"), reason="bench reset")
                except Exception:
                    pass
            try:
                q = urllib.parse.urlencode(
                    {"ratingKey": v.get("ratingKey"), "key": v.get("key"),
                     "state": "stopped", "time": 0,
                     "duration": v.get("duration") or 0, "X-Plex-Token": TOKEN})
                urllib.request.urlopen(urllib.request.Request(
                    f"{PLEX}/:/timeline?{q}",
                    headers={"X-Plex-Client-Identifier": cid,
                             "X-Plex-Product": "Plex Web"}), timeout=20).read()
            except Exception:
                pass
        time.sleep(6)
    return sessions().get("size") == "0"


def reset_watch(rk):
    """Unwatched and with no resume offset, so the row offers Play, not Resume."""
    for path in ("/:/scrobble", "/:/unscrobble"):
        try:
            api(path, parse=False, key=rk, identifier="com.plexapp.plugins.library")
        except Exception:
            pass


PROBE = """(() => {
  clearInterval(window.__pt);
  window.__p = {t0: performance.now(), hit: null};
  window.__pt = setInterval(() => {
    const v = document.querySelector('video');
    if (!v) return;
    if (window.__p.hit === null && v.videoWidth > 0 && v.currentTime > 0.05 && !v.paused) {
      window.__p.hit = performance.now() - window.__p.t0;
    }
  }, 20);
  return true;
})()"""

# the player caption carries a ticking clock, so "the text changed" is not a
# useful signal. Only the episode number is.
PROBE_NEXT = """((prevEp) => {
  clearInterval(window.__pt);
  window.__p = {t0: performance.now(), hit: null};
  const epNow = () => {
    const c = document.querySelector('[data-testid=playerControlsContainer]');
    const m = c && (c.innerText || '').match(/S\\d+\\s*[\\u00b7.\\-]\\s*E(\\d+)/);
    return m ? m[1] : null;
  };
  window.__pt = setInterval(() => {
    const v = document.querySelector('video');
    if (!v) return;
    const e = epNow();
    if (window.__p.hit === null && e && e !== prevEp &&
        v.videoWidth > 0 && v.currentTime > 0.05 && !v.paused) {
      window.__p.hit = performance.now() - window.__p.t0;
    }
  }, 20);
  return true;
})"""


def wait_hit(pg, budget):
    end = time.time() + budget
    while time.time() < end:
        st = json.loads(pg.evaluate("""JSON.stringify((() => {
            const v = document.querySelector('video');
            return {hit: (window.__p||{}).hit, paused: v ? v.paused : null};
        })())"""))
        if st.get("hit") is not None:
            return round(st["hit"] / 1000.0, 3)
        if st.get("paused"):
            pg.evaluate("() => {const v=document.querySelector('video'); if(v) v.play().catch(()=>{});}")
        time.sleep(0.2)
    return None


def ep_of(label):
    m = re.search(r"S\d+\s*[·.\-]\s*E(\d+)", label or "")
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--section", required=True)
    ap.add_argument("--season", required=True)
    ap.add_argument("--pairs", default="1-2,3-4,5-6,9-10")
    ap.add_argument("--budget", type=float, default=120)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    eps = {}
    for v in api(f"/library/sections/{a.section}/all", type=4).iter("Video"):
        if v.get("index"):
            eps[int(v.get("index"))] = v.get("ratingKey")

    season_url = f"{WEB}/#!/server/{MID}/details?key=%2Flibrary%2Fmetadata%2F{a.season}"
    pairs = [tuple(int(x) for x in q.split("-")) for q in a.pairs.split(",")]
    results = []

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        boot = ctx.pages[0] if ctx.pages else ctx.new_page()
        boot.goto(WEB + "/", wait_until="domcontentloaded", timeout=60000)
        if not boot.evaluate("localStorage.getItem('myPlexAccessToken')"):
            boot.evaluate("t => localStorage.setItem('myPlexAccessToken', t)", TOKEN)
        time.sleep(2)

        for rep, (first, second) in enumerate(pairs):
            rec = {"server": a.server, "rep": rep,
                   "ep1": f"E{first:02d}", "ep2": f"E{second:02d}"}
            clear_sessions()
            reset_watch(eps.get(first))
            reset_watch(eps.get(second))
            pg = ctx.new_page()
            try:
                pg.goto(season_url, wait_until="domcontentloaded", timeout=60000)
                ok, end = False, time.time() + 90
                while time.time() < end:
                    time.sleep(1.5)
                    n = pg.evaluate("() => document.querySelectorAll('[data-testid=cellItem]').length")
                    if n and n >= first:
                        ok = True
                        break
                if not ok:
                    rec["error"] = "season page never rendered"
                    results.append(rec); log(json.dumps(rec)); continue

                cells = pg.query_selector_all("[data-testid=cellItem]")
                cells[first - 1].hover(timeout=15000)
                time.sleep(1)
                btn = cells[first - 1].query_selector(
                    "[aria-label='Play'], [aria-label='Resume']")
                if btn is None:
                    rec["error"] = f"no Play control on the row for episode {first}"
                    results.append(rec); log(json.dumps(rec)); continue
                rec["play_control"] = btn.get_attribute("aria-label")

                pg.evaluate(PROBE)
                btn.click(timeout=15000)          # trusted click
                rec["press_play_s"] = wait_hit(pg, a.budget)
                time.sleep(2)
                rk, dec = session_info()
                rec["ep1_playing_key"] = rk
                rec["ep1_decision"] = dec
                rec["ep1_correct"] = (rk == eps.get(first))

                if rec["press_play_s"] is not None:
                    for i in range(5):
                        pg.mouse.move(600 + i * 40, 400 + i * 10)
                        time.sleep(0.3)
                    prev_ep = ep_of(pg.evaluate(LABEL_JS))
                    rec["ep1_label_ep"] = prev_ep
                    nxt = pg.query_selector("[data-testid=nextButton]")
                    if nxt is None:
                        rec["error"] = "no next-episode control in the player"
                    else:
                        pg.evaluate("e => (" + PROBE_NEXT + ")(e)", prev_ep)
                        nxt.click(timeout=15000)   # trusted click
                        rec["next_control"] = nxt.get_attribute("aria-label") or "Next"
                        rec["next_ep_s"] = wait_hit(pg, a.budget)
                        rec["ep2_label_ep"] = ep_of(pg.evaluate(LABEL_JS))
                        time.sleep(2)
                        rk2, dec2 = session_info()
                        rec["ep2_playing_key"] = rk2
                        rec["ep2_decision"] = dec2
                        rec["ep2_correct"] = (rk2 == eps.get(second))
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            finally:
                try:
                    close = pg.query_selector("[data-testid=closeButton]")
                    if close is not None:
                        close.click(timeout=8000)   # trusted: Plex posts its own stop
                    time.sleep(3)
                except Exception:
                    try:
                        pg.evaluate("""() => {
                            const v = document.querySelector('video');
                            if (v) { try { v.pause(); } catch (e) {} }
                        }""")
                    except Exception:
                        pass
                try:
                    pg.close()
                except Exception:
                    pass
                clear_sessions()

            results.append(rec)
            log(json.dumps(rec), flush=True)
            json.dump(results, open(a.out or f"/tmp/plex_ttp_{a.server}.json", "w"), indent=1)

    log("wrote", a.out or f"/tmp/plex_ttp_{a.server}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
