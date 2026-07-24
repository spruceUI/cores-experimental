from __future__ import annotations

import copy
from collections import Counter
import json
from pathlib import Path
import shlex
import unittest

from scripts.core_pipeline_lib.contracts import mixed_language, vemulator
from scripts.core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)
from scripts.core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from scripts.core_pipeline_lib.foundation import sha256_file


ROOT = Path(__file__).resolve().parents[1]
ORACLE_RUNS = (
    "tranche23f-uzem-vemulator-final-golden-v1",
    "tranche23g-uzem-vemulator-final-repro-v1",
)
ORACLE_E2E_FILE_SHA256 = {
    ORACLE_RUNS[0]: (
        "a09cf5669677db261574008158d0707e0595256fb2a53f87b5f01bb46c2ef8b0"
    ),
    ORACLE_RUNS[1]: (
        "07a0eced2b67bc0d199ffcf9ff1322f1b1f2102a2ad63122c952a237b179981a"
    ),
}
ORACLE_E2E_CONTENT_SHA256 = {
    ORACLE_RUNS[0]: (
        "e5f3b0d515d086ef88154f5ac6883b1f5f4443802efd902a1905c66e2c14c8ad"
    ),
    ORACLE_RUNS[1]: (
        "1f7ab7de48b6982acc6ad05cf4a7c88c132b82cb9a766b765c0163fbab97ba48"
    ),
}
ORACLE_BUILD_RECORD_SHA256 = {
    ORACLE_RUNS[0]: {
        "arm64": (
            "a489791f7cb4fff7b83918c6024583921a6e734a3fc10b9ff39e7aa4b03d4786"
        ),
        "armhf": (
            "2fed5b9886e7ff24035425ae1f0422a02d40384ff2fbc87fbf1add792003f790"
        ),
    },
    ORACLE_RUNS[1]: {
        "arm64": (
            "133b4b6492373ffe488a88f8f21ae6dc4e9e34aa7e5bd8ad9d20aa5e01a0806f"
        ),
        "armhf": (
            "17b33a5329f1562160059a2fb4b8d77b26d8cfc579659056314eb74866486c4e"
        ),
    },
}
ORACLE_LOG_SHA256 = {
    ORACLE_RUNS[0]: {
        "arm64": (
            "0a0f68ce89e80d835fb290ba7fb6bc5f230bf308a11712ed58da3c097428d88d"
        ),
        "armhf": (
            "b15b84dcb7aef5eee2a6fde8d40486e9666f5cb5c65b6336042fbc6d5700d226"
        ),
    },
    ORACLE_RUNS[1]: {
        "arm64": (
            "da809a246800145a892acb578879945907984a75416d8c5225a15738ba7da0bb"
        ),
        "armhf": (
            "06c731b5e37f483f82f672f833aa7ff60cf96ac58273606a1ae3c23162b14342"
        ),
    },
}
ORACLE_ARTIFACT = {
    "arm64": (
        "61043bc714311e7aeb56b92d1d184a5757d6e826d33d53b7a243b91a912ba082",
        107624,
    ),
    "armhf": (
        "b8f02db5e0a9310fe57dfbd3fa4ad9e030ee09d4f0fd0d8d2df18cbdc2693b41",
        86968,
    ),
}
ORACLE_METADATA = (
    "cb86096d041ad7486a98dc0c98921f88d26eea56a6b52112569763b02256f0c7",
    725,
)
ORACLE_PACKAGE = (
    "ffef51166c01f6414bc1258d66e4a71f810ee42a4cbda8a623dc32edb424cdf8",
    74370,
)
SOURCE_LOCK_PATH = (
    ROOT
    / "pins/sources/vemulator/7fade95506201aed83316cc3f2efe3d7cecf75a7.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "32f4725c7d318dc1c93c115448327227ecb01a1722c8b6b5044e16b835090427"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "fe035f98956157700a60a897e4463937f7833b2a138ebf96f1e5b15e780aa472"
)
SOURCE_RECORD_IDENTITY = {
    "commit": "7fade95506201aed83316cc3f2efe3d7cecf75a7",
    "requested_ref": "refs/heads/master",
    "resolved_commit": "7fade95506201aed83316cc3f2efe3d7cecf75a7",
    "resolved_url": "https://github.com/libretro/vemulator-libretro.git",
    "submodules": [],
    "tree": "09e8c0ec31c874ea555288c53c975e289e865c0a",
    "url": "https://github.com/libretro/vemulator-libretro.git",
}

COMPILERS = {
    "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
    "armhf": (
        "arm-a30-linux-gnueabihf-gcc",
        "arm-a30-linux-gnueabihf-g++",
    ),
}
C_OPTIONS = (
    "-Wall",
    "-pedantic",
    "-fPIC",
    "-I.",
    "-I./libretro-common/include",
    "-fPIC",
)
CXX_OPTIONS = (
    "-O3",
    "-Wall",
    "-pedantic",
    "-fPIC",
    "-I.",
    "-I./libretro-common/include",
    "-std=c++98",
    "-fPIC",
)


def build_vemulator_log_fixture(
    architecture: str, *, source_marker: bool = True
) -> str:
    """Build a portable exact log without requiring ignored evidence."""

    c_compiler, cxx_compiler = COMPILERS[architecture]
    compile_lines = []
    for output, source in vemulator.VEMULATOR_EXPECTED_COMPILE_PAIRS:
        is_c = source.endswith(".c")
        compile_lines.append(
            " ".join(
                (
                    c_compiler if is_c else cxx_compiler,
                    *(C_OPTIONS if is_c else CXX_OPTIONS),
                    "-c",
                    "-o",
                    output,
                    source,
                )
            )
        )

    compile_and_diagnostics = []
    for line in compile_lines:
        compile_and_diagnostics.append(line)
        if architecture == "arm64" and line.endswith(" ram.cpp"):
            compile_and_diagnostics.extend(
                vemulator.VEMULATOR_ARM64_COMPAT_DIAGNOSTIC_BLOCK.splitlines()
            )
        if architecture == "armhf" and line.endswith(" interrupts.cpp"):
            compile_and_diagnostics.extend(
                vemulator.VEMULATOR_ARMHF_COMPAT_DIAGNOSTIC_BLOCK.splitlines()
            )
        if architecture == "armhf" and line.endswith(" vmu.cpp"):
            compile_and_diagnostics.extend(
                vemulator.VEMULATOR_ARMHF_FLASH_DIAGNOSTIC_BLOCK.splitlines()
            )

    markers = [vemulator.VEMULATOR_SOURCE_HEAD_MARKER]
    if source_marker:
        markers.append(vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER)
    _c, _cxx, strip, make = vemulator.VEMULATOR_COMPILER_TOOLCHAINS[
        architecture
    ]
    return (
        "\n".join(
            (
                *vemulator.VEMULATOR_FETCH_PREFIX,
                *vemulator.VEMULATOR_SUCCESS_MARKER,
                *markers,
                "PLATFORM: Linux",
                "ARCHITECTURE: x86_64",
                "TARGET: unix",
                f"CC = {c_compiler}",
                f"CXX = {cxx_compiler}",
                f"CXX11 = {cxx_compiler}",
                f"CXX17 = {cxx_compiler}",
                f"STRIP = {strip}",
                f'Compiler: CC="{c_compiler}" CXX="{cxx_compiler}"',
                "=== x86 CPU detected... ===",
                "=== x86_64 CPU detected... ===",
                "unix",
                "unix",
                "=== VEmulator",
                "Building vemulator...",
                'cd "/libretro-super/libretro-vemulator"',
                f'{make} -f Makefile platform="unix" -j24  clean',
                vemulator.VEMULATOR_CLEAN_COMMAND,
                f'{make} -f Makefile platform="unix" -j24 '
                f'CC="{c_compiler}" CXX="{cxx_compiler}" ',
                *compile_and_diagnostics,
                " ".join(
                    vemulator.VEMULATOR_EXPECTED_ORDERED_LINK_ARGV[
                        architecture
                    ]
                ),
                *vemulator.VEMULATOR_SUCCESS_TRAILER,
            )
        )
        + "\n"
    )


def catalog_spec() -> dict:
    document = json.loads(
        (ROOT / "manifests/core-builds.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(document["cores"][vemulator.VEMULATOR_CORE_ID])


class VemulatorContractTests(unittest.TestCase):
    def contract_arguments(
        self, log: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = vemulator.VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY
        return (
            log,
            vemulator.VEMULATOR_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def assert_active_rejects(self, log: str, architecture: str) -> None:
        self.assertFalse(
            vemulator.vemulator_log_proves_contract(
                *self.contract_arguments(log, architecture)
            )
        )

    def test_exact_identity_spec_and_golden_predicates_are_core_owned(self) -> None:
        spec = catalog_spec()
        identity = vemulator.VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY
        self.assertTrue(vemulator.vemulator_spec_is_well_formed(spec))
        self.assertEqual(
            "vemulator-mixed-language-v1",
            vemulator.VEMULATOR_LOG_CONTRACT_ID,
        )
        self.assertEqual("core-arch-source", vemulator.VEMULATOR_LOG_PROOF_KIND)
        self.assertEqual("Makefile", identity["native_makefile"])
        self.assertEqual(
            "source-literal-v1",
            identity["native_runtime_version_derivation"],
        )
        self.assertEqual("0.1", identity["native_runtime_version"])
        self.assertEqual("main.cpp", identity["native_runtime_version_source"])
        self.assertNotIn("git_version", spec["build"])

        def changed(path: tuple[str, ...], value: object) -> dict:
            result = copy.deepcopy(spec)
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return result

        mutations = {
            "workflow": changed(("workflow",), "build.yml"),
            "source-url": changed(("source", "url"), "https://example.com"),
            "source-ref": changed(
                ("source", "requested_ref"), "refs/heads/main"
            ),
            "source-commit": changed(("source", "commit"), "0" * 40),
            "source-tree": changed(("source", "tree"), "0" * 40),
            "driver": changed(("build", "driver"), "direct-make"),
            "source-key": changed(("build", "source_key"), "uzem"),
            "source-dir": changed(("build", "source_dir"), "other"),
            "output": changed(("build", "output_path"), "other.so"),
            "artifact": changed(("build", "artifact_name"), "other.so"),
            "metadata": changed(
                ("metadata", "artifact_name"), "other.info"
            ),
            "targets": changed(("targets",), ["arm64"]),
        }
        injected_version = copy.deepcopy(spec)
        injected_version["build"]["git_version"] = {
            "derivation": "native-space-short7-v1",
            "value": " 7fade95",
        }
        mutations["injected-version"] = injected_version
        extra = copy.deepcopy(spec)
        extra["unexpected"] = True
        mutations["extra"] = extra
        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    vemulator.vemulator_spec_is_well_formed(mutation)
                )

        source = copy.deepcopy(SOURCE_RECORD_IDENTITY)
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            vemulator.vemulator_golden_source_is_well_formed(
                vemulator.VEMULATOR_CORE_ID, source
            )
        )
        self.assertTrue(
            vemulator.vemulator_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                vemulator.VEMULATOR_CORE_ID,
                source,
            )
        )
        for label, mutation in {
            "git-version": {**build, "git_version": {"value": "0.1"}},
            "definition": {**build, "compile_definitions": ["VERSION=0.1"]},
            "log-path": {**build, "log": "other.log"},
            "bad-hash": {**build, "log_sha256": "a" * 63},
            "extra": {**build, "unexpected": True},
        }.items():
            with self.subTest(golden_build=label):
                self.assertFalse(
                    vemulator.vemulator_golden_build_contract_is_well_formed(
                        mutation,
                        identity["source_commit"],
                        vemulator.VEMULATOR_CORE_ID,
                        source,
                    )
                )

    def test_compile_and_ordered_link_mutations_fail_closed(self) -> None:
        for architecture, (c_compiler, cxx_compiler) in COMPILERS.items():
            log = build_vemulator_log_fixture(architecture)
            compile_lines = [
                line for line in log.splitlines() if " -c " in line
            ]
            first_c = compile_lines[0]
            first_cxx = next(
                line for line in compile_lines if line.startswith(cxx_compiler)
            )
            link = " ".join(
                vemulator.VEMULATOR_EXPECTED_ORDERED_LINK_ARGV[architecture]
            )
            first_object = vemulator.VEMULATOR_EXPECTED_RAW_LINK_OBJECTS[0]
            second_object = vemulator.VEMULATOR_EXPECTED_RAW_LINK_OBJECTS[1]
            mutations = {
                "missing-compile": log.replace(first_c + "\n", "", 1),
                "duplicate-compile": log.replace(
                    first_c + "\n", first_c + "\n" + first_c + "\n", 1
                ),
                "changed-source": log.replace(
                    "compat_posix_string.c", "compat_other.c", 1
                ),
                "changed-output": log.replace(
                    "compat_posix_string.o", "compat_other.o", 1
                ),
                "changed-option": log.replace(" -Wall ", " -Wextra ", 1),
                "injected-version": log.replace(
                    " -Wall ", " -DGIT_VERSION=7fade95 -Wall ", 1
                ),
                "c-with-cxx": log.replace(c_compiler, cxx_compiler, 1),
                "cxx-with-c": log.replace(first_cxx, first_cxx.replace(
                    cxx_compiler, c_compiler, 1
                ), 1),
                "response-file": log.replace(
                    first_c, first_c + " @compile.rsp", 1
                ),
                "wrapped-compile": log.replace(
                    first_c, "ccache " + first_c, 1
                ),
                "env-compile": log.replace(first_c, "env " + first_c, 1),
                "wrong-link-compiler": log.replace(
                    link, link.replace(cxx_compiler, c_compiler, 1), 1
                ),
                "link-option": log.replace(
                    "-Wl,--no-undefined", "-Wl,--allow-shlib-undefined", 1
                ),
                "link-object": log.replace(first_object, "./other.o", 1),
                "link-reordered": log.replace(
                    f"{first_object} {second_object}",
                    f"{second_object} {first_object}",
                    1,
                ),
                "second-link": log.replace(link + "\n", link + "\n" + link + "\n", 1),
            }
            for label, mutation in mutations.items():
                with self.subTest(architecture=architecture, mutation=label):
                    self.assert_active_rejects(mutation, architecture)

    def test_fetch_setup_jobs_and_artifact_framing_fail_closed(self) -> None:
        for architecture in COMPILERS:
            log = build_vemulator_log_fixture(architecture)
            first_line = vemulator.VEMULATOR_FETCH_PREFIX[0]
            clone_line = vemulator.VEMULATOR_FETCH_PREFIX[-2]
            link = " ".join(
                vemulator.VEMULATOR_EXPECTED_ORDERED_LINK_ARGV[architecture]
            )
            clean = vemulator.VEMULATOR_CLEAN_COMMAND
            first_object = vemulator.VEMULATOR_EXPECTED_RAW_LINK_OBJECTS[0]
            overwrite = (
                f"cp /tmp/unreviewed.so {vemulator.VEMULATOR_BUILD_ARTIFACT_NAME}\n"
            )
            mutations = {
                "source-mutation-before-fetch": log.replace(
                    first_line,
                    "cp /tmp/unreviewed.cpp flash.cpp\n" + first_line,
                    1,
                ),
                "makefile-mutation-after-clone": log.replace(
                    clone_line + "\n",
                    clone_line + "\ncp /tmp/unreviewed.Makefile Makefile\n",
                    1,
                ),
                "source-mutation-before-clean": log.replace(
                    clean + "\n", "cp rogue.cpp flash.cpp\n" + clean + "\n", 1
                ),
                "source-mutation-before-compile": log.replace(
                    clean + "\n", clean + "\ncp rogue.cpp flash.cpp\n", 1
                ),
                "hidden-ccache-compiler": log.replace(
                    first_line, "ccache clang @compile.rsp\n" + first_line, 1
                ),
                "hidden-env-compiler": log.replace(
                    first_line,
                    "env clang -c evil.c -o evil.o\n" + first_line,
                    1,
                ),
                "hidden-shell-compiler": log.replace(
                    first_line,
                    "sh -c 'gcc -c evil.c -o evil.o'\n" + first_line,
                    1,
                ),
                "malformed-compiler": log.replace(
                    first_line, "clang 'open\n" + first_line, 1
                ),
                "wrong-clone": log.replace("vemulator-libretro.git", "other.git", 1),
                "wrong-directory": log.replace(
                    'cd "/libretro-super/libretro-vemulator"',
                    'cd "/tmp/libretro-vemulator"',
                    1,
                ),
                "wrong-makefile": log.replace("-f Makefile ", "-f Otherfile ", 1),
                "zero-jobs": log.replace("-j24", "-j0"),
                "mismatched-jobs": log.replace("-j24", "-j7", 1),
                "missing-clean": log.replace(clean + "\n", "", 1),
                "changed-clean": log.replace(
                    clean, clean.replace(first_object, "./other.o", 1), 1
                ),
                "duplicate-clean": log.replace(
                    clean + "\n", clean + "\n" + clean + "\n", 1
                ),
                "overwrite-before-clean": log.replace(
                    clean + "\n", overwrite + clean + "\n", 1
                ),
                "overwrite-before-link": log.replace(
                    link + "\n", overwrite + link + "\n", 1
                ),
                "overwrite-after-link": log.replace(
                    link + "\n", link + "\n" + overwrite, 1
                ),
                "missing-copy": log.replace(
                    vemulator.VEMULATOR_COPY_COMMAND + "\n", "", 1
                ),
                "duplicate-copy": log.replace(
                    vemulator.VEMULATOR_COPY_COMMAND + "\n",
                    vemulator.VEMULATOR_COPY_COMMAND
                    + "\n"
                    + vemulator.VEMULATOR_COPY_COMMAND
                    + "\n",
                    1,
                ),
                "trailing-output": log + "post-success output\n",
                "post-link-output": log.replace(
                    link + "\n", link + "\npost-link output\n", 1
                ),
            }
            for label, mutation in mutations.items():
                with self.subTest(architecture=architecture, mutation=label):
                    self.assert_active_rejects(mutation, architecture)

            alternate_jobs = log.replace("-j24", "-j7")
            self.assertTrue(
                vemulator.vemulator_log_proves_contract(
                    *self.contract_arguments(alternate_jobs, architecture)
                ),
                "one consistent positive scheduler width is non-semantic",
            )

    def test_diagnostics_are_exact_owned_and_parallel_position_tolerant(self) -> None:
        arm64 = build_vemulator_log_fixture("arm64")
        compat64 = vemulator.VEMULATOR_ARM64_COMPAT_DIAGNOSTIC_BLOCK
        compat_source64 = next(
            line
            for line in arm64.splitlines()
            if " -c " in line
            and line.endswith("libretro-common/compat/compat_snprintf.c")
        )
        link64 = " ".join(
            vemulator.VEMULATOR_EXPECTED_ORDERED_LINK_ARGV["arm64"]
        )
        for label, mutation in {
            "missing": arm64.replace(compat64 + "\n", "", 1),
            "duplicate": arm64.replace(
                compat64 + "\n", compat64 + "\n" + compat64 + "\n", 1
            ),
            "changed-line": arm64.replace(":83: warning:", ":84: warning:", 1),
            "extra-warning": arm64.replace(
                link64 + "\n", "warning: synthetic\n" + link64 + "\n", 1
            ),
            "extra-note": arm64.replace(
                link64 + "\n", "note: synthetic\n" + link64 + "\n", 1
            ),
            "before-owner": arm64.replace(compat64 + "\n", "", 1).replace(
                compat_source64 + "\n",
                compat64 + "\n" + compat_source64 + "\n",
                1,
            ),
            "armhf-flash-block": arm64.replace(
                link64 + "\n",
                vemulator.VEMULATOR_ARMHF_FLASH_DIAGNOSTIC_BLOCK
                + "\n"
                + link64
                + "\n",
                1,
            ),
        }.items():
            with self.subTest(architecture="arm64", mutation=label):
                self.assert_active_rejects(mutation, "arm64")

        moved64 = arm64.replace(compat64 + "\n", "", 1).replace(
            compat_source64 + "\n",
            compat_source64 + "\n" + compat64 + "\n",
            1,
        )
        self.assertTrue(
            vemulator.vemulator_log_proves_contract(
                *self.contract_arguments(moved64, "arm64")
            )
        )

        armhf = build_vemulator_log_fixture("armhf")
        compat_hf = vemulator.VEMULATOR_ARMHF_COMPAT_DIAGNOSTIC_BLOCK
        flash = vemulator.VEMULATOR_ARMHF_FLASH_DIAGNOSTIC_BLOCK
        flash_source = next(
            line
            for line in armhf.splitlines()
            if " -c " in line and line.endswith(" flash.cpp")
        )
        link_hf = " ".join(
            vemulator.VEMULATOR_EXPECTED_ORDERED_LINK_ARGV["armhf"]
        )
        for label, mutation in {
            "missing-compat": armhf.replace(compat_hf + "\n", "", 1),
            "missing-flash": armhf.replace(flash + "\n", "", 1),
            "duplicate-flash": armhf.replace(
                flash + "\n", flash + "\n" + flash + "\n", 1
            ),
            "changed-flash-warning": armhf.replace(
                "forming offset 12", "forming offset 11", 1
            ),
            "changed-flash-source": armhf.replace(
                "flash.cpp:395:45", "other.cpp:395:45", 1
            ),
            "flash-before-owner": armhf.replace(flash + "\n", "", 1).replace(
                flash_source + "\n", flash + "\n" + flash_source + "\n", 1
            ),
            "extra-warning": armhf.replace(
                link_hf + "\n", "warning: synthetic\n" + link_hf + "\n", 1
            ),
        }.items():
            with self.subTest(architecture="armhf", mutation=label):
                self.assert_active_rejects(mutation, "armhf")

        moved_flash = armhf.replace(flash + "\n", "", 1).replace(
            flash_source + "\n", flash_source + "\n" + flash + "\n", 1
        )
        self.assertTrue(
            vemulator.vemulator_log_proves_contract(
                *self.contract_arguments(moved_flash, "armhf")
            )
        )

    def test_identity_architecture_and_input_types_fail_closed(self) -> None:
        identity = vemulator.VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY
        log = build_vemulator_log_fixture("arm64")
        mutations = (
            (
                "wrong-core",
                (
                    log,
                    "uzem",
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ),
            (
                "wrong-commit",
                (
                    log,
                    vemulator.VEMULATOR_CORE_ID,
                    "arm64",
                    "0" * 40,
                    identity["source_tree"],
                ),
            ),
            (
                "wrong-tree",
                (
                    log,
                    vemulator.VEMULATOR_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    "0" * 40,
                ),
            ),
            (
                "unknown-architecture",
                (
                    log,
                    vemulator.VEMULATOR_CORE_ID,
                    "x86_64",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ),
        )
        for label, arguments in mutations:
            with self.subTest(mutation=label):
                self.assertFalse(
                    vemulator.vemulator_log_proves_contract(*arguments)
                )
        for malformed in (None, b"log", [], {}, 7):
            with self.subTest(malformed=malformed):
                self.assertFalse(
                    vemulator.vemulator_log_proves_contract(
                        malformed,
                        vemulator.VEMULATOR_CORE_ID,
                        "arm64",
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
