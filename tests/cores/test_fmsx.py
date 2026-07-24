"""Pinned fMSX individual lifecycle tests."""

from __future__ import annotations

import copy
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import fmsx
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


CORE_ID = "fmsx"
OTHER_CORE_ID = "bluemsx"
PIN_NAME = "fmsx-f013e213458e-b015409bc42c.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/fmsx/"
    "f013e213458e06d9df718e4bc4b09d46f88aa899.json"
)
SOURCE_COMMIT = "f013e213458e06d9df718e4bc4b09d46f88aa899"
SOURCE_TREE = "ae1b15cee162c073452cc9826b1e208d2250d2bf"
SOURCE_URL = "https://github.com/libretro/fmsx-libretro.git"
SOURCE_LOCK_ID = "fmsx-f013e213458e"
SOURCE_LOCK_FILE_SHA256 = (
    "ee232b50f06dd43b327207d2a0bc32241e5fcc117da8e9c74296bcfdbdc73373"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "0c8e8fbad60f1abc86e3e28d40939912db5dfe8947cc1ccb8fb3ec48407b8221"
)
SOURCE_SET_FILE_SHA256 = (
    "4bc1e5af210130f1bd5496a39cc2706f12719aabb792ddc5ba603ef64f77e28c"
)
SOURCE_SET_CONTENT_SHA256 = (
    "bb81c330b804e12a1c6db3d2aa42ab7c2058b13142aa8a2df0270a34fb4dceea"
)
PIN_FILE_SHA256 = (
    "606b506040bdcec79720c4fef72eb22d01adb741ee778f89819be4ed6edfa781"
)
PIN_CONTENT_SHA256 = (
    "28f887944c9b2defca5dfe8715ec2e4bc6e092c8133573134df44f9c6c4b72d9"
)
SELECTION_SHA256 = (
    "b015409bc42c3a8c419324cd9b8f7d9f9fd54aa0036edc0a512be972348b2e77"
)
SELECTED_RUN = "actions-sim-build-core-fmsx-w3"
REPRODUCTION_RUN = "build-core-fmsx-local-w3"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "6c32ca2b7cb946e4c5b8d34d7e994c32678ba359414b51004ade65e88cdcd744"
    ),
    REPRODUCTION_RUN: (
        "8b2a13e55a3121719e365fb19bc1845b945e5046b1133249aae35615fa6f8db5"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "634a4d9265182e9f66a11569a0426dc9f229c9cb5d8a4e623ae82056a6a196cb"
    ),
    REPRODUCTION_RUN: (
        "97a7531c4412dab4837a12182e099f8fbda3284f69be5164cff3bedbce5f9823"
    ),
}
PACKAGE_SHA256 = (
    "a7fef9470eecde513073ded334746fea43bdd6f6b1235c00a5226ae448df1b51"
)
PACKAGE_SIZE = 254343
METADATA_SHA256 = (
    "a7b863ff5e75c538ea77dbf3e7a75d1d57f56abad1b2c946dc5d30c7b206bc98"
)
METADATA_SIZE = 2128
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
            "5e72c1e9d7c6afa31cb1396cd700254c589e94a4327ef4cbcc11aa0fff0663f7"
        ),
        "artifact_size": 282848,
        "record_sha256": {
            SELECTED_RUN: (
                "ecc871765e16801252bcb6b07177c190b3387ba2de941f77f12657c4891e5d97"
            ),
            REPRODUCTION_RUN: (
                "883083551ed35b5d8e3e9f8a70a86819e5768bfcb6bc76e3daa5564b17cae86c"
            ),
        },
        "log_sha256": (
            "6c91821864091514e6576c409c67353afc0dd9d181075bcb608f76bbbb701878"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
        "version_requirements": ["GLIBC_2.17"],
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
            "738520c499279643a51900bc5360ecbdc323a46fbfc655f4284aa9624908d67f"
        ),
        "artifact_size": 301172,
        "record_sha256": {
            SELECTED_RUN: (
                "2dc18d95d9a494aedd6fcd583214786dd0e3a31d691c58a1b6b68020b26d5618"
            ),
            REPRODUCTION_RUN: (
                "455ae80ab752dc8084794731011275891237eac38c5754071aaa14e30b49e9d6"
            ),
        },
        "log_sha256": (
            "cc359c1b9073b241c9f91fc650a72a677e68e54af64d7af2cbe4a980eb82dad6"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
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
    "both ABI logs byte for byte",
    "no offline source cache",
    "31 C compile",
    "zero diagnostic lines",
    "exact ordered 31-object C link",
    "6.0 f013e21",
    "Non-commercial",
    "MSX.ROM",
    "DISK.ROM",
    "supports_no_game=false",
    "target-runtime",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all 16 device entries remain ineligible",
)


class FmsxCoreEvidenceTests(unittest.TestCase):
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
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)

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
                    {"derivation": "native-space-short7-v1", "value": " f013e21"},
                    golden_record["build"]["git_version"],
                )
                self.assertEqual([], golden_record["build"]["compile_definitions"])

                recipe = golden_record["recipe"]
                self.assertEqual(CORE_ID, recipe["core_id"])
                self.assertEqual(".github/workflows/build-fmsx.yml", recipe["workflow"])
                self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
                self.assertFalse(recipe["repository_dirty"])
                self.assertIn(
                    "scripts/core_pipeline_lib/contracts/fmsx.py",
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

        source_set_path = ROOT / SOURCE_SET_PATH
        source_set = load_document(source_set_path)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        self.assertEqual(SOURCE_SET_FILE_SHA256, file_sha256(source_set_path))
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
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
        target_hashes = {
            "nightly": (
                "678de78ebd0ddccb3b78cda2c81cf995f5a862a2844ae93f7fa6cd5ea2082d7f"
            ),
            "pinned": PIN_FILE_SHA256,
            "release": (
                "d9227b5eefe191543825cbe260627247cdec27cc483bbc76bb800275e43485ef"
            ),
        }
        content_hashes = {
            "nightly": (
                "1ba60196c3d4a6e2d6cc3de4ed0c17bc235e752b26d65fd1e54189afde74eeaa"
            ),
            "pinned": PIN_CONTENT_SHA256,
            "release": (
                "c44d67bb6a3fc793f70826ebb9fe3038be6f43ff2fd00c6f08344ddf6c05419c"
            ),
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
                self.assertEqual(target_hashes[channel], pointer["target"]["file_sha256"])
                self.assertEqual(
                    content_hashes[channel], pointer["target"]["content_sha256"]
                )
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
        self.assertEqual(SELECTION_SHA256, release["assets"][0]["selection_sha256"])

    def test_selected_and_local_runs_prove_four_exact_builds(self) -> None:
        contract = fmsx.FMSX_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("fmsx-c-only-v1", registered_contract.contract_id)
        self.assertEqual("fmsx_log_proves_contract", registered_contract.proof_name)
        self.assertEqual(31, contract.expected_compile_count)
        self.assertEqual(
            "a1439ee1038cef8d0ba4e80989a4e8d149ccb6dc6257256b3e45f001a7416286",
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "f5e30ab376935c5cd6e952e4390451198c6c53674f24f6899d96982d58b63d59"
                ),
                "armhf": (
                    "48022dc7f8ddc706c0ee6a6b4f0adbff770348575aebb46e50d37f8ecdeac050"
                ),
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            "6acaf4be9c83c81a78e315870e85fb622db139328777395611eb44fef07c4b6a",
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            "af4895bbc360f6d34d4fd7abd11ab879736d3bacccddd402fa6a120fac2601ea",
            contract.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "9c16578b2d7a5d7d469b7a1c29e239c93492d8b942aa32b893b1a730fb7e456e"
                ),
                "armhf": (
                    "db8b9abca71c6ff1067ee3b4687cc3d2a19ed1889741308ee4eabcedc69fcc1a"
                ),
            },
            fmsx.FMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256,
        )

        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        recipes: dict[str, list[dict[str, object]]] = {
            architecture: [] for architecture in TARGETS
        }
        toolchains: dict[str, list[dict[str, object]]] = {
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
                            "cores64/fmsx_libretro.so",
                            "cores/fmsx_libretro.so",
                            "fmsx_libretro.info",
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
                            "derivation": "native-space-short7-v1",
                            "value": " f013e21",
                        },
                        record["build"]["git_version"],
                    )
                    recipe = record["recipe"]
                    self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
                    self.assertFalse(recipe["repository_dirty"])
                    self.assertEqual(
                        ".github/workflows/build-fmsx.yml", recipe["workflow"]
                    )
                    recipes[architecture].append(recipe)
                    toolchain = record["toolchain"]
                    self.assertEqual(expected["image_id"], toolchain["image_id"])
                    toolchains[architecture].append(toolchain)

                    log_path = record_path.parent / record["build"]["log"]
                    log_bytes = log_path.read_bytes()
                    log_text = log_bytes.decode("utf-8")
                    self.assertEqual(expected["log_sha256"], file_sha256(log_path))
                    self.assertEqual(
                        expected["log_sha256"], record["build"]["log_sha256"]
                    )
                    logs[architecture].append(log_bytes)
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(
                            log_text, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
                        )
                    )
                    proof_count += 1
                    self.assertEqual(
                        31, log_text.count(fmsx.FMSX_NATIVE_GIT_VERSION_LOG_TOKEN)
                    )
                    self.assertEqual(31, log_text.count("-DGIT_VERSION="))
                    self.assertEqual(1, log_text.count(fmsx.FMSX_NATIVE_VERSION_MARKER))
                    lowered_log = log_text.casefold()
                    for marker in fmsx.FMSX_FORBIDDEN_DIAGNOSTIC_MARKERS:
                        self.assertNotIn(marker, lowered_log)
                    self.assertIsNone(fmsx.FMSX_MAKE_FAILURE_RE.search(log_text))

                    metadata_path = record_path.parent / record["metadata"]["path"]
                    self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                    self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                    metadata = metadata_path.read_bytes()
                    self.assertIn(
                        b'display_name = "Microsoft - MSX (fMSX)"', metadata
                    )
                    self.assertIn(b'display_version = "6.0"', metadata)
                    self.assertIn(b'license = "Non-commercial"', metadata)
                    self.assertIn(b'supports_no_game = "false"', metadata)
                    self.assertIn(b'firmware0_path = "MSX.ROM"', metadata)
                    self.assertIn(b'firmware5_path = "DISK.ROM"', metadata)
                    metadata_payloads.append(metadata)

                    artifact_path = record_path.parent / record["artifact"]["path"]
                    self.assertEqual(
                        expected["artifact_sha256"], file_sha256(artifact_path)
                    )
                    self.assertEqual(
                        expected["artifact_size"], record["artifact"]["size"]
                    )
                    artifact = artifact_path.read_bytes()
                    self.assertIn(b"6.0 f013e21", artifact)
                    artifacts[architecture].append(artifact)

        self.assertEqual(4, proof_count)
        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])
                self.assertEqual(logs[architecture][0], logs[architecture][1])
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
            if " -c " in line and fmsx.FMSX_NATIVE_GIT_VERSION_LOG_TOKEN in line
        )
        compile_line = lines.pop(compile_position)
        link_position = next(
            index for index, line in enumerate(lines) if "-o fmsx_libretro.so" in line
        )
        lines.insert(link_position + 1, compile_line)
        reordered_log = "".join(lines)
        mutations = {
            "source": log_text.replace(
                fmsx.FMSX_SOURCE_HEAD_MARKER,
                "HEAD is now at 0000000 tampered",
                1,
            ),
            "native-version": log_text.replace(
                fmsx.FMSX_NATIVE_VERSION_MARKER, "", 1
            ),
            "extra-warning": log_text + "warning: extra\n",
            "compile-after-link": reordered_log,
        }
        for label, mutated_log in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(log_text, mutated_log)
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(
                        mutated_log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                    )
                )

    def test_manifest_pin_source_set_and_reproduction_tampering_fail_closed(
        self,
    ) -> None:
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
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        malformed_pin = copy.deepcopy(pin)
        malformed_pin["sources"][0]["file_sha256"] = "0" * 64
        malformed_pin["content_sha256"] = pipeline.pin_set_content_sha256(
            malformed_pin
        )
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

        source_set = load_document(ROOT / SOURCE_SET_PATH)
        malformed_source_set = copy.deepcopy(source_set)
        malformed_source_set["sources"][CORE_ID]["commit"] = "0" * 40
        with self.assertRaisesRegex(
            registry.RegistryError, "source set reference path does not bind fmsx"
        ):
            registry.validate_source_set(malformed_source_set)

        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-fmsx-log-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_path.write_text(
                log_path.read_text(encoding="utf-8") + "warning: synthetic\n",
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


if __name__ == "__main__":
    unittest.main()
