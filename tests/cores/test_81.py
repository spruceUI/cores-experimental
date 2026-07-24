"""EightyOne individual lifecycle and reproducibility tests."""

from __future__ import annotations

from collections import Counter
import copy
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import core_81

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "81"
OTHER_CORE_ID = "a5200"
PIN_NAME = "81-fa7094910d04-a82f6eb4a7cc.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "fa7094910d040baa5fd8b11dbf6a1a618330ecd9"
SOURCE_TREE = "d73d124d16714e946ba9490627a4fc38c2aea37a"
SOURCE_LOCK_ID = "81-fa7094910d04"
SELECTION_SHA256 = (
    "a82f6eb4a7ccb563adcdf46fb2ba622edfc4131921793cd91cb8a3e9d7a297c5"
)
SELECTED_RUN = "actions-sim-build-core-81-v1"
REPRODUCTION_RUN = "build-core-81-local-v1"
SELECTED_E2E_CONTENT_SHA256 = (
    "e1ba2b87db03c9ce74fce4d463c3b665aada47529afcf5fb911eb0a3857328c8"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "e6fd26d5caa3ee1fd10cd345ea0ab9f3b91b53551fc0a96b04846b0bb36fb627"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "7feb7c36a36831d14216a8aab018fd7e89c08f9efaf90f8013eabd75ce074049"
    ),
    REPRODUCTION_RUN: (
        "32a81d531eec54901a369536b3d1730e516a760c6e4aa11a2e19ca0170aa6f88"
    ),
}
PACKAGE_SHA256 = (
    "f89b283137921ca1fa9ff7f127f367d85fecc91198457ce940d70668bcb8e53c"
)
METADATA_SHA256 = (
    "06036186b108b32901290288cde80b817a22f5a0cd0454da0ce520ad7ab647ec"
)
GENERATED_SOURCE_SHA256 = (
    "5a07d38a3bcd84ee5fa9abbdbe0bd706288d8ec4ee8095485447e35dc28a2862"
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
            "d0443666f01e7ab0d87727a233bf857e1a07775446421b448669e224885c189f"
        ),
        "artifact_size": 457552,
        "record_sha256": {
            SELECTED_RUN: (
                "b7f29c508fcc08e85887d74d62a13e1821a11c8d90faabd6ddd472333d2a6f78"
            ),
            REPRODUCTION_RUN: (
                "9f869408cc367e3f2b1a79d48283b299285c1409384f647bab0ef02dc6e2800e"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "d5ddfa9377fa83222047c0fa778d9116a99ee3f11619ac70079cad65ee43ae4f"
            ),
            REPRODUCTION_RUN: (
                "5830ef98a4fa94d6dd996fb78b19221d2a3822af0a141526c027ba5dc59d8f35"
            ),
        },
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBC_2.17",
        ],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "3b5efaeef6b2ddf3fc2aed5bf1eb9e2df0fecb3cd3408381014ba2a2c435079a"
        ),
        "artifact_size": 405672,
        "record_sha256": {
            SELECTED_RUN: (
                "22af7e6e6d5e52f00e1c77bac45be3a43c75fcf8a3755a866349f327e5af5fc6"
            ),
            REPRODUCTION_RUN: (
                "db0957b44c9f8fb3e124517931af2f34f18ebec5a3408a36864920df2def2f69"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "b601f8072829934cca9addd7be940e96d016de16e98c76cf2d771f6e6de7984b"
            ),
            REPRODUCTION_RUN: (
                "2cf09f463d07adea6b94c134d3547b68795918fbdb1e722bd659a58bffbdd452"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libgcc_s.so.1", "libm.so.6", "libstdc++.so.6"],
        "version_requirements": [
            "CXXABI_1.3.9",
            "CXXABI_ARM_1.3.3",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBC_2.4",
        ],
        "execution_profile_id": "ra32-a30-v1",
    },
}
CAVEAT_TOKENS = (
    "semantic at the log layer",
    "actions-sim-build-core-81-v1",
    "src/version.c",
    "39 reviewed warnings and 6 notes",
    "38 reviewed warnings and 11 notes",
    "unescaped inner quotes",
    "compiled zx81 and dkchr ROM headers",
    "GLIBCXX_3.4.20",
    "CXXABI_1.3.9",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "every device view remains ineligible",
)


class Core81LifecycleTests(unittest.TestCase):
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
                self.assertNotIn("git_version", golden_record["build"])
                self.assertEqual(
                    {
                        "kind": "post-build-sha256-v1",
                        "path": "src/version.c",
                        "sha256": GENERATED_SOURCE_SHA256,
                    },
                    golden_record["build"]["generated_source"],
                )
                snapshot_ref = golden_record["local_store"]["recipe_snapshots"][
                    architecture
                ]
                snapshot_path = ROOT / snapshot_ref["path"]
                self.assertEqual(10, load_document(snapshot_path)["schema_version"])
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

    def test_selected_and_reproduction_runs_match_releasable_bytes(self) -> None:
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
                            "cores64/81_libretro.so",
                            "cores/81_libretro.so",
                            "81_libretro.info",
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
                    self.assertEqual(
                        {
                            "kind": "post-build-sha256-v1",
                            "path": "src/version.c",
                            "sha256": GENERATED_SOURCE_SHA256,
                        },
                        record["build"]["generated_source"],
                    )
                    log_path = record_path.parent / record["build"]["log"]
                    log_text = log_path.read_text(encoding="utf-8")
                    self.assertEqual(
                        expected["log_sha256"][run_id], file_sha256(log_path)
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
                    logs[architecture].append(log_text)
                    artifact_path = record_path.parent / record["artifact"]["path"]
                    self.assertEqual(
                        expected["artifact_sha256"], file_sha256(artifact_path)
                    )
                    artifacts[architecture].append(artifact_path.read_bytes())
                    metadata_path = record_path.parent / record["metadata"]["path"]
                    self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                    metadata_payloads.append(metadata_path.read_bytes())
                    metadata = metadata_path.read_text(encoding="utf-8")
                    self.assertIn('display_version = "1.0a"', metadata)
                    self.assertIn('supported_extensions = "p|tzx|t81"', metadata)
                    self.assertIn('savestate = "true"', metadata)
                    self.assertIn('libretro_saves = "false"', metadata)
                    self.assertIn('supports_no_game = "false"', metadata)
                    self.assertIn('in the "p" and "tzx" formats', metadata)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
            self.assertNotEqual(logs[architecture][0], logs[architecture][1])
            self.assertEqual(
                Counter(logs[architecture][0].splitlines()),
                Counter(logs[architecture][1].splitlines()),
            )

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

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(core_81.core_81_spec_is_well_formed(catalog["cores"][CORE_ID]))
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/81.json").exists()
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
