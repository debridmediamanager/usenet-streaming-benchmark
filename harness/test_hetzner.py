#!/usr/bin/env python3
"""The Hetzner runners keep the benchmark account on its one reserved IPv4.

Drives hetzner-round.sh --selftest end to end against a fake hcloud and ssh
that model the Primary IP the way Hetzner does: it outlives the server, it can
be attached to one server at a time, and `primary-ip delete` destroys it.
"""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parent
RESERVED_ID, RESERVED_IP = "100000001", "192.0.2.10"

FAKE_HCLOUD = textwrap.dedent(f"""\
    #!/bin/bash
    S="$FAKE_STATE"
    echo "$*" >> "$S/calls"
    case "$1 $2" in
      "context list") echo "bench";;
      "ssh-key list") echo "me@example";;
      "primary-ip describe")
        [ -e "$S/ip-deleted" ] && exit 1
        if [[ "$*" == *".IP}}}}"* ]]; then
          echo "{RESERVED_ID} {RESERVED_IP} $(cat "$S/preassigned" 2>/dev/null || echo 0)"
        else
          a=0; [ -e "$S/server" ] && a=4242; echo "$a"
        fi;;
      "primary-ip list") [ -e "$S/server" ] && echo "{RESERVED_ID} $(cat "$S/name")";;
      "primary-ip delete") touch "$S/ip-deleted";;
      "server create")
        shift 2; while [ $# -gt 0 ]; do [ "$1" = --name ] && echo "$2" > "$S/name"; shift; done
        touch "$S/server";;
      "server describe") [ -e "$S/server" ] || exit 1; echo 4242;;
      "server ip") echo "$(cat "$S/server-ip" 2>/dev/null || echo {RESERVED_IP})";;
      "server delete") rm -f "$S/server";;
      *) echo "unexpected hcloud $*" >&2; exit 9;;
    esac
    """)

FAKE_SSH = textwrap.dedent(f"""\
    #!/bin/bash
    case "$*" in
      *ifconfig.me*) echo "$(cat "$FAKE_STATE/egress" 2>/dev/null || echo {RESERVED_IP})";;
      *"ip -6"*) echo 0;;
      *hostname*) echo "   remote says: fake, 2 cores";;
    esac
    exit 0
    """)


def executable(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ReservedIpTests(unittest.TestCase):
    def selftest(self, **state):
        tmp = tempfile.TemporaryDirectory(prefix="hetzner-test-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        bin_dir, s = root / "bin", root / "state"
        bin_dir.mkdir()
        s.mkdir()
        for name, value in state.items():
            (s / name.replace("_", "-")).write_text(value)
        executable(bin_dir / "hcloud", FAKE_HCLOUD)
        executable(bin_dir / "ssh", FAKE_SSH)
        executable(bin_dir / "ssh-keygen", "#!/bin/sh\nexit 0\n")
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                   FAKE_STATE=str(s), BOX_SSH_RETRY_S="0")
        run = subprocess.run(["bash", str(HERE / "hetzner-round.sh"), "--selftest"],
                             env=env, capture_output=True, text=True, timeout=60)
        calls = (s / "calls").read_text().splitlines() if (s / "calls").exists() else []
        return run, calls, s

    def test_box_is_created_on_the_reserved_ip_without_ipv6(self):
        run, calls, _ = self.selftest()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        create = next(c for c in calls if c.startswith("server create"))
        self.assertIn(f"--primary-ipv4 {RESERVED_ID}", create)
        self.assertIn("--without-ipv6", create)

    def test_teardown_deletes_the_server_and_never_the_reserved_ip(self):
        run, calls, s = self.selftest()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("server delete", " ".join(calls))
        self.assertFalse([c for c in calls if c.startswith("primary-ip delete")])
        self.assertFalse((s / "ip-deleted").exists())
        self.assertIn("reserved IP", run.stdout)

    def test_refuses_when_another_round_holds_the_ip(self):
        run, calls, _ = self.selftest(preassigned="777")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("another round is running", run.stderr)
        self.assertFalse([c for c in calls if c.startswith("server create")])

    def test_refuses_a_box_whose_egress_is_not_the_reserved_ip(self):
        run, _, _ = self.selftest(egress="203.0.113.9")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("not the reserved", run.stderr)

    def test_refuses_to_run_without_the_reserved_ip(self):
        run, calls, _ = self.selftest(ip_deleted="")
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse([c for c in calls if c.startswith("server create")])


if __name__ == "__main__":
    unittest.main()
