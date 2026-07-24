"""Pinned blueMSX individual lifecycle tests."""

from __future__ import annotations

import copy
from collections import Counter
import shlex
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import bluemsx
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


CORE_ID = "bluemsx"
OTHER_CORE_ID = "fmsx"
PIN_NAME = "bluemsx-5f595c79906f-5d1ea1b42de8.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/bluemsx/"
    "5f595c79906ff3379641b5ee8f3796106214a0a4.json"
)
SOURCE_COMMIT = "5f595c79906ff3379641b5ee8f3796106214a0a4"
SOURCE_TREE = "1d6e218616f313f9147aa7ecf3f74584a9aaa23c"
SOURCE_URL = "https://github.com/libretro/blueMSX-libretro.git"
SOURCE_LOCK_ID = "bluemsx-5f595c79906f"
SOURCE_LOCK_FILE_SHA256 = (
    "be3ef8c2e18497ba3f50b8998688d20eb5e68262123e9bcafbab08c25fe01e11"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "46a90fa7e78b9c164cd5d834b5ccaa1af8da5c5d7031e07bf52b7c2f79c2d894"
)
SOURCE_SET_FILE_SHA256 = (
    "89fb9b9819000f166130323b367df4e84db9a4d73deed81448466da537242feb"
)
SOURCE_SET_CONTENT_SHA256 = (
    "7ab11c415575e2c20d67d1b5ad79084e285ef05396791fee35286cf6f9789c9c"
)
PIN_FILE_SHA256 = (
    "0e398d19680f64046e0abee2c0683ebb695d2223b511608f49603bcc69c24427"
)
PIN_CONTENT_SHA256 = (
    "1ae07ed47fa8e85ca899e05938b8666310b1c9b4e7a44219c8ee68c92f2ef4a1"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "0f1117b4be872d14b3bf99be8c45bc72ba8a72a5ed3e0c6bf811a64de7ba9eb6"
)
SELECTION_SHA256 = (
    "5d1ea1b42de8462e0989872afb6e341eea58b404165185432af23815d0fb25fd"
)
SELECTED_RUN = "actions-sim-build-core-bluemsx-w3c"
REPRODUCTION_RUN = "build-core-bluemsx-local-w3c"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "cba80340888230cecfd2bd9a36852cc87c84b666ca320b576c915c674d7ccb7e"
    ),
    REPRODUCTION_RUN: (
        "dca17721dde8ca162fe9733d0a12b064e2ab652f0a476e39fca4b1fd45d8c725"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "269d346484409f2030c5acc3c6c77389990944d39835daa3f6b0c41fdcf81c4d"
    ),
    REPRODUCTION_RUN: (
        "8895f5936f65a8adac0a5d00f7ad4caaccb54cd3db4f5d8f66fd596c8457e023"
    ),
}
PACKAGE_SHA256 = (
    "8ec3c360d6be309730509311eb5cadce01b9dfeb173debc536f353908c8d7c9f"
)
PACKAGE_SIZE = 1513398
METADATA_SHA256 = (
    "e3840e08ff90f8567beedc9f96ee3597d48ea7a568cfd51aadca20850800257e"
)
METADATA_SIZE = 2286
RECIPE_HEAD = "197d7cc1f9a4bb96cf9af4c7292e95a0826ee7af"
CORE_SPEC_SHA256 = (
    "4e7eceb00b599dde521189fff912b92714668561c97b25dd2dea38b810d6afd8"
)
CATALOG_SHA256 = (
    "4b374c814b03b543769e485f850b8edf579add8896f2b52c974bddd3b3341415"
)
PIPELINE_SHA256 = (
    "a4ef27e27bf7bfc3312ef6aeb69033d3107ac0eb6a204f36dacbc46b7ec809d6"
)
PIPELINE_BUNDLE_CONTENT_SHA256 = (
    "964db21eb766f5fae148f4e6c7df3ab15ac7ca5e7e281d8f3daaee56da35df73"
)
WORKFLOW_SHA256 = (
    "5f297670b44d340c7cedc0586c03438d5364af3add69b0fdb835d28455b9c401"
)
TOOLCHAIN_LOCK_FILE_SHA256 = (
    "7606e9357490f451df4374d38aad73a0426e3bb956a732dcaaa6b32393ee8639"
)
TOOLCHAIN_LOCK_CONTENT_SHA256 = (
    "253f7d84cc71fa859553fa05fab4c2356b842196104953b092501850c217a794"
)
LIBRETRO_SUPER_COMMIT = "60f5c62789af16379446544d64228afa1d6b28b7"
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
            "14f32f0f61aa7a81d6ad34b244d33db0d88420eb132baa660dc48b7f835978bd"
        ),
        "artifact_size": 1812712,
        "record_sha256": {
            SELECTED_RUN: (
                "1140f00d0d6f5677da34abc1b7f01594fc2b0ade6a8bb26704769bec081cee97"
            ),
            REPRODUCTION_RUN: (
                "807aad70de6e23cf02f79aecbf404cd64283d54154f9bfd96c5f3aa7ef786c87"
            ),
        },
        "log_sha256": (
            "51ec8ba37ef3a8732b089e751d79f11293ae6ac7b92728548618d2166a4faae6"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6", "libstdc++.so.6"],
        "version_requirements": [
            "CXXABI_1.3",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.21",
            "GLIBC_2.17",
            "GLIBC_2.27",
        ],
        "execution_profile_id": "ra64-universal-v1",
        "image_id": (
            "sha256:538411e2759cd5482068fd0c1f24d5a033138cd9f49db31f2c620929a8b046a9"
        ),
        "toolchain_archive_sha256": (
            "8a3bdd7f36a10a092209cd8f308d2d2a85e316be7ede6d42562074243b25bc64"
        ),
        "toolchain_archive_size": 502531978,
        "recipe_snapshot_sha256": (
            "d276b9f77d713260a841c2b47a484774ba246bd2279c2a0e4d2fd3052a518106"
        ),
        "compilers": (
            "aarch64-linux-gnu-gcc",
            "aarch64-linux-gnu-g++",
        ),
        "cxx_compiler": "aarch64-linux-gnu-g++",
    },
    "armhf": {
        "artifact_sha256": (
            "604885f77e8cb3b800b4fa881d875af31bb31d66a94d776e1b2e2c4b6d248c3f"
        ),
        "artifact_size": 1538228,
        "record_sha256": {
            SELECTED_RUN: (
                "a17ced2ced17cf4c0311438fec032be7228a3c57498d40a4ed959c8d9d4f9af8"
            ),
            REPRODUCTION_RUN: (
                "b9657f74496cca08a693be46245cf8ad18fc6cce7142fecc2aa33039e556502c"
            ),
        },
        "log_sha256": (
            "1cca54101935e09492f630a6073c8a82199d40b11b6c4b1790124f46c473ef61"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libgcc_s.so.1", "libm.so.6", "libstdc++.so.6"],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.21",
            "GLIBC_2.4",
        ],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:393a23661c4178edfc4e5ea0221e5de317a40f2f50a9fff1cb76e9e322189dd9"
        ),
        "toolchain_archive_sha256": (
            "f297cbf988aeb15c3de90c1bc900494aaf4214320aa5fcfa2cbbf10d2e32f16e"
        ),
        "toolchain_archive_size": 835303648,
        "recipe_snapshot_sha256": (
            "a7946e81f20c14bb26735ef8014f3bb15be0b79603c6814b86004c3178d48e92"
        ),
        "compilers": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
        "cxx_compiler": "arm-a30-linux-gnueabihf-g++",
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
    "exactly 269 compiles (255 C and 14 C++)",
    "native version ' 5f595c7' on every C compile and no C++ compile",
    "exactly one upstream -w warning-suppression option on every compile",
    "suppression consistency, not warning-free source code",
    "GPLv2",
    "mixed tree",
    "Public distribution",
    "302 candidate system files",
    "nine C-BIOS ROMs",
    "correctly staged Machines and Databases directories",
    "system-data redistribution remain human legal and policy gates",
    "Metadata declares no-game support, full-path loading, disk control",
    "ten-image M3U handling",
    "disk-overlay persistence",
    "fixed 4 MiB allocation",
    "non-default fixed-epoch RTC option",
    "Mouse entry points are stubs",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "All eight device views have empty eligibility sets",
    "all 16 device entries remain ineligible",
)


class BlueMsxCoreEvidenceTests(unittest.TestCase):
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
        self.assertEqual(COMPATIBILITY_CONTENT_SHA256, compatibility["content_sha256"])
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
                    {
                        "compiler_scope": "c",
                        "derivation": "native-space-short7-v1",
                        "value": " 5f595c7",
                    },
                    golden_record["build"]["git_version"],
                )
                self.assertEqual([], golden_record["build"]["compile_definitions"])

                recipe = golden_record["recipe"]
                self._assert_recipe(recipe)
                toolchain = golden_record["toolchain"]
                self._assert_toolchain(toolchain, expected)
                snapshot_reference = golden_record["local_store"][
                    "recipe_snapshots"
                ][architecture]
                self.assertEqual(
                    expected["recipe_snapshot_sha256"], snapshot_reference["sha256"]
                )
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
        self.assertEqual(8, len(report["device_views"]))
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
                "4309e5a4582bb319f7ba3a95ca527fe5f214be85a0975698863c4b0661f4145d"
            ),
            "pinned": PIN_FILE_SHA256,
            "release": (
                "ad937feb5dcb77e46a9f7656c947d23a21e237d3e1993bb2b07ec6570569844b"
            ),
        }
        content_hashes = {
            "nightly": (
                "659e7a247a681a4857aeb7a44149bfcbe1043d6809929b56542f5d8c96128c1e"
            ),
            "pinned": PIN_CONTENT_SHA256,
            "release": (
                "b632741f02bc3776f1d21fb76b679604c508b452090a1e32a19b9683f000c25a"
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
        contract = bluemsx.BLUEMSX_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("bluemsx-mixed-language-v1", registered_contract.contract_id)
        self.assertEqual("bluemsx_log_proves_contract", registered_contract.proof_name)
        self.assertEqual(269, contract.expected_compile_count)
        self.assertEqual({"c": 255, "cxx": 14}, dict(contract.expected_language_counts))
        self.assertEqual(
            "cd7ff9673f83630e220fda7186b2887fe5cfb208019388223a503d4da0f385ec",
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "b164112377465c8b7d41d82f5a2385c19ce1f0021b3f8d1b48dc64ed025f96a1"
                ),
                "armhf": (
                    "82e9389a71aba5a01ef6229a80771ac70891b16dd8e1ec1fa59390049f840dca"
                ),
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            "4f7e5b8f24429107aa86d06e304bce477137c2cbe1468bae5b613c4067f550b4",
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            "7f65220d6c91961e84d4801548bd0da14349843fe176d69d7149752cc64a3d86",
            contract.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "8b495607ac268e960f0dc4822d07388636f8137e379dd15371ccada08776b17d"
                ),
                "armhf": (
                    "9b638c84c69d48f61577f6cdcccb22acf618e1ab353ec203f4330c19d3df6483"
                ),
            },
            dict(contract.expected_ordered_link_argv_sha256),
        )
        self.assertEqual("cxx", contract.expected_link_language)

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
                            "cores64/bluemsx_libretro.so",
                            "cores/bluemsx_libretro.so",
                            "bluemsx_libretro.info",
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
                            "compiler_scope": "c",
                            "derivation": "native-space-short7-v1",
                            "value": " 5f595c7",
                        },
                        record["build"]["git_version"],
                    )
                    recipe = record["recipe"]
                    self._assert_recipe(recipe)
                    recipes[architecture].append(recipe)
                    toolchain = record["toolchain"]
                    self._assert_toolchain(toolchain, expected)
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
                    self._assert_compile_scope(log_text, expected)
                    self.assertEqual(1, log_text.count(bluemsx.BLUEMSX_NATIVE_VERSION_MARKER))
                    lowered_log = log_text.casefold()
                    for marker in bluemsx.BLUEMSX_FORBIDDEN_EMITTED_DIAGNOSTIC_MARKERS:
                        self.assertNotIn(marker, lowered_log)
                    self.assertIsNone(bluemsx.BLUEMSX_MAKE_FAILURE_RE.search(log_text))

                    metadata_path = record_path.parent / record["metadata"]["path"]
                    self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                    self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                    metadata = metadata_path.read_bytes()
                    self.assertIn(
                        b'display_name = "MSX/SVI/ColecoVision/SG-1000 (blueMSX)"',
                        metadata,
                    )
                    self.assertIn(b'display_version = "SVN"', metadata)
                    self.assertIn(b'license = "GPLv2"', metadata)
                    self.assertIn(b'supports_no_game = "true"', metadata)
                    self.assertIn(b'needs_fullpath = "true"', metadata)
                    self.assertIn(
                        b'firmware0_path = "Databases/msxromdb.xml"', metadata
                    )
                    self.assertIn(
                        b'firmware1_path = "Machines/Shared Roms/MSX.rom"', metadata
                    )
                    metadata_payloads.append(metadata)

                    artifact_path = record_path.parent / record["artifact"]["path"]
                    self.assertEqual(
                        expected["artifact_sha256"], file_sha256(artifact_path)
                    )
                    self.assertEqual(expected["artifact_size"], record["artifact"]["size"])
                    artifact = artifact_path.read_bytes()
                    self.assertIn(b"blueMSX", artifact)
                    self.assertIn(b"git 5f595c7", artifact)
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

    def test_contract_rejects_source_version_suppression_and_order_mutations(
        self,
    ) -> None:
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
            and bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN in line
        )
        compile_line = lines.pop(compile_position)
        link_position = next(
            index
            for index, line in enumerate(lines)
            if "-o bluemsx_libretro.so" in line
        )
        lines.insert(link_position + 1, compile_line)
        reordered_log = "".join(lines)
        self.assertEqual(
            Counter(log_text.splitlines(keepends=True)),
            Counter(reordered_log.splitlines(keepends=True)),
        )
        cxx_line = next(
            line
            for line in log_text.splitlines(keepends=True)
            if line.startswith("aarch64-linux-gnu-g++") and " -c " in line
        )
        versioned_cxx_line = cxx_line.replace(
            " -c ",
            f" -c {bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN} ",
            1,
        )
        mutations = {
            "source": log_text.replace(
                bluemsx.BLUEMSX_SOURCE_HEAD_MARKER,
                "HEAD is now at 0000000 tampered",
                1,
            ),
            "native-version-marker": log_text.replace(
                bluemsx.BLUEMSX_NATIVE_VERSION_MARKER, "", 1
            ),
            "native-version-on-cxx": log_text.replace(
                cxx_line, versioned_cxx_line, 1
            ),
            "missing-warning-suppression": log_text.replace(" -w ", " ", 1),
            "extra-warning": log_text + "warning: synthetic\n",
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
            registry.RegistryError, "source set reference path does not bind bluemsx"
        ):
            registry.validate_source_set(malformed_source_set)

        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-bluemsx-log-",
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

    def _assert_recipe(self, recipe: dict[str, object]) -> None:
        self.assertEqual(CORE_ID, recipe["core_id"])
        self.assertEqual(".github/workflows/build-bluemsx.yml", recipe["workflow"])
        self.assertEqual(WORKFLOW_SHA256, recipe["workflow_sha256"])
        self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
        self.assertFalse(recipe["repository_dirty"])
        self.assertEqual(CORE_SPEC_SHA256, recipe["core_spec_sha256"])
        self.assertEqual(CATALOG_SHA256, recipe["catalog_sha256"])
        self.assertEqual(PIPELINE_SHA256, recipe["pipeline_sha256"])
        pipeline_bundle = recipe["pipeline_bundle"]
        self.assertIsInstance(pipeline_bundle, dict)
        assert isinstance(pipeline_bundle, dict)
        self.assertEqual(
            PIPELINE_BUNDLE_CONTENT_SHA256, pipeline_bundle["content_sha256"]
        )
        files = pipeline_bundle["files"]
        self.assertIsInstance(files, dict)
        assert isinstance(files, dict)
        self.assertIn("scripts/core_pipeline_lib/contracts/bluemsx.py", files)

    def _assert_toolchain(
        self, toolchain: dict[str, object], expected: dict[str, object]
    ) -> None:
        self.assertEqual(expected["image_id"], toolchain["image_id"])
        self.assertEqual(expected["image_id"], toolchain["resolved_image_id"])
        self.assertEqual(LIBRETRO_SUPER_COMMIT, toolchain["libretro_super_commit"])
        provenance = toolchain["archive_provenance"]
        self.assertIsInstance(provenance, dict)
        assert isinstance(provenance, dict)
        archive = provenance["archive"]
        self.assertIsInstance(archive, dict)
        assert isinstance(archive, dict)
        self.assertEqual(expected["toolchain_archive_sha256"], archive["sha256"])
        self.assertEqual(expected["toolchain_archive_size"], archive["size"])
        lock = provenance["lock"]
        self.assertIsInstance(lock, dict)
        assert isinstance(lock, dict)
        self.assertEqual("local-cache-v1", lock["lock_id"])
        self.assertEqual(TOOLCHAIN_LOCK_FILE_SHA256, lock["file_sha256"])
        self.assertEqual(TOOLCHAIN_LOCK_CONTENT_SHA256, lock["content_sha256"])

    def _assert_compile_scope(
        self, log_text: str, expected: dict[str, object]
    ) -> None:
        compilers = expected["compilers"]
        self.assertIsInstance(compilers, tuple)
        compile_commands: list[list[str]] = []
        for line in log_text.splitlines():
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if tokens and tokens[0] in compilers and "-c" in tokens:
                compile_commands.append(tokens)
        self.assertEqual(269, len(compile_commands))
        cxx_compiler = expected["cxx_compiler"]
        c_commands = [tokens for tokens in compile_commands if tokens[0] != cxx_compiler]
        cxx_commands = [tokens for tokens in compile_commands if tokens[0] == cxx_compiler]
        self.assertEqual(255, len(c_commands))
        self.assertEqual(14, len(cxx_commands))
        for tokens in compile_commands:
            self.assertEqual(1, tokens.count(bluemsx.BLUEMSX_WARNING_SUPPRESSION_OPTION))
        for tokens in c_commands:
            self.assertEqual(
                [bluemsx.BLUEMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN],
                [token for token in tokens if "GIT_VERSION" in token],
            )
        for tokens in cxx_commands:
            self.assertEqual([], [token for token in tokens if "GIT_VERSION" in token])


if __name__ == "__main__":
    unittest.main()
