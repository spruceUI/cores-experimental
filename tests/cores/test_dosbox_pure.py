"""Focused dosbox_pure catalog, overlay, contract, and canonical-state tests."""

from __future__ import annotations

import dataclasses
import hashlib
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import dosbox_pure
from core_pipeline_lib.contracts.command_line import (
    command_line_is_lexically_safe,
    semantic_log_path,
)
from core_pipeline_lib.contracts.mixed_language import (
    mixed_language_log_proves_contract,
)

from .support import ROOT, load_document


CORE_ID = "dosbox_pure"
SOURCE_URL = "https://github.com/libretro/dosbox-pure.git"
SOURCE_COMMIT = "a4a0bab7f8931433588f2fcad9045c85b277373d"
SOURCE_TREE = "0b64e0b00ba92300de9f73f213f3feaddf54a134"
SELECTED_RUN = "actions-sim-build-core-dosbox_pure-w3"
REPRODUCTION_RUN = "build-core-dosbox_pure-local-w3"


class DosboxPureManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/main",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual(
            "libretro-dosbox_pure", self.spec["build"]["source_dir"]
        )
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(
            dosbox_pure.dosbox_pure_spec_is_well_formed(self.spec)
        )
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(dosbox_pure.dosbox_pure_spec_is_well_formed(mutated))

    def test_echo_overlay_is_pinned_for_both_architectures(self) -> None:
        overlays = self.spec["build"]["overlays"]
        self.assertEqual({"arm64", "armhf"}, set(overlays))
        for arch, patches in overlays.items():
            self.assertEqual([dosbox_pure.DOSBOX_PURE_OVERLAY], patches, arch)

    def test_overlay_patch_file_matches_its_pinned_digest(self) -> None:
        overlay = dosbox_pure.DOSBOX_PURE_OVERLAY
        patch = (ROOT / overlay["patch_path"]).read_bytes()
        self.assertEqual(
            overlay["patch_sha256"], hashlib.sha256(patch).hexdigest()
        )
        # The overlay only unsilences the COMPILE recipe.
        self.assertIn(b"-\t@$(CXX)", patch)
        self.assertIn(b"+\t$(CXX)", patch)

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core dosbox_pure", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class DosboxPureTildeGuardTests(unittest.TestCase):
    """The `~`-mangled object names must stay inside both shared guards."""

    def test_containment_guard_admits_only_a_non_leading_tilde(self) -> None:
        self.assertEqual(
            "build/release/src~hardware~vga.cpp.o",
            semantic_log_path("build/release/src~hardware~vga.cpp.o", ".o"),
        )
        for escape in ("~/evil.o", "~user/evil.o", "build/~evil/x.o"):
            self.assertIsNone(semantic_log_path(escape, ".o"), escape)

    def test_line_guard_relaxation_is_opt_in_and_positional(self) -> None:
        embedded = "g++ -o build/release/src~dosbox.cpp.o -c src/dosbox.cpp"
        self.assertFalse(command_line_is_lexically_safe(embedded))
        self.assertTrue(command_line_is_lexically_safe(embedded, True))
        # A shell would expand each of these; the relaxation must not admit it.
        for escape in ("g++ -o ~/evil.o", "g++ -oX=~/evil.o", "~x -o a.o"):
            self.assertFalse(command_line_is_lexically_safe(escape, True), escape)


class DosboxPureCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/dosbox_pure.json"
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


class DosboxPureContractTests(unittest.TestCase):
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
                    dosbox_pure.dosbox_pure_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the dosbox_pure contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local dosbox_pure build logs present")

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local dosbox_pure build log present")
        tampered = dataclasses.replace(
            dosbox_pure.DOSBOX_PURE_LOG_CONTRACT,
            expected_compile_count=111,
            expected_language_counts={"cxx": 111},
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )

    def test_contract_rejects_the_log_without_the_tilde_opt_in(self) -> None:
        """Without allow_embedded_tilde the log is not even parseable."""

        log = self._log(SELECTED_RUN, "armhf") or self._log(
            REPRODUCTION_RUN, "armhf"
        )
        if log is None:
            self.skipTest("no workspace-local dosbox_pure build log present")
        tampered = dataclasses.replace(
            dosbox_pure.DOSBOX_PURE_LOG_CONTRACT, allow_embedded_tilde=False
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "armhf", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )

    def test_contract_rejects_a_wrong_compile_invocation_digest(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local dosbox_pure build log present")
        tampered = dataclasses.replace(
            dosbox_pure.DOSBOX_PURE_LOG_CONTRACT,
            expected_compile_invocation_sha256={
                "arm64": "0" * 64,
                "armhf": "0" * 64,
            },
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
