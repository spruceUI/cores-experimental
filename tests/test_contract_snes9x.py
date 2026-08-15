from __future__ import annotations

import copy
from collections import Counter
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import mixed_language, snes9x
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]
SELECTED_RUN = "actions-sim-build-core-snes9x-w3"


class Snes9xLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_snes9x(self) -> None:
        contract = core_log_contract_for(snes9x.SNES9X_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("snes9x-mixed-language-v1", contract.contract_id)
        self.assertEqual("snes9x_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({snes9x.SNES9X_CORE_ID}), contract.core_ids)

    def test_exact_catalog_identity_is_core_owned(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][snes9x.SNES9X_CORE_ID]
        identity = snes9x.SNES9X_GIT_VERSION_SPEC_IDENTITY

        self.assertIs(identity, pipeline.SNES9X_GIT_VERSION_SPEC_IDENTITY)
        self.assertTrue(snes9x.snes9x_spec_is_well_formed(spec))
        self.assertEqual(
            {
                "compiler_scope": "cxx",
                "derivation": "hyphen-short7-v1",
                "value": "-185488c",
            },
            spec["build"]["git_version"],
        )
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            [
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-185488c",
                "CORE_PIPELINE_GIT_VERSION|-185488c|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh snes9x",
            pipeline.libretro_build_shell(spec, snes9x.SNES9X_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][snes9x.SNES9X_CORE_ID]["build"]["git_version"].pop(
            "compiler_scope"
        )
        self.assertFalse(
            snes9x.snes9x_spec_is_well_formed(
                changed["cores"][snes9x.SNES9X_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "snes9x core must preserve its exact injected version",
        ):
            pipeline.validate_catalog(changed)

    def test_reviewed_parent_path_alias_is_contained(self) -> None:
        aliases = snes9x.SNES9X_LOG_CONTRACT.semantic_path_aliases
        self.assertEqual(
            "apu/apu.o",
            mixed_language.mixed_language_semantic_log_path(
                "../apu/apu.o", ".o", aliases
            ),
        )
        self.assertEqual(
            "libretro/libretro.cpp",
            mixed_language.mixed_language_semantic_log_path(
                "../libretro/libretro.cpp", ".cpp", aliases
            ),
        )
        self.assertIsNone(
            mixed_language.mixed_language_semantic_log_path(
                "../../escape.o", ".o", aliases
            )
        )
        self.assertIsNone(
            mixed_language.mixed_language_semantic_log_path(
                "/absolute/escape.o", ".o", aliases
            )
        )

    def test_synthetic_logs_dispatch_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, snes9x.SNES9X_CORE_ID, architecture
                )
                contract = replace(
                    snes9x.SNES9X_LOG_CONTRACT,
                    expected_compile_pair_sha256=fixture["compile_pair_sha256"],
                    expected_compile_invocation_sha256={
                        architecture: fixture["compile_invocation_sha256"]
                    },
                    expected_link_object_sha256=fixture["link_object_sha256"],
                    expected_raw_link_object_sha256=fixture[
                        "raw_link_object_sha256"
                    ],
                )
                self.assertEqual(
                    {"cxx": 54, "c": 3},
                    dict(contract.expected_language_counts),
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    snes9x.SNES9X_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(snes9x, "SNES9X_LOG_CONTRACT", contract):
                    self.assertTrue(snes9x.snes9x_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    warning_material = "\n".join(
                        snes9x.SNES9X_EXPECTED_WARNING_BLOCKS[architecture]
                    )
                    reordered_warning_material = "\n".join(
                        reversed(
                            snes9x.SNES9X_EXPECTED_WARNING_BLOCKS[architecture]
                        )
                    )
                    reordered_warning_log = fixture["log"].replace(
                        warning_material, reordered_warning_material, 1
                    )
                    self.assertTrue(
                        snes9x.snes9x_log_proves_contract(
                            reordered_warning_log,
                            snes9x.SNES9X_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    for label, changed_log in (
                        (
                            "missing-warning",
                            fixture["log"].replace(
                                snes9x.SNES9X_MEMMAP_WARNING_BLOCK + "\n", ""
                            ),
                        ),
                        (
                            "changed-diagnostic",
                            fixture["log"].replace(
                                "      |                 ^~~~~~~~~",
                                "      |                 ^~~~~~~~",
                            ),
                        ),
                        ("extra-warning", fixture["log"] + "warning: extra\n"),
                        ("error", fixture["log"] + "error: failure\n"),
                        ("fatal", fixture["log"] + "fatal: failure\n"),
                        (
                            "undefined",
                            fixture["log"] + "undefined reference to symbol\n",
                        ),
                        (
                            "dubious-owner",
                            fixture["log"] + "detected dubious ownership\n",
                        ),
                        (
                            "version-scope",
                            fixture["log"].replace(
                                fixture["version_token"], "", 1
                            ),
                        ),
                        (
                            "duplicate-compile",
                            fixture["log"] + fixture["compile_lines"][0] + "\n",
                        ),
                    ):
                        with self.subTest(
                            architecture=architecture, mutation=label
                        ):
                            self.assertFalse(
                                snes9x.snes9x_log_proves_contract(
                                    changed_log,
                                    snes9x.SNES9X_CORE_ID,
                                    architecture,
                                    spec["source"]["commit"],
                                    spec["source"]["tree"],
                                )
                            )
                    self.assertFalse(
                        snes9x.snes9x_log_proves_contract(
                            fixture["log"],
                            "mednafen_supafaust",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        snes9x.snes9x_log_proves_contract(
                            fixture["log"],
                            snes9x.SNES9X_CORE_ID,
                            architecture,
                            "0" * 40,
                            spec["source"]["tree"],
                        )
                    )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        identity = snes9x.SNES9X_GIT_VERSION_SPEC_IDENTITY
        log_paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / snes9x.SNES9X_CORE_ID
                / architecture
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        self.assertEqual(57, snes9x.SNES9X_LOG_CONTRACT.expected_compile_count)
        self.assertEqual(
            {"cxx": 54, "c": 3},
            dict(snes9x.SNES9X_LOG_CONTRACT.expected_language_counts),
        )
        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                log = log_path.read_text(encoding="utf-8")
                arguments = (
                    log,
                    snes9x.SNES9X_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                self.assertTrue(snes9x.snes9x_log_proves_contract(*arguments))
                self.assertEqual(
                    Counter(snes9x.SNES9X_EXPECTED_WARNING_LINES[architecture]),
                    Counter(
                        line
                        for line in log.splitlines()
                        if "warning:" in line.casefold()
                    ),
                )


if __name__ == "__main__":
    unittest.main()
