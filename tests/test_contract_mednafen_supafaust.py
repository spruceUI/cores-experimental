from __future__ import annotations

import copy
from collections import Counter
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mednafen_supafaust
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT
    / "tests/fixtures/per-core-oracles/mednafen_supafaust.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])
SELECTED_RUN = "actions-sim-build-core-mednafen_supafaust-w3"


class MednafenSupafaustLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_mednafen_supafaust(self) -> None:
        contract = core_log_contract_for(
            mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID
        )
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "mednafen-supafaust-cxx-link-v1", contract.contract_id
        )
        self.assertEqual(
            "mednafen_supafaust_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID}),
            contract.core_ids,
        )

    def test_exact_catalog_identity_is_core_owned(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        core_id = mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID
        spec = catalog["cores"][core_id]
        identity = (
            mednafen_supafaust.MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY
        )

        self.assertIs(
            identity,
            pipeline.MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY,
        )
        self.assertTrue(
            mednafen_supafaust.mednafen_supafaust_spec_is_well_formed(spec)
        )
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertNotIn("submodules", spec["source"])
        self.assertEqual(identity["source_key"], spec["build"]["source_key"])
        self.assertEqual(identity["source_dir"], spec["build"]["source_dir"])
        self.assertEqual(identity["output_path"], spec["build"]["output_path"])
        self.assertEqual(
            identity["artifact_name"], spec["build"]["artifact_name"]
        )
        self.assertEqual(identity["git_version"], spec["build"]["git_version"])
        self.assertEqual(
            identity["metadata_source_path"], spec["metadata"]["source_path"]
        )
        self.assertEqual(
            identity["metadata_artifact_name"],
            spec["metadata"]["artifact_name"],
        )
        self.assertEqual(identity["targets"], spec["targets"])
        self.assertEqual(
            [
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-2b93c0d",
                "CORE_PIPELINE_GIT_VERSION|-2b93c0d|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh mednafen_supafaust",
            pipeline.libretro_build_shell(spec, core_id),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][core_id]["build"]["git_version"].pop(
            "compiler_scope"
        )
        self.assertFalse(
            mednafen_supafaust.mednafen_supafaust_spec_is_well_formed(
                changed["cores"][core_id]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "mednafen_supafaust core must preserve its exact injected version",
        ):
            pipeline.validate_catalog(changed)

    def test_synthetic_logs_dispatch_and_fail_closed(self) -> None:
        core_id = mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, core_id, architecture
                )
                contract = replace(
                    mednafen_supafaust.MEDNAFEN_SUPAFAUST_LOG_CONTRACT,
                    expected_compile_pair_sha256=fixture[
                        "compile_pair_sha256"
                    ],
                    expected_compile_invocation_sha256={
                        architecture: fixture["compile_invocation_sha256"]
                    },
                    expected_link_object_sha256=fixture[
                        "link_object_sha256"
                    ],
                    expected_raw_link_object_sha256=fixture[
                        "raw_link_object_sha256"
                    ],
                )
                self.assertEqual(
                    {"cxx": 44}, dict(contract.expected_language_counts)
                )
                self.assertEqual(
                    {"cxx"},
                    {
                        language
                        for _output, _source, language, _compiler in fixture[
                            "entries"
                        ]
                    },
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    core_id,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    mednafen_supafaust,
                    "MEDNAFEN_SUPAFAUST_LOG_CONTRACT",
                    contract,
                ):
                    self.assertTrue(
                        mednafen_supafaust.mednafen_supafaust_log_proves_contract(
                            *arguments
                        )
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )

                    context_blocks = (
                        mednafen_supafaust.
                        MEDNAFEN_SUPAFAUST_EXPECTED_DIAGNOSTIC_CONTEXT_BLOCKS[
                            architecture
                        ]
                    )
                    diagnostic_material = "\n".join(context_blocks)
                    reordered_log = fixture["log"].replace(
                        diagnostic_material,
                        "\n".join(reversed(context_blocks)),
                        1,
                    )
                    self.assertTrue(
                        mednafen_supafaust.mednafen_supafaust_log_proves_contract(
                            reordered_log, *arguments[1:]
                        )
                    )

                    if architecture == "armhf":
                        mempatcher_context = context_blocks[3]
                        mempatcher_lines = mempatcher_context.splitlines()
                        spc_context = context_blocks[4]
                        interleaved_context = "\n".join(
                            (
                                *mempatcher_lines[:8],
                                spc_context,
                                *mempatcher_lines[8:],
                            )
                        )
                        interleaved_log = fixture["log"].replace(
                            mempatcher_context + "\n" + spc_context,
                            interleaved_context,
                            1,
                        )
                        self.assertNotEqual(fixture["log"], interleaved_log)
                        self.assertTrue(
                            mednafen_supafaust.
                            mednafen_supafaust_log_proves_contract(
                                interleaved_log, *arguments[1:]
                            )
                        )
                        reordered_context_log = fixture["log"].replace(
                            "\n".join(mempatcher_lines[:2]),
                            "\n".join(reversed(mempatcher_lines[:2])),
                            1,
                        )
                        self.assertNotEqual(
                            fixture["log"], reordered_context_log
                        )
                        self.assertFalse(
                            mednafen_supafaust.
                            mednafen_supafaust_log_proves_contract(
                                reordered_context_log, *arguments[1:]
                            )
                        )

                    context_old, context_new = (
                        (
                            "                 from mednafen/state.cpp:18:",
                            "                 from mednafen/state.cpp:19:",
                        )
                        if architecture == "arm64"
                        else (
                            "In file included from /opt/a30/"
                            "arm-a30-linux-gnueabihf/include/"
                            "c++/13.2.0/vector:72,",
                            "/opt/a30/arm-a30-linux-gnueabihf/include/"
                            "c++/13.2.0/vector:72,",
                        )
                    )
                    mutations = (
                        (
                            "spc-context",
                            fixture["log"].replace(
                                "In file included from mednafen/snes_faust/"
                                "apu.cpp:78:\n",
                                "",
                                1,
                            ),
                        ),
                        (
                            "abi-context",
                            fixture["log"].replace(
                                context_old, context_new, 1
                            ),
                        ),
                        ("extra-warning", fixture["log"] + "warning: extra\n"),
                        ("extra-note", fixture["log"] + "note: extra\n"),
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
                        (
                            "wrong-output",
                            fixture["log"].replace(
                                mednafen_supafaust.
                                MEDNAFEN_SUPAFAUST_BUILD_ARTIFACT_NAME,
                                "wrong_libretro.so",
                                1,
                            ),
                        ),
                    )
                    for label, changed_log in mutations:
                        with self.subTest(
                            architecture=architecture, mutation=label
                        ):
                            self.assertNotEqual(fixture["log"], changed_log)
                            self.assertFalse(
                                mednafen_supafaust.
                                mednafen_supafaust_log_proves_contract(
                                    changed_log, *arguments[1:]
                                )
                            )

                    for marker in (
                        "error: failure",
                        "fatal: failure",
                        "undefined reference to symbol",
                        "detected dubious ownership",
                        "make: *** [all] Error 1",
                    ):
                        self.assertFalse(
                            mednafen_supafaust.
                            mednafen_supafaust_log_proves_contract(
                                fixture["log"] + marker + "\n", *arguments[1:]
                            )
                        )
                    for identity_arguments in (
                        (
                            "snes9x",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        ),
                        (
                            core_id,
                            architecture,
                            "0" * 40,
                            spec["source"]["tree"],
                        ),
                        (
                            core_id,
                            architecture,
                            spec["source"]["commit"],
                            "0" * 40,
                        ),
                    ):
                        self.assertFalse(
                            mednafen_supafaust.
                            mednafen_supafaust_log_proves_contract(
                                fixture["log"], *identity_arguments
                            )
                        )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        core_id = mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID
        identity = (
            mednafen_supafaust.MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY
        )
        log_paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / core_id
                / architecture
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    mednafen_supafaust.mednafen_supafaust_log_proves_contract(
                        log_path.read_text(encoding="utf-8"),
                        core_id,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
