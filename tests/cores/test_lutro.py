"""Focused lutro catalog, workflow, contract, and archive-membership tests."""

from __future__ import annotations

import dataclasses
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import lutro
from core_pipeline_lib.contracts.c_only import c_only_log_proves_contract

from .support import ROOT, load_document


CORE_ID = "lutro"
SOURCE_URL = "https://github.com/libretro/libretro-lutro.git"
SOURCE_COMMIT = "1df938b3bf37b8d1eb6cdd07ec915c4f569a7551"
SOURCE_TREE = "d20aac44229476877084e26c2558c63737a86c98"
SELECTED_RUN = "actions-sim-build-core-lutro-v1"
REPRODUCTION_RUN = "build-core-lutro-local-v1"


class LutroManifestTests(unittest.TestCase):
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
        self.assertEqual("libretro-lutro", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(lutro.lutro_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(lutro.lutro_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core lutro", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class LutroCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/lutro.json"
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
            (ROOT / "manifests/compatibility/pending/lutro.json").exists()
        )
        for arch in ("arm64", "armhf"):
            self.assertNotIn(
                "libstdc++.so.6", compatibility["targets"][arch]["needed"]
            )


class LutroContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_contract_enables_archive_membership_mode(self) -> None:
        # the load-bearing difference from plain c_only: the Lua static archive
        contract = lutro.LUTRO_LOG_CONTRACT
        self.assertEqual(("liblua.a",), contract.expected_archive_names)
        self.assertEqual(
            lutro.LUTRO_EXPECTED_ARCHIVE_MEMBER_SHA256,
            contract.expected_archive_member_sha256,
        )
        self.assertEqual((("obj/player/", ""),), contract.semantic_path_aliases)

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    lutro.lutro_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the lutro contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local lutro build logs present")

    def test_contract_rejects_a_tampered_archive_member_set(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local lutro build log present")
        tampered = dataclasses.replace(
            lutro.LUTRO_LOG_CONTRACT, expected_archive_member_sha256="0" * 64
        )
        self.assertFalse(
            c_only_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local lutro build log present")
        tampered = dataclasses.replace(
            lutro.LUTRO_LOG_CONTRACT, expected_compile_count=999
        )
        self.assertFalse(
            c_only_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
