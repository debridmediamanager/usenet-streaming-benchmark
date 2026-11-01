#!/usr/bin/env python3
"""Pinned AIO filesystem provisioning; never starts a service.

On the round's host, export its designated account (NNTP_*), then invoke:
  python3 harness/prep_aiostreams_r13.py build
  python3 harness/prep_aiostreams_r13.py prepare
  python3 harness/prep_aiostreams_r13.py validate
  python3 harness/prep_aiostreams_r13.py reset
build fetches pinned source and runs its official Dockerfile. prepare renders a
private Docker env file and creates a STOPPED container. reset retires the whole
data directory (SQLite, NZBs, segment caches), refusing a running container.
The runner owns docker start/stop and readiness; no action starts NNTP work.
ROUND (round_profile.py) fixes BENCH, the provider HOST/PORT, the revision,
image and container name; NNTP_HOST/PORT/USER/PASS are required for prepare.
CONNS must equal 10. Runtime port is 13000.
Outputs: $BENCH/src/aiostreams-<revision>, $BENCH/aiostreams/runtime.env,
$BENCH/aiostreams/data, and image aiostreams:<round>-<revision[:12]>.
Source-backed tuning: prefetch20 matches upstream's ~2x-connection useful ceiling;
retain the high profile's 8GB disk cache and 40 command slots (10 sockets x4).
Census12 shares the same pool; streaming priority0.8 avoids starving background
checks. Keep lazy RAR, CRC and MKV padding on. par2/decode.ts explicitly does NOT
implement Reed-Solomon repair. No fabricated repair flag or external arr added.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import subprocess

import round_profile as profile

REVISION = profile.revision('aiostreams')
BENCH = Path(os.environ.get('BENCH', profile.BENCH))
CONTAINER = profile.container('aiostreams')
IMAGE = profile.image('aiostreams')
LABEL = 'usenet-benchmark.round'
ROUND = profile.TAG
HOME = BENCH / 'aiostreams'
SOURCE = BENCH / 'src' / ('aiostreams-' + REVISION)
ENV = HOME / 'runtime.env'
DATA = HOME / 'data'


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def inspect():
    result = subprocess.run(['docker', 'container', 'inspect', CONTAINER],
                            capture_output=True, text=True)
    if result.returncode:
        # Distinguish a missing container from an unavailable Docker daemon.
        run('docker', 'info', '--format', '{{.ServerVersion}}', capture=True)
        if 'No such' not in result.stderr:
            raise RuntimeError(result.stderr.strip())
        return None
    spec = json.loads(result.stdout)[0]
    if spec['Config'].get('Labels', {}).get(LABEL) != ROUND:
        raise RuntimeError('Refusing to touch unowned container ' + CONTAINER)
    if spec['State']['Running']:
        raise RuntimeError('Stop the benchmark container before provisioning/reset')
    return spec


def read_env():
    return dict(line.split('=', 1) for line in ENV.read_text().splitlines())


def validate():
    cfg = read_env()
    providers = json.loads(cfg['USENET_PROVIDERS'])
    assert len(providers) == 1
    p = providers[0]
    assert p['host'] == profile.HOST and p['port'] == profile.PORT
    assert p['tls'] and not p['tlsSkipVerify']
    assert p['maxConnections'] == 10 and p['pipelineDepth'] == 4
    assert p['enabled'] and not p['isBackup']
    assert p['username'] and p['password']
    assert cfg['USENET_PERFORMANCE_PROFILE'] == 'custom'
    assert cfg['USENET_MAX_CONCURRENT_DOWNLOADS'] == '40'
    assert cfg['SHARES_WEBDAV_ENABLED'] == 'true'
    assert cfg['SHARES_FUSE_ENABLED'] == cfg['SHARES_NFS_ENABLED'] == 'false'
    assert cfg['DATABASE_URI'] == 'sqlite:///app/data/db.sqlite'
    assert cfg['DISK_CACHE_DIR'] == '/app/data/cache'
    assert len(cfg['SECRET_KEY']) == 64
    assert ENV.stat().st_mode & 0o077 == 0
    print('AIO static config: one TLS provider, 10 sockets, depth4, native WebDAV13000')


def reset():
    inspect()
    HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    if DATA.exists():
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        DATA.rename(HOME / ('data.before-' + stamp))
    DATA.mkdir(mode=0o700)


def build():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCE.exists():
        SOURCE.mkdir()
        run('git', 'init', str(SOURCE))
        run('git', '-C', str(SOURCE), 'remote', 'add', 'origin',
            'https://github.com/Viren070/AIOStreams.git')
    head = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True)
    if head.returncode:
        run('git', '-C', str(SOURCE), 'fetch', '--depth=1', 'origin', REVISION)
        run('git', '-C', str(SOURCE), 'checkout', '--detach', REVISION)
    if run('git', '-C', str(SOURCE), 'rev-parse', 'HEAD', capture=True).strip() != REVISION:
        raise RuntimeError('Isolated source revision mismatch; refusing checkout overwrite')
    if run('git', '-C', str(SOURCE), 'status', '--porcelain', capture=True).strip():
        raise RuntimeError('Isolated source has changes; refusing to build modified source')
    run('docker', 'build', '--label', LABEL + '=' + ROUND,
        '--label', 'org.opencontainers.image.revision=' + REVISION,
        '-t', IMAGE, str(SOURCE))


def prepare():
    if os.environ.get('CONNS', '10') != '10':
        raise RuntimeError('This round requires exactly 10 connections')
    profile.check_provider(os.environ.get('NNTP_HOST'), os.environ.get('NNTP_PORT', '563'))
    user, password = os.environ['NNTP_USER'], os.environ['NNTP_PASS']
    if not user or not password:
        raise RuntimeError('Designated benchmark credentials are empty')
    spec = inspect()
    image = json.loads(run('docker', 'image', 'inspect', IMAGE, capture=True))[0]
    labels = image['Config'].get('Labels', {})
    if labels.get('org.opencontainers.image.revision') != REVISION:
        raise RuntimeError('Build the pinned benchmark image first')
    HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    old_key = read_env().get('SECRET_KEY') if ENV.exists() else None
    provider = dict(id='bench-' + profile.ROUND, name='Benchmark ' + profile.ROUND,
                    host=profile.HOST, port=profile.PORT, tls=True,
                    tlsSkipVerify=False, username=user, password=password,
                    maxConnections=10, priority=0, isBackup=False, enabled=True,
                    pipelineDepth=4)
    cfg = dict(PORT='13000', BASE_URL='http://127.0.0.1:13000',
               INTERNAL_URL='http://127.0.0.1:13000',
               SECRET_KEY=old_key or secrets.token_hex(32),
               DATABASE_URI='sqlite:///app/data/db.sqlite', DISK_CACHE_DIR='/app/data/cache',
               NODE_ENV='production', LOG_LEVEL='warn', LOG_SENSITIVE_INFO='false',
               AIOSTREAMS_AUTH='usenet:usenet',
               AIOSTREAMS_AUTH_PERMISSIONS='usenet=sabnzbd|webdav',
               SHARES_WEBDAV_ENABLED='true', SHARES_FUSE_ENABLED='false', SHARES_NFS_ENABLED='false',
               USENET_PROVIDERS=json.dumps([provider], separators=(',', ':')),
               USENET_PERFORMANCE_PROFILE='custom', USENET_MAX_CONCURRENT_DOWNLOADS='40',
               USENET_PREFETCH_SEGMENTS='20', USENET_SEGMENT_DISK_CACHE_BYTES='8000000000',
               USENET_MAX_CONCURRENT_INSPECTS='4', USENET_CENSUS_SHADOW_CONCURRENCY='12',
               USENET_STREAMING_PRIORITY='0.8', USENET_LAZY_RAR_RESOLUTION='true',
               USENET_VERIFY_MODE='census', USENET_VERIFY_BUDGET_MS='0',
               USENET_VERIFY_ARTICLE_CRC='true', USENET_MATROSKA_HOLE_FILL='true',
               USENET_DAMAGE_POLICY='strict', USENET_RECHECK_SCOPE='off',
               USENET_SABNZBD_API_ENABLED='true', SETTINGS_REFRESH_INTERVAL='0')
    if profile.ROUND != 'r13':
        # new upstream after r13: an ffprobe pass over the same engine. Its
        # defaults never fire on SAB+WebDAV, but a moved default would add reads.
        cfg['MEDIA_INFO_PROBE'] = 'false'
    with os.fdopen(os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        os.chmod(ENV, 0o600)
        for key, value in cfg.items():
            if '\n' in value or '\r' in value:
                raise RuntimeError('Multiline Docker env value rejected')
            f.write(key + '=' + value + '\n')
    validate()
    if spec:
        run('docker', 'container', 'rm', CONTAINER)
    reset()
    run('docker', 'create', '--name', CONTAINER, '--label', LABEL + '=' + ROUND,
        '--label', 'com.centurylinklabs.watchtower.enable=false',
        '--network', 'host', '--restart', 'no', '--env-file', str(ENV),
        '--mount', 'type=bind,src=' + str(DATA) + ',dst=/app/data', IMAGE)
    print('Created STOPPED ' + CONTAINER + '; source revision ' + REVISION)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'prepare', 'reset', 'validate'))
    args = parser.parse_args()
    profile.check_bench(BENCH)
    globals()[args.action]()


if __name__ == '__main__':
    main()
