"""Focused mupen64plus_next catalog, make-variable, GLES, and contract tests."""

from __future__ import annotations

import copy
import dataclasses
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mupen64plus_next
from core_pipeline_lib.contracts.c_asm import c_asm_log_proves_contract

from .support import ROOT, load_document


CORE_ID = "mupen64plus_next"
SOURCE_URL = "https://github.com/libretro/mupen64plus-libretro-nx.git"
SOURCE_COMMIT = "98c1b0d877542b01314b3b04272282ba223b65b3"
SOURCE_TREE = "e82f86deaeb37d3df9ad2673b53738af96848325"
SELECTED_RUN = "actions-sim-build-core-mupen64plus_next-w3"
REPRODUCTION_RUN = "build-core-mupen64plus_next-local-w3"


class Mupen64PlusNextManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/develop",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual(["arm64"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(
            mupen64plus_next.mupen64plus_next_spec_is_well_formed(self.spec)
        )
        mutated = copy.deepcopy(self.spec)
        mutated["targets"] = ["arm64", "armhf"]
        self.assertFalse(
            mupen64plus_next.mupen64plus_next_spec_is_well_formed(mutated)
        )

    def test_reviewed_make_variables_select_aarch64_and_gles(self) -> None:
        variables = self.spec["build"]["make_variables"]
        self.assertEqual({"FORCE_GLES": 1, "WITH_DYNAREC": "aarch64"}, variables)
        self.assertEqual(
            mupen64plus_next.MUPEN64PLUS_NEXT_MAKE_PROFILE,
            pipeline.make_variable_profile(variables),
        )
        # The string value is admitted only by this exact reviewed profile.
        for bad in ("aarch64 ", "$(shell id)", "", "arm64;rm"):
            self.assertIsNone(
                pipeline.make_variable_profile(
                    dict(variables, WITH_DYNAREC=bad)
                ),
                bad,
            )

    def test_submodule_fetch_is_disabled_for_a_stray_gitlink(self) -> None:
        """No .gitmodules at all, but one dangling gitlink."""

        self.assertIs(False, self.spec["build"]["submodules"])
        spec = {"build": {"submodules": False}}
        self.assertFalse(pipeline.spec_submodules_enabled(spec))
        self.assertTrue(pipeline.spec_submodules_enabled({"build": {}}))
        # Provenance must still record the gitlink rather than hide it.
        shell = pipeline.provenance_shell("src", True, False)
        self.assertIn("ls-tree -r HEAD", shell)
        self.assertIn("/output/submodules.txt", shell)
        # And the checkout must not attempt a fetch that cannot succeed.
        checkout = pipeline.checkout_shell("src", "a" * 40, True, False)
        self.assertNotIn("submodule update", checkout)

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core mupen64plus_next", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class Mupen64PlusNextCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        path = ROOT / "manifests/compatibility/mupen64plus_next.json"
        compatibility = load_document(path)
        report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual("valid", report["status"], report["errors"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual({"arm64"}, set(compatibility["targets"]))

    def test_artifact_needs_versioned_gles_sonames(self) -> None:
        """Unlike the shipped build, which linked the unversioned dev symlinks.

        This matters for device eligibility: libGLESv2.so.2 and libEGL.so.1 are
        the runtime sonames a device actually carries, and both are captured in
        the fleet's library observations.
        """

        compatibility = load_document(
            ROOT / "manifests/compatibility/mupen64plus_next.json"
        )
        needed = compatibility["targets"]["arm64"]["needed"]
        self.assertIn("libGLESv2.so.2", needed)
        self.assertIn("libEGL.so.1", needed)


class Mupen64PlusNextContractTests(unittest.TestCase):
    def _log(self, run_id: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / "arm64" / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            log = self._log(run_id)
            if log is None:
                continue
            self.assertTrue(
                mupen64plus_next.mupen64plus_next_log_proves_contract(
                    log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                ),
                f"{run_id}/arm64 did not prove the contract",
            )
            proven += 1
        if proven == 0:
            self.skipTest("no workspace-local build logs present")

    def test_contract_rejects_a_link_that_dropped_gles(self) -> None:
        log = self._log(SELECTED_RUN) or self._log(REPRODUCTION_RUN)
        if log is None:
            self.skipTest("no workspace-local build log present")
        without_gl = tuple(
            option
            for option in mupen64plus_next.MUPEN64PLUS_NEXT_EXPECTED_LINK_OPTIONS[
                "arm64"
            ]
            if option not in {"-lGLESv2", "-lEGL"}
        )
        tampered = dataclasses.replace(
            mupen64plus_next.MUPEN64PLUS_NEXT_LOG_CONTRACT,
            expected_link_options={"arm64": without_gl},
        )
        self.assertFalse(
            c_asm_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        log = self._log(SELECTED_RUN) or self._log(REPRODUCTION_RUN)
        if log is None:
            self.skipTest("no workspace-local build log present")
        tampered = dataclasses.replace(
            mupen64plus_next.MUPEN64PLUS_NEXT_LOG_CONTRACT,
            expected_c_compile_count={"arm64": 140},
        )
        self.assertFalse(
            c_asm_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
