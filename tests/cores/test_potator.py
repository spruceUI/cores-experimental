"""Pinned Potator individual lifecycle and reproducibility tests."""

from __future__ import annotations

import copy
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from scripts.core_pipeline_lib.contracts import potator

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


CORE_ID = "potator"
OTHER_CORE_ID = "race"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
PIN_FILE_SHA256 = _H["PIN_FILE_SHA256"]
PIN_CONTENT_SHA256 = _H["PIN_CONTENT_SHA256"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
PACKAGE_SHA256 = _H["PACKAGE_SHA256"]
TARGETS = _H["TARGETS"]

GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"

SOURCE_URL = _H["SOURCE_URL"]

SOURCE_LOCK_PATH = _H["SOURCE_LOCK_PATH"]

SOURCE_LOCK_FILE_SHA256 = _H["SOURCE_LOCK_FILE_SHA256"]

SOURCE_LOCK_CONTENT_SHA256 = _H["SOURCE_LOCK_CONTENT_SHA256"]

SOURCE_SET_CONTENT_SHA256 = _H["SOURCE_SET_CONTENT_SHA256"]

GOLDEN_FILE_SHA256 = (
    "2053d57aa38f1e52a8d63f4e775bcc3f5037a70105252145b4b288d74804d896"
)

GOLDEN_CONTENT_SHA256 = (
    "98a6cfb53cf36a46bbdee6a5ca2ef24714c74c255ac6870a41183e789b97c318"
)

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
    "8-command C-only native-version compile",
    "1.0.5  227c5f6",
    "four reviewed -Wmisleading-indentation warning/note pairs",
    "CPU-behavior runtime debt",
    "Public Domain",
    "Publication remains disabled",
    "No external firmware is declared, required, or packaged",
    "content loading",
    "controls",
    "palettes",
    "ghosting and frameskip",
    "audio/video pacing",
    "state save/load round trips",
    "reset and unload behavior",
    "sustained performance",
    "GLIBC_2.4",
    "provisional",
    "every device view remains ineligible",
)

class PotatorLifecycleTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)


    def test_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertTrue(source_set["local_only"])
        self.assertEqual("disabled", source_set["publication"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertEqual(
            PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"]
        )
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
        source_lock = registry.composed_source_lock(CORE_ID)
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(SOURCE_LOCK_IDENTITY, source_lock["source"])
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
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                cell = cells[architecture]
                self.assertEqual(CORE_ID, cell["core_id"])
                self.assertEqual(SOURCE_LOCK_ID, cell["source_lock_id"])
                self.assertEqual(expected["artifact_sha256"], cell["artifact_sha256"])
                self.assertEqual(
                    expected["execution_profile_id"], cell["execution_profile_id"]
                )
                self.assertEqual("static-build-only", cell["validation_scope"])
                self.assertEqual("provisional-unverified", cell["device_eligibility"])
        self.assertTrue(report["device_views"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                and view["eligibility"] == "provisional-unverified"
                for view in report["device_views"]
            )
        )

    def test_channels_and_release_target_one_semantic_core(self) -> None:
        target_paths = {
            "nightly": GOLDEN_PATH,
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT / ".local-e2e/channels" / f"{channel}.{CORE_ID}.json"
                )
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertTrue(pointer["local_only"])
                self.assertEqual("disabled", pointer["publication"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", target_path.casefold())
                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])

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
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual("disabled", release["publication"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])


    def test_lifecycle_mutations_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        mutations = {
            "digest": copy.deepcopy(compatibility),
            "publication": copy.deepcopy(compatibility),
            "runtime": copy.deepcopy(compatibility),
            "artifact": copy.deepcopy(compatibility),
            "glibc_floor": copy.deepcopy(compatibility),
            "run_identity": copy.deepcopy(compatibility),
        }
        mutations["digest"]["content_sha256"] = "0" * 64
        mutations["publication"]["publication"] = "enabled"
        mutations["runtime"]["targets"]["arm64"]["runtime_validation"] = "passed"
        mutations["artifact"]["targets"]["arm64"]["artifact_sha256"] = "0" * 64
        mutations["glibc_floor"]["targets"]["armhf"]["version_requirements"] = [
            "GLIBC_2.4",
            "GLIBC_2.7",
        ]
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

        source_set = registry.composed_source_set(SEMANTIC_ID)
        bad_digest = copy.deepcopy(source_set)
        bad_digest["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            registry.RegistryError,
            "source set.content_sha256 does not cover current content",
        ):
            registry.validate_source_set(bad_digest, verify_files=False)

        wrong_commit = copy.deepcopy(source_set)
        wrong_commit["sources"][CORE_ID]["commit"] = "0" * 40
        wrong_commit["content_sha256"] = registry.canonical_content_sha256(
            wrong_commit
        )
        with self.assertRaisesRegex(
            registry.RegistryError,
            "source set reference path does not bind potator",
        ):
            registry.validate_source_set(wrong_commit, verify_files=False)

        log_path = (
            ROOT / ".local-e2e/runs" / REPRODUCTION_RUN / CORE_ID / "arm64/build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        proof_mutations = {
            "native_version": log_text.replace(
                r'-DGIT_VERSION=\"" 227c5f6"\"',
                r'-DGIT_VERSION=\"" 0000000"\"',
                1,
            ),
            "link": log_text.replace(
                "-Wl,--no-undefined", "-Wl,--allow-shlib-undefined", 1
            ),
        }
        for label, mutated_log in proof_mutations.items():
            with self.subTest(proof_mutation=label):
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(
                        mutated_log,
                        CORE_ID,
                        "arm64",
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
                )

    def test_reproduction_rejects_recomputed_log_tampering(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-potator-log-",
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
            self.assertTrue(
                any(
                    f"{CORE_ID}/arm64" in error
                    and (
                        "historical build differs" in error
                        or "build log" in error
                    )
                    for error in report["errors"]
                ),
                report["errors"],
            )

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        self.assertTrue(potator.potator_spec_is_well_formed(catalog["cores"][CORE_ID]))
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/potator.json").exists()
        )
        coverage = pipeline.load_catalog_compatibility_coverage(
            catalog=catalog,
            repository_root=ROOT,
        )
        self.assertNotIn(CORE_ID, coverage["pending_compatibility_cores"])
        self.assertEqual(
            len(catalog["cores"]),
            coverage["compatibility_coverage_core_count"]
            + coverage["pending_compatibility_core_count"],
        )


if __name__ == "__main__":
    unittest.main()
