"""Exact Mednafen PC-FX portable mixed-language build contract."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
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


MEDNAFEN_PCFX_CORE_ID = "mednafen_pcfx"
PCFX_PORTABLE_MAKE_VARIABLES = {"IS_X86": 0}
PCFX_PORTABLE_MAKE_PROFILE = "mednafen-pcfx-portable-v1"
MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS = frozenset({"ARCH_X86"})
MEDNAFEN_PCFX_BUILD_ARTIFACT_NAME = "mednafen_pcfx_libretro.so"
MEDNAFEN_PCFX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
MEDNAFEN_PCFX_NATIVE_GIT_VERSION = " 650c30e"
MEDNAFEN_PCFX_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" 650c30e"\"'
)
MEDNAFEN_PCFX_NATIVE_GIT_VERSION_COMPILE_TOKEN = (
    '-DGIT_VERSION=" 650c30e"'
)
MEDNAFEN_PCFX_SOURCE_HEAD_MARKER = (
    "HEAD is now at 650c30e webOS: specify not x86 in Makefile (#102)"
)
MEDNAFEN_PCFX_MAKE_MARKERS = (
    "CORE_PIPELINE_MAKEFLAGS|IS_X86=0",
    "CORE_PIPELINE_MAKE_VARIABLE|IS_X86|0|command line",
)
MEDNAFEN_PCFX_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 650c30e"|file'
)

MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_pcfx.yml",
    "source_url": "https://github.com/libretro/beetle-pcfx-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "650c30ea2203636a1716675854d11c608ed6eacc",
    "source_tree": "de7ad272c9210e5dd7772a53a1480dbab47d49cc",
    "source_key": MEDNAFEN_PCFX_CORE_ID,
    "source_dir": "libretro-mednafen_pcfx",
    "output_path": "dist/unix/mednafen_pcfx_libretro.so",
    "artifact_name": MEDNAFEN_PCFX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_pcfx_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_pcfx_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "cxx",
    "make_variables": PCFX_PORTABLE_MAKE_VARIABLES,
    "native_makefile": "Makefile",
}

MEDNAFEN_PCFX_EXPECTED_COMPILE_COUNT = 94
MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS = {"c": 60, "cxx": 34}
MEDNAFEN_PCFX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e61c9c08bd49969baf71482752efdf818a78fa4cf02daa309179740c41919e1c"
)
MEDNAFEN_PCFX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "9cd4372cc4283f2ef1977e89f25e635fea06baf5db9fabe130610cddffdb8e12",
    "armhf": "b916efc119269ad1a247b886c57b7b4f26ecc398bfb9c9581d34908f9ab156a4",
}
MEDNAFEN_PCFX_EXPECTED_LINK_OBJECT_SHA256 = (
    "9481b21c046fd3db7c095917364c56293e8a28a1623eab13c39eeb185f861915"
)
MEDNAFEN_PCFX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9481b21c046fd3db7c095917364c56293e8a28a1623eab13c39eeb185f861915"
)
MEDNAFEN_PCFX_EXPECTED_LINK_OPTIONS = (
    "-pthread",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
MEDNAFEN_PCFX_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "8c7b6043811be9cf32cf07b40155bf321ce060e7fd20ffc74f745b22d2f5f03e",
    "armhf": "28c9762bd8f3ee84b526218d8f084de67a7913cc7405a1628c42888932238ef2",
}

MEDNAFEN_PCFX_EXPECTED_WARNING_LINES = {
    "arm64": (
        "mednafen/pcfx/input/gamepad.cpp:71:8: warning: variable "
        "'mode_changed' set but not used [-Wunused-but-set-variable]",
        "mednafen/cdrom/scsicd.cpp:1818:5: warning: suggest parentheses "
        "around operand of '!' or change '&' to '&&' or '!' to '~' "
        "[-Wparentheses]",
        "deps/libchdr/src/libchdr_chd.c:1162:6: warning: variable 'result' "
        "set but not used [-Wunused-but-set-variable]",
        "deps/libchdr/src/libchdr_chd.c:2271:37: warning: variable 'result' "
        "set but not used [-Wunused-but-set-variable]",
    ),
    "armhf": (
        "mednafen/pcfx/input/gamepad.cpp:71:8: warning: variable "
        "'mode_changed' set but not used [-Wunused-but-set-variable]",
        "mednafen/pcfx/soundbox.cpp:533:42: warning: unsigned conversion from "
        "'int64' {aka 'long long int'} to 'size_t' {aka 'unsigned int'} "
        "changes value from '-70368744177664' to '0' [-Woverflow]",
        "mednafen/pcfx/soundbox.cpp:533:80: warning: unsigned conversion from "
        "'int64' {aka 'long long int'} to 'size_t' {aka 'unsigned int'} "
        "changes value from '70364449210368' to '0' [-Woverflow]",
        "mednafen/cdrom/scsicd.cpp:1818:5: warning: suggest parentheses "
        "around operand of '!' or change '&' to '&&' or '!' to '~' "
        "[-Wparentheses]",
        "deps/libchdr/src/libchdr_chd.c:1162:13: warning: variable 'result' "
        "set but not used [-Wunused-but-set-variable]",
        "deps/libchdr/src/libchdr_chd.c:2271:37: warning: variable 'result' "
        "set but not used [-Wunused-but-set-variable]",
        "deps/libchdr/src/libchdr_chd.c:2531:17: warning: 'free' called on "
        "pointer 'codec' with nonzero offset 124 [-Wfree-nonheap-object]",
        "deps/libchdr/src/libchdr_chd.c:2531:17: warning: 'free' called on "
        "pointer 'codec' with nonzero offset 568 [-Wfree-nonheap-object]",
        "deps/libchdr/src/libchdr_chd.c:2531:17: warning: 'free' called on "
        "pointer 'codec' with nonzero offset 624 [-Wfree-nonheap-object]",
    ),
}
MEDNAFEN_PCFX_EXPECTED_NOTE_LINES = {
    "arm64": (),
    "armhf": (
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:445:7: note: parameter passing for argument of type "
        "'std::vector<__CHEATF>::iterator' changed in GCC 7.1",
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "stl_vector.h:1289:28: note: parameter passing for argument of type "
        "'__gnu_cxx::__normal_iterator<__CHEATF*, std::vector<__CHEATF> >' "
        "changed in GCC 7.1",
    ),
}

MEDNAFEN_PCFX_GAMEPAD_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "mednafen/pcfx/input/gamepad.cpp: In member function 'virtual void "
        "PCFX_Input_Gamepad::Frame(const void*)':",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["arm64"][0],
        "   71 |   bool mode_changed = false;",
        "      |        ^~~~~~~~~~~~",
    )
)
MEDNAFEN_PCFX_SCSICD_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "mednafen/cdrom/scsicd.cpp: In function 'void DoREADBase(uint32_t, "
        "uint32_t)':",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["arm64"][1],
        " 1818 |  if(!(toc.tracks[track].control) & 0x4)",
        "      |     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    )
)
MEDNAFEN_PCFX_ARM64_DECOMPRESS_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "deps/libchdr/src/libchdr_chd.c: In function 'decompress_v5_map':",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["arm64"][2],
        " 1162 |  int result = 0;",
        "      |      ^~~~~~",
    )
)
MEDNAFEN_PCFX_ARMHF_DECOMPRESS_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "deps/libchdr/src/libchdr_chd.c: In function 'decompress_v5_map':",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["armhf"][4],
        " 1162 |         int result = 0;",
        "      |             ^~~~~~",
    )
)
MEDNAFEN_PCFX_HUNK_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "deps/libchdr/src/libchdr_chd.c: In function "
        "'hunk_read_into_memory':",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["arm64"][3],
        " 2271 |                                 int result;",
        "      |                                     ^~~~~~",
    )
)
MEDNAFEN_PCFX_ARMHF_SOUNDBOX_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "mednafen/pcfx/soundbox.cpp: In function 'int "
        "SoundBox_StateAction(StateMem*, int, int)':",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["armhf"][1],
        "  533 |          clamp(&sbox.ResetAntiClick[ch], -((int64)0x4000 "
        "<< 32), (int64)0x3FFF << 32);",
        "      |                                          "
        "^~~~~~~~~~~~~~~~~~~~~~",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["armhf"][2],
        "  533 |          clamp(&sbox.ResetAntiClick[ch], -((int64)0x4000 "
        "<< 32), (int64)0x3FFF << 32);",
        "      |                                                                  "
        "~~~~~~~~~~~~~~^~~~~",
    )
)
MEDNAFEN_PCFX_ARMHF_FREE_124_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "In function 'zlib_codec_init',",
        "    inlined from 'cdfl_codec_init' at "
        "deps/libchdr/src/libchdr_chd.c:791:8,",
        "    inlined from 'cdfl_codec_init' at "
        "deps/libchdr/src/libchdr_chd.c:769:18:",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["armhf"][6],
        " 2531 |                 free(data);",
        "      |                 ^~~~~~~~~~",
    )
)
MEDNAFEN_PCFX_ARMHF_FREE_568_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "In function 'zlib_codec_init',",
        "    inlined from 'cdzl_codec_init' at "
        "deps/libchdr/src/libchdr_chd.c:686:8,",
        "    inlined from 'cdzl_codec_init' at "
        "deps/libchdr/src/libchdr_chd.c:668:18:",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["armhf"][7],
        " 2531 |                 free(data);",
        "      |                 ^~~~~~~~~~",
    )
)
MEDNAFEN_PCFX_ARMHF_FREE_624_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "In function 'zlib_codec_init',",
        "    inlined from 'cdlz_codec_init' at "
        "deps/libchdr/src/libchdr_chd.c:600:8:",
        MEDNAFEN_PCFX_EXPECTED_WARNING_LINES["armhf"][8],
        " 2531 |                 free(data);",
        "      |                 ^~~~~~~~~~",
    )
)
MEDNAFEN_PCFX_ARMHF_VECTOR_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:72,",
        "                 from mednafen/mempatcher.cpp:23:",
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc: In member function 'void std::vector<_Tp, "
        "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
        "{const __CHEATF&}; _Tp = __CHEATF; _Alloc = "
        "std::allocator<__CHEATF>]':",
        MEDNAFEN_PCFX_EXPECTED_NOTE_LINES["armhf"][0],
        "  445 |       vector<_Tp, _Alloc>::",
        "      |       ^~~~~~~~~~~~~~~~~~~",
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:66:",
        "In member function 'void std::vector<_Tp, "
        "_Alloc>::push_back(const value_type&) [with _Tp = __CHEATF; "
        "_Alloc = std::allocator<__CHEATF>]',",
        "    inlined from 'int AddCheatEntry(char*, char*, uint32, uint64, "
        "uint64, int, char, unsigned int, bool)' at "
        "mednafen/mempatcher.cpp:173:18,",
        "    inlined from 'int MDFNI_AddCheat(const char*, uint32, uint64, "
        "uint64, char, unsigned int, bool)' at "
        "mednafen/mempatcher.cpp:203:19:",
        MEDNAFEN_PCFX_EXPECTED_NOTE_LINES["armhf"][1],
        " 1289 |           _M_realloc_insert(end(), __x);",
        "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~",
    )
)
MEDNAFEN_PCFX_EXPECTED_DIAGNOSTIC_BLOCKS = {
    "arm64": (
        MEDNAFEN_PCFX_GAMEPAD_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_SCSICD_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARM64_DECOMPRESS_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_HUNK_DIAGNOSTIC_BLOCK,
    ),
    "armhf": (
        MEDNAFEN_PCFX_GAMEPAD_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARMHF_SOUNDBOX_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_SCSICD_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARMHF_DECOMPRESS_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_HUNK_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARMHF_FREE_124_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARMHF_FREE_568_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARMHF_FREE_624_DIAGNOSTIC_BLOCK,
        MEDNAFEN_PCFX_ARMHF_VECTOR_DIAGNOSTIC_BLOCK,
    ),
}
MEDNAFEN_PCFX_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
MEDNAFEN_PCFX_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def mednafen_pcfx_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable PC-FX portable catalog identity."""

    identity = MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": MEDNAFEN_PCFX_NATIVE_GIT_VERSION_DERIVATION,
                    "value": MEDNAFEN_PCFX_NATIVE_GIT_VERSION,
                    "compiler_scope": identity["compiler_scope"],
                },
                "make_variables": PCFX_PORTABLE_MAKE_VARIABLES,
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def mednafen_pcfx_golden_source_is_well_formed(
    core_id: object, source: object
) -> bool:
    """Bind a promoted PC-FX source record to the reviewed tree."""

    identity = MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == MEDNAFEN_PCFX_CORE_ID
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


def mednafen_pcfx_combined_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted PC-FX make and native-version contract."""

    identity = MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and mednafen_pcfx_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "make_variables": PCFX_PORTABLE_MAKE_VARIABLES,
            "git_version": {
                "derivation": MEDNAFEN_PCFX_NATIVE_GIT_VERSION_DERIVATION,
                "value": MEDNAFEN_PCFX_NATIVE_GIT_VERSION,
                "compiler_scope": identity["compiler_scope"],
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


MEDNAFEN_PCFX_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_PCFX_CORE_ID,
    expected_compile_count=MEDNAFEN_PCFX_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=MEDNAFEN_PCFX_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        MEDNAFEN_PCFX_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MEDNAFEN_PCFX_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        MEDNAFEN_PCFX_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_PCFX_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_PCFX_EXPECTED_LINK_OPTIONS,
    source_commit=MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY[
        "source_commit"
    ],
    source_tree=MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
)


def mednafen_pcfx_ordered_link_argv_sha256(tokens: list[str]) -> str:
    """Hash the complete ordered PC-FX linker argv without normalization."""

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
) -> bool:
    """Accept only a parallel interleaving of reviewed diagnostic streams."""

    expected_streams = tuple(
        tuple(block.splitlines()) for block in expected_context_blocks
    )
    expected_lines = Counter(
        line for stream in expected_streams for line in stream
    )
    actual_lines = tuple(
        line for line in build_log_text.splitlines() if line in expected_lines
    )
    if Counter(actual_lines) != expected_lines:
        return False

    states = {tuple(0 for _stream in expected_streams)}
    for line in actual_lines:
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


def _pcfx_markers_are_exact(lines: list[str]) -> bool:
    expected = (
        MEDNAFEN_PCFX_SOURCE_HEAD_MARKER,
        *MEDNAFEN_PCFX_MAKE_MARKERS,
        MEDNAFEN_PCFX_NATIVE_VERSION_MARKER,
    )
    observed = tuple(
        line
        for line in lines
        if line.startswith("HEAD is now at ")
        or line.startswith("CORE_PIPELINE_MAKE")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION")
    )
    return observed == expected


def _pcfx_compile_scope_is_exact(
    lines: list[str], arch: str
) -> tuple[list[int], list[tuple[int, list[str]]]] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        return None
    compile_positions: list[int] = []
    link_commands: list[tuple[int, list[str]]] = []
    c_count = 0
    cxx_count = 0
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return None
        if not tokens:
            continue
        compiler = Path(tokens[0]).name
        if "-c" in tokens:
            compile_positions.append(line_number)
            version_tokens = [
                token for token in tokens[1:] if "GIT_VERSION" in token
            ]
            if compiler in expected_cxx_compilers:
                cxx_count += 1
                if version_tokens != [
                    MEDNAFEN_PCFX_NATIVE_GIT_VERSION_COMPILE_TOKEN
                ]:
                    return None
            else:
                c_count += 1
                if version_tokens:
                    return None
            if any(
                macro in token
                for macro in MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS
                for token in tokens[1:]
            ):
                return None
            continue
        parsed_output = output_option(tokens)
        if (
            parsed_output is not None
            and parsed_output[0] == MEDNAFEN_PCFX_BUILD_ARTIFACT_NAME
        ):
            link_commands.append((line_number, tokens))
    if (
        c_count != MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS["c"]
        or cxx_count != MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS["cxx"]
        or len(compile_positions) != MEDNAFEN_PCFX_EXPECTED_COMPILE_COUNT
        or len(link_commands) != 1
    ):
        return None
    return compile_positions, link_commands


def mednafen_pcfx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove PC-FX portable markers, diagnostics, compile argv, and link."""

    if not isinstance(build_log_text, str):
        return False
    expected_warning_lines = MEDNAFEN_PCFX_EXPECTED_WARNING_LINES.get(arch)
    expected_note_lines = MEDNAFEN_PCFX_EXPECTED_NOTE_LINES.get(arch)
    expected_diagnostic_blocks = MEDNAFEN_PCFX_EXPECTED_DIAGNOSTIC_BLOCKS.get(
        arch
    )
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
            for marker in MEDNAFEN_PCFX_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or MEDNAFEN_PCFX_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS["cxx"]
        or build_log_text.count(MEDNAFEN_PCFX_NATIVE_GIT_VERSION_LOG_TOKEN)
        != MEDNAFEN_PCFX_EXPECTED_LANGUAGE_COUNTS["cxx"]
    ):
        return False
    lines = build_log_text.splitlines()
    if not _pcfx_markers_are_exact(lines):
        return False
    warning_lines = Counter(
        line for line in lines if "warning:" in line.casefold()
    )
    note_lines = Counter(line for line in lines if "note:" in line.casefold())
    if (
        warning_lines != Counter(expected_warning_lines)
        or note_lines != Counter(expected_note_lines)
        or not _diagnostic_context_lines_are_exact(
            build_log_text, expected_diagnostic_blocks
        )
    ):
        return False
    commands = _pcfx_compile_scope_is_exact(lines, arch)
    if commands is None:
        return False
    compile_positions, link_commands = commands
    link_position, link_tokens = link_commands[0]
    marker_position = lines.index(MEDNAFEN_PCFX_NATIVE_VERSION_MARKER)
    reviewed_diagnostic_lines = {
        line
        for block in expected_diagnostic_blocks
        for line in block.splitlines()
    }
    diagnostic_positions = [
        index
        for index, line in enumerate(lines)
        if line in reviewed_diagnostic_lines
    ]
    if (
        marker_position >= min(compile_positions)
        or max(compile_positions) >= link_position
        or (
            diagnostic_positions
            and max(diagnostic_positions) >= link_position
        )
        or mednafen_pcfx_ordered_link_argv_sha256(link_tokens)
        != MEDNAFEN_PCFX_EXPECTED_ORDERED_LINK_ARGV_SHA256.get(arch)
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        MEDNAFEN_PCFX_LOG_CONTRACT,
    )
