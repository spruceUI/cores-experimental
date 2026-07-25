"""Focused Gearboy catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import unittest
import zipfile
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from scripts.core_pipeline_lib.contracts import gearboy
from scripts.core_pipeline_lib.contracts import core_log_contract_for

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)
from .support import evidence_handles


CORE_ID = "gearboy"

_H = evidence_handles(CORE_ID)
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SOURCE_URL = _H["SOURCE_URL"]
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
SOURCE_LOCK_PATH = _H["SOURCE_LOCK_PATH"]
SOURCE_LOCK_FILE_SHA256 = _H["SOURCE_LOCK_FILE_SHA256"]
SOURCE_LOCK_CONTENT_SHA256 = _H["SOURCE_LOCK_CONTENT_SHA256"]
SOURCE_SET_FILE_SHA256 = _H["SOURCE_SET_FILE_SHA256"]
SOURCE_SET_CONTENT_SHA256 = _H["SOURCE_SET_CONTENT_SHA256"]
PIN_FILE_SHA256 = _H["PIN_FILE_SHA256"]
PIN_CONTENT_SHA256 = _H["PIN_CONTENT_SHA256"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
TARGETS = _H["TARGETS"]

GIT_DESCRIBE = "3.8.9-8-g36d723f"

GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"

GOLDEN_FILE_SHA256 = (
    "49c5731fdf801d162eb70174c74395e58f529ad795f814d26f543642b95666a6"
)

GOLDEN_CONTENT_SHA256 = (
    "f402a59373ce44fcdf1cd183fb2fcd33199ec100db1a8895d44a512739e30f7d"
)

SOURCE_RECORD = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
}

GOLDEN_BUILD = {
    "driver": "libretro-super",
    "environment": "sanitized-v1",
    "compile_definitions": [],
    "git_version": {
        "derivation": "native-git-describe-v1",
        "value": GIT_DESCRIBE,
    },
    "log": "build.log",
    "log_sha256": "a" * 64,
}

class GearboyCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_native_describe_identity(self) -> None:
        identity = gearboy.GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
        self.assertTrue(gearboy.gearboy_spec_is_well_formed(self.spec))
        self.assertTrue(
            pipeline.native_git_describe_spec_is_well_formed(
                self.spec, CORE_ID
            )
        )
        self.assertEqual(
            identity,
            pipeline.NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES[CORE_ID],
        )
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual(
            {
                "derivation": "native-git-describe-v1",
                "value": GIT_DESCRIBE,
            },
            pipeline.validated_git_version(self.spec),
        )
        self.assertEqual(
            {
                "derivation": "native-git-describe-v1",
                "value": GIT_DESCRIBE,
            },
            pipeline.exact_native_git_describe_contract(CORE_ID),
        )
        self.assertEqual(
            ["CORE_PIPELINE_NATIVE_GIT_VERSION|3.8.9-8-g36d723f|file"],
            pipeline.git_version_log_markers(self.spec),
        )
        shell = pipeline.git_version_shell(self.spec)
        self.assertIn("/libretro-super/libretro-gearboy/platforms/libretro", shell)
        self.assertIn("-f Makefile", shell)

    def test_catalog_rejects_cross_core_and_partial_describe_identities(self) -> None:
        mutations = {
            "gearcoleco-version": (
                ("build", "git_version", "value"),
                "1.6.6-11-g1123457",
            ),
            "unreviewed-version": (
                ("build", "git_version", "value"),
                "3.8.9-9-g36d723f",
            ),
            "wrong-source-tree": (("source", "tree"), "0" * 40),
            "wrong-source-key": (("build", "source_key"), "gearsystem"),
            "wrong-makefile-ref": (
                ("source", "requested_ref"),
                "refs/heads/main",
            ),
        }
        for label, (path, value) in mutations.items():
            catalog = copy.deepcopy(self.catalog)
            target = catalog["cores"][CORE_ID]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(mutation=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validate_catalog(catalog)

    def test_schema_keeps_gearboy_and_gearcoleco_exact_and_disjoint(self) -> None:
        schema = load_document(ROOT / "manifests" / "core-builds.schema.json")
        self.assertEqual(
            "1.6.6-11-g1123457",
            schema["$defs"]["nativeGitDescribeVersion"]["properties"][
                "value"
            ]["const"],
        )
        generic_refs = {
            branch["$ref"]
            for branch in schema["$defs"]["core"]["properties"]["build"][
                "properties"
            ]["git_version"]["oneOf"]
        }

    def test_golden_schema_binds_exact_gearboy_source_and_version(self) -> None:
        schema = load_document(
            ROOT / "manifests" / "golden-start.schema.json"
        )

    def test_copied_gearsystem_golden_identity_is_rejected(self) -> None:
        copied_source = copy.deepcopy(SOURCE_RECORD)
        copied_source.update(
            {
                "url": "https://github.com/drhelius/Gearsystem.git",
                "commit": "4f029e43f2d5207c5da78792503b0fff89b7b2c5",
                "tree": "8adfb454298c169327d705bebf94e699e5dbf480",
                "resolved_commit": (
                    "4f029e43f2d5207c5da78792503b0fff89b7b2c5"
                ),
                "resolved_url": "https://github.com/drhelius/Gearsystem.git",
            }
        )
        copied_build = copy.deepcopy(GOLDEN_BUILD)
        copied_build["git_version"]["value"] = "3.9.12-5-g4f029e4"
        self.assertFalse(
            pipeline.native_git_describe_golden_source_is_well_formed(
                CORE_ID, copied_source
            )
        )
        self.assertFalse(
            pipeline.git_version_golden_build_contract_is_well_formed(
                copied_build, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
            )
        )

    def test_pipeline_dispatches_core_owned_identity_and_golden_contracts(self) -> None:
        self.assertTrue(
            pipeline.native_git_describe_golden_source_is_well_formed(
                CORE_ID, SOURCE_RECORD
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                GOLDEN_BUILD,
                SOURCE_COMMIT,
                CORE_ID,
                SOURCE_RECORD,
            )
        )

        with mock.patch.object(
            pipeline, "gearboy_spec_is_well_formed", return_value=True
        ) as spec_proof:
            self.assertTrue(
                pipeline.native_git_describe_spec_is_well_formed({}, CORE_ID)
            )
            spec_proof.assert_called_once_with({})
        with mock.patch.object(
            pipeline,
            "gearboy_golden_source_is_well_formed",
            return_value=True,
        ) as source_proof:
            self.assertTrue(
                pipeline.native_git_describe_golden_source_is_well_formed(
                    CORE_ID, {}
                )
            )
            source_proof.assert_called_once_with(CORE_ID, {})
        with mock.patch.object(
            pipeline,
            "gearboy_golden_build_contract_is_well_formed",
            return_value=True,
        ) as build_proof:
            self.assertTrue(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    {}, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
                )
            )
            build_proof.assert_called_once_with(
                {}, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
            )

    def test_registry_and_proof_dispatch_are_singleton_and_core_owned(self) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("gearboy-mixed-language-v1", contract.contract_id)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual("gearboy_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)

        with mock.patch.object(
            pipeline, "gearboy_log_proves_contract", return_value=True
        ) as proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "build log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )
            proof.assert_called_once_with(
                "build log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
            )


class GearboyLifecycleTests(unittest.TestCase):

    def test_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests/core-builds.json")["cores"]
        )

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertTrue(source_set["local_only"])
        self.assertEqual("disabled", source_set["publication"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"])
        self.assertEqual(
            PIN_CONTENT_SHA256, source_set["evidence_pin"]["content_sha256"]
        )
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_PATH, source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, source["file_sha256"])
        self.assertEqual(SOURCE_LOCK_CONTENT_SHA256, source["content_sha256"])
        self.assertEqual(
            {
                "source_locks": 1,
                "execution_profiles": 5,
                "runtime_contracts": 8,
                "devices": 16,
                "build_evidence_cells": 2,
            },
            report["counts"],
        )
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
        for architecture, expected in TARGETS.items():
            self.assertEqual(
                expected["artifact_sha256"], cells[architecture]["artifact_sha256"]
            )
            self.assertEqual(
                expected["execution_profile_id"],
                cells[architecture]["execution_profile_id"],
            )
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                and view["eligibility"] == "provisional-unverified"
                for view in report["device_views"]
            )
        )


    def test_channels_release_and_mutations_fail_closed(self) -> None:
        target_paths = {
            "nightly": GOLDEN_PATH,
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            pointer = load_document(
                ROOT / ".local-e2e/channels" / f"{channel}.{CORE_ID}.json"
            )
            report = pipeline.validate_channel_pointer_document(
                pointer, expected_channel=channel, expected_core=CORE_ID
            )
            self.assertEqual("valid", report["status"], report["errors"])
            self.assertEqual(2, pointer["schema_version"])
            self.assertTrue(pointer["local_only"])
            self.assertEqual("disabled", pointer["publication"])
            self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
            self.assertEqual(target_path, pointer["target"]["path"])

        pin_path = ROOT / PIN_PATH
        pin = load_document(pin_path)
        release_root = ROOT / ".local-e2e/releases" / SEMANTIC_ID
        release_report = pipeline.validate_local_release(
            release_root,
            pin,
            file_sha256(pin_path),
            expected_release_id=SEMANTIC_ID,
        )
        self.assertEqual("valid", release_report["status"], release_report["errors"])

        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        mutations = {
            "digest": copy.deepcopy(compatibility),
            "publication": copy.deepcopy(compatibility),
            "runtime": copy.deepcopy(compatibility),
            "artifact": copy.deepcopy(compatibility),
            "run_identity": copy.deepcopy(compatibility),
        }
        mutations["digest"]["content_sha256"] = "0" * 64
        mutations["publication"]["publication"] = "enabled"
        mutations["runtime"]["targets"]["arm64"]["runtime_validation"] = "passed"
        mutations["artifact"]["targets"]["arm64"]["artifact_sha256"] = "0" * 64
        mutations["run_identity"]["reproduction_run"] = mutations["run_identity"][
            "e2e_run"
        ]
        mutations["run_identity"]["reproduction_e2e_content_sha256"] = mutations[
            "run_identity"
        ]["selected_e2e_content_sha256"]
        for label, mutated in mutations.items():
            if label != "digest":
                mutated["content_sha256"] = (
                    pipeline.core_compatibility_content_sha256(mutated)
                )
            with self.subTest(compatibility_mutation=label):
                report = pipeline.validate_core_compatibility_document(
                    mutated,
                    document_path=compatibility_path,
                    repository_root=ROOT,
                    verify_pin=label not in {"digest", "publication"},
                )
                self.assertEqual("invalid", report["status"], report["errors"])

    def test_reproduction_rejects_recomputed_log_tampering(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-gearboy-log-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_path.write_text(
                log_path.read_text(encoding="utf-8") + "warning: extra\n",
                encoding="utf-8",
            )
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)

            mutated = copy.deepcopy(compatibility)
            mutated["reproduction_run"] = (
                f".local-e2e/runs/{run_root.name}/e2e-record.json"
            )
            mutated["reproduction_e2e_content_sha256"] = evidence["content_sha256"]
            mutated["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(mutated)
            )
            report = pipeline.validate_core_compatibility_document(
                mutated,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertEqual("invalid", report["status"], report["errors"])

    def test_catalog_coverage_uses_canonical_state(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        coverage = pipeline.load_catalog_compatibility_coverage(
            catalog=catalog,
            repository_root=ROOT,
        )
        self.assertNotIn(CORE_ID, coverage["pending_compatibility_cores"])
        # Derive the expected canonical count from the filesystem so promoting a
        # bridge core never forces an edit here; the coverage tool must agree.
        canonical_manifests = len(
            list((ROOT / "manifests" / "compatibility").glob("*.json"))
        )
        self.assertEqual(
            canonical_manifests, coverage["canonical_compatibility_core_count"]
        )
        self.assertEqual(
            canonical_manifests,
            coverage["compatibility_coverage_core_count"],
        )
        self.assertEqual(
            len(catalog["cores"]),
            coverage["compatibility_coverage_core_count"]
            + coverage["pending_compatibility_core_count"],
        )


if __name__ == "__main__":
    unittest.main()
