"""Exact PokéMini C-only native-version build contract."""

from __future__ import annotations

from collections import Counter
import json
import re
import shlex

from ..foundation import sha256_bytes
from .command_line import output_option
from .compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


POKEMINI_CORE_ID = "pokemini"
POKEMINI_BUILD_ARTIFACT_NAME = "pokemini_libretro.so"
POKEMINI_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
POKEMINI_NATIVE_GIT_VERSION = " bb009b1"
POKEMINI_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" bb009b1"\"'
POKEMINI_NATIVE_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION=" bb009b1"'
POKEMINI_SOURCE_HEAD_MARKER = (
    "HEAD is now at bb009b1 Merge pull request #65 from cscd98/webos-cli"
)
POKEMINI_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" bb009b1"|file'
)
POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-pokemini.yml",
    "source_url": "https://github.com/libretro/PokeMini.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "bb009b1379ad15f1514f20ca7cbf710b4af42b3e",
    "source_tree": "f3a98fcf910c07bd9e0f5ee8466bed7865536c33",
    "source_key": POKEMINI_CORE_ID,
    "source_dir": "libretro-pokemini",
    "output_path": "dist/unix/pokemini_libretro.so",
    "artifact_name": POKEMINI_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/pokemini_libretro.info",
    "metadata_artifact_name": "pokemini_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile.libretro",
}

POKEMINI_EXPECTED_COMPILE_COUNT = 43
POKEMINI_EXPECTED_LANGUAGE_COUNTS = {"c": 43}
POKEMINI_EXPECTED_COMPILE_PAIR_SHA256 = (
    "17f65c12b7ef794447812008357fb682cb19db4a6a3e82486670da39d0145750"
)
POKEMINI_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "533510854d6e233ce8042544af7dbbd43eb387404ef1e011c534af9a4575b8d8",
    "armhf": "214985b96125d51986696ccca44d08d63e43ce6579e37cc13a4f15c33c141826",
}
POKEMINI_EXPECTED_LINK_OBJECT_SHA256 = (
    "3527e8711e8a30937f33c5be35b0e5d6c98721f4b141bcf6ed6acfb1fc1765c4"
)
POKEMINI_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "2e9b5de97a1877077d38b89bcb1e892efb3ff3db4f72395b3a966e351a97c25d"
)
POKEMINI_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=libretro/link.T",
    "-lm",
)
POKEMINI_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "804c9c7e9c3560725b2c64959c52211e851033eda5f25a16ec3431796f37c7d1",
    "armhf": "2a35d956f4cb48dc5478ba9234e5fa164160e4cef8a95935dcfaccea4cb2b37d",
}

POKEMINI_EXPECTED_WARNING_LINES = {
    "arm64": (
        "source/MinxCPU_CE.c:508:19: warning: this statement may fall "
        "through [-Wimplicit-fallthrough=]",
        "source/MinxIO.c:276:15: warning: this statement may fall through "
        "[-Wimplicit-fallthrough=]",
        "source/MinxIO.c:279:15: warning: this statement may fall through "
        "[-Wimplicit-fallthrough=]",
        "source/MinxIO.c:282:15: warning: this statement may fall through "
        "[-Wimplicit-fallthrough=]",
        "libretro/libretro.c:561:43: warning: '.eep' directive writing 4 "
        "bytes into a region of size between 0 and 511 [-Wformat-overflow=]",
    ),
    "armhf": (
        "source/MinxCPU_CE.c:508:40: warning: this statement may fall "
        "through [-Wimplicit-fallthrough=]",
        "source/MinxIO.c:276:36: warning: this statement may fall through "
        "[-Wimplicit-fallthrough=]",
        "source/MinxIO.c:279:36: warning: this statement may fall through "
        "[-Wimplicit-fallthrough=]",
        "source/MinxIO.c:282:36: warning: this statement may fall through "
        "[-Wimplicit-fallthrough=]",
        "libretro/libretro.c:561:57: warning: '.eep' directive writing 4 "
        "bytes into a region of size between 0 and 511 [-Wformat-overflow=]",
    ),
}
POKEMINI_EXPECTED_NOTE_LINES = {
    "arm64": (
        "source/MinxCPU_CE.c:510:3: note: here",
        "source/MinxIO.c:278:3: note: here",
        "source/MinxIO.c:281:3: note: here",
        "source/MinxIO.c:284:3: note: here",
        "/usr/aarch64-linux-gnu/include/bits/stdio2.h:36:10: note: "
        "'__builtin___sprintf_chk' output 6 or more bytes (assuming 517) "
        "into a destination of size 512",
    ),
    "armhf": (
        "source/MinxCPU_CE.c:510:17: note: here",
        "source/MinxIO.c:278:17: note: here",
        "source/MinxIO.c:281:17: note: here",
        "source/MinxIO.c:284:17: note: here",
        "libretro/libretro.c:561:17: note: 'sprintf' output 6 or more bytes "
        "(assuming 517) into a destination of size 512",
    ),
}

POKEMINI_ARM64_CPU_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "source/MinxCPU_CE.c: In function 'MinxCPU_ExecCE':",
        POKEMINI_EXPECTED_WARNING_LINES["arm64"][0],
        "  508 |    MinxCPU.SP.W.L = ADD16(MinxCPU.SP.W.L, I16);",
        "      |    ~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        POKEMINI_EXPECTED_NOTE_LINES["arm64"][0],
        "  510 |   case 0x6D: // ??? HL, #nn",
        "      |   ^~~~",
    )
)
POKEMINI_ARM64_IO_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "source/MinxIO.c: In function 'MinxIO_WriteReg':",
        POKEMINI_EXPECTED_WARNING_LINES["arm64"][1],
        "  276 |    PMR_REG_53 = 0x00;",
        POKEMINI_EXPECTED_NOTE_LINES["arm64"][1],
        "  278 |   case 0x54: // Unknown",
        "      |   ^~~~",
        POKEMINI_EXPECTED_WARNING_LINES["arm64"][2],
        "  279 |    PMR_REG_54 = val & 0x77;",
        POKEMINI_EXPECTED_NOTE_LINES["arm64"][2],
        "  281 |   case 0x55: // Unknown",
        "      |   ^~~~",
        POKEMINI_EXPECTED_WARNING_LINES["arm64"][3],
        "  282 |    PMR_REG_55 = val & 0x07;",
        POKEMINI_EXPECTED_NOTE_LINES["arm64"][3],
        "  284 |   case 0x60: // I/O Direction Select ( 0 = Input, 1 = Output )",
        "      |   ^~~~",
    )
)
POKEMINI_ARM64_LIBRETRO_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "libretro/libretro.c: In function 'retro_load_game':",
        POKEMINI_EXPECTED_WARNING_LINES["arm64"][4],
        '  561 |   sprintf(CommandLine.eeprom_file, "%s%c%s.eep", '
        "g_save_dir, slash, g_basename);",
        "      |                                           ^~~~",
        "In file included from /usr/aarch64-linux-gnu/include/stdio.h:867,",
        "                 from libretro/libretro.c:1:",
        POKEMINI_EXPECTED_NOTE_LINES["arm64"][4],
        "   36 |   return __builtin___sprintf_chk (__s, __USE_FORTIFY_LEVEL - 1,",
        "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        "   37 |       __bos (__s), __fmt, __va_arg_pack ());",
        "      |       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    )
)
POKEMINI_ARMHF_CPU_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "source/MinxCPU_CE.c: In function 'MinxCPU_ExecCE':",
        POKEMINI_EXPECTED_WARNING_LINES["armhf"][0],
        "  508 |                         MinxCPU.SP.W.L = "
        "ADD16(MinxCPU.SP.W.L, I16);",
        "      |                         ~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        POKEMINI_EXPECTED_NOTE_LINES["armhf"][0],
        "  510 |                 case 0x6D: // ??? HL, #nn",
        "      |                 ^~~~",
    )
)
POKEMINI_ARMHF_IO_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "source/MinxIO.c: In function 'MinxIO_WriteReg':",
        POKEMINI_EXPECTED_WARNING_LINES["armhf"][1],
        "  276 |                         PMR_REG_53 = 0x00;",
        POKEMINI_EXPECTED_NOTE_LINES["armhf"][1],
        "  278 |                 case 0x54: // Unknown",
        "      |                 ^~~~",
        POKEMINI_EXPECTED_WARNING_LINES["armhf"][2],
        "  279 |                         PMR_REG_54 = val & 0x77;",
        POKEMINI_EXPECTED_NOTE_LINES["armhf"][2],
        "  281 |                 case 0x55: // Unknown",
        "      |                 ^~~~",
        POKEMINI_EXPECTED_WARNING_LINES["armhf"][3],
        "  282 |                         PMR_REG_55 = val & 0x07;",
        POKEMINI_EXPECTED_NOTE_LINES["armhf"][3],
        "  284 |                 case 0x60: // I/O Direction Select "
        "( 0 = Input, 1 = Output )",
        "      |                 ^~~~",
    )
)
POKEMINI_ARMHF_LIBRETRO_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "libretro/libretro.c: In function 'retro_load_game':",
        POKEMINI_EXPECTED_WARNING_LINES["armhf"][4],
        '  561 |                 sprintf(CommandLine.eeprom_file, "%s%c%s.eep", '
        "g_save_dir, slash, g_basename);",
        "      |                                                         ^~~~",
        "In function 'InitialiseCommandLine',",
        "    inlined from 'retro_load_game' at libretro/libretro.c:1260:2:",
        POKEMINI_EXPECTED_NOTE_LINES["armhf"][4],
        '  561 |                 sprintf(CommandLine.eeprom_file, "%s%c%s.eep", '
        "g_save_dir, slash, g_basename);",
        "      |                 "
        "^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    )
)
POKEMINI_EXPECTED_DIAGNOSTIC_BLOCKS = {
    "arm64": (
        POKEMINI_ARM64_CPU_DIAGNOSTIC_BLOCK,
        POKEMINI_ARM64_IO_DIAGNOSTIC_BLOCK,
        POKEMINI_ARM64_LIBRETRO_DIAGNOSTIC_BLOCK,
    ),
    "armhf": (
        POKEMINI_ARMHF_CPU_DIAGNOSTIC_BLOCK,
        POKEMINI_ARMHF_IO_DIAGNOSTIC_BLOCK,
        POKEMINI_ARMHF_LIBRETRO_DIAGNOSTIC_BLOCK,
    ),
}
POKEMINI_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
POKEMINI_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def pokemini_spec_is_well_formed(spec: object) -> bool:
    """Require PokéMini's complete immutable catalog identity."""

    identity = POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": POKEMINI_NATIVE_GIT_VERSION_DERIVATION,
                    "value": POKEMINI_NATIVE_GIT_VERSION,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def pokemini_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed PokéMini tree."""

    identity = POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == POKEMINI_CORE_ID
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


def pokemini_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted PokéMini native-version build record."""

    identity = POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and pokemini_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": POKEMINI_NATIVE_GIT_VERSION_DERIVATION,
                "value": POKEMINI_NATIVE_GIT_VERSION,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


POKEMINI_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=POKEMINI_CORE_ID,
    expected_compile_count=POKEMINI_EXPECTED_COMPILE_COUNT,
    expected_language_counts=POKEMINI_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=POKEMINI_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        POKEMINI_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=POKEMINI_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        POKEMINI_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=POKEMINI_BUILD_ARTIFACT_NAME,
    expected_link_options=POKEMINI_EXPECTED_LINK_OPTIONS,
    source_commit=POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_link_language="c",
)


def pokemini_ordered_link_argv_sha256(tokens: list[str]) -> str:
    """Hash the complete ordered PokéMini linker argv without normalization."""

    return sha256_bytes(
        json.dumps(
            tokens,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def _diagnostic_context_lines_are_exact(
    build_log_text: str,
    expected_context_blocks: tuple[str, ...],
    link_line_number: int,
) -> bool:
    """Accept only pre-link interleavings of reviewed diagnostic streams."""

    expected_streams = tuple(
        tuple(block.splitlines()) for block in expected_context_blocks
    )
    expected_lines = Counter(
        line for stream in expected_streams for line in stream
    )
    actual_lines = tuple(
        (line_number, line)
        for line_number, line in enumerate(build_log_text.splitlines())
        if line in expected_lines
    )
    if (
        Counter(line for _line_number, line in actual_lines) != expected_lines
        or any(
            line_number >= link_line_number
            for line_number, _line in actual_lines
        )
    ):
        return False

    states = {tuple(0 for _stream in expected_streams)}
    for _line_number, line in actual_lines:
        next_states: set[tuple[int, ...]] = set()
        for state in states:
            for stream_index, stream in enumerate(expected_streams):
                position = state[stream_index]
                if position >= len(stream) or stream[position] != line:
                    continue
                advanced = list(state)
                advanced[stream_index] += 1
                next_states.add(tuple(advanced))
        if not next_states:
            return False
        states = next_states
    return any(
        all(
            position == len(expected_streams[index])
            for index, position in enumerate(state)
        )
        for state in states
    )


def _pokemini_markers_are_exact(lines: list[str]) -> bool:
    observed = tuple(
        line
        for line in lines
        if line.startswith("HEAD is now at ")
        or line.startswith("CORE_PIPELINE_")
    )
    return observed == (
        POKEMINI_SOURCE_HEAD_MARKER,
        POKEMINI_NATIVE_VERSION_MARKER,
    )


def _pokemini_compile_scope_is_exact(
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
                or [
                    token for token in tokens[1:] if "GIT_VERSION" in token
                ]
                != [POKEMINI_NATIVE_GIT_VERSION_COMPILE_TOKEN]
            ):
                return None
            continue
        parsed_output = output_option(tokens)
        if (
            parsed_output is not None
            and parsed_output[0] == POKEMINI_BUILD_ARTIFACT_NAME
        ):
            link_commands.append((line_number, tokens))
    if (
        len(compile_positions) != POKEMINI_EXPECTED_COMPILE_COUNT
        or len(link_commands) != 1
    ):
        return None
    return compile_positions, link_commands


def pokemini_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove exact source, native version, C argv, link, and diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    expected_warning_lines = POKEMINI_EXPECTED_WARNING_LINES.get(arch)
    expected_note_lines = POKEMINI_EXPECTED_NOTE_LINES.get(arch)
    expected_diagnostic_blocks = POKEMINI_EXPECTED_DIAGNOSTIC_BLOCKS.get(arch)
    if (
        expected_warning_lines is None
        or expected_note_lines is None
        or expected_diagnostic_blocks is None
    ):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in POKEMINI_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or POKEMINI_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != POKEMINI_EXPECTED_COMPILE_COUNT
        or build_log_text.count(POKEMINI_NATIVE_GIT_VERSION_LOG_TOKEN)
        != POKEMINI_EXPECTED_COMPILE_COUNT
    ):
        return False
    lines = build_log_text.splitlines()
    if not _pokemini_markers_are_exact(lines):
        return False
    warning_lines = Counter(
        line for line in lines if "warning:" in line.casefold()
    )
    note_lines = Counter(line for line in lines if "note:" in line.casefold())
    if (
        warning_lines != Counter(expected_warning_lines)
        or note_lines != Counter(expected_note_lines)
    ):
        return False
    commands = _pokemini_compile_scope_is_exact(lines, arch)
    if commands is None:
        return False
    compile_positions, link_commands = commands
    link_position, link_tokens = link_commands[0]
    source_position = lines.index(POKEMINI_SOURCE_HEAD_MARKER)
    marker_position = lines.index(POKEMINI_NATIVE_VERSION_MARKER)
    if (
        not _diagnostic_context_lines_are_exact(
            build_log_text,
            expected_diagnostic_blocks,
            link_position,
        )
        or not (
            source_position < marker_position < min(compile_positions)
            and max(compile_positions) < link_position
        )
        or pokemini_ordered_link_argv_sha256(link_tokens)
        != POKEMINI_EXPECTED_ORDERED_LINK_ARGV_SHA256.get(arch)
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        POKEMINI_LOG_CONTRACT,
    )
