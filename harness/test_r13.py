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
from run_r13 import check_counts

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
            check_counts({"nzbdav-og": 10, "unowned-newswest-consumer": 1})


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


if __name__ == "__main__":
    unittest.main()
