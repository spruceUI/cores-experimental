"""The load-smoke runtime capture binds contracts, candidate, and verdicts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = (
    ROOT / "manifests" / "device-runtime-captures" / "load-smoke-20260724-v1.json"
)
CONTRACTS_PATH = ROOT / "manifests" / "device-runtime-contracts.json"


class LoadSmokeCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
        cls.contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))[
            "contracts"
        ]
        cls.catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8")
        )["cores"]

    def test_capture_binds_the_sealed_candidate(self) -> None:
        self.assertEqual("load-smoke-v1", self.capture["kind"])
        self.assertEqual(
            "wave4b-complete-30124953754-1",
            self.capture["candidate"]["candidate_id"],
        )
        self.assertEqual(True, self.capture["local_only"])
        self.assertEqual("disabled", self.capture["publication"])

    def test_every_captured_contract_is_referenced_back(self) -> None:
        for contract_id, block in self.capture["contracts"].items():
            contract = self.contracts[contract_id]
            self.assertEqual("load-smoke-v1", contract["runtime_capture"])
            smoke = contract["load_smoke"]
            self.assertEqual(self.capture["capture_id"], smoke["capture_id"])
            self.assertEqual(
                [device["device_id"] for device in block["devices"]],
                smoke["devices_tested"],
            )
            excluded = {
                core
                for device in block["devices"]
                for core in device["failed"]
            }
            self.assertEqual(excluded, set(smoke["excluded_cores"]))
            self.assertEqual(
                "pass-with-exclusions" if excluded else "pass",
                smoke["result"],
            )

    def test_verdicts_cover_every_arch_matching_core_exactly_once(self) -> None:
        for block in self.capture["contracts"].values():
            for device in block["devices"]:
                verdict_cores = set(device["passed"]) | set(device["failed"])
                self.assertEqual(
                    device["artifacts_byte_verified"], len(verdict_cores)
                )
                self.assertEqual(
                    device["passed_count"], len(device["passed"])
                )
                for core in verdict_cores:
                    self.assertIn(core, self.catalog)

    def test_mini_family_exclusions_are_the_memory_pair(self) -> None:
        smoke = self.contracts["device-miyoo-mini-family-v0"]["load_smoke"]
        self.assertEqual(
            {"km_parallel_n64_xtreme_amped_turbo", "puae2021"},
            set(smoke["excluded_cores"]),
        )
        for devices in smoke["excluded_cores"].values():
            self.assertEqual(
                {"memory-zero-fill-map"}, set(devices.values())
            )


if __name__ == "__main__":
    unittest.main()
