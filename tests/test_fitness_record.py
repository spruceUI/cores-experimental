"""Tests for the consolidated device-fitness record composer (fitness_record.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fitness_record.py"

_spec = importlib.util.spec_from_file_location("fitness_record", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
fitness_record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fitness_record)


class MaxSymbolTests(unittest.TestCase):
    def test_picks_highest_version(self):
        symbols = ["GLIBCXX_3.4", "GLIBCXX_3.4.32", "GLIBCXX_3.4.21"]
        self.assertEqual(fitness_record.max_symbol(symbols, "GLIBCXX_"), "3.4.32")

    def test_absent_prefix_is_none(self):
        self.assertIsNone(fitness_record.max_symbol(["GLIBC_2.4"], "GLIBCXX_"))


class LockedToolchainTests(unittest.TestCase):
    def setUp(self):
        profiles = fitness_record._load_json(fitness_record.EXECUTION_PROFILES_PATH)
        self.images = fitness_record.locked_toolchain_images(profiles)

    def test_one_locked_image_per_architecture(self):
        self.assertEqual(set(self.images), {"arm64", "armhf"})

    def test_arch_maps_to_expected_locked_profile(self):
        self.assertEqual(self.images["arm64"]["profile"], "ra64-universal-v1")
        self.assertEqual(self.images["armhf"]["profile"], "ra32-a30-v1")

    def test_image_ids_are_sha256_refs(self):
        for arch in ("arm64", "armhf"):
            self.assertTrue(self.images[arch]["image_id"].startswith("sha256:"))

    def test_duplicate_locked_identity_is_rejected(self):
        profiles = {
            "profiles": {
                "a": {"build_identity": {"toolchain_architecture": "arm64", "image_id": "sha256:1"}},
                "b": {"build_identity": {"toolchain_architecture": "arm64", "image_id": "sha256:2"}},
            }
        }
        with self.assertRaises(fitness_record.FitnessRecordError):
            fitness_record.locked_toolchain_images(profiles)


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.gearboy = fitness_record.compose_fitness("gearboy")

    def test_references_authoritative_pin_without_duplicating_provenance(self):
        self.assertEqual(
            self.gearboy["pin"],
            "pins/core-sets/gearboy-36d723ff4410-f6f1b63e8798.json",
        )
        # The record stays compact: it points to the pin rather than embedding a
        # pipeline bundle or transcript proof.
        self.assertNotIn("pipeline_bundle", self.gearboy)

    def test_source_commit_and_scope(self):
        self.assertEqual(
            self.gearboy["source_commit"],
            "36d723ff44109e6d9eefba34e1c9a089c2d50e18",
        )
        self.assertEqual(self.gearboy["validation_scope"], "static-build-only")
        self.assertEqual(self.gearboy["publication"], "disabled")

    def test_per_abi_toolchain_and_abi_floor(self):
        arm64 = self.gearboy["targets"]["arm64"]
        armhf = self.gearboy["targets"]["armhf"]
        self.assertEqual(arm64["execution_profile"], "ra64-universal-v1")
        self.assertEqual(armhf["execution_profile"], "ra32-a30-v1")
        self.assertEqual(arm64["max_glibcxx"], "3.4.21")
        self.assertEqual(armhf["max_glibcxx"], "3.4.32")
        self.assertTrue(arm64["toolchain_image_id"].startswith("sha256:"))

    def test_runtime_smoke_is_pending(self):
        for target in self.gearboy["targets"].values():
            self.assertEqual(target["runtime_smoke"], "pending")

    def test_c_only_core_has_no_cxx_floor(self):
        record = fitness_record.compose_fitness("2048")
        armhf = record["targets"]["armhf"]
        self.assertIsNone(armhf["max_glibcxx"])
        self.assertNotIn("libstdc++.so.6", armhf["runtime_deps"])

    def test_mismatched_core_id_is_rejected(self):
        with self.assertRaises(fitness_record.FitnessRecordError):
            fitness_record.compose_fitness("no-such-core")


class ReportTests(unittest.TestCase):
    def test_all_canonical_cores_compose(self):
        report = fitness_record.build_report()
        self.assertEqual(report["core_count"], len(fitness_record.canonical_core_ids()))
        for core_id, record in report["records"].items():
            self.assertEqual(record["core_id"], core_id)
            self.assertTrue(record["targets"])

    def test_report_is_deterministic(self):
        self.assertEqual(fitness_record.build_report(), fitness_record.build_report())


if __name__ == "__main__":
    unittest.main()
