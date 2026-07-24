"""Exact Mednafen WonderSwan native-version mixed-language contract."""

from __future__ import annotations

from collections import Counter
import re
import shlex

from .compiler import TARGET_COMPILERS
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


MEDNAFEN_WSWAN_CORE_ID = "mednafen_wswan"
MEDNAFEN_WSWAN_BUILD_ARTIFACT_NAME = "mednafen_wswan_libretro.so"
MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
MEDNAFEN_WSWAN_NATIVE_GIT_VERSION = " da6d0d9"
MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" da6d0d9"\"'
)
MEDNAFEN_WSWAN_SOURCE_HEAD_MARKER = (
    "HEAD is now at da6d0d9 libretro: add webOS to CI (#102)"
)
MEDNAFEN_WSWAN_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" da6d0d9"|file'
)
MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_wswan.yml",
    "source_url": "https://github.com/libretro/beetle-wswan-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "da6d0d9acb8d4e9bd6725ab44225a275325d8352",
    "source_tree": "1387c79a0f2e8aad511a26fc4b1e272b152c691d",
    "source_key": MEDNAFEN_WSWAN_CORE_ID,
    "source_dir": "libretro-mednafen_wswan",
    "output_path": "dist/unix/mednafen_wswan_libretro.so",
    "artifact_name": MEDNAFEN_WSWAN_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_wswan_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_wswan_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
}

MEDNAFEN_WSWAN_EXPECTED_COMPILE_COUNT = 15
MEDNAFEN_WSWAN_EXPECTED_LANGUAGE_COUNTS = {"c": 14, "cxx": 1}
MEDNAFEN_WSWAN_EXPECTED_COMPILE_PAIR_SHA256 = (
    "acb083802bfa9b00f713af24e68b49ebddf383bca79cd4e67847e388f9b0f12a"
)
MEDNAFEN_WSWAN_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "78dc64b7f66f97d81b65d62c321a9933f9457647c736dff1107a7ccc75b89bd8",
    "armhf": "e894d5cf2f7a60c99a619ac1c3f15e4e67ef8cf021606f83fe967c0fdf722c80",
}
MEDNAFEN_WSWAN_EXPECTED_LINK_OBJECT_SHA256 = (
    "447ddc8ee8049bf6100fa08b75845d0f46d6dd6d3056fb4a53bb752d395cc3ef"
)
MEDNAFEN_WSWAN_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "447ddc8ee8049bf6100fa08b75845d0f46d6dd6d3056fb4a53bb752d395cc3ef"
)
MEDNAFEN_WSWAN_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
MEDNAFEN_WSWAN_EXPECTED_LINK_OBJECTS = (
    "mednafen/mempatcher.o",
    "mednafen/wswan/sound.o",
    "mednafen/wswan/interrupt.o",
    "mednafen/wswan/rtc.o",
    "mednafen/wswan/tcache.o",
    "mednafen/wswan/gfx.o",
    "mednafen/wswan/wswan-memory.o",
    "mednafen/wswan/v30mz.o",
    "mednafen/wswan/eeprom.o",
    "mednafen/sound/Blip_Buffer.o",
    "mednafen/state.o",
    "mednafen/settings.o",
    "libretro.o",
    "libretro-common/compat/compat_strl.o",
    "libretro-common/compat/compat_snprintf.o",
)
MEDNAFEN_WSWAN_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-o",
        MEDNAFEN_WSWAN_BUILD_ARTIFACT_NAME,
        *MEDNAFEN_WSWAN_EXPECTED_LINK_OBJECTS,
        *MEDNAFEN_WSWAN_EXPECTED_LINK_OPTIONS,
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-g++",
        "armhf": "arm-a30-linux-gnueabihf-g++",
    }.items()
}

MEDNAFEN_WSWAN_EXPECTED_WARNING_LINES = (
    "mednafen/wswan/v30mz.c:1239:40: warning: variable 'mult' set but not "
    "used [-Wunused-but-set-variable]",
    "mednafen/wswan/v30mz.c:1240:40: warning: variable 'mult' set but not "
    "used [-Wunused-but-set-variable]",
)
MEDNAFEN_WSWAN_WARNING_BLOCK = "\n".join(
    (
        "mednafen/wswan/v30mz.c: In function 'DoOP':",
        MEDNAFEN_WSWAN_EXPECTED_WARNING_LINES[0],
        " 1239 |          OP( 0xd4, i_aam    ) { uint32 mult=FETCH; mult=0; "
        "I.regs.b[AH] = I.regs.b[AL] / 10; I.regs.b[AL] %= 10; "
        "SetSZPF_Word(I.regs.w[AW]); CLK(17); } OP_EPILOGUE;",
        "      |                                        ^~~~",
        MEDNAFEN_WSWAN_EXPECTED_WARNING_LINES[1],
        " 1240 |          OP( 0xd5, i_aad    ) { uint32 mult=FETCH; mult=0; "
        "I.regs.b[AL] = I.regs.b[AH] * 10 + I.regs.b[AL]; "
        "I.regs.b[AH] = 0; SetSZPF_Byte(I.regs.b[AL]); CLK(6); } "
        "OP_EPILOGUE;",
        "      |                                        ^~~~",
    )
)
MEDNAFEN_WSWAN_ARMHF_EXPECTED_NOTE_LINES = (
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "vector.tcc:445:7: note: parameter passing for argument of type "
    "'std::vector<__CHEATF>::iterator' changed in GCC 7.1",
    "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
    "stl_vector.h:1289:28: note: parameter passing for argument of type "
    "'__gnu_cxx::__normal_iterator<__CHEATF*, std::vector<__CHEATF> >' "
    "changed in GCC 7.1",
)
MEDNAFEN_WSWAN_ARMHF_NOTE_BLOCK = "\n".join(
    (
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:72,",
        "                 from mednafen/mempatcher.cpp:22:",
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc: In member function 'void std::vector<_Tp, "
        "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
        "{const __CHEATF&}; _Tp = __CHEATF; _Alloc = "
        "std::allocator<__CHEATF>]':",
        MEDNAFEN_WSWAN_ARMHF_EXPECTED_NOTE_LINES[0],
        "  445 |       vector<_Tp, _Alloc>::",
        "      |       ^~~~~~~~~~~~~~~~~~~",
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:66:",
        "In member function 'void std::vector<_Tp, "
        "_Alloc>::push_back(const value_type&) [with _Tp = __CHEATF; "
        "_Alloc = std::allocator<__CHEATF>]',",
        "    inlined from 'int AddCheatEntry(char*, char*, uint32, uint64, "
        "uint64, int, char, unsigned int, bool)' at "
        "mednafen/mempatcher.cpp:145:20,",
        "    inlined from 'int MDFNI_AddCheat(const char*, uint32, uint64, "
        "uint64, char, unsigned int, bool)' at "
        "mednafen/mempatcher.cpp:176:21:",
        MEDNAFEN_WSWAN_ARMHF_EXPECTED_NOTE_LINES[1],
        " 1289 |           _M_realloc_insert(end(), __x);",
        "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~",
    )
)
MEDNAFEN_WSWAN_EXPECTED_DIAGNOSTIC_BLOCKS = {
    "arm64": (MEDNAFEN_WSWAN_WARNING_BLOCK,),
    "armhf": (
        MEDNAFEN_WSWAN_WARNING_BLOCK,
        MEDNAFEN_WSWAN_ARMHF_NOTE_BLOCK,
    ),
}
MEDNAFEN_WSWAN_EXPECTED_NOTE_LINES = {
    "arm64": (),
    "armhf": MEDNAFEN_WSWAN_ARMHF_EXPECTED_NOTE_LINES,
}
MEDNAFEN_WSWAN_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
MEDNAFEN_WSWAN_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def mednafen_wswan_spec_is_well_formed(spec: object) -> bool:
    """Require WonderSwan's complete catalog and native-version identity."""

    identity = MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": (
                        MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_DERIVATION
                    ),
                    "value": MEDNAFEN_WSWAN_NATIVE_GIT_VERSION,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def mednafen_wswan_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed WonderSwan tree."""

    identity = MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == MEDNAFEN_WSWAN_CORE_ID
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


def mednafen_wswan_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted WonderSwan native-version build record."""

    return bool(
        isinstance(build, dict)
        and source_commit
        == MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
        and mednafen_wswan_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_DERIVATION,
                "value": MEDNAFEN_WSWAN_NATIVE_GIT_VERSION,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


MEDNAFEN_WSWAN_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_WSWAN_CORE_ID,
    expected_compile_count=MEDNAFEN_WSWAN_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_WSWAN_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=(
        MEDNAFEN_WSWAN_EXPECTED_COMPILE_PAIR_SHA256
    ),
    expected_compile_invocation_sha256=(
        MEDNAFEN_WSWAN_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MEDNAFEN_WSWAN_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        MEDNAFEN_WSWAN_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_WSWAN_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_WSWAN_EXPECTED_LINK_OPTIONS,
    source_commit=(
        MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
    ),
    source_tree=(
        MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"]
    ),
)


def mednafen_wswan_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove source, version, compile, ordered link, and diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_link_argv = MEDNAFEN_WSWAN_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    expected_diagnostic_blocks = (
        MEDNAFEN_WSWAN_EXPECTED_DIAGNOSTIC_BLOCKS.get(arch)
    )
    expected_note_lines = MEDNAFEN_WSWAN_EXPECTED_NOTE_LINES.get(arch)
    if (
        expected_compilers is None
        or expected_link_argv is None
        or expected_diagnostic_blocks is None
        or expected_note_lines is None
    ):
        return False

    lines = build_log_text.splitlines()
    lowered_log = build_log_text.casefold()
    source_head_lines = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    native_version_lines = tuple(
        line
        for line in lines
        if line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION|")
    )
    warning_lines = tuple(
        line for line in lines if "warning:" in line.casefold()
    )
    note_lines = tuple(line for line in lines if "note:" in line.casefold())
    if (
        any(
            marker in lowered_log
            for marker in MEDNAFEN_WSWAN_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or MEDNAFEN_WSWAN_MAKE_FAILURE_RE.search(build_log_text) is not None
        or Counter(warning_lines)
        != Counter(MEDNAFEN_WSWAN_EXPECTED_WARNING_LINES)
        or Counter(note_lines) != Counter(expected_note_lines)
        or source_head_lines != (MEDNAFEN_WSWAN_SOURCE_HEAD_MARKER,)
        or native_version_lines != (MEDNAFEN_WSWAN_NATIVE_VERSION_MARKER,)
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != MEDNAFEN_WSWAN_EXPECTED_COMPILE_COUNT
        or build_log_text.count(MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_LOG_TOKEN)
        != MEDNAFEN_WSWAN_EXPECTED_COMPILE_COUNT
    ):
        return False

    compile_positions: list[int] = []
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
        elif MEDNAFEN_WSWAN_BUILD_ARTIFACT_NAME in tokens:
            link_invocations.append((line_number, tuple(tokens)))
    if (
        not compile_positions
        or len(link_invocations) != 1
        or link_invocations[0][1] != expected_link_argv
    ):
        return False

    source_position = lines.index(MEDNAFEN_WSWAN_SOURCE_HEAD_MARKER)
    version_position = lines.index(MEDNAFEN_WSWAN_NATIVE_VERSION_MARKER)
    link_position = link_invocations[0][0]
    if (
        not _diagnostic_context_lines_are_exact(
            build_log_text,
            expected_diagnostic_blocks,
            link_position,
        )
        or not (
            source_position < version_position < min(compile_positions)
            and max(compile_positions) < link_position
        )
    ):
        return False

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        MEDNAFEN_WSWAN_LOG_CONTRACT,
    )
