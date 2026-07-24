"""Pinned Snes9x 2005 Plus individual lifecycle tests."""

from __future__ import annotations

import json
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import snes9x2005_plus

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "snes9x2005_plus"
OTHER_CORE_ID = "snes9x2005"
RESERVED_HISTORY_TOKEN = "tranche"
PIN_NAME = "snes9x2005_plus-b60356971fc9-32f28e9ec741.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/snes9x2005_plus/"
    "b60356971fc9caae02cd0853676dced886a08be7.json"
)
SOURCE_LOCK_ID = "snes9x2005_plus-b60356971fc9"
SOURCE_COMMIT = "b60356971fc9caae02cd0853676dced886a08be7"
SOURCE_TREE = "5a13440308796f67a77f7e8fc16bbeee61ab301d"
SOURCE_URL = "https://github.com/libretro/snes9x2005.git"
SOURCE_LOCK_FILE_SHA256 = (
    "6865862ac006808a9f468ba73df9b99a292803ac140bc78449af72f134d74292"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "300c8502d4367895195dfcf84cd30ceff75ab84eedfeedba39097187b016358a"
)
SOURCE_SET_FILE_SHA256 = (
    "70025acd3224cf15f0bc47b8146aac0474974683878800805d7bee8241307a49"
)
SOURCE_SET_CONTENT_SHA256 = (
    "26da37f8aa5a5d1ab4d5bb009528d1858cf6d1277ce9cd335ff1ac354de59d7f"
)
PIN_FILE_SHA256 = (
    "55e4327420c261cb0830d85b1b5a652eae0b115ce71aca31bd30765268057395"
)
PIN_CONTENT_SHA256 = (
    "a0a7151bcd1151b2a390be032f32336212ed5aa8e9545b8d3c64118ec096efff"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "2e5eba8599aeede91f97e33b611476d2967a09cb310d79d013088249472fb2b7"
)
SELECTION_SHA256 = (
    "32f28e9ec7417ab1c83564adaa46a31aa2fa965398c41c324d0f0542e1799ae0"
)
SELECTED_RUN = "actions-sim-build-core-snes9x2005_plus-v1"
REPRODUCTION_RUN = "build-core-snes9x2005_plus-local-v1"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "72f21e63abee87817be77229343fffcf71f875d6bed805dce1cd87079575b1e0"
    ),
    REPRODUCTION_RUN: (
        "0cc8ea9a0cc422450c90b89fb4c0169e398f0d4d114f39ff835324b85ba65dc3"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "3c4932d211b1861e72f022f091e1d4987216c8ba9de8707221eda055c2a4cd2e"
    ),
    REPRODUCTION_RUN: (
        "868edfbfec7b1be11f4545423d0eee73510811f14f1b87ccffdd9cee598317b5"
    ),
}
PACKAGE_SHA256 = (
    "da6d86969fe506e0dd86929fd4f3b6960d18b2cda16091f37885b235d408a123"
)
PACKAGE_SIZE = 480524
METADATA_SHA256 = (
    "2e1f46c49714bcfb59926ebfe394d98004c20e7c0c38d1412dc4196e0eb34dd4"
)
METADATA_SIZE = 1456
RECIPE_HEAD = "9d95cda3d6dce32c8d33d85a58f37adad19d38d7"
CORE_SPEC_SHA256 = (
    "cc9a4d637c0b0c1fbb90d571f56c58a39b3b8623373945b23f588ee0f5860ff7"
)
CATALOG_SHA256 = (
    "028a7677a13242cdb2e9a91ba85eab6093498a9d66cd6bb7bd90ec3f3b97670f"
)
PIPELINE_SHA256 = (
    "0769decb45af2d38edca1b38171cef230715756533ab5d483ea2a73eb9f8d8ef"
)
PIPELINE_BUNDLE_CONTENT_SHA256 = (
    "d4f5928d2c412e75ee02378aa03b944d58625e35eae8bc047d50cf03eeed0c0d"
)
WORKFLOW_SHA256 = (
    "63c9747ff53d521db79647370341151533c0f6fbace108a7444e36c5c553ffd1"
)
CONTRACT_FILE_SHA256 = (
    "7762f45b058ebe117639f4f4cee5cf6cebc4ff853a2298421e3a2064cc175f4a"
)
COMMON_CONTRACT_FILE_SHA256 = (
    "9d5e0788272dd7a53473b99bd84e48a152345f25082e89d171a9f411d750e2de"
)
CONTRACT_REGISTRY_FILE_SHA256 = (
    "8cf0fee0e979fcc3c7a0df3038375b5ff72a1c33d11e84702fcf4c3a07949541"
)
TOOLCHAIN_LOCK_FILE_SHA256 = (
    "bc2fc35e12b30b6a7ca333543077f6812ed797001c05dd8dd2719670e1c6989f"
)
TOOLCHAIN_LOCK_CONTENT_SHA256 = (
    "538d677d4a8c0f1382c851d93c9d628e6c4dbebcdebda0a4b652b7bcacb4493a"
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
            "f6b0e49f3230a8d858f7fe30d27f624e629c9e017f351dd4c4c2b92dc6b56f02"
        ),
        "artifact_size": 827808,
        "log_sha256": (
            "7d96670dc3d50d2953874695f616fa9e28f92e746079a79a66e71b06c4fe37e9"
        ),
        "log_size": 25326,
        "record_sha256": {
            SELECTED_RUN: (
                "0a63b0b7e8b1e7e53c882b069d01f6070308e444cd11f208c6aba60367d1b599"
            ),
            REPRODUCTION_RUN: (
                "073f20e802adb55cc85efccc50775f3b49a63d70e30ae9214aff3ad0766f9825"
            ),
        },
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
        "recipe_snapshot_sha256": (
            "6b1ad58cb8ee6cd3f466d6935c8760cea7ca29cb816752f53578885ce8cb35d7"
        ),
        "recipe_snapshot_size": 1980939,
    },
    "armhf": {
        "artifact_sha256": (
            "5a9825a71f88d41f956067d584aaed1e2620856fdb6cb8b45bc81f9ef8c12a43"
        ),
        "artifact_size": 661940,
        "log_sha256": (
            "a526846c10ccc1dd916e21f13976bb4a03218e593ec42fb2979ab4cf5d32d7d3"
        ),
        "log_size": 24971,
        "record_sha256": {
            SELECTED_RUN: (
                "fc828ea597c7be228a13fd05da217ad00c312ea20a9ceda49102fecfe82d1d67"
            ),
            REPRODUCTION_RUN: (
                "ebd6296285f65520c6185824b33835a104784fe73a9da539374a0cff15970b71"
            ),
        },
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:e09ffce413cf62c14a24fd8aa3beebbbfaccd5b0b5223ac529d132f4aabd92b9"
        ),
        "toolchain_archive_sha256": (
            "e2b103c7bf1fdc9bb3ce3cf7bcde9cf2f3fd473fb0d916e8b4d0b4d278fd1afe"
        ),
        "toolchain_archive_size": 784604625,
        "recipe_snapshot_sha256": (
            "a9831ffdb80bf1ec22aa9e28b848b87d88c25510a174613aee536029b398fce3"
        ),
        "recipe_snapshot_size": 1980648,
    },
}
EXPECTED_CONTRACT = {
    "compile_count": 33,
    "compile_pair_sha256": (
        "61e4543b2f6e3b713ceb3615bebf2a943ba2ea74e0aedfa57415e61e8901dd35"
    ),
    "compile_invocation_sha256": {
        "arm64": (
            "8058993976c39e3246212acabbde24df4eb5339e08199ad089d65d900bc49312"
        ),
        "armhf": (
            "1f8d26cf63982712200cf16c9d836ba78ddac5a75d8fa865d5604907aff13473"
        ),
    },
    "link_object_sha256": (
        "8426b2dea08a9d17c1c57f353216afe9e52b183c0eb052a17c2f1245f7127b33"
    ),
    "raw_link_object_sha256": (
        "b1ee2d7695a8ba77b5b09430e60b2805c0d807e22fb4149ef80227043d38e492"
    ),
    "ordered_link_argv_sha256": {
        "arm64": (
            "e9a8958217329891ecfe59c4be0146e932a39e6477a0375a1a5e734d2540179e"
        ),
        "armhf": (
            "7665e3999e2477f8090493e1334c4cb3753eb31efda9c793a9a48da06f663b29"
        ),
    },
    "warning_count": {"arm64": 16, "armhf": 12},
    "note_count": {"arm64": 12, "armhf": 12},
    "diagnostic_member_count": {"arm64": 84, "armhf": 72},
    "diagnostic_lines_sha256": {
        "arm64": (
            "cf587b0459866f1526beaf8f4a6bf1e5734d0ed8501f11139fdafb9db7c919b2"
        ),
        "armhf": (
            "1c0426bf66c38deb6411ed0ef3c384f1e0b25d8ba064d81f67a49799ef607d01"
        ),
    },
}
CAVEAT_TOKENS = (
    "byte for byte",
    "no offline source cache",
    "dockerfile_linkage=unverified-local-cache",
    "33 C compiles",
    "USE_BLARGG_APU=1",
    "Blargg",
    "16 warnings",
    "ARMHF contains exactly 12 memmap array-bounds warnings and 12 notes",
    "Non-commercial",
    "LGPL-2.1-or-later",
    "human legal and policy gate",
    "supports_no_game=false",
    "needs_fullpath=false",
    "no firmware is declared or packaged",
    "State compatibility with the base snes9x2005 core is not claimed",
    "performance and thermals",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all 16 device entries remain ineligible",
)


class Snes9x2005PlusCoreEvidenceTests(unittest.TestCase):
    def test_individual_lifecycle_documents_bind_exact_evidence(self) -> None:
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
        self.assertEqual(
            COMPATIBILITY_CONTENT_SHA256, compatibility["content_sha256"]
        )
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

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected = selection["targets"][architecture]
                golden = selected["golden_record"]
                self.assertEqual(CORE_ID, golden["core_id"])
                self.assertEqual(SOURCE_COMMIT, golden["source"]["commit"])
                self.assertEqual(SOURCE_TREE, golden["source"]["tree"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], selected["artifact"]["sha256"]
                )
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self._assert_individual_references(
                    golden["e2e"]["run_id"],
                    golden["e2e"]["record"],
                    golden["e2e"]["package"],
                    golden["local_record"],
                )
                self._assert_recipe(golden["recipe"])
                self._assert_toolchain(golden["toolchain"], expected)
                snapshot_reference = golden["local_store"]["recipe_snapshots"][
                    architecture
                ]
                self.assertEqual(
                    expected["recipe_snapshot_sha256"], snapshot_reference["sha256"]
                )
                snapshot_path = ROOT / snapshot_reference["path"]
                self.assertEqual(
                    expected["recipe_snapshot_size"], snapshot_path.stat().st_size
                )
                snapshot = load_document(snapshot_path)
                self.assertEqual(9, snapshot["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path, golden, f"{CORE_ID}/{architecture}"
                    ),
                )

        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)
        self._assert_individual_references(
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            SOURCE_LOCK_ID,
            SOURCE_LOCK_PATH,
            compatibility["golden_source"],
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
            selection["e2e"]["run_id"],
        )

    def test_individual_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set_path = ROOT / SOURCE_SET_PATH
        source_set = load_document(source_set_path)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SOURCE_SET_FILE_SHA256, file_sha256(source_set_path))
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
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
        source_lock = load_document(ROOT / SOURCE_LOCK_PATH)
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, file_sha256(ROOT / SOURCE_LOCK_PATH))
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(SOURCE_URL, source_lock["source"]["url"])
        self.assertEqual(SOURCE_COMMIT, source_lock["source"]["commit"])
        self.assertEqual(SOURCE_TREE, source_lock["source"]["tree"])
        self.assertEqual([], source_lock["source"]["submodules"])

        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
        self.assertEqual(16, report["counts"]["devices"])
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
                self.assertEqual("build_golden", cell["tier"])
                self.assertEqual("static-build-only", cell["validation_scope"])
                self.assertEqual(
                    "provisional-unverified", cell["device_eligibility"]
                )
                self.assertEqual(
                    "unverified-local-cache", cell["dockerfile_linkage"]
                )

        self.assertEqual(8, len(report["device_views"]))
        self.assertEqual(
            16, sum(len(view["devices"]) for view in report["device_views"])
        )
        self.assertTrue(
            all(
                view["status"] == "provisional"
                and view["eligibility"] == "provisional-unverified"
                and not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )
        self._assert_individual_references(
            source_set["source_set_id"],
            source_set["evidence_pin"]["path"],
            source_set["evidence_pin"]["pin_id"],
            source["path"],
            source["source_lock_id"],
        )

    def test_individual_channels_and_release_bind_semantic_artifacts(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer_path = (
                    ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
                )
                pointer = load_document(pointer_path)
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self._assert_individual_references(
                    str(pointer_path.relative_to(ROOT)),
                    pointer["target"]["id"],
                    pointer["target"]["path"],
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
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])
        self.assertEqual(PACKAGE_SIZE, release["assets"][0]["size"])
        self._assert_individual_references(
            release["release_id"],
            release["assets"][0]["path"],
            str((release_root / "release-manifest.json").relative_to(ROOT)),
        )

    def test_selected_and_reproduction_runs_are_byte_reproducible(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                self._assert_individual_references(run_id)
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence_path = run_root / "e2e-record.json"
                evidence = load_document(evidence_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
                self.assertEqual(E2E_CONTENT_SHA256[run_id], evidence["content_sha256"])
                self.assertEqual(run_id, evidence["run_id"])
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    [CORE_ID], [item["core_id"] for item in evidence["packages"]]
                )

                package = evidence["packages"][0]
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                self.assertEqual(PACKAGE_SIZE, package["size"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/snes9x2005_plus_libretro.so",
                            "cores/snes9x2005_plus_libretro.so",
                            "snes9x2005_plus_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )
                    package_manifest = json.loads(archive.read("manifest.json"))
                    self.assertEqual(CORE_ID, package_manifest["core_id"])
                    self.assertTrue(package_manifest["local_only"])
                    self.assertEqual("disabled", package_manifest["publication"])
                    self.assertEqual(
                        METADATA_SHA256, package_manifest["metadata"]["sha256"]
                    )
                    for architecture, expected in TARGETS.items():
                        self.assertEqual(
                            expected["artifact_sha256"],
                            package_manifest["artifacts"][architecture]["sha256"],
                        )
                        self.assertEqual(
                            SOURCE_COMMIT,
                            package_manifest["artifacts"][architecture][
                                "source_commit"
                            ],
                        )

                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        record_path = (
                            run_root / CORE_ID / architecture / "build-record.json"
                        )
                        record = load_document(record_path)
                        self.assertEqual(
                            expected["record_sha256"][run_id], file_sha256(record_path)
                        )
                        self.assertEqual(SOURCE_COMMIT, record["source"]["commit"])
                        self.assertEqual(SOURCE_TREE, record["source"]["tree"])
                        self.assertEqual([], record["source"]["submodules"])
                        self.assertEqual(
                            {
                                "compiler_scope": "c",
                                "derivation": "native-space-short7-v1",
                                "value": " b603569",
                            },
                            record["build"]["git_version"],
                        )
                        self.assertEqual(
                            {"USE_BLARGG_APU": 1},
                            record["build"]["make_variables"],
                        )
                        self._assert_recipe(record["recipe"])
                        self._assert_toolchain(record["toolchain"], expected)

                        log_path = record_path.parent / record["build"]["log"]
                        self.assertEqual(expected["log_sha256"], file_sha256(log_path))
                        self.assertEqual(expected["log_size"], log_path.stat().st_size)
                        log_text = log_path.read_text(encoding="utf-8")
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
                            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_WARNING_COUNT[
                                architecture
                            ],
                            sum(
                                "warning:" in line.casefold()
                                for line in log_text.splitlines()
                            ),
                        )
                        self.assertEqual(
                            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_NOTE_COUNT[
                                architecture
                            ],
                            sum(
                                "note:" in line.casefold()
                                for line in log_text.splitlines()
                            ),
                        )
                        logs[architecture].append(log_path.read_bytes())

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        self.assertEqual(METADATA_SIZE, metadata_path.stat().st_size)
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "v1.36"', metadata)
                        self.assertIn(b'license = "Non-commercial"', metadata)
                        self.assertIn(b'supports_no_game = "false"', metadata)
                        self.assertIn(b'needs_fullpath = "false"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        self.assertEqual(
                            expected["artifact_size"], artifact_path.stat().st_size
                        )
                        artifacts[architecture].append(artifact_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_registered_contract_binds_exact_compile_link_and_diagnostics(self) -> None:
        self.assertEqual(
            EXPECTED_CONTRACT["compile_count"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["compile_pair_sha256"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["compile_invocation_sha256"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["link_object_sha256"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["raw_link_object_sha256"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_RAW_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["ordered_link_argv_sha256"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_ORDERED_LINK_ARGV_SHA256,
        )
        self.assertEqual(
            (
                "-fPIC",
                "-shared",
                "-Wl,--no-undefined",
                "-Wl,--version-script=link.T",
                "-lm",
            ),
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_LINK_OPTIONS,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["warning_count"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_WARNING_COUNT,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["note_count"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_NOTE_COUNT,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["diagnostic_member_count"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_MEMBER_COUNT,
        )
        self.assertEqual(
            EXPECTED_CONTRACT["diagnostic_lines_sha256"],
            snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_LINES_SHA256,
        )
        self.assertEqual(
            {"USE_BLARGG_APU": 1},
            snes9x2005_plus.SNES9X2005_PLUS_MAKE_VARIABLES,
        )
        self.assertEqual(
            " b603569", snes9x2005_plus.SNES9X2005_PLUS_NATIVE_GIT_VERSION
        )

    def _assert_recipe(self, recipe: dict[str, object]) -> None:
        self.assertEqual(CORE_ID, recipe["core_id"])
        self.assertEqual(
            ".github/workflows/build-snes9x2005_plus.yml", recipe["workflow"]
        )
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
        self.assertEqual(
            CONTRACT_FILE_SHA256,
            files["scripts/core_pipeline_lib/contracts/snes9x2005_plus.py"],
        )
        self.assertEqual(
            COMMON_CONTRACT_FILE_SHA256,
            files["scripts/core_pipeline_lib/contracts/snes9x2005_common.py"],
        )
        self.assertEqual(
            CONTRACT_REGISTRY_FILE_SHA256,
            files["scripts/core_pipeline_lib/contracts/registry.py"],
        )

    def _assert_toolchain(
        self, toolchain: dict[str, object], expected: dict[str, object]
    ) -> None:
        self.assertEqual("unverified-local-cache", toolchain["dockerfile_linkage"])
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

    def _assert_individual_references(self, *references: str) -> None:
        for reference in references:
            self.assertNotIn(RESERVED_HISTORY_TOKEN, reference.casefold(), reference)


if __name__ == "__main__":
    unittest.main()
