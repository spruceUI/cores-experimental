"""Focused chailove catalog, overlay, contract, and canonical-state tests."""

from __future__ import annotations

import dataclasses
import hashlib
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import chailove
from core_pipeline_lib.contracts.c_asm import c_asm_log_proves_contract

from .support import ROOT, load_document


CORE_ID = "chailove"
SOURCE_URL = "https://github.com/libretro/ChaiLove.git"
SOURCE_COMMIT = "5fa2014d9a1359836f165ab251831bce878ec2be"
SOURCE_TREE = "6d11c7be6a39132d97e99bb81588d581613222ae"
SELECTED_RUN = "actions-sim-build-core-chailove-w3"
REPRODUCTION_RUN = "build-core-chailove-local-w3"


class ChailoveManifestTests(unittest.TestCase):
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
        self.assertEqual("libretro-chailove", self.spec["build"]["source_dir"])
        self.assertEqual(
            "dist/unix/chailove_libretro.so", self.spec["build"]["output_path"]
        )
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(chailove.chailove_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(chailove.chailove_spec_is_well_formed(mutated))

    def test_echo_overlay_is_pinned_for_both_architectures(self) -> None:
        overlays = self.spec["build"]["overlays"]
        self.assertEqual({"arm64", "armhf"}, set(overlays))
        for arch, patches in overlays.items():
            self.assertEqual([chailove.CHAILOVE_OVERLAY], patches, arch)

    def test_overlay_patch_file_matches_its_pinned_digest(self) -> None:
        overlay = chailove.CHAILOVE_OVERLAY
        patch = (ROOT / overlay["patch_path"]).read_bytes()
        self.assertEqual(
            overlay["patch_sha256"], hashlib.sha256(patch).hexdigest()
        )
        # The overlay only unsilences the Makefile's recipe echo.
        self.assertIn(b"Makefile", patch)
        self.assertIn(b"-Q=@", patch)
        self.assertIn(b"+Q=", patch)

    def test_spec_is_not_well_formed_without_the_overlay(self) -> None:
        build = {
            key: value
            for key, value in self.spec["build"].items()
            if key != "overlays"
        }
        mutated = {**self.spec, "build": build}
        self.assertFalse(chailove.chailove_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core chailove", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class ChailoveCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/chailove.json"
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
        for arch in ("arm64", "armhf"):
            self.assertIn(
                "libstdc++.so.6", compatibility["targets"][arch]["needed"]
            )


class ChailoveContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    chailove.chailove_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the chailove contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local chailove build logs present")

    def test_contract_rejects_a_wrong_assembly_compile_count(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local chailove build log present")
        tampered = dataclasses.replace(
            chailove.CHAILOVE_LOG_CONTRACT,
            expected_asm_compile_count={"arm64": 2, "armhf": 2},
        )
        self.assertFalse(
            c_asm_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )

    def test_contract_rejects_a_wrong_compile_invocation_digest(self) -> None:
        log = self._log(SELECTED_RUN, "armhf") or self._log(
            REPRODUCTION_RUN, "armhf"
        )
        if log is None:
            self.skipTest("no workspace-local chailove build log present")
        tampered = dataclasses.replace(
            chailove.CHAILOVE_LOG_CONTRACT,
            expected_compile_invocation_sha256={
                "arm64": "0" * 64,
                "armhf": "0" * 64,
            },
        )
        self.assertFalse(
            c_asm_log_proves_contract(
                log, CORE_ID, "armhf", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
