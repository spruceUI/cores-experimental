"""Pinned VICE xvic individual lifecycle tests."""

from __future__ import annotations

import copy
from collections import Counter
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import vice_xvic
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


CORE_ID = "vice_xvic"
OTHER_CORE_ID = "vice_x64"
PIN_NAME = "vice_xvic-7946cfa0d377-e23a9971f265.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "7946cfa0d3775e958616d4d107de867a4616ae6c"
SOURCE_TREE = "db2760ffc97b9c20ef8777fcb7689082be66bc45"
SOURCE_URL = "https://github.com/libretro/vice-libretro.git"
SOURCE_LOCK_ID = "vice_xvic-7946cfa0d377"
SOURCE_LOCK_FILE_SHA256 = (
    "1b254bedfa0de9438ab6f7082dfb58132d51216821e7a9e221eccc67729114e2"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "db0c1810cf88141e880e6803f5874f8fecc24f35978c889928dbebbd143e7e4f"
)
SELECTION_SHA256 = (
    "e23a9971f265954c7aca8c221523fb35a36710fd6d997c89344632f4e89b4eea"
)
SELECTED_RUN = "actions-sim-build-core-vice_xvic-w3c"
REPRODUCTION_RUN = "build-core-vice_xvic-local-w3c"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "93c879130afe9b69ed63f29d0a5c5638b709c61d5040d9d7b3c896296eea89e1"
    ),
    REPRODUCTION_RUN: (
        "ad4231056ef69eca6347f533840f657e52cfa6cb092e666cda677ee790657bde"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "2438c579f9b096a4619eab6dea907bd896e224ce105317a88af496ad16d219f3"
    ),
    REPRODUCTION_RUN: (
        "205207855ee79c5aeba5fb8f36719d6bf3d6064655fef89e89883cf9d0115557"
    ),
}
PACKAGE_SHA256 = (
    "10906ebef5504ea8fb41363da5ee0d0ffa1aac927bc72995e46015db8e63b8d1"
)
PACKAGE_SIZE = 2049996
METADATA_SHA256 = (
    "48b23d8971b40aad47efb526b23b8ce11a5f21edd83a4b10fdd0de63a911e571"
)
METADATA_SIZE = 1053
RECIPE_HEAD = "197d7cc1f9a4bb96cf9af4c7292e95a0826ee7af"
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
            "8b3eda61d9c20032fea521ba24f2e97a690eee6cf2447abd2a02e12255907e0a"
        ),
        "artifact_size": 2879480,
        "record_sha256": {
            SELECTED_RUN: (
                "f26c8e3a34aa359178c28e3145be883dd0366f19d7343d8cb6db21dc30786d97"
            ),
            REPRODUCTION_RUN: (
                "e35c2a781328d85ce9290a2c193b2400b194c04c45bfb611266dd98fad8c98f5"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "c5ad18bfc8f1f1e996f91f188f227a9e8ef5d2625828c815d2ad3c541f7bb6ce"
            ),
            REPRODUCTION_RUN: (
                "2a5e63e5647e5e8bdb342ccf13572a4428daacbf0c969553b4f663b46d4b9a03"
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
            "GLIBCXX_3.4.9",
            "GLIBC_2.17",
            "GLIBC_2.29",
        ],
        "execution_profile_id": "ra64-universal-v1",
        "image_id": (
            "sha256:538411e2759cd5482068fd0c1f24d5a033138cd9f49db31f2c620929a8b046a9"
        ),
        "toolchain_archive_sha256": (
            "8a3bdd7f36a10a092209cd8f308d2d2a85e316be7ede6d42562074243b25bc64"
        ),
        "toolchain_archive_size": 502531978,
    },
    "armhf": {
        "artifact_sha256": (
            "8bdec5897cd866061a52cb6e7d2f4428e9727692f66b6959c47efbdb5f94e3f5"
        ),
        "artifact_size": 2374668,
        "record_sha256": {
            SELECTED_RUN: (
                "9dc9e4557939889ac8613ba6b932eace8e41f0909ba2c74afcc95e072e23e399"
            ),
            REPRODUCTION_RUN: (
                "3d7a9d9cd214c32c75f31091fa6f86bf2cc760aab1e72f276b10ec66fa0bb9df"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "db72cd5f8990d75702edf0e28e313870b9fa827db6576ad0fdd3cfc382e30a02"
            ),
            REPRODUCTION_RUN: (
                "775835a79bdf25708038d1a259ff1454fa50c1e65f9d7e58e1f84e7bd601c108"
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
            "GLIBCXX_3.4.9",
            "GLIBC_2.4",
            "GLIBC_2.7",
        ],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:393a23661c4178edfc4e5ea0221e5de317a40f2f50a9fff1cb76e9e322189dd9"
        ),
        "toolchain_archive_sha256": (
            "f297cbf988aeb15c3de90c1bc900494aaf4214320aa5fcfa2cbbf10d2e32f16e"
        ),
        "toolchain_archive_size": 835303648,
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
    "exactly 438 native-version compiles",
    "428 C and 10 C++",
    "no diagnostic lines",
    "exact ordered link",
    "GPLv2",
    "display version 3.9",
    "supports_no_game=true",
    "needs_fullpath=true",
    "3.10 7946cfa0d3",
    "metadata/runtime version discrepancy",
    "Base VIC-20 ROMs are embedded",
    "no firmware redistribution rights",
    "target-runtime gates",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "every device view remains ineligible",
)


class ViceXvicCoreEvidenceTests(unittest.TestCase):
    def test_singleton_pin_manifest_and_source_set_bind_exact_evidence(self) -> None:
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
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN],
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            E2E_CONTENT_SHA256[REPRODUCTION_RUN],
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

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SIZE, selection["package"]["size"])
        self.assertEqual(METADATA_SHA256, selection["metadata"]["sha256"])
        self.assertEqual(METADATA_SIZE, selection["metadata"]["size"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN],
            selection["e2e"]["content_sha256"],
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
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual(METADATA_SHA256, golden_record["metadata"]["sha256"])
                self.assertEqual(METADATA_SIZE, golden_record["metadata"]["size"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["version_requirements"], artifact["version_requirements"]
                )
                self.assertEqual(
                    {"derivation": "native-space-short10-v1", "value": " 7946cfa0d3"},
                    golden_record["build"]["git_version"],
                )
                self.assertEqual([], golden_record["build"]["compile_definitions"])

                recipe = golden_record["recipe"]
                self.assertEqual(CORE_ID, recipe["core_id"])
                self.assertEqual(
                    ".github/workflows/build-vice_xvic.yml", recipe["workflow"]
                )
                self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
                self.assertFalse(recipe["repository_dirty"])
                self.assertIn(
                    "scripts/core_pipeline_lib/contracts/vice_xvic.py",
                    recipe["pipeline_bundle"]["files"],
                )
                toolchain = golden_record["toolchain"]
                self.assertEqual(expected["image_id"], toolchain["image_id"])
                self.assertEqual(expected["image_id"], toolchain["resolved_image_id"])
                archive = toolchain["archive_provenance"]["archive"]
                self.assertEqual(
                    expected["toolchain_archive_sha256"], archive["sha256"]
                )
                self.assertEqual(expected["toolchain_archive_size"], archive["size"])
                self.assertEqual(
                    "local-cache-v1", toolchain["archive_provenance"]["lock"]["lock_id"]
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
                        snapshot_path, golden_record, f"{CORE_ID}/{architecture}"
                    ),
                )

        source_set = load_document(ROOT / SOURCE_SET_PATH)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
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
        cells = {cell["architecture"]: cell for cell in report["build_evidence_cells"]}
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
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

    def test_channels_and_release_are_core_scoped_and_local_only(self) -> None:
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
                    pointer, expected_channel=channel, expected_core=CORE_ID
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(channel, pointer["channel"])
                self.assertTrue(pointer["local_only"])
                self.assertEqual("disabled", pointer["publication"])
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
        self.assertTrue(release["local_only"])
        self.assertEqual("disabled", release["publication"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])
        self.assertEqual(PACKAGE_SIZE, release["assets"][0]["size"])

    def test_selected_and_local_runs_prove_four_exact_parallel_builds(self) -> None:
        contract = vice_xvic.VICE_XVIC_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("vice-xvic-mixed-language-v1", registered_contract.contract_id)
        self.assertEqual(
            "vice_xvic_log_proves_contract", registered_contract.proof_name
        )
        self.assertEqual(438, contract.expected_compile_count)
        self.assertEqual({"c": 428, "cxx": 10}, dict(contract.expected_language_counts))
        self.assertEqual(
            "e83044294f09dbc1aaf858a3dc79cfd202f02cb4465146fd24c5caa1108a7eb6",
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "292ba3764442b7242d8a374775c3a36a6ad12e9102208b9dd2c4a95781a1ec68"
                ),
                "armhf": (
                    "4126cf021ba5507bcf829d8dc8226ce699a7fb5157db7160d280cd3488e796eb"
                ),
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            "ba25b56627c06226dbc1cbe06c2b19025312b3e450aceb06b139ead6c78d47e3",
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            "a2053f4152a1387ca4526e9a7ac84f04b41d9c7e5f904a84a43eb0054c61a078",
            contract.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "567c6b9c31dee696a46ed842fd332aa52e3b5ac271d571adea74811236b1374a"
                ),
                "armhf": (
                    "62687d4bd1a0a0e081430fa481706487103de44ae548e1c57079159ab51c235e"
                ),
            },
            dict(contract.expected_ordered_link_argv_sha256),
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
        proof_count = 0
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                e2e_path = run_root / "e2e-record.json"
                evidence = load_document(e2e_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(e2e_path))
                self.assertEqual(E2E_CONTENT_SHA256[run_id], evidence["content_sha256"])
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    [CORE_ID],
                    [item["core_id"] for item in evidence["packages"]],
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
                            "cores64/vice_xvic_libretro.so",
                            "cores/vice_xvic_libretro.so",
                            "vice_xvic_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )

                builds = {build["architecture"]: build for build in evidence["builds"]}
                self.assertEqual(set(TARGETS), set(builds))
                for architecture, expected in TARGETS.items():
                    build = builds[architecture]
                    self.assertEqual(CORE_ID, build["core_id"])
                    self.assertEqual("passed", build["result"])
                    self.assertEqual(
                        expected["record_sha256"][run_id],
                        build["record_sha256"],
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
                            "derivation": "native-space-short10-v1",
                            "value": " 7946cfa0d3",
                        },
                        record["build"]["git_version"],
                    )
                    recipe = record["recipe"]
                    self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
                    self.assertFalse(recipe["repository_dirty"])
                    self.assertEqual(
                        ".github/workflows/build-vice_xvic.yml",
                        recipe["workflow"],
                    )
                    recipes[architecture].append(recipe)
                    toolchain = record["toolchain"]
                    self.assertEqual(expected["image_id"], toolchain["image_id"])
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
                            log_text, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
                        )
                    )
                    proof_count += 1
                    self.assertEqual(
                        439,
                        log_text.count(
                            vice_xvic.VICE_XVIC_NATIVE_GIT_VERSION_LOG_TOKEN
                        ),
                    )
                    self.assertEqual(439, log_text.count("-DGIT_VERSION="))
                    self.assertEqual(439, log_text.count("-DCORE_NAME="))
                    self.assertEqual(439, log_text.count("-D__XVIC__"))
                    lowered_log = log_text.casefold()
                    for marker in vice_xvic.VICE_XVIC_FORBIDDEN_DIAGNOSTIC_MARKERS:
                        self.assertNotIn(marker, lowered_log)

                    metadata_path = record_path.parent / record["metadata"]["path"]
                    self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                    self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                    metadata = metadata_path.read_bytes()
                    self.assertIn(
                        b'display_name = "Commodore - VIC-20 (VICE xvic)"',
                        metadata,
                    )
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
                    self.assertIn(b"VICE xvic", artifact)
                    self.assertIn(b"3.10 7946cfa0d3", artifact)
                    artifacts[architecture].append(artifact)

        self.assertEqual(4, proof_count)
        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(
                payload == metadata_payloads[0]
                for payload in metadata_payloads[1:]
            )
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

    def test_contract_rejects_source_version_diagnostics_and_reordering(self) -> None:
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
            and vice_xvic.VICE_XVIC_NATIVE_GIT_VERSION_LOG_TOKEN in line
        )
        compile_line = lines.pop(compile_position)
        link_position = next(
            index
            for index, line in enumerate(lines)
            if "-o vice_xvic_libretro.so" in line
        )
        lines.insert(link_position + 1, compile_line)
        reordered_log = "".join(lines)
        self.assertEqual(
            Counter(log_text.splitlines(keepends=True)),
            Counter(reordered_log.splitlines(keepends=True)),
        )
        mutations = {
            "source": log_text.replace(
                vice_xvic.VICE_XVIC_SOURCE_HEAD_MARKER,
                "HEAD is now at 0000000000 tampered",
                1,
            ),
            "native-version": log_text.replace(
                vice_xvic.VICE_XVIC_NATIVE_VERSION_MARKER, "", 1
            ),
            "extra-warning": log_text + "warning: extra\n",
            "compile-after-link": reordered_log,
        }
        for label, mutated_log in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(log_text, mutated_log)
                self.assertFalse(
                    vice_xvic.vice_xvic_log_proves_contract(
                        mutated_log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                    )
                )

    def test_manifest_pin_and_reproduction_tampering_fail_closed(self) -> None:
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
            "core compatibility content digest is invalid",
            digest_report["errors"],
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
            same_run, document_path=compatibility_path, repository_root=ROOT
        )
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        malformed_pin = copy.deepcopy(pin)
        malformed_pin["sources"][0]["file_sha256"] = "0" * 64
        malformed_pin["content_sha256"] = pipeline.pin_set_content_sha256(malformed_pin)
        with mock.patch.object(
            compatibility_records, "load_json", return_value=malformed_pin
        ):
            pin_report = pipeline.validate_core_compatibility_document(
                compatibility,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
        self.assertEqual("invalid", pin_report["status"])
        self.assertIn(
            "individual core pin: source 0 no longer matches the pin",
            pin_report["errors"],
        )

        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-vice-xvic-log-",
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
            with self.assertRaisesRegex(
                pipeline.PipelineError, "historical build differs"
            ):
                pipeline._validate_compatibility_e2e_run(
                    run_root / "e2e-record.json", CORE_ID, expected_targets
                )

    def test_recomputed_reordered_reproduction_is_rejected(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-reorder-vice-xvic-",
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
                and vice_xvic.VICE_XVIC_NATIVE_GIT_VERSION_LOG_TOKEN in line
            )
            compile_line = lines.pop(compile_position)
            link_position = next(
                index
                for index, line in enumerate(lines)
                if "-o vice_xvic_libretro.so" in line
            )
            lines.insert(link_position + 1, compile_line)
            reordered_log = "".join(lines)
            self.assertEqual(
                Counter(log_text.splitlines(keepends=True)),
                Counter(reordered_log.splitlines(keepends=True)),
            )
            self.assertFalse(
                vice_xvic.vice_xvic_log_proves_contract(
                    reordered_log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
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
            mutated["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(mutated)
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
