"""Pinned VICE x64 individual lifecycle tests."""

from __future__ import annotations

import copy
from collections import Counter
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import vice_x64
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


CORE_ID = "vice_x64"
OTHER_CORE_ID = "gearcoleco"
PIN_NAME = "vice_x64-7946cfa0d377-1085a07760d4.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "7946cfa0d3775e958616d4d107de867a4616ae6c"
SOURCE_TREE = "db2760ffc97b9c20ef8777fcb7689082be66bc45"
SOURCE_URL = "https://github.com/libretro/vice-libretro.git"
SOURCE_LOCK_ID = "vice_x64-7946cfa0d377"
SOURCE_LOCK_FILE_SHA256 = (
    "28889e0d4f80bfb1e6efa082aa231ff8c8c355ef60f1b37caf8e7abfa326f399"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "d5d918cb679dfa3ea51a8efca2798cb6051d8fcf139d8519955a476a42d4841e"
)
SELECTION_SHA256 = (
    "1085a07760d4f425962a8f218d0c644bd505296acae17a8a86e5fb7150150219"
)
SELECTED_RUN = "actions-sim-build-core-vice_x64-w3"
REPRODUCTION_RUN = "build-core-vice_x64-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "c57bb46de4cfe6e41dc92ad319e6aa71c9603e55aa6f2fe4d6411f00e507c19c"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "31302d5bf1ee7eb9e9c9a04acad4d26b2a4e1ef17a90c89277ae55ed6f08dd5a"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "5c2084f40af1848d71a523ee2f1af760162431f99d65511c3340e9e68bf814f9"
    ),
    REPRODUCTION_RUN: (
        "c0dd1f8920348ad5adff3a0c4f962cc0361a2ede6efa7c78c8222b41b2cde1db"
    ),
}
PACKAGE_SHA256 = (
    "d414b84404b0fb940232df2955710e3a5b8b4dd5b7aff64968a58bb77d4cd076"
)
PACKAGE_SIZE = 2522811
METADATA_SHA256 = (
    "4051f9d21e2e22e8268b2c98cde07bfd942d71e135bf0ad455c3c12a7e1fdd23"
)
METADATA_SIZE = 2210
RECIPE_HEAD = "9d95cda3d6dce32c8d33d85a58f37adad19d38d7"
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
            "2ec9bd7e0d9cdf35b43ff5e672c998fee10a79119a151b3f5d5c42f0c2d45121"
        ),
        "artifact_size": 3580888,
        "record_sha256": {
            SELECTED_RUN: (
                "c87e49c43a669602b10f1c102d8a353998ae2eba2a2805f25a5ca2ebcfe9a194"
            ),
            REPRODUCTION_RUN: (
                "506d1ad753ffdc3f894d5c20b9f5ecf9551ec17f37674168c0abadcd5906ddda"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "040f766c5b686c55d286f0024a5855e60c737d119e0a92d6d1a396d62e0def32"
            ),
            REPRODUCTION_RUN: (
                "3beeca425d69c37506a4aa8e8503d11635df6426eb64c693ab9f63de333f3fba"
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
            "GCC_3.0",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.11",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.9",
            "GLIBC_2.17",
            "GLIBC_2.29",
        ],
        "execution_profile_id": "ra64-universal-v1",
        "image_id": (
            "sha256:cc8a545183ab61910e87b86b9d498ebff596ec8a253e28272e96f3f7a7fd4488"
        ),
        "toolchain_archive_sha256": (
            "bb1c69cf19fcf3cbccaee06cc8b8a01bf7020fb1ac306d3d876530b6e9636012"
        ),
        "toolchain_archive_size": 444660272,
    },
    "armhf": {
        "artifact_sha256": (
            "69061cfb98940f0a66200a214a477fb7545dc1a112018acf5aa02a9d07c0780a"
        ),
        "artifact_size": 2914924,
        "record_sha256": {
            SELECTED_RUN: (
                "bd4cee2484aca8c0888385ab0dcdbcfce2ffc06af927530f5b0cfd6a8f6945eb"
            ),
            REPRODUCTION_RUN: (
                "0ffec2870f85f2f1c4ce53b48c00e2405f3a61a2ce82f91a8c028b816f2f9563"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "f8303045f5ec96d48f3f4d64bd93074b82fb0c2094779a54e473ae51a6917dd2"
            ),
            REPRODUCTION_RUN: (
                "6770809e8b7f353c71b7ea5ef2854e3091227452b22eae4cdda7ffacd67ff342"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libgcc_s.so.1", "libm.so.6", "libstdc++.so.6"],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.11",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.9",
            "GLIBC_2.4",
            "GLIBC_2.7",
        ],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:e09ffce413cf62c14a24fd8aa3beebbbfaccd5b0b5223ac529d132f4aabd92b9"
        ),
        "toolchain_archive_sha256": (
            "e2b103c7bf1fdc9bb3ce3cf7bcde9cf2f3fd473fb0d916e8b4d0b4d278fd1afe"
        ),
        "toolchain_archive_size": 784604625,
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
    "same exact line multiset",
    "no offline source cache",
    "exactly 564 native-version compiles",
    "536 C and 28 C++",
    "no diagnostic lines",
    "exact ordered link",
    "GPLv2",
    "display version 3.9",
    "supports_no_game=true",
    "needs_fullpath=true",
    "3.10 7946cfa0d3",
    "metadata/runtime version discrepancy",
    "Base ROMs are embedded",
    "Four optional JiffyDOS replacements",
    "no firmware redistribution rights",
    "target-runtime gates",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "every device view remains ineligible",
)


class ViceX64CoreEvidenceTests(unittest.TestCase):
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
        self.assertEqual(PACKAGE_SIZE, selection["package"]["size"])
        self.assertEqual(METADATA_SHA256, selection["metadata"]["sha256"])
        self.assertEqual(METADATA_SIZE, selection["metadata"]["size"])
        self.assertEqual(PACKAGE_SHA256, selection["e2e"]["package_sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
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
            E2E_FILE_SHA256[REPRODUCTION_RUN], file_sha256(reproduction_path)
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
        self.assertTrue(caveats)
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)
        for reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            compatibility["golden_source"],
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
            caveats,
        ):
            self.assertNotIn("tranche", reference.casefold())

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
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], selected_target["artifact"]["sha256"]
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual([], golden_record["build"]["compile_definitions"])
                self.assertEqual(
                    {
                        "derivation": "native-space-short10-v1",
                        "value": " 7946cfa0d3",
                    },
                    golden_record["build"]["git_version"],
                )
                self.assertEqual(METADATA_SHA256, golden_record["metadata"]["sha256"])
                self.assertEqual(METADATA_SIZE, golden_record["metadata"]["size"])
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
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["version_requirements"], artifact["version_requirements"]
                )

                recipe = golden_record["recipe"]
                self.assertEqual(CORE_ID, recipe["core_id"])
                self.assertEqual(
                    ".github/workflows/build-vice_x64.yml", recipe["workflow"]
                )
                self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
                self.assertFalse(recipe["repository_dirty"])
                self.assertIn(
                    "scripts/core_pipeline_lib/contracts/vice_x64.py",
                    recipe["pipeline_bundle"]["files"],
                )
                toolchain = golden_record["toolchain"]
                self.assertEqual(expected["image_id"], toolchain["image_id"])
                self.assertEqual(expected["image_id"], toolchain["resolved_image_id"])
                archive = toolchain["archive_provenance"]["archive"]
                self.assertEqual(expected["toolchain_archive_sha256"], archive["sha256"])
                self.assertEqual(expected["toolchain_archive_size"], archive["size"])
                self.assertEqual(
                    "local-cache-v1",
                    toolchain["archive_provenance"]["lock"]["lock_id"],
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
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock_path = ROOT / source["path"]
        source_lock = load_document(source_lock_path)
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, file_sha256(source_lock_path))
        self.assertEqual(SOURCE_LOCK_CONTENT_SHA256, source_lock["content_sha256"])
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
                self.assertEqual(expected["artifact_sha256"], cell["artifact_sha256"])
                self.assertEqual(
                    expected["execution_profile_id"], cell["execution_profile_id"]
                )
                self.assertEqual("provisional-unverified", cell["device_eligibility"])
        self.assertTrue(report["device_views"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                and view["eligibility"] == "provisional-unverified"
                for view in report["device_views"]
            )
        )

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
            "source set reference path does not bind vice_x64",
        ):
            registry.validate_source_set(wrong_commit, verify_files=False)

    def test_channel_lifecycle_is_semantic_and_core_isolated(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
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
                self.assertTrue(pointer["local_only"])
                self.assertEqual("disabled", pointer["publication"])
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
        self.assertEqual(PACKAGE_SIZE, release["assets"][0]["size"])

    def test_selected_and_reproduction_runs_prove_exact_parallel_builds(
        self,
    ) -> None:
        contract = vice_x64.VICE_X64_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("vice-x64-mixed-language-v1", registered_contract.contract_id)
        self.assertEqual("vice_x64_log_proves_contract", registered_contract.proof_name)
        self.assertEqual(564, contract.expected_compile_count)
        self.assertEqual(
            {"c": 536, "cxx": 28}, dict(contract.expected_language_counts)
        )
        self.assertEqual(
            "276b4e5cbccc4fefbc6d1f937cb9cf7d1cde203ccda05bee3036e26022c59982",
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "7d6daaf8b6ae2b6f36a6ddafe3450cc8e1fbf77d37f76494ced907cc172e440b"
                ),
                "armhf": (
                    "289b2fa41eb43af8e39d95b2b0c6d118bced528ed0be8b0424019fba009029da"
                ),
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            "a9c89773f61c919e19b022799598f246fffcd861774fe359605ad3e9dffee01b",
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            "31f02b19970b0a0dc441dac98908875807984e549ab249e499f3bbcd93eb6b63",
            contract.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            (
                "-shared",
                "-Wl,--version-script=./libretro/link.T",
                "-Wl,--gc-sections",
                "-s",
                "-lm",
                "-fPIC",
            ),
            contract.expected_link_options,
        )

        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, dict[str, bytes]] = {
            architecture: {} for architecture in TARGETS
        }
        toolchains: dict[str, list[dict[str, object]]] = {
            architecture: [] for architecture in TARGETS
        }
        recipes: dict[str, list[dict[str, object]]] = {
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
                self.assertEqual(PACKAGE_SIZE, package["size"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/vice_x64_libretro.so",
                            "cores/vice_x64_libretro.so",
                            "vice_x64_libretro.info",
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
                                "derivation": "native-space-short10-v1",
                                "value": " 7946cfa0d3",
                            },
                            record["build"]["git_version"],
                        )

                        recipe = record["recipe"]
                        self.assertEqual(CORE_ID, recipe["core_id"])
                        self.assertEqual(
                            ".github/workflows/build-vice_x64.yml",
                            recipe["workflow"],
                        )
                        self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
                        self.assertFalse(recipe["repository_dirty"])
                        recipes[architecture].append(recipe)
                        toolchain = record["toolchain"]
                        self.assertEqual(expected["image_id"], toolchain["image_id"])
                        self.assertEqual(
                            expected["image_id"], toolchain["resolved_image_id"]
                        )
                        archive = toolchain["archive_provenance"]["archive"]
                        self.assertEqual(
                            expected["toolchain_archive_sha256"], archive["sha256"]
                        )
                        self.assertEqual(
                            expected["toolchain_archive_size"], archive["size"]
                        )
                        toolchains[architecture].append(toolchain)

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(
                            expected["log_sha256"][run_id], file_sha256(log_path)
                        )
                        logs[architecture][run_id] = log_bytes
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
                            565,
                            log_text.count(
                                vice_x64.VICE_X64_NATIVE_GIT_VERSION_LOG_TOKEN
                            ),
                        )
                        self.assertEqual(565, log_text.count("-DGIT_VERSION="))
                        self.assertEqual(565, log_text.count("-DCORE_NAME="))
                        self.assertEqual(565, log_text.count("-D__X64__"))
                        lowered_log = log_text.casefold()
                        for marker in vice_x64.VICE_X64_FORBIDDEN_DIAGNOSTIC_MARKERS:
                            self.assertNotIn(marker, lowered_log)

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "3.9"', metadata)
                        self.assertIn(b'license = "GPLv2"', metadata)
                        self.assertIn(b'supports_no_game = "true"', metadata)
                        self.assertIn(b'needs_fullpath = "true"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        self.assertEqual(
                            expected["artifact_size"], record["artifact"]["size"]
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"3.10 7946cfa0d3", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])
                selected_log = logs[architecture][SELECTED_RUN]
                reproduction_log = logs[architecture][REPRODUCTION_RUN]
                self.assertNotEqual(selected_log, reproduction_log)
                self.assertEqual(
                    Counter(selected_log.splitlines(keepends=True)),
                    Counter(reproduction_log.splitlines(keepends=True)),
                )
                self.assertEqual(
                    toolchains[architecture][0], toolchains[architecture][1]
                )
                self.assertEqual(recipes[architecture][0], recipes[architecture][1])

    def test_contract_rejects_source_version_and_order_mutations(self) -> None:
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
        lines = log_text.splitlines(keepends=True)
        compile_position = next(
            index
            for index, line in enumerate(lines)
            if " -c " in line
            and vice_x64.VICE_X64_NATIVE_GIT_VERSION_LOG_TOKEN in line
        )
        compile_line = lines.pop(compile_position)
        link_position = next(
            index
            for index, line in enumerate(lines)
            if "-o vice_x64_libretro.so" in line
        )
        lines.insert(link_position + 1, compile_line)
        reordered_log = "".join(lines)
        self.assertEqual(
            Counter(log_text.splitlines(keepends=True)),
            Counter(reordered_log.splitlines(keepends=True)),
        )
        mutations = {
            "source": log_text.replace(
                vice_x64.VICE_X64_SOURCE_HEAD_MARKER,
                "HEAD is now at 0000000000 tampered",
                1,
            ),
            "native-version": log_text.replace(
                vice_x64.VICE_X64_NATIVE_VERSION_MARKER,
                "",
                1,
            ),
            "extra-warning": log_text + "warning: extra\n",
            "compile-after-link": reordered_log,
        }
        for label, mutated_log in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(log_text, mutated_log)
                self.assertFalse(
                    vice_x64.vice_x64_log_proves_contract(
                        mutated_log,
                        CORE_ID,
                        "arm64",
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
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

        malformed = copy.deepcopy(compatibility)
        malformed["targets"]["arm64"]["artifact_sha256"] = 7
        malformed["content_sha256"] = pipeline.core_compatibility_content_sha256(
            malformed
        )
        malformed_report = pipeline.validate_core_compatibility_document(
            malformed,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", malformed_report["status"])
        self.assertIn(
            f"{CORE_ID}/arm64: artifact digest is invalid",
            malformed_report["errors"],
        )

        missing_reproduction = copy.deepcopy(compatibility)
        missing_reproduction["reproduction_run"] = (
            ".local-e2e/runs/nonexistent-vice_x64/e2e-record.json"
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

        pin_mutations = {
            "digest": copy.deepcopy(pin),
            "semantic_id": copy.deepcopy(pin),
            "source_reference": copy.deepcopy(pin),
        }
        pin_mutations["digest"]["content_sha256"] = "0" * 64
        pin_mutations["semantic_id"]["pin_id"] = "vice_x64-nonsemantic-pin"
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
            "source_reference": "individual core pin: source 0 no longer matches the pin",
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
                prefix=f"compat-tamper-vice-x64-{mutation}-",
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
                    record["build"]["git_version"]["value"] = "tampered"
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
                refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)
                with self.assertRaisesRegex(pipeline.PipelineError, expected_error):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )

    def test_reproduction_rejects_compile_reordering_with_same_lines(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-reorder-vice-x64-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_text = log_path.read_text(encoding="utf-8")
            lines = log_text.splitlines(keepends=True)
            compile_position = next(
                index
                for index, line in enumerate(lines)
                if " -c " in line
                and vice_x64.VICE_X64_NATIVE_GIT_VERSION_LOG_TOKEN in line
            )
            compile_line = lines.pop(compile_position)
            link_position = next(
                index
                for index, line in enumerate(lines)
                if "-o vice_x64_libretro.so" in line
            )
            lines.insert(link_position + 1, compile_line)
            reordered_log = "".join(lines)
            self.assertEqual(
                Counter(log_text.splitlines(keepends=True)),
                Counter(reordered_log.splitlines(keepends=True)),
            )
            self.assertFalse(
                vice_x64.vice_x64_log_proves_contract(
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
            refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)

            mutated = copy.deepcopy(compatibility)
            mutated["reproduction_run"] = (
                f".local-e2e/runs/{run_root.name}/e2e-record.json"
            )
            mutated["reproduction_e2e_content_sha256"] = evidence["content_sha256"]
            mutated["content_sha256"] = pipeline.core_compatibility_content_sha256(
                mutated
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
