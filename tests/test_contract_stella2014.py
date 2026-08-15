from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import stella2014
from core_pipeline_lib.contracts import mixed_language
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class Stella2014LogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_stella2014(self) -> None:
        contract = core_log_contract_for(stella2014.STELLA2014_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("stella2014-mixed-language-v1", contract.contract_id)
        self.assertEqual("stella2014_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({stella2014.STELLA2014_CORE_ID}), contract.core_ids
        )

    def test_catalog_and_command_scope_use_stella2014_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][stella2014.STELLA2014_CORE_ID]
        identity = stella2014.STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[
                stella2014.STELLA2014_CORE_ID
            ],
        )
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(identity["artifact_name"], spec["build"]["artifact_name"])
        self.assertNotIn("compiler_scope", spec["build"]["git_version"])
        self.assertEqual(
            '" 4a7da82"', pipeline.command_scoped_native_git_version(spec)
        )

    def test_reviewed_stella2014_source_alias_is_core_owned(self) -> None:
        contract = stella2014.stella2014_mixed_language_contract()
        self.assertEqual(
            "libretro-common/unit.o",
            mixed_language.mixed_language_semantic_log_path(
                "stella/../libretro-common/unit.o",
                ".o",
                contract.semantic_path_aliases,
            ),
        )
        self.assertIsNone(
            mixed_language.mixed_language_semantic_log_path(
                "stella/../other/unit.o",
                ".o",
                contract.semantic_path_aliases,
            )
        )

    def test_exact_stella2014_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, stella2014.STELLA2014_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    stella2014.STELLA2014_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    stella2014,
                    "STELLA2014_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    stella2014.STELLA2014_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    stella2014,
                    "STELLA2014_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    stella2014,
                    "STELLA2014_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        stella2014.stella2014_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        stella2014.stella2014_log_proves_contract(
                            fixture["log"],
                            "handy",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        stella2014.stella2014_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            stella2014.STELLA2014_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
