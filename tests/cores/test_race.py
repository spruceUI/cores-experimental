"""Pinned RACE individual lifecycle and reproducibility tests."""

from __future__ import annotations

import copy
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import race

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "race"
OTHER_CORE_ID = "mednafen_ngp"
PIN_NAME = "race-c7810dd7f172-c3119de987bf.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"
SOURCE_COMMIT = "c7810dd7f172827bfa2004813bc000b13786636b"
SOURCE_TREE = "344c09b682f79f2135479bdd0a76d193edfdf167"
SOURCE_URL = "https://github.com/libretro/RACE.git"
SOURCE_LOCK_ID = "race-c7810dd7f172"
SOURCE_LOCK_PATH = (
    "pins/sources/race/c7810dd7f172827bfa2004813bc000b13786636b.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "5a4aedc4caf38b4b4c892e4f10381999b5a042fd362f3905b06c4464cc435a8e"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "74a7f1333b4c95fc1a0045b2ae1f395e8000836e3b6738cbdc1c79b54ed6d7a7"
)
SOURCE_SET_CONTENT_SHA256 = (
    "3cc69104aecacea4d1d63a87402de49e62e0d4c5e014bc845364e1225c5105a1"
)
PIN_FILE_SHA256 = (
    "0635c1ac459778d63166de7168becd99d266320b5875fc0bbf482529c8750686"
)
PIN_CONTENT_SHA256 = (
    "5c75517313ed35fed650cd7e281469606d276d061b40edc821143995cb9152df"
)
GOLDEN_FILE_SHA256 = (
    "f01f130512c37d4de1dcad974bb25e7c49f65b58f33b37b57ff95bc92e929461"
)
GOLDEN_CONTENT_SHA256 = (
    "1045c956505df0028a5568810a799e1d0b8372716e155ee936c28944a9dee3d0"
)
SELECTION_SHA256 = (
    "c3119de987bfb2680c15add1a63a9a3d362af6a9684072c7bec52f6fd5650c9a"
)
SELECTED_RUN = "actions-sim-build-core-race-v1"
REPRODUCTION_RUN = "build-core-race-local-v1"
SELECTED_E2E_CONTENT_SHA256 = (
    "89b3097a73ed5c022b3e98b40d8e288b98deecef29ce4d164ef83421cd8b92dc"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "153ef3b8e76f83a3fe475d6d8a1be088349fb546a0020df6ae3b41f14cd2ebd6"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "9efd36fc7441dfcc36213544a3be199c3f68bd829db586546fdea23f9f1428bf"
    ),
    REPRODUCTION_RUN: (
        "4b2d1df9c15c7cb5dd24b45eda06c0f227b13dce12660880d6861b6bfe98fdc6"
    ),
}
PACKAGE_SHA256 = (
    "7abb3e87ff59d6dac1fe0a74d442bf1b0b6cf2f189f24ea307dd8731d6483b1e"
)
PACKAGE_SIZE = 242146
METADATA_SHA256 = (
    "41e1bc89e77d30ea387af20997364cee068f936399b4ea2aa192c5d4afd12453"
)
METADATA_SIZE = 1074
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
            "67c432adb1c0baf1fdbaceb4851cd3f11545cbc51267f5441fbff5073ea9261c"
        ),
        "artifact_size": 445288,
        "record_sha256": {
            SELECTED_RUN: (
                "1bdf79eae7394511652b1931d9c508fafe6cf57d98194f3516e55f3219d00e93"
            ),
            REPRODUCTION_RUN: (
                "ffd90311f3eabb3d92df610207b5d2c4ee1fcb3335f7cb3cf7c24d30cc9cf888"
            ),
        },
        "log_sha256": (
            "6ca3dcd77386e223496b370e56637184c897116ff800a4f1800cc24698343fec"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "1a337bc84387c054d5c7e2e1027ee8129884ad0ef497c9ac16b7e95e66600f74"
        ),
        "artifact_size": 324460,
        "record_sha256": {
            SELECTED_RUN: (
                "2467c216bbdd8e6df30d10ffd3cddcb20668e8db264d8bec1f3a004f1d7e8267"
            ),
            REPRODUCTION_RUN: (
                "ec9d8c6cfc5f5a77de98bddaa5f2a6d2486e1fdb8fa2685bd91b06844279a076"
            ),
        },
        "log_sha256": (
            "099a986c57b9ac02a61496eb6f838037119207a6f9df9acd47116b355e7143ef"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
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
    "27-command C-only native-version compile",
    "v2.16 c7810dd",
    "no warnings, notes, errors, or fatal diagnostics",
    "GPLv2",
    "Publication remains disabled",
    "ngpBios.c is compiled internal source",
    "not an external firmware blob",
    "reset",
    "core options",
    "unaligned-access behavior",
    "GLIBC_2.7",
    "provisional",
    "every device view remains ineligible",
)


class RaceLifecycleTests(unittest.TestCase):
    def test_catalog_and_semantic_pin_bind_promoted_evidence(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][CORE_ID]
        self.assertTrue(race.race_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(spec, CORE_ID)
        )
        self.assertEqual("libretro-super", spec["build"]["driver"])
        self.assertEqual(
            {
                "derivation": "native-space-short7-v1",
                "value": " c7810dd",
                "compiler_scope": "c",
            },
            pipeline.validated_git_version(spec),
        )

        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        pin_report = pipeline.validate_pin_set_document(pin, document_path=pin_path)
        self.assertEqual("valid", pin_report["status"], pin_report["errors"])
        compatibility_report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual(
            "valid", compatibility_report["status"], compatibility_report["errors"]
        )

        self.assertEqual(PIN_FILE_SHA256, file_sha256(pin_path))
        self.assertEqual(PIN_CONTENT_SHA256, pin["content_sha256"])
        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertIsNone(pin["parent"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])

        self.assertEqual(1, len(pin["sources"]))
        golden_reference = pin["sources"][0]
        self.assertEqual(GOLDEN_PATH, golden_reference["path"])
        self.assertEqual(SEMANTIC_ID, golden_reference["pin_id"])
        self.assertEqual(GOLDEN_FILE_SHA256, golden_reference["file_sha256"])
        self.assertEqual(
            GOLDEN_CONTENT_SHA256, golden_reference["content_sha256"]
        )
        golden_path = ROOT / GOLDEN_PATH
        golden = load_document(golden_path)
        self.assertEqual(GOLDEN_FILE_SHA256, file_sha256(golden_path))
        self.assertEqual(GOLDEN_CONTENT_SHA256, golden["content_sha256"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
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
                self.assertEqual(SOURCE_RECORD_IDENTITY, golden_record["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    {
                        "compiler_scope": "c",
                        "derivation": "native-space-short7-v1",
                        "value": " c7810dd",
                    },
                    golden_record["build"]["git_version"],
                )
                snapshot_reference = golden_record["local_store"][
                    "recipe_snapshots"
                ][architecture]
                snapshot_path = ROOT / snapshot_reference["path"]
                self.assertEqual(9, load_document(snapshot_path)["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        golden_record,
                        f"{CORE_ID}/{architecture}",
                    ),
                )

    def test_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
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
        source_lock = load_document(ROOT / source["path"])
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
                self.assertEqual(
                    "provisional-unverified", cell["device_eligibility"]
                )
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
        self.assertEqual(
            "valid", release_report["status"], release_report["errors"]
        )
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual("disabled", release["publication"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

    def test_selected_and_reproduction_runs_are_byte_identical(self) -> None:
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("race-c-only-v1", registered_contract.contract_id)
        self.assertEqual("race_log_proves_contract", registered_contract.proof_name)
        self.assertEqual(27, race.RACE_EXPECTED_COMPILE_COUNT)
        self.assertEqual(" c7810dd", race.RACE_NATIVE_GIT_VERSION)

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
                self.assertTrue(evidence["local_only"])
                self.assertEqual("disabled", evidence["publication"])
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
                self.assertEqual(PACKAGE_SIZE, package["size"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/race_libretro.so",
                            "cores/race_libretro.so",
                            "race_libretro.info",
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
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual("libretro-super", record["build"]["driver"])
                        self.assertEqual("sanitized-v1", record["build"]["environment"])
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertEqual(
                            {
                                "compiler_scope": "c",
                                "derivation": "native-space-short7-v1",
                                "value": " c7810dd",
                            },
                            record["build"]["git_version"],
                        )

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
                        self.assertEqual(
                            27,
                            log_text.count(r'-DGIT_VERSION=\"" c7810dd"\"'),
                        )
                        logs[architecture].append(log_path.read_bytes())

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "v2.16"', metadata)
                        self.assertIn(b'license = "GPLv2"', metadata)
                        self.assertIn(
                            b'supported_extensions = "ngp|ngc|ngpc|npc"', metadata
                        )
                        self.assertIn(b'supports_no_game = "false"', metadata)
                        self.assertIn(b'savestate = "true"', metadata)
                        self.assertIn(
                            b'savestate_features = "serialized"', metadata
                        )
                        self.assertIn(b'libretro_saves = "true"', metadata)
                        self.assertIn(b'needs_fullpath = "true"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"v2.16 c7810dd", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                self.assertEqual(logs[architecture][0], logs[architecture][1])

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
            "GLIBC_2.4"
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

        source_set = load_document(ROOT / SOURCE_SET_PATH)
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
            "source set reference path does not bind race",
        ):
            registry.validate_source_set(wrong_commit, verify_files=False)

        log_path = (
            ROOT / ".local-e2e/runs" / REPRODUCTION_RUN / CORE_ID / "arm64/build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        proof_mutations = {
            "native_version": log_text.replace(
                r'-DGIT_VERSION=\"" c7810dd"\"',
                r'-DGIT_VERSION=\"" 0000000"\"',
                1,
            ),
            "link": log_text.replace(
                "-Wl,-no-undefined", "-Wl,--allow-shlib-undefined", 1
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

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(race.race_spec_is_well_formed(catalog["cores"][CORE_ID]))
        self.assertFalse((ROOT / "manifests/compatibility/pending/race.json").exists())
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
