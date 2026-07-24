"""Tests for the tiered contract policy and light promotion gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "contract_tier", ROOT / "scripts" / "contract_tier.py"
)
assert _spec is not None and _spec.loader is not None
contract_tier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract_tier)


class TierPolicyTests(unittest.TestCase):
    def test_registered_contract_is_heavy(self):
        heavy = contract_tier.heavy_cores()
        self.assertIn("uzem", heavy)
        self.assertIn("gambatte", heavy)
        self.assertEqual(contract_tier.core_tier("uzem"), "heavy")

    def test_core_without_registered_contract_is_light(self):
        # A core with no registered log contract defaults to the light tier.
        self.assertEqual(contract_tier.core_tier("nonexistent-core"), "light")


class LightGateTests(unittest.TestCase):
    def test_uzem_static_evidence_pends_on_runtime(self):
        verdict = contract_tier.light_gate_status("uzem", "pending")
        self.assertEqual(verdict["verdict"], "pending-runtime")
        self.assertEqual(verdict["static_evidence"], "valid")

    def test_runtime_pass_makes_light_gate_pass(self):
        self.assertEqual(
            contract_tier.light_gate_status("uzem", "pass")["verdict"], "pass"
        )

    def test_runtime_fail_fails_the_gate(self):
        self.assertEqual(
            contract_tier.light_gate_status("uzem", "fail")["verdict"], "fail"
        )

    def test_missing_manifest_reports_no_manifest(self):
        self.assertEqual(
            contract_tier.light_gate_status("no-such-core")["verdict"], "no-manifest"
        )

    def test_unknown_smoke_status_rejected(self):
        with self.assertRaises(ValueError):
            contract_tier.light_gate_status("uzem", "maybe")


class ArmhfCeilingTests(unittest.TestCase):
    def test_uzem_is_over_the_mini_ceiling(self):
        manifest = {"targets": {"armhf": {"version_requirements": ["GLIBCXX_3.4.29"]}}}
        self.assertTrue(contract_tier._armhf_over_mini(manifest))

    def test_within_ceiling_is_not_flagged(self):
        manifest = {"targets": {"armhf": {"version_requirements": ["GLIBCXX_3.4.21"]}}}
        self.assertFalse(contract_tier._armhf_over_mini(manifest))


class TierReportTests(unittest.TestCase):
    def setUp(self):
        self.report = contract_tier.tier_report()

    def test_report_shape_and_universal_runtime_gate(self):
        self.assertEqual(
            self.report["runtime_gate"],
            "required-for-full-promotion-both-tiers",
        )
        self.assertEqual(
            self.report["counts"]["cores"], len(self.report["cores"])
        )
        self.assertEqual(
            self.report["counts"]["heavy"] + self.report["counts"]["light"],
            self.report["counts"]["cores"],
        )

    def test_uzem_row_is_heavy_pending_and_mini_ineligible(self):
        row = next(r for r in self.report["cores"] if r["core"] == "uzem")
        self.assertEqual(row["tier"], "heavy")
        self.assertEqual(row["light_gate"], "pending-runtime")
        self.assertTrue(row["armhf_mini_ineligible"])

    def test_smoke_index_promotes_runtime_verified(self):
        report = contract_tier.tier_report({"uzem": "pass"})
        self.assertGreaterEqual(report["counts"]["runtime_verified"], 1)
        row = next(r for r in report["cores"] if r["core"] == "uzem")
        self.assertEqual(row["light_gate"], "pass")


if __name__ == "__main__":
    unittest.main()
