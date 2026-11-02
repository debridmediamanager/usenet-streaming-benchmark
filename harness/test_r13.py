#!/usr/bin/env python3
"""Connection isolation, effective-config boundaries and real-corpus damage controls."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import corpus_r10 as corpus
import damage_r10 as damage
from readback_r13 import match
from run_r13 import check_counts, select_field
from census_r14 import verdict
from tables_r14 import fresh_seeks

REPO = Path(__file__).resolve().parent.parent


def fixture(name):
    return json.loads((REPO / "fixtures" / name).read_text())


class ConnectionGateTests(unittest.TestCase):
    def test_rejects_auxiliary_pool_beyond_total_budget(self):
        with self.assertRaisesRegex(RuntimeError, "budget exceeded"):
            check_counts({"aiostreams": 11})

    def test_rejects_overlap_even_below_aggregate_budget(self):
        with self.assertRaisesRegex(RuntimeError, "Concurrent"):
            check_counts({"zurg": 4, "altmount": 4})

    def test_rejects_unknown_account_consumer_during_target_run(self):
        with self.assertRaisesRegex(RuntimeError, "Concurrent"):
            check_counts({"nzbdav-og": 10, "unowned-provider-consumer": 1})


class EffectiveConfigTests(unittest.TestCase):
    def test_rejects_changed_origin_in_real_string_list(self):
        actual = fixture("round13-altmount-effective-config.json")["actual"]
        expected = copy.deepcopy(actual)
        expected["api"]["allowed_origins"][1] = "https://invalid.example"
        with self.assertRaisesRegex(AssertionError, "allowed_origins"):
            match(actual, expected)

    def test_rejects_oversized_pool_after_omitted_false_flags(self):
        actual = fixture("round13-decypharr-effective-config.json")["actual"]
        actual["usenet"]["providers"][0]["max_connections"] = 11
        expected = {"use_auth": False, "disable_webdav": False,
                    "usenet": {"providers": [{"max_connections": 10}]}}
        with self.assertRaisesRegex(AssertionError, "max_connections"):
            match(actual, expected)


class DamageCorpusTests(unittest.TestCase):
    def test_control_is_intact_and_percentage_is_within_real_file(self):
        record = fixture("round13-damage-first-article.json")
        with tempfile.TemporaryDirectory(prefix="r13-corpus-") as directory:
            filename = corpus.BY_ID["damaged-partial"]["nzb"]
            subprocess.run(["7z", "x", "-pdmmbench", "-y", f"-o{directory}",
                            str(REPO / "corpus/corpus.7z"), filename],
                           check=True, stdout=subprocess.DEVNULL)
            nzb = Path(directory) / filename
            self.assertEqual(hashlib.sha256(nzb.read_bytes()).hexdigest(),
                             record["nzb_sha256"])
            target, _ = damage.pick_file(damage.parse_nzb(str(nzb)))
            self.assertEqual(len(target["segments"]), record["segment_count"])
            controls = []

            def request(url, auth, offset, length, want_hash=False, **kwargs):
                if not want_hash:
                    controls.append((offset, length))
                return {"http": 503, "bytes": 0, "error": "I/O isolated for range-selection test"}

            # This phase uses only the first payload's length. All relevant
            # dimensions and yEnc fields are captured from the real article.
            with patch.object(damage, "true_bytes", return_value=(
                    bytes(record["decoded_bytes"]), record["metadata"])), \
                    patch.object(damage, "verify_alignment", return_value={"aligned": True}), \
                    patch.object(damage, "inspect_gap", return_value={"content": "no bytes"}), \
                    patch.object(damage, "timed_stream", side_effect=request):
                result = damage.run("http://isolated/media", None, str(nzb),
                                    hole_index=record["holes"][0])
            start, length = controls[0]
            self.assertGreater(start, result["hole_end"])
            self.assertLessEqual(start + length, record["metadata"]["file_size"])
            self.assertGreaterEqual(result["hole_position_pct"], 0)
            self.assertLessEqual(result["hole_position_pct"], 100)


class SelectFieldTests(unittest.TestCase):
    def test_a_subset_keeps_the_field_order(self):
        self.assertEqual(select_field("aiostreams,raw"), ["raw", "aiostreams"])

    def test_no_subset_is_the_whole_field(self):
        self.assertEqual(len(select_field(None)), 7)

    def test_an_unknown_target_is_refused(self):
        with self.assertRaises(SystemExit):
            select_field("raw,aiostream")


class FreshSeekTests(unittest.TestCase):
    def test_a_seek_inside_the_entrys_own_sequential_read_is_not_fresh(self):
        row = {"seq_offset": 100, "seq_bytes": 50, "seeks": {"points": [
            {"offset": 10, "ttfb_s": 0.5}, {"offset": 120, "ttfb_s": 0.001},
            {"offset": 150, "ttfb_s": 0.4}, {"offset": 200, "ttfb_s": None}]}}
        self.assertEqual(fresh_seeks(row), [0.5, 0.4])


class CorpusCensusTests(unittest.TestCase):
    def test_the_deliberate_hole_is_as_built(self):
        self.assertTrue(verdict("ToyStory5Damaged.nzb", ["<hole@x>"], [])["ok"])

    def test_a_provider_gap_in_a_complete_post_fails_the_census(self):
        self.assertFalse(verdict("ToyStory5.nzb", ["<gone@x>"], [])["ok"])

    def test_a_body_refused_after_stat_said_present_fails_the_census(self):
        self.assertFalse(verdict("Bosch.S01.nzb", [], ["<lied@x>"])["ok"])


def render_decypharr(round_name):
    """since_r14_decypharr on round 13's real decypharr block, under ROUND."""
    import os, sys
    env = dict(os.environ, ROUND=round_name, NNTP_USER="u", NNTP_PASS="p",
               BENCH={"r13": "/home/ben/bench-round13-20261001", "r14": "/root/bench-round14"}[round_name])
    for inherited in ("NNTP_HOST", "NNTP_PORT"):  # each profile supplies its own
        env.pop(inherited, None)
    code = ("import json, config_r13 as c; print(json.dumps(c.since_r14_decypharr("
            "{'usenet': {'disk_buffer_path': '/b/decyrun/streams', 'max_connections': 10}})))")
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=Path(__file__).parent,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class DecypharrSinceRound13Tests(unittest.TestCase):
    def test_round14_keeps_the_disk_cache_under_its_new_name(self):
        usenet = render_decypharr("r14")["usenet"]
        self.assertEqual(usenet.get("disk_path"), "/b/decyrun/streams")
        self.assertNotIn("disk_buffer_path", usenet)

    def test_round14_never_joins_the_public_gossip_network(self):
        self.assertEqual(render_decypharr("r14").get("hearsay"), {"disabled": True})

    def test_round13_renders_exactly_what_it_ran(self):
        self.assertEqual(render_decypharr("r13"),
                         {"usenet": {"disk_buffer_path": "/b/decyrun/streams", "max_connections": 10}})



class RerunPinTests(unittest.TestCase):
    def profile_env(self, pin):
        import os, sys
        env = dict(os.environ, ROUND="r14")
        env.pop("ROUND_PIN", None)
        if pin:
            env["ROUND_PIN"] = pin
        out = subprocess.run([sys.executable, "round_profile.py", "env"], env=env, cwd=Path(__file__).parent,
                             capture_output=True, text=True, check=True).stdout
        return dict(line[len("export "):].split("=", 1) for line in out.splitlines())

    def test_a_rerun_pin_moves_zurg_and_leaves_the_round_pin_alone(self):
        import tempfile
        repo = Path(__file__).resolve().parent.parent
        pins = json.loads((repo / "config/round14-existing.json").read_text())
        pins["zurg"]["revision"] = "f" * 40
        with tempfile.NamedTemporaryFile("w", suffix=".json") as pin:
            json.dump(pins, pin); pin.flush()
            rerun, round14 = self.profile_env(pin.name), self.profile_env(None)
        self.assertEqual(rerun["REV_ZURG"], "f" * 40)
        self.assertEqual(rerun["ROUND_MANIFEST"], pin.name)
        self.assertEqual(round14["REV_ZURG"], "e4fac5cbdf3b9b8983f939029849c20960810d71")
        self.assertEqual({k: v for k, v in rerun.items() if "ZURG" not in k and k != "ROUND_MANIFEST"},
                         {k: v for k, v in round14.items() if "ZURG" not in k and k != "ROUND_MANIFEST"})


if __name__ == "__main__":
    unittest.main()
