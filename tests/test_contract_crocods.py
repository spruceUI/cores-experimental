from __future__ import annotations

from collections import Counter
from pathlib import Path
import shlex
import unittest

from .core_contract_helpers import pipeline
from scripts.core_pipeline_lib.contracts import crocods
from scripts.core_pipeline_lib.contracts.cpc_common import (
    cpc_compile_command_pair,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_file


ROOT = Path(__file__).resolve().parents[1]
COMPILERS = {
    "arm64": "aarch64-linux-gnu-gcc",
    "armhf": "arm-a30-linux-gnueabihf-gcc",
}
CXX_COMPILERS = {
    "arm64": "aarch64-linux-gnu-g++",
    "armhf": "arm-a30-linux-gnueabihf-g++",
}
ORACLE_DIRECTORY = (
    ROOT
    / "tests"
    / "fixtures"
    / "per-core-oracles"
    / "crocods"
)
ORACLE_LOGS = {
    "arm64-final": ORACLE_DIRECTORY / "arm64-final-build.txt",
    "arm64-repro": ORACLE_DIRECTORY / "arm64-repro-build.txt",
    "armhf": ORACLE_DIRECTORY / "armhf-build.txt",
}
ORACLE_LOG_IDENTITIES = {
    "arm64-final": (
        "df936492192a8393f9c6e701fe55685a7aa48b05a2f05a580c6c87f87db03b03",
        16595,
    ),
    "arm64-repro": (
        "1299926e041ead6934ab42101573072093e2c49c9045b4c1a626e8f590fb0d60",
        16595,
    ),
    "armhf": (
        "05c5c87eedb63795e408c68da023507c71edf1d94811643bcac33133272708d3",
        9900,
    ),
}
CURRENT_REAL_LOG_RUNS = (
    "actions-sim-build-core-crocods-w3",
    "build-core-crocods-local-w3",
)


def build_crocods_fixture(arch: str) -> dict:
    compiler = COMPILERS[arch]
    cxx_compiler = CXX_COMPILERS[arch]
    oracle_key = "arm64-final" if arch == "arm64" else "armhf"
    log = ORACLE_LOGS[oracle_key].read_text(encoding="utf-8")
    compile_lines: list[str] = []
    pairs: list[tuple[str, str]] = []
    link_lines: list[str] = []
    for line in log.splitlines():
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens or tokens[0] != compiler:
            continue
        if "-c" in tokens:
            pair = cpc_compile_command_pair(tokens, {compiler})
            if pair is None:
                raise AssertionError(f"invalid tracked compile oracle: {line}")
            compile_lines.append(line)
            pairs.append(pair)
        elif "-o" in tokens:
            link_lines.append(line)
    if len(link_lines) != 1:
        raise AssertionError("tracked CrocoDS oracle must have one link")
    trace_lines = [
        f"Makefile:485: update target '{pairs[0][0]}' due to: {pairs[0][1]}"
    ]
    return {
        "compile_lines": compile_lines,
        "compiler": compiler,
        "cxx_compiler": cxx_compiler,
        "link_line": link_lines[0],
        "log": log,
        "pairs": pairs,
        "trace_lines": trace_lines,
    }


def build_crocods_log(arch: str) -> str:
    return build_crocods_fixture(arch)["log"]


class CrocodsLogContractTests(unittest.TestCase):
    def test_identity_and_contract_are_owned_by_crocods(self) -> None:
        identity = crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        contract = crocods.CROCODS_LOG_CONTRACT
        self.assertEqual("crocods", crocods.CROCODS_CORE_ID)
        self.assertEqual(crocods.CROCODS_CORE_ID, identity["source_key"])
        self.assertEqual(50, contract.expected_c_compile_count)
        self.assertEqual(identity["source_commit"], contract.source_commit)
        self.assertEqual(identity["source_tree"], contract.source_tree)
        self.assertIsNone(contract.make_trace)
        exact = crocods.CROCODS_EXACT_LOG_CONTRACT
        self.assertEqual(
            crocods.CROCODS_EXPECTED_COMPILE_PAIR_SHA256,
            exact.expected_compile_pair_sha256,
        )
        self.assertEqual(
            crocods.CROCODS_EXPECTED_COMPILE_INVOCATION_SHA256,
            exact.expected_compile_invocation_sha256,
        )
        self.assertEqual(
            crocods.CROCODS_EXPECTED_LINK_OBJECT_SHA256,
            exact.expected_link_object_sha256,
        )
        self.assertEqual(
            crocods.CROCODS_EXPECTED_RAW_LINK_OBJECT_SHA256,
            exact.expected_raw_link_object_sha256,
        )
        # No link-invocation pin: the Makefile's object order is filesystem
        # enumeration, tolerated by design (the object multisets stay pinned).
        self.assertIsNone(exact.expected_link_invocation_sha256)
        stream_lengths = {
            name: len(lines)
            for name, lines in (
                crocods.CROCODS_EXPECTED_DIAGNOSTIC_STREAMS["arm64"].items()
            )
        }
        self.assertEqual(
            {
                "apps_autorun": 29,
                "platform": 38,
                "apps_disk": 13,
                "gif": 4,
                "iniparser": 12,
            },
            stream_lengths,
        )
        for name, lines in (
            crocods.CROCODS_EXPECTED_DIAGNOSTIC_STREAMS["arm64"].items()
        ):
            with self.subTest(diagnostic_stream=name):
                self.assertEqual(
                    crocods.CROCODS_EXPECTED_DIAGNOSTIC_STREAM_SHA256[name],
                    crocods._lines_sha256(lines),
                )

    def test_exact_log_is_accepted_for_each_architecture(self) -> None:
        identity = crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        for arch in COMPILERS:
            with self.subTest(arch=arch):
                log = build_crocods_log(arch)
                self.assertTrue(
                    crocods.crocods_log_proves_contract(
                        log,
                        crocods.CROCODS_CORE_ID,
                        arch,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(
                        log,
                        crocods.CROCODS_CORE_ID,
                        arch,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_tracked_oracles_bind_two_parallel_orders_and_exact_bytes(
        self,
    ) -> None:
        identity = crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        logs: dict[str, str] = {}
        for label, path in ORACLE_LOGS.items():
            with self.subTest(oracle=label):
                expected_sha256, expected_size = ORACLE_LOG_IDENTITIES[label]
                self.assertEqual(expected_sha256, sha256_file(path))
                self.assertEqual(expected_size, path.stat().st_size)
                architecture = "arm64" if label.startswith("arm64") else "armhf"
                log = path.read_text(encoding="utf-8")
                logs[label] = log
                self.assertTrue(
                    crocods.crocods_log_proves_contract(
                        log,
                        crocods.CROCODS_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
        self.assertNotEqual(logs["arm64-final"], logs["arm64-repro"])
        self.assertEqual(
            Counter(logs["arm64-final"].splitlines()),
            Counter(logs["arm64-repro"].splitlines()),
        )

    def test_workspace_current_logs_still_prove_when_available(self) -> None:
        identity = crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        paths = {
            (run_id, architecture): (
                ROOT
                / ".local-e2e"
                / "runs"
                / run_id
                / crocods.CROCODS_CORE_ID
                / architecture
                / "build.log"
            )
            for run_id in CURRENT_REAL_LOG_RUNS
            for architecture in COMPILERS
        }
        if any(not path.is_file() for path in paths.values()):
            self.skipTest("workspace-local CrocoDS logs are unavailable")
        for (run_id, architecture), path in paths.items():
            with self.subTest(run_id=run_id, architecture=architecture):
                self.assertTrue(
                    crocods.crocods_log_proves_contract(
                        path.read_text(encoding="utf-8"),
                        crocods.CROCODS_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_build_shell_does_not_enable_cap32_make_trace(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][crocods.CROCODS_CORE_ID]
        self.assertEqual(
            "./libretro-build.sh crocods",
            pipeline.libretro_build_shell(spec, crocods.CROCODS_CORE_ID),
        )

    def test_compile_link_trace_and_identity_contract_fail_closed(self) -> None:
        identity = crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        fixture = build_crocods_fixture("armhf")
        baseline = fixture["log"]
        arguments = (
            crocods.CROCODS_CORE_ID,
            "armhf",
            identity["source_commit"],
            identity["source_tree"],
        )
        first_compile = fixture["compile_lines"][0]
        second_compile = fixture["compile_lines"][1]
        first_output, first_source = fixture["pairs"][0]
        second_output, _second_source = fixture["pairs"][1]
        first_compile_tokens = shlex.split(first_compile)
        version_option = (
            f'-DGIT_VERSION="{crocods.CROCODS_NATIVE_GIT_VERSION}"'
        )
        version_index = first_compile_tokens.index(version_option)
        missing_version_tokens = (
            first_compile_tokens[:version_index]
            + first_compile_tokens[version_index + 1 :]
        )
        wrong_version_tokens = list(first_compile_tokens)
        wrong_version_tokens[version_index] = '-DGIT_VERSION=" rogue"'
        duplicate_version_tokens = list(first_compile_tokens)
        duplicate_version_tokens.insert(version_index, version_option)
        injected_macro_tokens = list(first_compile_tokens)
        injected_macro_tokens.insert(version_index + 1, "-DROGUE=1")
        source_index = first_compile_tokens.index(first_source)
        extra_source_tokens = list(first_compile_tokens)
        extra_source_tokens.insert(source_index, "crocods-core/rogue.c")
        response_tokens = list(first_compile_tokens)
        response_tokens.insert(version_index + 1, "@compiler.rsp")
        preprocessor_response_tokens = list(first_compile_tokens)
        preprocessor_response_tokens.insert(
            version_index + 1, "-Wp,@compiler.rsp"
        )
        explicit_language_tokens = list(first_compile_tokens)
        explicit_language_tokens[version_index + 1 : version_index + 1] = [
            "-x",
            "c",
        ]
        link_tokens = shlex.split(fixture["link_line"])
        first_link_object = link_tokens.index(f"./{first_output}")
        second_link_object = link_tokens.index(f"./{second_output}")
        mismatched_link_tokens = list(link_tokens)
        mismatched_link_tokens[first_link_object] = f"./{second_output}"
        reordered_link_tokens = list(link_tokens)
        reordered_link_tokens[first_link_object], reordered_link_tokens[
            second_link_object
        ] = (
            reordered_link_tokens[second_link_object],
            reordered_link_tokens[first_link_object],
        )
        normalized_raw_link_tokens = list(link_tokens)
        normalized_raw_link_tokens[first_link_object] = first_output
        success_trailer = "\n".join(crocods.CROCODS_SUCCESS_TRAILER) + "\n"
        mutations = {
            "unexpected-marker": (
                "CORE_PIPELINE_MAKE_TRACE|MAKEFLAGS=--trace|scoped\n"
                + baseline
            ),
            "unexpected-trace": (
                fixture["trace_lines"][0] + "\n" + baseline
            ),
            "compile-count-mismatch": baseline.replace(
                first_compile + "\n", "", 1
            ),
            "duplicate-compile-pair": baseline.replace(
                second_compile, first_compile, 1
            ),
            "missing-native-version-compile": baseline.replace(
                first_compile, shlex.join(missing_version_tokens), 1
            ),
            "wrong-native-version-compile": baseline.replace(
                first_compile, shlex.join(wrong_version_tokens), 1
            ),
            "duplicate-native-version-compile": baseline.replace(
                first_compile, shlex.join(duplicate_version_tokens), 1
            ),
            "injected-compile-definition": baseline.replace(
                first_compile, shlex.join(injected_macro_tokens), 1
            ),
            "extra-source-operand": baseline.replace(
                first_compile, shlex.join(extra_source_tokens), 1
            ),
            "compiler-wrapper": baseline.replace(
                first_compile, "ccache " + first_compile, 1
            ),
            "compiler-path-wrapper": baseline.replace(
                first_compile,
                first_compile.replace(
                    fixture["compiler"], f"/tmp/{fixture['compiler']}", 1
                ),
                1,
            ),
            "target-cxx": baseline.replace(
                first_compile,
                first_compile.replace(
                    fixture["compiler"], fixture["cxx_compiler"], 1
                ),
                1,
            ),
            "response-file": baseline.replace(
                first_compile, shlex.join(response_tokens), 1
            ),
            "forwarded-preprocessor-response": baseline.replace(
                first_compile, shlex.join(preprocessor_response_tokens), 1
            ),
            "explicit-language": baseline.replace(
                first_compile, shlex.join(explicit_language_tokens), 1
            ),
            "link-object-mismatch": baseline.replace(
                fixture["link_line"], shlex.join(mismatched_link_tokens), 1
            ),
            "normalized-raw-link-path": baseline.replace(
                fixture["link_line"],
                shlex.join(normalized_raw_link_tokens),
                1,
            ),
            "forwarded-linker-response": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,@link.rsp -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "forwarded-link-archive": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,cpc/rogue.a -shared ", 1
                ),
                1,
            ),
            "forwarded-link-arbitrary-input": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,cpc/rogue.data -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object-wl-equals": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl=cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object-xlinker-equals": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Xlinker=cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object-xlinker-split": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Xlinker cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "unexpected-link-library": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -lm", " -l:rogue.a -L/tmp -lm", 1
                ),
                1,
            ),
            "unexpected-link-script": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(" -lm", " -Trogue.ld -lm", 1),
                1,
            ),
            "missing-native-version-marker": baseline.replace(
                crocods.CROCODS_NATIVE_GIT_VERSION_MARKER + "\n", "", 1
            ),
            "wrong-native-version-marker": baseline.replace(
                crocods.CROCODS_NATIVE_GIT_VERSION_MARKER,
                'CORE_PIPELINE_NATIVE_GIT_VERSION|" rogue"|file',
                1,
            ),
            "duplicate-native-version-marker": baseline.replace(
                crocods.CROCODS_NATIVE_GIT_VERSION_MARKER,
                crocods.CROCODS_NATIVE_GIT_VERSION_MARKER
                + "\n"
                + crocods.CROCODS_NATIVE_GIT_VERSION_MARKER,
                1,
            ),
            "wrong-source-head-marker": baseline.replace(
                crocods.CROCODS_SOURCE_HEAD_MARKER,
                "HEAD is now at 0000000 rogue",
                1,
            ),
            "extra-warning": baseline.replace(
                success_trailer,
                "rogue.c:1:1: warning: injected warning\n" + success_trailer,
                1,
            ),
            "make-failure": baseline.replace(
                success_trailer,
                "make: *** [Makefile:1: rogue] Error 2\n" + success_trailer,
                1,
            ),
            "linker-failure": baseline.replace(
                success_trailer,
                "collect2: error: ld returned 1 exit status\n"
                + success_trailer,
                1,
            ),
            "fatal-failure": baseline.replace(
                success_trailer,
                "fatal: injected failure\n" + success_trailer,
                1,
            ),
            "missing-success-trailer": baseline.removesuffix(success_trailer),
        }
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    crocods.crocods_log_proves_contract(changed, *arguments)
                )
        self.assertFalse(
            crocods.crocods_log_proves_contract(
                baseline,
                "cap32",
                "armhf",
                identity["source_commit"],
                identity["source_tree"],
            )
        )
        for label, commit, tree in (
            ("wrong-commit", "0" * 40, identity["source_tree"]),
            ("wrong-tree", identity["source_commit"], "0" * 40),
        ):
            with self.subTest(identity=label):
                self.assertFalse(
                    crocods.crocods_log_proves_contract(
                        baseline,
                        crocods.CROCODS_CORE_ID,
                        "armhf",
                        commit,
                        tree,
                    )
                )
        with self.assertRaises(PipelineError):
            crocods.crocods_log_proves_contract(
                baseline,
                crocods.CROCODS_CORE_ID,
                "unknown",
                identity["source_commit"],
                identity["source_tree"],
            )

    def test_arm64_diagnostic_stream_and_position_mutations_fail(self) -> None:
        identity = crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        baseline = ORACLE_LOGS["arm64-final"].read_text(encoding="utf-8")
        arguments = (
            crocods.CROCODS_CORE_ID,
            "arm64",
            identity["source_commit"],
            identity["source_tree"],
        )
        apps_autorun = (
            crocods.CROCODS_EXPECTED_DIAGNOSTIC_STREAMS["arm64"][
                "apps_autorun"
            ]
        )
        swapped_lines = baseline.splitlines()
        first_position = swapped_lines.index(apps_autorun[0])
        second_position = swapped_lines.index(apps_autorun[1])
        swapped_lines[first_position], swapped_lines[second_position] = (
            swapped_lines[second_position],
            swapped_lines[first_position],
        )
        swapped_stream = "\n".join(swapped_lines) + "\n"

        moved_lines = baseline.splitlines()
        heading = apps_autorun[0]
        moved_lines.remove(heading)
        link_position = next(
            index
            for index, line in enumerate(moved_lines)
            if f" -o {crocods.CROCODS_BUILD_ARTIFACT_NAME} " in line
        )
        moved_lines.insert(link_position + 1, heading)
        diagnostic_after_link = "\n".join(moved_lines) + "\n"

        success_trailer = "\n".join(crocods.CROCODS_SUCCESS_TRAILER) + "\n"
        mutations = {
            "changed-warning": baseline.replace(
                apps_autorun[1], apps_autorun[1] + " injected", 1
            ),
            "missing-context": baseline.replace(apps_autorun[2] + "\n", "", 1),
            "same-lines-wrong-stream-order": swapped_stream,
            "diagnostic-after-link": diagnostic_after_link,
            "extra-note": baseline.replace(
                success_trailer,
                "rogue.c:1:1: note: injected note\n" + success_trailer,
                1,
            ),
        }
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    crocods.crocods_log_proves_contract(changed, *arguments)
                )


if __name__ == "__main__":
    unittest.main()
