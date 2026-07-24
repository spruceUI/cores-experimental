from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import gambatte, mixed_language
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class GambatteLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_gambatte(self) -> None:
        contract = core_log_contract_for(gambatte.GAMBATTE_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("gambatte-mixed-language-v1", contract.contract_id)
        self.assertEqual("gambatte_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({gambatte.GAMBATTE_CORE_ID}), contract.core_ids
        )

    def test_catalog_and_command_scope_use_gambatte_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][gambatte.GAMBATTE_CORE_ID]
        identity = gambatte.GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[
                gambatte.GAMBATTE_CORE_ID
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
        self.assertEqual("cxx", spec["build"]["git_version"]["compiler_scope"])
        self.assertEqual(
            '" dfc1655"', pipeline.command_scoped_native_git_version(spec)
        )
        self.assertEqual(
            "./libretro-build.sh gambatte",
            pipeline.libretro_build_shell(spec, gambatte.GAMBATTE_CORE_ID),
        )
        origin_shell = pipeline.git_version_shell(spec)
        self.assertIn("export MAKEFLAGS=", origin_shell)
        self.assertIn("-f Makefile.libretro", origin_shell)

    def test_reviewed_gambatte_source_aliases_are_core_owned(self) -> None:
        aliases = gambatte.gambatte_mixed_language_contract().semantic_path_aliases
        self.assertEqual(
            "libgambatte/libretro/unit.o",
            mixed_language.mixed_language_semantic_log_path(
                "libgambatte/src/../libretro/unit.o", ".o", aliases
            ),
        )
        self.assertEqual(
            "libgambatte/libretro-common/compat/unit.o",
            mixed_language.mixed_language_semantic_log_path(
                "libgambatte/src/../libretro-common/compat/unit.o",
                ".o",
                aliases,
            ),
        )
        self.assertIsNone(
            mixed_language.mixed_language_semantic_log_path(
                "libgambatte/src/../other/unit.o", ".o", aliases
            )
        )

    def test_exact_gambatte_log_dispatches_through_individual_proof(self) -> None:
        fixture = build_mixed_language_log_fixture(
            pipeline, ROOT, gambatte.GAMBATTE_CORE_ID, "arm64"
        )
        spec = fixture["spec"]
        arguments = (
            fixture["log"],
            gambatte.GAMBATTE_CORE_ID,
            "arm64",
            spec["source"]["commit"],
            spec["source"]["tree"],
        )
        with mock.patch.object(
            gambatte,
            "GAMBATTE_EXPECTED_COMPILE_PAIR_SHA256",
            fixture["compile_pair_sha256"],
        ), mock.patch.dict(
            gambatte.GAMBATTE_EXPECTED_COMPILE_INVOCATION_SHA256,
            {"arm64": fixture["compile_invocation_sha256"]},
        ), mock.patch.object(
            gambatte,
            "GAMBATTE_EXPECTED_LINK_OBJECT_SHA256",
            fixture["link_object_sha256"],
        ), mock.patch.object(
            gambatte,
            "GAMBATTE_EXPECTED_RAW_LINK_OBJECT_SHA256",
            fixture["raw_link_object_sha256"],
        ):
            self.assertTrue(gambatte.gambatte_log_proves_contract(*arguments))
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(*arguments)
            )
            self.assertFalse(
                gambatte.gambatte_log_proves_contract(
                    fixture["log"],
                    "tgbdual",
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            self.assertFalse(
                gambatte.gambatte_log_proves_contract(
                    fixture["log"] + "fatal: synthetic failure\n",
                    gambatte.GAMBATTE_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )


if __name__ == "__main__":
    unittest.main()
