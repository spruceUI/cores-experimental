from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mednafen_pcfx, mixed_language
from core_pipeline_lib.contracts.mednafen_pcfx import (
    mednafen_pcfx_combined_golden_build_contract_is_well_formed,
)


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT
    / "tests/fixtures/per-core-oracles/mednafen_pcfx.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
        / architecture
        / "build.log"
    )


def load_catalog_document() -> dict:
    return json.loads(
        (ROOT / "manifests/core-builds.json").read_text(encoding="utf-8")
    )


def build_mednafen_pcfx_log_fixture(
    architecture: str,
) -> tuple[
    mixed_language.MixedLanguageLogContract,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
]:
    """Build the complete contract shape without external build evidence."""

    c_compiler, cxx_compiler = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }[architecture]
    c_lines = tuple(
        f"{c_compiler} -c -o pcfx/c/unit_{index:03d}.o "
        f"pcfx/c/unit_{index:03d}.c -O2 -DNDEBUG -fPIC"
        for index in range(
            mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS["c"]
        )
    )
    version_token = (
        mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_LOG_TOKEN
    )
    cxx_lines = tuple(
        f"{cxx_compiler} -c -o pcfx/cxx/unit_{index:03d}.o "
        f"pcfx/cxx/unit_{index:03d}.cpp {version_token} "
        "-O2 -DNDEBUG -fPIC"
        for index in range(
            mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS["cxx"]
        )
    )
    compile_lines = (*c_lines, *cxx_lines)
    expected_compilers = {c_compiler, cxx_compiler}
    parsed_invocations = tuple(
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            expected_compilers,
            {cxx_compiler},
        )
        for line in compile_lines
    )
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct PC-FX compile fixture")
    invocations = tuple(
        invocation
        for invocation in parsed_invocations
        if invocation is not None
    )
    pairs = tuple(
        (output, source)
        for output, source, _language, *_raw in invocations
    )
    objects = tuple(output for output, _source in pairs)
    link_argv = (
        cxx_compiler,
        "-o",
        mednafen_pcfx.MEDNAFEN_PCFX_BUILD_ARTIFACT_NAME,
        *objects,
        *mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_LINK_OPTIONS,
    )
    contract = replace(
        mednafen_pcfx.MEDNAFEN_PCFX_LOG_CONTRACT,
        expected_compile_pair_sha256=(
            mixed_language.mixed_language_compile_pair_sha256(pairs)
        ),
        expected_compile_invocation_sha256={
            architecture: (
                mixed_language.mixed_language_compile_invocation_sha256(
                    invocations
                )
            )
        },
        expected_link_object_sha256=(
            mixed_language.mixed_language_link_object_sha256(objects)
        ),
        expected_raw_link_object_sha256=(
            mixed_language.mixed_language_raw_link_object_sha256(objects)
        ),
    )
    diagnostic_blocks = (
        mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_DIAGNOSTIC_BLOCKS[
            architecture
        ]
    )
    diagnostic_lines = tuple(
        line for block in diagnostic_blocks for line in block.splitlines()
    )
    log = (
        "\n".join(
            (
                mednafen_pcfx.MEDNAFEN_PCFX_SOURCE_HEAD_MARKER,
                *mednafen_pcfx.MEDNAFEN_PCFX_MAKE_MARKERS,
                mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_VERSION_MARKER,
                *compile_lines,
                *diagnostic_lines,
                " ".join(link_argv),
            )
        )
        + "\n"
    )
    return contract, compile_lines, link_argv, diagnostic_blocks, log


@contextmanager
def synthetic_contract(
    architecture: str,
    contract: mixed_language.MixedLanguageLogContract,
    link_argv: tuple[str, ...],
):
    ordered_digest = mednafen_pcfx.mednafen_pcfx_ordered_link_argv_sha256(
        list(link_argv)
    )
    with mock.patch.object(
        mednafen_pcfx,
        "MEDNAFEN_PCFX_EXPECTED_ORDERED_LINK_ARGV_SHA256",
        {architecture: ordered_digest},
    ), mock.patch.object(
        mednafen_pcfx,
        "MEDNAFEN_PCFX_LOG_CONTRACT",
        contract,
    ):
        yield


class MednafenPcfxModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = (
            mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        return (
            build_log_text,
            mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_catalog_and_promoted_contracts_are_exact_and_core_owned(
        self,
    ) -> None:
        spec = load_catalog_document()["cores"][
            mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
        ]
        identity = (
            mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertTrue(
            mednafen_pcfx.mednafen_pcfx_spec_is_well_formed(spec)
        )
        self.assertEqual(
            {
                "derivation": (
                    mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_DERIVATION
                ),
                "value": mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION,
                "compiler_scope": "cxx",
            },
            spec["build"]["git_version"],
        )
        self.assertEqual(
            {"IS_X86": 0}, spec["build"]["make_variables"]
        )
        self.assertEqual("Makefile", identity["native_makefile"])

        source = {
            **spec["source"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "make_variables": {"IS_X86": 0},
            "git_version": copy.deepcopy(spec["build"]["git_version"]),
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            mednafen_pcfx.mednafen_pcfx_golden_source_is_well_formed(
                mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID, source
            )
        )
        self.assertTrue(
            mednafen_pcfx_combined_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                source,
            )
        )

        for label, changed_source in {
            "tree": {**source, "tree": "0" * 40},
            "resolved-commit": {**source, "resolved_commit": "0" * 40},
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/other.git",
            },
            "submodule": {
                **source,
                "submodules": [{"path": "foreign", "commit": "0" * 40}],
            },
            "extra": {**source, "unexpected": True},
        }.items():
            with self.subTest(source=label):
                self.assertFalse(
                    mednafen_pcfx.mednafen_pcfx_golden_source_is_well_formed(
                        mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                        changed_source,
                    )
                )
                self.assertFalse(
                    mednafen_pcfx_combined_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                        changed_source,
                    )
                )

        for label, changed_build in {
            "host-x86": {**build, "make_variables": {"IS_X86": 1}},
            "missing-make": {
                key: value
                for key, value in build.items()
                if key != "make_variables"
            },
            "version": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "value": " 0000000",
                },
            },
            "scope": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "compiler_scope": "all",
                },
            },
            "epoch": {**build, "source_date_epoch": 1},
            "digest": {**build, "log_sha256": "invalid"},
            "extra": {**build, "unexpected": True},
        }.items():
            with self.subTest(build=label):
                self.assertFalse(
                    mednafen_pcfx_combined_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                        source,
                    )
                )

    def test_shared_pipeline_generates_exact_portable_native_contract(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
        spec = catalog["cores"][core_id]
        expected_git_version = {
            "derivation": (
                mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_DERIVATION
            ),
            "value": mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION,
            "compiler_scope": "cxx",
        }
        expected_make_variables = {"IS_X86": 0}
        self.assertEqual(
            [mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_VERSION_MARKER],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            list(mednafen_pcfx.MEDNAFEN_PCFX_MAKE_MARKERS),
            pipeline.make_variable_log_markers(spec),
        )

        git_shell = pipeline.git_version_shell(spec)
        self.assertIn(
            "make --no-print-directory -s "
            "-C /libretro-super/libretro-mednafen_pcfx "
            "-f Makefile -f "
            "/tmp/core-pipeline-native-git-version-origin.mk "
            "core_pipeline_native_git_version_origin",
            git_shell,
        )
        self.assertNotIn("Makefile.libretro", git_shell)

        make_shell = pipeline.make_variable_shell(spec)
        self.assertIn("export MAKEFLAGS=IS_X86=0", make_shell)
        self.assertIn(
            "make --no-print-directory -s "
            "-C /libretro-super/libretro-mednafen_pcfx "
            "-f Makefile -f "
            "/tmp/core-pipeline-make-variable-origins.mk "
            "core_pipeline_make_variable_origins",
            make_shell,
        )
        self.assertNotIn("Makefile.libretro", make_shell)

        expected_build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": expected_git_version,
            "make_variables": expected_make_variables,
        }
        build_shell = pipeline.libretro_build_shell(spec, core_id)
        self.assertEqual("./libretro-build.sh mednafen_pcfx", build_shell)
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                self.assertEqual(
                    expected_build,
                    pipeline.normalized_build_contract(spec, architecture),
                )
                container_shell = pipeline.container_build_script(
                    core_id, architecture, spec, catalog["resolver"]
                )
                ordered_positions = (
                    container_shell.index("export MAKEFLAGS=IS_X86=0"),
                    container_shell.index(
                        "CORE_PIPELINE_MAKEFLAGS|$MAKEFLAGS"
                    ),
                    container_shell.index(
                        "CORE_PIPELINE_MAKE_VARIABLE|IS_X86|$(IS_X86)|"
                        "$(origin IS_X86)"
                    ),
                    container_shell.index(
                        "CORE_PIPELINE_NATIVE_GIT_VERSION|$(GIT_VERSION)|"
                        "$(origin GIT_VERSION)"
                    ),
                    container_shell.index(build_shell),
                )
                self.assertEqual(
                    tuple(sorted(ordered_positions)), ordered_positions
                )

    def test_pcfx_schema_requires_cxx_native_version_and_portable_make(
        self,
    ) -> None:
        schema = pipeline.load_json(ROOT / "manifests/core-builds.schema.json")
        self.assertEqual(
            {"$ref": "#/$defs/mednafenPcfxCore"},
            schema["properties"]["cores"]["properties"][
                mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
            ],
        )
        self.assertEqual(
            ["c", "cxx"],
            schema["$defs"]["nativeGitVersion"]["properties"][
                "compiler_scope"
            ]["enum"],
        )
        self.assertEqual(
            "cxx",
            schema["$defs"]["gitVersion"]["properties"][
                "compiler_scope"
            ]["const"],
        )

        pcfx_build = schema["$defs"]["mednafenPcfxCore"]["allOf"][1][
            "properties"
        ]["build"]
        pcfx_git_version = pcfx_build["properties"]["git_version"][
            "allOf"
        ][1]
        self.assertEqual(["compiler_scope"], pcfx_git_version["required"])
        self.assertEqual(
            {"const": "cxx"},
            pcfx_git_version["properties"]["compiler_scope"],
        )
        self.assertIn("make_variables", pcfx_build["required"])
        self.assertEqual(
            {"$ref": "#/$defs/pcfxPortableMakeVariables"},
            pcfx_build["properties"]["make_variables"],
        )

    def test_shared_validators_bind_pcfx_cxx_version_and_portable_make(
        self,
    ) -> None:
        spec = load_catalog_document()["cores"][
            mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
        ]
        git_version = spec["build"]["git_version"]
        make_variables = spec["build"]["make_variables"]
        source_commit = spec["source"]["commit"]
        version_token = (
            mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_LOG_TOKEN
        )
        for architecture in ("arm64", "armhf"):
            _contract, compile_lines, _link, _diagnostics, log = (
                build_mednafen_pcfx_log_fixture(architecture)
            )
            c_line = compile_lines[0]
            cxx_line = compile_lines[-1]
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log, git_version, source_commit, architecture
                    )
                )
                self.assertTrue(
                    pipeline.make_variable_log_proves_contract(
                        log, make_variables, architecture
                    )
                )
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        log.replace(
                            c_line,
                            c_line.replace(
                                " -O2", f" {version_token} -O2", 1
                            ),
                            1,
                        ),
                        git_version,
                        source_commit,
                        architecture,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        log.replace(
                            cxx_line,
                            cxx_line.replace(f" {version_token}", "", 1),
                            1,
                        ),
                        git_version,
                        source_commit,
                        architecture,
                    )
                )
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        log.replace(
                            cxx_line,
                            cxx_line.replace(
                                " -O2", " -DARCH_X86 -O2", 1
                            ),
                            1,
                        ),
                        make_variables,
                        architecture,
                    )
                )

    def test_catalog_predicate_rejects_each_owned_boundary(self) -> None:
        spec = load_catalog_document()["cores"][
            mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
        ]

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(spec)
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "workflow",
                lambda changed: changed.update({"workflow": "build.yml"}),
            ),
            mutation(
                "source-url",
                lambda changed: changed["source"].update(
                    {"url": "https://example.com/other.git"}
                ),
            ),
            mutation(
                "source-ref",
                lambda changed: changed["source"].update(
                    {"requested_ref": "refs/heads/main"}
                ),
            ),
            mutation(
                "source-commit",
                lambda changed: changed["source"].update(
                    {"commit": "0" * 40}
                ),
            ),
            mutation(
                "source-tree",
                lambda changed: changed["source"].update({"tree": "0" * 40}),
            ),
            mutation(
                "version-value",
                lambda changed: changed["build"]["git_version"].update(
                    {"value": " 0000000"}
                ),
            ),
            mutation(
                "compiler-scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "all"}
                ),
            ),
            mutation(
                "make-variable",
                lambda changed: changed["build"].update(
                    {"make_variables": {"IS_X86": 1}}
                ),
            ),
            mutation(
                "output",
                lambda changed: changed["build"].update(
                    {"output_path": "dist/unix/other.so"}
                ),
            ),
            mutation(
                "metadata",
                lambda changed: changed["metadata"].update(
                    {"artifact_name": "other.info"}
                ),
            ),
            mutation(
                "targets",
                lambda changed: changed.update({"targets": ["arm64"]}),
            ),
            mutation(
                "extra",
                lambda changed: changed.update({"unexpected": True}),
            ),
        )
        for label, changed in mutations:
            with self.subTest(mutation=label):
                self.assertFalse(
                    mednafen_pcfx.mednafen_pcfx_spec_is_well_formed(changed)
                )

    def test_reviewed_build_fingerprints_are_individual_and_exact(self) -> None:
        self.assertEqual(
            94, mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_COMPILE_COUNT
        )
        self.assertEqual(
            {"c": 60, "cxx": 34},
            mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS,
        )
        self.assertEqual(
            "e61c9c08bd49969baf71482752efdf818a78fa4cf02daa309179740c41919e1c",
            mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "9cd4372cc4283f2ef1977e89f25e635fea06baf5db9fabe130610cddffdb8e12"
                ),
                "armhf": (
                    "b916efc119269ad1a247b886c57b7b4f26ecc398bfb9c9581d34908f9ab156a4"
                ),
            },
            mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            "9481b21c046fd3db7c095917364c56293e8a28a1623eab13c39eeb185f861915",
            mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            {"ARCH_X86"},
            set(mednafen_pcfx.MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS),
        )
        self.assertEqual(
            {"arm64": 4, "armhf": 9},
            {
                arch: len(lines)
                for arch, lines in (
                    mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_WARNING_LINES.items()
                )
            },
        )
        self.assertEqual(
            {"arm64": 4, "armhf": 9},
            {
                arch: len(blocks)
                for arch, blocks in (
                    mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_DIAGNOSTIC_BLOCKS.items()
                )
            },
        )

    def test_synthetic_logs_prove_both_architecture_contracts(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compile, link_argv, _diagnostics, log = (
                build_mednafen_pcfx_log_fixture(architecture)
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    mednafen_pcfx.mednafen_pcfx_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_diagnostic_streams_allow_parallel_interleaving(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compile, link_argv, blocks, log = (
                build_mednafen_pcfx_log_fixture(architecture)
            )
            original = "\n".join(blocks)
            streams = [block.splitlines() for block in blocks]
            interleaved = "\n".join(
                line
                for index in range(max(map(len, streams)))
                for stream in streams
                if index < len(stream)
                for line in (stream[index],)
            )
            changed = log.replace(original, interleaved, 1)
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    mednafen_pcfx.mednafen_pcfx_log_proves_contract(
                        *self.contract_arguments(changed, architecture)
                    )
                )

    def test_synthetic_log_rejects_marker_and_identity_mutations(self) -> None:
        contract, _compile, link_argv, _diagnostics, log = (
            build_mednafen_pcfx_log_fixture("arm64")
        )
        arguments = self.contract_arguments(log)[1:]
        head = mednafen_pcfx.MEDNAFEN_PCFX_SOURCE_HEAD_MARKER
        marker = mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_VERSION_MARKER
        make_marker = mednafen_pcfx.MEDNAFEN_PCFX_MAKE_MARKERS[0]
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "missing-marker": log.replace(marker + "\n", "", 1),
            "late-marker": log.replace(marker + "\n", "", 1) + marker + "\n",
            "wrong-origin": log.replace("|file", "|command line", 1),
            "wrong-make": log.replace(make_marker, make_marker[:-1] + "1", 1),
            "injected-version": (
                log + "CORE_PIPELINE_GIT_VERSION|-650c30e|command line\n"
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_pcfx.mednafen_pcfx_log_proves_contract(
                            changed, *arguments
                        )
                    )
            for label, changed_arguments in {
                "core": (
                    "mednafen_wswan",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                ),
                "commit": (
                    mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                ),
                "tree": (
                    mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                ),
                "architecture": (
                    mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID,
                    "unknown",
                    contract.source_commit,
                    contract.source_tree,
                ),
            }.items():
                with self.subTest(identity=label):
                    self.assertFalse(
                        mednafen_pcfx.mednafen_pcfx_log_proves_contract(
                            log, *changed_arguments
                        )
                    )

    def test_synthetic_log_rejects_compile_and_link_mutations(self) -> None:
        contract, compile_lines, link_argv, _diagnostics, log = (
            build_mednafen_pcfx_log_fixture("arm64")
        )
        arguments = self.contract_arguments(log)[1:]
        c_line = compile_lines[0]
        cxx_line = compile_lines[-1]
        link_line = " ".join(link_argv)
        version_token = (
            mednafen_pcfx.MEDNAFEN_PCFX_NATIVE_GIT_VERSION_LOG_TOKEN
        )
        first_objects = "pcfx/c/unit_000.o pcfx/c/unit_001.o"
        mutations = {
            "missing-compile": log.replace(c_line + "\n", "", 1),
            "duplicate-compile": log.replace(c_line, c_line + "\n" + c_line, 1),
            "compile-option": log.replace(
                c_line, c_line.replace("-O2", "-O3", 1), 1
            ),
            "response-file": log.replace(
                c_line, c_line.replace(" -O2", " @args.rsp -O2", 1), 1
            ),
            "version-on-c": log.replace(
                c_line, c_line.replace(" -O2", f" {version_token} -O2", 1), 1
            ),
            "version-missing-cxx": log.replace(
                cxx_line, cxx_line.replace(f" {version_token}", "", 1), 1
            ),
            "host-macro": log.replace(
                c_line, c_line.replace(" -O2", " -DARCH_X86 -O2", 1), 1
            ),
            "link-missing-object": log.replace(
                link_line,
                link_line.replace(" pcfx/c/unit_000.o", "", 1),
                1,
            ),
            "link-object-order": log.replace(
                link_line,
                link_line.replace(
                    first_objects,
                    "pcfx/c/unit_001.o pcfx/c/unit_000.o",
                    1,
                ),
                1,
            ),
            "link-option-order": log.replace(
                link_line,
                link_line.replace("-pthread -fPIC", "-fPIC -pthread", 1),
                1,
            ),
            "link-compiler": log.replace(
                link_line,
                link_line.replace(
                    "aarch64-linux-gnu-g++", "aarch64-linux-gnu-gcc", 1
                ),
                1,
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_pcfx.mednafen_pcfx_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_synthetic_log_rejects_diagnostic_mutations(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compile, link_argv, blocks, log = (
                build_mednafen_pcfx_log_fixture(architecture)
            )
            arguments = self.contract_arguments(log, architecture)[1:]
            warning = (
                mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_WARNING_LINES[
                    architecture
                ][0]
            )
            context_line = blocks[0].splitlines()[0]
            late_context_line = blocks[0].splitlines()[-1]
            diagnostic_text = "\n".join(blocks)
            mutations = {
                "missing-warning": log.replace(warning + "\n", "", 1),
                "changed-warning": log.replace(
                    "warning: variable 'mode_changed'",
                    "warning: value 'mode_changed'",
                    1,
                ),
                "missing-context": log.replace(context_line + "\n", "", 1),
                "changed-context": log.replace(
                    context_line, context_line.replace("virtual ", ""), 1
                ),
                "extra-warning": log + "warning: synthetic warning\n",
                "extra-note": log + "note: synthetic note\n",
                "error": log + "error: synthetic error\n",
                "make": log + "make: *** [all] Error 2\n",
                "linker": log + "undefined reference to synthetic_symbol\n",
                "late-diagnostics": log.replace(
                    diagnostic_text + "\n", "", 1
                )
                + diagnostic_text
                + "\n",
                "late-context": log.replace(
                    late_context_line + "\n", "", 1
                )
                + late_context_line
                + "\n",
            }
            if architecture == "armhf":
                note = mednafen_pcfx.MEDNAFEN_PCFX_EXPECTED_NOTE_LINES[
                    architecture
                ][0]
                mutations["missing-note"] = log.replace(note + "\n", "", 1)
                mutations["changed-note"] = log.replace(
                    "changed in GCC 7.1", "changed in GCC 8.1", 1
                )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                for label, changed in mutations.items():
                    with self.subTest(mutation=label):
                        self.assertFalse(
                            mednafen_pcfx.mednafen_pcfx_log_proves_contract(
                                changed, *arguments
                            )
                        )

class MednafenPcfxRecipeSnapshotTests(unittest.TestCase):
    def test_recipe_snapshot_v8_binds_portable_native_contract(self) -> None:
        catalog_path = ROOT / "manifests/core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = mednafen_pcfx.MEDNAFEN_PCFX_CORE_ID
        architecture = "arm64"
        spec = catalog["cores"][core_id]
        source = {
            **spec["source"],
            "resolved_commit": spec["source"]["commit"],
            "resolved_url": spec["source"]["url"],
            "submodules": [],
        }
        recipe = copy.deepcopy(
            pipeline.recipe_record(catalog_path, core_id, spec)
        )
        pipeline_bundle = recipe.pop("pipeline_bundle")
        commit_blacklist = recipe.pop("commit_blacklist")
        self.assertTrue(
            pipeline.pipeline_source_bundle_is_well_formed(pipeline_bundle)
        )
        self.assertTrue(
            pipeline.commit_blacklist_reference_is_well_formed(
                commit_blacklist
            )
        )
        record = {
            "core_id": core_id,
            "architecture": architecture,
            "source": source,
            "recipe": recipe,
            "toolchain": {
                **catalog["toolchains"][architecture],
                "resolved_image_id": catalog["toolchains"][architecture][
                    "image_id"
                ],
                "resolver_digests": catalog["resolver"],
                "archive_provenance": pipeline.expected_archive_provenance(
                    catalog, architecture
                ),
            },
            "artifact": {"sha256": "a" * 64, "needed": []},
            "metadata": {"status": "valid", "sha256": "b" * 64},
            "build": {
                **pipeline.normalized_build_contract(spec, architecture),
                "log": "build.log",
                "log_sha256": "c" * 64,
            },
        }
        self.assertTrue(
            mednafen_pcfx_combined_golden_build_contract_is_well_formed(
                record["build"],
                source["resolved_commit"],
                core_id,
                source,
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "mednafen-pcfx-v8.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(8, snapshot["schema_version"])
            self.assertEqual(
                pipeline.recorded_build_contract(record["build"]),
                snapshot["build"],
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "mednafen_pcfx/v8"
                ),
            )

            original_identity = pipeline.provenance_identity_sha256(record)
            for label, mutate in (
                (
                    "host-x86",
                    lambda changed: changed["build"]["make_variables"].update(
                        {"IS_X86": 1}
                    ),
                ),
                (
                    "missing-make-variable",
                    lambda changed: changed["build"].pop("make_variables"),
                ),
                (
                    "compiler-scope",
                    lambda changed: changed["build"]["git_version"].update(
                        {"compiler_scope": "all"}
                    ),
                ),
            ):
                changed = copy.deepcopy(record)
                mutate(changed)
                with self.subTest(build=label):
                    self.assertNotEqual(
                        original_identity,
                        pipeline.provenance_identity_sha256(changed),
                    )
                    self.assertFalse(
                        mednafen_pcfx_combined_golden_build_contract_is_well_formed(
                            changed["build"],
                            source["resolved_commit"],
                            core_id,
                            source,
                        )
                    )
                    self.assertTrue(
                        pipeline.verify_recipe_snapshot(
                            snapshot_path,
                            changed,
                            f"mednafen_pcfx/v8-{label}",
                        )
                    )

            snapshot["schema_version"] = 7
            snapshot_path.write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            self.assertIn(
                "mednafen_pcfx/v8-version: recipe snapshot schema version mismatch",
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "mednafen_pcfx/v8-version"
                ),
            )


if __name__ == "__main__":
    unittest.main()
