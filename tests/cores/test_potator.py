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


CORE_ID = "potator"
OTHER_CORE_ID = "race"
PIN_NAME = "potator-227c5f6f3ce7-66e2c96acf38.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"
SOURCE_COMMIT = "227c5f6f3ce74d32e9002ce24c1420288559a860"
SOURCE_TREE = "9111933525a4508075937f251829132cf2081ba9"
SOURCE_URL = "https://github.com/libretro/potator.git"
SOURCE_LOCK_ID = "potator-227c5f6f3ce7"
SOURCE_LOCK_PATH = (
    "pins/sources/potator/227c5f6f3ce74d32e9002ce24c1420288559a860.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "8044bbf6398ccefa73b2dc1c2b123b4e67c52ca185cb45b4641314cfdd949bd8"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "5fcaf01f34d511e0d37d086b8962d4a689ffad1be725f895a66c9137c5bb5086"
)
SOURCE_SET_CONTENT_SHA256 = (
    "18a3398d1a0d588346b02dea847f63abcde1c9076cb85b66f797fca8aff463d9"
)
PIN_FILE_SHA256 = (
    "3de10207e80a7e47004c87f5e5e980bc6f92c777a5343468ce06652d172cf5c5"
)
PIN_CONTENT_SHA256 = (
    "9d96c53565a74785be6392a091769dea1e9b04d23b6e8d3f6012c05f31144862"
)
GOLDEN_FILE_SHA256 = (
    "2053d57aa38f1e52a8d63f4e775bcc3f5037a70105252145b4b288d74804d896"
)
GOLDEN_CONTENT_SHA256 = (
    "98a6cfb53cf36a46bbdee6a5ca2ef24714c74c255ac6870a41183e789b97c318"
)
SELECTION_SHA256 = (
    "66e2c96acf382d506aabc8e708c2399998a2517f8fd8e55412814d97cce8c51a"
)
SELECTED_RUN = "actions-sim-build-core-potator-w3"
REPRODUCTION_RUN = "build-core-potator-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "6bb81226e712383a7df4e117a665412a68b56ebd9d91684e1bf89b11f7c208ea"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "feaceb99f3b7a3a5da89c37cb1f10a9077e78727a0ba922b50a98ec9d5b26d13"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "c726f9b225dcbebbccc860cec894a378fab93a1d534cb0c0642d69093a9df2f3"
    ),
    REPRODUCTION_RUN: (
        "759a4fc63fc52d1d2d1b07b2aa1fcdf8cef6c0d3ca5ffaa9c7861a2acbf0a348"
    ),
}
PACKAGE_SHA256 = (
    "601a7088532366868584baebb23b28b6ecaf60a60947badb4408bb813527911c"
)
PACKAGE_SIZE = 46578
METADATA_SHA256 = (
    "1e7155841e4dcdb7feef31018432d2e259cbfd2b349add6d4731165cee8ede1a"
)
METADATA_SIZE = 497
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
            "6fd73f2261490a358cb22e5f16be4b51c537b0fd5d0c5a703326bffb1868ea4f"
        ),
        "artifact_size": 72328,
        "record_sha256": {
            SELECTED_RUN: (
                "4a63966cb49e9e1114a45e30bbfddd04e72dbb3f295a83a7f8f724aad5062a9d"
            ),
            REPRODUCTION_RUN: (
                "6843d9dfb669aad2d7b108b35d4b2a45fff10e7330768e05cf9650f4e81c4d31"
            ),
        },
        "log_sha256": (
            "eff8f2038fbc0796f292e1c1e855aabdd7fe598784ce1f68f02de154524ba7d7"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "453d625fa5821723e89a54decf22c61bc44edde8287e2f364e58c2df69d7c689"
        ),
        "artifact_size": 57560,
        "record_sha256": {
            SELECTED_RUN: (
                "ef43784bd46b3514a0673d2e5954bddf15303363366d4ec14658839ad4318513"
            ),
            REPRODUCTION_RUN: (
                "5f3143f38b9f3529860125ae84e31a5b527a2b479a3f481c68ff9988d9394ea3"
            ),
        },
        "log_sha256": (
            "8e899e1ed9f5db878d650d0c4bd044af7b3c162f38d53f028a9b14adc3d43da7"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6"],
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
    def test_catalog_and_semantic_pin_bind_promoted_evidence(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][CORE_ID]
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            spec["source"],
        )
        self.assertTrue(potator.potator_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(spec, CORE_ID)
        )
        self.assertEqual(
            potator.POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[CORE_ID],
        )
        self.assertEqual("libretro-super", spec["build"]["driver"])
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
        self.assertNotIn("make_variables", spec["build"])
        self.assertEqual(
            {
                "derivation": "native-space-short7-v1",
                "value": " 227c5f6",
                "compiler_scope": "c",
            },
            pipeline.validated_git_version(spec),
        )
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" 227c5f6"|file'],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual([], pipeline.compile_definitions_for_target(spec, "arm64"))
        self.assertEqual([], pipeline.compile_definitions_for_target(spec, "armhf"))
        self.assertIsNone(pipeline.validated_source_date_epoch(spec))

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
        self.assertEqual(CORE_ID, compatibility["core_id"])
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
        self.assertEqual(GOLDEN_CONTENT_SHA256, golden_reference["content_sha256"])
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
        self.assertEqual(PACKAGE_SHA256, selection["e2e"]["package_sha256"])
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
                        "value": " 227c5f6",
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

    def test_selected_and_reproduction_runs_are_byte_identical(self) -> None:
        contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("potator-c-only-v1", contract.contract_id)
        self.assertEqual("potator_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual(8, potator.POTATOR_EXPECTED_COMPILE_COUNT)
        self.assertEqual(" 227c5f6", potator.POTATOR_NATIVE_GIT_VERSION)

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
                            "cores64/potator_libretro.so",
                            "cores/potator_libretro.so",
                            "potator_libretro.info",
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
                        self.assertEqual(build["record_sha256"], file_sha256(record_path))
                        record = load_document(record_path)
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual("libretro-super", record["build"]["driver"])
                        self.assertEqual("sanitized-v1", record["build"]["environment"])
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertEqual(
                            {
                                "compiler_scope": "c",
                                "derivation": "native-space-short7-v1",
                                "value": " 227c5f6",
                            },
                            record["build"]["git_version"],
                        )

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(expected["log_sha256"], file_sha256(log_path))
                        logs[architecture].append(log_bytes)
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
                            8,
                            log_text.count(r'-DGIT_VERSION=\"" 227c5f6"\"'),
                        )

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                        metadata = metadata_path.read_bytes()
                        self.assertIn(
                            b'display_name = "Watara - Supervision (Potator)"',
                            metadata,
                        )
                        self.assertIn(b'supported_extensions = "bin|sv"', metadata)
                        self.assertIn(b'license = "Public Domain"', metadata)
                        self.assertIn(b'display_version = "1.0.5"', metadata)
                        self.assertIn(b'supports_no_game = "false"', metadata)
                        self.assertIn(b'savestate = "true"', metadata)
                        self.assertIn(
                            b'savestate_features = "deterministic"', metadata
                        )
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"1.0.5  227c5f6", artifact)
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
