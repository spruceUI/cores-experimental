"""Exact Mednafen PCE Fast C-only compile and C++ link contract."""

from __future__ import annotations

import re
import shlex

from .compiler import TARGET_COMPILERS, TARGET_CXX_COMPILERS
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)
from .log_checks import sequence_positions as _sequence_positions


MEDNAFEN_PCE_FAST_CORE_ID = "mednafen_pce_fast"
MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME = (
    "mednafen_pce_fast_libretro.so"
)
MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_COUNT = 92
MEDNAFEN_PCE_FAST_EXPECTED_LANGUAGE_COUNTS = {"c": 92}
MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_PAIR_SHA256 = (
    "a1868c0b32b6cb09f36659da821c92f1e67ab74c3661c5db035dd0e0c1a22651"
)
MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "1ba39c8ccf01c079d36c7c3c254fb61b65f2f986216ef63a65240223577df5a3",
    "armhf": "fad2707687674019f915ddf3949384e669629e4222cd55b28ca3adc844ab5019",
}
MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECT_SHA256 = (
    "4a8a606fabae2257c0a828036f4555717a8055aa83832254997998c6e3df6401"
)
MEDNAFEN_PCE_FAST_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "4a8a606fabae2257c0a828036f4555717a8055aa83832254997998c6e3df6401"
)
MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "95fc0641f3658d4ec9a0d78189f4da1d7ebb021f116f0e6ec5eb1dcd4a5b7207",
    "armhf": "1ba9fc35d3dd19bd5cec7bd6281dc2e8a446068dd9f0404557461b636cfffa02",
}
MEDNAFEN_PCE_FAST_EXPECTED_LINK_OPTIONS = (
    "-lrt",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECTS = (
    "libretro-common/cdrom/cdrom.o",
    "libretro-common/vfs/vfs_implementation_cdrom.o",
    "mednafen/hw_misc/arcade_card/arcade_card.o",
    "mednafen/pce_fast/pcecd_drive.o",
    "mednafen/pce_fast/pcecd.o",
    "mednafen/pce_fast/psg.o",
    "mednafen/pce_fast/huc6280.o",
    "mednafen/pce_fast/input.o",
    "mednafen/pce_fast/vdc.o",
    "mednafen/sound/Blip_Buffer.o",
    "mednafen/cdrom/CDAccess.o",
    "mednafen/cdrom/CDAccess_Image.o",
    "mednafen/cdrom/CDAccess_CCD.o",
    "mednafen/cdrom/audioreader.o",
    "mednafen/cdrom/cdromif.o",
    "mednafen/cdrom/CDUtility.o",
    "mednafen/cdrom/lec.o",
    "mednafen/cdrom/galois.o",
    "mednafen/cdrom/l-ec.o",
    "mednafen/cdrom/edc_crc32.o",
    "mednafen/cdrom/recover-raw.o",
    "deps/lzma-19.00/src/Alloc.o",
    "deps/lzma-19.00/src/Bra86.o",
    "deps/lzma-19.00/src/BraIA64.o",
    "deps/lzma-19.00/src/CpuArch.o",
    "deps/lzma-19.00/src/Delta.o",
    "deps/lzma-19.00/src/LzFind.o",
    "deps/lzma-19.00/src/Lzma86Dec.o",
    "deps/lzma-19.00/src/LzmaDec.o",
    "deps/lzma-19.00/src/LzmaEnc.o",
    "deps/libchdr/src/libchdr_bitstream.o",
    "deps/libchdr/src/libchdr_cdrom.o",
    "deps/libchdr/src/libchdr_chd.o",
    "deps/libchdr/src/libchdr_flac.o",
    "deps/libchdr/src/libchdr_huffman.o",
    "deps/zstd/lib/common/entropy_common.o",
    "deps/zstd/lib/common/error_private.o",
    "deps/zstd/lib/common/fse_decompress.o",
    "deps/zstd/lib/common/zstd_common.o",
    "deps/zstd/lib/common/xxhash.o",
    "deps/zstd/lib/decompress/huf_decompress.o",
    "deps/zstd/lib/decompress/zstd_ddict.o",
    "deps/zstd/lib/decompress/zstd_decompress.o",
    "deps/zstd/lib/decompress/zstd_decompress_block.o",
    "deps/zlib-1.2.11/adler32.o",
    "deps/zlib-1.2.11/crc32.o",
    "deps/zlib-1.2.11/inffast.o",
    "deps/zlib-1.2.11/inflate.o",
    "deps/zlib-1.2.11/inftrees.o",
    "deps/zlib-1.2.11/zutil.o",
    "mednafen/cdrom/CDAccess_CHD.o",
    "mednafen/tremor/bitwise.o",
    "mednafen/tremor/block.o",
    "mednafen/tremor/codebook.o",
    "mednafen/tremor/floor0.o",
    "mednafen/tremor/floor1.o",
    "mednafen/tremor/framing.o",
    "mednafen/tremor/info.o",
    "mednafen/tremor/mapping0.o",
    "mednafen/tremor/mdct.o",
    "mednafen/tremor/registry.o",
    "mednafen/tremor/res012.o",
    "mednafen/tremor/sharedbook.o",
    "mednafen/tremor/synthesis.o",
    "mednafen/tremor/vorbisfile.o",
    "mednafen/tremor/window.o",
    "libretro.o",
    "mednafen/general.o",
    "mednafen/cdstream.o",
    "mednafen/mempatcher.o",
    "mednafen/okiadpcm.o",
    "mednafen/file.o",
    "mednafen/settings.o",
    "mednafen/state.o",
    "mednafen/mednafen-endian.o",
    "libretro-common/streams/file_stream.o",
    "libretro-common/streams/file_stream_transforms.o",
    "libretro-common/file/file_path.o",
    "libretro-common/file/retro_dirent.o",
    "libretro-common/lists/string_list.o",
    "libretro-common/lists/dir_list.o",
    "libretro-common/compat/compat_strl.o",
    "libretro-common/compat/compat_snprintf.o",
    "libretro-common/compat/compat_posix_string.o",
    "libretro-common/compat/compat_strcasestr.o",
    "libretro-common/compat/fopen_utf8.o",
    "libretro-common/encodings/encoding_utf.o",
    "libretro-common/encodings/encoding_crc32.o",
    "libretro-common/memmap/memalign.o",
    "libretro-common/string/stdstring.o",
    "libretro-common/time/rtime.o",
    "libretro-common/vfs/vfs_implementation.o",
)
MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-o",
        MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME,
        *MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECTS,
        *MEDNAFEN_PCE_FAST_EXPECTED_LINK_OPTIONS,
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-g++",
        "armhf": "arm-a30-linux-gnueabihf-g++",
    }.items()
}

MEDNAFEN_PCE_FAST_SOURCE_HEAD_MARKER = (
    "HEAD is now at 0bc6c86 Fetch translations & Recreate "
    "libretro_core_options_intl.h"
)
MEDNAFEN_PCE_FAST_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{MEDNAFEN_PCE_FAST_CORE_ID}",
)
MEDNAFEN_PCE_FAST_SUCCESS_TRAILER = (
    'cp "mednafen_pce_fast_libretro.so" '
    '"/libretro-super/dist/unix/mednafen_pce_fast_libretro.so"',
    *MEDNAFEN_PCE_FAST_SUCCESS_MARKER,
)

MEDNAFEN_PCE_FAST_FORBIDDEN_LOG_FRAGMENTS = (
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
MEDNAFEN_PCE_FAST_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
MEDNAFEN_PCE_FAST_DIAGNOSTIC_SOURCE_RE = re.compile(
    r"^(?:/[^:]+|[A-Za-z0-9_./+-]+): In "
    r"(?:function|member function) .+$"
)
MEDNAFEN_PCE_FAST_DIAGNOSTIC_CONTEXT_RE = re.compile(
    r"^\s+(?:\d+ )?\|"
)

MEDNAFEN_PCE_FAST_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_pce_fast.yml",
    "source_url": (
        "https://github.com/libretro/beetle-pce-fast-libretro.git"
    ),
    "source_requested_ref": "refs/heads/master",
    "source_commit": "0bc6c86928343ca4202c5b6ef33fa4387c47fc12",
    "source_tree": "80bd8d86bb10d9ab374d6de4ca3e129498c3c3e0",
    "source_key": MEDNAFEN_PCE_FAST_CORE_ID,
    "source_dir": "libretro-mednafen_pce_fast",
    "output_path": "dist/unix/mednafen_pce_fast_libretro.so",
    "artifact_name": MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_pce_fast_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_pce_fast_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mednafen_pce_fast core must preserve its exact "
    "source, recipe, metadata, and target contract"
)


def mednafen_pce_fast_spec_is_well_formed(spec: object) -> bool:
    """Require PCE Fast's complete immutable catalog identity."""

    identity = MEDNAFEN_PCE_FAST_SPEC_IDENTITY
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


MEDNAFEN_PCE_FAST_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_PCE_FAST_CORE_ID,
    expected_compile_count=MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_PCE_FAST_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=(
        MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_PAIR_SHA256
    ),
    expected_compile_invocation_sha256=(
        MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=(
        MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECT_SHA256
    ),
    expected_raw_link_object_sha256=(
        MEDNAFEN_PCE_FAST_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_PCE_FAST_EXPECTED_LINK_OPTIONS,
    source_commit=MEDNAFEN_PCE_FAST_SPEC_IDENTITY["source_commit"],
    source_tree=MEDNAFEN_PCE_FAST_SPEC_IDENTITY["source_tree"],
    expected_ordered_link_argv_sha256=(
        MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV_SHA256
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
        or line.startswith("In function ")
        or line.startswith("In member function ")
        or line.lstrip().startswith(("from ", "inlined from "))
        or MEDNAFEN_PCE_FAST_DIAGNOSTIC_SOURCE_RE.fullmatch(line)
        is not None
        or MEDNAFEN_PCE_FAST_DIAGNOSTIC_CONTEXT_RE.match(line) is not None
    )


def mednafen_pce_fast_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove exact source, C compile, C++ link, and clean diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    expected_link_argv = MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV.get(
        arch
    )
    if (
        expected_compilers is None
        or expected_cxx_compilers is None
        or expected_link_argv is None
    ):
        return False

    lines = build_log_text.splitlines()
    lowered_log = build_log_text.casefold()
    source_lines = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    success_positions = _sequence_positions(
        lines, MEDNAFEN_PCE_FAST_SUCCESS_MARKER
    )
    if (
        any(
            fragment in lowered_log
            for fragment in MEDNAFEN_PCE_FAST_FORBIDDEN_LOG_FRAGMENTS
        )
        or MEDNAFEN_PCE_FAST_MAKE_FAILURE_RE.search(build_log_text)
        is not None
        or source_lines != (MEDNAFEN_PCE_FAST_SOURCE_HEAD_MARKER,)
        or any("CORE_PIPELINE_" in line for line in lines)
        or "GIT_VERSION" in build_log_text
        or any(_line_is_diagnostic_context(line) for line in lines)
        or len(success_positions) != 2
        or lines.count(MEDNAFEN_PCE_FAST_SUCCESS_MARKER[0]) != 2
        or lines.count(MEDNAFEN_PCE_FAST_SUCCESS_MARKER[1]) != 2
        or tuple(lines[-len(MEDNAFEN_PCE_FAST_SUCCESS_TRAILER) :])
        != MEDNAFEN_PCE_FAST_SUCCESS_TRAILER
        or lines.count(MEDNAFEN_PCE_FAST_SUCCESS_TRAILER[0]) != 1
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
            if tokens[0] in expected_cxx_compilers:
                return False
            compile_positions.append(line_number)
        elif MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME in tokens:
            link_invocations.append((line_number, tuple(tokens)))

    if not compile_positions or len(link_invocations) != 1:
        return False
    source_position = lines.index(MEDNAFEN_PCE_FAST_SOURCE_HEAD_MARKER)
    link_position, link_argv = link_invocations[0]
    expected_link_position = (
        len(lines) - len(MEDNAFEN_PCE_FAST_SUCCESS_TRAILER) - 1
    )
    if (
        len(compile_positions) != MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_COUNT
        or link_argv != expected_link_argv
        or link_position != expected_link_position
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
        MEDNAFEN_PCE_FAST_LOG_CONTRACT,
    )
