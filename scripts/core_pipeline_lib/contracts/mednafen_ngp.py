"""Exact Mednafen Neo Geo Pocket mixed-language build-log contract."""

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


MEDNAFEN_NGP_CORE_ID = "mednafen_ngp"
MEDNAFEN_NGP_BUILD_ARTIFACT_NAME = "mednafen_ngp_libretro.so"
MEDNAFEN_NGP_EXPECTED_COMPILE_COUNT = 37
MEDNAFEN_NGP_EXPECTED_LANGUAGE_COUNTS = {"c": 32, "cxx": 5}
MEDNAFEN_NGP_EXPECTED_COMPILE_PAIR_SHA256 = (
    "2d36f1d8205d09d6b19074b75baa82fe01d77d57db21dd65516d356bbc198081"
)
MEDNAFEN_NGP_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "91218e05000d70d63381243328df9dc94c435dd98d0bce8294da0a288522534e",
    "armhf": "08a292af429e4356e7b3af6ee7091eb416c70d998d4ca7a1a4eb38a9a13a925c",
}
MEDNAFEN_NGP_EXPECTED_LINK_OBJECT_SHA256 = (
    "eb563f5c036c7f7b9c61b987298ed547958b589107d1bbaba47c1037b525aef7"
)
MEDNAFEN_NGP_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "eb563f5c036c7f7b9c61b987298ed547958b589107d1bbaba47c1037b525aef7"
)
MEDNAFEN_NGP_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "0be8a0dcfddf7b14b08d742542cc91e1a9b59a22117612466ca9ecb4c6c3c24a",
    "armhf": "3020ce2c2346fa2380bc71dd014b2a79e01c5755e8de03522c8251efa9f2d766",
}
MEDNAFEN_NGP_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
    "-lm",
)
MEDNAFEN_NGP_EXPECTED_LINK_OBJECTS = (
    "mednafen/ngp/sound.o",
    "mednafen/ngp/T6W28_Apu.o",
    "mednafen/sound/Blip_Buffer.o",
    "mednafen/mempatcher.o",
    "mednafen/sound/Stereo_Buffer.o",
    "mednafen/ngp/biosHLE.o",
    "mednafen/ngp/bios.o",
    "mednafen/ngp/flash.o",
    "mednafen/ngp/dma.o",
    "mednafen/ngp/gfx.o",
    "mednafen/ngp/interrupt.o",
    "mednafen/ngp/mem.o",
    "mednafen/ngp/rom.o",
    "mednafen/ngp/system.o",
    "mednafen/ngp/TLCS-900h/TLCS900h_interpret.o",
    "mednafen/ngp/TLCS-900h/TLCS900h_interpret_dst.o",
    "mednafen/ngp/TLCS-900h/TLCS900h_interpret_reg.o",
    "mednafen/ngp/TLCS-900h/TLCS900h_interpret_single.o",
    "mednafen/ngp/TLCS-900h/TLCS900h_interpret_src.o",
    "mednafen/ngp/TLCS-900h/TLCS900h_registers.o",
    "mednafen/hw_cpu/z80-fuse/z80_ops.o",
    "mednafen/hw_cpu/z80-fuse/z80.o",
    "mednafen/ngp/rtc.o",
    "mednafen/ngp/Z80_interface.o",
    "mednafen/state.o",
    "libretro.o",
    "libretro-common/streams/file_stream.o",
    "libretro-common/compat/fopen_utf8.o",
    "libretro-common/compat/compat_strl.o",
    "libretro-common/compat/compat_snprintf.o",
    "libretro-common/encodings/encoding_utf.o",
    "libretro-common/vfs/vfs_implementation.o",
    "libretro-common/file/file_path.o",
    "libretro-common/time/rtime.o",
    "libretro-common/string/stdstring.o",
    "libretro-common/compat/compat_posix_string.o",
    "mednafen/settings.o",
)
MEDNAFEN_NGP_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-o",
        MEDNAFEN_NGP_BUILD_ARTIFACT_NAME,
        *MEDNAFEN_NGP_EXPECTED_LINK_OBJECTS,
        *MEDNAFEN_NGP_EXPECTED_LINK_OPTIONS,
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-g++",
        "armhf": "arm-a30-linux-gnueabihf-g++",
    }.items()
}

MEDNAFEN_NGP_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
MEDNAFEN_NGP_NATIVE_GIT_VERSION = " a50d5ac"
MEDNAFEN_NGP_NATIVE_GIT_VERSION_COMPILER_SCOPE = frozenset({"c", "cxx"})
MEDNAFEN_NGP_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE = {"c": 2, "cxx": 1}
MEDNAFEN_NGP_NATIVE_GIT_VERSION_OCCURRENCE_COUNT = 69
MEDNAFEN_NGP_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" a50d5ac"\"'
)
MEDNAFEN_NGP_SOURCE_HEAD_MARKER = (
    "HEAD is now at a50d5ac Add support for 16KB pages on Android. (#119)"
)
MEDNAFEN_NGP_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{MEDNAFEN_NGP_CORE_ID}",
)
MEDNAFEN_NGP_SUCCESS_TRAILER = (
    'cp "mednafen_ngp_libretro.so" '
    '"/libretro-super/dist/unix/mednafen_ngp_libretro.so"',
    *MEDNAFEN_NGP_SUCCESS_MARKER,
)

MEDNAFEN_NGP_EXPECTED_WARNING_LINES = (
    "libretro_core_options.h:63:56: warning: missing braces around "
    "initializer [-Wmissing-braces]",
) * 3
MEDNAFEN_NGP_WARNING_CONTEXT = (
    "In file included from libretro.c:6:",
    MEDNAFEN_NGP_EXPECTED_WARNING_LINES[0],
    "   63 | struct retro_core_option_definition option_defs_us[] = {",
    "      |                                                        ^",
    MEDNAFEN_NGP_EXPECTED_WARNING_LINES[1],
    MEDNAFEN_NGP_EXPECTED_WARNING_LINES[2],
)
MEDNAFEN_NGP_ARMHF_EXPECTED_NOTE_LINES = (
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "vector.tcc:445:7: note: parameter passing for argument of type "
    "'std::vector<__CHEATF>::iterator' changed in GCC 7.1",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "stl_vector.h:1289:28: note: parameter passing for argument of type "
    "'__gnu_cxx::__normal_iterator<__CHEATF*, std::vector<__CHEATF> >' "
    "changed in GCC 7.1",
)
MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT = (
    "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
    "c++/13.2.0/vector:72,",
    "                 from mednafen/mempatcher.cpp:23:",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "vector.tcc: In member function 'void std::vector<_Tp, "
    "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
    "{const __CHEATF&}; _Tp = __CHEATF; _Alloc = "
    "std::allocator<__CHEATF>]':",
    MEDNAFEN_NGP_ARMHF_EXPECTED_NOTE_LINES[0],
    "  445 |       vector<_Tp, _Alloc>::",
    "      |       ^~~~~~~~~~~~~~~~~~~",
    "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
    "c++/13.2.0/vector:66:",
    "In member function 'void std::vector<_Tp, "
    "_Alloc>::push_back(const value_type&) [with _Tp = __CHEATF; "
    "_Alloc = std::allocator<__CHEATF>]',",
    "    inlined from 'int AddCheatEntry(char*, char*, uint32, uint64, "
    "uint64, int, char, unsigned int, bool)' at "
    "mednafen/mempatcher.cpp:167:20,",
    "    inlined from 'int MDFNI_AddCheat(const char*, uint32, uint64, "
    "uint64, char, unsigned int, bool)' at "
    "mednafen/mempatcher.cpp:198:21:",
    MEDNAFEN_NGP_ARMHF_EXPECTED_NOTE_LINES[1],
    " 1289 |           _M_realloc_insert(end(), __x);",
    "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~",
)
MEDNAFEN_NGP_EXPECTED_NOTE_LINES = {
    "arm64": (),
    "armhf": MEDNAFEN_NGP_ARMHF_EXPECTED_NOTE_LINES,
}
MEDNAFEN_NGP_ALLOWED_DIAGNOSTIC_CONTEXTS = {
    "arm64": (MEDNAFEN_NGP_WARNING_CONTEXT,),
    "armhf": (
        (*MEDNAFEN_NGP_WARNING_CONTEXT, *MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT),
        (*MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT, *MEDNAFEN_NGP_WARNING_CONTEXT),
    ),
}
MEDNAFEN_NGP_FORBIDDEN_LOG_FRAGMENTS = (
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
MEDNAFEN_NGP_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
MEDNAFEN_NGP_DIAGNOSTIC_SOURCE_RE = re.compile(
    r"^(?:/[^:]+|[A-Za-z0-9_./-]+): In (?:function|member function) .+$"
)
MEDNAFEN_NGP_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")

MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_ngp.yml",
    "source_url": "https://github.com/libretro/beetle-ngp-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "a50d5ac288a81f2104ddf43195a4efdd15c72227",
    "source_tree": "2614efc4a43347f75a16e4b87c536806f7de2ba1",
    "source_key": MEDNAFEN_NGP_CORE_ID,
    "source_dir": "libretro-mednafen_ngp",
    "output_path": "dist/unix/mednafen_ngp_libretro.so",
    "artifact_name": MEDNAFEN_NGP_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_ngp_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_ngp_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mednafen_ngp core must preserve its exact native "
    "version, source, recipe, metadata, and target contract"
)


def mednafen_ngp_spec_is_well_formed(spec: object) -> bool:
    """Require Neo Geo Pocket's complete immutable catalog identity."""

    identity = MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY
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


MEDNAFEN_NGP_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_NGP_CORE_ID,
    expected_compile_count=MEDNAFEN_NGP_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_NGP_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=MEDNAFEN_NGP_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        MEDNAFEN_NGP_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MEDNAFEN_NGP_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        MEDNAFEN_NGP_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_NGP_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_NGP_EXPECTED_LINK_OPTIONS,
    source_commit=MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY[
        "source_commit"
    ],
    source_tree=MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_ordered_link_argv_sha256=(
        MEDNAFEN_NGP_EXPECTED_ORDERED_LINK_ARGV_SHA256
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
        or line.startswith("In member function ")
        or line.lstrip().startswith(("from ", "inlined from "))
        or MEDNAFEN_NGP_DIAGNOSTIC_SOURCE_RE.fullmatch(line) is not None
        or MEDNAFEN_NGP_DIAGNOSTIC_CONTEXT_RE.match(line) is not None
    )


def mednafen_ngp_log_proves_contract(
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
    expected_link_argv = MEDNAFEN_NGP_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    expected_notes = MEDNAFEN_NGP_EXPECTED_NOTE_LINES.get(arch)
    allowed_diagnostic_contexts = (
        MEDNAFEN_NGP_ALLOWED_DIAGNOSTIC_CONTEXTS.get(arch)
    )
    if (
        expected_compilers is None
        or expected_cxx_compilers is None
        or expected_link_argv is None
        or expected_notes is None
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
    warning_positions = _sequence_positions(
        lines, MEDNAFEN_NGP_WARNING_CONTEXT
    )
    note_positions = (
        _sequence_positions(lines, MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT)
        if expected_notes
        else ()
    )
    success_positions = _sequence_positions(lines, MEDNAFEN_NGP_SUCCESS_MARKER)
    if (
        any(
            fragment in lowered_log
            for fragment in MEDNAFEN_NGP_FORBIDDEN_LOG_FRAGMENTS
        )
        or MEDNAFEN_NGP_MAKE_FAILURE_RE.search(build_log_text) is not None
        or source_lines != (MEDNAFEN_NGP_SOURCE_HEAD_MARKER,)
        or pipeline_marker_lines
        # Multiset: parallel make reorders per-TU warning blocks (see the
        # identical relaxation in mednafen_lynx, observed live).
        or Counter(warning_lines) != Counter(MEDNAFEN_NGP_EXPECTED_WARNING_LINES)
        or note_lines != expected_notes
        or Counter(diagnostic_context)
        not in [Counter(allowed) for allowed in allowed_diagnostic_contexts]
        or len(warning_positions) != 1
        or (bool(expected_notes) and len(note_positions) != 1)
        or len(success_positions) != 2
        or lines.count(MEDNAFEN_NGP_SUCCESS_MARKER[0]) != 2
        or lines.count(MEDNAFEN_NGP_SUCCESS_MARKER[1]) != 2
        or tuple(lines[-len(MEDNAFEN_NGP_SUCCESS_TRAILER) :])
        != MEDNAFEN_NGP_SUCCESS_TRAILER
        or lines.count(MEDNAFEN_NGP_SUCCESS_TRAILER[0]) != 1
        or build_log_text.count("-DGIT_VERSION=")
        != MEDNAFEN_NGP_NATIVE_GIT_VERSION_OCCURRENCE_COUNT
        or build_log_text.count(MEDNAFEN_NGP_NATIVE_GIT_VERSION_LOG_TOKEN)
        != MEDNAFEN_NGP_NATIVE_GIT_VERSION_OCCURRENCE_COUNT
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
            if invocation[:2] == ("libretro.o", "libretro.c"):
                libretro_compile_positions.append(line_number)
            if invocation[:2] == (
                "mednafen/mempatcher.o",
                "mednafen/mempatcher.cpp",
            ):
                mempatcher_compile_positions.append(line_number)
            expected_occurrences = (
                MEDNAFEN_NGP_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE[
                    "cxx" if tokens[0] in expected_cxx_compilers else "c"
                ]
            )
            if (
                line.count(MEDNAFEN_NGP_NATIVE_GIT_VERSION_LOG_TOKEN)
                != expected_occurrences
            ):
                return False
        elif MEDNAFEN_NGP_BUILD_ARTIFACT_NAME in tokens:
            link_invocations.append((line_number, tuple(tokens)))

    if not compile_positions or len(link_invocations) != 1:
        return False
    source_position = lines.index(MEDNAFEN_NGP_SOURCE_HEAD_MARKER)
    link_position, link_argv = link_invocations[0]
    warning_start = warning_positions[0]
    warning_end = warning_start + len(MEDNAFEN_NGP_WARNING_CONTEXT) - 1
    expected_link_position = len(lines) - len(MEDNAFEN_NGP_SUCCESS_TRAILER) - 1
    notes_are_framed = not expected_notes
    if expected_notes and len(mempatcher_compile_positions) == 1:
        note_start = note_positions[0]
        note_end = note_start + len(MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT) - 1
        notes_are_framed = (
            mempatcher_compile_positions[0] < note_start
            and note_end < link_position
        )
    if (
        len(compile_positions) != MEDNAFEN_NGP_EXPECTED_COMPILE_COUNT
        or len(libretro_compile_positions) != 1
        or len(mempatcher_compile_positions) != 1
        or link_argv != expected_link_argv
        or link_position != expected_link_position
        or not (libretro_compile_positions[0] < warning_start)
        or warning_end >= link_position
        or not notes_are_framed
        or max(diagnostic_positions) >= link_position
        or not (
            success_positions[0] < source_position < min(compile_positions)
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
        MEDNAFEN_NGP_LOG_CONTRACT,
    )
