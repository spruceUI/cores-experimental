"""Exact fMSX C-only native-version build contract."""

from __future__ import annotations

import re
import shlex

from .c_only import COnlyLogContract, c_only_log_proves_contract
from .command_line import ordered_command_argv_sha256, output_option
from .compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)


FMSX_CORE_ID = "fmsx"
FMSX_BUILD_ARTIFACT_NAME = "fmsx_libretro.so"
FMSX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
FMSX_NATIVE_GIT_VERSION = " f013e21"
FMSX_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" f013e21"\"'
FMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION=" f013e21"'
FMSX_SOURCE_HEAD_MARKER = (
    "HEAD is now at f013e21 Merge pull request #131 from jdeath/master"
)
FMSX_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" f013e21"|file'
)
FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-fmsx.yml",
    "source_url": "https://github.com/libretro/fmsx-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "f013e213458e06d9df718e4bc4b09d46f88aa899",
    "source_tree": "ae1b15cee162c073452cc9826b1e208d2250d2bf",
    "source_key": FMSX_CORE_ID,
    "source_dir": "libretro-fmsx",
    "output_path": "dist/unix/fmsx_libretro.so",
    "artifact_name": FMSX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/fmsx_libretro.info",
    "metadata_artifact_name": "fmsx_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
}

FMSX_EXPECTED_COMPILE_COUNT = 31
FMSX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "a1439ee1038cef8d0ba4e80989a4e8d149ccb6dc6257256b3e45f001a7416286"
)
FMSX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "f5e30ab376935c5cd6e952e4390451198c6c53674f24f6899d96982d58b63d59",
    "armhf": "48022dc7f8ddc706c0ee6a6b4f0adbff770348575aebb46e50d37f8ecdeac050",
}
FMSX_EXPECTED_LINK_OBJECT_SHA256 = (
    "6acaf4be9c83c81a78e315870e85fb622db139328777395611eb44fef07c4b6a"
)
FMSX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "af4895bbc360f6d34d4fd7abd11ab879736d3bacccddd402fa6a120fac2601ea"
)
FMSX_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
)
FMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "9c16578b2d7a5d7d469b7a1c29e239c93492d8b942aa32b893b1a730fb7e456e",
    "armhf": "db8b9abca71c6ff1067ee3b4687cc3d2a19ed1889741308ee4eabcedc69fcc1a",
}
FMSX_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
    "collect2: ld returned",
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
FMSX_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def fmsx_spec_is_well_formed(spec: object) -> bool:
    """Require fMSX's complete immutable catalog identity."""

    identity = FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": FMSX_NATIVE_GIT_VERSION_DERIVATION,
                    "value": FMSX_NATIVE_GIT_VERSION,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def fmsx_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed fMSX tree."""

    identity = FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == FMSX_CORE_ID
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


def fmsx_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted fMSX native-version build record."""

    identity = FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and fmsx_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": FMSX_NATIVE_GIT_VERSION_DERIVATION,
                "value": FMSX_NATIVE_GIT_VERSION,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


FMSX_LOG_CONTRACT = COnlyLogContract(
    core_id=FMSX_CORE_ID,
    expected_compile_count=FMSX_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=FMSX_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=FMSX_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=FMSX_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=FMSX_BUILD_ARTIFACT_NAME,
    expected_link_options=FMSX_EXPECTED_LINK_OPTIONS,
    source_commit=FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=FMSX_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def _fmsx_markers_are_exact(lines: list[str]) -> bool:
    observed = tuple(
        line
        for line in lines
        if line.startswith("HEAD is now at ")
        or line.startswith("CORE_PIPELINE_")
    )
    return observed == (FMSX_SOURCE_HEAD_MARKER, FMSX_NATIVE_VERSION_MARKER)


def _fmsx_compile_and_link_scope_is_exact(
    lines: list[str],
    arch: str,
) -> tuple[list[int], list[tuple[int, list[str]]]] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        return None
    expected_c_compilers = expected_compilers - expected_cxx_compilers
    compile_positions: list[int] = []
    link_commands: list[tuple[int, list[str]]] = []
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return None
        if not tokens or tokens[0] not in expected_compilers:
            continue
        if "-c" in tokens:
            compile_positions.append(line_number)
            if (
                tokens[0] not in expected_c_compilers
                or tokens.count("-w") != 0
                or [
                    token for token in tokens[1:] if "GIT_VERSION" in token
                ]
                != [FMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN]
            ):
                return None
            continue
        parsed_output = output_option(tokens)
        if (
            parsed_output is not None
            and parsed_output[0] == FMSX_BUILD_ARTIFACT_NAME
        ):
            link_commands.append((line_number, tokens))
    if (
        len(compile_positions) != FMSX_EXPECTED_COMPILE_COUNT
        or len(link_commands) != 1
    ):
        return None
    return compile_positions, link_commands


def fmsx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove fMSX's source, native version, C argv, link, and diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in FMSX_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or FMSX_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != FMSX_EXPECTED_COMPILE_COUNT
        or build_log_text.count(FMSX_NATIVE_GIT_VERSION_LOG_TOKEN)
        != FMSX_EXPECTED_COMPILE_COUNT
    ):
        return False
    lines = build_log_text.splitlines()
    if not _fmsx_markers_are_exact(lines):
        return False
    commands = _fmsx_compile_and_link_scope_is_exact(lines, arch)
    if commands is None:
        return False
    compile_positions, link_commands = commands
    link_position, link_tokens = link_commands[0]
    source_position = lines.index(FMSX_SOURCE_HEAD_MARKER)
    marker_position = lines.index(FMSX_NATIVE_VERSION_MARKER)
    if (
        not (
            source_position < marker_position < min(compile_positions)
            and max(compile_positions) < link_position
        )
        or ordered_command_argv_sha256(link_tokens)
        != FMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256.get(arch)
    ):
        return False
    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FMSX_LOG_CONTRACT,
    )
