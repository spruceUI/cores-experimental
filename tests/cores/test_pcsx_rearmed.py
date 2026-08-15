"""Focused PCSX ReARMed catalog, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from .support import pipeline
from core_pipeline_lib.contracts import pcsx_rearmed

from .support import ROOT, load_document
from .support import evidence_handles


CORE_ID = "pcsx_rearmed"

_H = evidence_handles(CORE_ID)
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]

SOURCE_URL = _H["SOURCE_URL"]

SOURCE_DATE_EPOCH = 1782602899

ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=0",
    "HWCAP2_CRC32=0",
    "HWCAP2_SHA1=0",
    "HWCAP2_SHA2=0",
]

class PcsxRearmedManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_recipe_with_epoch_and_definitions(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
                "submodules": [
                    {
                        "path": "frontend/libpicofe",
                        "commit": "dd11f2d723162eb1cf8e6db9f40de7db0d0b6bba",
                    }
                ],
            },
            self.spec["source"],
        )
        self.assertEqual(
            {
                "driver": "libretro-super",
                "source_key": CORE_ID,
                "source_dir": "libretro-pcsx_rearmed",
                "output_path": "dist/unix/pcsx_rearmed_libretro.so",
                "artifact_name": "pcsx_rearmed_libretro.so",
                "source_date_epoch": SOURCE_DATE_EPOCH,
                "compile_definitions": {"armhf": ARMHF_COMPILE_DEFINITIONS},
            },
            self.spec["build"],
        )
        self.assertNotIn("git_version", self.spec["build"])
        self.assertNotIn("make_variables", self.spec["build"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(pcsx_rearmed.pcsx_rearmed_spec_is_well_formed(self.spec))
        mutated = {
            **self.spec,
            "build": {
                k: v
                for k, v in self.spec["build"].items()
                if k != "source_date_epoch"
            },
        }
        self.assertFalse(
            pcsx_rearmed.pcsx_rearmed_spec_is_well_formed(mutated)
        )


class PcsxRearmedCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/pcsx_rearmed.json"
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
            (
                ROOT / "manifests/compatibility/pending/pcsx_rearmed.json"
            ).exists()
        )
        # PCSX ReARMed is a C core: no libstdc++ dependency, so it clears every
        # device provider ceiling (including the Miyoo Mini).
        for arch in ("arm64", "armhf"):
            needed = compatibility["targets"][arch]["needed"]
            self.assertNotIn("libstdc++.so.6", needed)


class PcsxRearmedContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None


    def test_contract_rejects_a_wrong_assembly_count(self) -> None:
        from unittest import mock

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local PCSX ReARMed build log present")
        with mock.patch.object(
            pcsx_rearmed,
            "PCSX_REARMED_EXPECTED_ASM_COMPILE_COUNT",
            {"arm64": 99, "armhf": 6},
        ):
            self.assertFalse(
                pcsx_rearmed.pcsx_rearmed_log_proves_contract(
                    log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )


if __name__ == "__main__":
    unittest.main()
