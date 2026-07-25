"""Pinned Snes9x 2005 Plus individual lifecycle tests."""

from __future__ import annotations

import json
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import snes9x2005_plus

from .support import ROOT, file_sha256, load_core_documents, load_document
from .support import evidence_handles


CORE_ID = "snes9x2005_plus"
OTHER_CORE_ID = "snes9x2005"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_LOCK_PATH = _H["SOURCE_LOCK_PATH"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SOURCE_URL = _H["SOURCE_URL"]
SOURCE_LOCK_FILE_SHA256 = _H["SOURCE_LOCK_FILE_SHA256"]
SOURCE_LOCK_CONTENT_SHA256 = _H["SOURCE_LOCK_CONTENT_SHA256"]
SOURCE_SET_FILE_SHA256 = _H["SOURCE_SET_FILE_SHA256"]
SOURCE_SET_CONTENT_SHA256 = _H["SOURCE_SET_CONTENT_SHA256"]
PIN_FILE_SHA256 = _H["PIN_FILE_SHA256"]
PIN_CONTENT_SHA256 = _H["PIN_CONTENT_SHA256"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
PACKAGE_SHA256 = _H["PACKAGE_SHA256"]
PACKAGE_SIZE = _H["PACKAGE_SIZE"]
RECIPE_HEAD = _H["RECIPE_HEAD"]
CORE_SPEC_SHA256 = _H["CORE_SPEC_SHA256"]
CATALOG_SHA256 = _H["CATALOG_SHA256"]
PIPELINE_SHA256 = _H["PIPELINE_SHA256"]
PIPELINE_BUNDLE_CONTENT_SHA256 = _H["PIPELINE_BUNDLE_CONTENT_SHA256"]
WORKFLOW_SHA256 = _H["WORKFLOW_SHA256"]
TOOLCHAIN_LOCK_FILE_SHA256 = _H["TOOLCHAIN_LOCK_FILE_SHA256"]
TOOLCHAIN_LOCK_CONTENT_SHA256 = _H["TOOLCHAIN_LOCK_CONTENT_SHA256"]
LIBRETRO_SUPER_COMMIT = _H["LIBRETRO_SUPER_COMMIT"]
TARGETS = _H["TARGETS"]

RESERVED_HISTORY_TOKEN = "tranche"

CONTRACT_FILE_SHA256 = (
    "7762f45b058ebe117639f4f4cee5cf6cebc4ff853a2298421e3a2064cc175f4a"
)

COMMON_CONTRACT_FILE_SHA256 = (
    "9d5e0788272dd7a53473b99bd84e48a152345f25082e89d171a9f411d750e2de"
)

CONTRACT_REGISTRY_FILE_SHA256 = (
    "f20d87f0379059351c7a2fee3daf2bb33186efa79c617dad1363c143fafddca5"
)

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
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)


    def test_individual_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

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
        source_lock = registry.composed_source_lock(CORE_ID)
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
