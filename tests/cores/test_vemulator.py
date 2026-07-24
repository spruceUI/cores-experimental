"""Focused VEmulator catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import core_log_contract_for
from scripts.core_pipeline_lib.contracts import vemulator
from tests.test_contract_vemulator import build_vemulator_log_fixture

from .support import ROOT


CORE_ID = "vemulator"
SOURCE_COMMIT = "7fade95506201aed83316cc3f2efe3d7cecf75a7"
SOURCE_TREE = "09e8c0ec31c874ea555288c53c975e289e865c0a"


class VemulatorCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_and_marker_bind_exact_source_native_identity(self) -> None:
        self.assertTrue(vemulator.vemulator_spec_is_well_formed(self.spec))
        self.assertEqual(
            frozenset({CORE_ID, "freeintv"}),
            pipeline.EXACT_SOURCE_NATIVE_CORE_IDS,
        )
        self.assertEqual(
            [vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER],
            pipeline.source_identity_log_markers(CORE_ID, self.spec),
        )
        shell = pipeline.source_identity_shell(CORE_ID, self.spec)
        self.assertEqual(1, shell.count("CORE_PIPELINE_SOURCE_IDENTITY|"))
        self.assertIn(vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER, shell)

        build_script = pipeline.container_build_script(
            CORE_ID,
            "arm64",
            self.spec,
            self.catalog["resolver"],
        )
        self.assertEqual(
            1, build_script.count(vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER)
        )
        self.assertLess(
            build_script.index("git -C libretro-vemulator checkout --detach"),
            build_script.index(vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER),
        )
        self.assertLess(
            build_script.index(vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER),
            build_script.index("rm -f dist/unix/vemulator_libretro.so"),
        )

    def test_marker_is_not_generic_or_available_to_mutated_specs(self) -> None:
        mutation = copy.deepcopy(self.spec)
        mutation["source"]["tree"] = "0" * 40
        self.assertEqual(
            [], pipeline.source_identity_log_markers(CORE_ID, mutation)
        )
        self.assertEqual(
            [], pipeline.source_identity_log_markers("uzem", self.spec)
        )
        self.assertEqual("", pipeline.source_identity_shell(None, self.spec))

    def test_catalog_rejects_partial_or_cross_core_identity(self) -> None:
        mutations = {
            "source-commit": (("source", "commit"), "0" * 40),
            "source-tree": (("source", "tree"), "0" * 40),
            "source-key": (("build", "source_key"), "uzem"),
            "artifact": (("build", "artifact_name"), "uzem_libretro.so"),
            "extra-version": (
                ("build", "git_version"),
                {
                    "derivation": "native-space-short7-v1",
                    "value": " 7fade95",
                },
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

    def test_public_composition_roots_cannot_bypass_core_owned_proofs(
        self,
    ) -> None:
        with mock.patch.object(
            pipeline, "vemulator_spec_is_well_formed", return_value=False
        ) as spec_proof:
            self.assertEqual(
                [], pipeline.source_identity_log_markers(CORE_ID, self.spec)
            )
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_catalog(copy.deepcopy(self.catalog))
            self.assertGreaterEqual(spec_proof.call_count, 2)

        source = {
            "url": self.spec["source"]["url"],
            "requested_ref": self.spec["source"]["requested_ref"],
            "commit": SOURCE_COMMIT,
            "tree": SOURCE_TREE,
            "resolved_commit": SOURCE_COMMIT,
            "resolved_url": self.spec["source"]["url"],
            "submodules": [],
        }
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            pipeline.vemulator_golden_source_is_well_formed(CORE_ID, source)
        )
        self.assertTrue(
            pipeline.vemulator_golden_build_contract_is_well_formed(
                build, SOURCE_COMMIT, CORE_ID, source
            )
        )

    def test_registry_and_proof_dispatch_are_singleton(self) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("vemulator-mixed-language-v1", contract.contract_id)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual("vemulator_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)

        with mock.patch.object(
            pipeline, "vemulator_log_proves_contract", return_value=True
        ) as proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )
            proof.assert_called_once_with(
                "log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
            )

    def test_fresh_provenance_hash_binds_plain_source_native_build(self) -> None:
        record = {
            "core_id": CORE_ID,
            "source": {},
            "recipe": {"pipeline_bundle": pipeline.pipeline_source_bundle()},
            "toolchain": {},
            "artifact": {},
            "metadata": {},
            "build": {
                "driver": "libretro-super",
                "environment": "sanitized-v1",
                "compile_definitions": [],
            },
        }
        changed = copy.deepcopy(record)
        changed["build"]["environment"] = "unsanitized"
        self.assertNotEqual(
            pipeline.provenance_identity_sha256(record),
            pipeline.provenance_identity_sha256(changed),
        )


if __name__ == "__main__":
    unittest.main()
