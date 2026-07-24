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
from core_pipeline_lib.contracts.command_line import (
    command_line_is_lexically_safe,
    ordered_command_argv_sha256,
)
from core_pipeline_lib.foundation import sha256_file


ROOT = Path(__file__).resolve().parents[1]
ORACLE_DIRECTORY = (
    ROOT
    / "tests"
    / "fixtures"
    / "per-core-oracles"
    / "genesis_plus_gx"
)
ORACLE_LOGS = {
    "arm64-final": (
        ORACLE_DIRECTORY / "arm64-final-build.txt"
    ),
    "arm64-repro": (
        ORACLE_DIRECTORY / "arm64-repro-build.txt"
    ),
    "armhf": ORACLE_DIRECTORY / "armhf-build.txt",
}
ORACLE_LOG_IDENTITIES = {
    "arm64-final": (
        "1b946fc9d4e4cb700c12aab1deaa8ccb03943405b401bf19ad47db1f1e0cc93c",
        110092,
        174,
    ),
    "arm64-repro": (
        "178dcdaa3cdca335d0c593ddb9183ad9ceb40b0f05b8473255eb53cce9634c22",
        110092,
        174,
    ),
    "armhf": (
        "fcac51db9ea06dee58581de12c2dd1b62674ebb7f74c2d1b173415ad91ca4140",
        109116,
        153,
    ),
}


def build_genesis_plus_gx_log_fixture(architecture: str) -> dict:
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
    core_id = genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID
    spec = catalog["cores"][core_id]
    compiler, cxx_compiler = compilers[architecture]
    contract = genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT
    count = contract.expected_compile_count
    version_value = spec["build"]["git_version"]["value"]
    version_token = '-DGIT_VERSION=\\""' + version_value + '"\\"'
    pairs = [
        (f"genplus/unit_{index:03d}.o", f"genplus/unit_{index:03d}.c")
        for index in range(count)
    ]
    pairs[-2:] = [
        (
            "libretro/libretro-common/cdrom/cdrom.o",
            "libretro/libretro-common/cdrom/cdrom.c",
        ),
        ("libretro/libretro.o", "libretro/libretro.c"),
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
            raise AssertionError("synthetic Genesis Plus GX fixture is invalid")
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
    diagnostic_lines = [
        line
        for stream in (
            genesis_plus_gx.GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS[
                architecture
            ].values()
        )
        for line in stream
    ]
    make_program = "make" if architecture == "arm64" else "gmake"
    phase_lines = {
        "clone": (
            'git clone "https://github.com/libretro/Genesis-Plus-GX.git" '
            '"/libretro-super/libretro-genesis_plus_gx"'
        ),
        "cd": 'cd "/libretro-super/libretro-genesis_plus_gx"',
        "clean": (
            f'{make_program} -f Makefile.libretro platform="unix" '
            "-j24  clean"
        ),
        "build": (
            f'{make_program} -f Makefile.libretro platform="unix" -j24 '
            f'CC="{compiler}" CXX="{cxx_compiler}" '
        ),
    }
    prelude_lines = [
        "PLATFORM: Linux",
        "ARCHITECTURE: x86_64",
        "TARGET: unix",
        "=== Genesis Plus GX",
        "Fetching genesis_plus_gx...",
        phase_lines["clone"],
        "Cloning into '/libretro-super/libretro-genesis_plus_gx'...",
        "1 core(s) successfully processed:",
        "\tgenesis_plus_gx",
        genesis_plus_gx.GENESIS_PLUS_GX_SOURCE_HEAD_MARKER,
        *pipeline.git_version_log_markers(spec),
        "PLATFORM: Linux",
        "ARCHITECTURE: x86_64",
        "TARGET: unix",
        f"CC = {compiler}",
        f"CXX = {cxx_compiler}",
        f"CXX11 = {cxx_compiler}",
        f"CXX17 = {cxx_compiler}",
        f"STRIP = {compiler.removesuffix('gcc')}strip",
        f'Compiler: CC="{compiler}" CXX="{cxx_compiler}"',
        "=== x86 CPU detected... ===",
        "=== x86_64 CPU detected... ===",
        "unix",
        "unix",
        "=== Genesis Plus GX",
        "Building genesis_plus_gx...",
        phase_lines["cd"],
        phase_lines["clean"],
        "rm -f ./synthetic-clean.o",
        "rm -f genesis_plus_gx_libretro.so",
        phase_lines["build"],
    ]
    lines = [
        *prelude_lines,
        *[compile_lines[index] for index in compile_order],
        *diagnostic_lines,
        link_line,
        *genesis_plus_gx.GENESIS_PLUS_GX_SUCCESS_TRAILER,
    ]
    canonicalized_lines = genesis_plus_gx._canonicalized_parallelism_lines(
        tuple(lines), architecture
    )
    canonicalized_lines = genesis_plus_gx._canonicalized_wildcard_object_lines(
        canonicalized_lines
    )
    if canonicalized_lines is None:
        raise AssertionError(
            "synthetic Genesis Plus GX scheduler fixture is invalid"
        )
    log = "\n".join(lines) + "\n"
    return {
        "architecture": architecture,
        "compiler": compiler,
        "compile_lines": compile_lines,
        "cxx_compiler": cxx_compiler,
        "diagnostic_lines": diagnostic_lines,
        "link_line": link_line,
        "log": log,
        "log_line_multiset_sha256": (
            genesis_plus_gx._multiset_lines_sha256(canonicalized_lines)
        ),
        "pairs": pairs,
        "phase_lines": phase_lines,
        "prelude_line_count": len(prelude_lines),
        "prelude_sha256": genesis_plus_gx._lines_sha256(
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


def patch_genesis_plus_gx_contract(fixture: dict):
    contract = replace(
        genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT,
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
        genesis_plus_gx,
        GENESIS_PLUS_GX_LOG_CONTRACT=contract,
        GENESIS_PLUS_GX_EXPECTED_LOG_LINE_MULTISET_SHA256={
            fixture["architecture"]: fixture["log_line_multiset_sha256"]
        },
        GENESIS_PLUS_GX_EXPECTED_PRELUDE_LINE_COUNT={
            fixture["architecture"]: fixture["prelude_line_count"]
        },
        GENESIS_PLUS_GX_EXPECTED_PRELUDE_SHA256={
            fixture["architecture"]: fixture["prelude_sha256"]
        },
    )


class GenesisPlusGxLogContractTests(unittest.TestCase):
    def test_individual_constants_bind_the_base_contract(self) -> None:
        core_id = genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID
        self.assertEqual("genesis_plus_gx", core_id)
        self.assertEqual(
            genesis_plus_gx.GENESIS_PLUS_GX_C_COMPILE_COUNT,
            genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT.expected_compile_count,
        )
        self.assertEqual(
            genesis_plus_gx.GENESIS_PLUS_GX_COMPILE_PAIR_SHA256,
            genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT.expected_compile_pair_sha256,
        )
        self.assertEqual(
            genesis_plus_gx.GENESIS_PLUS_GX_COMPILE_INVOCATION_SHA256,
            (
                genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT
                .expected_compile_invocation_sha256
            ),
        )
        self.assertEqual(
            genesis_plus_gx.GENESIS_PLUS_GX_LINK_OBJECT_SHA256,
            genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT.expected_link_object_sha256,
        )
        self.assertEqual(
            genesis_plus_gx.GENESIS_PLUS_GX_RAW_LINK_OBJECT_SHA256,
            (
                genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT
                .expected_raw_link_object_sha256
            ),
        )
        # No link-invocation pin: filesystem-ordered object list, tolerated
        # by design; the object multisets stay pinned.
        self.assertIsNone(
            genesis_plus_gx.GENESIS_PLUS_GX_LOG_CONTRACT
            .expected_link_invocation_sha256
        )
        self.assertEqual(
            "c67efaa2ee59bcc7843af62f3988b0d21aa4efc33b76c123b4456159b8dba226",
            genesis_plus_gx.GENESIS_PLUS_GX_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "3c5230277f45f7229e68eaa84a9789a40518b53bce0e3e7005ccb96658ca117d"
                ),
                "armhf": (
                    "492b944204da4419de18a186ba4ea4303d6b63dfa722a808f8daf203aa7167a2"
                ),
            },
            genesis_plus_gx.GENESIS_PLUS_GX_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            "fb819ef64ee50aff786ce185fcb8205e7345ceada1d3f41b7ae596e9992a1bdf",
            genesis_plus_gx.GENESIS_PLUS_GX_RAW_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "f05411146d5dbf14a57c8a25543d8abb116880d56f14424302848059ff32ebd9"
                ),
                "armhf": (
                    "e80466c1a92b0c83086211dccde87453ea69a49625ba780ac09f7cd2c54219eb"
                ),
            },
            genesis_plus_gx.GENESIS_PLUS_GX_EXPECTED_LOG_LINE_MULTISET_SHA256,
        )
        self.assertEqual(
            {"arm64": 32, "armhf": 32},
            genesis_plus_gx.GENESIS_PLUS_GX_EXPECTED_PRELUDE_LINE_COUNT,
        )
        self.assertEqual(
            {
                "arm64": (
                    "0e6b7febe535330adb4938533d9739169fd7e9da058f82086038b0c3f83c70ea"
                ),
                "armhf": (
                    "8f2a700d59e88f699381819f46fa63c5835ca636ebb7db78397539b01ada2217"
                ),
            },
            genesis_plus_gx.GENESIS_PLUS_GX_EXPECTED_PRELUDE_SHA256,
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
            genesis_plus_gx.GENESIS_PLUS_GX_PARALLEL_COMMAND,
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
                genesis_plus_gx
                .GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE
            ),
        )
        stream_lengths = {
            name: len(lines)
            for name, lines in (
                genesis_plus_gx
                .GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS["arm64"]
                .items()
            )
        }
        self.assertEqual({"cdrom": 8, "libretro": 13}, stream_lengths)
        for name, lines in (
            genesis_plus_gx
            .GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS["arm64"]
            .items()
        ):
            with self.subTest(diagnostic_stream=name):
                self.assertEqual(
                    (
                        genesis_plus_gx
                        .GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAM_SHA256[name]
                    ),
                    genesis_plus_gx._lines_sha256(lines),
                )

    def test_catalog_and_command_scope_use_base_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        core_id = genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID
        spec = catalog["cores"][core_id]
        identity = (
            genesis_plus_gx.GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertIs(identity, pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[core_id])
        self.assertEqual(
            {
                "url": "https://github.com/libretro/Genesis-Plus-GX.git",
                "requested_ref": "refs/heads/master",
                "commit": "fa4dca561e08d5be9077419f7b255e1da213ed21",
                "tree": "7f4b0916e938e15e046e1c35acd0173aab1aaac3",
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
                "value": " fa4dca5",
                "compiler_scope": "c",
            },
            pipeline.validated_git_version(spec),
        )
        self.assertEqual(
            '" fa4dca5"', pipeline.command_scoped_native_git_version(spec)
        )
        markers = pipeline.git_version_log_markers(spec)
        self.assertEqual(
            [
                (
                    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                    '" fa4dca5"|command-scoped-environment'
                ),
                'CORE_PIPELINE_NATIVE_GIT_VERSION|" fa4dca5"|environment',
            ],
            markers,
        )
        origin_shell = pipeline.git_version_shell(spec)
        build_shell = pipeline.libretro_build_shell(spec, core_id)
        assignment = "GIT_VERSION='\" fa4dca5\"'"
        self.assertIn(markers[0], origin_shell)
        self.assertIn("core_pipeline_native_git_version_origin", origin_shell)
        self.assertIn(assignment + " make --no-print-directory", origin_shell)
        self.assertEqual(
            assignment + " ./libretro-build.sh genesis_plus_gx",
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

    def test_exact_log_accepts_parallel_compile_order_with_exact_link(
        self,
    ) -> None:
        core_id = genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID
        for architecture in ("arm64", "armhf"):
            fixture = build_genesis_plus_gx_log_fixture(architecture)
            spec = fixture["spec"]
            with self.subTest(
                architecture=architecture
            ), patch_genesis_plus_gx_contract(fixture):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        fixture["log"],
                        spec["build"]["git_version"],
                        spec["source"]["commit"],
                        architecture,
                    )
                )
                self.assertTrue(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        fixture["log"],
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
                    "-o genesis_plus_gx_libretro.so",
                    "-ogenesis_plus_gx_libretro.so",
                    1,
                )
                self.assertFalse(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        split_compile_output,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                self.assertNotEqual(fixture["log"], reordered_compile_lines)
                self.assertTrue(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        reordered_compile_lines,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                self.assertFalse(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        attached_link_output,
                        core_id,
                        architecture,
                        spec["source"]["commit"],
                        spec["source"]["tree"],
                    )
                )
                self.assertIn("-o" + first_output, first_compile)

    def test_parallelism_canonicalization_is_tightly_scoped(self) -> None:
        core_id = genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID
        for architecture in ("arm64", "armhf"):
            fixture = build_genesis_plus_gx_log_fixture(architecture)
            baseline = fixture["log"]
            spec = fixture["spec"]
            clean_line = fixture["phase_lines"]["clean"]
            build_line = fixture["phase_lines"]["build"]

            def replace_both(token: str) -> str:
                return baseline.replace(
                    clean_line,
                    clean_line.replace("-j24", token, 1),
                    1,
                ).replace(
                    build_line,
                    build_line.replace("-j24", token, 1),
                    1,
                )

            both_j4 = replace_both("-j4")
            mutations = {
                "only-clean-changed": baseline.replace(
                    clean_line,
                    clean_line.replace("-j24", "-j4", 1),
                    1,
                ),
                "only-build-changed": baseline.replace(
                    build_line,
                    build_line.replace("-j24", "-j4", 1),
                    1,
                ),
                "zero-jobs": replace_both("-j0"),
                "leading-zero-jobs": replace_both("-j04"),
                "long-jobs-option": replace_both("--jobs=4"),
                "changed-clean-surroundings": baseline.replace(
                    clean_line,
                    clean_line.replace(
                        'platform="unix"', "platform=unix", 1
                    ),
                    1,
                ),
            }
            arguments = (
                core_id,
                architecture,
                spec["source"]["commit"],
                spec["source"]["tree"],
            )
            with self.subTest(
                architecture=architecture,
                scheduler="same-positive-canonical-decimal",
            ), patch_genesis_plus_gx_contract(fixture):
                self.assertTrue(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        both_j4, *arguments
                    )
                )
                canonicalized = (
                    genesis_plus_gx._canonicalized_parallelism_lines(
                        tuple(both_j4.splitlines()), architecture
                    )
                )
                self.assertIsNotNone(canonicalized)
                self.assertEqual(
                    2,
                    sum(
                        "-j<JOBS>" in line
                        for line in canonicalized or ()
                    ),
                )
                for label, changed_log in mutations.items():
                    with self.subTest(
                        architecture=architecture,
                        scheduler=label,
                    ):
                        self.assertFalse(
                            genesis_plus_gx
                            .genesis_plus_gx_log_proves_contract(
                                changed_log, *arguments
                            )
                        )

    def test_compile_and_link_parser_fails_closed(self) -> None:
        fixture = build_genesis_plus_gx_log_fixture("arm64")
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
            "duplicate-attached-output": baseline.replace(
                "-o" + first_output,
                "-o" + first_output + " -ogenplus/rogue.o",
                1,
            ),
            "mixed-output": baseline.replace(
                "-o" + first_output,
                "-o" + first_output + " -o genplus/rogue.o",
                1,
            ),
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
            "forwarded-response-file": baseline.replace(
                first_compile,
                first_compile.replace(
                    " -O2 ", " -Wp,@compiler.rsp -O2 ", 1
                ),
                1,
            ),
            "explicit-language": baseline.replace(
                first_compile,
                first_compile.replace(" -O2 ", " -x c -O2 ", 1),
                1,
            ),
            "end-options": baseline.replace(
                first_compile,
                first_compile.replace(" -O2 ", " -- -O2 ", 1),
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
                "-o genesis_plus_gx_libretro.so",
                "-ogenesis_plus_gx_libretro.so",
                1,
            ),
            "missing-link-output": baseline.replace(
                "-o genesis_plus_gx_libretro.so ", "", 1
            ),
            "wrong-link-output": baseline.replace(
                "genesis_plus_gx_libretro.so", "rogue_libretro.so", 1
            ),
            "mixed-link-output": baseline.replace(
                "-o genesis_plus_gx_libretro.so",
                "-o genesis_plus_gx_libretro.so -orogue_libretro.so",
                1,
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
            "link-source-input": baseline.replace(
                link_line,
                link_line.replace(" -shared ", " rogue.c -shared ", 1),
                1,
            ),
            "unexpected-link-option": baseline.replace(
                link_line,
                link_line.replace(" -shared ", " -pthread -shared ", 1),
                1,
            ),
            "forwarded-link-object": baseline.replace(
                link_line,
                link_line.replace(
                    " -shared ", " -Wl,genplus/rogue.o -shared ", 1
                ),
                1,
            ),
            "xlinker-object": baseline.replace(
                link_line,
                link_line.replace(
                    " -shared ", " -Xlinker genplus/rogue.o -shared ", 1
                ),
                1,
            ),
            "link-response-file": baseline.replace(
                link_line,
                link_line.replace(" -shared ", " @link.rsp -shared ", 1),
                1,
            ),
            "malformed-command": baseline + compiler + " 'unterminated -c\n",
        }
        with patch_genesis_plus_gx_contract(fixture):
            self.assertTrue(
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                    baseline,
                    genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            for label, changed_log in mutations.items():
                with self.subTest(log=label):
                    self.assertFalse(
                        genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                            changed_log,
                            genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
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
                        genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                            baseline,
                            genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                            "arm64",
                            commit,
                            tree,
                        )
                    )

    def test_markers_diagnostics_and_success_envelope_fail_closed(self) -> None:
        for architecture in ("arm64", "armhf"):
            fixture = build_genesis_plus_gx_log_fixture(architecture)
            baseline = fixture["log"]
            spec = fixture["spec"]
            source_marker = genesis_plus_gx.GENESIS_PLUS_GX_SOURCE_HEAD_MARKER
            build_arg_marker = (
                genesis_plus_gx
                .GENESIS_PLUS_GX_NATIVE_GIT_VERSION_BUILD_ARG_MARKER
            )
            native_marker = (
                genesis_plus_gx.GENESIS_PLUS_GX_NATIVE_GIT_VERSION_MARKER
            )
            first_compile = fixture["compile_lines"][0]
            link_line = fixture["link_line"]

            def insert_before_link(line: str) -> str:
                return baseline.replace(
                    link_line + "\n", line + "\n" + link_line + "\n", 1
                )

            def move_phase_line_after_first_compile(line: str) -> str:
                moved = baseline.replace(line + "\n", "", 1)
                return moved.replace(
                    first_compile + "\n",
                    first_compile + "\n" + line + "\n",
                    1,
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
                    + "\nCORE_PIPELINE_GIT_VERSION|fa4dca5|legacy\n",
                    1,
                ),
                "compile-before-markers": moved_compile,
                "link-before-compile": moved_link,
                "injected-warning": baseline.replace(
                    link_line + "\n",
                    "synthetic.c:1: warning: injected diagnostic\n"
                    + link_line
                    + "\n",
                    1,
                ),
                "injected-note": baseline.replace(
                    link_line + "\n",
                    "synthetic.c:1: note: injected diagnostic\n"
                    + link_line
                    + "\n",
                    1,
                ),
                "compiler-error": baseline.replace(
                    link_line + "\n",
                    "cc1: error: synthetic failure\n" + link_line + "\n",
                    1,
                ),
                "make-failure": baseline.replace(
                    link_line + "\n",
                    "make[1]: *** [Makefile:1: all] Error 2\n"
                    + link_line
                    + "\n",
                    1,
                ),
                "undefined-reference": baseline.replace(
                    link_line + "\n",
                    "ld: undefined reference to synthetic_symbol\n"
                    + link_line
                    + "\n",
                    1,
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
                    genesis_plus_gx.GENESIS_PLUS_GX_SUCCESS_TRAILER[0]
                    + "\n",
                    "",
                    1,
                ),
                "missing-success": baseline.replace(
                    "1 core(s) successfully processed:\n"
                    "\tgenesis_plus_gx\n",
                    "",
                    1,
                ),
                "duplicate-success-trailer": baseline
                + "".join(
                    line + "\n"
                    for line in (
                        genesis_plus_gx.GENESIS_PLUS_GX_SUCCESS_TRAILER
                    )
                ),
                "duplicate-success-summary": baseline.replace(
                    genesis_plus_gx.GENESIS_PLUS_GX_SUCCESS_TRAILER[0]
                    + "\n",
                    "1 core(s) successfully processed:\n"
                    "\tgenesis_plus_gx\n"
                    + genesis_plus_gx.GENESIS_PLUS_GX_SUCCESS_TRAILER[0]
                    + "\n",
                    1,
                ),
                "nonterminal-success": baseline + "post-success noise\n",
            }
            mutations.update(
                {
                    f"{phase}-after-first-compile": (
                        move_phase_line_after_first_compile(line)
                    )
                    for phase, line in fixture["phase_lines"].items()
                }
            )
            diagnostic_lines = fixture["diagnostic_lines"]
            if diagnostic_lines:
                diagnostic_block = "\n".join(diagnostic_lines) + "\n"
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
                    }
                )
                stream_map = (
                    genesis_plus_gx
                    .GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS[
                        architecture
                    ]
                )
                compile_source_map = (
                    genesis_plus_gx
                    .GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE[
                        architecture
                    ]
                )
                for name, stream in stream_map.items():
                    stream_block = "\n".join(stream) + "\n"
                    owner_source = compile_source_map[name]
                    owner_compile = next(
                        line
                        for line in fixture["compile_lines"]
                        if f" -c {owner_source} " in line
                    )
                    moved_before_owner = baseline.replace(
                        stream_block, "", 1
                    ).replace(
                        owner_compile + "\n",
                        stream_block + owner_compile + "\n",
                        1,
                    )
                    mutations[
                        f"{name}-diagnostics-before-owner"
                    ] = moved_before_owner
                streams = list(
                    stream_map.values()
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
            ), patch_genesis_plus_gx_contract(fixture):
                self.assertTrue(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        valid_interleave,
                        genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
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
                            genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                                changed_log,
                                genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                                architecture,
                                spec["source"]["commit"],
                                spec["source"]["tree"],
                            )
                        )

    def test_tracked_historical_logs_prove_exact_contract(self) -> None:
        identity = (
            genesis_plus_gx.GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                self.assertTrue(
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        *arguments
                    )
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
                    genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                        *portable_arguments
                    )
                )
        self.assertNotEqual(logs["arm64-final"], logs["arm64-repro"])
        self.assertEqual(
            Counter(logs["arm64-final"].splitlines()),
            Counter(logs["arm64-repro"].splitlines()),
        )

    def test_tracked_base_logs_do_not_prove_wide_contract(self) -> None:
        identity = (
            genesis_plus_gx_wide
            .GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        for label, path in ORACLE_LOGS.items():
            architecture = "arm64" if label.startswith("arm64") else "armhf"
            arguments = (
                path.read_text(encoding="utf-8"),
                genesis_plus_gx_wide.GENESIS_PLUS_GX_WIDE_CORE_ID,
                architecture,
                identity["source_commit"],
                identity["source_tree"],
            )
            with self.subTest(log=label):
                self.assertFalse(
                    genesis_plus_gx_wide
                    .genesis_plus_gx_wide_log_proves_contract(*arguments)
                )
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

    def test_active_shell_syntax_fails_closed(self) -> None:
        fixture = build_genesis_plus_gx_log_fixture("arm64")
        baseline = fixture["log"]
        compile_line = fixture["compile_lines"][0]
        spec = fixture["spec"]
        output, _source = fixture["pairs"][0]
        suffixes = {
            "semicolon-redirection": f";cat</tmp/rogue.o>{output}",
            "and-list": " && cat /tmp/rogue.o",
            "or-list": " || true",
            "pipe": " | cat",
            "input-redirection": " < /tmp/rogue.o",
            "output-redirection": " > /tmp/rogue.o",
            "dollar-command-substitution": " $(cat /tmp/rogue.o)",
            "parameter-expansion": " ${ROGUE_OBJECT}",
            "backtick-substitution": " `cat /tmp/rogue.o`",
            "comment": " # ignored proof suffix",
            "asterisk-glob": " *",
            "question-glob": " ?",
            "bracket-glob": " [ab]",
            "brace-expansion": " {one,two}",
            "tilde-expansion": " ~/rogue.o",
            "subshell": " (cat /tmp/rogue.o)",
            "history-operator": " ! true",
            "tab-control": "\t-DROGUE=1",
            "non-ascii": " é",
            "line-continuation": " " + "\\",
        }
        self.assertTrue(command_line_is_lexically_safe(compile_line))
        with patch_genesis_plus_gx_contract(fixture):
            for label, suffix in suffixes.items():
                injected_line = compile_line + suffix
                changed_log = baseline.replace(compile_line, injected_line, 1)
                with self.subTest(syntax=label):
                    self.assertFalse(
                        command_line_is_lexically_safe(injected_line)
                    )
                    self.assertFalse(
                        pipeline.git_version_log_proves_contract(
                            changed_log,
                            spec["build"]["git_version"],
                            spec["source"]["commit"],
                            "arm64",
                        )
                    )
                    self.assertFalse(
                        genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                            changed_log,
                            genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                            "arm64",
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )

    def test_full_compile_argv_digest_rejects_external_inputs(self) -> None:
        fixture = build_genesis_plus_gx_log_fixture("arm64")
        baseline = fixture["log"]
        compile_line = fixture["compile_lines"][0]
        spec = fixture["spec"]
        external_options = {
            "compiler-plugin": "-fplugin=/tmp/rogue.so",
            "compiler-specs": "-specs=/tmp/rogue.specs",
            "forced-include": "-include/tmp/rogue.h",
            "forced-macros": "-imacros/tmp/rogue.h",
            "subtool-prefix": "-B/tmp/rogue-bin",
        }
        with patch_genesis_plus_gx_contract(fixture):
            self.assertTrue(
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                    baseline,
                    genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            for label, option in external_options.items():
                injected_line = compile_line + " " + option
                changed_log = baseline.replace(compile_line, injected_line, 1)
                with self.subTest(option=label):
                    self.assertTrue(
                        command_line_is_lexically_safe(injected_line)
                    )
                    self.assertTrue(
                        pipeline.git_version_log_proves_contract(
                            changed_log,
                            spec["build"]["git_version"],
                            spec["source"]["commit"],
                            "arm64",
                        )
                    )
                    self.assertFalse(
                        genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                            changed_log,
                            genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                            "arm64",
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )

    def test_exact_base_log_uses_the_individual_contract(self) -> None:
        fixture = build_genesis_plus_gx_log_fixture("arm64")
        log = fixture["log"]
        identity = (
            genesis_plus_gx.GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        arguments = (
            log,
            genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
            "arm64",
            identity["source_commit"],
            identity["source_tree"],
        )
        with patch_genesis_plus_gx_contract(fixture):
            self.assertTrue(
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(*arguments)
            )
            self.assertFalse(
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                    log,
                    "genesis_plus_gx_wide",
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                )
            )
            self.assertFalse(
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                    log + "fatal: synthetic failure\n", *arguments[1:]
                )
            )
            self.assertFalse(
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                    log,
                    genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                    "arm64",
                    "0" * 40,
                    identity["source_tree"],
                )
            )
            with self.assertRaisesRegex(
                pipeline.PipelineError, "unknown architecture"
            ):
                genesis_plus_gx.genesis_plus_gx_log_proves_contract(
                    log,
                    genesis_plus_gx.GENESIS_PLUS_GX_CORE_ID,
                    "unknown",
                    identity["source_commit"],
                    identity["source_tree"],
                )


if __name__ == "__main__":
    unittest.main()
