"""Focused FBNeo catalog, workflow, schema, and pending-state tests."""

from __future__ import annotations

import unittest

from .support import pipeline
from core_pipeline_lib.contracts import fbneo

from .support import ROOT, load_document


CORE_ID = "fbneo"
SOURCE_URL = "https://github.com/libretro/FBNeo.git"
SOURCE_COMMIT = "9d7716aa20cbdf49024f42980c33c7cd366e784f"
SOURCE_TREE = "e533af34d2db18f11cefadbb93e509579580d0b7"
SOURCE_DATE_EPOCH = 1777823586
NATIVE_VERSION = {
    "derivation": "fbneo-native-short9-date-v1",
    "value": "9d7716aa2",
    "git_date": "260503",
    "compiler_scope": "cxx",
}
ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=1",
    "HWCAP2_CRC32=16",
    "HWCAP2_SHA1=4",
    "HWCAP2_SHA2=8",
]
FORBIDDEN_NEEDED_PREFIXES = [
    "libEGL",
    "libGL",
    "libGLES",
    "libOpenGL",
    "libSDL",
    "libz",
]


class FbneoManifestTests(unittest.TestCase):
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
        self.assertEqual(
            {
                "driver": "libretro-super",
                "source_key": CORE_ID,
                "source_dir": "libretro-fbneo",
                "output_path": "dist/unix/fbneo_libretro.so",
                "artifact_name": "fbneo_libretro.so",
                "compile_definitions": {
                    "armhf": ARMHF_COMPILE_DEFINITIONS,
                },
                "source_date_epoch": SOURCE_DATE_EPOCH,
                "git_version": NATIVE_VERSION,
                "overlays": {
                    "arm64": [dict(fbneo.FBNEO_SORT_OVERLAY)],
                    "armhf": [dict(fbneo.FBNEO_SORT_OVERLAY)],
                },
            },
            self.spec["build"],
        )
        self.assertEqual(
            {
                "source_path": (
                    "/libretro-super/dist/info/fbneo_libretro.info"
                ),
                "artifact_name": "fbneo_libretro.info",
            },
            self.spec["metadata"],
        )
        self.assertEqual(
            FORBIDDEN_NEEDED_PREFIXES,
            self.spec["validation"]["forbidden_needed_prefixes"],
        )
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertNotIn("replacement", self.spec["metadata"])
        self.assertNotIn("make_variables", self.spec["build"])
        self.assertNotIn("recipe_profile", self.spec["build"])

    def test_workflow_is_a_read_only_shared_pipeline_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertIn("timeout-minutes: 45", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core fbneo", workflow)
        self.assertIn(
            "scripts/toolchain_archive.py verify-downloads", workflow
        )
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)

    def test_schemas_bind_closed_catalog_source_and_golden_shapes(
        self,
    ) -> None:
        catalog_schema = load_document(
            ROOT / "manifests/core-builds.schema.json"
        )
        self.assertNotIn(
            "fbneo",
            catalog_schema["properties"]["cores"].get(
                "properties", {}
            ),
        )
        version_schema = catalog_schema["$defs"]["fbneoNativeVersion"]
        self.assertEqual(
            {"derivation", "value", "git_date", "compiler_scope"},
            set(version_schema["required"]),
        )
        self.assertFalse(version_schema["additionalProperties"])
        self.assertEqual(
            NATIVE_VERSION,
            {
                key: value["const"]
                for key, value in version_schema["properties"].items()
            },
        )
        golden_schema = load_document(
            ROOT / "manifests/golden-start.schema.json"
        )
        build_golden = golden_schema["$defs"]["buildGolden"]
        branch = next(
            candidate
            for candidate in build_golden["dependentSchemas"]["build"]
            ["then"]["oneOf"]
            if candidate["properties"]["core_id"].get("const") == CORE_ID
        )
        golden_build = branch["properties"]["build"]
        self.assertEqual(
            {
                "driver",
                "environment",
                "compile_definitions",
                "git_version",
                "source_date_epoch",
                "log",
                "log_sha256",
            },
            set(golden_build["required"]),
        )
        self.assertEqual(
            set(golden_build["required"]),
            set(golden_build["propertyNames"]["enum"]),
        )
        self.assertEqual(
            {"$ref": "#/$defs/fbneoNativeVersion"},
            golden_build["properties"]["git_version"],
        )
        self.assertEqual(
            [{"const": []}, {"const": ARMHF_COMPILE_DEFINITIONS}],
            golden_build["properties"]["compile_definitions"]["oneOf"],
        )
        target_branches = branch["allOf"]
        expected_by_arch = {
            "arm64": [],
            "armhf": ARMHF_COMPILE_DEFINITIONS,
        }
        for target_branch in target_branches:
            architecture = target_branch["if"]["properties"]["architecture"][
                "const"
            ]
            self.assertEqual(
                expected_by_arch[architecture],
                target_branch["then"]["properties"]["build"]["properties"]
                ["compile_definitions"]["const"],
            )
        core_golden_schema = load_document(
            ROOT / "manifests/core-golden.schema.json"
        )
        wrappers = (
            core_golden_schema["properties"]["build_goldens"]
            ["additionalProperties"]["additionalProperties"]["allOf"]
        )
        wrapper = next(
            item
            for item in wrappers
            if item.get("if", {}).get("properties", {}).get("core_id", {})
            .get("const")
            == CORE_ID
        )
        self.assertEqual(["build"], wrapper["then"]["required"])

    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/fbneo.json"
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
            (ROOT / "manifests/compatibility/pending/fbneo.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
