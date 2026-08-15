"""LowRes NX shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import lowresnx
from core_pipeline_lib.contracts.registry import core_log_contract_for
from core_pipeline_lib.foundation import sha256_file
from tests.core_contract_helpers import build_c_only_log_fixture


ROOT = Path(__file__).resolve().parents[1]
CONTROL_LOG_IDENTITIES = {
    "arm64": (
        "266ffed71feed3711ebb532b37e4b7a1ed81ae38edfacfdc5b481d29c7a7294e",
        21910,
    ),
    "armhf": (
        "b4ea85c19ca20991a2be6afd2435dd45bbd8d48790dd5a32e7075f3622388102",
        22230,
    ),
}
SOURCE_LOCK_FILE_SHA256 = (
    "7e2567911869847ba52daf8a28867854db5fd93fed2723c2d16c2ddc59b95473"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "9af4c42d7e184aae60553d405e114715d533b4f9eb84a8a9678b498842d01ae4"
)


class LowResNXContractTests(unittest.TestCase):
    def test_source_lock_is_exact_and_catalog_bound(self) -> None:
        identity = lowresnx.LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        source_lock = registry.composed_source_lock("lowresnx")

        registry.validate_source_lock(
            source_lock,
        )
        self.assertEqual("lowresnx-35adc1a215e9", source_lock["source_lock_id"])
        self.assertEqual(lowresnx.LOWRESNX_CORE_ID, source_lock["core_id"])
        self.assertEqual(
            {
                "url": identity["source_url"],
                "requested_ref": identity["source_requested_ref"],
                "commit": identity["source_commit"],
                "tree": identity["source_tree"],
                "submodules": [],
            },
            source_lock["source"],
        )
        self.assertEqual(
            SOURCE_LOCK_CONTENT_SHA256,
            source_lock["content_sha256"],
        )
        self.assertEqual(
            SOURCE_LOCK_CONTENT_SHA256,
            registry.canonical_content_sha256(source_lock),
        )

    def test_registry_identity_is_owned_by_lowresnx(self) -> None:
        contract = core_log_contract_for(lowresnx.LOWRESNX_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("lowresnx-c-only-v1", contract.contract_id)
        self.assertEqual("lowresnx_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertIn("zero-diagnostic contract", contract.failure_message)
        self.assertEqual(
            frozenset({lowresnx.LOWRESNX_CORE_ID}), contract.core_ids
        )

    def test_exact_catalog_and_promoted_record_contracts(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = lowresnx.LOWRESNX_CORE_ID
        spec = catalog["cores"][core_id]
        identity = lowresnx.LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "derivation": lowresnx.LOWRESNX_NATIVE_GIT_VERSION_DERIVATION,
                "value": lowresnx.LOWRESNX_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
            "log": "build.log",
            "log_sha256": "a" * 64,
        }

        self.assertIs(identity, pipeline.LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY)
        self.assertTrue(lowresnx.lowresnx_spec_is_well_formed(spec))
        self.assertTrue(
            lowresnx.lowresnx_golden_source_is_well_formed(core_id, source)
        )
        self.assertTrue(
            lowresnx.lowresnx_golden_build_contract_is_well_formed(
                build, identity["source_commit"], core_id, source
            )
        )
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" 35adc1a"|file'],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh lowresnx",
            pipeline.libretro_build_shell(spec, core_id),
        )

        wrong_spec = copy.deepcopy(spec)
        wrong_spec["build"]["git_version"]["compiler_scope"] = "cxx"
        self.assertFalse(lowresnx.lowresnx_spec_is_well_formed(wrong_spec))
        changed_catalog = copy.deepcopy(catalog)
        changed_catalog["cores"][core_id] = wrong_spec
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            r"cores\.lowresnx",
        ):
            pipeline.validate_catalog(changed_catalog)
        wrong_source = copy.deepcopy(source)
        wrong_source["submodules"] = [
            {"path": "injected", "commit": "0" * 40}
        ]
        self.assertFalse(
            lowresnx.lowresnx_golden_source_is_well_formed(
                core_id, wrong_source
            )
        )
        wrong_build = copy.deepcopy(build)
        wrong_build["git_version"]["compiler_scope"] = "cxx"
        self.assertFalse(
            lowresnx.lowresnx_golden_build_contract_is_well_formed(
                wrong_build, identity["source_commit"], core_id, source
            )
        )

    def test_exact_lowresnx_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_c_only_log_fixture(
                    pipeline, ROOT, lowresnx.LOWRESNX_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    lowresnx.LOWRESNX_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    lowresnx,
                    "LOWRESNX_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    lowresnx.LOWRESNX_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    lowresnx,
                    "LOWRESNX_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    lowresnx,
                    "LOWRESNX_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        lowresnx.lowresnx_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    markers = pipeline.git_version_log_markers(spec)
                    permuted_log = (
                        "\n".join(
                            [
                                *markers,
                                *reversed(fixture["compile_lines"]),
                                fixture["link_line"],
                            ]
                        )
                        + "\n"
                    )
                    framed_log = (
                        "CORE_PIPELINE_TEST_PREFIX|lowresnx\n"
                        + fixture["log"]
                        + "cp lowresnx_libretro.so dist/lowresnx_libretro.so\n"
                        + "CORE_PIPELINE_TEST_SUCCESS|lowresnx\n"
                    )
                    self.assertTrue(
                        lowresnx.lowresnx_log_proves_contract(
                            permuted_log, *arguments[1:]
                        )
                    )
                    self.assertTrue(
                        lowresnx.lowresnx_log_proves_contract(
                            framed_log, *arguments[1:]
                        )
                    )
                    self.assertFalse(
                        lowresnx.lowresnx_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )

                    def assert_rejected(log_text: str) -> None:
                        mutated_arguments = (log_text, *arguments[1:])
                        self.assertFalse(
                            lowresnx.lowresnx_log_proves_contract(
                                *mutated_arguments
                            )
                        )
                        self.assertFalse(
                            pipeline.registered_core_log_contract_proves(
                                *mutated_arguments
                            )
                        )

                    for diagnostic in (
                        "synthetic.c:1: warning: unreviewed warning",
                        "synthetic.c:1: note: unreviewed note",
                        "synthetic.c:1: error: unreviewed error",
                        "fatal: synthetic failure",
                        "undefined reference to synthetic_symbol",
                        "aarch64-linux-gnu-ld: cannot find -lsynthetic",
                        "collect2: ld returned 1 exit status",
                        "make: *** [lowresnx_libretro.so] Error 1",
                    ):
                        with self.subTest(
                            architecture=architecture,
                            diagnostic=diagnostic,
                        ):
                            assert_rejected(fixture["log"] + diagnostic + "\n")

                    lines = fixture["log"].splitlines()
                    first_compile = lines.index(fixture["compile_lines"][0])
                    link_position = lines.index(fixture["link_line"])

                    gap_lines = list(lines)
                    gap_lines.insert(first_compile + 1, "UNREVIEWED BUILD OUTPUT")
                    assert_rejected("\n".join(gap_lines) + "\n")

                    moved_trailer_lines = [
                        *lines[:link_position],
                        "cp lowresnx_libretro.so dist/lowresnx_libretro.so",
                        *lines[link_position:],
                    ]
                    assert_rejected("\n".join(moved_trailer_lines) + "\n")

                    compile_after_link_lines = list(lines)
                    moved_compile = compile_after_link_lines.pop(first_compile)
                    moved_link_position = compile_after_link_lines.index(
                        fixture["link_line"]
                    )
                    compile_after_link_lines.insert(
                        moved_link_position + 1, moved_compile
                    )
                    assert_rejected("\n".join(compile_after_link_lines) + "\n")

                    warning_after_trailer = (
                        framed_log + "synthetic.c:1: warning: moved warning\n"
                    )
                    assert_rejected(warning_after_trailer)

    def test_workspace_control_logs_prove_contract_when_available(self) -> None:
        identity = lowresnx.LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "manual"
                / f"lowresnx-{architecture}-control-v1"
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local LowRes NX control logs are unavailable")
        for architecture, path in paths.items():
            with self.subTest(architecture=architecture):
                expected_sha256, expected_size = CONTROL_LOG_IDENTITIES[
                    architecture
                ]
                self.assertEqual(expected_sha256, sha256_file(path))
                self.assertEqual(expected_size, path.stat().st_size)
                self.assertTrue(
                    lowresnx.lowresnx_log_proves_contract(
                        path.read_text(encoding="utf-8"),
                        lowresnx.LOWRESNX_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
