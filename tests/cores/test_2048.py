"""2048 individual lifecycle and reproducibility tests."""

from __future__ import annotations

import copy
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import core_2048

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "2048"
OTHER_CORE_ID = "a5200"
PIN_NAME = "2048-c90437d3c391-e1ff15dd7d6a.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "c90437d3c3913999624deca3fb55ecfa632b72c4"
SOURCE_TREE = "5b8bcab69dc90185f10356b5780bf9d827684474"
SOURCE_LOCK_ID = "2048-c90437d3c391"
SELECTION_SHA256 = (
    "e1ff15dd7d6a80b1a493dc5f0ae0b101371cb7caee262a4a4d0c59b81b241c45"
)
SELECTED_RUN = "actions-sim-build-core-2048-w3"
REPRODUCTION_RUN = "build-core-2048-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "d5d4f5399fe3d0b08429683aace99d6fb24ed229127a04d3360a1f414114b40e"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "f4abc542d2568eb0cc34a6d351a9ee45fb287326e7e863d3251ea54358acb445"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "61707b5be5f44a77bb8f8efa8471e455722cd2369079e067edcba1e5996ff983"
    ),
    REPRODUCTION_RUN: (
        "c102bb68db2322a96b31aa4fed131d5bbe4501b7b197f8dfd7b18573cd606bf9"
    ),
}
PACKAGE_SHA256 = (
    "ac17f00e57b0a0ba2f7078257aad956f186f3e5b4cba0e5fcbc2f85c9b1285f6"
)
METADATA_SHA256 = (
    "ef884f20a92289f262a5be747f1468637f9168efc65154843836c23effd51a79"
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
            "0d68255bed61ad493f42c37c039bdcefec82ea20b8eb75c9f0b5260fa21e4ca9"
        ),
        "artifact_size": 88832,
        "record_sha256": {
            SELECTED_RUN: (
                "ae26db4ee6804d652e69767f54ad6081e4e412925c2ad02b81699ed99fa207fd"
            ),
            REPRODUCTION_RUN: (
                "29f831ee4f68a96905d20a62b5119d2e0abe7ebdae35e1c1bc03b71155af633b"
            ),
        },
        "log_sha256": (
            "82fc666bf2439dc36f64ad6024eab41059f7b2e3d64151ec982b1315a88b4790"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "dfa66f938682ea7b36183568ed2890865cc9062d1d0c3ac6c8948aeb4df215e8"
        ),
        "artifact_size": 80492,
        "record_sha256": {
            SELECTED_RUN: (
                "7c70af7e6ddfcdc54c61bdf865f64fc7b575a752e017ef6c6c726d4580b6c19b"
            ),
            REPRODUCTION_RUN: (
                "6a829a452bb007e6def121afe1e142a389f30d3758703283b3f5ccd8d74352d3"
            ),
        },
        "log_sha256": (
            "92c449b687b07e4032902e37d99943050270b12909b5e440fb941f9095c5b3fe"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
    },
}
CAVEAT_TOKENS = (
    "16-source C-only compile",
    "eight commits newer",
    "Unlicense/Public Domain",
    "libretro_saves=false",
    "RETRO_MEMORY_SAVE_RAM",
    "expected silence/no-audio initialization behavior",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)


class Core2048LifecycleTests(unittest.TestCase):
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
            "valid", compatibility_report["status"], compatibility_report["errors"]
        )

        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertIsNone(pin["parent"])
        self.assertEqual(PIN_PATH, compatibility["golden_source"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(
            f".local-e2e/runs/{SELECTED_RUN}/e2e-record.json",
            compatibility["e2e_run"],
        )
        self.assertEqual(
            f".local-e2e/runs/{REPRODUCTION_RUN}/e2e-record.json",
            compatibility["reproduction_run"],
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
            compatibility["reproduction_e2e_content_sha256"],
        )
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden_record = selected_target["golden_record"]
                artifact = golden_record["artifact"]
                self.assertEqual(SOURCE_COMMIT, golden_record["source"]["commit"])
                self.assertEqual(SOURCE_TREE, golden_record["source"]["tree"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(
                    {
                        "compiler_scope": "c",
                        "derivation": "native-space-short7-v1",
                        "value": " c90437d",
                    },
                    golden_record["build"]["git_version"],
                )
                snapshot_ref = golden_record["local_store"]["recipe_snapshots"][
                    architecture
                ]
                snapshot_path = ROOT / snapshot_ref["path"]
                self.assertEqual(9, load_document(snapshot_path)["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        golden_record,
                        f"{CORE_ID}/{architecture}",
                    ),
                )

    def test_source_set_maps_shared_profiles_without_device_claims(self) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests/core-builds.json")["cores"]
        )

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
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
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_channels_and_release_target_one_semantic_core(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
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
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
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
        self.assertEqual(
            "valid", release_report["status"], release_report["errors"]
        )
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

    def test_selected_and_reproduction_runs_are_byte_identical(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts = {architecture: [] for architecture in TARGETS}
        logs = {architecture: [] for architecture in TARGETS}
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                run_root = ROOT / ".local-e2e/runs" / run_id
                evidence_path = run_root / "e2e-record.json"
                evidence = load_document(evidence_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    SELECTED_E2E_CONTENT_SHA256
                    if run_id == SELECTED_RUN
                    else REPRODUCTION_E2E_CONTENT_SHA256,
                    evidence["content_sha256"],
                )
                package_path = run_root / evidence["packages"][0]["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/2048_libretro.so",
                            "cores/2048_libretro.so",
                            "2048_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )

                for architecture, expected in TARGETS.items():
                    record_path = run_root / CORE_ID / architecture / "build-record.json"
                    record = load_document(record_path)
                    self.assertEqual(
                        expected["record_sha256"][run_id], file_sha256(record_path)
                    )
                    self.assertEqual(SOURCE_COMMIT, record["source"]["commit"])
                    self.assertEqual(SOURCE_TREE, record["source"]["tree"])
                    log_path = record_path.parent / record["build"]["log"]
                    log_text = log_path.read_text(encoding="utf-8")
                    self.assertEqual(expected["log_sha256"], file_sha256(log_path))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(
                            log_text,
                            CORE_ID,
                            architecture,
                            SOURCE_COMMIT,
                            SOURCE_TREE,
                        )
                    )
                    logs[architecture].append(log_path.read_bytes())
                    artifact_path = record_path.parent / record["artifact"]["path"]
                    self.assertEqual(
                        expected["artifact_sha256"], file_sha256(artifact_path)
                    )
                    artifacts[architecture].append(artifact_path.read_bytes())
                    metadata_path = record_path.parent / record["metadata"]["path"]
                    self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                    metadata_payloads.append(metadata_path.read_bytes())
                    metadata = metadata_path.read_text(encoding="utf-8")
                    self.assertIn('savestate = "true"', metadata)
                    self.assertIn('libretro_saves = "false"', metadata)
                    self.assertIn('supports_no_game = "true"', metadata)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
            self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_compatibility_and_registered_proof_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
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

        changed_artifact = copy.deepcopy(compatibility)
        changed_artifact["targets"]["arm64"]["artifact_sha256"] = "0" * 64
        changed_artifact["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(changed_artifact)
        )
        changed_report = pipeline.validate_core_compatibility_document(
            changed_artifact,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", changed_report["status"])

        log_path = (
            ROOT / ".local-e2e/runs" / REPRODUCTION_RUN / CORE_ID / "arm64/build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        self.assertFalse(
            pipeline.registered_core_log_contract_proves(
                log_text.replace("-Wl,--no-undefined", "-Wl,--version-script=link.T", 1),
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(
            core_2048.core_2048_spec_is_well_formed(catalog["cores"][CORE_ID])
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/2048.json").exists()
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
