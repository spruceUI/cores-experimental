"""Exact Mednafen Virtual Boy mixed-language build-log contract."""

from __future__ import annotations

import re
import shlex

from .compiler import TARGET_COMPILERS
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)
from .log_checks import sequence_positions as _sequence_positions


MEDNAFEN_VB_CORE_ID = "mednafen_vb"
MEDNAFEN_VB_BUILD_ARTIFACT_NAME = "mednafen_vb_libretro.so"
MEDNAFEN_VB_EXPECTED_COMPILE_COUNT = 13
MEDNAFEN_VB_EXPECTED_LANGUAGE_COUNTS = {"c": 10, "cxx": 3}
MEDNAFEN_VB_EXPECTED_COMPILE_PAIR_SHA256 = (
    "6cb04e872fe9036b76a3ff8e46ebf1c7a5105f99f974e9a66d2d54d6961f3db1"
)
MEDNAFEN_VB_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "4c5a3f1fa866731c491c379546adf43e8a3c6c21a60763f2e8a3a6954b4fd76d",
    "armhf": "53e5830aba2b0cbcf5e23aaf274e528b84df9d19da9370dbecdb0acc6ddda2d1",
}
MEDNAFEN_VB_EXPECTED_LINK_OBJECT_SHA256 = (
    "df94b68d4cf87d090ac4a991a8833286a2e09554b53f06d656c8941370496860"
)
MEDNAFEN_VB_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "df94b68d4cf87d090ac4a991a8833286a2e09554b53f06d656c8941370496860"
)
# No ordered-link-argv pin: the Makefile's object list is filesystem enumeration
# order, which differs per host (GitHub runners produced the identical
# object multiset in a different order). The link stays pinned by the
# order-tolerant object multisets and the ordered option set.
MEDNAFEN_VB_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)

MEDNAFEN_VB_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
MEDNAFEN_VB_NATIVE_GIT_VERSION = " 38e7a0e"
MEDNAFEN_VB_NATIVE_GIT_VERSION_COMPILER_SCOPE = frozenset({"c", "cxx"})
MEDNAFEN_VB_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" 38e7a0e"\"'
)
MEDNAFEN_VB_SOURCE_HEAD_MARKER = (
    "HEAD is now at 38e7a0e Add a core option for opposite directions (#85)"
)
MEDNAFEN_VB_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{MEDNAFEN_VB_CORE_ID}",
)
MEDNAFEN_VB_SUCCESS_TRAILER = (
    'cp "mednafen_vb_libretro.so" '
    '"/libretro-super/dist/unix/mednafen_vb_libretro.so"',
    *MEDNAFEN_VB_SUCCESS_MARKER,
)

MEDNAFEN_VB_ARMHF_EXPECTED_NOTE_LINES = (
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "vector.tcc:445:7: note: parameter passing for argument of type "
    "'std::vector<__CHEATF>::iterator' changed in GCC 7.1",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "stl_vector.h:1289:28: note: parameter passing for argument of type "
    "'__gnu_cxx::__normal_iterator<__CHEATF*, std::vector<__CHEATF> >' "
    "changed in GCC 7.1",
)
MEDNAFEN_VB_ARMHF_DIAGNOSTIC_CONTEXT = (
    "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
    "c++/13.2.0/vector:72,",
    "                 from mednafen/mempatcher.cpp:25:",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "vector.tcc: In member function 'void std::vector<_Tp, "
    "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
    "{const __CHEATF&}; _Tp = __CHEATF; _Alloc = "
    "std::allocator<__CHEATF>]':",
    MEDNAFEN_VB_ARMHF_EXPECTED_NOTE_LINES[0],
    "  445 |       vector<_Tp, _Alloc>::",
    "      |       ^~~~~~~~~~~~~~~~~~~",
    "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
    "c++/13.2.0/vector:66:",
    "In member function 'void std::vector<_Tp, "
    "_Alloc>::push_back(const value_type&) [with _Tp = __CHEATF; "
    "_Alloc = std::allocator<__CHEATF>]',",
    "    inlined from 'int AddCheatEntry(char*, char*, uint32, uint64, "
    "uint64, int, char, unsigned int, bool)' at "
    "mednafen/mempatcher.cpp:160:18,",
    "    inlined from 'int MDFNI_AddCheat(const char*, uint32, uint64, "
    "uint64, char, unsigned int, bool)' at "
    "mednafen/mempatcher.cpp:194:19:",
    MEDNAFEN_VB_ARMHF_EXPECTED_NOTE_LINES[1],
    " 1289 |           _M_realloc_insert(end(), __x);",
    "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~",
)
MEDNAFEN_VB_EXPECTED_NOTE_LINES = {
    "arm64": (),
    "armhf": MEDNAFEN_VB_ARMHF_EXPECTED_NOTE_LINES,
}
MEDNAFEN_VB_EXPECTED_DIAGNOSTIC_CONTEXT = {
    "arm64": (),
    "armhf": MEDNAFEN_VB_ARMHF_DIAGNOSTIC_CONTEXT,
}
MEDNAFEN_VB_FORBIDDEN_LOG_FRAGMENTS = (
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
    "warning:",
)
MEDNAFEN_VB_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
MEDNAFEN_VB_DIAGNOSTIC_SOURCE_RE = re.compile(
    r"^(?:/[^:]+|[A-Za-z0-9_./-]+): In (?:function|member function) .+$"
)
MEDNAFEN_VB_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")

MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_vb.yml",
    "source_url": "https://github.com/libretro/beetle-vb-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "38e7a0ec9ac7079ca1c1e3dd9aaf5b56f527efca",
    "source_tree": "842c635c9a5fdbef374616f01fa2d57bf1ec3fa7",
    "source_key": MEDNAFEN_VB_CORE_ID,
    "source_dir": "libretro-mednafen_vb",
    "output_path": "dist/unix/mednafen_vb_libretro.so",
    "artifact_name": MEDNAFEN_VB_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_vb_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_vb_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mednafen_vb core must preserve its exact native "
    "version, source, recipe, metadata, and target contract"
)


def mednafen_vb_spec_is_well_formed(spec: object) -> bool:
    """Require Virtual Boy's complete immutable catalog identity."""

    identity = MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY
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


MEDNAFEN_VB_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_VB_CORE_ID,
    expected_compile_count=MEDNAFEN_VB_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_VB_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=MEDNAFEN_VB_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        MEDNAFEN_VB_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MEDNAFEN_VB_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        MEDNAFEN_VB_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_VB_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_VB_EXPECTED_LINK_OPTIONS,
    source_commit=MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY[
        "source_commit"
    ],
    source_tree=MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
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
        or MEDNAFEN_VB_DIAGNOSTIC_SOURCE_RE.fullmatch(line) is not None
        or MEDNAFEN_VB_DIAGNOSTIC_CONTEXT_RE.match(line) is not None
    )


def mednafen_vb_log_proves_contract(
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
    expected_notes = MEDNAFEN_VB_EXPECTED_NOTE_LINES.get(arch)
    expected_diagnostic_context = (
        MEDNAFEN_VB_EXPECTED_DIAGNOSTIC_CONTEXT.get(arch)
    )
    if (
        expected_compilers is None
        or expected_notes is None
        or expected_diagnostic_context is None
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
    note_lines = tuple(line for line in lines if "note:" in line.casefold())
    diagnostic_positions = tuple(
        position
        for position, line in enumerate(lines)
        if _line_is_diagnostic_context(line)
    )
    diagnostic_context = tuple(lines[position] for position in diagnostic_positions)
    success_positions = _sequence_positions(lines, MEDNAFEN_VB_SUCCESS_MARKER)
    if (
        any(
            fragment in lowered_log
            for fragment in MEDNAFEN_VB_FORBIDDEN_LOG_FRAGMENTS
        )
        or MEDNAFEN_VB_MAKE_FAILURE_RE.search(build_log_text) is not None
        or source_lines != (MEDNAFEN_VB_SOURCE_HEAD_MARKER,)
        or pipeline_marker_lines
        or note_lines != expected_notes
        or diagnostic_context != expected_diagnostic_context
        or len(success_positions) != 2
        or tuple(lines[-len(MEDNAFEN_VB_SUCCESS_TRAILER) :])
        != MEDNAFEN_VB_SUCCESS_TRAILER
        or lines.count(MEDNAFEN_VB_SUCCESS_TRAILER[0]) != 1
        or build_log_text.count("-DGIT_VERSION=")
        != MEDNAFEN_VB_EXPECTED_COMPILE_COUNT
        or build_log_text.count(MEDNAFEN_VB_NATIVE_GIT_VERSION_LOG_TOKEN)
        != MEDNAFEN_VB_EXPECTED_COMPILE_COUNT
    ):
        return False

    compile_positions: list[int] = []
    compile_lines: list[str] = []
    link_positions: list[int] = []
    for line_number, line in enumerate(lines):
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens or tokens[0] not in expected_compilers:
            continue
        if "-c" in tokens:
            compile_positions.append(line_number)
            compile_lines.append(line)
        elif MEDNAFEN_VB_BUILD_ARTIFACT_NAME in tokens:
            link_positions.append(line_number)
    source_position = lines.index(MEDNAFEN_VB_SOURCE_HEAD_MARKER)
    expected_link_position = len(lines) - len(MEDNAFEN_VB_SUCCESS_TRAILER) - 1
    if (
        len(compile_positions) != MEDNAFEN_VB_EXPECTED_COMPILE_COUNT
        or any(
            line.count(MEDNAFEN_VB_NATIVE_GIT_VERSION_LOG_TOKEN) != 1
            for line in compile_lines
        )
        or len(link_positions) != 1
        or link_positions[0] != expected_link_position
        or (
            bool(expected_diagnostic_context)
            and not (
                max(compile_positions) < min(diagnostic_positions)
                and max(diagnostic_positions) < link_positions[0]
            )
        )
        or not (
            success_positions[0] < source_position < min(compile_positions)
            and max(compile_positions) < link_positions[0]
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
        MEDNAFEN_VB_LOG_CONTRACT,
    )
