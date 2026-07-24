from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import tgbdual
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class TgbdualLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_tgbdual(self) -> None:
        contract = core_log_contract_for(tgbdual.TGBDUAL_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("tgbdual-cxx-link-v1", contract.contract_id)
        self.assertEqual("tgbdual_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({tgbdual.TGBDUAL_CORE_ID}), contract.core_ids
        )

    def test_catalog_and_command_scope_use_tgbdual_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][tgbdual.TGBDUAL_CORE_ID]
        identity = tgbdual.TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[
                tgbdual.TGBDUAL_CORE_ID
            ],
        )
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(
            identity["source_requested_ref"], spec["source"]["requested_ref"]
        )
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual("libretro-super", spec["build"]["driver"])
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
        self.assertNotIn("make_variables", spec["build"])
        self.assertEqual(
            [], pipeline.compile_definitions_for_target(spec, "arm64")
        )
        self.assertEqual(
            [], pipeline.compile_definitions_for_target(spec, "armhf")
        )
        self.assertIsNone(pipeline.validated_source_date_epoch(spec))
        self.assertEqual(identity["artifact_name"], spec["build"]["artifact_name"])
        self.assertEqual(
            {
                "compiler_scope": "cxx",
                "derivation": "native-space-short7-v1",
                "value": " bf816b0",
            },
            spec["build"]["git_version"],
        )
        self.assertEqual(
            '" bf816b0"', pipeline.command_scoped_native_git_version(spec)
        )
        self.assertEqual(
            "./libretro-build.sh tgbdual",
            pipeline.libretro_build_shell(spec, tgbdual.TGBDUAL_CORE_ID),
        )
        origin_shell = pipeline.git_version_shell(spec)
        self.assertIn("export MAKEFLAGS=", origin_shell)
        self.assertIn("-f Makefile", origin_shell)

    def test_exact_cxx_log_dispatches_through_individual_proof(self) -> None:
        fixture = build_mixed_language_log_fixture(
            pipeline, ROOT, tgbdual.TGBDUAL_CORE_ID, "arm64"
        )
        self.assertEqual(
            {"cxx": 9},
            tgbdual.tgbdual_cxx_contract().expected_language_counts,
        )
        self.assertEqual(
            {"cxx"},
            {
                language
                for _output, _source, language, _compiler in fixture["entries"]
            },
        )
        spec = fixture["spec"]
        arguments = (
            fixture["log"],
            tgbdual.TGBDUAL_CORE_ID,
            "arm64",
            spec["source"]["commit"],
            spec["source"]["tree"],
        )
        with mock.patch.object(
            tgbdual,
            "TGBDUAL_EXPECTED_COMPILE_PAIR_SHA256",
            fixture["compile_pair_sha256"],
        ), mock.patch.dict(
            tgbdual.TGBDUAL_EXPECTED_COMPILE_INVOCATION_SHA256,
            {"arm64": fixture["compile_invocation_sha256"]},
        ), mock.patch.object(
            tgbdual,
            "TGBDUAL_EXPECTED_LINK_OBJECT_SHA256",
            fixture["link_object_sha256"],
        ), mock.patch.object(
            tgbdual,
            "TGBDUAL_EXPECTED_RAW_LINK_OBJECT_SHA256",
            fixture["raw_link_object_sha256"],
        ):
            self.assertTrue(tgbdual.tgbdual_log_proves_contract(*arguments))
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(*arguments)
            )
            self.assertFalse(
                tgbdual.tgbdual_log_proves_contract(
                    fixture["log"],
                    "gambatte",
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            duplicate = fixture["log"] + fixture["compile_lines"][0] + "\n"
            self.assertFalse(
                tgbdual.tgbdual_log_proves_contract(
                    duplicate,
                    tgbdual.TGBDUAL_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )


if __name__ == "__main__":
    unittest.main()
