from __future__ import annotations

from pathlib import Path
import shlex
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import gambatte, mixed_language
from core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)
from core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from core_pipeline_lib.contracts.registry import core_log_contract_for
from core_pipeline_lib.foundation import sha256_bytes, sha256_file
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]
ORACLE_ROOT = ROOT / "tests/fixtures/per-core-oracles/gambatte"
ORACLE_FILE_SHA256 = {
    "arm64": "65dbbe317653686fd54f29e6cd7aeaa085b02b5bd750f274130b946e9ba43637",
    "armhf": "a72a8cb650e3ae66abdb298054f925573a7937ec90067977cf107520cd633cd1",
}
ORACLE_SIZE = {"arm64": 28236, "armhf": 28533}
TUNING_MARKER = (
    "CORE_PIPELINE_CHIPSET_TUNING|"
    '{"compiler_argument_mapping_version":"gcc-machine-flags-v1",'
    '"compiler_arguments":[],"content_sha256":'
    '"f1cde5e5d8896ad26393b84289da1ef9bb84aa3a7db9fadf3ce2207fa243d7e0",'
    '"profile_id":"universal-v1"}'
)


class GambatteLogContractTests(unittest.TestCase):
    def _oracle_raw(self, arch: str) -> str:
        return (ORACLE_ROOT / f"{arch}-build.txt").read_text(
            encoding="utf-8"
        )

    def _oracle_proof_log(self, arch: str) -> str:
        """Mirror the registry-owned empty-tuning projection."""

        lines = self._oracle_raw(arch).splitlines()
        self.assertEqual(TUNING_MARKER, lines[0])
        return "\n".join(lines[1:]) + "\n"

    def _arguments(
        self, log: str, arch: str
    ) -> tuple[str, str, str, str, str]:
        identity = gambatte.GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            log,
            gambatte.GAMBATTE_CORE_ID,
            arch,
            identity["source_commit"],
            identity["source_tree"],
        )

    def _assert_rejected(self, log: str, arch: str) -> None:
        arguments = self._arguments(log, arch)
        self.assertFalse(gambatte.gambatte_log_proves_contract(*arguments))
        self.assertFalse(
            pipeline.registered_core_log_contract_proves(*arguments)
        )

    def _compile_and_link_lines(
        self, log: str, arch: str
    ) -> tuple[list[str], str]:
        expected_compilers = TARGET_COMPILERS[arch]
        expected_cxx_compilers = TARGET_CXX_COMPILERS[arch]
        contract = gambatte.gambatte_mixed_language_contract()
        compile_lines: list[str] = []
        link_lines: list[str] = []
        for line in log.splitlines():
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if not tokens or tokens[0] not in expected_compilers:
                continue
            if "-c" in tokens:
                compile_lines.append(line)
            elif (
                mixed_language.mixed_language_link_command(
                    tokens, expected_cxx_compilers, contract
                )
                is not None
            ):
                link_lines.append(line)
        self.assertEqual(1, len(link_lines))
        return compile_lines, link_lines[0]

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
        self.assertEqual(
            identity["artifact_name"], spec["build"]["artifact_name"]
        )
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
        aliases = (
            gambatte.gambatte_mixed_language_contract().semantic_path_aliases
        )
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

    def test_raw_compile_and_ordered_link_maps_are_explicit_and_exact(
        self,
    ) -> None:
        contract = gambatte.gambatte_mixed_language_contract()
        self.assertEqual(
            gambatte.GAMBATTE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256,
            contract.expected_raw_compile_invocation_sha256,
        )
        self.assertEqual(
            gambatte.GAMBATTE_EXPECTED_ORDERED_LINK_ARGV_SHA256,
            contract.expected_ordered_link_argv_sha256,
        )
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                compile_lines, link_line = self._compile_and_link_lines(
                    self._oracle_proof_log(arch), arch
                )
                self.assertEqual(
                    gambatte.GAMBATTE_EXPECTED_COMPILE_COUNT,
                    len(compile_lines),
                )
                self.assertEqual(
                    gambatte.GAMBATTE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256[
                        arch
                    ],
                    mixed_language.mixed_language_raw_compile_invocation_sha256(
                        tuple(shlex.split(line)) for line in compile_lines
                    ),
                )
                self.assertEqual(
                    gambatte.GAMBATTE_EXPECTED_ORDERED_LINK_ARGV_SHA256[arch],
                    ordered_command_argv_sha256(shlex.split(link_line)),
                )

    def test_tracked_real_log_oracles_are_exact_and_prove_contract(
        self,
    ) -> None:
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                path = ORACLE_ROOT / f"{arch}-build.txt"
                raw = path.read_text(encoding="utf-8")
                proof_log = self._oracle_proof_log(arch)
                self.assertEqual(ORACLE_FILE_SHA256[arch], sha256_file(path))
                self.assertEqual(ORACLE_SIZE[arch], path.stat().st_size)
                self.assertEqual(84, len(raw.splitlines()))
                self.assertTrue(raw.endswith("\n"))
                # The direct core proof receives the registry-projected log,
                # never an unprojected registry-owned tuning marker.
                self.assertFalse(
                    gambatte.gambatte_log_proves_contract(
                        *self._arguments(raw, arch)
                    )
                )
                self.assertTrue(
                    gambatte.gambatte_log_proves_contract(
                        *self._arguments(proof_log, arch)
                    )
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(
                        *self._arguments(proof_log, arch)
                    )
                )
                tuning = pipeline.execution_tuning_profile(
                    "universal-v1", arch
                )
                self.assertTrue(
                    pipeline._registered_core_log_contract_proves(
                        *self._arguments(raw, arch), tuning=tuning
                    )
                )

    def test_synthetic_fixture_dispatches_with_all_exact_digests(self) -> None:
        fixture = build_mixed_language_log_fixture(
            pipeline, ROOT, gambatte.GAMBATTE_CORE_ID, "arm64"
        )
        spec = fixture["spec"]
        marker_count = len(pipeline.git_version_log_markers(spec))
        command_lines = fixture["log"].splitlines()[marker_count:]
        compile_lines = [
            line for line in command_lines if " -c " in f" {line} "
        ]
        clean_command = "rm -f " + " ".join(
            [
                *[entry[0] for entry in fixture["entries"]],
                gambatte.GAMBATTE_BUILD_ARTIFACT_NAME,
            ]
        )
        c_compiler = fixture["c_compiler"]
        cxx_compiler = fixture["cxx_compiler"]
        framed_log = (
            "\n".join(
                (
                    *gambatte.GAMBATTE_FETCH_PREFIX,
                    *gambatte.GAMBATTE_SUCCESS_MARKER,
                    gambatte.GAMBATTE_SOURCE_HEAD_MARKER,
                    *gambatte.GAMBATTE_NATIVE_VERSION_MARKERS,
                    *gambatte._post_marker_build_prefix("arm64"),
                    'make -f Makefile.libretro platform="unix" -j24  clean',
                    clean_command,
                    (
                        'make -f Makefile.libretro platform="unix" -j24 '
                        f'CC="{c_compiler}" CXX="{cxx_compiler}" '
                    ),
                    *command_lines,
                    *gambatte.GAMBATTE_SUCCESS_TRAILER,
                )
            )
            + "\n"
        )
        arguments = (
            framed_log,
            gambatte.GAMBATTE_CORE_ID,
            "arm64",
            spec["source"]["commit"],
            spec["source"]["tree"],
        )
        raw_compile_sha256 = (
            mixed_language.mixed_language_raw_compile_invocation_sha256(
                tuple(shlex.split(line)) for line in compile_lines
            )
        )
        ordered_link_sha256 = ordered_command_argv_sha256(
            shlex.split(fixture["link_line"])
        )
        with mock.patch.object(
            gambatte,
            "GAMBATTE_EXPECTED_COMPILE_PAIR_SHA256",
            fixture["compile_pair_sha256"],
        ), mock.patch.dict(
            gambatte.GAMBATTE_EXPECTED_COMPILE_INVOCATION_SHA256,
            {"arm64": fixture["compile_invocation_sha256"]},
        ), mock.patch.dict(
            gambatte.GAMBATTE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256,
            {"arm64": raw_compile_sha256},
        ), mock.patch.object(
            gambatte,
            "GAMBATTE_EXPECTED_LINK_OBJECT_SHA256",
            fixture["link_object_sha256"],
        ), mock.patch.object(
            gambatte,
            "GAMBATTE_EXPECTED_RAW_LINK_OBJECT_SHA256",
            fixture["raw_link_object_sha256"],
        ), mock.patch.dict(
            gambatte.GAMBATTE_EXPECTED_ORDERED_LINK_ARGV_SHA256,
            {"arm64": ordered_link_sha256},
        ), mock.patch.object(
            gambatte,
            "GAMBATTE_CLEAN_COMMAND_SHA256",
            sha256_bytes(clean_command.encode("utf-8")),
        ):
            self.assertTrue(gambatte.gambatte_log_proves_contract(*arguments))
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(*arguments)
            )
            self.assertFalse(
                gambatte.gambatte_log_proves_contract(
                    framed_log,
                    "tgbdual",
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            self.assertFalse(
                gambatte.gambatte_log_proves_contract(
                    framed_log + "fatal: synthetic failure\n",
                    gambatte.GAMBATTE_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )

    def test_parallel_compile_echo_permutation_remains_accepted(self) -> None:
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                log = self._oracle_proof_log(arch)
                lines = log.splitlines()
                expected_compilers = TARGET_COMPILERS[arch]
                positions = [
                    position
                    for position, line in enumerate(lines)
                    if (tokens := shlex.split(line))
                    and tokens[0] in expected_compilers
                    and "-c" in tokens
                ]
                self.assertEqual(
                    gambatte.GAMBATTE_EXPECTED_COMPILE_COUNT, len(positions)
                )
                reversed_lines = [lines[position] for position in positions]
                reversed_lines.reverse()
                for position, replacement in zip(
                    positions, reversed_lines, strict=True
                ):
                    lines[position] = replacement
                permuted = "\n".join(lines) + "\n"
                self.assertTrue(
                    gambatte.gambatte_log_proves_contract(
                        *self._arguments(permuted, arch)
                    )
                )

    def test_current_jobs_marker_and_matching_j8_invocations_are_accepted(
        self,
    ) -> None:
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                log = self._oracle_proof_log(arch)
                current = (
                    "CORE_PIPELINE_JOBS|8\n"
                    + log.replace("-j24  clean", "-j8  clean", 1).replace(
                        "-j24 CC=", "-j8 CC=", 1
                    )
                )
                self.assertTrue(
                    gambatte.gambatte_log_proves_contract(
                        *self._arguments(current, arch)
                    )
                )

    def test_whole_log_diagnostics_and_make_failures_are_rejected(self) -> None:
        diagnostics = (
            "synthetic.c:1: warning: unreviewed warning",
            "synthetic.c:1: note: unreviewed note",
            "synthetic.c:1: error: unreviewed error",
            "fatal: synthetic failure",
            "undefined reference to synthetic_symbol",
            "aarch64-linux-gnu-ld: cannot find -lsynthetic",
            "collect2: ld returned 1 exit status",
            "make: *** [gambatte_libretro.so] Error 1",
            "gmake[1]: *** [all] Error 2",
            "tool: command not found",
            "linker command failed with exit code 1",
            "Killed",
        )
        for arch in ("arm64", "armhf"):
            log = self._oracle_proof_log(arch)
            for diagnostic in diagnostics:
                with self.subTest(arch=arch, diagnostic=diagnostic):
                    self._assert_rejected(
                        log.replace(
                            gambatte.GAMBATTE_COPY_COMMAND,
                            diagnostic
                            + "\n"
                            + gambatte.GAMBATTE_COPY_COMMAND,
                            1,
                        ),
                        arch,
                    )

    def test_command_envelope_and_exact_spelling_fail_closed(self) -> None:
        for arch in ("arm64", "armhf"):
            log = self._oracle_proof_log(arch)
            compile_lines, link_line = self._compile_and_link_lines(log, arch)
            first_compile, second_compile = compile_lines[:2]
            first_object = "libgambatte/src/bootloader.o"
            second_object = "libgambatte/src/cpu.o"
            first_native, second_native, third_native = (
                gambatte.GAMBATTE_NATIVE_VERSION_MARKERS
            )
            cd_command = 'cd "/libretro-super/libretro-gambatte"'
            clean_invocation = next(
                line
                for line in log.splitlines()
                if re_fullmatch_make_clean(line)
            )
            build_invocation = next(
                line
                for line in log.splitlines()
                if " -j24 CC=" in line
                and "-f Makefile.libretro" in line
            )
            clean_command = next(
                line for line in log.splitlines() if line.startswith("rm -f ")
            )
            mutations = {
                "opaque-prefix": "UNREVIEWED BUILD OUTPUT\n" + log,
                "wrapped-compiler-prefix": (
                    "ccache aarch64-linux-gnu-gcc synthetic.c\n" + log
                ),
                "opaque-before-compile": log.replace(
                    first_compile,
                    "UNREVIEWED BUILD OUTPUT\n" + first_compile,
                    1,
                ),
                "file-write-before-compile": log.replace(
                    first_compile,
                    "touch injected\n" + first_compile,
                    1,
                ),
                "source-mutation-after-markers": log.replace(
                    third_native,
                    third_native + "\ngit checkout deadbee",
                    1,
                ),
                "wrapped-compiler-before-compile": log.replace(
                    first_compile,
                    "ccache aarch64-linux-gnu-gcc synthetic.c\n"
                    + first_compile,
                    1,
                ),
                "artifact-overwrite-before-compile": log.replace(
                    first_compile,
                    "cp /tmp/unreviewed.so gambatte_libretro.so\n"
                    + first_compile,
                    1,
                ),
                "opaque-compile-gap": log.replace(
                    first_compile,
                    first_compile + "\nUNREVIEWED BUILD OUTPUT",
                    1,
                ),
                "make-compile-gap": log.replace(
                    first_compile,
                    first_compile + "\nmake synthetic-step",
                    1,
                ),
                "opaque-after-link": log.replace(
                    link_line, link_line + "\nUNREVIEWED BUILD OUTPUT", 1
                ),
                "artifact-overwrite-after-link": log.replace(
                    link_line,
                    link_line
                    + "\nprintf attacker > gambatte_libretro.so",
                    1,
                ),
                "strip-after-link": log.replace(
                    link_line,
                    link_line + "\nstrip gambatte_libretro.so",
                    1,
                ),
                "compile-after-link": log.replace(
                    second_compile + "\n", "", 1
                ).replace(
                    link_line + "\n",
                    link_line + "\n" + second_compile + "\n",
                    1,
                ),
                "missing-compile": log.replace(first_compile + "\n", "", 1),
                "duplicate-compile": log.replace(
                    first_compile + "\n",
                    first_compile + "\n" + first_compile + "\n",
                    1,
                ),
                "changed-compile-option": log.replace(
                    first_compile,
                    first_compile.replace(" -O2 ", " -O3 ", 1),
                    1,
                ),
                "compile-output-spelling-drift": log.replace(
                    first_compile,
                    first_compile.replace(" -o", " -o ", 1),
                    1,
                ),
                "missing-link": log.replace(link_line + "\n", "", 1),
                "duplicate-link": log.replace(
                    link_line + "\n", link_line + "\n" + link_line + "\n", 1
                ),
                "reordered-link-options": log.replace(
                    link_line,
                    link_line.replace("-fPIC -shared", "-shared -fPIC", 1),
                    1,
                ),
                "reordered-link-objects": log.replace(
                    link_line,
                    link_line.replace(
                        f"{first_object} {second_object}",
                        f"{second_object} {first_object}",
                        1,
                    ),
                    1,
                ),
                "link-output-spelling-drift": log.replace(
                    link_line,
                    link_line.replace(
                        " -o gambatte_libretro.so",
                        " -ogambatte_libretro.so",
                        1,
                    ),
                    1,
                ),
                "reordered-native-markers": log.replace(
                    first_native + "\n" + second_native,
                    second_native + "\n" + first_native,
                    1,
                ),
                "source-marker-spelling-drift": log.replace(
                    gambatte.GAMBATTE_SOURCE_HEAD_MARKER,
                    gambatte.GAMBATTE_SOURCE_HEAD_MARKER.replace(
                        "Recreate", "Regenerate", 1
                    ),
                    1,
                ),
                "native-marker-spelling-drift": log.replace(
                    first_native,
                    first_native.replace(
                        "command-scoped-makeflags", "command scoped makeflags"
                    ),
                    1,
                ),
                "missing-source-marker": log.replace(
                    gambatte.GAMBATTE_SOURCE_HEAD_MARKER + "\n", "", 1
                ),
                "duplicate-source-marker": log.replace(
                    gambatte.GAMBATTE_SOURCE_HEAD_MARKER,
                    gambatte.GAMBATTE_SOURCE_HEAD_MARKER
                    + "\n"
                    + gambatte.GAMBATTE_SOURCE_HEAD_MARKER,
                    1,
                ),
                "missing-native-marker": log.replace(
                    first_native + "\n", "", 1
                ),
                "duplicate-native-marker": log.replace(
                    first_native,
                    first_native + "\n" + first_native,
                    1,
                ),
                "coordinated-unreviewed-marker-sha": marker_sha_mutation(log),
                "success-spelling-drift": log.replace(
                    "\tgambatte", "\tGambatte", 1
                ),
                "copy-path-spelling-drift": log.replace(
                    gambatte.GAMBATTE_COPY_COMMAND,
                    gambatte.GAMBATTE_COPY_COMMAND.replace(
                        "/dist/unix/", "/dist/other/", 1
                    ),
                    1,
                ),
                "clean-invocation-jobs-drift": log.replace(
                    clean_invocation,
                    clean_invocation.replace("-j24", "-j23", 1),
                    1,
                ),
                "missing-cd": log.replace(cd_command + "\n", "", 1),
                "changed-cd": log.replace(cd_command, "true", 1),
                "missing-clean-invocation": log.replace(
                    clean_invocation + "\n", "", 1
                ),
                "clean-command-spelling-drift": log.replace(
                    clean_command,
                    clean_command.replace("rm -f ", "rm -rf ", 1),
                    1,
                ),
                "missing-clean-command": log.replace(
                    clean_command + "\n", "", 1
                ),
                "build-invocation-jobs-drift": log.replace(
                    build_invocation,
                    build_invocation.replace("-j24", "-j23", 1),
                    1,
                ),
                "missing-build-invocation": log.replace(
                    build_invocation + "\n", "", 1
                ),
                "jobs-marker-mismatch": (
                    "CORE_PIPELINE_JOBS|8\n" + log
                ),
                "zero-jobs-marker": (
                    "CORE_PIPELINE_JOBS|0\n" + log
                ),
                "empty-jobs-marker": (
                    "CORE_PIPELINE_JOBS|\n" + log
                ),
                "word-jobs-marker": (
                    "CORE_PIPELINE_JOBS|eight\n" + log
                ),
                "negative-jobs-marker": (
                    "CORE_PIPELINE_JOBS|-8\n" + log
                ),
                "leading-zero-jobs-marker": (
                    "CORE_PIPELINE_JOBS|08\n" + log
                ),
                "duplicate-jobs-marker": (
                    "CORE_PIPELINE_JOBS|24\n"
                    "CORE_PIPELINE_JOBS|24\n"
                    + log
                ),
                "jobs-marker-after-prefix": log.replace(
                    gambatte.GAMBATTE_FETCH_PREFIX[0],
                    gambatte.GAMBATTE_FETCH_PREFIX[0]
                    + "\nCORE_PIPELINE_JOBS|24",
                    1,
                ),
                "arbitrary-trailing-output": (
                    log + "UNREVIEWED TRAILING OUTPUT\n"
                ),
            }
            for label, mutation in mutations.items():
                with self.subTest(arch=arch, mutation=label):
                    self.assertNotEqual(log, mutation)
                    self._assert_rejected(mutation, arch)

    def test_malformed_unknown_and_non_string_inputs_fail_closed(self) -> None:
        log = self._oracle_proof_log("arm64")
        first_compile, _link = self._compile_and_link_lines(log, "arm64")
        malformed = log.replace(
            first_compile[0], first_compile[0] + " 'unterminated", 1
        )
        self._assert_rejected(malformed, "arm64")
        identity = gambatte.GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        for arch in ("mips", "", [], {}):
            with self.subTest(arch=arch):
                self.assertFalse(
                    gambatte.gambatte_log_proves_contract(
                        log,
                        gambatte.GAMBATTE_CORE_ID,
                        arch,  # type: ignore[arg-type]
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
        for value in (None, b"", object()):
            with self.subTest(value_type=type(value).__name__):
                self.assertFalse(
                    gambatte.gambatte_log_proves_contract(
                        value,  # type: ignore[arg-type]
                        gambatte.GAMBATTE_CORE_ID,
                        "arm64",
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


def re_fullmatch_make_clean(line: str) -> bool:
    return bool(
        line.startswith(("make -f ", "gmake -f "))
        and 'platform="unix"' in line
        and line.endswith("  clean")
    )


def marker_sha_mutation(log: str) -> str:
    compile_token = gambatte.GAMBATTE_NATIVE_GIT_VERSION_LOG_TOKEN
    changed_compile_token = compile_token.replace("dfc1655", "deadbee")
    if log.count(compile_token) != 31:
        raise AssertionError("oracle must contain exactly 31 versioned compiles")
    mutated = log.replace(
        gambatte.GAMBATTE_SOURCE_HEAD_MARKER,
        gambatte.GAMBATTE_SOURCE_HEAD_MARKER.replace(
            "dfc1655", "deadbee"
        ),
        1,
    )
    for marker in gambatte.GAMBATTE_NATIVE_VERSION_MARKERS:
        mutated = mutated.replace(
            marker, marker.replace("dfc1655", "deadbee"), 1
        )
    mutated = mutated.replace(compile_token, changed_compile_token)
    if mutated.count(changed_compile_token) != 31 or mutated == log:
        raise AssertionError("coordinated marker mutation was incomplete")
    return mutated


if __name__ == "__main__":
    unittest.main()
