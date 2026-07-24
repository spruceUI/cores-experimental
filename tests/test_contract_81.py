"""EightyOne shared compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import core_81
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class Core81LogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_81(self) -> None:
        contract = core_log_contract_for(core_81.CORE_81_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("core-81-mixed-language-v1", contract.contract_id)
        self.assertEqual("core_81_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({core_81.CORE_81_ID}), contract.core_ids)

    def test_catalog_uses_81_owned_generated_source_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][core_81.CORE_81_ID]
        identity = core_81.CORE_81_SPEC_IDENTITY
        self.assertTrue(core_81.core_81_spec_is_well_formed(spec))
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            identity["generated_source"], spec["build"]["generated_source"]
        )
        self.assertTrue(
            core_81.core_81_generated_source_contract_is_well_formed(
                spec["build"]["generated_source"]
            )
        )

    def test_generated_version_shell_binds_the_reviewed_sha256(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][core_81.CORE_81_ID]
        shell = core_81.core_81_generated_version_shell(spec)
        self.assertIn(core_81.CORE_81_GENERATED_VERSION_SHA256, shell)
        self.assertIn("src/version.c", shell)

    def test_golden_source_and_build_records_are_bound_exactly(self) -> None:
        identity = core_81.CORE_81_SPEC_IDENTITY
        source = {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "generated_source": identity["generated_source"],
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            core_81.core_81_golden_source_is_well_formed(core_81.CORE_81_ID, source)
        )
        self.assertTrue(
            core_81.core_81_golden_build_contract_is_well_formed(
                build, identity["source_commit"], core_81.CORE_81_ID, source
            )
        )
        drifted = {**source, "tree": "b" * 40}
        self.assertFalse(
            core_81.core_81_golden_source_is_well_formed(core_81.CORE_81_ID, drifted)
        )

    def test_exact_81_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, core_81.CORE_81_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    core_81.CORE_81_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    core_81,
                    "CORE_81_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    core_81.CORE_81_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    core_81,
                    "CORE_81_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    core_81,
                    "CORE_81_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(core_81.core_81_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        core_81.core_81_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        core_81.core_81_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            core_81.CORE_81_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
