"""Focused PicoDrive catalog, workflow, and pending-state tests."""

from __future__ import annotations

import hashlib
import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, file_sha256, load_document


CORE_ID = "picodrive"
SOURCE_URL = "https://github.com/libretro/picodrive.git"
SOURCE_COMMIT = "f0d4a0118a9733a1f10bce5a4ac772c474f9300d"
SOURCE_TREE = "a9e95a725edb219535032f18d03677361d5657bc"
SOURCE_DATE_EPOCH = 1775134253
COMPILE_DEFINITIONS = {
    "armhf": [
        "HWCAP2_AES=1",
        "HWCAP2_CRC32=16",
        "HWCAP2_SHA1=4",
        "HWCAP2_SHA2=8",
    ]
}
RECIPE_PROFILE = {
    "kind": "picodrive-v1",
    "git_revision": "-f0d4a011",
    "armhf_host_tools": {
        "CYCLONE_CC": "gcc",
        "CYCLONE_CXX": "g++",
    },
}
FORBIDDEN_NEEDED_PREFIXES = [
    "libEGL",
    "libGL",
    "libGLES",
    "libOpenGL",
    "libSDL",
    "libstdc++",
    "libz",
]
METADATA_REPLACEMENT = {
    "kind": "whole-file-v1",
    "path": "metadata/picodrive/source-v1.info",
    "preimage_sha256": (
        "35cef57b4b61d95a86e1ceee3a7c325d9d16bbdc136b4b3a556e808864de06c5"
    ),
    "replacement_sha256": (
        "ee4443f075c57c90b4d7a99c3a7c7e54ee141b21899dc88a3c8c52152556e181"
    ),
}
RECURSIVE_SUBMODULES = [
    {
        "state": " ",
        "commit": "3ac7cf1bdeecb60e2414980e8dc72ff092f69769",
        "path": "cpu/cyclone",
    },
    {
        "state": " ",
        "commit": "e62ac5995b1c7ef65ece35293914843b8ee57d49",
        "path": "pico/cd/libchdr",
    },
    {
        "state": " ",
        "commit": "a2dfc20ff507e4fd075cd325620bcea655e2c1f7",
        "path": "pico/sound/emu2413",
    },
    {
        "state": " ",
        "commit": "dd762b861ecadf5ddd5fb03e9ca1db6707b54fbb",
        "path": "platform/common/dr_libs",
    },
    {
        "state": " ",
        "commit": "d1a166c83ab445b1c14bc83d37c84e18d172e5f5",
        "path": "platform/common/dr_libs/tests/external/miniaudio",
    },
    {
        "state": " ",
        "commit": "9ed5822606dd7ff20a782a882e8fd611cb53ba88",
        "path": "platform/libpicofe",
    },
]


class PicoDriveManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog_path = ROOT / "manifests/core-builds.json"
        self.catalog = load_document(self.catalog_path)
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_source_recipe_and_real_outputs(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        build = self.spec["build"]
        self.assertEqual("libretro-super", build["driver"])
        self.assertEqual("picodrive", build["source_key"])
        self.assertEqual("libretro-picodrive", build["source_dir"])
        self.assertEqual(
            "libretro-picodrive/picodrive_libretro.so", build["output_path"]
        )
        self.assertEqual("picodrive_libretro.so", build["artifact_name"])
        self.assertEqual(SOURCE_DATE_EPOCH, build["source_date_epoch"])
        self.assertEqual(COMPILE_DEFINITIONS, build["compile_definitions"])
        self.assertEqual(RECIPE_PROFILE, build["recipe_profile"])
        self.assertNotIn("arm64", build["compile_definitions"])
        self.assertNotIn("git_version", build)

        self.assertEqual(
            {
                "source_path": (
                    "/libretro-super/dist/info/picodrive_libretro.info"
                ),
                "artifact_name": "picodrive_libretro.info",
                "replacement": METADATA_REPLACEMENT,
            },
            self.spec["metadata"],
        )
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertEqual(
            FORBIDDEN_NEEDED_PREFIXES,
            self.spec["validation"]["forbidden_needed_prefixes"],
        )

    def test_metadata_replacement_only_corrects_the_source_version(self) -> None:
        path = ROOT / METADATA_REPLACEMENT["path"]
        replacement = path.read_bytes()
        old = b'display_version = "1.99"'
        new = b'display_version = "2.05"'
        self.assertEqual(0, replacement.count(old))
        self.assertEqual(1, replacement.count(new))
        preimage = replacement.replace(new, old)
        self.assertEqual(
            METADATA_REPLACEMENT["preimage_sha256"],
            hashlib.sha256(preimage).hexdigest(),
        )
        self.assertEqual(
            METADATA_REPLACEMENT["replacement_sha256"], file_sha256(path)
        )

    def test_workflow_is_a_read_only_shared_pipeline_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core picodrive", workflow)
        self.assertIn("scripts/toolchain_archive.py verify-downloads", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)

    def test_schemas_bind_the_closed_recipe_and_recursive_source_graph(
        self,
    ) -> None:
        catalog_schema = load_document(
            ROOT / "manifests/core-builds.schema.json"
        )
        self.assertEqual(
            {"$ref": "#/$defs/core"},
            catalog_schema["properties"]["cores"][
                "properties"
            ]["picodrive"],
        )
        self.assertEqual(
            RECIPE_PROFILE,
            {
                "kind": catalog_schema["$defs"]["picodriveRecipeProfile"]
                ["properties"]["kind"]["const"],
                "git_revision": catalog_schema["$defs"]
                ["picodriveRecipeProfile"]["properties"]["git_revision"]
                ["const"],
                "armhf_host_tools": {
                    key: value["const"]
                    for key, value in catalog_schema["$defs"]
                    ["picodriveRecipeProfile"]["properties"]
                    ["armhf_host_tools"]["properties"].items()
                },
            },
        )
        generic_build = (
            catalog_schema["$defs"]["nonNativeCore"]["allOf"][1]
            ["properties"]["build"]
        )
        self.assertEqual(
            {"required": ["recipe_profile"]}, generic_build["not"]
        )
        golden_schema = load_document(
            ROOT / "manifests/golden-start.schema.json"
        )
        core_golden_schema = load_document(
            ROOT / "manifests/core-golden.schema.json"
        )
        wrappers = (
            core_golden_schema["properties"]["build_goldens"]
            ["additionalProperties"]["additionalProperties"]["allOf"]
        )
        picodrive_wrapper = next(
            item
            for item in wrappers
            if item.get("if", {}).get("properties", {}).get("core_id", {})
            .get("const")
            == CORE_ID
        )
        self.assertEqual(
            ["build"], picodrive_wrapper["then"]["required"]
        )

    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/picodrive.json"
        compatibility = load_document(compatibility_path)
        report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual("valid", report["status"], report["errors"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/picodrive.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
