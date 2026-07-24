"""Focused fake-08 direct-make, workflow, contract, and driver tests."""

from __future__ import annotations

import dataclasses
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import fake08
from core_pipeline_lib.contracts.mixed_language import (
    mixed_language_log_proves_contract,
)

from .support import ROOT, load_document


CORE_ID = "fake08"
SOURCE_URL = "https://github.com/jtothebell/fake-08.git"
SOURCE_COMMIT = "814991a2571ad3970e386cef48f3b148aa1c27b9"
SOURCE_TREE = "5c4f211679d422eb7ac5883730b4a9d583a27fef"
SELECTED_RUN = "actions-sim-build-core-fake08-v1"
REPRODUCTION_RUN = "build-core-fake08-local-v1"


class Fake08ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_direct_make_recipe_with_subdir_and_args(self) -> None:
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
        self.assertEqual("direct-make", build["driver"])
        self.assertEqual("platform/libretro", build["make_subdir"])
        self.assertEqual(["V=1"], build["make_args"])
        self.assertNotIn("platforms", build)
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(fake08.fake08_spec_is_well_formed(self.spec))
        mutated = {
            **self.spec,
            "build": {**self.spec["build"], "make_args": ["V=0"]},
        }
        self.assertFalse(fake08.fake08_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core fake08", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class Fake08CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/fake08.json"
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
            (ROOT / "manifests/compatibility/pending/fake08.json").exists()
        )


class Fake08ContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_contract_admits_c_sources_under_the_cxx_compiler(self) -> None:
        # the load-bearing relaxation: fake08's Makefile sets CC = $(CXX)
        self.assertTrue(
            fake08.FAKE08_LOG_CONTRACT.cxx_compiler_compiles_c
        )
        self.assertEqual(
            {"c": 36, "cxx": 20},
            dict(fake08.FAKE08_LOG_CONTRACT.expected_language_counts),
        )

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    fake08.fake08_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the fake08 contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local fake08 build logs present")

    def test_strict_compiler_language_check_would_reject(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local fake08 build log present")
        strict = dataclasses.replace(
            fake08.FAKE08_LOG_CONTRACT, cxx_compiler_compiles_c=False
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, strict
            )
        )


if __name__ == "__main__":
    unittest.main()
