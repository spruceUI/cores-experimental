"""Pinned Mednafen SuperGrafx individual lifecycle tests."""

from __future__ import annotations

from collections import Counter
import copy
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import mednafen_supergrafx

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "mednafen_supergrafx"
OTHER_CORE_ID = "mednafen_pce_fast"
PIN_NAME = "mednafen_supergrafx-3c6fcd3deded-6f92f2753900.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"
SOURCE_COMMIT = "3c6fcd3deded54ebecd69408f108407ac03d11b5"
SOURCE_TREE = "076a59d1084ebf3a6ab80f4b5a144fa865c46c9b"
SOURCE_URL = "https://github.com/libretro/beetle-supergrafx-libretro.git"
SOURCE_LOCK_ID = "mednafen_supergrafx-3c6fcd3deded"
SOURCE_LOCK_PATH = (
    "pins/sources/mednafen_supergrafx/"
    "3c6fcd3deded54ebecd69408f108407ac03d11b5.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "b6ef62e973aa4e57c3726433300e04160e7415fec5d84ddec6ffaec939e276c1"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "4a724044ccf00caf150dc543eda18677a0da01b4727b0e67b1027c614d67290a"
)
SOURCE_SET_CONTENT_SHA256 = (
    "90651332f5c5b49d49288ac0c65945f90bde250ec2083fe8eae861081a499a8e"
)
PIN_FILE_SHA256 = (
    "2be42731227719897faf4ad829831bba1010c834605fb70b9a228e1efe091c15"
)
PIN_CONTENT_SHA256 = (
    "a55af5945b63a2226160a56a4993a8a54572f0ad7941e1e9197576893ba266a2"
)
GOLDEN_FILE_SHA256 = (
    "39a38b6e8005ccf3968654d8aaa18a24b5ba3128ca415872ac6cb194ee6aa7d0"
)
GOLDEN_CONTENT_SHA256 = (
    "76657ad31a6eaeaf81649fa1ad08f5e1b83a02583eed9c319a46606c28abf76c"
)
SELECTION_SHA256 = (
    "6f92f2753900aad1d159c7389e5a6d1864a5ebd4b86c147a08cde29f2769e96e"
)
SELECTED_RUN = "actions-sim-build-core-mednafen_supergrafx-v1"
REPRODUCTION_RUN = "build-core-mednafen_supergrafx-local-v1"
SELECTED_E2E_CONTENT_SHA256 = (
    "8aafb99b8638afb3b9d0c13bdfa783d4e240d9549cd67ef42305423a174fe905"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "9888372cdb76c3ba75ffda508cfd71fdb3623577224e0925a3c6e62ac6cd7841"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "147da6e4e712b0b4b1a438a7f11b1258b2ec280bc4e5dcf712919861281f8c37"
    ),
    REPRODUCTION_RUN: (
        "05d55a7ed5b985f809ab883c0aeeb43042a468a390857539675cf971a82b18dc"
    ),
}
PACKAGE_SHA256 = (
    "88239b36f536da972806db127ead1d4fa6bfedaf258b3dbd5d374ca78d137a1a"
)
PACKAGE_SIZE = 1011218
METADATA_SHA256 = (
    "ab7f73bbfe0f8c94413f1db6981ec51c82f772f8278cd4564c839124c2a3411c"
)
METADATA_SIZE = 1921
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
            "c4d55157ab1bf2fff095348e6f821ba4e5d5219f005fe7ec550556bb7804c164"
        ),
        "artifact_size": 3763168,
        "record_sha256": {
            SELECTED_RUN: (
                "6c49ab7417362162e16a2a9d2696b821a249f6ba1f647a0488cdcc18d3e28b97"
            ),
            REPRODUCTION_RUN: (
                "fb51bad5d7494556d7ee68e7519dfa9e5e8d3cc986bfaec570a793963a3774cb"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "d0f1ab98d8de1051f97ea3286ba1a293253998268e4454ec709ef6576270c6c9"
            ),
            REPRODUCTION_RUN: (
                "d0f1ab98d8de1051f97ea3286ba1a293253998268e4454ec709ef6576270c6c9"
            ),
        },
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.9",
            "GCC_3.0",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBC_2.17",
            "GLIBC_2.27",
        ],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "2536584094622656915bd3fc684fcf7b2f911f17f0e56a87184ae962b41ed6ca"
        ),
        "artifact_size": 2166576,
        "record_sha256": {
            SELECTED_RUN: (
                "d156a11dec2324e326d6b93a736fd2b310841cb0726abd0ad001d019a64fbd80"
            ),
            REPRODUCTION_RUN: (
                "73b184246c34283705fa71985303d49179e36eebbcb2fc18529c5b21dcb26754"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "2e5b8e835fb692b0995a0dd8db0eee77762671fbafcca39b0131cdd097cdd1eb"
            ),
            REPRODUCTION_RUN: (
                "5d23e64cdc93d5df9424412ede933d1faee497039c579f8ed1e25a840764cee0"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": [
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "librt.so.1",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.9",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBC_2.4",
            "GLIBC_2.7",
        ],
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
    "raw build logs differ only through valid parallel diagnostic ordering",
    "89 compiles comprise 60 C and 29 C++ commands",
    "C++ compilation",
    "v1.29.0 3c6fcd3",
    "exactly two reviewed warnings and no notes",
    "exactly seven reviewed warnings and five reviewed notes",
    "dangling-pointer warning",
    "three free-nonheap-object warnings",
    "GPLv2",
    "display version v1.23.0",
    "pce|sgx|cue|ccd|chd",
    "No firmware or BIOS is packaged",
    "syscard3.pce",
    "38179df8f4ac870017db21ebcbf53114",
    "ra64-universal-v1",
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


class MednafenSupergrafxLifecycleTests(unittest.TestCase):
    def test_catalog_pin_and_compatibility_bind_promoted_evidence(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][CORE_ID]
        self.assertTrue(
            mednafen_supergrafx.mednafen_supergrafx_spec_is_well_formed(spec)
        )
        self.assertEqual("libretro-super", spec["build"]["driver"])
        self.assertEqual(
            {
                "derivation": "native-space-short7-v1",
                "value": " 3c6fcd3",
                "compiler_scope": "cxx",
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
            "valid",
            compatibility_report["status"],
            compatibility_report["errors"],
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
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual(expected["elf"], target["elf"])
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
                self.assertEqual(
                    {
                        "compiler_scope": "cxx",
                        "derivation": "native-space-short7-v1",
                        "value": " 3c6fcd3",
                    },
                    golden_record["build"]["git_version"],
                )
                self.assertEqual(
                    METADATA_SHA256, golden_record["metadata"]["sha256"]
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
            load_document(ROOT / "manifests/core-builds.json")["cores"]
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
                self.assertEqual(
                    expected["artifact_sha256"], cell["artifact_sha256"]
                )
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

    def test_selected_and_reproduction_runs_prove_parallel_builds(self) -> None:
        contract = mednafen_supergrafx.mednafen_supergrafx_mixed_language_contract()
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual(
            "mednafen-supergrafx-mixed-language-v1",
            registered_contract.contract_id,
        )
        self.assertEqual(
            "mednafen_supergrafx_log_proves_contract",
            registered_contract.proof_name,
        )
        self.assertEqual(89, contract.expected_compile_count)
        self.assertEqual(
            {"c": 60, "cxx": 29}, dict(contract.expected_language_counts)
        )
        self.assertEqual(
            mednafen_supergrafx.MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_PAIR_SHA256,
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            mednafen_supergrafx.MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OBJECT_SHA256,
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            mednafen_supergrafx.MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OPTIONS,
            contract.expected_link_options,
        )

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
                    names = set(archive.namelist())
                    self.assertEqual(
                        {
                            "cores64/mednafen_supergrafx_libretro.so",
                            "cores/mednafen_supergrafx_libretro.so",
                            "mednafen_supergrafx_libretro.info",
                            "manifest.json",
                        },
                        names,
                    )
                    self.assertFalse(
                        any(
                            name.casefold().endswith(".pce")
                            or "syscard" in name.casefold()
                            for name in names
                        )
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
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual("libretro-super", record["build"]["driver"])
                        self.assertEqual(
                            "sanitized-v1", record["build"]["environment"]
                        )
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertEqual(
                            {
                                "compiler_scope": "cxx",
                                "derivation": "native-space-short7-v1",
                                "value": " 3c6fcd3",
                            },
                            record["build"]["git_version"],
                        )

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(
                            expected["log_sha256"][run_id], file_sha256(log_path)
                        )
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
                            29,
                            log_text.count(r'-DGIT_VERSION=\"" 3c6fcd3"\"'),
                        )
                        lowered_log = log_text.casefold()
                        for marker in FAILURE_MARKERS:
                            self.assertNotIn(marker, lowered_log)

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "v1.23.0"', metadata)
                        self.assertIn(b'license = "GPLv2"', metadata)
                        self.assertIn(
                            b'supported_extensions = "pce|sgx|cue|ccd|chd"',
                            metadata,
                        )
                        self.assertIn(b'supports_no_game = "false"', metadata)
                        self.assertIn(b'needs_fullpath = "true"', metadata)
                        self.assertIn(b'disk_control = "true"', metadata)
                        self.assertIn(b'savestate_features = "deterministic"', metadata)
                        self.assertIn(b'libretro_saves = "true"', metadata)
                        self.assertIn(b'core_options = "true"', metadata)
                        self.assertIn(b'firmware_count = 4', metadata)
                        self.assertIn(b'firmware0_path = "syscard3.pce"', metadata)
                        self.assertIn(b'firmware3_path = "gexpress.pce"', metadata)
                        self.assertEqual(4, metadata.count(b'_opt = "true"'))
                        self.assertIn(
                            b'38179df8f4ac870017db21ebcbf53114', metadata
                        )
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"v1.29.0 3c6fcd3", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                # The pinned per-run log hashes state whether the independent
                # runs reproduced the log byte for byte or merely reordered
                # complete lines under parallel make; hold the bytes to it.
                pinned = TARGETS[architecture]["log_sha256"]
                if pinned[SELECTED_RUN] == pinned[REPRODUCTION_RUN]:
                    self.assertEqual(logs[architecture][0], logs[architecture][1])
                else:
                    self.assertNotEqual(logs[architecture][0], logs[architecture][1])
                self.assertEqual(
                    Counter(logs[architecture][0].splitlines()),
                    Counter(logs[architecture][1].splitlines()),
                )

    def test_lifecycle_mutations_fail_closed(self) -> None:
        _, pin, compatibility_path, compatibility = load_core_documents(
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
        mutations["glibc_floor"]["targets"]["arm64"]["version_requirements"] = [
            item
            for item in TARGETS["arm64"]["version_requirements"]
            if item != "GLIBC_2.27"
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

        bad_pin = copy.deepcopy(pin)
        bad_pin["content_sha256"] = "0" * 64
        bad_pin_report = pipeline.validate_pin_set_document(bad_pin)
        self.assertEqual("invalid", bad_pin_report["status"])

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
            "source set reference path does not bind mednafen_supergrafx",
        ):
            registry.validate_source_set(wrong_commit, verify_files=False)

        log_path = (
            ROOT / ".local-e2e/runs" / REPRODUCTION_RUN / CORE_ID / "arm64/build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        proof_mutations = {
            "native_version": log_text.replace(
                r'-DGIT_VERSION=\"" 3c6fcd3"\"',
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
            prefix="compat-tamper-supergrafx-log-",
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
            self.assertEqual("invalid", report["status"])
            self.assertIn(
                "individual core reproduction E2E validation failed: "
                f"{CORE_ID}/arm64 compatibility build: historical build differs",
                report["errors"],
            )

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(
            mednafen_supergrafx.mednafen_supergrafx_spec_is_well_formed(
                catalog["cores"][CORE_ID]
            )
        )
        pending_path = ROOT / "manifests/compatibility/pending" / f"{CORE_ID}.json"
        self.assertFalse(pending_path.exists())
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
