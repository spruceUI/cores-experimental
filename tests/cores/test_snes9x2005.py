"""Pinned Snes9x 2005 individual lifecycle tests."""

from __future__ import annotations

import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import snes9x2005

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "snes9x2005"
OTHER_CORE_ID = "snes9x"
PIN_NAME = "snes9x2005-b60356971fc9-23fbb6c59d54.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/snes9x2005/"
    "b60356971fc9caae02cd0853676dced886a08be7.json"
)
SOURCE_LOCK_ID = "snes9x2005-b60356971fc9"
SOURCE_COMMIT = "b60356971fc9caae02cd0853676dced886a08be7"
SOURCE_TREE = "5a13440308796f67a77f7e8fc16bbeee61ab301d"
SOURCE_URL = "https://github.com/libretro/snes9x2005.git"
SOURCE_LOCK_FILE_SHA256 = (
    "99f564cd05976e52b616f03836b4e9317e43a72a34c7920fc5c278b70b1ae8cf"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "fc58d405652e984a9bb7cd44e2fb640bf83e926438d3f97519fdbb9098e14a65"
)
SOURCE_SET_FILE_SHA256 = (
    "35a538bdadd8cda3f503ff6f49f6c3e46c1cb56077f730ca909ae3a9e1fe9e04"
)
SOURCE_SET_CONTENT_SHA256 = (
    "5f63fbeea0aa74e5ca433784f5b95230d1db5ae27b6594bf50aa5f757d8e5189"
)
PIN_FILE_SHA256 = (
    "556e1a078634287ffbf2c731f9eac166530741416ccd89d2574e2c5f39cb7098"
)
PIN_CONTENT_SHA256 = (
    "80c79e0cb6fff5bc820683850b7574d330ecf909550cb2875d82fbc6084c084c"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "d67d0e3701c9009384c215a8f633ef0729aa1e4a91cb0529173664ffa4a68fc6"
)
SELECTION_SHA256 = (
    "23fbb6c59d54e35431022dfad885fef4438935faf8588cb65a6439a1d9f41100"
)
SELECTED_RUN = "actions-sim-build-core-snes9x2005-w3"
REPRODUCTION_RUN = "build-core-snes9x2005-local-w3"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "a452b164c4e64793f95ce5c7ab396bd379674202056e9d5138405341572b0407"
    ),
    REPRODUCTION_RUN: (
        "17e9b71569aeb9796908a4c50f190c4e65865b51c75f63867fed513243518523"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "7e7574f6ce96a30b58c78c880fa6793e5ac23fd2048f6d7425e2a8e3f0dfbebe"
    ),
    REPRODUCTION_RUN: (
        "f88a85c925f7333fa52df20eff53054e48773d586391833a271ec307b6cf47c3"
    ),
}
PACKAGE_SHA256 = (
    "defdcff77c68c774d4707dc6638974ac6d7583b99f089d9825e893c3fa8da19c"
)
PACKAGE_SIZE = 525268
METADATA_SHA256 = (
    "b77d8b7338e11ac85d7e60106ff56579862ec3fc64c2c58c01912537e2e2620c"
)
METADATA_SIZE = 1402
RECIPE_HEAD = "9d95cda3d6dce32c8d33d85a58f37adad19d38d7"
CORE_SPEC_SHA256 = (
    "2384a8a9b4c6d5efa2c3b5ced5c9d933d2984f396802d6283b81456b3bfd4f1d"
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
    "29dec7c13f7abe6b9a072574efb4f19623cd8dacb75acb59632b7bd56fc26a41"
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
            "c6b13597f672643978e3c24e267f5967d24c47a5f4861d8424ca34585ba5bbe9"
        ),
        "artifact_size": 913696,
        "log_sha256": (
            "273f7b734f59202d17a5372e044106fdff2dafb9a3ae0417c4b23fb55ad9ab1b"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "ea2446b201ead9ccb9bf8cac78d511150ae742103ce19a9449c94da5e05309bf"
            ),
            REPRODUCTION_RUN: (
                "d2ef26afc13936020ff2a8c79bb4e4781e6a846e93920f246ae8aee6bdf0232d"
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
            "012b69735182e547c00b472384c61beb1cf4f9936c0027b4788f054edb9cf3e6"
        ),
    },
    "armhf": {
        "artifact_sha256": (
            "4f1bc67226079460aee765875a7036747b798424d14dfe077c7b28b43f25a80b"
        ),
        "artifact_size": 753224,
        "log_sha256": (
            "49c9b4984c1785de5e639e4bee051e755e7c02a2004e9ef1b88230ce01e351eb"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "520b90b127d7186f3aee3dafa544ed77b375245557bcc407dde1848720ac7cf4"
            ),
            REPRODUCTION_RUN: (
                "7705897a27368a22d23e5673d0d79e628be1ac14b184dd1542da2d0238ca009b"
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
            "a1bba9a896a4b75a236cc336a4ea3d3ee471c8887d2791ec4ce236605d447204"
        ),
    },
}
CAVEAT_TOKENS = (
    "both ABI logs byte for byte",
    "no offline source cache",
    "dockerfile_linkage=unverified-local-cache",
    "35 C compiles",
    "12 reviewed array-bounds warnings",
    "USE_BLARGG_APU=0",
    "Non-commercial",
    "human legal and policy gate",
    "supports_no_game=false",
    "in-memory loading",
    "target-runtime",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all 16 device entries remain ineligible",
)


class Snes9x2005CoreEvidenceTests(unittest.TestCase):
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
                self._assert_recipe(golden["recipe"])
                self._assert_toolchain(golden["toolchain"], expected)
                snapshot_reference = golden["local_store"]["recipe_snapshots"][
                    architecture
                ]
                self.assertEqual(
                    expected["recipe_snapshot_sha256"], snapshot_reference["sha256"]
                )
                snapshot_path = ROOT / snapshot_reference["path"]
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
        for active_reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            compatibility["golden_source"],
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
        ):
            self.assertNotIn("tranche", active_reference.casefold())

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
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(SOURCE_URL, source_lock["source"]["url"])
        self.assertEqual(SOURCE_COMMIT, source_lock["source"]["commit"])
        self.assertEqual(SOURCE_TREE, source_lock["source"]["tree"])
        self.assertEqual([], source_lock["source"]["submodules"])

        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
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
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_individual_channels_and_release_bind_semantic_artifacts(self) -> None:
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
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", pointer["target"]["path"].casefold())

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
                self.assertNotIn("tranche", run_id.casefold())
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence_path = run_root / "e2e-record.json"
                evidence = load_document(evidence_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
                self.assertEqual(E2E_CONTENT_SHA256[run_id], evidence["content_sha256"])
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
                            "cores64/snes9x2005_libretro.so",
                            "cores/snes9x2005_libretro.so",
                            "snes9x2005_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
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
                        self._assert_recipe(record["recipe"])
                        self._assert_toolchain(record["toolchain"], expected)

                        log_path = record_path.parent / record["build"]["log"]
                        self.assertEqual(expected["log_sha256"], file_sha256(log_path))
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
                            snes9x2005.SNES9X2005_EXPECTED_WARNING_COUNT,
                            sum(
                                "warning:" in line.casefold()
                                for line in log_text.splitlines()
                            ),
                        )
                        self.assertEqual(
                            snes9x2005.SNES9X2005_EXPECTED_NOTE_COUNT,
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

    def _assert_recipe(self, recipe: dict[str, object]) -> None:
        self.assertEqual(CORE_ID, recipe["core_id"])
        self.assertEqual(".github/workflows/build-snes9x2005.yml", recipe["workflow"])
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
        self.assertIn("scripts/core_pipeline_lib/contracts/snes9x2005.py", files)

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


if __name__ == "__main__":
    unittest.main()
