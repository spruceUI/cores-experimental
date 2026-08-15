"""Focused parallel_n64 catalog, make-variable, GLES, and contract tests."""

from __future__ import annotations

import copy
import dataclasses
import unittest

from .support import pipeline
from core_pipeline_lib.contracts import parallel_n64
from core_pipeline_lib.contracts.c_asm import c_asm_log_proves_contract

from .support import evidence_handles, ROOT, load_document


CORE_ID = "parallel_n64"
_H = evidence_handles(CORE_ID)
SOURCE_URL = "https://github.com/libretro/parallel-n64.git"
SOURCE_COMMIT = "00c6c9df91d2c2daaae615cefad7911be556fbfa"
SOURCE_TREE = "d762ea5fe18afe5f245080082148005f1c7ce811"
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]


class ParallelN64ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
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
            "libretro-parallel_n64", self.spec["build"]["source_dir"]
        )

    def test_core_is_shipped_and_built_arm64_only(self) -> None:
        self.assertEqual(["arm64"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(
            parallel_n64.parallel_n64_spec_is_well_formed(self.spec)
        )
        mutated = copy.deepcopy(self.spec)
        mutated["targets"] = ["arm64", "armhf"]
        self.assertFalse(
            parallel_n64.parallel_n64_spec_is_well_formed(mutated)
        )

    def test_reviewed_make_variables_select_aarch64_and_gles(self) -> None:
        variables = self.spec["build"]["make_variables"]
        self.assertEqual(
            {"GLES": 1, "NOSSE": 1, "WITH_DYNAREC": "aarch64"}, variables
        )
        self.assertEqual(
            parallel_n64.PARALLEL_N64_MAKE_PROFILE,
            pipeline.make_variable_profile(variables),
        )
        # The string value is admitted only by this exact reviewed profile.
        for bad in ("aarch64 ", "$(shell id)", "", "arm64;rm"):
            mutated = dict(variables, WITH_DYNAREC=bad)
            self.assertIsNone(pipeline.make_variable_profile(mutated), bad)

    def test_make_variables_reach_the_build_as_canonical_makeflags(
        self,
    ) -> None:
        self.assertEqual(
            "GLES=1 NOSSE=1 WITH_DYNAREC=aarch64",
            pipeline.canonical_makeflags(self.spec),
        )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core parallel_n64", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class ParallelN64CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/parallel_n64.json"
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
        self.assertEqual({"arm64"}, set(compatibility["targets"]))

    def test_artifact_needs_a_gles_provider(self) -> None:
        """The one catalog core that links GL directly, not via the frontend."""

        compatibility = load_document(
            ROOT / "manifests/compatibility/parallel_n64.json"
        )
        self.assertIn(
            "libGLESv2.so.2", compatibility["targets"]["arm64"]["needed"]
        )


class ParallelN64ContractTests(unittest.TestCase):
    def _log(self, run_id: str) -> str | None:
        path = (
            ROOT
            / ".local-e2e"
            / "runs"
            / run_id
            / CORE_ID
            / "arm64"
            / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            log = self._log(run_id)
            if log is None:
                continue
            self.assertTrue(
                parallel_n64.parallel_n64_log_proves_contract(
                    log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                ),
                f"{run_id}/arm64 did not prove the parallel_n64 contract",
            )
            proven += 1
        if proven == 0:
            self.skipTest("no workspace-local parallel_n64 build logs present")

    def test_contract_rejects_a_link_that_dropped_gles(self) -> None:
        log = self._log(SELECTED_RUN) or self._log(REPRODUCTION_RUN)
        if log is None:
            self.skipTest("no workspace-local parallel_n64 build log present")
        without_gles = tuple(
            option
            for option in parallel_n64.PARALLEL_N64_EXPECTED_LINK_OPTIONS[
                "arm64"
            ]
            if option != "-lGLESv2"
        )
        tampered = dataclasses.replace(
            parallel_n64.PARALLEL_N64_LOG_CONTRACT,
            expected_link_options={"arm64": without_gles},
        )
        self.assertFalse(
            c_asm_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )

    def test_contract_rejects_a_wrong_assembly_compile_count(self) -> None:
        log = self._log(SELECTED_RUN) or self._log(REPRODUCTION_RUN)
        if log is None:
            self.skipTest("no workspace-local parallel_n64 build log present")
        tampered = dataclasses.replace(
            parallel_n64.PARALLEL_N64_LOG_CONTRACT,
            expected_asm_compile_count={"arm64": 0},
        )
        self.assertFalse(
            c_asm_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
