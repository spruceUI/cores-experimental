"""Pinned Mednafen Supafaust build-evidence tests."""

from __future__ import annotations

import copy
from collections import Counter
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import mednafen_supafaust
from core_pipeline_lib.records import compatibility as compatibility_records

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "mednafen_supafaust"
OTHER_CORE_ID = "snes9x"
PIN_NAME = "mednafen_supafaust-2b93c0d7dff5-debb21b70273.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "2b93c0d7dff5b8f6c4e60e049d66849923fa8bba"
SOURCE_TREE = "68dcc9b53118d9933f716c7219989822a89d10d7"
SOURCE_LOCK_ID = "mednafen_supafaust-2b93c0d7dff5"
SELECTION_SHA256 = (
    "debb21b7027360d66a1e22636c7adf53d3111657290031afc616c168842b7968"
)
SELECTED_RUN = "actions-sim-build-core-mednafen_supafaust-w3"
REPRODUCTION_RUN = "build-core-mednafen_supafaust-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "089fd6ee1dc60982a73110e045d77791521c42357ac1d13d4076ade487829cf9"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "3f3641eaf18a15b057a141a235557ff1f44b6494ef4572626c67e20da81633ec"
)
PACKAGE_SHA256 = (
    "a499b7a721fc2e0e42b71898175b424dd2bdba4a6b304b226cc2872a1a8923c0"
)
METADATA_SHA256 = (
    "97e61e6720ec59c780ed6563d1f2f93a5ae3ef2b4c7e5960800a99bac4d46033"
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
            "1df2ea7bab84e601edd41ddadd42b18866439b79f54c896e2c1bd9c290994d1e"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "faf58f3ded9f050b0930f4a4ec19e6ed8e8f52cb042e0ec7c9912f86633f5ba1"
            ),
            REPRODUCTION_RUN: (
                "2bf3cea5d2cdc5fe3bca032462999cb2356bf605ddae19ad694e019c6431d434"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "fba48a736d82373569b8d46483e12b729c8634eb3432b6a45994f647d2220ada"
            ),
            REPRODUCTION_RUN: (
                "7df414c004cfc64ba472fd61e009f5acb73e2431abcdd47dc17c09fae6510042"
            ),
        },
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libpthread.so.0",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.3",
            "CXXABI_1.3.8",
            "GCC_3.0",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.14",
            "GLIBCXX_3.4.15",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBC_2.17",
            "GLIBC_2.29",
        ],
    },
    "armhf": {
        "artifact_sha256": (
            "ea5e15a297f6d52dc801da181fa3008dd7be911b6e6a728b01c3cc433aa9d36b"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "bba577694ceddac9deef8b75bc0138e7bf9d615195d4e8930b6a5e41c6000a63"
            ),
            REPRODUCTION_RUN: (
                "d2ffcb7bbdd3c416772f433cc235252f873173113c075a23ccf4f94702115258"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "7fa24fed00a9bcdb117a99602382d23581409246a30fa16886da45d3c8199859"
            ),
            REPRODUCTION_RUN: (
                "800069305337d7e4a098ee4ec3e5655c09168d04cdb0bafc0248acc27f42c6f5"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": [
            "ld-linux-armhf.so.3",
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libpthread.so.0",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.13",
            "CXXABI_1.3.3",
            "CXXABI_1.3.8",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.14",
            "GLIBCXX_3.4.15",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.29",
            "GLIBC_2.17",
            "GLIBC_2.4",
        ],
    },
}
CAVEAT_TOKENS = (
    "44 C++ compiles",
    "1.29.0-2b93c0d",
    "eight warnings and no notes",
    "nine warnings plus eight",
    "GPLv2+",
    "smc|fig|sfc|gd3|gd7|dx2|bsx|swc",
    "CXXABI_1.3.13",
    "GLIBCXX_3.4.29",
    "ra32-a30-v1",
    "all device views remain ineligible",
)
FAILURE_MARKERS = (
    "error:",
    "fatal:",
    "undefined reference",
    "dubious ownership",
    "make: ***",
)


class MednafenSupafaustCoreEvidenceTests(unittest.TestCase):
    def test_singleton_pin_and_compatibility_bind_promoted_evidence(self) -> None:
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
        self.assertIsNone(pin["parent"])
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
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )
        reproduction = load_document(
            ROOT / ".local-e2e" / "runs" / REPRODUCTION_RUN / "e2e-record.json"
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256, reproduction["content_sha256"]
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
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
            self.assertNotIn("tranche", active_reference.casefold())

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
                self.assertEqual([], golden_record["source"]["submodules"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], selected_target["artifact"]["sha256"]
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                elf_class = expected["elf"].split("/", 1)[0]
                self.assertEqual(elf_class, artifact["elf"]["class"])
                self.assertEqual(
                    "AArch64" if architecture == "arm64" else "ARM",
                    artifact["elf"]["machine"],
                )
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

    def test_singleton_source_set_maps_profiles_without_device_claims(self) -> None:
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
        self.assertNotIn("tranche", source_set["evidence_pin"]["path"].casefold())
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock = load_document(ROOT / source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source_lock["source"]["commit"])
        self.assertEqual(SOURCE_TREE, source_lock["source"]["tree"])
        self.assertEqual([], source_lock["source"]["submodules"])
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

    def test_channel_lifecycle_is_semantic_and_core_isolated_when_present(
        self,
    ) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        pointer_paths = {
            channel: ROOT
            / ".local-e2e"
            / "channels"
            / f"{channel}.{CORE_ID}.json"
            for channel in target_paths
        }
        if not any(path.is_file() for path in pointer_paths.values()):
            self.skipTest("workspace-local individual channel aliases are unavailable")
        self.assertTrue(
            all(path.is_file() for path in pointer_paths.values()), pointer_paths
        )

        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(pointer_paths[channel])
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(channel, pointer["channel"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", pointer["target"]["path"].casefold())

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

    def test_selected_and_reproduction_runs_prove_exact_parallel_builds(
        self,
    ) -> None:
        contract = mednafen_supafaust.MEDNAFEN_SUPAFAUST_LOG_CONTRACT
        self.assertEqual(44, contract.expected_compile_count)
        self.assertEqual({"cxx": 44}, dict(contract.expected_language_counts))
        self.assertEqual(
            "7dd41788976cdf6d1565bd301f04be1d597e191156f9cf48a4707a55ce204451",
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "0d29c247ec1558f6267ee2c2028a4865b7311d15ea46bf1527f7170b8dba8fa7"
                ),
                "armhf": (
                    "2c37be190952b0e69b240d8cbde7a15a412fb8f594e2f2d79de905c4021fa476"
                ),
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            "b857c8382f4199eb69efdbe0006bdd103e89e7a991562040893a820aa595b4a9",
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            contract.expected_link_object_sha256,
            contract.expected_raw_link_object_sha256,
        )

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
                self.assertNotIn("tranche", run_id.casefold())
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence = load_document(run_root / "e2e-record.json")
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    SELECTED_E2E_CONTENT_SHA256
                    if run_id == SELECTED_RUN
                    else REPRODUCTION_E2E_CONTENT_SHA256,
                    evidence["content_sha256"],
                )
                self.assertEqual(
                    [CORE_ID], [item["core_id"] for item in evidence["packages"]]
                )
                package = evidence["packages"][0]
                self.assertEqual("packaged", package["result"])
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/mednafen_supafaust_libretro.so",
                            "cores/mednafen_supafaust_libretro.so",
                            "mednafen_supafaust_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )

                builds = {
                    build["architecture"]: build for build in evidence["builds"]
                }
                self.assertEqual(set(TARGETS), set(builds))
                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        build = builds[architecture]
                        self.assertEqual(CORE_ID, build["core_id"])
                        self.assertEqual("passed", build["result"])
                        self.assertEqual(
                            expected["record_sha256"][run_id], build["record_sha256"]
                        )
                        record_path = ROOT / build["record"]
                        self.assertEqual(
                            build["record_sha256"], file_sha256(record_path)
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
                        self.assertEqual([], record["source"]["submodules"])
                        self.assertEqual("libretro-super", record["build"]["driver"])
                        self.assertEqual("sanitized-v1", record["build"]["environment"])
                        self.assertEqual(
                            {
                                "compiler_scope": "cxx",
                                "derivation": "hyphen-short7-v1",
                                "value": "-2b93c0d",
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
                        note_lines = [
                            line
                            for line in log_text.splitlines()
                            if "note:" in line.casefold()
                        ]
                        self.assertEqual(
                            Counter(
                                mednafen_supafaust.
                                MEDNAFEN_SUPAFAUST_EXPECTED_WARNING_LINES[
                                    architecture
                                ]
                            ),
                            Counter(warning_lines),
                        )
                        self.assertEqual(
                            Counter(
                                mednafen_supafaust.
                                MEDNAFEN_SUPAFAUST_EXPECTED_NOTE_LINES[architecture]
                            ),
                            Counter(note_lines),
                        )
                        lowered_log = log_text.casefold()
                        for marker in FAILURE_MARKERS:
                            self.assertNotIn(marker, lowered_log)

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "1.29.0"', metadata)
                        self.assertIn(b'license = "GPLv2+"', metadata)
                        self.assertIn(
                            b'supported_extensions = "smc|fig|sfc|gd3|gd7|dx2|bsx|swc"',
                            metadata,
                        )
                        self.assertIn(b'savestate_features = "deterministic"', metadata)
                        self.assertIn(b'hw_render = "false"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"1.29.0-2b93c0d", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])
                self.assertNotEqual(logs[architecture][0], logs[architecture][1])
                self.assertEqual(
                    Counter(logs[architecture][0].splitlines(keepends=True)),
                    Counter(logs[architecture][1].splitlines(keepends=True)),
                )

    def test_compatibility_and_pin_mutations_fail_closed(self) -> None:
        _, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        wrong_digest = copy.deepcopy(compatibility)
        wrong_digest["content_sha256"] = "0" * 64
        digest_report = pipeline.validate_core_compatibility_document(
            wrong_digest,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", digest_report["status"])
        self.assertIn(
            "core compatibility content digest is invalid", digest_report["errors"]
        )

        malformed_documents = {
            "artifact": copy.deepcopy(compatibility),
            "elf": copy.deepcopy(compatibility),
            "target": copy.deepcopy(compatibility),
        }
        malformed_documents["artifact"]["targets"]["arm64"]["artifact_sha256"] = 7
        malformed_documents["elf"]["targets"]["arm64"]["elf"] = "ELF64/arbitrary"
        malformed_documents["target"]["targets"]["arm64"] = []
        expected_errors = {
            "artifact": f"{CORE_ID}/arm64: artifact digest is invalid",
            "elf": f"{CORE_ID}/arm64: ELF label is invalid",
            "target": f"{CORE_ID}/arm64: compatibility target is invalid",
        }
        for label, malformed in malformed_documents.items():
            with self.subTest(compatibility_mutation=label):
                malformed["content_sha256"] = (
                    pipeline.core_compatibility_content_sha256(malformed)
                )
                report = pipeline.validate_core_compatibility_document(
                    malformed,
                    document_path=compatibility_path,
                    repository_root=ROOT,
                    verify_pin=False,
                )
                self.assertEqual("invalid", report["status"])
                self.assertIn(expected_errors[label], report["errors"])

        missing_reproduction = copy.deepcopy(compatibility)
        missing_reproduction["reproduction_run"] = (
            ".local-e2e/runs/nonexistent-mednafen-supafaust/e2e-record.json"
        )
        missing_reproduction["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(missing_reproduction)
        )
        missing_report = pipeline.validate_core_compatibility_document(
            missing_reproduction,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", missing_report["status"])
        self.assertIn(
            "individual core reproduction E2E record is unavailable",
            missing_report["errors"],
        )

        wrong_reproduction_digest = copy.deepcopy(compatibility)
        wrong_reproduction_digest["reproduction_e2e_content_sha256"] = "0" * 64
        wrong_reproduction_digest["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(wrong_reproduction_digest)
        )
        reproduction_digest_report = pipeline.validate_core_compatibility_document(
            wrong_reproduction_digest,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertIn(
            "individual core reproduction E2E content differs from compatibility",
            reproduction_digest_report["errors"],
        )

        same_run = copy.deepcopy(compatibility)
        same_run["reproduction_run"] = same_run["e2e_run"]
        same_run["reproduction_e2e_content_sha256"] = same_run[
            "selected_e2e_content_sha256"
        ]
        same_run["content_sha256"] = pipeline.core_compatibility_content_sha256(
            same_run
        )
        same_run_report = pipeline.validate_core_compatibility_document(
            same_run,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        swapped_runs = copy.deepcopy(compatibility)
        swapped_runs["e2e_run"], swapped_runs["reproduction_run"] = (
            swapped_runs["reproduction_run"],
            swapped_runs["e2e_run"],
        )
        swapped_runs["content_sha256"] = pipeline.core_compatibility_content_sha256(
            swapped_runs
        )
        swapped_report = pipeline.validate_core_compatibility_document(
            swapped_runs,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", swapped_report["status"])
        self.assertIn(
            "individual core selected E2E run differs from compatibility",
            swapped_report["errors"],
        )

        pin_mutations = {
            "digest": copy.deepcopy(pin),
            "semantic_id": copy.deepcopy(pin),
            "source_reference": copy.deepcopy(pin),
        }
        pin_mutations["digest"]["content_sha256"] = "0" * 64
        pin_mutations["semantic_id"]["pin_id"] = (
            "mednafen_supafaust-nonsemantic-pin"
        )
        pin_mutations["semantic_id"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["semantic_id"])
        )
        pin_mutations["source_reference"]["sources"][0]["file_sha256"] = "0" * 64
        pin_mutations["source_reference"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["source_reference"])
        )
        expected_pin_errors = {
            "digest": "individual core pin: pin-set content digest is invalid",
            "semantic_id": "individual core pin ID is not semantic",
            "source_reference": (
                "individual core pin: source 0 no longer matches the pin"
            ),
        }
        for label, malformed_pin in pin_mutations.items():
            with self.subTest(pin_mutation=label), mock.patch.object(
                compatibility_records,
                "load_json",
                return_value=malformed_pin,
            ):
                pin_report = pipeline.validate_core_compatibility_document(
                    compatibility,
                    document_path=compatibility_path,
                    repository_root=ROOT,
                )
                self.assertEqual("invalid", pin_report["status"])
                self.assertIn(expected_pin_errors[label], pin_report["errors"])

    def test_reproduction_rejects_recomputed_record_tampering(self) -> None:
        _, pin, _, _ = load_core_documents(CORE_ID, PIN_NAME)
        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        mutations = {
            "log": "historical build differs",
            "build": "historical build differs",
            "recipe": "historical recipe differs",
            "source": "historical source differs",
            "toolchain": "historical toolchain differs",
            "record_fields": "build record fields are invalid",
        }
        for mutation, expected_error in mutations.items():
            with self.subTest(mutation=mutation), copied_e2e_run(
                REPRODUCTION_RUN,
                prefix=f"compat-tamper-supafaust-{mutation}-",
                content_hasher=pipeline.e2e_content_sha256,
            ) as (run_root, evidence):
                record_path = run_root / CORE_ID / "arm64" / "build-record.json"
                record = load_document(record_path)
                if mutation == "log":
                    log_path = record_path.parent / record["build"]["log"]
                    log_path.write_text(
                        log_path.read_text(encoding="utf-8") + "warning: extra\n",
                        encoding="utf-8",
                    )
                    record["build"]["log_sha256"] = file_sha256(log_path)
                elif mutation == "build":
                    record["build"]["environment"] = "tampered-v1"
                elif mutation == "recipe":
                    record["recipe"]["repository_dirty"] = not record["recipe"][
                        "repository_dirty"
                    ]
                elif mutation == "source":
                    record["source"]["resolved_url"] = (
                        "https://example.invalid/tampered.git"
                    )
                elif mutation == "toolchain":
                    record["toolchain"]["compiler"] += " tampered"
                else:
                    record["unexpected"] = True
                write_document(record_path, record)
                refresh_copied_e2e(
                    run_root,
                    evidence,
                    pipeline.e2e_content_sha256,
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError, expected_error
                ):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )

    def test_reproduction_rejects_impossible_diagnostic_reordering(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-reorder-supafaust-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_text = log_path.read_text(encoding="utf-8")
            warning_block = (
                mednafen_supafaust.MEDNAFEN_SUPAFAUST_MTHREAD_WARNING_BLOCK
                + "\n"
            )
            warning_lines = warning_block.splitlines(keepends=True)
            reordered_block = "".join(
                (warning_lines[1], warning_lines[0], *warning_lines[2:])
            )
            reordered_log = log_text.replace(
                warning_block, reordered_block, 1
            )
            self.assertNotEqual(log_text, reordered_log)
            self.assertEqual(
                Counter(log_text.splitlines(keepends=True)),
                Counter(reordered_log.splitlines(keepends=True)),
            )
            self.assertFalse(
                mednafen_supafaust.mednafen_supafaust_log_proves_contract(
                    reordered_log,
                    CORE_ID,
                    "arm64",
                    SOURCE_COMMIT,
                    SOURCE_TREE,
                )
            )
            log_path.write_text(reordered_log, encoding="utf-8")
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(
                run_root,
                evidence,
                pipeline.e2e_content_sha256,
            )

            mutated = copy.deepcopy(compatibility)
            mutated["reproduction_run"] = (
                f".local-e2e/runs/{run_root.name}/e2e-record.json"
            )
            mutated["reproduction_e2e_content_sha256"] = evidence[
                "content_sha256"
            ]
            mutated["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(mutated)
            )
            report = pipeline.validate_core_compatibility_document(
                mutated,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertEqual("invalid", report["status"])
            registered_contract = pipeline.core_log_contract_for(CORE_ID)
            self.assertIsNotNone(registered_contract)
            assert registered_contract is not None
            self.assertTrue(
                any(
                    registered_contract.failure_message in error
                    for error in report["errors"]
                ),
                report["errors"],
            )


if __name__ == "__main__":
    unittest.main()
