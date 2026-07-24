"""Focused ECWolf catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import ecwolf

from .support import ROOT, load_document


CORE_ID = "ecwolf"
SOURCE_URL = "https://github.com/libretro/ecwolf.git"
SOURCE_COMMIT = "4731f0075d6c225921b40b341b23971e73dd9dfc"
SOURCE_TREE = "4e651e299a236ecfbbb4e44427e0087790ff1c64"
SELECTED_RUN = "actions-sim-build-core-ecwolf-v1"
REPRODUCTION_RUN = "build-core-ecwolf-local-v1"


class EcwolfManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_simple_libretro_super_recipe(self) -> None:
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
                "source_dir": "libretro-ecwolf",
                "output_path": "dist/unix/ecwolf_libretro.so",
                "artifact_name": "ecwolf_libretro.so",
            },
            self.spec["build"],
        )
        # A simple bridge-promoted core carries no strict-contract fields.
        self.assertNotIn("git_version", self.spec["build"])
        self.assertNotIn("compile_definitions", self.spec["build"])
        self.assertNotIn("make_variables", self.spec["build"])
        self.assertNotIn("recipe_profile", self.spec["build"])
        self.assertNotIn("overlays", self.spec["build"])
        self.assertNotIn("validation", self.spec)
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(ecwolf.ecwolf_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(ecwolf.ecwolf_spec_is_well_formed(mutated))

    def test_workflow_is_a_read_only_shared_pipeline_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertIn("timeout-minutes: 45", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core ecwolf", workflow)
        self.assertIn("scripts/toolchain_archive.py verify-downloads", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class EcwolfCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/ecwolf.json"
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
            (ROOT / "manifests/compatibility/pending/ecwolf.json").exists()
        )
        # ARMHF references only the base GLIBCXX_3.4 symbol, so the core clears
        # the Miyoo Mini fallback ceiling and is not a Mini-over-ceiling core.
        armhf_requirements = set(
            compatibility["targets"]["armhf"]["version_requirements"]
        )
        self.assertNotIn("GLIBCXX_3.4.29", armhf_requirements)
        self.assertNotIn("GLIBCXX_3.4.32", armhf_requirements)


class EcwolfContractTests(unittest.TestCase):
    """Guardrail on the mixed-language oracle against the workspace logs.

    ``.local-e2e`` runs are workspace-local (git-ignored); when the promotion
    evidence is present these assertions catch a copied-sha256 regression that
    a synthetic fixture cannot, and skip cleanly on a fresh checkout.
    """

    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT
            / ".local-e2e"
            / "runs"
            / run_id
            / CORE_ID
            / arch
            / "build.log"
        )
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    ecwolf.ecwolf_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the ECWolf contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local ECWolf build logs present")

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local ECWolf build log present")
        from unittest import mock

        with mock.patch.object(
            ecwolf, "ECWOLF_EXPECTED_COMPILE_COUNT", ecwolf.ECWOLF_EXPECTED_COMPILE_COUNT + 1
        ):
            self.assertFalse(
                ecwolf.ecwolf_log_proves_contract(
                    log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )


if __name__ == "__main__":
    unittest.main()
