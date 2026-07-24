"""Exact Mednafen Lynx mixed-language build-log contract."""

from __future__ import annotations

import re
import shlex
from collections import Counter

from .compiler import TARGET_COMPILERS, TARGET_CXX_COMPILERS
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_compile_invocation,
    mixed_language_log_proves_contract,
)
from .log_checks import sequence_positions as _sequence_positions


MEDNAFEN_LYNX_CORE_ID = "mednafen_lynx"
MEDNAFEN_LYNX_BUILD_ARTIFACT_NAME = "mednafen_lynx_libretro.so"
MEDNAFEN_LYNX_EXPECTED_COMPILE_COUNT = 29
MEDNAFEN_LYNX_EXPECTED_LANGUAGE_COUNTS = {"c": 13, "cxx": 16}
MEDNAFEN_LYNX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "bea485e01741c8b8ac75737076aca33964a0f64eb0302ce9746aca098e95c117"
)
MEDNAFEN_LYNX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "d50f0c22dd77e092baede36926135e1148922652626f9a2ebc15823db8abb3fa",
    "armhf": "788f14e0c559f85a6f8d56d55f987ecaf86ddb1b02c5ce9f15a5b54e9a21e147",
}
MEDNAFEN_LYNX_EXPECTED_LINK_OBJECT_SHA256 = (
    "7f1af36da151c0c4924a34e2c8f203a07cec1eda8b9ae3d3414005ba8653382e"
)
MEDNAFEN_LYNX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "7f1af36da151c0c4924a34e2c8f203a07cec1eda8b9ae3d3414005ba8653382e"
)
MEDNAFEN_LYNX_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "512f71c8113d9f13a1b766e35686b331a4df6c88521c84454099e47b45a76967",
    "armhf": "a6cfcd56fdb58cd4c0613dc39ae9aadfab43b11f36c5a54114f8458e624e4f7a",
}
MEDNAFEN_LYNX_EXPECTED_LINK_OPTIONS = (
    "-lrt",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
MEDNAFEN_LYNX_EXPECTED_LINK_OBJECTS = (
    "mednafen/lynx/cart.o",
    "mednafen/lynx/c65c02.o",
    "mednafen/lynx/memmap.o",
    "mednafen/lynx/mikie.o",
    "mednafen/lynx/ram.o",
    "mednafen/lynx/rom.o",
    "mednafen/lynx/susie.o",
    "mednafen/lynx/system.o",
    "mednafen/sound/Blip_Buffer.o",
    "mednafen/settings.o",
    "mednafen/state.o",
    "mednafen/mempatcher.o",
    "mednafen/md5.o",
    "mednafen/sound/Stereo_Buffer.o",
    "mednafen/endian.o",
    "libretro.o",
    "scrc32.o",
    "libretro-common/streams/file_stream.o",
    "libretro-common/compat/fopen_utf8.o",
    "libretro-common/compat/compat_posix_string.o",
    "libretro-common/compat/compat_snprintf.o",
    "libretro-common/compat/compat_strl.o",
    "libretro-common/compat/compat_strcasestr.o",
    "libretro-common/encodings/encoding_utf.o",
    "libretro-common/file/file_path.o",
    "libretro-common/vfs/vfs_implementation.o",
    "libretro-common/time/rtime.o",
    "libretro-common/string/stdstring.o",
    "mednafen/file.o",
)
MEDNAFEN_LYNX_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-o",
        MEDNAFEN_LYNX_BUILD_ARTIFACT_NAME,
        *MEDNAFEN_LYNX_EXPECTED_LINK_OBJECTS,
        *MEDNAFEN_LYNX_EXPECTED_LINK_OPTIONS,
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-g++",
        "armhf": "arm-a30-linux-gnueabihf-g++",
    }.items()
}

MEDNAFEN_LYNX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
MEDNAFEN_LYNX_NATIVE_GIT_VERSION = " fcdefcf"
MEDNAFEN_LYNX_NATIVE_GIT_VERSION_COMPILER_SCOPE = frozenset({"cxx"})
MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE = {"c": 0, "cxx": 1}
MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCE_COUNT = 16
MEDNAFEN_LYNX_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" fcdefcf"\"'
)
MEDNAFEN_LYNX_SOURCE_HEAD_MARKER = (
    "HEAD is now at fcdefcf Merge pull request #75 from cscd98/webos-ci"
)
MEDNAFEN_LYNX_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{MEDNAFEN_LYNX_CORE_ID}",
)
MEDNAFEN_LYNX_SUCCESS_TRAILER = (
    'cp "mednafen_lynx_libretro.so" '
    '"/libretro-super/dist/unix/mednafen_lynx_libretro.so"',
    *MEDNAFEN_LYNX_SUCCESS_MARKER,
)

MEDNAFEN_LYNX_TRUNCATION_CONTEXT = {
    "arm64": (
        "libretro.cpp: In function 'bool retro_load_game(const "
        "retro_game_info*)':",
        "libretro.cpp:191:41: warning: '%s' directive output may be truncated "
        "writing up to 4095 bytes into a region of size 2048 "
        "[-Wformat-truncation=]",
        '  191 |  snprintf(bios_path, sizeof(bios_path),"%s" SLASH "%s", '
        'retro_system_directory, "lynxboot.img");',
        "      |                                         ^~              "
        "~~~~~~~~~~~~~~~~~~~~~~",
        "In file included from /usr/aarch64-linux-gnu/include/stdio.h:867,",
        "                 from /usr/aarch64-linux-gnu/include/c++/9/cstdio:42,",
        "                 from /usr/aarch64-linux-gnu/include/c++/9/ext/"
        "string_conversions.h:43,",
        "                 from /usr/aarch64-linux-gnu/include/c++/9/bits/"
        "basic_string.h:6496,",
        "                 from /usr/aarch64-linux-gnu/include/c++/9/string:55,",
        "                 from mednafen/git.h:4,",
        "                 from mednafen/mednafen.h:8,",
        "                 from libretro.cpp:2:",
        "/usr/aarch64-linux-gnu/include/bits/stdio2.h:67:35: note: "
        "'__builtin___snprintf_chk' output between 14 and 4109 bytes into a "
        "destination of size 2048",
        "   67 |   return __builtin___snprintf_chk (__s, __n, "
        "__USE_FORTIFY_LEVEL - 1,",
        "      |          ~~~~~~~~~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~"
        "~~~~~~~~",
        "   68 |        __bos (__s), __fmt, __va_arg_pack ());",
        "      |        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    ),
    "armhf": (
        "libretro.cpp: In function 'bool retro_load_game(const "
        "retro_game_info*)':",
        "libretro.cpp:191:48: warning: '%s' directive output may be truncated "
        "writing up to 4095 bytes into a region of size 2048 "
        "[-Wformat-truncation=]",
        '  191 |         snprintf(bios_path, sizeof(bios_path),"%s" SLASH '
        '"%s", retro_system_directory, "lynxboot.img");',
        "      |                                                ^~              "
        "~~~~~~~~~~~~~~~~~~~~~~",
        "In function 'bool MDFNI_LoadGame(const uint8_t*, size_t)',",
        "    inlined from 'bool retro_load_game(const retro_game_info*)' at "
        "libretro.cpp:264:23:",
        "libretro.cpp:191:17: note: 'snprintf' output between 14 and 4109 "
        "bytes into a destination of size 2048",
        '  191 |         snprintf(bios_path, sizeof(bios_path),"%s" SLASH '
        '"%s", retro_system_directory, "lynxboot.img");',
        "      |         ~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
        "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    ),
}
MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT = (
    "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/c++/"
    "13.2.0/vector:72,",
    "                 from mednafen/mempatcher.cpp:23:",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/vector.tcc: "
    "In member function 'void std::vector<_Tp, _Alloc>::_M_realloc_insert("
    "iterator, _Args&& ...) [with _Args = {const __CHEATF&}; _Tp = __CHEATF; "
    "_Alloc = std::allocator<__CHEATF>]':",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "vector.tcc:445:7: note: parameter passing for argument of type "
    "'std::vector<__CHEATF>::iterator' changed in GCC 7.1",
    "  445 |       vector<_Tp, _Alloc>::",
    "      |       ^~~~~~~~~~~~~~~~~~~",
    "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/c++/"
    "13.2.0/vector:66:",
    "In member function 'void std::vector<_Tp, _Alloc>::push_back(const "
    "value_type&) [with _Tp = __CHEATF; _Alloc = std::allocator<__CHEATF>]',",
    "    inlined from 'int AddCheatEntry(char*, char*, uint32, uint64, uint64, "
    "int, char, unsigned int, bool)' at mednafen/mempatcher.cpp:178:18,",
    "    inlined from 'int MDFNI_AddCheat(const char*, uint32, uint64, uint64, "
    "char, unsigned int, bool)' at mednafen/mempatcher.cpp:211:19:",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "stl_vector.h:1289:28: note: parameter passing for argument of type "
    "'__gnu_cxx::__normal_iterator<__CHEATF*, std::vector<__CHEATF> >' "
    "changed in GCC 7.1",
    " 1289 |           _M_realloc_insert(end(), __x);",
    "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~",
)
MEDNAFEN_LYNX_EXPECTED_WARNING_LINES = {
    architecture: tuple(
        line for line in context if "warning:" in line.casefold()
    )
    for architecture, context in MEDNAFEN_LYNX_TRUNCATION_CONTEXT.items()
}
MEDNAFEN_LYNX_EXPECTED_NOTE_LINES = {
    "arm64": tuple(
        line
        for line in MEDNAFEN_LYNX_TRUNCATION_CONTEXT["arm64"]
        if "note:" in line.casefold()
    ),
    "armhf": tuple(
        line
        for line in (
            *MEDNAFEN_LYNX_TRUNCATION_CONTEXT["armhf"],
            *MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT,
        )
        if "note:" in line.casefold()
    ),
}
MEDNAFEN_LYNX_ALLOWED_NOTE_LINES = {
    "arm64": (MEDNAFEN_LYNX_EXPECTED_NOTE_LINES["arm64"],),
    "armhf": (
        MEDNAFEN_LYNX_EXPECTED_NOTE_LINES["armhf"],
        tuple(
            line
            for line in (
                *MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT,
                *MEDNAFEN_LYNX_TRUNCATION_CONTEXT["armhf"],
            )
            if "note:" in line.casefold()
        ),
    ),
}
MEDNAFEN_LYNX_ALLOWED_DIAGNOSTIC_CONTEXTS = {
    "arm64": (MEDNAFEN_LYNX_TRUNCATION_CONTEXT["arm64"],),
    "armhf": (
        (
            *MEDNAFEN_LYNX_TRUNCATION_CONTEXT["armhf"],
            *MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT,
        ),
        (
            *MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT,
            *MEDNAFEN_LYNX_TRUNCATION_CONTEXT["armhf"],
        ),
    ),
}
MEDNAFEN_LYNX_FORBIDDEN_LOG_FRAGMENTS = (
    "aborted",
    "bus error",
    "cannot find",
    "collect2:",
    "command not found",
    "core dumped",
    "dubious ownership",
    "error:",
    "fatal:",
    "file format not recognized",
    "floating point exception",
    "illegal instruction",
    "internal compiler error",
    "killed",
    "no such file or directory",
    "permission denied",
    "segmentation fault",
    "terminated",
    "undefined reference",
)
MEDNAFEN_LYNX_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
MEDNAFEN_LYNX_DIAGNOSTIC_SOURCE_RE = re.compile(
    r"^(?:/[^:]+|[A-Za-z0-9_./-]+): In (?:function|member function) .+$"
)
MEDNAFEN_LYNX_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")

MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_lynx.yml",
    "source_url": "https://github.com/libretro/beetle-lynx-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "fcdefcfb3c11d6d2e71be076a5d3df2e88ab73ed",
    "source_tree": "3e815d4d338aa1a201e009b36cf34e5a53ad4c9e",
    "source_key": MEDNAFEN_LYNX_CORE_ID,
    "source_dir": "libretro-mednafen_lynx",
    "output_path": "dist/unix/mednafen_lynx_libretro.so",
    "artifact_name": MEDNAFEN_LYNX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_lynx_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_lynx_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mednafen_lynx core must preserve its exact native "
    "version, source, recipe, metadata, and target contract"
)


def mednafen_lynx_spec_is_well_formed(spec: object) -> bool:
    """Require Lynx's complete immutable catalog identity."""

    identity = MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


MEDNAFEN_LYNX_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_LYNX_CORE_ID,
    expected_compile_count=MEDNAFEN_LYNX_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_LYNX_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=MEDNAFEN_LYNX_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        MEDNAFEN_LYNX_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MEDNAFEN_LYNX_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        MEDNAFEN_LYNX_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_LYNX_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_LYNX_EXPECTED_LINK_OPTIONS,
    source_commit=MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY[
        "source_commit"
    ],
    source_tree=MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_ordered_link_argv_sha256=(
        MEDNAFEN_LYNX_EXPECTED_ORDERED_LINK_ARGV_SHA256
    ),
)


def _line_is_diagnostic_context(line: str) -> bool:
    lowered = line.casefold()
    return bool(
        "warning:" in lowered
        or "note:" in lowered
        or "error:" in lowered
        or "fatal:" in lowered
        or line.startswith("In file included from ")
        or line.startswith(("In function ", "In member function "))
        or line.lstrip().startswith(("from ", "inlined from "))
        or MEDNAFEN_LYNX_DIAGNOSTIC_SOURCE_RE.fullmatch(line) is not None
        or MEDNAFEN_LYNX_DIAGNOSTIC_CONTEXT_RE.match(line) is not None
    )


def mednafen_lynx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove exact source, native version, compile, link, and diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    expected_link_argv = MEDNAFEN_LYNX_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    expected_warnings = MEDNAFEN_LYNX_EXPECTED_WARNING_LINES.get(arch)
    allowed_note_lines = MEDNAFEN_LYNX_ALLOWED_NOTE_LINES.get(arch)
    truncation_context = MEDNAFEN_LYNX_TRUNCATION_CONTEXT.get(arch)
    allowed_diagnostic_contexts = (
        MEDNAFEN_LYNX_ALLOWED_DIAGNOSTIC_CONTEXTS.get(arch)
    )
    if (
        expected_compilers is None
        or expected_cxx_compilers is None
        or expected_link_argv is None
        or expected_warnings is None
        or allowed_note_lines is None
        or truncation_context is None
        or allowed_diagnostic_contexts is None
    ):
        return False

    lines = build_log_text.splitlines()
    lowered_log = build_log_text.casefold()
    source_lines = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    pipeline_marker_lines = tuple(
        line for line in lines if "CORE_PIPELINE_" in line
    )
    warning_lines = tuple(
        line for line in lines if "warning:" in line.casefold()
    )
    note_lines = tuple(line for line in lines if "note:" in line.casefold())
    diagnostic_positions = tuple(
        position
        for position, line in enumerate(lines)
        if _line_is_diagnostic_context(line)
    )
    diagnostic_context = tuple(
        lines[position] for position in diagnostic_positions
    )
    truncation_positions = _sequence_positions(lines, truncation_context)
    # The psabi note block can be split by parallel-make interleaving (a
    # foreign diagnostic line landing inside it), so contiguity cannot be
    # required. Exactness is kept two ways instead: every block line must
    # appear in the log exactly as often as in the block, and their first
    # occurrences must preserve the block's relative order.
    def _in_order_with_exact_counts(sequence: tuple[str, ...]) -> bool:
        expected_counts = Counter(sequence)
        actual_counts = Counter(
            line for line in lines if line in expected_counts
        )
        if actual_counts != expected_counts:
            return False
        cursor = 0
        for line in sequence:
            try:
                cursor = lines.index(line, cursor) + 1
            except ValueError:
                return False
        return True

    psabi_ordered = (
        _in_order_with_exact_counts(MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT)
        if arch == "armhf"
        else True
    )
    success_positions = _sequence_positions(
        lines, MEDNAFEN_LYNX_SUCCESS_MARKER
    )
    if (
        any(
            fragment in lowered_log
            for fragment in MEDNAFEN_LYNX_FORBIDDEN_LOG_FRAGMENTS
        )
        or MEDNAFEN_LYNX_MAKE_FAILURE_RE.search(build_log_text) is not None
        or source_lines != (MEDNAFEN_LYNX_SOURCE_HEAD_MARKER,)
        or pipeline_marker_lines
        # Multiset comparisons: parallel make interleaves the per-TU
        # diagnostic blocks nondeterministically (observed live: the armhf
        # vector-include and libretro.cpp warning blocks swapped order between
        # two byte-identical-content builds). Every line stays exactly pinned;
        # only inter-block emission order is tolerated, matching the shared
        # engines' parallel-log stance.
        or Counter(warning_lines) != Counter(expected_warnings)
        or Counter(note_lines)
        not in [Counter(allowed) for allowed in allowed_note_lines]
        or Counter(diagnostic_context)
        not in [Counter(allowed) for allowed in allowed_diagnostic_contexts]
        or len(truncation_positions) != 1
        or not psabi_ordered
        or len(success_positions) != 2
        or lines.count(MEDNAFEN_LYNX_SUCCESS_MARKER[0]) != 2
        or lines.count(MEDNAFEN_LYNX_SUCCESS_MARKER[1]) != 2
        or tuple(lines[-len(MEDNAFEN_LYNX_SUCCESS_TRAILER) :])
        != MEDNAFEN_LYNX_SUCCESS_TRAILER
        or lines.count(MEDNAFEN_LYNX_SUCCESS_TRAILER[0]) != 1
        or build_log_text.count("-DGIT_VERSION=")
        != MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCE_COUNT
        or build_log_text.count(MEDNAFEN_LYNX_NATIVE_GIT_VERSION_LOG_TOKEN)
        != MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCE_COUNT
    ):
        return False

    compile_positions: list[int] = []
    libretro_compile_positions: list[int] = []
    mempatcher_compile_positions: list[int] = []
    link_invocations: list[tuple[int, tuple[str, ...]]] = []
    for line_number, line in enumerate(lines):
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens or tokens[0] not in expected_compilers:
            continue
        if "-c" in tokens:
            compile_positions.append(line_number)
            invocation = mixed_language_compile_invocation(
                tokens,
                expected_compilers,
                expected_cxx_compilers,
            )
            if invocation is None:
                return False
            if invocation[:2] == ("libretro.o", "libretro.cpp"):
                libretro_compile_positions.append(line_number)
            if invocation[:2] == (
                "mednafen/mempatcher.o",
                "mednafen/mempatcher.cpp",
            ):
                mempatcher_compile_positions.append(line_number)
            language = "cxx" if tokens[0] in expected_cxx_compilers else "c"
            expected_occurrences = (
                MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE[
                    language
                ]
            )
            if (
                line.count(MEDNAFEN_LYNX_NATIVE_GIT_VERSION_LOG_TOKEN)
                != expected_occurrences
            ):
                return False
        elif MEDNAFEN_LYNX_BUILD_ARTIFACT_NAME in tokens:
            link_invocations.append((line_number, tuple(tokens)))

    if not compile_positions or len(link_invocations) != 1:
        return False
    source_position = lines.index(MEDNAFEN_LYNX_SOURCE_HEAD_MARKER)
    link_position, link_argv = link_invocations[0]
    truncation_start = truncation_positions[0]
    truncation_end = truncation_start + len(truncation_context) - 1
    expected_link_position = len(lines) - len(MEDNAFEN_LYNX_SUCCESS_TRAILER) - 1
    psabi_is_framed = arch != "armhf"
    if arch == "armhf" and len(mempatcher_compile_positions) == 1:
        # The block may be interleaved (see _in_order_with_exact_counts), so
        # frame by its first and last member lines rather than by a
        # contiguous span. Same property proven: the psabi diagnostics all
        # sit after the mempatcher compile and before the link.
        psabi_line_set = set(MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT)
        psabi_member_positions = [
            position
            for position, line in enumerate(lines)
            if line in psabi_line_set
        ]
        psabi_is_framed = bool(
            psabi_member_positions
            and mempatcher_compile_positions[0] < psabi_member_positions[0]
            and psabi_member_positions[-1] < link_position
        )
    if (
        len(compile_positions) != MEDNAFEN_LYNX_EXPECTED_COMPILE_COUNT
        or len(libretro_compile_positions) != 1
        or len(mempatcher_compile_positions) != 1
        or link_argv != expected_link_argv
        or link_position != expected_link_position
        or not (libretro_compile_positions[0] < truncation_start)
        or truncation_end >= link_position
        or not psabi_is_framed
        or max(diagnostic_positions) >= link_position
        or not (
            success_positions[0] + len(MEDNAFEN_LYNX_SUCCESS_MARKER)
            == source_position
            and source_position < min(compile_positions)
            and max(compile_positions) < link_position
            and success_positions[1] == len(lines) - 2
        )
    ):
        return False

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        MEDNAFEN_LYNX_LOG_CONTRACT,
    )
