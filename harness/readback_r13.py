#!/usr/bin/env python3
"""Read the one already-running target; never start services or print credentials."""
import json
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode


def fetch(port, path, fields=None):
    from config_r13 import KEY

    data = urlencode(fields).encode() if fields is not None else None
    req = Request(f"http://127.0.0.1:{port}{path}", data=data,
                  headers={"x-api-key": KEY, "Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def match(got, expected, skip=()):
    for key, value in expected.items():
        if key in skip:
            continue
        if isinstance(value, dict):
            match(got[key], value, skip)
        elif isinstance(value, list):
            assert len(got[key]) == len(value), key
            for actual, wanted in zip(got[key], value):
                if isinstance(wanted, dict):
                    match(actual, wanted, skip)
                else:
                    assert actual == wanted, f"Effective setting differs: {key}"
        else:
            # Go's omitempty omits these false booleans, not their effective value.
            if key in ("use_auth", "disable_webdav"):
                actual = got.get(key, False)
            else:
                actual = got[key]
            assert actual == value, f"Effective setting differs: {key}"


def main():
    from config_r13 import ROOT, KEY, infini_settings, nzbdav_settings

    target = sys.argv[1]
    if target in ("infinidysk", "nzbdav-og"):
        expected = infini_settings() if target == "infinidysk" else nzbdav_settings()
        got = fetch(18092 if target == "infinidysk" else 18093, "/api/get-config",
                    [("config-keys", k) for k in expected] + [("apikey", KEY)])
        rows = got.get("configItems", got.get("ConfigItems"))
        values = {r.get("configName", r.get("ConfigName")): r.get("configValue", r.get("ConfigValue")) for r in rows}
        for k, v in expected.items():
            if k in ("usenet.providers", "webdav.pass", "api.key"):
                continue
            assert values[k] == v, f"Effective setting differs: {k}"
        providers = json.loads(values["usenet.providers"])["Providers"]
        assert len(providers) == 1
        p = providers[0]
        assert p["Host"] == "newswest.frugalusenet.com" and p["Port"] == 563
        assert p["UseSsl"] is True and p["MaxConnections"] == 10
    elif target in ("altmount", "decypharr"):
        path = "altmount/config.yaml" if target == "altmount" else "decyrun/config.json"
        expected = json.loads((ROOT / path).read_text())
        got = fetch(18081 if target == "altmount" else 18282, "/api/config")
        got = got.get("data", got)
        if target == "altmount":
            # The CLI accepts this knob; ImportAPIResponse omits it. Keep the
            # configured cap, and compare the API's actual projection.
            assert expected["import"].pop("max_concurrent_imports") == 2
        match(got, expected, skip=("password", "username", "key_override", "id", "log", "categories"))
    elif target == "zurg":
        got = fetch(19998, "/config")["config"]
        expected = json.loads((ROOT / "zurgrun/config.yml").read_text())
        for k in ("enable_repair", "rclone_enabled", "nzb_segments", "par2_patch_cache_mb", "check_for_changes_every_secs"):
            assert got[k] == expected[k], f"Effective setting differs: {k}"
        # Dashboard API does not expose NNTP pool options; startup logs and live socket gate cover those.
    else:
        raise SystemExit("Unknown existing target")
    print(f"{target}: effective config readback passed (secret contents suppressed)")


if __name__ == "__main__":
    main()
