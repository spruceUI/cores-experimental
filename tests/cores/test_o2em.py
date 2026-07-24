"""Pinned O2EM build-evidence tests."""

from __future__ import annotations

import copy
from collections import Counter
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import o2em
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


CORE_ID = "o2em"
OTHER_CORE_ID = "prosystem"
PIN_NAME = "o2em-e03d3be88f79-a966ff1d0775.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "e03d3be88f79fe940b933e53f1515d97313f6c59"
SOURCE_TREE = "fef887dc747594a47e9bed9ac7367d2912b579d1"
SOURCE_URL = "https://github.com/libretro/libretro-o2em.git"
SOURCE_LOCK_ID = "o2em-e03d3be88f79"
SELECTION_SHA256 = (
    "a966ff1d0775c53cd287dc5e0615a1ef1ecd983094bf5ef09493114259207db8"
)
SELECTED_RUN = "actions-sim-build-core-o2em-w3"
REPRODUCTION_RUN = "build-core-o2em-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "76a3aa90248c26a1ca79a06a12e3fc4472b0c169358130e02214111a8e222c09"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "bb846bfdd517444502c2e74c20301bbab7851d413cb78a29f1f3e2ef55156530"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "fd118b71690c7890e0c03f039e67bfbd20835cfdf0cc55cfb1e8290bbd1b816c"
    ),
    REPRODUCTION_RUN: (
        "0ca14ba9fc6a5125c7dec8d0aa9b8cf3aa772a3060b2c569221c5fb0483fdb6e"
    ),
}
PACKAGE_SHA256 = (
    "da9ac3e4d2f713fd189bc8e6e0f61639489424c382bc56eb176d8d8839d9a5f3"
)
METADATA_SHA256 = (
    "d8cbfb38f736448d16817a4b2f17d61843e43c1b8bf64fae228a9d9e95e48378"
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
            "b2bdd1da9d01e6a673debf7b233aee67ef2ebe13ecde4953bb574bdef16766d6"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "ebc583f0bd7eb9129b2619a600ddfca5a2a4e358da33a20c1b70a2add44d58cf"
            ),
            REPRODUCTION_RUN: (
                "7e80fa306f79ee2ab1acae8724f61462a142a55b640fb408a5f975ebd91e127b"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "9765f77a372c9b024128b44bdade9bdc9e7b25f0a706f23d6a434bd547eee3c3"
            ),
            REPRODUCTION_RUN: (
                "9765f77a372c9b024128b44bdade9bdc9e7b25f0a706f23d6a434bd547eee3c3"
            ),
        },
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "720b854e6ab444ca78a6cdaba9f310064830a2686c714f94eef24507b804b94a"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "f2ac8331cbd6100d9eef6e3401b44f4efd8b315b7667e29147b4a1c7d91b32a8"
            ),
            REPRODUCTION_RUN: (
                "fed897af69a8e514e451e458781316ba9d6012902dcb815b64884546be09a7dc"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "34260f6ad9a869d157aa5b82d7161424849192c8756b04ee4a938d80097a3448"
            ),
            REPRODUCTION_RUN: (
                "34260f6ad9a869d157aa5b82d7161424849192c8756b04ee4a938d80097a3448"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.17", "GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
    },
}
SOURCE_LOCK_IDENTITY = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "submodules": [],
}
SOURCE_RECORD_IDENTITY = {
    "commit": SOURCE_COMMIT,
    "requested_ref": "refs/heads/master",
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
    "tree": SOURCE_TREE,
    "url": SOURCE_URL,
}
CAVEAT_TOKENS = (
    "same line multiset",
    "42 C compile commands",
    "1.18 e03d3be",
    "Artistic License",
    "o2rom.bin",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)


class O2emCoreEvidenceTests(unittest.TestCase):
    def test_semantic_pin_and_compatibility_bind_promoted_evidence(self) -> None:
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
            selection["e2e"]["content_sha256"],
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        reproduction_path = (
            ROOT / ".local-e2e" / "runs" / REPRODUCTION_RUN / "e2e-record.json"
        )
        reproduction = load_document(reproduction_path)
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
            reproduction["content_sha256"],
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
                self.assertEqual(architecture, golden_record["architecture"])
                self.assertEqual(SOURCE_RECORD_IDENTITY, golden_record["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual(
                    "needs-target-runtime", target["runtime_validation"]
                )
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(
                    expected["artifact_sha256"], target["artifact_sha256"]
                )
                self.assertEqual(
                    expected["artifact_sha256"],
                    selected_target["artifact"]["sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual([], golden_record["build"]["compile_definitions"])
                self.assertNotIn("git_version", golden_record["build"])
                self.assertEqual(METADATA_SHA256, golden_record["metadata"]["sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(
                    expected["elf"].split("/", 1)[0], artifact["elf"]["class"]
                )
                self.assertEqual(
                    "AArch64" if architecture == "arm64" else "ARM",
                    artifact["elf"]["machine"],
                )
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"],
                    target["version_requirements"],
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

    def test_source_set_binds_immutable_source_and_execution_profiles(self) -> None:
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
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock = load_document(ROOT / source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(SOURCE_LOCK_IDENTITY, source_lock["source"])
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
                self.assertEqual(
                    expected["artifact_sha256"], cell["artifact_sha256"]
                )
                self.assertEqual(
                    expected["execution_profile_id"],
                    cell["execution_profile_id"],
                )
        self.assertTrue(report["device_views"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_channels_target_semantic_core_artifacts(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": (
                f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json"
            ),
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
        self.assertEqual(
            "valid", release_report["status"], release_report["errors"]
        )
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

    def test_selected_and_local_runs_prove_exact_reproducible_builds(self) -> None:
        contract = o2em.O2EM_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("o2em-c-only-v1", registered_contract.contract_id)
        self.assertEqual("o2em_log_proves_contract", registered_contract.proof_name)
        self.assertEqual(42, contract.expected_compile_count)
        self.assertEqual(
            "114f728cdc7478e5051cdf758c1c2e6c8a3ec79429df70fc9b5c4a9137b6823c",
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "db363efa7a87669274fd8287d048b4afc2abfc37494216c612b88e081cfbdf43"
                ),
                "armhf": (
                    "2d97f851bc6881e85566d83b77c0a4460c0e605463508779cb8948c8dd02f680"
                ),
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            "ac914313d526274da887a23b6be0f30aa4177e427040b56a94180bd7f5b9c7e2",
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
                e2e_path = run_root / "e2e-record.json"
                evidence = load_document(e2e_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(e2e_path))
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
                            "cores64/o2em_libretro.so",
                            "cores/o2em_libretro.so",
                            "o2em_libretro.info",
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
                            expected["record_sha256"][run_id],
                            build["record_sha256"],
                        )
                        record_path = ROOT / build["record"]
                        self.assertEqual(
                            build["record_sha256"], file_sha256(record_path)
                        )
                        record = load_document(record_path)
                        self.assertEqual(CORE_ID, record["core_id"])
                        self.assertEqual(architecture, record["architecture"])
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual(
                            "libretro-super", record["build"]["driver"]
                        )
                        self.assertEqual(
                            "sanitized-v1", record["build"]["environment"]
                        )
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertNotIn("git_version", record["build"])

                        log_path = record_path.parent / record["build"]["log"]
                        log_text = log_path.read_text(encoding="utf-8")
                        self.assertEqual(
                            expected["log_sha256"][run_id], file_sha256(log_path)
                        )
                        self.assertEqual(
                            expected["log_sha256"][run_id],
                            record["build"]["log_sha256"],
                        )
                        logs[architecture].append(log_text)
                        self.assertEqual(
                            42,
                            log_text.count(o2em.O2EM_NATIVE_GIT_VERSION_LOG_TOKEN),
                        )
                        self.assertEqual(42, log_text.count("-DGIT_VERSION="))
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                log_text,
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
                            )
                        )
                        lowered_log = log_text.casefold()
                        for marker in o2em.O2EM_FORBIDDEN_DIAGNOSTIC_MARKERS:
                            self.assertNotIn(marker, lowered_log)
                        self.assertIsNone(o2em.O2EM_MAKE_FAILURE_RE.search(log_text))

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "1.18"', metadata)
                        self.assertIn(b'license = "Artistic License"', metadata)
                        self.assertIn(b'firmware0_path = "o2rom.bin"', metadata)
                        self.assertIn(b'firmware3_path = "jopac.bin"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"1.18 e03d3be", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])

        self.assertEqual(logs["armhf"][0], logs["armhf"][1])
        # The v2 toolchain builds log deterministically, so the arm64 runs now
        # reproduce the log byte for byte as well.
        self.assertEqual(logs["arm64"][0], logs["arm64"][1])
        self.assertEqual(
            Counter(logs["arm64"][0].splitlines(keepends=True)),
            Counter(logs["arm64"][1].splitlines(keepends=True)),
        )
        clone_line = "Cloning into '/libretro-super/libretro-o2em'...\n"
        for log_text in logs["arm64"]:
            self.assertEqual(1, log_text.count(clone_line))

    def test_documents_and_registered_proof_fail_closed_on_tampering(self) -> None:
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
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        pin_mutations = {
            "digest": copy.deepcopy(pin),
            "semantic_id": copy.deepcopy(pin),
            "source_reference": copy.deepcopy(pin),
        }
        pin_mutations["digest"]["content_sha256"] = "0" * 64
        pin_mutations["semantic_id"]["pin_id"] = "o2em-nonsemantic-pin"
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

        source_set = load_document(ROOT / SOURCE_SET_PATH)
        malformed_source_set = copy.deepcopy(source_set)
        malformed_source_set["sources"][CORE_ID]["commit"] = "0" * 40
        with self.assertRaisesRegex(
            registry.RegistryError,
            "source set reference path does not bind o2em",
        ):
            registry.validate_source_set(malformed_source_set)

        log_path = (
            ROOT
            / ".local-e2e"
            / "runs"
            / REPRODUCTION_RUN
            / CORE_ID
            / "arm64"
            / "build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        proof_mutations = {
            "diagnostic": log_text + "warning: synthetic warning\n",
            "injected_marker": (
                log_text + "CORE_PIPELINE_GIT_VERSION|-e03d3be|command line\n"
            ),
            "native_version": log_text.replace(
                o2em.O2EM_NATIVE_GIT_VERSION_LOG_TOKEN,
                r'-DGIT_VERSION=\"-e03d3be\"',
                1,
            ),
        }
        for label, changed_log in proof_mutations.items():
            with self.subTest(proof_mutation=label):
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(
                        changed_log,
                        CORE_ID,
                        "arm64",
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
                )

    def test_reproduction_rejects_recomputed_build_record_tampering(self) -> None:
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
                prefix=f"compat-tamper-o2em-{mutation}-",
                content_hasher=pipeline.e2e_content_sha256,
            ) as (run_root, evidence):
                record_path = run_root / CORE_ID / "arm64" / "build-record.json"
                record = load_document(record_path)
                if mutation == "log":
                    log_path = record_path.parent / record["build"]["log"]
                    log_path.write_text(
                        log_path.read_text(encoding="utf-8")
                        + "warning: synthetic warning\n",
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
                with self.assertRaisesRegex(pipeline.PipelineError, expected_error):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )


if __name__ == "__main__":
    unittest.main()
