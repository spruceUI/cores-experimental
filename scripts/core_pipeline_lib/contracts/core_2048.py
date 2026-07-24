"""Exact 2048 native-version C-only compile/link contract.

2048 uses the shared C-only compile/link proof standard: the reviewed compile
and link commands are proven exactly via ``c_only_log_proves_contract`` (which
sorts compile invocations, so parallel-interleaved build logs are accepted).
Its promoted source/build records are still bound through the golden helpers
below; the former full-log-envelope proof was dropped in favour of the shared
standard.
"""

from __future__ import annotations

import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


CORE_2048_ID = "2048"
CORE_2048_BUILD_ARTIFACT_NAME = "2048_libretro.so"
CORE_2048_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
CORE_2048_NATIVE_GIT_VERSION = " c90437d"
CORE_2048_EXPECTED_COMPILE_COUNT = 16
CORE_2048_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e15afefc64cd06e9f26d68a5124270e88c6a886782cd930bf9a94d16ce83fb36"
)
CORE_2048_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "47328d3e04439be146af20f6fe9db46b85387ef4aeb6f1e90a8cc207e662d9ff",
    "armhf": "40e09b77580589538c16430ada74f2e526895834fea85966fed63656e9943b8f",
}
CORE_2048_EXPECTED_LINK_OBJECT_SHA256 = (
    "929bbb72e9485d363a68b41714900cae8bfacfd6304975a12fb197fcf13ee23a"
)
CORE_2048_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "eebfd7e37326a10874071276455b84ecec1f506368ea3b9346953e3fb719e1ab"
)
CORE_2048_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-lm",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-2048.yml",
    "source_url": "https://github.com/libretro/libretro-2048.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "c90437d3c3913999624deca3fb55ecfa632b72c4",
    "source_tree": "5b8bcab69dc90185f10356b5780bf9d827684474",
    "source_key": CORE_2048_ID,
    "source_dir": "libretro-2048",
    "output_path": "dist/unix/2048_libretro.so",
    "artifact_name": CORE_2048_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/2048_libretro.info",
    "metadata_artifact_name": "2048_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile.libretro",
    "compiler_scope": "c",
}


def core_2048_spec_is_well_formed(spec: object) -> bool:
    """Require 2048's complete immutable catalog identity."""

    identity = CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(spec, dict)
        and spec
        == {
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
                    "derivation": CORE_2048_NATIVE_GIT_VERSION_DERIVATION,
                    "value": CORE_2048_NATIVE_GIT_VERSION,
                    "compiler_scope": "c",
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def core_2048_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed 2048 tree."""

    identity = CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == CORE_2048_ID
        and isinstance(source, dict)
        and source
        == {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
    )


def core_2048_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted 2048 native-version build record."""

    identity = CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and core_2048_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": CORE_2048_NATIVE_GIT_VERSION_DERIVATION,
                "value": CORE_2048_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def core_2048_c_only_contract() -> COnlyLogContract:
    """Return 2048's exact compile/link proof parameters."""

    return COnlyLogContract(
        core_id=CORE_2048_ID,
        expected_compile_count=CORE_2048_EXPECTED_COMPILE_COUNT,
        expected_compile_pair_sha256=CORE_2048_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            CORE_2048_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=CORE_2048_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=CORE_2048_BUILD_ARTIFACT_NAME,
        expected_link_options=CORE_2048_EXPECTED_LINK_OPTIONS,
        source_commit=CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        expected_raw_link_object_sha256=(
            CORE_2048_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
    )


def core_2048_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove 2048's exact compile and link commands for one architecture."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        core_2048_c_only_contract(),
    )
