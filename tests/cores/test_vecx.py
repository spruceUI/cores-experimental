"""VecX individual catalog and build-contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import vecx
from tests.test_contract_vecx import build_vecx_log_fixture

from .support import (
    ROOT,
    file_sha256,
    load_core_documents,
    load_document,
)


CORE_ID = "vecx"
OTHER_CORE_ID = "prosystem"
PIN_NAME = "vecx-8f671cc9d737-4686ef94bf56.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "8f671cc9d737f2890c3ce19e177e2984dcae121f"
SOURCE_TREE = "49ae584713edede2a70792ecf6cb744b11fff2e6"
SOURCE_URL = "https://github.com/libretro/libretro-vecx.git"
SOURCE_LOCK_ID = "vecx-8f671cc9d737"
SELECTION_SHA256 = (
    "4686ef94bf5663774c2134793211747442264d9f8022d489b78ec7756435a1cf"
)
SELECTED_RUN = "actions-sim-build-core-vecx-v1"
REPRODUCTION_RUN = "build-core-vecx-local-v1"
SELECTED_E2E_CONTENT_SHA256 = (
    "b188e468224d938e050391c7fe3bef89a49ac7f27e503e6517da79a1b2cae021"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "848f9c2404fb57283c4cad9f2c71eebd9649d4b8764cb2be746dc5dc64dcfbfa"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "bc377ca2efe5e0bacf77b890d7c5cd036bcec58c33b03df0f783d2cca13f84b0"
    ),
    REPRODUCTION_RUN: (
        "f355947a6cf5bf4c7bb9c01101e14f919362a471953563e28e1d85442766144a"
    ),
}
PACKAGE_SHA256 = (
    "316c893f984b88c0684fa41358fe802613b8bec77fde17183b30e6d9b38631e4"
)
METADATA_SHA256 = vecx.VECX_METADATA_REPLACEMENT_SHA256
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
            "8a041cbedb449b01e6a71a657107e3a5a4839fb9a34d43a1ee81883832d6c578"
        ),
        "artifact_size": 106040,
        "record_sha256": {
            SELECTED_RUN: (
                "3cd2d702e951f31b06cf27be176ceff14d0e39ceb9d2dfee5eaf92a84a1e84d2"
            ),
            REPRODUCTION_RUN: (
                "dd2c595cb043f46c7860b09795ead4115bb60ee7963f8433bdc4969a1c86cc77"
            ),
        },
        "log_sha256": (
            "aa594b8674de6738abd126cf5d6ad60792a27df502d98399ab1993d716a8158e"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "ebf753efb74779929bb0753611c81786f0c38b88adf82f648d97704af1022b6f"
        ),
        "artifact_size": 86488,
        "record_sha256": {
            SELECTED_RUN: (
                "1dcfe59a60e0a27abdb868ba1c7399b73264b98c1e36a648a717a7fbf84a26c8"
            ),
            REPRODUCTION_RUN: (
                "abcb16e064e021b5092f20222a715e3e0c06be04870cc2ee8efb204a7e426f50"
            ),
        },
        "log_sha256": (
            "42c687505d95c85f99abc64c1d872434f2ffb761bb69d3be5a1c71619347ccae"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4"],
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
    "all four C compile commands",
    "complete ordered link invocation",
    "1.2 8f671cc",
    "GPLv3",
    "No external firmware",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)


class VecxCoreTests(unittest.TestCase):
    def _legacy_recipe_without_pipeline_bundle(self, recipe: dict) -> dict:
        legacy_recipe = copy.deepcopy(recipe)
        pipeline_bundle = legacy_recipe.pop("pipeline_bundle")
        commit_blacklist = legacy_recipe.pop("commit_blacklist")
        self.assertTrue(
            pipeline.pipeline_source_bundle_is_well_formed(pipeline_bundle)
        )
        self.assertTrue(
            pipeline.commit_blacklist_reference_is_well_formed(commit_blacklist)
        )
        self.assertNotIn("pipeline_bundle", legacy_recipe)
        self.assertNotIn("commit_blacklist", legacy_recipe)
        return legacy_recipe

    def test_vecx_semantic_pin_and_compatibility_bind_promoted_evidence(
        self,
    ) -> None:
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
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )
        self.assertEqual(
            f".local-e2e/runs/{SELECTED_RUN}/e2e-record.json",
            compatibility["e2e_run"],
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            f".local-e2e/runs/{REPRODUCTION_RUN}/e2e-record.json",
            compatibility["reproduction_run"],
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
            compatibility["reproduction_e2e_content_sha256"],
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
            caveats,
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
                    expected["artifact_sha256"], selected_target["artifact"]["sha256"]
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual([], golden_record["build"]["compile_definitions"])
                self.assertEqual(
                    vecx.VECX_SOFTWARE_MAKE_VARIABLES,
                    golden_record["build"]["make_variables"],
                )
                self.assertEqual(
                    {
                        "derivation": vecx.VECX_NATIVE_GIT_VERSION_DERIVATION,
                        "value": vecx.VECX_NATIVE_GIT_VERSION,
                    },
                    golden_record["build"]["git_version"],
                )
                self.assertEqual(
                    vecx.VECX_METADATA_REPLACEMENT,
                    golden_record["build"]["metadata_replacement"],
                )
                self.assertEqual(METADATA_SHA256, golden_record["metadata"]["sha256"])
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

    def test_vecx_source_set_release_and_channels_are_core_owned(self) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        profile_report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, profile_report["source_set_id"])
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
        self.assertEqual(1, profile_report["counts"]["source_locks"])
        self.assertEqual(2, profile_report["counts"]["build_evidence_cells"])
        self.assertEqual(
            {
                "catalog_cores": catalog_core_count,
                "catalog_unlocked_cores": catalog_core_count - 1,
                "evidence_cells": 2,
                "locked_cores": 1,
            },
            profile_report["mirror"],
        )
        cells = {
            cell["architecture"]: cell
            for cell in profile_report["build_evidence_cells"]
        }
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(profile=architecture):
                self.assertEqual(CORE_ID, cells[architecture]["core_id"])
                self.assertEqual(
                    SOURCE_LOCK_ID, cells[architecture]["source_lock_id"]
                )
                self.assertEqual(
                    expected["artifact_sha256"],
                    cells[architecture]["artifact_sha256"],
                )
                self.assertEqual(
                    expected["execution_profile_id"],
                    cells[architecture]["execution_profile_id"],
                )
        self.assertTrue(profile_report["device_views"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in profile_report["device_views"]
            )
        )

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

    def test_vecx_selected_and_local_runs_reproduce_exact_bytes(self) -> None:
        contract = vecx.VECX_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("vecx-software-c-only-v1", registered_contract.contract_id)
        self.assertEqual("vecx_log_proves_contract", registered_contract.proof_name)
        self.assertEqual(4, contract.expected_compile_count)
        self.assertEqual(
            vecx.VECX_EXPECTED_COMPILE_PAIR_SHA256,
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            vecx.VECX_EXPECTED_COMPILE_INVOCATION_SHA256,
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            vecx.VECX_EXPECTED_LINK_OBJECT_SHA256,
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            vecx.VECX_EXPECTED_RAW_LINK_OBJECT_SHA256,
            contract.expected_raw_link_object_sha256,
        )

        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
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
                self.assertEqual(76617, package["size"])
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/vecx_libretro.so",
                            "cores/vecx_libretro.so",
                            "vecx_libretro.info",
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
                        self.assertEqual("libretro-super", record["build"]["driver"])
                        self.assertEqual(
                            "sanitized-v1", record["build"]["environment"]
                        )
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertEqual(
                            vecx.VECX_SOFTWARE_MAKE_VARIABLES,
                            record["build"]["make_variables"],
                        )
                        self.assertEqual(
                            vecx.VECX_METADATA_REPLACEMENT,
                            record["build"]["metadata_replacement"],
                        )

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(expected["log_sha256"], file_sha256(log_path))
                        self.assertEqual(
                            expected["log_sha256"], record["build"]["log_sha256"]
                        )
                        logs[architecture].append(log_bytes)
                        self.assertEqual(
                            4,
                            log_text.count(vecx.VECX_NATIVE_GIT_VERSION_LOG_TOKEN),
                        )
                        self.assertEqual(4, log_text.count("-DGIT_VERSION="))
                        self.assertEqual(
                            1, log_text.count(vecx.VECX_METADATA_REPLACEMENT_MARKER)
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
                        lowered_log = log_text.casefold()
                        for marker in vecx.VECX_FORBIDDEN_DIAGNOSTIC_MARKERS:
                            self.assertNotIn(marker, lowered_log)
                        for marker in vecx.VECX_FORBIDDEN_GPU_LOG_MARKERS:
                            self.assertNotIn(marker, lowered_log)
                        self.assertIsNone(vecx.VECX_MAKE_FAILURE_RE.search(log_text))

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'license = "GPLv3"', metadata)
                        self.assertIn(b'hw_render = "false"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        self.assertEqual(
                            expected["needed"], record["artifact"]["needed"]
                        )
                        self.assertTrue(
                            all(
                                not library.casefold().startswith(
                                    ("libegl", "libgl", "libgles", "libopengl")
                                )
                                for library in record["artifact"]["needed"]
                            )
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"1.2 8f671cc", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_vecx_compatibility_and_registered_proof_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
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
        link_line = next(
            line
            for line in log_text.splitlines()
            if " -ovecx_libretro.so " in line and " -c " not in line
        )
        reordered_link = link_line.replace(
            "./e6809.o ./vecx_psg.o", "./vecx_psg.o ./e6809.o"
        )
        self.assertNotEqual(link_line, reordered_link)
        self.assertFalse(
            pipeline.registered_core_log_contract_proves(
                log_text.replace(link_line, reordered_link, 1),
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_vecx_software_recipe_is_exact_typed_and_sanitized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["vecx"]
        expected_git_version = {
            "derivation": "native-space-short7-v1",
            "value": " 8f671cc",
        }
        expected_replacement = {
            "kind": "whole-file-v1",
            "path": "metadata/vecx/software-v1.info",
            "preimage_sha256": (
                "9eec259b2b84256aca32cdcd37b084732"
                "b17d2fce829dac01bab9a84ea01b4e3"
            ),
            "replacement_sha256": (
                "2f22e8069a304878b52aeb5d7f789812"
                "bf271c61e5c41e0cb0fbd6acb5d28c1a"
            ),
        }
        self.assertEqual(
            {
                "url": "https://github.com/libretro/libretro-vecx.git",
                "requested_ref": "refs/heads/master",
                "commit": "8f671cc9d737f2890c3ce19e177e2984dcae121f",
                "tree": "49ae584713edede2a70792ecf6cb744b11fff2e6",
            },
            spec["source"],
        )
        self.assertEqual({"HAS_GPU": 0}, pipeline.validated_make_variables(spec))
        self.assertEqual(expected_git_version, pipeline.validated_git_version(spec))
        self.assertEqual(expected_replacement, spec["metadata"]["replacement"])
        self.assertEqual(
            expected_replacement,
            pipeline.validated_metadata_replacement(spec),
        )
        self.assertTrue(
            pipeline.metadata_replacement_contract_is_well_formed(
                expected_replacement
            )
        )
        self.assertFalse(
            pipeline.metadata_replacement_contract_is_well_formed(
                {**expected_replacement, "replacement_sha256": "b" * 64}
            )
        )
        self.assertEqual(
            expected_replacement["replacement_sha256"],
            pipeline.sha256_file(ROOT / expected_replacement["path"]),
        )
        self.assertEqual(
            ["libEGL", "libGL", "libGLES", "libOpenGL"],
            pipeline.validated_forbidden_needed_prefixes(spec),
        )
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
        schema = json.loads(
            (ROOT / "manifests" / "core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "#/$defs/vecxCore",
            schema["properties"]["cores"]["properties"]["vecx"]["$ref"],
        )
        vecx_schema = schema["$defs"]["vecxCore"]["allOf"][1]
        self.assertIn("validation", vecx_schema["required"])
        self.assertIn(
            "make_variables",
            vecx_schema["properties"]["build"]["required"],
        )
        self.assertEqual(
            expected_git_version["value"],
            vecx_schema["properties"]["build"]["properties"]["git_version"][
                "allOf"
            ][1]["properties"]["value"]["const"],
        )
        self.assertIn(
            "replacement",
            vecx_schema["properties"]["metadata"]["required"],
        )
        for arch in ("arm64", "armhf"):
            contract = pipeline.normalized_build_contract(spec, arch)
            self.assertEqual({"HAS_GPU": 0}, contract["make_variables"])
            self.assertEqual(expected_git_version, contract["git_version"])
            self.assertEqual(
                expected_replacement, contract["metadata_replacement"]
            )

        script = pipeline.container_build_script(
            "vecx", "arm64", spec, catalog["resolver"]
        )
        unset_variables = set(
            next(
                line for line in script.splitlines() if line.startswith("unset ")
            ).split()[1:]
        )
        self.assertTrue({"GIT_VERSION", "HAS_GPU"}.issubset(unset_variables))
        self.assertIn("HAS_GPU=0", script)
        self.assertIn(" 8f671cc", script)
        self.assertIn(expected_replacement["preimage_sha256"], script)
        self.assertIn(expected_replacement["replacement_sha256"], script)
        self.assertIn("/metadata-replacements/vecx.info", script)
        self.assertGreater(
            script.index(expected_replacement["preimage_sha256"]),
            script.index("./libretro-build.sh vecx"),
        )
        self.assertLess(
            script.index(expected_replacement["preimage_sha256"]),
            script.rindex(expected_replacement["replacement_sha256"]),
        )

    def test_vecx_catalog_contract_mutations_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")

        def mutation(label: str, mutate, message: str) -> tuple[str, dict, str]:
            changed = copy.deepcopy(catalog)
            mutate(changed["cores"]["vecx"])
            return label, changed, message

        def remove_software_contract(
            spec: dict, *, single_target: bool = False
        ) -> None:
            spec["build"].pop("make_variables")
            spec["build"].pop("git_version")
            spec["metadata"].pop("replacement")
            spec.pop("validation")
            if single_target:
                spec["targets"] = ["arm64"]

        mutations = (
            mutation(
                "missing-make-variable",
                lambda spec: spec["build"]["make_variables"].pop("HAS_GPU"),
                "make_variables",
            ),
            mutation(
                "extra-make-variable",
                lambda spec: spec["build"]["make_variables"].update(
                    {"OPENGL": 0}
                ),
                "make_variables",
            ),
            mutation(
                "gpu-enabled",
                lambda spec: spec["build"]["make_variables"].update(
                    {"HAS_GPU": 1}
                ),
                "VecX software",
            ),
            mutation(
                "boolean-gpu",
                lambda spec: spec["build"]["make_variables"].update(
                    {"HAS_GPU": False}
                ),
                "exact integer",
            ),
            mutation(
                "missing-native-version",
                lambda spec: spec["build"].pop("git_version"),
                "VecX software build keys",
            ),
            mutation(
                "hyphen-version",
                lambda spec: spec["build"]["git_version"].update(
                    {
                        "derivation": "hyphen-short7-v1",
                        "value": "-8f671cc",
                    }
                ),
                "native-space-short7-v1",
            ),
            mutation(
                "wrong-native-version",
                lambda spec: spec["build"]["git_version"].update(
                    {"value": " 0000000"}
                ),
                "first seven source commit",
            ),
            mutation(
                "replacement-kind",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"kind": "line-edit-v1"}
                ),
                "whole-file-v1",
            ),
            mutation(
                "replacement-path",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"path": "metadata/vecx/../software-v1.info"}
                ),
                "path",
            ),
            mutation(
                "preimage",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"preimage_sha256": "a" * 64}
                ),
                "preimage_sha256",
            ),
            mutation(
                "replacement-digest",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"replacement_sha256": "b" * 64}
                ),
                "replacement_sha256",
            ),
            mutation(
                "replacement-extra",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"extra": True}
                ),
                "exact metadata replacement fields",
            ),
            mutation(
                "dependency-policy",
                lambda spec: spec["validation"][
                    "forbidden_needed_prefixes"
                ].remove("libGL"),
                "VecX software dependency policy",
            ),
            mutation(
                "source-identity",
                lambda spec: spec["source"].update({"tree": "a" * 40}),
                "VecX software source",
            ),
            mutation(
                "all-software-controls-removed",
                remove_software_contract,
                "exact VecX software",
            ),
            mutation(
                "all-software-controls-removed-single-target",
                lambda spec: remove_software_contract(
                    spec, single_target=True
                ),
                "exact VecX software",
            ),
        )
        for label, changed, message in mutations:
            with self.subTest(label=label), self.assertRaisesRegex(
                pipeline.PipelineError, message
            ):
                pipeline.validate_catalog(changed)

    def test_vecx_make_and_native_version_log_proofs_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["vecx"]
        variables = spec["build"]["make_variables"]
        git_version = spec["build"]["git_version"]
        metadata_replacement = spec["metadata"]["replacement"]
        make_markers = pipeline.make_variable_log_markers(spec)
        version_markers = pipeline.git_version_log_markers(spec)
        metadata_markers = pipeline.metadata_replacement_markers(
            metadata_replacement
        )
        compilers = {
            "arm64": "aarch64-linux-gnu-gcc",
            "armhf": "arm-a30-linux-gnueabihf-gcc",
        }
        version_token = r'-DGIT_VERSION=\"" 8f671cc"\"'

        def valid_log(arch: str) -> str:
            compiler = compilers[arch]
            return (
                "\n".join([*make_markers, *version_markers])
                + f"\n{compiler} {version_token} -c source.c -o source.o\n"
                + f"{compiler} -shared source.o -lm -o vecx_libretro.so\n"
                + "\n".join(metadata_markers)
                + "\n"
            )

        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                log = valid_log(arch)
                self.assertTrue(
                    pipeline.make_variable_log_proves_contract(
                        log, variables, arch
                    )
                )
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log,
                        git_version,
                        spec["source"]["commit"],
                        arch,
                    )
                )
                self.assertTrue(
                    pipeline.metadata_replacement_log_proves_contract(
                        log, metadata_replacement
                    )
                )

        baseline = valid_log("arm64")
        compile_line = next(
            line for line in baseline.splitlines() if " -c " in line
        )
        make_mutations = {
            "missing-marker": baseline.replace(make_markers[0] + "\n", "", 1),
            "environment-origin": baseline.replace(
                "|command line", "|environment", 1
            ),
            "duplicate-marker": make_markers[0] + "\n" + baseline,
            "markers-after-compile": compile_line
            + "\n"
            + "\n".join([*make_markers, *version_markers])
            + "\naarch64-linux-gnu-gcc -shared source.o -lm "
            + "-o vecx_libretro.so\n",
            "has-gpu-define": baseline.replace(
                " -c source.c", " -DHAS_GPU -c source.c", 1
            ),
            "has-gpu-undef": baseline.replace(
                " -c source.c", " -UHAS_GPU -c source.c", 1
            ),
            "has-gpu-wp": baseline.replace(
                " -c source.c", " -Wp,-DHAS_GPU=0 -c source.c", 1
            ),
            "gl-link": baseline.replace(" -lm ", " -lm -lGL ", 1),
            "obfuscated-compiler-gl-link": baseline.replace(
                "aarch64-linux-gnu-gcc -shared",
                'aarch64-linux-gnu-g""cc -shared',
            ).replace(" -lm ", " -lm -lGL ", 1),
            "opengl-link": baseline.replace(" -lm ", " -lm -lOpenGL ", 1),
            "gles-link": baseline.replace(" -lm ", " -lm -lGLESv2 ", 1),
            "egl-link": baseline.replace(" -lm ", " -lm -lEGL ", 1),
            "gpu-source": baseline.replace(
                "source.c", "libretro-common/glsym/glsym_gl.c", 1
            ),
            "gpu-object": baseline.replace(
                "source.o -lm", "libretro-common/glsym/rglgen.o -lm", 1
            ),
            "response-file": baseline.replace(
                " -c source.c", " @compiler-options.rsp -c source.c", 1
            ),
        }
        for label, changed_log in make_mutations.items():
            with self.subTest(make_log=label):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        changed_log, variables, "arm64"
                    )
                )

        version_mutations = {
            "missing-marker": baseline.replace(version_markers[0] + "\n", "", 1),
            "environment-origin": baseline.replace(
                version_markers[-1],
                version_markers[-1].replace("|file", "|environment"),
            ),
            "duplicate-marker": version_markers[0] + "\n" + baseline,
            "markers-after-compile": compile_line
            + "\n"
            + "\n".join([*make_markers, *version_markers])
            + "\naarch64-linux-gnu-gcc -shared source.o -lm "
            + "-o vecx_libretro.so\n",
            "hyphen-version": baseline.replace(" 8f671cc", "-8f671cc"),
            "wrong-native-version": baseline.replace(" 8f671cc", " 0000000"),
            "missing-compile-token": baseline.replace(" " + version_token, "", 1),
            "unquoted-version": baseline.replace(
                version_token, "-DGIT_VERSION=8f671cc"
            ),
            "obfuscated-unbound-compile": baseline
            + 'aarch64-linux-gnu-g""cc -""c other.c -o other.o\n',
        }
        for label, changed_log in version_mutations.items():
            with self.subTest(version_log=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        changed_log,
                        git_version,
                        spec["source"]["commit"],
                        "arm64",
                    )
                )

        for label, changed_log in {
            "missing-marker": baseline.replace(
                metadata_markers[0] + "\n", "", 1
            ),
            "duplicate-marker": metadata_markers[0] + "\n" + baseline,
            "wrong-preimage": baseline.replace(
                metadata_replacement["preimage_sha256"], "a" * 64
            ),
            "wrong-replacement": baseline.replace(
                metadata_replacement["replacement_sha256"], "b" * 64
            ),
        }.items():
            with self.subTest(metadata_log=label):
                self.assertFalse(
                    pipeline.metadata_replacement_log_proves_contract(
                        changed_log, metadata_replacement
                    )
                )

    def test_vecx_recipe_snapshot_v8_binds_combined_software_contract(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "vecx"
        arch = "arm64"
        spec = catalog["cores"][core_id]
        replacement_path = spec["metadata"]["replacement"]["path"]
        record = {
            "core_id": core_id,
            "architecture": arch,
            "source": {
                **spec["source"],
                "resolved_commit": spec["source"]["commit"],
                "resolved_url": spec["source"]["url"],
                "submodules": [],
            },
            "recipe": self._legacy_recipe_without_pipeline_bundle(
                pipeline.recipe_record(catalog_path, core_id, spec)
            ),
            "toolchain": {
                **catalog["toolchains"][arch],
                "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                "resolver_digests": catalog["resolver"],
                "archive_provenance": pipeline.expected_archive_provenance(
                    catalog, arch
                ),
            },
            "artifact": {
                "needed": [
                    "ld-linux-aarch64.so.1",
                    "libc.so.6",
                    "libm.so.6",
                ]
            },
            "metadata": {
                "status": "valid",
                "sha256": spec["metadata"]["replacement"]["replacement_sha256"],
            },
            "build": {
                **pipeline.normalized_build_contract(spec, arch),
                "log": "build.log",
                "log_sha256": "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "vecx-v8.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(8, snapshot["schema_version"])
            self.assertEqual(
                pipeline.recorded_build_contract(record["build"]),
                snapshot["build"],
            )
            self.assertIn(replacement_path, snapshot["files"])
            self.assertEqual(
                spec["metadata"]["replacement"]["replacement_sha256"],
                snapshot["files"][replacement_path]["sha256"],
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "vecx/v8"
                ),
            )

            original_identity = pipeline.provenance_identity_sha256(record)
            for label, mutate in (
                (
                    "make-variable",
                    lambda changed: changed["build"]["make_variables"].update(
                        {"HAS_GPU": 1}
                    ),
                ),
                (
                    "native-version",
                    lambda changed: changed["build"]["git_version"].update(
                        {"value": " 0000000"}
                    ),
                ),
                (
                    "metadata-replacement",
                    lambda changed: changed["build"][
                        "metadata_replacement"
                    ].update({"replacement_sha256": "b" * 64}),
                ),
            ):
                changed = copy.deepcopy(record)
                mutate(changed)
                with self.subTest(build=label):
                    self.assertNotEqual(
                        original_identity,
                        pipeline.provenance_identity_sha256(changed),
                    )
                    self.assertTrue(
                        pipeline.verify_recipe_snapshot(
                            snapshot_path, changed, f"vecx/v8-{label}"
                        )
                    )

            tampered_snapshot = copy.deepcopy(snapshot)
            tampered_snapshot["schema_version"] = 7
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertIn(
                "vecx/v8-version: recipe snapshot schema version mismatch",
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "vecx/v8-version"
                ),
            )

            tampered_snapshot = copy.deepcopy(snapshot)
            tampered_snapshot["files"][replacement_path]["text"] += "\n"
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "vecx/v8-metadata-bytes"
                )
            )

            tampered_snapshot["files"][replacement_path]["sha256"] = (
                pipeline.sha256_bytes(
                    tampered_snapshot["files"][replacement_path]["text"].encode()
                )
            )
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "recipe record digest mismatch" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, record, "vecx/v8-metadata-rehashed"
                    )
                )
            )

            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            wrong_metadata = copy.deepcopy(record)
            wrong_metadata["metadata"]["sha256"] = "b" * 64
            self.assertTrue(
                any(
                    "metadata does not match" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, wrong_metadata, "vecx/v8-output-metadata"
                    )
                )
            )

            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            forbidden = copy.deepcopy(record)
            forbidden["artifact"]["needed"].append("libGL.so.1")
            self.assertTrue(
                any(
                    "dependency policy" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, forbidden, "vecx/v8-dependency"
                    )
                )
            )

    def test_vecx_metadata_replacement_is_output_bound(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "vecx"
        spec = catalog["cores"][core_id]
        arch = "arm64"
        replacement = spec["metadata"]["replacement"]
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes((ROOT / replacement["path"]).read_bytes())
            log.write_text(
                build_vecx_log_fixture(arch),
                encoding="utf-8",
            )
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
                "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
            }
            document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": arch,
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "source": {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "submodules": [],
                },
                "toolchain": {
                    **catalog["toolchains"][arch],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, arch
                    ),
                    "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
                "build": {
                    **pipeline.normalized_build_contract(spec, arch),
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
            }
            record = root / "build-record.json"
            record.write_text(json.dumps(document), encoding="utf-8")
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ):
                self.assertEqual(
                    (artifact, metadata, log),
                    pipeline.validate_build_record_identity(
                        document, record, catalog_path, catalog
                    ),
                )

                metadata.write_bytes(b"self-consistent wrong metadata\n")
                wrong = copy.deepcopy(document)
                wrong["metadata"].update(
                    {
                        "sha256": pipeline.sha256_file(metadata),
                        "size": metadata.stat().st_size,
                    }
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "exact catalog replacement"
                ):
                    pipeline.validate_build_record_identity(
                        wrong, record, catalog_path, catalog
                    )

            wrong_metadata = {
                "status": "valid",
                "path": spec["metadata"]["artifact_name"],
                "sha256": "b" * 64,
                "size": 1,
            }
            package_result = pipeline.package_e2e_core(
                root,
                core_id,
                [
                    {
                        "architecture": target,
                        "result": "passed",
                        "metadata": copy.deepcopy(wrong_metadata),
                    }
                    for target in spec["targets"]
                ],
                spec,
            )
            self.assertEqual("not_packaged", package_result["result"])
            self.assertIn("catalog replacement", package_result["reason"])


if __name__ == "__main__":
    unittest.main()
