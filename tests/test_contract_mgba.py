from __future__ import annotations

import copy
import json
from pathlib import Path
import shlex
import unittest
import zipfile

from scripts.core_pipeline_lib.contracts import c_only, mgba
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
    "tranche1-mgba-golden-v1",
    "tranche1-mgba-repro-v1",
    "t5b-mgba-v2-control-20260716",
    "t5b-mgba-v2-final-20260716",
)
ORACLE_E2E_FILE_SHA256 = {
    ORACLE_RUNS[0]: (
        "14a7052542c12a192ced5cc40089bbe28d1c8030f63dcfeb2cb1b3bf54d8687f"
    ),
    ORACLE_RUNS[1]: (
        "cfa9e7ea3fd0bb48a4d268a3ba511fee6a61c2dccf366855dfd10b2ce2832141"
    ),
    ORACLE_RUNS[2]: (
        "3407c7fac15c35ad75355bfc9675e42e2774e79f10c8aa60a579a778599eece0"
    ),
    ORACLE_RUNS[3]: (
        "8ce79b96b9901b6a6f234262e67ea73e2566383bcda7640ea0d8e15d602381b7"
    ),
}
ORACLE_E2E_CONTENT_SHA256 = {
    ORACLE_RUNS[0]: (
        "534ddab8e0e6e510ca0e9ac0b5237b7e403141bd10e76e4b4450120f4879d1bd"
    ),
    ORACLE_RUNS[1]: (
        "cfba036697cd6bf510f5bc43dbaa66e6406c832985cec372fab6552ec2e09f87"
    ),
    ORACLE_RUNS[2]: (
        "627543bc36dbd0c4640d5a6f00df88f184c767b00a3350b70f97aacd133b2aca"
    ),
    ORACLE_RUNS[3]: (
        "4ef3f8702ab1b8feeb40de9bc7d671eba5737cae2a49af3caeac5942aa8992ef"
    ),
}
ORACLE_BUILD_RECORD_SHA256 = {
    ORACLE_RUNS[0]: {
        "arm64": (
            "109c705d33a638079ca3203434183189aa502ee6bfb38598829af2363402878f"
        ),
        "armhf": (
            "8d3f90bb359335eb5181583e05a1d97af999711f0e9ad4a0f532f58dffff0046"
        ),
    },
    ORACLE_RUNS[1]: {
        "arm64": (
            "23a47bb486c36372cb5e4ada2b4449d30c6f794053ff5e361bbab76cf55c0c25"
        ),
        "armhf": (
            "3d88e8e2fb0e7c9bf67a27aa61bb131168b4831419f4e2564daf7fee6768348b"
        ),
    },
    ORACLE_RUNS[2]: {
        "arm64": (
            "e49222a0cd221f82698d5d636f5a7fb5498b79f06b3bdc26fc067a5e4f97040d"
        ),
        "armhf": (
            "1c0a46864e6a5ebc62fdcfdc0c5660e169addec6d46e0d0bc04a515172821f0b"
        ),
    },
    ORACLE_RUNS[3]: {
        "arm64": (
            "f0ec4026680a142a5c89bd003844bf9a36766615810d1fbc22a84f1ce0417a77"
        ),
        "armhf": (
            "6269741487535ad7e0e3425ca218ca6a757e4701f6baf99f2608d10197a4474a"
        ),
    },
}
ORACLE_LOG_SHA256 = {
    "arm64": "f014ed09fbd7aa1101b7f41d0d972ce113e372374dc0646fe957a366d7208501",
    "armhf": "dc541fa28e8d159b7033ee4e6ad92d531b05885aa144247f8e67b33ad8695be9",
}
ORACLE_ARTIFACT = {
    "arm64": (
        "4a7190d3c4ea327cf342c5755dc05a72de4532d793a549a0dd302d416bf47392",
        3351104,
    ),
    "armhf": (
        "b84920d8c02e5fb7840e47e65679b57a5c935868b5a24ddfc0a4b8f18a65c2b1",
        2021140,
    ),
}
ORACLE_METADATA = (
    "64444beb8268d3a57d53a45564c55049f39ff621315401fef86e82f3849042d6",
    1794,
)
ORACLE_PACKAGE = (
    "b19288a7160aae8c206cd22004b167aa1f904add0ca3a4db3bc3aebadf79d2b7",
    986853,
)
SOURCE_LOCK_PATH = (
    ROOT
    / "pins/sources/mgba/6dce57eef127dc4cc292644f38196e0e7c58590c.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "399d95173036301ccfe95813a573ce93fd6ebb01759c8d16f95c2473410f3fe6"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "321827d0fd627b76cc95ee03e6ff8154b673e7957e63cdf5e5df5a56961cecec"
)
WORKFLOW_PATH = ROOT / ".github/workflows/build-mgba.yml"
WORKFLOW_FILE_SHA256 = (
    "9883cd92d67512dc8cc2a9d2564a91560595204e975b9fda5b51791a10882a26"
)
SOURCE_RECORD_IDENTITY = {
    "commit": "6dce57eef127dc4cc292644f38196e0e7c58590c",
    "requested_ref": "refs/heads/master",
    "resolved_commit": "6dce57eef127dc4cc292644f38196e0e7c58590c",
    "resolved_url": "https://github.com/libretro/mgba.git",
    "submodules": [],
    "tree": "72edb48f24f569f2b00c850cac61f6db0c80bf4e",
    "url": "https://github.com/libretro/mgba.git",
}

# These describe inputs, not runtime/device eligibility. All four BIOS files
# are optional and none is present in the reviewed package.
REVIEWED_LICENSE = "MPLv2.0"
OPTIONAL_FIRMWARE = (
    "gba_bios.bin",
    "gb_bios.bin",
    "gbc_bios.bin",
    "sgb_bios.bin",
)
COMMON_COMPILE_OPTIONS = (
    "-O3",
    "-fPIC",
    mgba.MGBA_NATIVE_GIT_VERSION_LOG_TOKEN,
    "-std=c99",
    "-D_GNU_SOURCE",
    "-DHAVE_LOCALE",
    "-DHAVE_STRNDUP",
    "-DHAVE_STRDUP",
    "-DDISABLE_THREADING",
    "-DMINIMAL_CORE=2",
    "-D__LIBRETRO__",
    "-DMINIMAL_CORE=2",
    "-DM_CORE_GBA",
    "-DM_CORE_GB",
    "-DENABLE_VFS",
    "-DENABLE_DIRECTORIES",
    "-DHAVE_STDINT_H",
    "-DHAVE_INTTYPES_H",
    "-DINLINE=inline",
    "-DCOLOR_16_BIT",
    "-DRESAMPLE_LIBRARY=2",
    "-DM_PI=3.14159265358979323846",
    "-DMGBA_STANDALONE",
    "-DPATH_MAX=4096",
    "-DSSIZE_MAX=2147483648",
    "-DNDEBUG",
    "-DHAVE_LOCALTIME_R",
    "-DCOLOR_5_6_5",
    "-DENABLE_VFS_FD",
    "-I./src",
    "-I./src/arm",
    "-I./include",
    "-I./src/platform/libretro",
)
COMPILERS = {
    "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
    "armhf": (
        "arm-a30-linux-gnueabihf-gcc",
        "arm-a30-linux-gnueabihf-g++",
    ),
}


def build_mgba_log_fixture(
    architecture: str, *, native_marker: bool = True
) -> str:
    """Build the reviewed argv/envelope without ignored local evidence."""

    c_compiler, cxx_compiler = COMPILERS[architecture]
    _c, _cxx, strip, make = mgba.MGBA_COMPILER_TOOLCHAINS[architecture]
    compile_lines = tuple(
        " ".join(
            (
                c_compiler,
                "-c",
                "-o",
                output,
                source,
                *COMMON_COMPILE_OPTIONS,
            )
        )
        for output, source in mgba.MGBA_EXPECTED_COMPILE_PAIRS
    )
    pipeline_markers = (
        (mgba.MGBA_NATIVE_VERSION_MARKER,) if native_marker else ()
    )
    return (
        "\n".join(
            (
                *mgba.MGBA_FETCH_PREFIX,
                *mgba.MGBA_SUCCESS_MARKER,
                mgba.MGBA_SOURCE_HEAD_MARKER,
                *pipeline_markers,
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
                "=== mGBA",
                "Building mgba...",
                'cd "/libretro-super/libretro-mgba"',
                f'{make} -f Makefile.libretro platform="unix" -j24  clean',
                mgba.MGBA_OBJECT_CLEAN_COMMAND,
                mgba.MGBA_ARTIFACT_CLEAN_COMMAND,
                f'{make} -f Makefile.libretro platform="unix" -j24 '
                f'CC="{c_compiler}" CXX="{cxx_compiler}" ',
                *compile_lines,
                *mgba.MGBA_EXPECTED_DIAGNOSTIC_LINES[architecture],
                " ".join(
                    mgba.MGBA_EXPECTED_ORDERED_LINK_ARGV[architecture]
                ),
                *mgba.MGBA_SUCCESS_TRAILER,
            )
        )
        + "\n"
    )


def hardened_spec() -> dict:
    identity = mgba.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return {
        "workflow": identity["workflow"],
        "source": {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
        },
        "build": {
            "driver": "libretro-super",
            "source_key": identity["source_key"],
            "source_dir": identity["source_dir"],
            "output_path": identity["output_path"],
            "artifact_name": identity["artifact_name"],
            "git_version": {
                "derivation": mgba.MGBA_NATIVE_GIT_VERSION_DERIVATION,
                "value": mgba.MGBA_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
        },
        "metadata": {
            "source_path": identity["metadata_source_path"],
            "artifact_name": identity["metadata_artifact_name"],
        },
        "targets": identity["targets"],
    }


class MgbaContractTests(unittest.TestCase):
    def contract_arguments(
        self, log: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = mgba.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            log,
            mgba.MGBA_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def assert_active_rejects(self, log: str, architecture: str) -> None:
        self.assertFalse(
            mgba.mgba_log_proves_contract(
                *self.contract_arguments(log, architecture)
            )
        )

    def test_exact_identity_spec_source_and_golden_predicates(self) -> None:
        spec = hardened_spec()
        identity = mgba.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertTrue(mgba.mgba_spec_is_well_formed(spec))
        self.assertEqual("mgba-c-only-v1", mgba.MGBA_LOG_CONTRACT_ID)
        self.assertEqual("core-arch-source", mgba.MGBA_LOG_PROOF_KIND)
        self.assertEqual("Makefile.libretro", identity["native_makefile"])
        self.assertEqual("c", identity["compiler_scope"])
        self.assertEqual(
            {
                "derivation": "native-space-short9-v1",
                "value": " 6dce57eef",
                "compiler_scope": "c",
            },
            spec["build"]["git_version"],
        )

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
            "source-ref": changed(("source", "requested_ref"), "main"),
            "source-commit": changed(("source", "commit"), "0" * 40),
            "source-tree": changed(("source", "tree"), "0" * 40),
            "driver": changed(("build", "driver"), "direct-make"),
            "source-key": changed(("build", "source_key"), "gpsp"),
            "source-dir": changed(("build", "source_dir"), "other"),
            "output": changed(("build", "output_path"), "other.so"),
            "artifact": changed(("build", "artifact_name"), "other.so"),
            "derivation": changed(
                ("build", "git_version", "derivation"),
                "native-space-short10-v1",
            ),
            "version": changed(
                ("build", "git_version", "value"), " 6dce57eef1"
            ),
            "scope": changed(
                ("build", "git_version", "compiler_scope"), "cxx"
            ),
            "metadata": changed(
                ("metadata", "artifact_name"), "other.info"
            ),
            "targets": changed(("targets",), ["arm64"]),
        }
        extra = copy.deepcopy(spec)
        extra["unexpected"] = True
        mutations["extra"] = extra
        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(mgba.mgba_spec_is_well_formed(mutation))

        source = copy.deepcopy(SOURCE_RECORD_IDENTITY)
        self.assertTrue(
            mgba.mgba_golden_source_is_well_formed(mgba.MGBA_CORE_ID, source)
        )
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": copy.deepcopy(spec["build"]["git_version"]),
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            mgba.mgba_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                mgba.MGBA_CORE_ID,
                source,
            )
        )
        for field, value in {
            "url": "https://example.com",
            "commit": "0" * 40,
            "tree": "0" * 40,
            "submodules": ["unexpected"],
        }.items():
            changed_source = copy.deepcopy(source)
            changed_source[field] = value
            with self.subTest(source_mutation=field):
                self.assertFalse(
                    mgba.mgba_golden_source_is_well_formed(
                        mgba.MGBA_CORE_ID, changed_source
                    )
                )
        changed_build = copy.deepcopy(build)
        changed_build["git_version"]["value"] = " 000000000"
        self.assertFalse(
            mgba.mgba_golden_build_contract_is_well_formed(
                changed_build,
                identity["source_commit"],
                mgba.MGBA_CORE_ID,
                source,
            )
        )

    def test_compile_link_clean_and_artifact_mutations_fail_closed(self) -> None:
        for architecture, (c_compiler, cxx_compiler) in COMPILERS.items():
            log = build_mgba_log_fixture(architecture)
            compile_lines = [
                line for line in log.splitlines() if " -c " in line
            ]
            first_compile, second_compile = compile_lines[:2]
            first_output, first_source = mgba.MGBA_EXPECTED_COMPILE_PAIRS[0]
            link_line = " ".join(
                mgba.MGBA_EXPECTED_ORDERED_LINK_ARGV[architecture]
            )
            first_object = mgba.MGBA_EXPECTED_RAW_LINK_OBJECTS[0]
            second_object = mgba.MGBA_EXPECTED_RAW_LINK_OBJECTS[1]
            object_overwrite = f"cp /tmp/unreviewed.o {first_object}\n"
            artifact_overwrite = (
                f"cp /tmp/unreviewed.so {mgba.MGBA_BUILD_ARTIFACT_NAME}\n"
            )
            mutations = {
                "missing-compile": log.replace(first_compile + "\n", "", 1),
                "duplicate-compile": log.replace(
                    first_compile + "\n",
                    first_compile + "\n" + first_compile + "\n",
                    1,
                ),
                "cxx-compile": log.replace(
                    first_compile,
                    first_compile.replace(c_compiler, cxx_compiler, 1),
                    1,
                ),
                "clang-compile": log.replace(
                    first_compile,
                    first_compile.replace(c_compiler, "clang", 1),
                    1,
                ),
                "ccache-wrapper": log.replace(
                    first_compile, "ccache " + first_compile, 1
                ),
                "response-file": log.replace(
                    first_compile,
                    first_compile + " @compile.rsp",
                    1,
                ),
                "malformed-quote": log.replace(
                    first_compile, c_compiler + " 'open", 1
                ),
                "wrong-output": log.replace(
                    first_compile,
                    first_compile.replace(first_output, "src/other.o", 1),
                    1,
                ),
                "wrong-source": log.replace(
                    first_compile,
                    first_compile.replace(first_source, "src/other.c", 1),
                    1,
                ),
                "attached-output": log.replace(
                    f" -o {first_output} ", f" -o{first_output} ", 1
                ),
                "wrong-option": log.replace(
                    first_compile,
                    first_compile.replace("-O3", "-O2", 1),
                    1,
                ),
                "missing-native-version": log.replace(
                    mgba.MGBA_NATIVE_GIT_VERSION_LOG_TOKEN + " ", "", 1
                ),
                "wrong-native-version": log.replace(
                    mgba.MGBA_NATIVE_GIT_VERSION_LOG_TOKEN,
                    r'-DGIT_VERSION=\"" 000000000"\"',
                    1,
                ),
                "duplicate-native-version": log.replace(
                    first_compile,
                    first_compile.replace(
                        "-std=c99",
                        mgba.MGBA_NATIVE_GIT_VERSION_LOG_TOKEN + " -std=c99",
                        1,
                    ),
                    1,
                ),
                "missing-link": log.replace(link_line + "\n", "", 1),
                "duplicate-link": log.replace(
                    link_line + "\n", link_line + "\n" + link_line + "\n", 1
                ),
                "cxx-link": log.replace(
                    link_line,
                    link_line.replace(c_compiler, cxx_compiler, 1),
                    1,
                ),
                "link-response-file": log.replace(
                    link_line, link_line + " @objects.rsp", 1
                ),
                "link-reordered-objects": log.replace(
                    f"{first_object} {second_object}",
                    f"{second_object} {first_object}",
                    1,
                ),
                "link-missing-object": log.replace(
                    link_line,
                    link_line.replace(first_object + " ", "", 1),
                    1,
                ),
                "wrong-link-option": log.replace(
                    link_line,
                    link_line.replace("-shared", "-static", 1),
                    1,
                ),
                "object-overwrite-before-clean": log.replace(
                    mgba.MGBA_OBJECT_CLEAN_COMMAND + "\n",
                    object_overwrite + mgba.MGBA_OBJECT_CLEAN_COMMAND + "\n",
                    1,
                ),
                "object-overwrite-before-link": log.replace(
                    link_line + "\n", object_overwrite + link_line + "\n", 1
                ),
                "artifact-overwrite-after-link": log.replace(
                    link_line + "\n",
                    link_line + "\n" + artifact_overwrite,
                    1,
                ),
                "artifact-touch": log.replace(
                    link_line + "\n",
                    f"touch {mgba.MGBA_BUILD_ARTIFACT_NAME}\n" + link_line + "\n",
                    1,
                ),
                "missing-object-clean": log.replace(
                    mgba.MGBA_OBJECT_CLEAN_COMMAND + "\n", "", 1
                ),
                "changed-object-clean": log.replace(
                    mgba.MGBA_OBJECT_CLEAN_COMMAND,
                    mgba.MGBA_OBJECT_CLEAN_COMMAND.replace(
                        first_object, "./other.o", 1
                    ),
                    1,
                ),
                "missing-artifact-clean": log.replace(
                    mgba.MGBA_ARTIFACT_CLEAN_COMMAND + "\n", "", 1
                ),
                "missing-copy": log.replace(
                    mgba.MGBA_COPY_COMMAND + "\n", "", 1
                ),
                "duplicate-copy": log.replace(
                    mgba.MGBA_COPY_COMMAND + "\n",
                    mgba.MGBA_COPY_COMMAND
                    + "\n"
                    + mgba.MGBA_COPY_COMMAND
                    + "\n",
                    1,
                ),
                "compile-after-link": log.replace(
                    second_compile + "\n", "", 1
                ).replace(
                    link_line + "\n",
                    link_line + "\n" + second_compile + "\n",
                    1,
                ),
            }
            for label, mutation in mutations.items():
                with self.subTest(architecture=architecture, mutation=label):
                    self.assert_active_rejects(mutation, architecture)

    def test_diagnostic_occurrence_and_zero_policy_fail_closed(self) -> None:
        arm64 = build_mgba_log_fixture("arm64")
        block = "\n".join(mgba.MGBA_ARM64_DIAGNOSTIC_LINES)
        link_line = " ".join(mgba.MGBA_EXPECTED_ORDERED_LINK_ARGV["arm64"])
        owner_line = next(
            line
            for line in arm64.splitlines()
            if " -c " in line and " src/util/vfs/vfs-fd.c " in line
        )
        mutations = {
            "missing-block": arm64.replace(block + "\n", "", 1),
            "duplicate-block": arm64.replace(
                block + "\n", block + "\n" + block + "\n", 1
            ),
            "changed-warning": arm64.replace(
                "[-Wunused-result]", "[-Wother]", 1
            ),
            "changed-context": arm64.replace(
                "In function '_vfdTruncate'", "In function 'other'", 1
            ),
            "before-owner": arm64.replace(block + "\n", "", 1).replace(
                owner_line + "\n", block + "\n" + owner_line + "\n", 1
            ),
            "after-link": arm64.replace(block + "\n", "", 1).replace(
                link_line + "\n", link_line + "\n" + block + "\n", 1
            ),
            "extra-warning": arm64.replace(
                link_line + "\n", "warning: synthetic\n" + link_line + "\n", 1
            ),
            "extra-note": arm64.replace(
                link_line + "\n", "note: synthetic\n" + link_line + "\n", 1
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(architecture="arm64", mutation=label):
                self.assert_active_rejects(mutation, "arm64")

        armhf = build_mgba_log_fixture("armhf")
        armhf_link = " ".join(
            mgba.MGBA_EXPECTED_ORDERED_LINK_ARGV["armhf"]
        )
        for label, mutation in {
            "arm64-block": armhf.replace(
                armhf_link + "\n", block + "\n" + armhf_link + "\n", 1
            ),
            "warning": armhf.replace(
                armhf_link + "\n",
                "warning: synthetic\n" + armhf_link + "\n",
                1,
            ),
            "note": armhf.replace(
                armhf_link + "\n", "note: synthetic\n" + armhf_link + "\n", 1
            ),
        }.items():
            with self.subTest(architecture="armhf", mutation=label):
                self.assert_active_rejects(mutation, "armhf")

    def test_identity_architecture_input_types_and_cross_core_reuse_fail(
        self,
    ) -> None:
        identity = mgba.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
        arm64 = build_mgba_log_fixture("arm64")
        mutations = (
            (
                "wrong-core",
                (
                    arm64,
                    "gpsp",
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ),
            (
                "wrong-commit",
                (
                    arm64,
                    mgba.MGBA_CORE_ID,
                    "arm64",
                    "0" * 40,
                    identity["source_tree"],
                ),
            ),
            (
                "wrong-tree",
                (
                    arm64,
                    mgba.MGBA_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    "0" * 40,
                ),
            ),
            (
                "unknown-architecture",
                (
                    arm64,
                    mgba.MGBA_CORE_ID,
                    "x86_64",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ),
            (
                "cross-architecture-log",
                (
                    arm64,
                    mgba.MGBA_CORE_ID,
                    "armhf",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ),
        )
        for label, arguments in mutations:
            with self.subTest(mutation=label):
                self.assertFalse(mgba.mgba_log_proves_contract(*arguments))
        self.assertFalse(
            mgba.mgba_log_proves_contract(
                None,  # type: ignore[arg-type]
                mgba.MGBA_CORE_ID,
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )


if __name__ == "__main__":
    unittest.main()
