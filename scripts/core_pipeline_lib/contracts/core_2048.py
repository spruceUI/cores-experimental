"""Exact 2048 native-version C-only compile/link contract.

2048 uses the shared C-only compile/link proof standard for exact, permutation-
tolerant compile argv and object closure. Its core-owned wrapper additionally
requires the reviewed native-version marker, a gap-free compile/link command
envelope, and a zero-diagnostic whole log.
"""

from __future__ import annotations

import re
import shlex

from .c_only import (
    COnlyLogContract,
    c_only_compile_invocation,
    c_only_link_command,
    c_only_log_proves_contract,
)
from .compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)


CORE_2048_ID = "2048"
CORE_2048_BUILD_ARTIFACT_NAME = "2048_libretro.so"
CORE_2048_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
CORE_2048_NATIVE_GIT_VERSION = " c90437d"
CORE_2048_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" c90437d"\"'
CORE_2048_NATIVE_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION=" c90437d"'
CORE_2048_SOURCE_HEAD_MARKER = (
    "HEAD is now at c90437d Allow continuing after 2048 (#67)"
)
CORE_2048_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" c90437d"|file'
)
CORE_2048_EXPECTED_COMPILE_COUNT = 16
CORE_2048_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e15afefc64cd06e9f26d68a5124270e88c6a886782cd930bf9a94d16ce83fb36"
)
CORE_2048_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "47328d3e04439be146af20f6fe9db46b85387ef4aeb6f1e90a8cc207e662d9ff",
    "armhf": "40e09b77580589538c16430ada74f2e526895834fea85966fed63656e9943b8f",
}
CORE_2048_EXPECTED_RAW_COMPILE_INVOCATION_SHA256 = {
    "arm64": "391b0df4a11cb917bd9e02be9c8c4460f9f53b274dc047a7ed58b44c8459912e",
    "armhf": "3f841c0450dea0776409083908bc313ff509cc9e73a970af5ff4f5736f5bfa6f",
}
CORE_2048_EXPECTED_LINK_OBJECT_SHA256 = (
    "929bbb72e9485d363a68b41714900cae8bfacfd6304975a12fb197fcf13ee23a"
)
CORE_2048_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "eebfd7e37326a10874071276455b84ecec1f506368ea3b9346953e3fb719e1ab"
)
CORE_2048_EXPECTED_LINK_INVOCATION_SHA256 = {
    "arm64": "0a696df6120dcc26bf56aa62755d309126b8eee6391acdf1763859147a7b6baa",
    "armhf": "fca378fe494bdddf531e4c5ce32d2cfe6514c6d704125f2a0a20ad8b41f282a9",
}
CORE_2048_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-lm",
)
CORE_2048_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{CORE_2048_ID}",
)
CORE_2048_SUCCESS_TRAILER = (
    'cp "2048_libretro.so" "/libretro-super/dist/unix/2048_libretro.so"',
    *CORE_2048_SUCCESS_MARKER,
)
CORE_2048_FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "warning:",
    "error:",
    "fatal:",
    "note:",
    "undefined reference",
    "dubious ownership",
    "cannot find",
    "no such file or directory",
    "internal compiler error",
    "permission denied",
    "command not found",
    "collect2:",
    "linker command failed",
    "compilation terminated",
    "file format not recognized",
    "segmentation fault",
    "core dumped",
    "killed",
    "aborted",
    "terminated",
    "bus error",
    "illegal instruction",
    "broken pipe",
    "floating point exception",
)
CORE_2048_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
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
        expected_link_invocation_sha256=(
            CORE_2048_EXPECTED_LINK_INVOCATION_SHA256
        ),
        expected_raw_compile_invocation_sha256=(
            CORE_2048_EXPECTED_RAW_COMPILE_INVOCATION_SHA256
        ),
    )


def _core_2048_compile_and_link_scope_is_exact(
    lines: list[str],
    arch: str,
    contract: COnlyLogContract,
) -> tuple[list[int], int] | None:
    """Locate the sole exact 2048 compile set and link command."""

    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        return None
    expected_c_compilers = expected_compilers - expected_cxx_compilers
    compile_positions: list[int] = []
    link_positions: list[int] = []
    for position, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return None
        if not tokens or tokens[0] not in expected_c_compilers:
            continue
        if "-c" in tokens:
            if (
                c_only_compile_invocation(
                    tokens,
                    expected_c_compilers,
                    contract.semantic_path_aliases,
                    contract.sha_pinned_object_names,
                )
                is not None
            ):
                compile_positions.append(position)
            continue
        if (
            c_only_link_command(tokens, expected_c_compilers, contract)
            is not None
        ):
            link_positions.append(position)
    if (
        len(compile_positions) != CORE_2048_EXPECTED_COMPILE_COUNT
        or len(link_positions) != 1
    ):
        return None
    return compile_positions, link_positions[0]


def _sequence_positions(
    lines: list[str], sequence: tuple[str, ...]
) -> tuple[int, ...]:
    """Return every start position of an exact contiguous line sequence."""

    width = len(sequence)
    return tuple(
        position
        for position in range(len(lines) - width + 1)
        if tuple(lines[position : position + width]) == sequence
    )


def _core_2048_log_envelope_is_exact(
    lines: list[str],
    arch: str,
    contract: COnlyLogContract,
) -> bool:
    """Bind exact framing and a gap-free compile-through-link span."""

    source_markers = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    native_version_markers = tuple(
        line
        for line in lines
        if line.startswith(
            (
                "CORE_PIPELINE_NATIVE_GIT_VERSION",
                "CORE_PIPELINE_GIT_VERSION",
            )
        )
    )
    success_positions = _sequence_positions(lines, CORE_2048_SUCCESS_MARKER)
    if (
        source_markers != (CORE_2048_SOURCE_HEAD_MARKER,)
        or native_version_markers != (CORE_2048_NATIVE_VERSION_MARKER,)
        or len(success_positions) != 2
        or lines.count(CORE_2048_SUCCESS_MARKER[0]) != 2
        or lines.count(CORE_2048_SUCCESS_MARKER[1]) != 2
        or tuple(lines[-len(CORE_2048_SUCCESS_TRAILER) :])
        != CORE_2048_SUCCESS_TRAILER
        or lines.count(CORE_2048_SUCCESS_TRAILER[0]) != 1
    ):
        return False
    commands = _core_2048_compile_and_link_scope_is_exact(
        lines, arch, contract
    )
    if commands is None:
        return False
    compile_positions, link_position = commands
    source_position = lines.index(CORE_2048_SOURCE_HEAD_MARKER)
    marker_position = lines.index(CORE_2048_NATIVE_VERSION_MARKER)
    copy_position = len(lines) - len(CORE_2048_SUCCESS_TRAILER)
    command_positions = tuple(sorted((*compile_positions, link_position)))
    return bool(
        success_positions[0]
        < source_position
        < marker_position
        < min(compile_positions)
        and max(compile_positions) < link_position < copy_position
        and command_positions
        == tuple(range(min(compile_positions), link_position + 1))
    )


def core_2048_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove 2048's exact zero-diagnostic C build envelope."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in CORE_2048_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or CORE_2048_MAKE_FAILURE_RE.search(build_log_text) is not None
        or build_log_text.count("-DGIT_VERSION=")
        != CORE_2048_EXPECTED_COMPILE_COUNT
        or build_log_text.count(CORE_2048_NATIVE_GIT_VERSION_LOG_TOKEN)
        != CORE_2048_EXPECTED_COMPILE_COUNT
    ):
        return False
    lines = build_log_text.splitlines()
    contract = core_2048_c_only_contract()
    return bool(
        _core_2048_log_envelope_is_exact(lines, arch, contract)
        and c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            contract,
        )
    )
