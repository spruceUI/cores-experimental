from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import shlex
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import genesis_plus_gx, genesis_plus_gx_wide
from core_pipeline_lib.contracts.c_only import (
    c_only_compile_invocation,
    c_only_compile_invocation_sha256,
    c_only_compile_pair_sha256,
    c_only_link_object_sha256,
    c_only_raw_link_object_sha256,
)
from core_pipeline_lib.contracts.command_line import ordered_command_argv_sha256
from core_pipeline_lib.foundation import sha256_file


ROOT = Path(__file__).resolve().parents[1]
ORACLE_DIRECTORY = (
    ROOT
    / "tests"
    / "fixtures"
    / "per-core-oracles"
    / "genesis_plus_gx_wide"
)
ORACLE_LOGS = {
    "arm64-final": ORACLE_DIRECTORY / "arm64-final-build.txt",
    "arm64-repro": ORACLE_DIRECTORY / "arm64-repro-build.txt",
    "armhf": ORACLE_DIRECTORY / "armhf-build.txt",
}
ORACLE_LOG_IDENTITIES = {
    "arm64-final": (
        "8b37e8dd6bf072cb75a19d8cb243406b3fa798e0515976fd9d9c537ee9fffc8d",
        90711,
        163,
    ),
    "arm64-repro": (
        "86e233f0ab64f00d5985ffdbea2b990d15ef47e60e6fed0ee91d06820744dd60",
        90711,
        163,
    ),
    "armhf": (
        "9d52149408262de1a3b22b549ecc07b9283ce7c1968e728c2188927ea39551f4",
        89680,
        142,
    ),
}


def build_genesis_plus_gx_wide_log_fixture(architecture: str) -> dict:
    compilers = {
        "arm64": (
            "aarch64-linux-gnu-gcc",
            "aarch64-linux-gnu-g++",
        ),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }
    catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
    core_id = genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID
    spec = catalog["cores"][core_id]
    compiler, cxx_compiler = compilers[architecture]
    contract = genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
    count = contract.expected_compile_count
    version_value = spec["build"]["git_version"]["value"]
    version_token = '-DGIT_VERSION=\\""' + version_value + '"\\"'
    pairs = [
        (f"genplus/unit_{index:03d}.o", f"genplus/unit_{index:03d}.c")
        for index in range(count)
    ]
    compile_lines = [
        (
            f"{compiler} -o{output} -c {source} {version_token} "
            "-O2 -DNDEBUG -fPIC"
        )
        for output, source in pairs
    ]
    compile_invocations = []
    for compile_line in compile_lines:
        invocation = c_only_compile_invocation(
            shlex.split(compile_line), {compiler}
        )
        if invocation is None:
            raise AssertionError(
                "synthetic Genesis Plus GX Wide fixture is invalid"
            )
        compile_invocations.append(invocation)
    raw_link_operands = [
        f"./{output}" for output, _source in reversed(pairs)
    ]
    link_line = " ".join(
        [
            compiler,
            "-o",
            contract.build_artifact_name,
            "-fPIC",
            *raw_link_operands,
            "-shared",
            "-Wl,--version-script=./libretro/link.T",
            "-Wl,--no-undefined",
            "-lm",
        ]
    )
    compile_order = [*range(0, count, 2), *range(1, count, 2)]
    diagnostic_compile_source = {
        name: pairs[index][1]
        for index, name in enumerate(
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS[
                architecture
            ]
        )
    }
    diagnostic_lines = [
        line
        for stream in (
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS[
                architecture
            ]
            .values()
        )
        for line in stream
    ]
    make_command = "make" if architecture == "arm64" else "gmake"
    phase_lines = {
        "clone": (
            'git clone "https://github.com/libretro/Genesis-Plus-GX-Wide.git" '
            '"/libretro-super/libretro-genesis_plus_gx_wide"'
        ),
        "cd": 'cd "/libretro-super/libretro-genesis_plus_gx_wide"',
        "clean": (
            f'{make_command} -f Makefile.libretro platform="unix" '
            "-j24  clean"
        ),
        "build": (
            f'{make_command} -f Makefile.libretro platform="unix" -j24 '
            f'CC="{compiler}" CXX="{cxx_compiler}" '
        ),
    }
    prelude_lines = [
        "PLATFORM: Linux",
        "ARCHITECTURE: x86_64",
        "TARGET: unix",
        "=== Genesis Plus GX",
        "Fetching genesis_plus_gx_wide...",
        phase_lines["clone"],
        "Cloning into '/libretro-super/libretro-genesis_plus_gx_wide'...",
        "1 core(s) successfully processed:",
        "\tgenesis_plus_gx_wide",
        genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_SOURCE_HEAD_MARKER,
        *pipeline.git_version_log_markers(spec),
        "Building genesis_plus_gx_wide...",
        phase_lines["cd"],
        phase_lines["clean"],
        "rm -f synthetic-wide-objects",
        phase_lines["build"],
    ]
    lines = [
        *prelude_lines,
        *[compile_lines[index] for index in compile_order],
        *diagnostic_lines,
        link_line,
        *genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER,
    ]
    log = "\n".join(lines) + "\n"
    canonicalized_lines = (
        genesis_plus_gx_wide._canonicalized_parallelism_lines(
            tuple(log.splitlines()), architecture
        )
    )
    if canonicalized_lines is None:
        raise AssertionError(
            "synthetic Genesis Plus GX Wide parallel commands are invalid"
        )
    return {
        "architecture": architecture,
        "compiler": compiler,
        "compile_lines": compile_lines,
        "cxx_compiler": cxx_compiler,
        "diagnostic_compile_source": diagnostic_compile_source,
        "diagnostic_lines": diagnostic_lines,
        "link_line": link_line,
        "log": log,
        "log_line_multiset_sha256": (
            genesis_plus_gx_wide._multiset_lines_sha256(
                canonicalized_lines
            )
        ),
        "pairs": pairs,
        "phase_lines": phase_lines,
        "prelude_lines": prelude_lines,
        "prelude_sha256": genesis_plus_gx_wide._lines_sha256(
            canonicalized_lines[: len(prelude_lines)]
        ),
        "pair_sha256": c_only_compile_pair_sha256(pairs),
        "invocation_sha256": c_only_compile_invocation_sha256(
            compile_invocations
        ),
        "link_object_sha256": c_only_link_object_sha256(
            output for output, _source in pairs
        ),
        "raw_link_object_sha256": c_only_raw_link_object_sha256(
            raw_link_operands
        ),
        "link_invocation_sha256": ordered_command_argv_sha256(
            shlex.split(link_line)
        ),
        "raw_link_operands": raw_link_operands,
        "spec": spec,
        "version_token": version_token,
    }


def patch_genesis_plus_gx_wide_contract(fixture: dict):
    contract = replace(
        genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT,
        expected_compile_pair_sha256=fixture["pair_sha256"],
        expected_compile_invocation_sha256={
            fixture["architecture"]: fixture["invocation_sha256"]
        },
        expected_link_object_sha256=fixture["link_object_sha256"],
        expected_raw_link_object_sha256=fixture["raw_link_object_sha256"],
        expected_link_invocation_sha256={
            fixture["architecture"]: fixture["link_invocation_sha256"]
        },
    )
    return mock.patch.multiple(
        genesis_plus_gx_wide,
        GENESIS_PLUS_GX_WIDE_LOG_CONTRACT=contract,
        GENESIS_PLUS_GX_WIDE_EXPECTED_LOG_LINE_MULTISET_SHA256={
            fixture["architecture"]: fixture[
                "log_line_multiset_sha256"
            ]
        },
        GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_LINE_COUNT={
            fixture["architecture"]: len(fixture["prelude_lines"])
        },
        GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_SHA256={
            fixture["architecture"]: fixture["prelude_sha256"]
        },
        GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE={
            fixture["architecture"]: fixture[
                "diagnostic_compile_source"
            ]
        },
    )


class GenesisPlusGxWideLogContractTests(unittest.TestCase):
    def test_individual_constants_bind_the_wide_contract(self) -> None:
        core_id = genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID
        self.assertEqual("genesis_plus_gx_wide", core_id)
        self.assertEqual(
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_C_COMPILE_COUNT,
            (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
                .expected_compile_count
            ),
        )
        self.assertEqual(
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_COMPILE_PAIR_SHA256,
            (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
                .expected_compile_pair_sha256
            ),
        )
        self.assertEqual(
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_COMPILE_INVOCATION_SHA256,
            (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
                .expected_compile_invocation_sha256
            ),
        )
        self.assertEqual(
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LINK_OBJECT_SHA256,
            (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
                .expected_link_object_sha256
            ),
        )
        self.assertEqual(
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_RAW_LINK_OBJECT_SHA256,
            (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
                .expected_raw_link_object_sha256
            ),
        )
        self.assertEqual(
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LINK_INVOCATION_SHA256,
            (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LOG_CONTRACT
                .expected_link_invocation_sha256
            ),
        )
        self.assertEqual(
            "d57eadc2c06b2c88ec9fd5ad2b0b3d30ef45c918044e571dce9b1861bbe0574d",
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "4fbe11782d08a47d8677e82d6980d9b2d3c76cb5943364dc603d809d385b0267"
                ),
                "armhf": (
                    "c3ca0f9e58e1e516cc7c4d8a65f485a4f1801e182de8660abab8f0d49f2bd1c6"
                ),
            },
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            "ba4396294516013831bd08a87deb9437b1ad4949730820ce397a94e9d75fad0f",
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_RAW_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "e510f0e940003d7582a74495689b800610fab1a083545be1f0359b22995ed0bc"
                ),
                "armhf": (
                    "dbee2ead17bebf265ed2e3b010713e3f00fa4edb643bcc7ab57ef850ed66645d"
                ),
            },
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_LINK_INVOCATION_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "b78708f9863d6bfa407b0cb09b11cf173da079927e67feaf6ebd1ea878de737b"
                ),
                "armhf": (
                    "fe3ff4cefd35047fbbb92fc1adf9947452cc3ab8c5216247753d07895c9c6be5"
                ),
            },
            (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_EXPECTED_LOG_LINE_MULTISET_SHA256
            ),
        )
        self.assertEqual(
            {"arm64": 32, "armhf": 32},
            (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_LINE_COUNT
            ),
        )
        self.assertEqual(
            {
                "arm64": (
                    "72d93236699d543e720b908396300c7e2d253cc746320d1b8e271cf2895cf21d"
                ),
                "armhf": (
                    "413ba5df644488f36cf91e071eb87c1d8716d8f66e10088e8d9356b33dec3543"
                ),
            },
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_SHA256,
        )
        self.assertEqual(
            {
                "arm64": {
                    "make": "make",
                    "cc": "aarch64-linux-gnu-gcc",
                    "cxx": "aarch64-linux-gnu-g++",
                },
                "armhf": {
                    "make": "gmake",
                    "cc": "arm-a30-linux-gnueabihf-gcc",
                    "cxx": "arm-a30-linux-gnueabihf-g++",
                },
            },
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_PARALLEL_COMMAND,
        )
        self.assertEqual(
            {
                "arm64": {
                    "cdrom": "libretro/libretro-common/cdrom/cdrom.c",
                    "libretro": "libretro/libretro.c",
                },
                "armhf": {},
            },
            (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE
            ),
        )
        stream_lengths = {
            name: len(lines)
            for name, lines in (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS["arm64"]
                .items()
            )
        }
        self.assertEqual({"cdrom": 8, "libretro": 13}, stream_lengths)
        for name, lines in (
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS["arm64"]
            .items()
        ):
            with self.subTest(diagnostic_stream=name):
                self.assertEqual(
                    (
                        genesis_plus_gx_wide
                        .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAM_SHA256[
                            name
                        ]
                    ),
                    genesis_plus_gx_wide._lines_sha256(lines),
                )

    def test_catalog_and_command_scope_use_wide_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        core_id = genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID
        spec = catalog["cores"][core_id]
        identity = (
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertIs(identity, pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[core_id])
        self.assertEqual(
            {
                "url": "https://github.com/libretro/Genesis-Plus-GX-Wide.git",
                "requested_ref": "refs/heads/main",
                "commit": "29d9d104338f46bc2e65438fb207bcf54f701e92",
                "tree": "27e05ed457d9c10e51b6c69067e1c05599df08fb",
            },
            spec["source"],
        )
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(
            identity["source_requested_ref"], spec["source"]["requested_ref"]
        )
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(identity["artifact_name"], spec["build"]["artifact_name"])
        self.assertEqual(
            {
                "derivation": "native-space-short7-v1",
                "value": " 29d9d10",
                "compiler_scope": "c",
            },
            pipeline.validated_git_version(spec),
        )
        self.assertEqual(
            '" 29d9d10"', pipeline.command_scoped_native_git_version(spec)
        )
        markers = pipeline.git_version_log_markers(spec)
        self.assertEqual(
            [
                (
                    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                    '" 29d9d10"|command-scoped-environment'
                ),
                'CORE_PIPELINE_NATIVE_GIT_VERSION|" 29d9d10"|environment',
            ],
            markers,
        )
        origin_shell = pipeline.git_version_shell(spec)
        build_shell = pipeline.libretro_build_shell(spec, core_id)
        assignment = "GIT_VERSION='\" 29d9d10\"'"
        self.assertIn(markers[0], origin_shell)
        self.assertIn("core_pipeline_native_git_version_origin", origin_shell)
        self.assertIn(assignment + " make --no-print-directory", origin_shell)
        self.assertEqual(
            assignment + " ./libretro-build.sh genesis_plus_gx_wide",
            build_shell,
        )
        container_shell = pipeline.container_build_script(
            core_id, "arm64", spec, catalog["resolver"]
        )
        self.assertLess(
            container_shell.index(markers[0]),
            container_shell.index(build_shell),
        )
        self.assertEqual(2, container_shell.count(assignment))
        snapshot_record = {
            "core_id": core_id,
            "architecture": "arm64",
            "source": {
                **spec["source"],
                "resolved_commit": spec["source"]["commit"],
                "resolved_url": spec["source"]["url"],
                "submodules": [],
            },
            "recipe": {
                "catalog_path": "manifests/core-builds.json",
                "workflow": spec["workflow"],
            },
            "toolchain": {
                **catalog["toolchains"]["arm64"],
                "resolved_image_id": catalog["toolchains"]["arm64"]["image_id"],
                "resolver_digests": catalog["resolver"],
            },
            "build": {
                **pipeline.normalized_build_contract(spec, "arm64"),
                "log": "build.log",
                "log_sha256": "a" * 64,
            },
        }
        snapshot = json.loads(pipeline.recipe_snapshot(snapshot_record))
        self.assertEqual(7, snapshot["schema_version"])

    def test_exact_log_accepts_order_independent_compile_and_link_sets(
        self,
    ) -> None:
        core_id = genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID
        for architecture in ("arm64", "armhf"):
            fixture = build_genesis_plus_gx_wide_log_fixture(architecture)
            spec = fixture["spec"]
            with self.subTest(
                architecture=architecture
            ), patch_genesis_plus_gx_wide_contract(fixture):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        fixture["log"],
                        spec["build"]["git_version"],
                        spec["source"]["commit"],
                        architecture,
                    )
                )
                self.assertTrue(
                    genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                        fixture["log"],
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                portable_jobs_log = fixture["log"].replace("-j24", "-j4")
                self.assertEqual(2, fixture["log"].count("-j24"))
                self.assertTrue(
                    genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                        portable_jobs_log,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                first_compile = fixture["compile_lines"][0]
                first_output, _first_source = fixture["pairs"][0]
                split_compile_output = fixture["log"].replace(
                    f"-o{first_output}", f"-o {first_output}", 1
                )
                reordered_lines = fixture["log"].splitlines()
                first_compile_position = reordered_lines.index(first_compile)
                reordered_lines[
                    first_compile_position : first_compile_position + 2
                ] = reversed(
                    reordered_lines[
                        first_compile_position : first_compile_position + 2
                    ]
                )
                reordered_compile_lines = "\n".join(reordered_lines) + "\n"
                attached_link_output = fixture["log"].replace(
                    "-o genesis_plus_gx_wide_libretro.so",
                    "-ogenesis_plus_gx_wide_libretro.so",
                    1,
                )
                self.assertFalse(
                    genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                        split_compile_output,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                self.assertNotEqual(fixture["log"], reordered_compile_lines)
                self.assertTrue(
                    genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                        reordered_compile_lines,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                self.assertFalse(
                    genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                        attached_link_output,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                self.assertIn("-o" + first_output, first_compile)

    def test_compile_and_link_parser_fails_closed(self) -> None:
        fixture = build_genesis_plus_gx_wide_log_fixture("arm64")
        baseline = fixture["log"]
        spec = fixture["spec"]
        first_compile = fixture["compile_lines"][0]
        second_compile = fixture["compile_lines"][1]
        first_output, first_source = fixture["pairs"][0]
        second_output, second_source = fixture["pairs"][1]
        link_line = fixture["link_line"]
        first_link_operand, second_link_operand = fixture[
            "raw_link_operands"
        ][:2]
        compiler = fixture["compiler"]
        mutations = {
            "missing-compile": baseline.replace(first_compile + "\n", "", 1),
            "duplicate-compile-pair": baseline.replace(
                second_compile, first_compile, 1
            ),
            "duplicate-output-different-source": baseline.replace(
                second_compile,
                second_compile.replace(
                    "-o" + second_output, "-o" + first_output, 1
                ),
                1,
            ),
            "duplicate-source-different-output": baseline.replace(
                second_compile,
                second_compile.replace(second_source, first_source, 1),
                1,
            ),
            "canonical-pair-substitution": baseline.replace(
                first_compile,
                first_compile.replace(
                    first_output, "genplus/substitute_000.o", 1
                ).replace(first_source, "genplus/substitute_000.c", 1),
                1,
            ).replace(
                "./" + first_output, "./genplus/substitute_000.o", 1
            ),
            "extra-source": baseline.replace(
                first_compile,
                first_compile.replace(
                    first_source, first_source + " extra.c", 1
                ),
                1,
            ),
            "source-extension": baseline.replace(
                first_source, "genplus/unit_000.cpp", 1
            ),
            "output-source-mismatch": baseline.replace(
                "-o" + first_output, "-ogenplus/rogue.o", 1
            ),
            "missing-output": baseline.replace(
                "-o" + first_output + " ", "", 1
            ),
            "bare-output": baseline.replace("-o" + first_output, "-o", 1),
            "duplicate-c": baseline.replace(" -c ", " -c -c ", 1),
            "compiler-wrapper": baseline.replace(
                first_compile, "ccache " + first_compile, 1
            ),
            "compiler-path-wrapper": baseline.replace(
                first_compile,
                first_compile.replace(compiler, "/tmp/" + compiler, 1),
                1,
            ),
            "target-cxx": baseline.replace(
                first_compile,
                first_compile.replace(compiler, fixture["cxx_compiler"], 1),
                1,
            ),
            "response-file": baseline.replace(
                first_compile,
                first_compile.replace(" -O2 ", " @compiler.rsp -O2 ", 1),
                1,
            ),
            "explicit-language": baseline.replace(
                first_compile,
                first_compile.replace(" -O2 ", " -x c -O2 ", 1),
                1,
            ),
            "missing-link": baseline.replace(link_line + "\n", "", 1),
            "duplicate-link": baseline + link_line + "\n",
            "reordered-link-operands": baseline.replace(
                f"{first_link_operand} {second_link_operand}",
                f"{second_link_operand} {first_link_operand}",
                1,
            ),
            "raw-link-alias": baseline.replace(
                first_link_operand,
                first_link_operand.removeprefix("./"),
                1,
            ),
            "reordered-link-option": baseline.replace(
                f"-fPIC {first_link_operand}",
                f"{first_link_operand} -fPIC",
                1,
            ),
            "attached-link-output": baseline.replace(
                "-o genesis_plus_gx_wide_libretro.so",
                "-ogenesis_plus_gx_wide_libretro.so",
                1,
            ),
            "missing-link-output": baseline.replace(
                "-o genesis_plus_gx_wide_libretro.so ", "", 1
            ),
            "wrong-link-output": baseline.replace(
                "genesis_plus_gx_wide_libretro.so", "rogue_libretro.so", 1
            ),
            "link-object-mismatch": baseline.replace(
                link_line,
                link_line.replace(
                    "./" + first_output, "./" + second_output, 1
                ),
                1,
            ),
            "link-archive-input": baseline.replace(
                link_line,
                link_line.replace(" -shared ", " rogue.a -shared ", 1),
                1,
            ),
            "unexpected-link-option": baseline.replace(
                link_line,
                link_line.replace(" -shared ", " -pthread -shared ", 1),
                1,
            ),
            "link-response-file": baseline.replace(
                link_line,
                link_line.replace(" -shared ", " @link.rsp -shared ", 1),
                1,
            ),
            "malformed-command": baseline + compiler + " 'unterminated -c\n",
        }
        with patch_genesis_plus_gx_wide_contract(fixture):
            self.assertTrue(
                genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                    baseline,
                    genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            for label, changed_log in mutations.items():
                with self.subTest(log=label):
                    self.assertFalse(
                        genesis_plus_gx_wide
                        .genesis_plus_gx_wide_log_proves_contract(
                            changed_log,
                            (
                                genesis_plus_gx_wide
                                .GENESIS_PLUS_GX_WIDE_CORE_ID
                            ),
                            "arm64",
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )

            for label, commit, tree in (
                ("wrong-commit", "0" * 40, spec["source"]["tree"]),
                ("wrong-tree", spec["source"]["commit"], "0" * 40),
            ):
                with self.subTest(identity=label):
                    self.assertFalse(
                        genesis_plus_gx_wide
                        .genesis_plus_gx_wide_log_proves_contract(
                            baseline,
                            (
                                genesis_plus_gx_wide
                                .GENESIS_PLUS_GX_WIDE_CORE_ID
                            ),
                            "arm64",
                            commit,
                            tree,
                        )
                    )

    def test_exact_version_proof_rejects_automatic_abbreviation(self) -> None:
        fixture = build_genesis_plus_gx_wide_log_fixture("arm64")
        baseline = fixture["log"]
        spec = fixture["spec"]
        markers = pipeline.git_version_log_markers(spec)
        first_compile = fixture["compile_lines"][0]
        token = fixture["version_token"]
        mutations = {
            "missing-build-arg-marker": baseline.replace(
                markers[0] + "\n", "", 1
            ),
            "duplicate-build-arg-marker": markers[0] + "\n" + baseline,
            "wrong-build-arg-scope": baseline.replace(
                "|command-scoped-environment", "|ambient-environment", 1
            ),
            "wrong-make-origin": baseline.replace("|environment", "|file", 1),
            "late-markers": baseline.replace("\n".join(markers) + "\n", "", 1)
            + "\n".join(markers)
            + "\n",
            "auto-expanded-eight-char": baseline.replace(
                " 29d9d10", " 29d9d104"
            ),
            "missing-compile-token": baseline.replace(" " + token, "", 1),
            "duplicate-compile-token": baseline.replace(
                token, token + " " + token, 1
            ),
            "unquoted-token": baseline.replace(
                token, "-DGIT_VERSION=29d9d10", 1
            ),
            "conflicting-token": baseline.replace(
                token,
                token + r' -DGIT_VERSION=\"" 0000000"\"',
                1,
            ),
            "token-on-cxx": baseline
            + (
                f"{fixture['cxx_compiler']} {token} -c rogue.cpp "
                "-orogue.o\n"
            ),
            "response-file": baseline.replace(
                first_compile,
                first_compile.replace(" -O2 ", " @compiler.rsp -O2 ", 1),
                1,
            ),
            "forwarded-response-file": baseline.replace(
                first_compile,
                first_compile.replace(
                    " -O2 ", " -Wp,@compiler.rsp -O2 ", 1
                ),
                1,
            ),
            "compiler-wrapper": baseline.replace(
                first_compile, "ccache " + first_compile, 1
            ),
            "compiler-path-wrapper": baseline.replace(
                first_compile,
                first_compile.replace(
                    fixture["compiler"], "/tmp/" + fixture["compiler"], 1
                ),
                1,
            ),
        }
        for label, changed_log in mutations.items():
            with self.subTest(log=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        changed_log,
                        spec["build"]["git_version"],
                        spec["source"]["commit"],
                        "arm64",
                    )
                )

    def test_markers_diagnostics_and_success_envelope_fail_closed(self) -> None:
        for architecture in ("arm64", "armhf"):
            fixture = build_genesis_plus_gx_wide_log_fixture(architecture)
            baseline = fixture["log"]
            spec = fixture["spec"]
            source_marker = (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_SOURCE_HEAD_MARKER
            )
            build_arg_marker = (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_BUILD_ARG_MARKER
            )
            native_marker = (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_MARKER
            )
            first_compile = fixture["compile_lines"][0]
            link_line = fixture["link_line"]
            copy_line = (
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER[0]
            )

            def insert_before_link(line: str) -> str:
                return baseline.replace(
                    link_line + "\n", line + "\n" + link_line + "\n", 1
                )

            def move_before_copy(line: str) -> str:
                moved = baseline.replace(line + "\n", "", 1)
                return moved.replace(
                    copy_line + "\n", line + "\n" + copy_line + "\n", 1
                )

            moved_compile = baseline.replace(first_compile + "\n", "", 1)
            moved_compile = moved_compile.replace(
                source_marker + "\n",
                first_compile + "\n" + source_marker + "\n",
                1,
            )
            moved_link = baseline.replace(link_line + "\n", "", 1)
            moved_link = moved_link.replace(
                first_compile + "\n",
                link_line + "\n" + first_compile + "\n",
                1,
            )
            mutations = {
                "missing-source-marker": baseline.replace(
                    source_marker + "\n", "", 1
                ),
                "wrong-source-marker": baseline.replace(
                    source_marker,
                    "HEAD is now at 00000000 synthetic source",
                    1,
                ),
                "duplicate-source-marker": baseline.replace(
                    source_marker + "\n",
                    source_marker + "\n" + source_marker + "\n",
                    1,
                ),
                "missing-build-arg-marker": baseline.replace(
                    build_arg_marker + "\n", "", 1
                ),
                "missing-native-marker": baseline.replace(
                    native_marker + "\n", "", 1
                ),
                "swapped-native-markers": baseline.replace(
                    build_arg_marker + "\n" + native_marker,
                    native_marker + "\n" + build_arg_marker,
                    1,
                ),
                "legacy-version-marker": baseline.replace(
                    native_marker + "\n",
                    native_marker
                    + "\nCORE_PIPELINE_GIT_VERSION|29d9d10|legacy\n",
                    1,
                ),
                "compile-before-markers": moved_compile,
                "link-before-compile": moved_link,
                "mismatched-parallel-jobs": baseline.replace(
                    "-j24", "-j4", 1
                ),
                "unbounded-parallel-jobs": baseline.replace("-j24", "-j0"),
                "leading-zero-parallel-jobs": baseline.replace(
                    "-j24", "-j04"
                ),
                "long-form-parallel-jobs": baseline.replace(
                    "-j24", "--jobs=4"
                ),
                "changed-clean-command": baseline.replace(
                    fixture["phase_lines"]["clean"],
                    fixture["phase_lines"]["clean"].replace(
                        "Makefile.libretro", "./Makefile.libretro", 1
                    ),
                    1,
                ),
                **{
                    f"{name}-after-link": move_before_copy(line)
                    for name, line in fixture["phase_lines"].items()
                },
                "injected-warning": insert_before_link(
                    "synthetic.c:1: warning: injected diagnostic"
                ),
                "injected-note": insert_before_link(
                    "synthetic.c:1: note: injected diagnostic"
                ),
                "compiler-error": insert_before_link(
                    "cc1: error: synthetic failure"
                ),
                "make-failure": insert_before_link(
                    "make[1]: *** [Makefile:1: all] Error 2"
                ),
                "undefined-reference": insert_before_link(
                    "ld: undefined reference to synthetic_symbol"
                ),
                "ninja-failure": insert_before_link(
                    "ninja: build stopped: subcommand failed."
                ),
                "generic-build-failure": insert_before_link("BUILD FAILED"),
                "killed": insert_before_link("Killed"),
                "shell-command-not-found": insert_before_link(
                    "/bin/sh: 1: synthetic-tool: not found"
                ),
                "compilation-terminated": insert_before_link(
                    "compilation terminated."
                ),
                "sanitizer-failure": insert_before_link(
                    "AddressSanitizer: DEADLYSIGNAL"
                ),
                "copy-failure": insert_before_link(
                    "cp: cannot stat synthetic.so"
                ),
                "missing-copy": baseline.replace(
                    genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER[
                        0
                    ]
                    + "\n",
                    "",
                    1,
                ),
                "missing-success": baseline.replace(
                    "1 core(s) successfully processed:\n"
                    "\tgenesis_plus_gx_wide\n",
                    "",
                    1,
                ),
                "duplicate-success-trailer": baseline
                + "".join(
                    line + "\n"
                    for line in (
                        genesis_plus_gx_wide
                        .GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER
                    )
                ),
                "nonterminal-success": baseline + "post-success noise\n",
            }
            diagnostic_lines = fixture["diagnostic_lines"]
            if diagnostic_lines:
                diagnostic_block = "\n".join(diagnostic_lines) + "\n"
                diagnostics_before_owner = {}
                for name, stream in (
                    genesis_plus_gx_wide
                    .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS[
                        architecture
                    ]
                    .items()
                ):
                    stream_block = "\n".join(stream) + "\n"
                    owner_source = fixture["diagnostic_compile_source"][name]
                    owner_compile = next(
                        line
                        for line in fixture["compile_lines"]
                        if f" -c {owner_source} " in line
                    )
                    without_stream = baseline.replace(stream_block, "", 1)
                    diagnostics_before_owner[
                        f"{name}-diagnostics-before-owner"
                    ] = without_stream.replace(
                        owner_compile + "\n",
                        stream_block + owner_compile + "\n",
                        1,
                    )
                mutations.update(
                    {
                        "missing-diagnostic-line": baseline.replace(
                            diagnostic_lines[0] + "\n", "", 1
                        ),
                        "changed-diagnostic-line": baseline.replace(
                            "directive argument is null",
                            "directive argument changed",
                            1,
                        ),
                        "reordered-diagnostic-members": baseline.replace(
                            diagnostic_lines[0]
                            + "\n"
                            + diagnostic_lines[1],
                            diagnostic_lines[1]
                            + "\n"
                            + diagnostic_lines[0],
                            1,
                        ),
                        "diagnostics-after-link": baseline.replace(
                            diagnostic_block, "", 1
                        ).replace(
                            link_line + "\n",
                            link_line + "\n" + diagnostic_block,
                            1,
                        ),
                        **diagnostics_before_owner,
                    }
                )
                streams = list(
                    genesis_plus_gx_wide
                    .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS[
                        architecture
                    ]
                    .values()
                )
                interleaved = [
                    stream[index]
                    for index in range(max(map(len, streams)))
                    for stream in streams
                    if index < len(stream)
                ]
                valid_interleave = baseline.replace(
                    diagnostic_block,
                    "\n".join(interleaved) + "\n",
                    1,
                )
            else:
                valid_interleave = baseline

            with self.subTest(
                architecture=architecture,
                log="valid-interleave",
            ), patch_genesis_plus_gx_wide_contract(fixture):
                self.assertTrue(
                    genesis_plus_gx_wide
                    .genesis_plus_gx_wide_log_proves_contract(
                        valid_interleave,
                        genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                for label, changed_log in mutations.items():
                    with self.subTest(
                        architecture=architecture,
                        log=label,
                    ):
                        self.assertFalse(
                            genesis_plus_gx_wide
                            .genesis_plus_gx_wide_log_proves_contract(
                                changed_log,
                                (
                                    genesis_plus_gx_wide
                                    .GENESIS_PLUS_GX_WIDE_CORE_ID
                                ),
                                architecture,
                                spec["source"]["commit"],
                                spec["source"]["tree"],
                            )
                        )

    def test_tracked_historical_logs_prove_exact_contract(self) -> None:
        identity = (
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        logs: dict[str, str] = {}
        for label, path in ORACLE_LOGS.items():
            with self.subTest(log=label):
                expected_sha256, expected_size, expected_lines = (
                    ORACLE_LOG_IDENTITIES[label]
                )
                self.assertEqual(expected_sha256, sha256_file(path))
                self.assertEqual(expected_size, path.stat().st_size)
                log = path.read_text(encoding="utf-8")
                self.assertEqual(expected_lines, len(log.splitlines()))
                architecture = (
                    "arm64" if label.startswith("arm64") else "armhf"
                )
                logs[label] = log
                arguments = (
                    log,
                    genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                self.assertTrue(
                    genesis_plus_gx_wide
                    .genesis_plus_gx_wide_log_proves_contract(*arguments)
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )
                portable_arguments = (
                    log.replace("-j24", "-j4"),
                    *arguments[1:],
                )
                self.assertEqual(2, log.count("-j24"))
                self.assertTrue(
                    genesis_plus_gx_wide
                    .genesis_plus_gx_wide_log_proves_contract(
                        *portable_arguments
                    )
                )
        self.assertNotEqual(logs["arm64-final"], logs["arm64-repro"])
        self.assertEqual(
            Counter(logs["arm64-final"].splitlines()),
            Counter(logs["arm64-repro"].splitlines()),
        )

    def test_tracked_log_phase_reordering_fails_closed(self) -> None:
        log = ORACLE_LOGS["arm64-final"].read_text(encoding="utf-8")
        lines = log.splitlines()
        identity = (
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        copy_line = (
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER[0]
        )
        phase_lines = {
            "clone": next(line for line in lines if line.startswith("git clone ")),
            "cd": next(line for line in lines if line.startswith("cd \"")),
            "clean": next(
                line
                for line in lines
                if line.startswith("make -f ") and line.endswith(" clean")
            ),
            "build": next(
                line
                for line in lines
                if line.startswith("make -f ") and " CC=" in line
            ),
        }
        mutations = {}
        for name, line in phase_lines.items():
            without_line = log.replace(line + "\n", "", 1)
            mutations[f"{name}-after-link"] = without_line.replace(
                copy_line + "\n",
                line + "\n" + copy_line + "\n",
                1,
            )
        for name, stream in (
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS["arm64"]
            .items()
        ):
            stream_block = "\n".join(stream) + "\n"
            owner_source = (
                genesis_plus_gx_wide
                .GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE[
                    "arm64"
                ][name]
            )
            owner_compile = next(
                line for line in lines if f" -c {owner_source} " in line
            )
            without_stream = log.replace(stream_block, "", 1)
            mutations[f"{name}-diagnostics-before-owner"] = (
                without_stream.replace(
                    owner_compile + "\n",
                    stream_block + owner_compile + "\n",
                    1,
                )
            )
        for label, changed_log in mutations.items():
            with self.subTest(log=label):
                self.assertFalse(
                    genesis_plus_gx_wide
                    .genesis_plus_gx_wide_log_proves_contract(
                        changed_log,
                        genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                        "arm64",
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_tracked_wide_logs_do_not_prove_base_contract(self) -> None:
        identity = (
            genesis_plus_gx.GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        for label, path in ORACLE_LOGS.items():
            architecture = "arm64" if label.startswith("arm64") else "armhf"
            arguments = (
                path.read_text(encoding="utf-8"),
                genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                architecture,
                identity["source_commit"],
                identity["source_tree"],
            )
            with self.subTest(log=label):
                self.assertFalse(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        *arguments
                    )
                )
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

    def test_exact_wide_log_uses_the_individual_contract(self) -> None:
        fixture = build_genesis_plus_gx_wide_log_fixture("arm64")
        log = fixture["log"]
        spec = fixture["spec"]
        arguments = (
            log,
            genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
            "arm64",
            spec["source"]["commit"],
            spec["source"]["tree"],
        )
        with patch_genesis_plus_gx_wide_contract(fixture):
            self.assertTrue(
                genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                    *arguments
                )
            )
            self.assertFalse(
                genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                    log,
                    "genesis_plus_gx",
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            self.assertFalse(
                genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                    log + "fatal: synthetic failure\n", *arguments[1:]
                )
            )
            self.assertFalse(
                genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                    log,
                    genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    "0" * 40,
                )
            )
            with self.assertRaisesRegex(
                pipeline.PipelineError, "unknown architecture"
            ):
                genesis_plus_gx_wide.genesis_plus_gx_wide_log_proves_contract(
                    log,
                    genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                    "unknown",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )


if __name__ == "__main__":
    unittest.main()
