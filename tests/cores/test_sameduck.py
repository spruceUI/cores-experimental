"""Focused sameduck catalog, workflow, contract, and object-naming tests."""

from __future__ import annotations

import dataclasses
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import sameduck
from core_pipeline_lib.contracts.c_only import c_only_log_proves_contract

from .support import ROOT, load_document


CORE_ID = "sameduck"
SOURCE_URL = "https://github.com/libretro/sameduck.git"
SOURCE_COMMIT = "f0286ee9d6c44950d9a442463ffdb1ff014a5d5b"
SOURCE_TREE = "c04c4f24a078b55386a1c62ae3619dde5b5087d9"
SELECTED_RUN = "actions-sim-build-core-sameduck-w3"
REPRODUCTION_RUN = "build-core-sameduck-local-w3"


class SameduckManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/SameDuck-libretro",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual("libretro-sameduck", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(sameduck.sameduck_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(sameduck.sameduck_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core sameduck", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class SameduckCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/sameduck.json"
        compatibility = load_document(compatibility_path)
        report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual("valid", report["status"], report["errors"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/sameduck.json").exists()
        )


class SameduckContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_contract_uses_sha_pinned_object_names(self) -> None:
        # the load-bearing relaxation: sameduck names objects
        # build/obj/<path>/<name>_libretro.c.o, not <stem>.o
        self.assertTrue(
            sameduck.SAMEDUCK_LOG_CONTRACT.sha_pinned_object_names
        )
        self.assertEqual(
            (("..//", ""),),
            sameduck.SAMEDUCK_LOG_CONTRACT.semantic_path_aliases,
        )

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    sameduck.sameduck_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the sameduck contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local sameduck build logs present")

    def test_strict_object_naming_would_reject(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local sameduck build log present")
        strict = dataclasses.replace(
            sameduck.SAMEDUCK_LOG_CONTRACT, sha_pinned_object_names=False
        )
        self.assertFalse(
            c_only_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, strict
            )
        )


if __name__ == "__main__":
    unittest.main()
