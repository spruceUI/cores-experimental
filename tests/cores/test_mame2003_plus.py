"""Focused MAME 2003-Plus catalog, workflow, and pending-state tests."""

from __future__ import annotations

import copy
import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, load_document


CORE_ID = "mame2003_plus"
SOURCE_URL = "https://github.com/libretro/mame2003-plus-libretro.git"
SOURCE_COMMIT = "5373e38e1091eb28f075513ecdc2575bafc8a5e3"
SOURCE_TREE = "990e22f33a33cbfe733e22b3b5fef6cda76056fb"
SOURCE_DATE_EPOCH = 1777763287
NATIVE_GIT_VERSION = {
    "derivation": "native-space-short8-v1",
    "value": " 5373e38e",
    "compiler_scope": "c",
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
SOURCE_RECORD = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
}


class Mame2003PlusManifestTests(unittest.TestCase):
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
                "source_dir": "libretro-mame2003_plus",
                "output_path": "dist/unix/mame2003_plus_libretro.so",
                "artifact_name": "mame2003_plus_libretro.so",
                "source_date_epoch": SOURCE_DATE_EPOCH,
                "git_version": NATIVE_GIT_VERSION,
            },
            self.spec["build"],
        )
        self.assertEqual(
            {
                "source_path": (
                    "/libretro-super/dist/info/"
                    "mame2003_plus_libretro.info"
                ),
                "artifact_name": "mame2003_plus_libretro.info",
            },
            self.spec["metadata"],
        )
        self.assertEqual(
            FORBIDDEN_NEEDED_PREFIXES,
            self.spec["validation"]["forbidden_needed_prefixes"],
        )
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertNotIn("replacement", self.spec["metadata"])
        self.assertNotIn("recipe_profile", self.spec["build"])

    def test_shared_source_contract_rejects_noncanonical_resolved_url(
        self,
    ) -> None:
        self.assertTrue(
            pipeline.native_git_version_golden_source_is_well_formed(
                CORE_ID, SOURCE_RECORD
            )
        )
        changed = copy.deepcopy(SOURCE_RECORD)
        changed["resolved_url"] = SOURCE_URL.removesuffix(".git")
        self.assertFalse(
            pipeline.native_git_version_golden_source_is_well_formed(
                CORE_ID, changed
            )
        )

    def test_workflow_is_a_read_only_shared_pipeline_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertIn("timeout-minutes: 45", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core mame2003_plus", workflow)
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
            "mame2003_plus",
            catalog_schema["properties"]["cores"].get(
                "properties", {}
            ),
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
        wrapper = next(
            item
            for item in wrappers
            if item.get("if", {}).get("properties", {}).get("core_id", {})
            .get("const")
            == CORE_ID
        )
        self.assertEqual(["build"], wrapper["then"]["required"])

    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/mame2003_plus.json"
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
            (ROOT / "manifests/compatibility/pending/mame2003_plus.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
