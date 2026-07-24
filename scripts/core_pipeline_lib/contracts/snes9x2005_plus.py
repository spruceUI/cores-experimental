"""Exact Snes9x 2005 Plus C-only native-version build contract."""

from __future__ import annotations

from collections import Counter
import re
import shlex

from ..errors import PipelineError
from .c_only import COnlyLogContract, c_only_log_proves_contract
from .command_line import ordered_command_argv_sha256, output_option
from .compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from .snes9x2005_common import native_git_version_spec_is_well_formed
from .log_checks import lines_sha256 as _lines_sha256, multiset_lines_sha256 as _multiset_lines_sha256


SNES9X2005_PLUS_CORE_ID = "snes9x2005_plus"
SNES9X2005_PLUS_BUILD_ARTIFACT_NAME = "snes9x2005_plus_libretro.so"
SNES9X2005_PLUS_MAKE_VARIABLES = {"USE_BLARGG_APU": 1}
SNES9X2005_PLUS_MAKE_PROFILE = "snes9x2005-plus-v1"
SNES9X2005_PLUS_NATIVE_GIT_VERSION = " b603569"
SNES9X2005_PLUS_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" b603569"\"'
)
SNES9X2005_PLUS_NATIVE_GIT_VERSION_COMPILE_TOKEN = (
    '-DGIT_VERSION=" b603569"'
)
SNES9X2005_PLUS_APU_COMPILE_TOKEN = "-DUSE_BLARGG_APU"
SNES9X2005_PLUS_SOURCE_HEAD_MARKER = (
    "HEAD is now at b603569 Merge pull request #103 from cscd98/webos-ci"
)
SNES9X2005_PLUS_MAKEFLAGS_MARKER = (
    "CORE_PIPELINE_MAKEFLAGS|USE_BLARGG_APU=1"
)
SNES9X2005_PLUS_MAKE_VARIABLE_MARKER = (
    "CORE_PIPELINE_MAKE_VARIABLE|USE_BLARGG_APU|1|command line"
)
SNES9X2005_PLUS_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" b603569"|file'
)
SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "source_url": "https://github.com/libretro/snes9x2005.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "b60356971fc9caae02cd0853676dced886a08be7",
    "source_tree": "5a13440308796f67a77f7e8fc16bbeee61ab301d",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile",
    "workflow": ".github/workflows/build-snes9x2005_plus.yml",
    "source_key": SNES9X2005_PLUS_CORE_ID,
    "source_dir": "libretro-snes9x2005_plus",
    "output_path": "dist/unix/snes9x2005_plus_libretro.so",
    "artifact_name": SNES9X2005_PLUS_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/snes9x2005_plus_libretro.info"
    ),
    "metadata_artifact_name": "snes9x2005_plus_libretro.info",
    "make_variables": SNES9X2005_PLUS_MAKE_VARIABLES,
}

SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT = 33
SNES9X2005_PLUS_EXPECTED_COMPILE_PAIR_SHA256 = (
    "61e4543b2f6e3b713ceb3615bebf2a943ba2ea74e0aedfa57415e61e8901dd35"
)
SNES9X2005_PLUS_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "8058993976c39e3246212acabbde24df4eb5339e08199ad089d65d900bc49312",
    "armhf": "1f8d26cf63982712200cf16c9d836ba78ddac5a75d8fa865d5604907aff13473",
}
SNES9X2005_PLUS_EXPECTED_LINK_OBJECT_SHA256 = (
    "8426b2dea08a9d17c1c57f353216afe9e52b183c0eb052a17c2f1245f7127b33"
)
SNES9X2005_PLUS_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "b1ee2d7695a8ba77b5b09430e60b2805c0d807e22fb4149ef80227043d38e492"
)
SNES9X2005_PLUS_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
    "-lm",
)
SNES9X2005_PLUS_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "e9a8958217329891ecfe59c4be0146e932a39e6477a0375a1a5e734d2540179e",
    "armhf": "7665e3999e2477f8090493e1334c4cb3753eb31efda9c793a9a48da06f663b29",
}

SNES9X2005_PLUS_EXPECTED_WARNING_COUNT = {"arm64": 16, "armhf": 12}
SNES9X2005_PLUS_EXPECTED_NOTE_COUNT = {"arm64": 12, "armhf": 12}
SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_MEMBER_COUNT = {
    "arm64": 84,
    "armhf": 72,
}
SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_LINES_SHA256 = {
    "arm64": "cf587b0459866f1526beaf8f4a6bf1e5734d0ed8501f11139fdafb9db7c919b2",
    "armhf": "1c0426bf66c38deb6411ed0ef3c384f1e0b25d8ba064d81f67a49799ef607d01",
}
SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_HEADINGS = {
    "arm64": (
        "source/apu_blargg.c: In function 'spc_cpu_write':",
        "source/apu_blargg.c: In function 'spc_run_until_':",
        "source/memmap.c: In function 'LoROMMap':",
        "source/memmap.c: In function 'SetaDSPMap':",
        "source/memmap.c: In function 'JumboLoROMMap':",
    ),
    "armhf": (
        "source/memmap.c: In function 'LoROMMap':",
        "source/memmap.c: In function 'SetaDSPMap':",
        "source/memmap.c: In function 'JumboLoROMMap':",
    ),
}
SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_BLOCK_SHA256_COUNTS = {
    "arm64": {
        "95ccd18de3bb7dab6031ea263284ea6d8d09580bc896aeb60040ba999965fa39": 1,
        "9c60fef2231eb8b257d9eb2a235e6fc6b8398e282c50685be6fd745dfabc1f16": 1,
        "03d49c01295fee8cf119858875086c2d3c3d3667c065a161ae80d929367ed5be": 1,
        "502b58128a9bdd4438910fb05e7ba3bc57bf9ace539b765d99bb2f5d3f260bcd": 1,
        "184a30e4eb45c7d0f9381d3b3bd57cd8136f8bcfe5263fca5b362860cf1f77f4": 2,
        "d20ebb772217e58cd422a45cc7be7a991bc9d88e5f2917c86b907ee6c5f43f26": 2,
        "e7f476c687f10237a482365782b8ec304157f8ac61430ee4abf17c857ae9b329": 2,
        "7be4ab27d3e6ddbb4928d61609814b4d8479c0dcfa03c82f987986c3c0444f4b": 2,
        "d0b15493b7085d4dfc2aafb9b832432b10f5b65b1432e2ddec9b58914c085936": 2,
        "4f9a786ead2de7388a237b7da7d75a8960797f18491d3b8f747d00b5d4cd6b46": 2,
    },
    "armhf": {
        "01ba8243f2bf9b95322511171c24b4762500eefaae41ca33829b99918ab06d61": 2,
        "8f8da9754d8138c84c3b0120dea9b399acb5adfb5c5ff18e45d50bfa2e873494": 2,
        "529ed22e7571992355e81d0e00fce599711e5be309f0a9aa5ff05ee224a2707f": 2,
        "3ff9038b0e6e40652bf461f9b7b8e4c407e30460f4433fa2aae4b7cf54006092": 2,
        "95d202c8a358b10e250be05165c1f652c18bfe971b2e07887f4dac9cb0479760": 2,
        "4cac8b2ae1aabd23b9da3e8d64c00424ae1d7493d69fcc992ed391eba065ec92": 2,
    },
}
SNES9X2005_PLUS_DIAGNOSTIC_SOURCE_PREFIXES = (
    "source/apu_blargg.c:",
    "source/memmap.c:",
)
SNES9X2005_PLUS_FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "error:",
    "fatal:",
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
SNES9X2005_PLUS_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SNES9X2005_PLUS_DIAGNOSTIC_CONTEXT_LINE_RE = re.compile(
    r"^\s+(?:\d+ )?\|"
)


def snes9x2005_plus_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable Plus-core catalog identity."""

    return native_git_version_spec_is_well_formed(
        spec, SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
    )


SNES9X2005_PLUS_LOG_CONTRACT = COnlyLogContract(
    core_id=SNES9X2005_PLUS_CORE_ID,
    expected_compile_count=SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=(
        SNES9X2005_PLUS_EXPECTED_COMPILE_PAIR_SHA256
    ),
    expected_compile_invocation_sha256=(
        SNES9X2005_PLUS_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=(
        SNES9X2005_PLUS_EXPECTED_LINK_OBJECT_SHA256
    ),
    build_artifact_name=SNES9X2005_PLUS_BUILD_ARTIFACT_NAME,
    expected_link_options=SNES9X2005_PLUS_EXPECTED_LINK_OPTIONS,
    source_commit=(
        SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
    ),
    source_tree=(
        SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"]
    ),
    expected_raw_link_object_sha256=(
        SNES9X2005_PLUS_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def _diagnostic_context_is_exact(
    lines: list[str],
    arch: str,
    version_position: int,
    link_position: int,
) -> bool:
    """Prove reviewed diagnostics while tolerating whole-block reordering."""

    expected_block_counts = (
        SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_BLOCK_SHA256_COUNTS.get(arch)
    )
    expected_headings = SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_HEADINGS.get(arch)
    expected_member_count = (
        SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_MEMBER_COUNT.get(arch)
    )
    if (
        expected_block_counts is None
        or expected_headings is None
        or expected_member_count is None
    ):
        return False
    known_headings = {
        heading
        for headings in SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_HEADINGS.values()
        for heading in headings
    }
    headings: Counter[str] = Counter()
    block_fingerprints: Counter[str] = Counter()
    block_members: list[str] = []
    for position, line in enumerate(lines):
        is_heading = line in known_headings
        is_tagged = (
            "warning:" in line.casefold() or "note:" in line.casefold()
        )
        is_context = (
            SNES9X2005_PLUS_DIAGNOSTIC_CONTEXT_LINE_RE.match(line) is not None
        )
        is_known_source_diagnostic = line.startswith(
            SNES9X2005_PLUS_DIAGNOSTIC_SOURCE_PREFIXES
        )
        if not (
            is_heading
            or is_tagged
            or is_context
            or is_known_source_diagnostic
        ):
            continue
        if position <= version_position or position >= link_position:
            return False
        if is_heading:
            headings[line] += 1
            continue
        if is_known_source_diagnostic and not is_tagged:
            return False
        if is_tagged or is_context:
            block_members.append(line)

    if len(block_members) != expected_member_count:
        return False
    position = 0
    while position < len(block_members):
        remaining = len(block_members) - position
        if (
            remaining < 3
            or "warning:" not in block_members[position].casefold()
            or any(
                SNES9X2005_PLUS_DIAGNOSTIC_CONTEXT_LINE_RE.match(
                    block_members[position + offset]
                )
                is None
                for offset in (1, 2)
            )
        ):
            return False
        block_size = 3
        if (
            remaining >= 6
            and "note:" in block_members[position + 3].casefold()
        ):
            if any(
                SNES9X2005_PLUS_DIAGNOSTIC_CONTEXT_LINE_RE.match(
                    block_members[position + offset]
                )
                is None
                for offset in (4, 5)
            ):
                return False
            block_size = 6
        block = tuple(block_members[position : position + block_size])
        if block_size == 3:
            if not block[0].startswith("source/apu_blargg.c:"):
                return False
        elif not (
            block[0].startswith("source/memmap.c:")
            and block[3].startswith("source/memmap.c:")
        ):
            return False
        block_fingerprints[_lines_sha256(block)] += 1
        position += block_size
    return bool(
        headings == Counter(expected_headings)
        and block_fingerprints == Counter(expected_block_counts)
    )


def _snes9x2005_plus_markers_are_exact(lines: list[str]) -> bool:
    observed = tuple(
        line
        for line in lines
        if line.startswith("HEAD is now at ")
        or line.startswith("CORE_PIPELINE_")
    )
    return observed == (
        SNES9X2005_PLUS_SOURCE_HEAD_MARKER,
        SNES9X2005_PLUS_MAKEFLAGS_MARKER,
        SNES9X2005_PLUS_MAKE_VARIABLE_MARKER,
        SNES9X2005_PLUS_NATIVE_VERSION_MARKER,
    )


def _snes9x2005_plus_compile_and_link_scope_is_exact(
    lines: list[str],
    arch: str,
) -> tuple[list[int], tuple[int, list[str]]] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
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
                or [token for token in tokens[1:] if "GIT_VERSION" in token]
                != [SNES9X2005_PLUS_NATIVE_GIT_VERSION_COMPILE_TOKEN]
                or [token for token in tokens[1:] if "USE_BLARGG_APU" in token]
                != [SNES9X2005_PLUS_APU_COMPILE_TOKEN]
            ):
                return None
            continue
        parsed_output = output_option(tokens)
        if (
            parsed_output is not None
            and parsed_output[0] == SNES9X2005_PLUS_BUILD_ARTIFACT_NAME
        ):
            if tokens[0] not in expected_c_compilers:
                return None
            link_commands.append((line_number, tokens))
    if (
        len(compile_positions) != SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT
        or len(link_commands) != 1
    ):
        return None
    return compile_positions, link_commands[0]


def snes9x2005_plus_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the exact Plus source, C build, link, and diagnostics."""

    if (
        core_id != SNES9X2005_PLUS_CORE_ID
        or not isinstance(build_log_text, str)
    ):
        return False
    if arch not in TARGET_COMPILERS:
        raise PipelineError(f"unknown architecture: {arch}")
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in SNES9X2005_PLUS_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or SNES9X2005_PLUS_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or "CORE_PIPELINE_MAKE_DEFAULT" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT
        or build_log_text.count(SNES9X2005_PLUS_NATIVE_GIT_VERSION_LOG_TOKEN)
        != SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT
        or build_log_text.count(SNES9X2005_PLUS_APU_COMPILE_TOKEN)
        != SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT
    ):
        return False
    lines = build_log_text.splitlines()
    if not _snes9x2005_plus_markers_are_exact(lines):
        return False
    commands = _snes9x2005_plus_compile_and_link_scope_is_exact(lines, arch)
    if commands is None:
        return False
    compile_positions, (link_position, link_tokens) = commands
    source_position = lines.index(SNES9X2005_PLUS_SOURCE_HEAD_MARKER)
    makeflags_position = lines.index(SNES9X2005_PLUS_MAKEFLAGS_MARKER)
    make_variable_position = lines.index(SNES9X2005_PLUS_MAKE_VARIABLE_MARKER)
    version_position = lines.index(SNES9X2005_PLUS_NATIVE_VERSION_MARKER)
    if not (
        source_position
        < makeflags_position
        < make_variable_position
        < version_position
        and version_position < min(compile_positions)
        and max(compile_positions) < link_position
        and ordered_command_argv_sha256(link_tokens)
        == SNES9X2005_PLUS_EXPECTED_ORDERED_LINK_ARGV_SHA256.get(arch)
    ):
        return False

    warning_positions = tuple(
        index
        for index, line in enumerate(lines)
        if "warning:" in line.casefold()
    )
    note_positions = tuple(
        index
        for index, line in enumerate(lines)
        if "note:" in line.casefold()
    )
    diagnostic_positions = tuple(sorted((*warning_positions, *note_positions)))
    diagnostic_lines = tuple(lines[index] for index in diagnostic_positions)
    if (
        len(warning_positions)
        != SNES9X2005_PLUS_EXPECTED_WARNING_COUNT.get(arch)
        or len(note_positions) != SNES9X2005_PLUS_EXPECTED_NOTE_COUNT.get(arch)
        or not diagnostic_positions
        or diagnostic_positions[0] <= version_position
        or diagnostic_positions[-1] >= link_position
        or any(
            not line.startswith(SNES9X2005_PLUS_DIAGNOSTIC_SOURCE_PREFIXES)
            for line in diagnostic_lines
        )
        or _multiset_lines_sha256(diagnostic_lines)
        != SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_LINES_SHA256.get(arch)
        or not _diagnostic_context_is_exact(
            lines,
            arch,
            version_position,
            link_position,
        )
    ):
        return False
    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        SNES9X2005_PLUS_LOG_CONTRACT,
    )


__all__ = [
    "SNES9X2005_PLUS_APU_COMPILE_TOKEN",
    "SNES9X2005_PLUS_BUILD_ARTIFACT_NAME",
    "SNES9X2005_PLUS_CORE_ID",
    "SNES9X2005_PLUS_EXPECTED_COMPILE_COUNT",
    "SNES9X2005_PLUS_EXPECTED_COMPILE_INVOCATION_SHA256",
    "SNES9X2005_PLUS_EXPECTED_COMPILE_PAIR_SHA256",
    "SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_BLOCK_SHA256_COUNTS",
    "SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_HEADINGS",
    "SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_LINES_SHA256",
    "SNES9X2005_PLUS_EXPECTED_LINK_OBJECT_SHA256",
    "SNES9X2005_PLUS_EXPECTED_LINK_OPTIONS",
    "SNES9X2005_PLUS_EXPECTED_NOTE_COUNT",
    "SNES9X2005_PLUS_EXPECTED_ORDERED_LINK_ARGV_SHA256",
    "SNES9X2005_PLUS_EXPECTED_RAW_LINK_OBJECT_SHA256",
    "SNES9X2005_PLUS_EXPECTED_WARNING_COUNT",
    "SNES9X2005_PLUS_LOG_CONTRACT",
    "SNES9X2005_PLUS_MAKE_PROFILE",
    "SNES9X2005_PLUS_MAKE_VARIABLES",
    "SNES9X2005_PLUS_NATIVE_GIT_VERSION",
    "SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY",
    "snes9x2005_plus_log_proves_contract",
    "snes9x2005_plus_spec_is_well_formed",
]
