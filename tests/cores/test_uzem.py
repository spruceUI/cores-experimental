"""Focused Uzem catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

from .support import pipeline
from scripts.core_pipeline_lib.contracts import core_log_contract_for
from scripts.core_pipeline_lib.contracts import uzem

from .support import ROOT


CORE_ID = "uzem"
SOURCE_COMMIT = "d4fe82c38bf3fc789b955bcfcc81dc2e3a2ea89f"
SOURCE_TREE = "949f7cb3c2f61295335ea59e35e7d9f031693ac1"
SOURCE_URL = "https://github.com/libretro/libretro-uzem.git"
SOURCE_RECORD = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
}
GOLDEN_BUILD = {
    "driver": "libretro-super",
    "environment": "sanitized-v1",
    "compile_definitions": [],
    "git_version": {
        "derivation": "native-space-short7-v1",
        "value": " d4fe82c",
    },
    "log": "build.log",
    "log_sha256": "a" * 64,
}


class UzemCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_native_version_identity(self) -> None:
        self.assertTrue(uzem.uzem_spec_is_well_formed(self.spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(
                self.spec, CORE_ID
            )
        )
        self.assertEqual(
            uzem.UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[CORE_ID],
        )
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
                "derivation": "native-space-short7-v1",
                "value": " d4fe82c",
            },
            pipeline.validated_git_version(self.spec),
        )
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" d4fe82c"|file'],
            pipeline.git_version_log_markers(self.spec),
        )
        shell = pipeline.git_version_shell(self.spec)
        self.assertIn("/libretro-super/libretro-uzem", shell)
        self.assertIn("-f Makefile.libretro", shell)

    def test_catalog_rejects_partial_or_cross_core_identity(self) -> None:
        mutations = {
            "source-commit": (("source", "commit"), "0" * 40),
            "source-tree": (("source", "tree"), "0" * 40),
            "source-key": (("build", "source_key"), "vemulator"),
            "version": (("build", "git_version", "value"), " d4fe82d"),
            "compiler-scope": (
                ("build", "git_version", "compiler_scope"),
                "cxx",
            ),
        }
        for label, (path, value) in mutations.items():
            catalog = copy.deepcopy(self.catalog)
            target = catalog["cores"][CORE_ID]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(mutation=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validate_catalog(catalog)

    def test_pipeline_dispatches_core_owned_golden_contracts(self) -> None:
        self.assertTrue(
            pipeline.uzem_native_golden_source_is_well_formed(
                CORE_ID, SOURCE_RECORD
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                GOLDEN_BUILD,
                SOURCE_COMMIT,
                CORE_ID,
                SOURCE_RECORD,
            )
        )

        with mock.patch.object(
            pipeline, "uzem_spec_is_well_formed", return_value=True
        ) as spec_proof:
            self.assertTrue(
                pipeline.native_git_version_spec_is_well_formed({}, CORE_ID)
            )
            spec_proof.assert_called_once_with({})
        with mock.patch.object(
            pipeline,
            "uzem_golden_source_is_well_formed",
            return_value=True,
        ) as source_proof:
            self.assertTrue(
                pipeline.native_git_version_golden_source_is_well_formed(
                    CORE_ID, {}
                )
            )
            source_proof.assert_called_once_with(CORE_ID, {})
        with mock.patch.object(
            pipeline,
            "uzem_golden_build_contract_is_well_formed",
            return_value=True,
        ) as build_proof:
            self.assertTrue(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    {}, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
                )
            )
            build_proof.assert_called_once_with(
                {}, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
            )

    def test_public_composition_roots_cannot_bypass_core_owned_proofs(
        self,
    ) -> None:
        with mock.patch.object(
            pipeline, "uzem_spec_is_well_formed", return_value=False
        ) as spec_proof:
            self.assertFalse(
                pipeline.native_git_version_spec_is_well_formed(
                    self.spec, CORE_ID
                )
            )
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_catalog(copy.deepcopy(self.catalog))
            self.assertGreaterEqual(spec_proof.call_count, 2)

        with mock.patch.object(
            pipeline,
            "uzem_golden_source_is_well_formed",
            return_value=False,
        ) as source_proof:
            self.assertFalse(
                pipeline.native_git_version_golden_source_is_well_formed(
                    CORE_ID, SOURCE_RECORD
                )
            )
            source_proof.assert_called_once_with(CORE_ID, SOURCE_RECORD)

    def test_registry_and_proof_dispatch_are_singleton(self) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("uzem-mixed-language-v1", contract.contract_id)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual("uzem_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)

        with mock.patch.object(
            pipeline, "uzem_log_proves_contract", return_value=True
        ) as proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )
            proof.assert_called_once_with(
                "log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
            )


if __name__ == "__main__":
    unittest.main()
