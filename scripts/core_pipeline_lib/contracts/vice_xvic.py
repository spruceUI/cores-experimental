"""Exact VICE xvic native-short10 mixed-language build contract."""

from __future__ import annotations

import re
import shlex

from .command_line import output_option
from .compiler import TARGET_COMPILERS, line_may_name_target_compiler
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


VICE_XVIC_CORE_ID = "vice_xvic"
VICE_XVIC_BUILD_ARTIFACT_NAME = "vice_xvic_libretro.so"
VICE_XVIC_NATIVE_GIT_VERSION_DERIVATION = "native-space-short10-v1"
VICE_XVIC_NATIVE_GIT_VERSION = " 7946cfa0d3"
VICE_XVIC_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" 7946cfa0d3"\"'
)
VICE_XVIC_NATIVE_GIT_VERSION_COMPILE_TOKEN = (
    '-DGIT_VERSION=" 7946cfa0d3"'
)
VICE_XVIC_CORE_NAME_LOG_TOKEN = r'-DCORE_NAME=\"xvic\"'
VICE_XVIC_CORE_NAME_COMPILE_TOKEN = '-DCORE_NAME="xvic"'
VICE_XVIC_MACHINE_COMPILE_TOKEN = "-D__XVIC__"
VICE_XVIC_SOURCE_HEAD_MARKER = (
    "HEAD is now at 7946cfa0d3 Init FF override ratio properly"
)
VICE_XVIC_GIT_ABBREV_MARKER = (
    "CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV|command line:|10"
)
VICE_XVIC_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 7946cfa0d3"|file'
)
VICE_XVIC_CFLAGS_MARKER = (
    r'CFLAGS:  -O3 -DNDEBUG -Wno-format -Wno-format-security -DHAVE_7ZIP '
    r'-D_7ZIP_ST -DHAVE_CONFIG_H -MMD -D__LIBRETRO__ -DUSE_LIBRETRO_VFS '
    r'-DCORE_NAME=\"xvic\" -D__XVIC__ -DGIT_VERSION=\"" 7946cfa0d3"\"'
)
VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-vice_xvic.yml",
    "source_url": "https://github.com/libretro/vice-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "7946cfa0d3775e958616d4d107de867a4616ae6c",
    "source_tree": "db2760ffc97b9c20ef8777fcb7689082be66bc45",
    "source_key": VICE_XVIC_CORE_ID,
    "source_dir": "libretro-vice",
    "output_path": "dist/unix/vice_xvic_libretro.so",
    "artifact_name": VICE_XVIC_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/vice_xvic_libretro.info"
    ),
    "metadata_artifact_name": "vice_xvic_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
    "git_version_value": VICE_XVIC_NATIVE_GIT_VERSION,
    "source_date_epoch": 1780486798,
}

VICE_XVIC_SEMANTIC_PATH_ALIASES = (("build/./", ""),)
VICE_XVIC_EXPECTED_COMPILE_COUNT = 438
VICE_XVIC_EXPECTED_LANGUAGE_COUNTS = {"c": 428, "cxx": 10}
VICE_XVIC_EXPECTED_SOURCE_SUFFIX_COUNTS = {
    ".c": 428,
    ".cc": 10,
}
VICE_XVIC_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e83044294f09dbc1aaf858a3dc79cfd202f02cb4465146fd24c5caa1108a7eb6"
)
VICE_XVIC_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "292ba3764442b7242d8a374775c3a36a6ad12e9102208b9dd2c4a95781a1ec68",
    "armhf": "4126cf021ba5507bcf829d8dc8226ce699a7fb5157db7160d280cd3488e796eb",
}
VICE_XVIC_EXPECTED_LINK_OBJECT_SHA256 = (
    "ba25b56627c06226dbc1cbe06c2b19025312b3e450aceb06b139ead6c78d47e3"
)
VICE_XVIC_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "a2053f4152a1387ca4526e9a7ac84f04b41d9c7e5f904a84a43eb0054c61a078"
)
VICE_XVIC_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=./libretro/link.T",
    "-Wl,--gc-sections",
    "-s",
    "-lm",
    "-fPIC",
)
VICE_XVIC_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "567c6b9c31dee696a46ed842fd332aa52e3b5ac271d571adea74811236b1374a",
    "armhf": "62687d4bd1a0a0e081430fa481706487103de44ae548e1c57079159ab51c235e",
}
VICE_XVIC_EXPECTED_DIAGNOSTIC_LINES_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
VICE_XVIC_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
VICE_XVIC_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def vice_xvic_spec_is_well_formed(spec: object) -> bool:
    """Require VICE xvic's complete immutable catalog identity."""

    identity = VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "source_date_epoch": identity["source_date_epoch"],
                "git_version": {
                    "derivation": VICE_XVIC_NATIVE_GIT_VERSION_DERIVATION,
                    "value": VICE_XVIC_NATIVE_GIT_VERSION,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def vice_xvic_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed VICE xvic tree."""

    identity = VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == VICE_XVIC_CORE_ID
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


def vice_xvic_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted VICE xvic native-short10 build record."""

    identity = VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and vice_xvic_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": VICE_XVIC_NATIVE_GIT_VERSION_DERIVATION,
                "value": VICE_XVIC_NATIVE_GIT_VERSION,
            },
            "source_date_epoch": identity["source_date_epoch"],
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


VICE_XVIC_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=VICE_XVIC_CORE_ID,
    expected_compile_count=VICE_XVIC_EXPECTED_COMPILE_COUNT,
    expected_language_counts=VICE_XVIC_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=VICE_XVIC_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        VICE_XVIC_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=VICE_XVIC_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        VICE_XVIC_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=VICE_XVIC_BUILD_ARTIFACT_NAME,
    expected_link_options=VICE_XVIC_EXPECTED_LINK_OPTIONS,
    source_commit=VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    semantic_path_aliases=VICE_XVIC_SEMANTIC_PATH_ALIASES,
    expected_ordered_link_argv_sha256=(
        VICE_XVIC_EXPECTED_ORDERED_LINK_ARGV_SHA256
    ),
)


def _vice_xvic_markers_are_exact(lines: list[str]) -> bool:
    observed = tuple(
        line
        for line in lines
        if line.startswith("HEAD is now at ")
        or line.startswith("CORE_PIPELINE_")
    )
    return observed == (
        VICE_XVIC_SOURCE_HEAD_MARKER,
        VICE_XVIC_GIT_ABBREV_MARKER,
        VICE_XVIC_NATIVE_VERSION_MARKER,
    )


def _vice_xvic_compile_and_link_scope_is_exact(
    lines: list[str],
    arch: str,
) -> tuple[list[int], list[tuple[int, list[str]]]] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    if expected_compilers is None:
        return None
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
                [token for token in tokens[1:] if "GIT_VERSION" in token]
                != [VICE_XVIC_NATIVE_GIT_VERSION_COMPILE_TOKEN]
                or [token for token in tokens[1:] if "CORE_NAME" in token]
                != [VICE_XVIC_CORE_NAME_COMPILE_TOKEN]
                or tokens.count(VICE_XVIC_MACHINE_COMPILE_TOKEN) != 1
            ):
                return None
            continue
        parsed_output = output_option(tokens)
        if (
            parsed_output is not None
            and parsed_output[0] == VICE_XVIC_BUILD_ARTIFACT_NAME
        ):
            link_commands.append((line_number, tokens))
    if (
        len(compile_positions) != VICE_XVIC_EXPECTED_COMPILE_COUNT
        or len(link_commands) != 1
    ):
        return None
    return compile_positions, link_commands


def vice_xvic_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove xvic's source, short10 version, compile, link, and diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in VICE_XVIC_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or VICE_XVIC_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != VICE_XVIC_EXPECTED_COMPILE_COUNT + 1
        or build_log_text.count(VICE_XVIC_NATIVE_GIT_VERSION_LOG_TOKEN)
        != VICE_XVIC_EXPECTED_COMPILE_COUNT + 1
        or build_log_text.count("-DCORE_NAME=")
        != VICE_XVIC_EXPECTED_COMPILE_COUNT + 1
        or build_log_text.count(VICE_XVIC_CORE_NAME_LOG_TOKEN)
        != VICE_XVIC_EXPECTED_COMPILE_COUNT + 1
        or build_log_text.count(VICE_XVIC_MACHINE_COMPILE_TOKEN)
        != VICE_XVIC_EXPECTED_COMPILE_COUNT + 1
    ):
        return False
    lines = build_log_text.splitlines()
    cflags_lines = tuple(line for line in lines if line.startswith("CFLAGS:"))
    if (
        not _vice_xvic_markers_are_exact(lines)
        or cflags_lines != (VICE_XVIC_CFLAGS_MARKER,)
    ):
        return False
    commands = _vice_xvic_compile_and_link_scope_is_exact(lines, arch)
    if commands is None:
        return False
    compile_positions, link_commands = commands
    source_position = lines.index(VICE_XVIC_SOURCE_HEAD_MARKER)
    config_position = lines.index(VICE_XVIC_GIT_ABBREV_MARKER)
    version_position = lines.index(VICE_XVIC_NATIVE_VERSION_MARKER)
    link_position = link_commands[0][0]
    if not (
        source_position < config_position < version_position
        and version_position < min(compile_positions)
        and max(compile_positions) < link_position
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        VICE_XVIC_LOG_CONTRACT,
    )
