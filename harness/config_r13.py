#!/usr/bin/env python3
"""Render secret-bearing files on zen only; JSON is also valid YAML 1.2."""
import json
import os
from pathlib import Path
import sqlite3
import sys

KEY = "benchbenchbenchbenchbenchbench12"
ROOT = Path(os.environ.get("BENCH", "/home/ben/bench-round13-20261001"))
if ROOT != Path("/home/ben/bench-round13-20261001") or ROOT.is_symlink():
    raise SystemExit("Refusing non-round13 BENCH or symlink")
if int(os.environ.get("CONNS", "10")) != 10:
    raise SystemExit("Round13 requires CONNS=10")
HOST = os.environ.get("NNTP_HOST", "newswest.frugalusenet.com")
if HOST != "newswest.frugalusenet.com" or int(os.environ.get("NNTP_PORT", "563")) != 563:
    raise SystemExit("Only newswest.frugalusenet.com:563 TLS is permitted")
USER, PASS = os.environ["NNTP_USER"], os.environ["NNTP_PASS"]
if any("\n" in v or "\r" in v for v in (USER, PASS)):
    raise SystemExit("Credentials cannot contain env-file line breaks")


def save(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def provider():
    return {"ProviderId": "11111111-2222-3333-4444-555555555555", "Type": 1,
            "Host": HOST, "Port": 563, "UseSsl": True, "SkipTlsVerification": False,
            "User": USER, "Pass": PASS, "MaxConnections": 10,
            "MaxTransferConnections": 10, "Priority": 0, "StorageGroup": ""}


def infini_settings():
    return {
        "usenet.providers": json.dumps({"Providers": [provider()]}),
        "usenet.max-download-connections": "10", "usenet.max-queue-connections": "10",
        "usenet.queue-pipelining.enabled": "true", "usenet.queue-pipelining.depth": "4",
        "usenet.streaming-body-batch-width": "4", "usenet.pipelined-body-requests": "true",
        "usenet.article-buffer-size": "40", "usenet.in-flight-article-budget-mb": "256",
        "usenet.shared-streams.enabled": "true", "usenet.shared-streams.ring-mb": "32",
        "usenet.warm-connections.enabled": "true", "usenet.warm-connections.floor": "2",
        "usenet.idle-connection-timeout-seconds": "120",
        "usenet.segment-cache.enabled": "false", "queue.worker-count": "2",
        "repair.enable": "true", "repair.par2-enabled": "true",
        "repair.par2-max-memory-mb": "256", "repair.par2-fetch-concurrency": "2",
        "repair.par2-max-release-gb": "200", "repair.par2-max-missing-slices": "64",
        "repair.healthcheck-workers": "1", "repair.healthcheck-concurrency": "2",
        "api.key": KEY, "api.completed-downloads-dir": "/completed",
        "webdav.user": "usenet", "webdav.pass": "usenet",
    }


def nzbdav_settings():
    p = provider()
    p.pop("MaxTransferConnections")
    return {"usenet.providers": json.dumps({"Providers": [p]}),
            "usenet.max-download-connections": "10", "usenet.article-buffer-size": "40",
            "api.key": KEY, "api.completed-downloads-dir": "/completed"}


def seed():
    path = ROOT / "nzbdav-og/config-r10/db.sqlite"
    db = sqlite3.connect(f"file:{path}?mode=rw", uri=True)
    with db:
        for k, v in nzbdav_settings().items():
            db.execute("INSERT INTO ConfigItems(ConfigName,ConfigValue) VALUES (?,?) "
                       "ON CONFLICT(ConfigName) DO UPDATE SET ConfigValue=excluded.ConfigValue", (k, v))
    for k, v in nzbdav_settings().items():
        assert db.execute("SELECT ConfigValue FROM ConfigItems WHERE ConfigName=?", (k,)).fetchone() == (v,)
    roots = db.execute("SELECT COUNT(*) FROM DavItems WHERE Id LIKE '00000000-0000-0000-0000-%'").fetchone()[0]
    releases = db.execute("SELECT COUNT(*) FROM DavItems WHERE Id NOT LIKE '00000000-0000-0000-0000-%'").fetchone()[0]
    assert roots == 5 and releases == 0, (roots, releases)
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()
    path.chmod(0o600)
    print("NZBDav migration-created SQLite: five roots, empty library, provider/download=10")


def render():
    save("zurgrun/config.yml", {
        "zurg": "v1", "providers": [{"type": "nzb", "nntp": {
            "host": HOST, "port": 563, "tls": True, "username": USER, "password": PASS,
            "connections": 10, "pipeline_depth": 4, "warm_connections": 2, "cache_size_mb": 256}}],
        "port": 19998, "host": "127.0.0.1", "base_url": "http://127.0.0.1:19998",
        "check_for_changes_every_secs": 5, "enable_repair": True,
        "par2_patch_cache_mb": 512, "memory_limit_mb": 1024, "nzb_segments": "mmap",
        "load_dumped_torrents": False, "serve_strm_files": False, "save_strm_files": False,
        "rclone_enabled": False, "auto_analyze_new_torrents": False, "log_level": "INFO",
        "directories": {"all": {"group_order": 1, "filters": [{"regex": "/.*/"}]}}})
    save("altmount/config.yaml", {
        "webdav": {"port": 18081, "user": "usenet", "password": "usenet"},
        "api": {"prefix": "/api", "key_override": KEY,
                "allowed_origins": ["http://127.0.0.1:18081", "http://localhost:18081"]},
        "auth": {"login_required": False},
        "database": {"path": str(ROOT / "altmount/cfg/altmount.db")},
        "metadata": {"root_path": str(ROOT / "altmount/cfg/metadata")},
        "streaming": {"max_prefetch": 60, "failure_masking": {"enabled": False, "threshold": 3}},
        "segment_cache": {"memory_mb": 256, "enabled": False, "cache_path": str(ROOT / "altmount/cfg/segment-cache")},
        "memory_limit_mb": 1024, "rclone": {"mount_enabled": False},
        "import": {"max_processor_workers": 2, "queue_processing_interval_seconds": 5,
                   "segment_sample_percentage": 1, "import_strategy": "NONE", "max_concurrent_imports": 2},
        "health": {"enabled": True, "check_interval_seconds": 60, "max_concurrent_segment_checks": 10,
                   "repair": {"enabled": True}},
        "par2_repair": {"enabled": True, "max_connections": 10, "max_memory_mb": 256,
                        "max_concurrent_jobs": 1, "max_repair_ratio": 1.0, "repair_on_import": True},
        "sabnzbd": {"enabled": False}, "arrs": {"enabled": False},
        "log": {"file": str(ROOT / "altmount/cfg/altmount.log"), "level": "info"},
        "providers": [{"id": "bench-round13", "host": HOST, "port": 563, "username": USER,
                       "password": PASS, "max_connections": 10, "min_connections_alive": 2,
                       "inflight_requests": 10, "stat_inflight_requests": 100,
                       "tls": True, "insecure_tls": False, "enabled": True, "is_backup_provider": False}]})
    save("decyrun/config.json", {
        "bind_address": "127.0.0.1", "port": "18282", "log_level": "info", "use_auth": False,
        "disable_webdav": False, "download_folder": str(ROOT / "decyrun/downloads"), "max_active_downloads": 2,
        "usenet": {"providers": [{"host": HOST, "port": 563, "username": USER, "password": PASS,
                                 "ssl": True, "max_connections": 10, "priority": 1}],
                   "max_connections": 10, "processing_max_connections": 10, "read_ahead": "32MB",
                   "buffer_memory": "256MB", "socket_read_buffer": "0", "socket_write_buffer": "0",
                   "conn_idle_timeout": "2m", "disk_buffer_path": str(ROOT / "decyrun/streams")},
        "categories": ["movies", "tv"],
        "repair": {"enabled": True, "source": "managed", "schedule": "5m", "workers": 2,
                   "nntp_connection_percent": 20, "strategy": "per_entry", "recheck_interval": "1m", "auto_repair": True}})
    env = ROOT / "infinidysk/r13.env"
    env.parent.mkdir(parents=True, exist_ok=True)
    rows = {"PORT": "18094", "ASPNETCORE_URLS": "http://127.0.0.1:18092",
            "BACKEND_URL": "http://127.0.0.1:18092", "CONFIG_PATH": "/config", "LOG_LEVEL": "warning",
            "FRONTEND_BACKEND_API_KEY": KEY, "WEBDAV_USER": "usenet", "WEBDAV_PASSWORD": "usenet",
            "DOTNET_PROCESSOR_COUNT": "2", "DOTNET_GCHeapHardLimit": "60000000"}
    for k, v in infini_settings().items():
        rows["NZBDAV_CONFIG__" + k.replace("-", "_").replace(".", "__").upper()] = v
    env.write_text("".join(f"{k}={v}\n" for k, v in rows.items()))
    env.chmod(0o600)
    print("Rendered isolated configs (secret contents suppressed)")


if __name__ == "__main__":
    {"render": render, "seed": seed}[sys.argv[1]]()
