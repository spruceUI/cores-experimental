"""Uzem shared compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import uzem
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class UzemLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_uzem(self) -> None:
        contract = core_log_contract_for(uzem.UZEM_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("uzem-mixed-language-v1", contract.contract_id)
        self.assertEqual("uzem_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({uzem.UZEM_CORE_ID}), contract.core_ids)

    def test_catalog_uses_uzem_owned_native_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][uzem.UZEM_CORE_ID]
        identity = uzem.UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertTrue(uzem.uzem_spec_is_well_formed(spec))
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            uzem.UZEM_NATIVE_GIT_VERSION_DERIVATION,
            spec["build"]["git_version"]["derivation"],
        )
        self.assertEqual(
            uzem.UZEM_NATIVE_GIT_VERSION, spec["build"]["git_version"]["value"]
        )

    def test_golden_source_and_build_records_are_bound_exactly(self) -> None:
        identity = uzem.UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
            "git_version": {
                "derivation": uzem.UZEM_NATIVE_GIT_VERSION_DERIVATION,
                "value": uzem.UZEM_NATIVE_GIT_VERSION,
            },
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            uzem.uzem_golden_source_is_well_formed(uzem.UZEM_CORE_ID, source)
        )
        self.assertTrue(
            uzem.uzem_golden_build_contract_is_well_formed(
                build, identity["source_commit"], uzem.UZEM_CORE_ID, source
            )
        )
        # A drifted source tree fails closed.
        drifted = {**source, "tree": "b" * 40}
        self.assertFalse(
            uzem.uzem_golden_source_is_well_formed(uzem.UZEM_CORE_ID, drifted)
        )

    def test_exact_uzem_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, uzem.UZEM_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    uzem.UZEM_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    uzem,
                    "UZEM_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    uzem.UZEM_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    uzem,
                    "UZEM_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    uzem,
                    "UZEM_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(uzem.uzem_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        uzem.uzem_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        uzem.uzem_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            uzem.UZEM_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
