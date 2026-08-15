"""Exact Gambatte zero-diagnostic mixed-language build-log contract.

The neutral mixed-language proof pins the exact 31 C++ and 16 C compile
invocations plus the final link.  This core-owned wrapper additionally binds
the reviewed source/native-version markers, a gap-free compile-through-link
envelope, the successful lifecycle trailer, and a zero-diagnostic whole log.
"""

from __future__ import annotations

import re
import shlex

from ..foundation import sha256_bytes
from .compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_compile_invocation,
    mixed_language_link_command,
    mixed_language_log_proves_contract,
)


GAMBATTE_CORE_ID = "gambatte"
GAMBATTE_EXPECTED_COMPILE_COUNT = 47
GAMBATTE_EXPECTED_LANGUAGE_COUNTS = {"c": 16, "cxx": 31}
GAMBATTE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "41da9360e228fcf28b2f063e5e72f48b22d6bfce3dd4844d7439ababc0db2e87"
)
GAMBATTE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "aa39c9d63b45dc2c0e71b207864c3ec37ccf9249fa48492302763dd0c74650ed",
    "armhf": "afa4a906c570592ceed13db5ed41f0380be0e13fc5a206df19336b6fbfbbc3d8",
}
GAMBATTE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256 = {
    "arm64": "d72b78d26965711fb619c81df0668b70f2f2dfafce982f149a289b92336c9541",
    "armhf": "f50b98f57432c00883e693efa08d5645cc1296de23cd4385208771cf986e8159",
}
GAMBATTE_EXPECTED_LINK_OBJECT_SHA256 = (
    "3ff42dabb0b5e12d27e31d852fb27e43e2a308d00a2fc030a27b1f4645e8c7d8"
)
GAMBATTE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9cd855ee762f60b71d8f5468292ec91e255cb2dbe83f10613ea6c2e64abdc600"
)
GAMBATTE_BUILD_ARTIFACT_NAME = "gambatte_libretro.so"
GAMBATTE_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,-version-script=libgambatte/libretro/link.T",
)
GAMBATTE_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "226d915d5b00da52bc14b76b0e38fc4ab5bbf7fef01538f2bc4253cca15000c5",
    "armhf": "d29b343ea737fcc0894b0db493a6a5597063b03bb74f588d4f166a1387842cd9",
}
GAMBATTE_NATIVE_GIT_VERSION = " dfc1655"
GAMBATTE_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" dfc1655"\"'
)
GAMBATTE_SOURCE_HEAD_MARKER = (
    "HEAD is now at dfc1655 Fetch translations & Recreate "
    "libretro_core_options_intl.h"
)
GAMBATTE_FETCH_PREFIX = (
    "PLATFORM: Linux",
    "ARCHITECTURE: x86_64",
    "TARGET: unix",
    "=== Gambatte",
    "Fetching gambatte...",
    'git clone "https://github.com/libretro/gambatte-libretro.git" '
    '"/libretro-super/libretro-gambatte"',
    "Cloning into '/libretro-super/libretro-gambatte'...",
)
GAMBATTE_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{GAMBATTE_CORE_ID}",
)
GAMBATTE_COPY_COMMAND = (
    'cp "gambatte_libretro.so" '
    '"/libretro-super/dist/unix/gambatte_libretro.so"'
)
GAMBATTE_SUCCESS_TRAILER = (
    GAMBATTE_COPY_COMMAND,
    *GAMBATTE_SUCCESS_MARKER,
)
GAMBATTE_FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "warning:",
    "note:",
    "error:",
    "fatal:",
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
GAMBATTE_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
GAMBATTE_JOBS_MARKER_RE = re.compile(
    r"^CORE_PIPELINE_JOBS\|([1-9][0-9]*)$"
)
GAMBATTE_CLEAN_COMMAND_SHA256 = (
    "9c52b01382be48d4286b7677a1603523fbcd760cf85bcb251fa86fa9b9b926f2"
)
GAMBATTE_COMPILER_TOOLCHAINS = {
    "arm64": (
        "aarch64-linux-gnu-gcc",
        "aarch64-linux-gnu-g++",
        "aarch64-linux-gnu-strip",
        "make",
    ),
    "armhf": (
        "arm-a30-linux-gnueabihf-gcc",
        "arm-a30-linux-gnueabihf-g++",
        "arm-a30-linux-gnueabihf-strip",
        "gmake",
    ),
}
GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gambatte.yml",
    "source_url": "https://github.com/libretro/gambatte-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "dfc165599f3f1068c40a0b7ad6fe5f161283d483",
    "source_tree": "5ca06b386819d5a99f83531d38d88d1d04db426c",
    "source_key": GAMBATTE_CORE_ID,
    "source_dir": "libretro-gambatte",
    "output_path": "dist/unix/gambatte_libretro.so",
    "artifact_name": GAMBATTE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/gambatte_libretro.info",
    "metadata_artifact_name": "gambatte_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "cxx",
    "native_makefile": "Makefile.libretro",
}
GAMBATTE_SEMANTIC_PATH_ALIASES = (
    ("libgambatte/src/../libretro/", "libgambatte/libretro/"),
    (
        "libgambatte/src/../libretro-common/",
        "libgambatte/libretro-common/",
    ),
)


def _native_version_markers(short_commit: str) -> tuple[str, ...]:
    return (
        "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
        f'" {short_commit}"|command-scoped-makeflags',
        "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
        f'-- GIT_VERSION="\\ {short_commit}"',
        "CORE_PIPELINE_NATIVE_GIT_VERSION|"
        f'" {short_commit}"|command line',
    )


GAMBATTE_NATIVE_VERSION_MARKERS = _native_version_markers("dfc1655")


def _post_marker_build_prefix(arch: str) -> tuple[str, ...] | None:
    toolchain = GAMBATTE_COMPILER_TOOLCHAINS.get(arch)
    if toolchain is None:
        return None
    c_compiler, cxx_compiler, strip, _make = toolchain
    return (
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
        "=== Gambatte",
        "Building gambatte...",
        'cd "/libretro-super/libretro-gambatte"',
    )


def gambatte_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Gambatte's exact proof parameters from its owned constants."""

    return MixedLanguageLogContract(
        core_id=GAMBATTE_CORE_ID,
        expected_compile_count=GAMBATTE_EXPECTED_COMPILE_COUNT,
        expected_language_counts=GAMBATTE_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=GAMBATTE_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            GAMBATTE_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=GAMBATTE_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            GAMBATTE_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=GAMBATTE_BUILD_ARTIFACT_NAME,
        expected_link_options=GAMBATTE_EXPECTED_LINK_OPTIONS,
        source_commit=(
            GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
        ),
        source_tree=GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        semantic_path_aliases=GAMBATTE_SEMANTIC_PATH_ALIASES,
        expected_ordered_link_argv_sha256=(
            GAMBATTE_EXPECTED_ORDERED_LINK_ARGV_SHA256
        ),
        expected_raw_compile_invocation_sha256=(
            GAMBATTE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256
        ),
    )


def _sequence_positions(
    lines: list[str], sequence: tuple[str, ...]
) -> tuple[int, ...]:
    width = len(sequence)
    return tuple(
        position
        for position in range(len(lines) - width + 1)
        if tuple(lines[position : position + width]) == sequence
    )


def _compile_and_link_scope_is_exact(
    lines: list[str],
    arch: str,
    contract: MixedLanguageLogContract,
) -> tuple[tuple[int, ...], int] | None:
    """Locate the sole exact 47-compile/one-link Gambatte command set."""

    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        return None
    compile_positions: list[int] = []
    link_positions: list[int] = []
    for position, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return None
        if not tokens or tokens[0] not in expected_compilers:
            continue
        if "-c" in tokens:
            if (
                mixed_language_compile_invocation(
                    tokens,
                    expected_compilers,
                    expected_cxx_compilers,
                    contract.semantic_path_aliases,
                    contract.cxx_compiler_compiles_c,
                    contract.sha_pinned_object_names,
                )
                is not None
            ):
                compile_positions.append(position)
            continue
        if (
            mixed_language_link_command(
                tokens, expected_cxx_compilers, contract
            )
            is not None
        ):
            link_positions.append(position)
    if (
        len(compile_positions) != GAMBATTE_EXPECTED_COMPILE_COUNT
        or len(link_positions) != 1
    ):
        return None
    return tuple(compile_positions), link_positions[0]


def _log_envelope_is_exact(
    lines: list[str], arch: str, contract: MixedLanguageLogContract
) -> bool:
    """Bind source/version framing and a gap-free compile/link envelope."""

    jobs_markers = tuple(
        (position, line)
        for position, line in enumerate(lines)
        if line.startswith("CORE_PIPELINE_JOBS|")
    )
    marker_jobs: str | None = None
    if jobs_markers:
        if len(jobs_markers) != 1 or jobs_markers[0][0] != 0:
            return False
        jobs_match = GAMBATTE_JOBS_MARKER_RE.fullmatch(jobs_markers[0][1])
        if jobs_match is None:
            return False
        marker_jobs = jobs_match.group(1)
        lines = lines[1:]
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
    success_positions = _sequence_positions(lines, GAMBATTE_SUCCESS_MARKER)
    fetch_positions = _sequence_positions(lines, GAMBATTE_FETCH_PREFIX)
    post_marker_prefix = _post_marker_build_prefix(arch)
    if (
        source_markers != (GAMBATTE_SOURCE_HEAD_MARKER,)
        or native_version_markers != GAMBATTE_NATIVE_VERSION_MARKERS
        or fetch_positions != (0,)
        or len(success_positions) != 2
        or lines.count(GAMBATTE_SUCCESS_MARKER[0]) != 2
        or lines.count(GAMBATTE_SUCCESS_MARKER[1]) != 2
        or tuple(lines[-len(GAMBATTE_SUCCESS_TRAILER) :])
        != GAMBATTE_SUCCESS_TRAILER
        or lines.count(GAMBATTE_COPY_COMMAND) != 1
        or post_marker_prefix is None
    ):
        return False
    commands = _compile_and_link_scope_is_exact(lines, arch, contract)
    if commands is None:
        return False
    compile_positions, link_position = commands
    source_position = lines.index(GAMBATTE_SOURCE_HEAD_MARKER)
    marker_positions = tuple(
        lines.index(marker) for marker in GAMBATTE_NATIVE_VERSION_MARKERS
    )
    copy_position = len(lines) - len(GAMBATTE_SUCCESS_TRAILER)
    command_positions = tuple(sorted((*compile_positions, link_position)))
    clean_invocation_position = marker_positions[-1] + 1 + len(
        post_marker_prefix
    )
    clean_command_position = clean_invocation_position + 1
    build_invocation_position = clean_command_position + 1
    c_compiler, cxx_compiler, _strip, make = GAMBATTE_COMPILER_TOOLCHAINS[
        arch
    ]
    clean_match: re.Match[str] | None = None
    if clean_invocation_position < len(lines):
        clean_match = re.fullmatch(
            re.escape(f'{make} -f Makefile.libretro platform="unix" -j')
            + r"([1-9][0-9]*)  clean",
            lines[clean_invocation_position],
        )
    jobs = clean_match.group(1) if clean_match is not None else None
    expected_build_invocation = (
        f'{make} -f Makefile.libretro platform="unix" -j{jobs} '
        f'CC="{c_compiler}" CXX="{cxx_compiler}" '
        if jobs is not None
        else None
    )
    return bool(
        fetch_positions[0] + len(GAMBATTE_FETCH_PREFIX)
        == success_positions[0]
        and success_positions[0] + len(GAMBATTE_SUCCESS_MARKER)
        == source_position
        and marker_positions
        == tuple(
            range(
                source_position + 1,
                source_position + 1 + len(GAMBATTE_NATIVE_VERSION_MARKERS),
            )
        )
        and tuple(
            lines[
                marker_positions[-1] + 1 : clean_invocation_position
            ]
        )
        == post_marker_prefix
        and clean_match is not None
        and (marker_jobs is None or marker_jobs == jobs)
        and clean_command_position < len(lines)
        and lines[clean_command_position].startswith("rm -f ")
        and sha256_bytes(lines[clean_command_position].encode("utf-8"))
        == GAMBATTE_CLEAN_COMMAND_SHA256
        and build_invocation_position < len(lines)
        and expected_build_invocation is not None
        and lines[build_invocation_position] == expected_build_invocation
        and min(compile_positions) == build_invocation_position + 1
        and max(compile_positions) < link_position < copy_position
        and command_positions
        == tuple(range(min(compile_positions), link_position + 1))
        and link_position + 1 == copy_position
    )


def gambatte_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Gambatte's exact zero-diagnostic build envelope."""

    if not isinstance(build_log_text, str):
        return False
    if (
        not isinstance(arch, str)
        or arch not in TARGET_COMPILERS
        or arch not in TARGET_CXX_COMPILERS
    ):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in GAMBATTE_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or GAMBATTE_MAKE_FAILURE_RE.search(build_log_text) is not None
        or build_log_text.count("-DGIT_VERSION=")
        != GAMBATTE_EXPECTED_LANGUAGE_COUNTS["cxx"]
        or build_log_text.count(GAMBATTE_NATIVE_GIT_VERSION_LOG_TOKEN)
        != GAMBATTE_EXPECTED_LANGUAGE_COUNTS["cxx"]
    ):
        return False
    contract = gambatte_mixed_language_contract()
    return bool(
        mixed_language_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            contract,
        )
        and _log_envelope_is_exact(build_log_text.splitlines(), arch, contract)
    )
