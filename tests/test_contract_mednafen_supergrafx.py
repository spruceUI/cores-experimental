"""SuperGrafx shared compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mednafen_supergrafx as sgx
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class MednafenSupergrafxLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_supergrafx(self) -> None:
        contract = core_log_contract_for(sgx.MEDNAFEN_SUPERGRAFX_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "mednafen-supergrafx-mixed-language-v1", contract.contract_id
        )
        self.assertEqual(
            "mednafen_supergrafx_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({sgx.MEDNAFEN_SUPERGRAFX_CORE_ID}), contract.core_ids
        )

    def test_catalog_uses_supergrafx_owned_native_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][sgx.MEDNAFEN_SUPERGRAFX_CORE_ID]
        identity = sgx.MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertTrue(sgx.mednafen_supergrafx_spec_is_well_formed(spec))
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            sgx.MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_DERIVATION,
            spec["build"]["git_version"]["derivation"],
        )
        self.assertEqual(
            sgx.MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION,
            spec["build"]["git_version"]["value"],
        )
        self.assertEqual("cxx", spec["build"]["git_version"]["compiler_scope"])

    def test_exact_supergrafx_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, sgx.MEDNAFEN_SUPERGRAFX_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    sgx.MEDNAFEN_SUPERGRAFX_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    sgx,
                    "MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    sgx.MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    sgx,
                    "MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    sgx,
                    "MEDNAFEN_SUPERGRAFX_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        sgx.mednafen_supergrafx_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        sgx.mednafen_supergrafx_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        sgx.mednafen_supergrafx_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            sgx.MEDNAFEN_SUPERGRAFX_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
