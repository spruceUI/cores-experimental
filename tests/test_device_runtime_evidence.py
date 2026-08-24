"""Artifact-bound physical-device runtime evidence and projection tests."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "device_runtime_evidence.py"
V1_PATH = (
    ROOT
    / "manifests"
    / "device-runtime-captures"
    / "load-smoke-20260724-v1.json"
)
V2_PATH = (
    ROOT
    / "manifests"
    / "device-runtime-captures"
    / "load-smoke-20260724-v2.json"
)

_spec = importlib.util.spec_from_file_location("device_runtime_evidence", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
device_runtime_evidence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(device_runtime_evidence)


EXPECTED_DEVICES = [
    "ANBERNIC_RG28XX",
    "ANBERNIC_RG34XXSP",
    "ANBERNIC_RGCUBEXX",
    "ANBERNIC_RGXX640480",
    "GKD_PIXEL2",
    "MAGICX_ZERO28",
    "MIYOO_A30",
    "MIYOO_FLIP",
    "MIYOO_MINI",
    "MIYOO_MINI_FLIP",
    "MIYOO_MINI_PLUS",
    "MIYOO_MINI_V4",
    "TRIMUI_BRICK",
    "TRIMUI_BRICK_PRO",
    "TRIMUI_SMART_PRO",
    "TRIMUI_SMART_PRO_S",
]
HISTORICAL_COUNTS = {
    "FAIL": 4,
    "NO_BUILD": 64,
    "PASS": 654,
    "UNKNOWN": 846,
}
CURRENT_COUNTS = {
    "FAIL": 4,
    "NO_BUILD": 64,
    "PASS": 650,
    "UNKNOWN": 850,
}
V1_SHA256 = "a36c192848efcbd9f2d56280da2b601b080e845f062430860adbb5beedb6dee2"
HISTORICAL_YABA_ARM64_SHA256 = (
    "0c6d8ddf43d0830161466443971a960587e18437bf9a7fdc2de1c644bd70ea69"
)
CURRENT_YABA_ARM64_SHA256 = (
    "e6e413d07efbeb6dd3c0a08db430dbc180b9992b2af22618c8ffbbfdaf9290ec"
)
KM_PARALLEL_ARMHF_SHA256 = (
    "827e0ca99a60bdf833a2ac7ca0f863bf25787d8e1139b0906e034c6fc0d9213e"
)


def _device_index(document: dict) -> dict[str, dict]:
    return {device["device_id"]: device for device in document["devices"]}


def _result_index(document: dict) -> dict[tuple[str, str], dict]:
    return {
        (device["device_id"], result["core_id"]): result
        for device in document["devices"]
        for result in device["results"]
    }


class DeviceRuntimeMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checked_in = json.loads(V2_PATH.read_text(encoding="utf-8"))
        cls.derived = device_runtime_evidence.build_migration(ROOT)
        cls.devices = _device_index(cls.checked_in)
        cls.results = _result_index(cls.checked_in)

    def test_v1_bytes_are_immutable(self) -> None:
        self.assertEqual(V1_SHA256, hashlib.sha256(V1_PATH.read_bytes()).hexdigest())

    def test_checked_in_v2_is_exact_generator_output(self) -> None:
        self.assertEqual(self.derived, self.checked_in)
        self.assertEqual(
            device_runtime_evidence._render_json(self.derived),
            V2_PATH.read_text(encoding="utf-8"),
        )
        summary = device_runtime_evidence.validate_capture(
            self.checked_in, repo_root=ROOT
        )
        self.assertEqual(HISTORICAL_COUNTS, summary["status_counts"])

    def test_migration_binds_full_commit_and_exact_snapshots(self) -> None:
        self.assertEqual(
            "aaaee534cb75d8ca0e65c2afe2e4390f1c184478",
            self.checked_in["candidate"]["repository_commit"],
        )
        derivation = self.checked_in["derivation"]
        self.assertEqual(
            "627040e2c783eabc1c9e2d0eac9c72f5274667312cd1705e74c5f06cb0197b1f",
            derivation["device_runtime_contracts"]["file_sha256"],
        )
        self.assertEqual(
            "902d11a9fc9a07802bb0c0ef8ca4611be37310b45cd4a3e1bcfe81fc9477c049",
            derivation["execution_profiles"]["file_sha256"],
        )
        self.assertEqual(98, derivation["evidence_indexes"]["file_count"])

    def test_manifest_is_an_exact_98_by_16_physical_partition(self) -> None:
        self.assertEqual(
            EXPECTED_DEVICES,
            [row["device_id"] for row in self.checked_in["devices"]],
        )
        artifacts = self.checked_in["artifacts"]
        core_order = [subject["core_id"] for subject in artifacts]
        self.assertEqual(98, len(core_order))
        self.assertEqual(sorted(core_order), core_order)
        self.assertEqual(98, len(set(core_order)))
        for device in self.checked_in["devices"]:
            self.assertEqual(
                core_order,
                [result["core_id"] for result in device["results"]],
                device["device_id"],
            )
            self.assertEqual(
                {device["architecture"]},
                {result["architecture"] for result in device["results"]},
            )
        self.assertEqual(98 * 16, len(self.results))

    def test_every_result_references_its_exact_artifact_subject(self) -> None:
        subjects = {
            (subject["core_id"], architecture): target
            for subject in self.checked_in["artifacts"]
            for architecture, target in subject["targets"].items()
        }
        for (device_id, core_id), result in self.results.items():
            target = subjects[(core_id, self.devices[device_id]["architecture"])]
            expected = target["sha256"] if target is not None else None
            self.assertEqual(expected, result["artifact_sha256"])

    def test_uncaptured_mini_siblings_do_not_inherit_failures(self) -> None:
        for core_id in ("km_parallel_n64_xtreme_amped_turbo", "puae2021"):
            for device_id in ("MIYOO_MINI_PLUS", "MIYOO_MINI_FLIP"):
                result = self.results[(device_id, core_id)]
                self.assertEqual("FAIL", result["load_result"])
                self.assertEqual("memory-zero-fill-map", result["reason"])
            for device_id in ("MIYOO_MINI", "MIYOO_MINI_V4"):
                result = self.results[(device_id, core_id)]
                self.assertEqual("UNKNOWN", result["load_result"])
                self.assertEqual("device-not-captured", result["reason"])

    def test_recorded_frontend_name_is_not_silently_rewritten(self) -> None:
        mini_plus = self.devices["MIYOO_MINI_PLUS"]
        self.assertEqual("ra32-mini-v0", mini_plus["execution_profile_id"])
        self.assertEqual("present", mini_plus["frontend_availability"])
        self.assertEqual("RetroArch/ra32.mini", mini_plus["frontend_path"])
        self.assertEqual(
            "f7350c5755277b4aca957ce08055c71685bd59cf5967cfbb72899e932d8fae4d",
            mini_plus["frontend_sha256"],
        )
        self.assertEqual("retroarch", mini_plus["retroarch_binary"])
        self.assertEqual("CAPTURED", mini_plus["capture_status"])

    def test_policy_exclusions_are_orthogonal_to_load_results(self) -> None:
        ffmpeg = self.results[("MIYOO_A30", "ffmpeg")]
        self.assertEqual("PASS", ffmpeg["load_result"])
        self.assertEqual(
            {"status": "EXCLUDED", "reason": "default-excluded"},
            ffmpeg["policy"],
        )
        swanstation = self.results[("MIYOO_A30", "swanstation")]
        self.assertEqual("NO_BUILD", swanstation["load_result"])
        self.assertEqual(
            {"status": "EXCLUDED", "reason": "armhf-not-consumed"},
            swanstation["policy"],
        )

    def test_schema_and_semantic_tampering_fail_closed(self) -> None:
        malformed = copy.deepcopy(self.checked_in)
        malformed["devices"][0]["results"][0]["reason"] = "invented-pass-reason"
        malformed["content_sha256"] = device_runtime_evidence._document_content_sha256(
            malformed
        )
        with self.assertRaises(device_runtime_evidence.DeviceRuntimeEvidenceError):
            device_runtime_evidence.validate_capture(malformed, repo_root=ROOT)

        missing = copy.deepcopy(self.checked_in)
        missing["devices"][0]["results"].pop()
        missing["content_sha256"] = device_runtime_evidence._document_content_sha256(
            missing
        )
        with self.assertRaises(device_runtime_evidence.DeviceRuntimeEvidenceError):
            device_runtime_evidence.validate_capture(missing, repo_root=ROOT)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaises(device_runtime_evidence.DeviceRuntimeEvidenceError):
            device_runtime_evidence._decode_json_object(
                b'{"schema_version":2,"schema_version":2}', "duplicate fixture"
            )


class CurrentPhysicalDeviceProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection = (
            device_runtime_evidence.project_current_physical_devices(
                repo_root=ROOT, capture_path=V2_PATH
            )
        )
        cls.devices = _device_index(cls.projection)
        cls.results = _result_index(cls.projection)

    def test_public_projection_api_is_an_exact_current_matrix(self) -> None:
        self.assertEqual(EXPECTED_DEVICES, self.projection["device_order"])
        self.assertEqual(98, len(self.projection["core_order"]))
        self.assertEqual(
            sorted(self.projection["core_order"]), self.projection["core_order"]
        )
        self.assertEqual(CURRENT_COUNTS, self.projection["status_counts"])
        self.assertEqual(98 * 16, sum(self.projection["status_counts"].values()))
        self.assertEqual(98 * 16, len(self.results))
        self.assertEqual(
            self.projection,
            device_runtime_evidence.project_current(
                repo_root=ROOT, capture_path=V2_PATH
            ),
        )

    def test_current_yabasanshiro_bytes_require_new_device_execution(self) -> None:
        historical = {
            subject["core_id"]: subject
            for subject in json.loads(V2_PATH.read_text(encoding="utf-8"))["artifacts"]
        }
        self.assertEqual(
            HISTORICAL_YABA_ARM64_SHA256,
            historical["yabasanshiro"]["targets"]["arm64"]["sha256"],
        )
        changed_devices = {
            "MIYOO_FLIP",
            "TRIMUI_BRICK",
            "TRIMUI_SMART_PRO",
            "TRIMUI_SMART_PRO_S",
        }
        actual_changed: set[str] = set()
        for device_id in EXPECTED_DEVICES:
            device = self.devices[device_id]
            result = self.results[(device_id, "yabasanshiro")]
            if device["architecture"] == "armhf":
                self.assertEqual("NO_BUILD", result["load_result"])
                continue
            self.assertEqual(CURRENT_YABA_ARM64_SHA256, result["artifact"]["sha256"])
            self.assertEqual("UNKNOWN", result["load_result"])
            if result["reason"] == "artifact-not-observed":
                actual_changed.add(device_id)
            else:
                self.assertEqual("device-not-captured", result["reason"])
        self.assertEqual(changed_devices, actual_changed)

    def test_canonical_mini_failure_artifact_is_still_exact(self) -> None:
        for device_id in (
            "MIYOO_MINI",
            "MIYOO_MINI_FLIP",
            "MIYOO_MINI_PLUS",
            "MIYOO_MINI_V4",
        ):
            result = self.results[
                (device_id, "km_parallel_n64_xtreme_amped_turbo")
            ]
            self.assertEqual(KM_PARALLEL_ARMHF_SHA256, result["artifact"]["sha256"])
        self.assertEqual(
            "FAIL",
            self.results[
                ("MIYOO_MINI_PLUS", "km_parallel_n64_xtreme_amped_turbo")
            ]["load_result"],
        )
        self.assertEqual(
            "UNKNOWN",
            self.results[
                ("MIYOO_MINI", "km_parallel_n64_xtreme_amped_turbo")
            ]["load_result"],
        )

    def test_family_disagreement_is_unknown_not_broadcast(self) -> None:
        families = {
            family["runtime_family_id"]: family
            for family in self.projection["families"]
        }
        mini = {
            result["core_id"]: result
            for result in families["miyoo-mini-v0"]["results"]
        }
        for core_id in ("km_parallel_n64_xtreme_amped_turbo", "puae2021"):
            result = mini[core_id]
            self.assertEqual("UNKNOWN", result["load_result"])
            self.assertEqual("mixed-physical-device-results", result["reason"])
            self.assertEqual(
                {"FAIL", "UNKNOWN"},
                {member["load_result"] for member in result["member_results"]},
            )

    def test_family_duplicates_and_missing_rows_fail_closed(self) -> None:
        devices = copy.deepcopy(self.projection["devices"])
        devices.append(copy.deepcopy(devices[0]))
        with self.assertRaises(device_runtime_evidence.DeviceRuntimeEvidenceError):
            device_runtime_evidence.aggregate_families(devices)

        devices = copy.deepcopy(self.projection["devices"])
        mini = next(row for row in devices if row["device_id"] == "MIYOO_MINI")
        mini["results"].pop()
        with self.assertRaises(device_runtime_evidence.DeviceRuntimeEvidenceError):
            device_runtime_evidence.aggregate_families(devices)


if __name__ == "__main__":
    unittest.main()
