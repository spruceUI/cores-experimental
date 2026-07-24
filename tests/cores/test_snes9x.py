"""Pinned Snes9x build-evidence tests."""

from __future__ import annotations

from collections import Counter
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import snes9x

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "snes9x"
OTHER_CORE_ID = "prosystem"
PIN_NAME = "snes9x-185488cd83aa-1007f6c98b6b.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "185488cd83aaf274752a742c94d45561cbecb7af"
SOURCE_TREE = "da7c15404a93174aa0972d8ec053471e6cef064d"
SOURCE_LOCK_ID = "snes9x-185488cd83aa"
SELECTION_SHA256 = (
    "1007f6c98b6b1a4c4dd688c36c5169ac86bf56e46b3ba76918a237d75811f4c1"
)
SELECTED_RUN = "actions-sim-build-core-snes9x-v1"
REPRODUCTION_RUN = "build-core-snes9x-local-v1"
PACKAGE_SHA256 = (
    "3d734cbaeb15e0ef12bc682970cf6cf26cc2be4ab4cbfaa2c4b92d8b799a81ef"
)
METADATA_SHA256 = (
    "fa62b78d58bc4c30f4e0a4a581f0cb3252447b7f198b55bd6ebe2e4b9bde5cc2"
)
RUNNERS = {
    SELECTED_RUN: {
        "backend": "local-docker",
        "local_only": True,
        "mode": "simulated",
        "profile": "github-actions",
        "publication": "disabled",
    },
    REPRODUCTION_RUN: {
        "backend": "local-docker",
        "local_only": True,
        "mode": "native",
        "profile": "local",
        "publication": "disabled",
    },
}
TARGETS = {
    "arm64": {
        "artifact_sha256": (
            "02ccdd5033b1f1468590a9589fbc1a9c45e0b91c4852c93e1310b5239446cea9"
        ),
        "log_sha256": {
            SELECTED_RUN: (
                "a71f14117ed3cb767323c459547f44337cf8d78ab8f5819c43a65eb8fbf68e7f"
            ),
            REPRODUCTION_RUN: (
                "4b479c7d71b7fa85f58efeca993f2f2830985eb09b3dad544a81711cd57cb4cc"
            ),
        },
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libm.so.6",
            "libstdc++.so.6",
            "libz.so.1",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.9",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.11",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.9",
            "GLIBC_2.17",
            "GLIBC_2.29",
        ],
    },
    "armhf": {
        "artifact_sha256": (
            "522ebc0889787fa2162e6070f64a0c5888afda6d44f62b321daca26558cd84ef"
        ),
        "log_sha256": {
            SELECTED_RUN: (
                "34ad1737dddfebb8db2dce9f8b346700ce361cdee9bb0c058e345b1d266b2de0"
            ),
            REPRODUCTION_RUN: (
                "34ad1737dddfebb8db2dce9f8b346700ce361cdee9bb0c058e345b1d266b2de0"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": [
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libstdc++.so.6",
            "libz.so.1",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.9",
            "CXXABI_ARM_1.3.3",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.11",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.29",
            "GLIBCXX_3.4.32",
            "GLIBCXX_3.4.9",
            "GLIBC_2.4",
        ],
    },
}
CAVEAT_TOKENS = (
    "54 C++ compiles",
    "three C compiles",
    "1.63-185488c",
    "display version 1.61",
    "Non-commercial",
    "BS-X.bin",
    "STBIOS.bin",
    "GLIBCXX_3.4.32",
    "ra32-a30-v1",
    "all device views remain ineligible",
)
FAILURE_MARKERS = ("error:", "fatal:", "undefined reference", "dubious ownership")


class Snes9xCoreEvidenceTests(unittest.TestCase):
    def test_individual_pin_and_compatibility_bind_promoted_evidence(self) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        pin_report = pipeline.validate_pin_set_document(pin, document_path=pin_path)
        self.assertEqual("valid", pin_report["status"], pin_report["errors"])
        compatibility_report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual(
            "valid",
            compatibility_report["status"],
            compatibility_report["errors"],
        )
        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["e2e"]["package_sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            selection["e2e"]["content_sha256"],
            compatibility["selected_e2e_content_sha256"],
        )
        reproduction = load_document(
            ROOT / ".local-e2e" / "runs" / REPRODUCTION_RUN / "e2e-record.json"
        )
        self.assertEqual(
            reproduction["content_sha256"],
            compatibility["reproduction_e2e_content_sha256"],
        )
        self.assertEqual(
            f".local-e2e/runs/{SELECTED_RUN}/e2e-record.json",
            compatibility["e2e_run"],
        )
        self.assertEqual(
            f".local-e2e/runs/{REPRODUCTION_RUN}/e2e-record.json",
            compatibility["reproduction_run"],
        )
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)
        for active_reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            compatibility["golden_source"],
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
        ):
            self.assertNotIn("tranche", active_reference.lower())

        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden_record = selected_target["golden_record"]
                artifact = golden_record["artifact"]

                self.assertEqual(CORE_ID, golden_record["core_id"])
                self.assertEqual(SOURCE_COMMIT, golden_record["source"]["commit"])
                self.assertEqual(SOURCE_TREE, golden_record["source"]["tree"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], selected_target["artifact"]["sha256"]
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["version_requirements"],
                    artifact["version_requirements"],
                )

                snapshot_reference = golden_record["local_store"][
                    "recipe_snapshots"
                ][architecture]
                snapshot_path = ROOT / snapshot_reference["path"]
                snapshot = load_document(snapshot_path)
                self.assertEqual(9, snapshot["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        golden_record,
                        f"{CORE_ID}/{architecture}",
                    ),
                )

    def test_individual_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertNotIn("tranche", source_set["evidence_pin"]["path"].lower())
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock = load_document(ROOT / source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(8, len(source_lock["source"]["submodules"]))
        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
        self.assertEqual(
            {
                "catalog_cores": catalog_core_count,
                "catalog_unlocked_cores": catalog_core_count - 1,
                "evidence_cells": 2,
                "locked_cores": 1,
            },
            report["mirror"],
        )

        cells = {
            cell["architecture"]: cell for cell in report["build_evidence_cells"]
        }
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                cell = cells[architecture]
                self.assertEqual(CORE_ID, cell["core_id"])
                self.assertEqual(SOURCE_LOCK_ID, cell["source_lock_id"])
                self.assertEqual(expected["artifact_sha256"], cell["artifact_sha256"])
                self.assertEqual(
                    "ra64-universal-v1"
                    if architecture == "arm64"
                    else "ra32-a30-v1",
                    cell["execution_profile_id"],
                )
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_individual_channels_and_release_bind_semantic_artifacts(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
                )
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(channel, pointer["channel"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", pointer["target"]["path"].lower())

                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])
                self.assertIn(
                    "channel pointer document does not match its core alias filename",
                    wrong_core["errors"],
                )

        pin_path = ROOT / PIN_PATH
        pin = load_document(pin_path)
        release_root = ROOT / ".local-e2e" / "releases" / SEMANTIC_ID
        release_report = pipeline.validate_local_release(
            release_root,
            pin,
            file_sha256(pin_path),
            expected_release_id=SEMANTIC_ID,
        )
        self.assertEqual("valid", release_report["status"], release_report["errors"])
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

    def test_selected_and_reproduction_runs_prove_exact_mixed_builds(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[str]] = {
            architecture: [] for architecture in TARGETS
        }
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                self.assertNotIn("tranche", run_id.lower())
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence = load_document(run_root / "e2e-record.json")
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    [CORE_ID],
                    [item["core_id"] for item in evidence["packages"]],
                )
                package = evidence["packages"][0]
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/snes9x_libretro.so",
                            "cores/snes9x_libretro.so",
                            "snes9x_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )
                    self.assertNotIn("BS-X.bin", archive.namelist())
                    self.assertNotIn("STBIOS.bin", archive.namelist())

                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        record_path = (
                            run_root / CORE_ID / architecture / "build-record.json"
                        )
                        record = load_document(record_path)
                        log_path = record_path.parent / record["build"]["log"]
                        log_text = log_path.read_text(encoding="utf-8")
                        self.assertEqual(
                            expected["log_sha256"][run_id], file_sha256(log_path)
                        )
                        logs[architecture].append(log_text)
                        self.assertEqual(SOURCE_COMMIT, record["source"]["commit"])
                        self.assertEqual(SOURCE_TREE, record["source"]["tree"])
                        self.assertEqual(
                            {
                                "compiler_scope": "cxx",
                                "derivation": "hyphen-short7-v1",
                                "value": "-185488c",
                            },
                            record["build"]["git_version"],
                        )
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                log_text,
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
                            )
                        )
                        warning_lines = [
                            line
                            for line in log_text.splitlines()
                            if "warning:" in line.casefold()
                        ]
                        self.assertEqual(
                            Counter(snes9x.SNES9X_EXPECTED_WARNING_LINES[architecture]),
                            Counter(warning_lines),
                        )
                        lowered_log = log_text.casefold()
                        for marker in FAILURE_MARKERS:
                            self.assertNotIn(marker, lowered_log)

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "1.61"', metadata)
                        self.assertIn(b'license = "Non-commercial"', metadata)
                        self.assertIn(b'firmware0_path = "BS-X.bin"', metadata)
                        self.assertIn(b'firmware1_path = "STBIOS.bin"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"],
                            file_sha256(artifact_path),
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"1.63-185488c", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])
                # The pinned per-run log hashes state whether the independent
                # runs reproduced the log byte for byte or merely reordered
                # complete lines under parallel make; hold the bytes to it.
                pinned = TARGETS[architecture]["log_sha256"]
                if pinned[SELECTED_RUN] == pinned[REPRODUCTION_RUN]:
                    self.assertEqual(logs[architecture][0], logs[architecture][1])
                else:
                    self.assertNotEqual(logs[architecture][0], logs[architecture][1])
                self.assertEqual(
                    Counter(logs[architecture][0].splitlines(keepends=True)),
                    Counter(logs[architecture][1].splitlines(keepends=True)),
                )


if __name__ == "__main__":
    unittest.main()
