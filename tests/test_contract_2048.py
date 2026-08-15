"""2048 shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shlex
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import c_only, core_2048
from core_pipeline_lib.contracts.command_line import ordered_command_argv_sha256
from core_pipeline_lib.contracts.registry import core_log_contract_for
from core_pipeline_lib.foundation import sha256_file
from tests.core_contract_helpers import build_c_only_log_fixture


ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOCK_FILE_SHA256 = (
    "1a91c8cc3f0349ec6b191fa5a14c1e3bd48f84086950cad2836fe11085ff6ce6"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "c89f2f646f2c3c1414a2a8969488e29d6ff2d6002be3e73c41c789851ee2f55a"
)


class Core2048ContractTests(unittest.TestCase):
    def test_source_lock_is_exact_and_catalog_bound(self) -> None:
        identity = core_2048.CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
        source_lock = registry.composed_source_lock("2048")

        registry.validate_source_lock(
            source_lock,
        )
        self.assertEqual("2048-c90437d3c391", source_lock["source_lock_id"])
        self.assertEqual(core_2048.CORE_2048_ID, source_lock["core_id"])
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
            registry.canonical_content_sha256(source_lock),
        )

    def test_registry_identity_is_owned_by_2048(self) -> None:
        contract = core_log_contract_for(core_2048.CORE_2048_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("core-2048-c-only-v1", contract.contract_id)
        self.assertEqual("core_2048_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertIn("source framing", contract.failure_message)
        self.assertIn("successful lifecycle", contract.failure_message)
        self.assertEqual(
            frozenset({core_2048.CORE_2048_ID}), contract.core_ids
        )

    def test_exact_catalog_and_promoted_record_contracts(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = core_2048.CORE_2048_ID
        spec = catalog["cores"][core_id]
        identity = core_2048.CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "derivation": (
                    core_2048.CORE_2048_NATIVE_GIT_VERSION_DERIVATION
                ),
                "value": core_2048.CORE_2048_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
            "log": "build.log",
            "log_sha256": "a" * 64,
        }

        self.assertIs(
            identity, pipeline.CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertTrue(core_2048.core_2048_spec_is_well_formed(spec))
        self.assertTrue(
            core_2048.core_2048_golden_source_is_well_formed(core_id, source)
        )
        self.assertTrue(
            core_2048.core_2048_golden_build_contract_is_well_formed(
                build, identity["source_commit"], core_id, source
            )
        )
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" c90437d"|file'],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh 2048",
            pipeline.libretro_build_shell(spec, core_id),
        )

        wrong_spec = copy.deepcopy(spec)
        wrong_spec["build"]["git_version"]["compiler_scope"] = "cxx"
        self.assertFalse(core_2048.core_2048_spec_is_well_formed(wrong_spec))
        changed_catalog = copy.deepcopy(catalog)
        changed_catalog["cores"][core_id] = wrong_spec
        with self.assertRaisesRegex(pipeline.PipelineError, r"cores\.2048"):
            pipeline.validate_catalog(changed_catalog)
        wrong_source = copy.deepcopy(source)
        wrong_source["submodules"] = [
            {"path": "injected", "commit": "0" * 40}
        ]
        self.assertFalse(
            core_2048.core_2048_golden_source_is_well_formed(
                core_id, wrong_source
            )
        )
        wrong_build = copy.deepcopy(build)
        wrong_build["git_version"]["compiler_scope"] = "cxx"
        self.assertFalse(
            core_2048.core_2048_golden_build_contract_is_well_formed(
                wrong_build, identity["source_commit"], core_id, source
            )
        )

    def test_exact_2048_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_c_only_log_fixture(
                    pipeline, ROOT, core_2048.CORE_2048_ID, architecture
                )
                spec = fixture["spec"]
                compile_lines = fixture["compile_lines"]
                link_line = fixture["link_line"]

                def framed_log(
                    commands: list[str],
                    *,
                    prefix: tuple[str, ...] = (),
                    trailer: tuple[str, ...] = (
                        core_2048.CORE_2048_SUCCESS_TRAILER
                    ),
                ) -> str:
                    return (
                        "\n".join(
                            [
                                *prefix,
                                "PLATFORM: Linux",
                                "=== 2048",
                                "Fetching 2048...",
                                *core_2048.CORE_2048_SUCCESS_MARKER,
                                core_2048.CORE_2048_SOURCE_HEAD_MARKER,
                                core_2048.CORE_2048_NATIVE_VERSION_MARKER,
                                (
                                    "make -f Makefile.libretro platform=unix "
                                    "-j24 clean"
                                ),
                                "rm -f 2048_libretro.so",
                                *commands,
                                *trailer,
                            ]
                        )
                        + "\n"
                    )

                log = framed_log(
                    [*compile_lines, link_line],
                    prefix=(
                        "CORE_PIPELINE_CHIPSET_TUNING|synthetic-universal-v1",
                    ),
                )
                arguments = (
                    log,
                    core_2048.CORE_2048_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                raw_compile_invocation_sha256 = (
                    c_only.c_only_raw_compile_invocation_sha256(
                        tuple(shlex.split(line)) for line in compile_lines
                    )
                )
                link_invocation_sha256 = ordered_command_argv_sha256(
                    shlex.split(link_line)
                )
                with mock.patch.object(
                    core_2048,
                    "CORE_2048_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    core_2048.CORE_2048_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    core_2048,
                    "CORE_2048_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    core_2048,
                    "CORE_2048_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ), mock.patch.dict(
                    core_2048.CORE_2048_EXPECTED_RAW_COMPILE_INVOCATION_SHA256,
                    {architecture: raw_compile_invocation_sha256},
                ), mock.patch.dict(
                    core_2048.CORE_2048_EXPECTED_LINK_INVOCATION_SHA256,
                    {architecture: link_invocation_sha256},
                ):
                    self.assertTrue(
                        core_2048.core_2048_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )

                    reversed_log = framed_log(
                        [*reversed(compile_lines), link_line]
                    )
                    self.assertTrue(
                        core_2048.core_2048_log_proves_contract(
                            reversed_log, *arguments[1:]
                        )
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(
                            reversed_log, *arguments[1:]
                        )
                    )

                    self.assertFalse(
                        core_2048.core_2048_log_proves_contract(
                            log,
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )

                    def assert_rejected(log_text: str) -> None:
                        mutated_arguments = (log_text, *arguments[1:])
                        self.assertFalse(
                            core_2048.core_2048_log_proves_contract(
                                *mutated_arguments
                            )
                        )
                        self.assertFalse(
                            pipeline.registered_core_log_contract_proves(
                                *mutated_arguments
                            )
                        )

                    for changed_source in (
                        ("0" * 40, spec["source"]["tree"]),
                        (spec["source"]["commit"], "0" * 40),
                    ):
                        changed_arguments = (
                            log,
                            core_2048.CORE_2048_ID,
                            architecture,
                            *changed_source,
                        )
                        self.assertFalse(
                            core_2048.core_2048_log_proves_contract(
                                *changed_arguments
                            )
                        )
                        self.assertFalse(
                            pipeline.registered_core_log_contract_proves(
                                *changed_arguments
                            )
                        )

                    copy_line = core_2048.CORE_2048_SUCCESS_TRAILER[0]
                    for diagnostic in (
                        "synthetic.c:1: warning: unreviewed warning",
                        "synthetic.c:1: note: unreviewed note",
                        "synthetic.c:1: error: unreviewed error",
                        "fatal: synthetic failure",
                        "undefined reference to synthetic_symbol",
                        "aarch64-linux-gnu-ld: cannot find -lsynthetic",
                        "collect2: ld returned 1 exit status",
                        "make: *** [2048_libretro.so] Error 1",
                        "tool: command not found",
                        "linker command failed with exit code 1",
                        "Killed",
                    ):
                        with self.subTest(
                            architecture=architecture,
                            diagnostic=diagnostic,
                        ):
                            assert_rejected(
                                log.replace(
                                    copy_line,
                                    diagnostic + "\n" + copy_line,
                                    1,
                                )
                            )

                    mutations = {
                        "opaque-gap": log.replace(
                            compile_lines[0],
                            compile_lines[0] + "\nUNREVIEWED BUILD OUTPUT",
                            1,
                        ),
                        "make-gap": log.replace(
                            compile_lines[0],
                            compile_lines[0] + "\nmake synthetic-step",
                            1,
                        ),
                        "compile-after-link": framed_log(
                            [*compile_lines[1:], link_line, compile_lines[0]]
                        ),
                        "link-before-compiles-complete": framed_log(
                            [compile_lines[0], link_line, *compile_lines[1:]]
                        ),
                        "missing-compile": framed_log(
                            [*compile_lines[1:], link_line]
                        ),
                        "duplicate-compile": framed_log(
                            [compile_lines[0], *compile_lines, link_line]
                        ),
                        "altered-compile": framed_log(
                            [
                                compile_lines[0].replace(
                                    " -O2 ", " -O3 ", 1
                                ),
                                *compile_lines[1:],
                                link_line,
                            ]
                        ),
                        "missing-link": framed_log([*compile_lines]),
                        "duplicate-link": framed_log(
                            [*compile_lines, link_line, link_line]
                        ),
                        "altered-link": framed_log(
                            [
                                *compile_lines,
                                link_line.replace(
                                    "2048_libretro.so", "other.so", 1
                                ),
                            ]
                        ),
                        "reordered-link-flags": framed_log(
                            [
                                *compile_lines,
                                link_line.replace(
                                    "-fPIC -shared", "-shared -fPIC", 1
                                ),
                            ]
                        ),
                        "reordered-link-objects": framed_log(
                            [
                                *compile_lines,
                                link_line.replace(
                                    "./src/unit_015.o ./src/unit_014.o",
                                    "./src/unit_014.o ./src/unit_015.o",
                                    1,
                                ),
                            ]
                        ),
                        "extra-compiler-command": log.replace(
                            link_line,
                            (
                                f"{fixture['c_compiler']} -E synthetic.c\n"
                                + link_line
                            ),
                            1,
                        ),
                        "missing-source-marker": log.replace(
                            core_2048.CORE_2048_SOURCE_HEAD_MARKER + "\n",
                            "",
                            1,
                        ),
                        "duplicate-source-marker": log.replace(
                            core_2048.CORE_2048_SOURCE_HEAD_MARKER,
                            (
                                core_2048.CORE_2048_SOURCE_HEAD_MARKER
                                + "\n"
                                + core_2048.CORE_2048_SOURCE_HEAD_MARKER
                            ),
                            1,
                        ),
                        "altered-source-marker": log.replace(
                            core_2048.CORE_2048_SOURCE_HEAD_MARKER,
                            "HEAD is now at c90437d altered subject",
                            1,
                        ),
                        "missing-native-marker": log.replace(
                            core_2048.CORE_2048_NATIVE_VERSION_MARKER + "\n",
                            "",
                            1,
                        ),
                        "duplicate-native-marker": log.replace(
                            core_2048.CORE_2048_NATIVE_VERSION_MARKER,
                            (
                                core_2048.CORE_2048_NATIVE_VERSION_MARKER
                                + "\n"
                                + core_2048.CORE_2048_NATIVE_VERSION_MARKER
                            ),
                            1,
                        ),
                        "altered-native-marker": log.replace(
                            core_2048.CORE_2048_NATIVE_VERSION_MARKER,
                            'CORE_PIPELINE_NATIVE_GIT_VERSION|" deadbee"|file',
                            1,
                        ),
                        "arbitrary-trailing-output": (
                            log + "UNREVIEWED TRAILING OUTPUT\n"
                        ),
                    }

                    lines = log.splitlines()
                    trailer_width = len(core_2048.CORE_2048_SUCCESS_TRAILER)
                    body = lines[:-trailer_width]
                    trailer = lines[-trailer_width:]
                    link_position = body.index(link_line)
                    mutations["trailer-before-link"] = (
                        "\n".join(
                            [
                                *body[:link_position],
                                *trailer,
                                *body[link_position:],
                            ]
                        )
                        + "\n"
                    )

                    for label, mutation in mutations.items():
                        with self.subTest(
                            architecture=architecture,
                            mutation=label,
                        ):
                            assert_rejected(mutation)


if __name__ == "__main__":
    unittest.main()
