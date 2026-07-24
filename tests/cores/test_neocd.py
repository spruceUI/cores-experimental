"""Focused NeoCD catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import neocd

from .support import ROOT, load_document


CORE_ID = "neocd"
SOURCE_URL = "https://github.com/libretro/neocd_libretro.git"
SOURCE_COMMIT = "9e9ad181bed60f84f9cff02c03617b41e8a31cfe"
SOURCE_TREE = "c82440c78b368bbd4c58122d796e4d9beb40c22a"
ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=0",
    "HWCAP2_CRC32=0",
    "HWCAP2_SHA1=0",
    "HWCAP2_SHA2=0",
]
SELECTED_RUN = "actions-sim-build-core-neocd-v1"
REPRODUCTION_RUN = "build-core-neocd-local-v1"


class NeocdManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_recipe_with_armhf_definitions(self) -> None:
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
                "source_dir": "libretro-neocd",
                "output_path": "dist/unix/neocd_libretro.so",
                "artifact_name": "neocd_libretro.so",
                "compile_definitions": {"armhf": ARMHF_COMPILE_DEFINITIONS},
            },
            self.spec["build"],
        )
        self.assertNotIn("git_version", self.spec["build"])
        self.assertNotIn("make_variables", self.spec["build"])
        self.assertNotIn("recipe_profile", self.spec["build"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(neocd.neocd_spec_is_well_formed(self.spec))
        mutated = {
            **self.spec,
            "build": {
                k: v
                for k, v in self.spec["build"].items()
                if k != "compile_definitions"
            },
        }
        self.assertFalse(neocd.neocd_spec_is_well_formed(mutated))

    def test_workflow_is_a_read_only_shared_pipeline_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core neocd", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("contents: write", workflow)


class NeocdCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/neocd.json"
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
            (ROOT / "manifests/compatibility/pending/neocd.json").exists()
        )
        # NeoCD's ARMHF C++ build needs GLIBCXX above the Miyoo Mini fallback
        # ceiling (3.4.24), so it is a Mini-over-ceiling core.
        armhf = compatibility["targets"]["armhf"]
        self.assertIn("libstdc++.so.6", armhf["needed"])
        max_glibcxx = max(
            (
                tuple(int(p) for p in req[len("GLIBCXX_"):].split("."))
                for req in armhf["version_requirements"]
                if req.startswith("GLIBCXX_") and req[len("GLIBCXX_"):]
            ),
            default=(),
        )
        self.assertGreater(max_glibcxx, (3, 4, 24))


class NeocdContractTests(unittest.TestCase):
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
                    neocd.neocd_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the NeoCD contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local NeoCD build logs present")

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        from unittest import mock

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local NeoCD build log present")
        with mock.patch.object(
            neocd,
            "NEOCD_EXPECTED_COMPILE_COUNT",
            neocd.NEOCD_EXPECTED_COMPILE_COUNT + 1,
        ):
            self.assertFalse(
                neocd.neocd_log_proves_contract(
                    log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )


if __name__ == "__main__":
    unittest.main()
