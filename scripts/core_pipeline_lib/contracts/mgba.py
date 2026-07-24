"""Exact mGBA native-version C-only build-log contract."""

from __future__ import annotations

from collections import Counter
import re
import shlex

from .c_only import (
    COnlyLogContract,
    c_only_compile_invocation,
    c_only_log_proves_contract,
)
from .command_line import (
    command_line_is_lexically_safe,
    ordered_command_argv_sha256,
    output_option,
)
from .compiler import (
    COMPILER_COMMAND_RE,
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from .log_checks import sequence_positions as _sequence_positions, compiler_token_name as _compiler_token_name


MGBA_CORE_ID = "mgba"
MGBA_BUILD_ARTIFACT_NAME = "mgba_libretro.so"
MGBA_LOG_CONTRACT_ID = "mgba-c-only-v1"
MGBA_LOG_PROOF_KIND = "core-arch-source"

# This reviewed source tree used Git's repository-dependent default abbreviation
# and emitted nine characters. Active builds must fix ``core.abbrev=9`` before
# relying on this value; it is intentionally not mislabeled as short7/short10.
MGBA_NATIVE_GIT_VERSION_DERIVATION = "native-space-short9-v1"
MGBA_NATIVE_GIT_VERSION = " 6dce57eef"
MGBA_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" 6dce57eef"\"'
MGBA_NATIVE_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION=" 6dce57eef"'
MGBA_SOURCE_HEAD_MARKER = "HEAD is now at 6dce57eef Update .gitlab-ci.yml"
MGBA_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 6dce57eef"|file'
)
MGBA_COPY_COMMAND = (
    'cp "mgba_libretro.so" "/libretro-super/dist/unix/mgba_libretro.so"'
)
MGBA_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{MGBA_CORE_ID}",
)
MGBA_SUCCESS_TRAILER = (MGBA_COPY_COMMAND, *MGBA_SUCCESS_MARKER)
MGBA_FETCH_PREFIX = (
    "PLATFORM: Linux",
    "ARCHITECTURE: x86_64",
    "TARGET: unix",
    "=== mGBA",
    "Fetching mgba...",
    'git clone "https://github.com/libretro/mgba.git" '
    '"/libretro-super/libretro-mgba"',
    "Cloning into '/libretro-super/libretro-mgba'...",
)

MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mgba.yml",
    "source_url": "https://github.com/libretro/mgba.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "6dce57eef127dc4cc292644f38196e0e7c58590c",
    "source_tree": "72edb48f24f569f2b00c850cac61f6db0c80bf4e",
    "source_key": MGBA_CORE_ID,
    "source_dir": "libretro-mgba",
    "output_path": "dist/unix/mgba_libretro.so",
    "artifact_name": MGBA_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/mgba_libretro.info",
    "metadata_artifact_name": "mgba_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile.libretro",
}
MGBA_EXPECTED_COMPILE_COUNT = 98
MGBA_EXPECTED_COMPILE_PAIR_SHA256 = (
    "4a11224ca75acb1bb9852726123bb7d5ef68b4abaa38387778ff603e4f6e4b8f"
)
MGBA_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "bf31fee7eeb1f5990b97ff05f226c34c1d6c10cb8391f1568acb2658ce413435",
    "armhf": "eda9ddd79a86bfbe4f40074ff0e9396fe38440fbb02404fb9b472f08b315cad5",
}
MGBA_EXPECTED_RAW_COMPILE_INVOCATION_SHA256 = {
    "arm64": "1a7b855b4d7ecbf31cb0b8120f7daf6d07ff72a2b5e0360b2e25232fc9b39da1",
    "armhf": "6ac96399a5943a658340a00c417e9f00ea99f2a08cbd2341c710bc747d107c5a",
}
MGBA_EXPECTED_LINK_OBJECT_SHA256 = (
    "76a27bd26c1667bbefa698a7d0fed9f0a6dcfe21490ed6a7b85de9465c0ae373"
)
MGBA_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "98e4bef5222b75be7c1aeb664c1802acd174612a28dacf3100f1f3159c9e9b5e"
)
MGBA_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-lm",
)
MGBA_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "927d3d342bc21d237e61c903215296fac670e8c9e2df932a1686d7f18dc7ee64",
    "armhf": "5a4d6a0f0f60347c3f4ca681ec51a8b96784e4949655815a2553a7a45917799c",
}

MGBA_EXPECTED_RAW_LINK_OBJECTS = tuple(
    """
./src/arm/arm.o
./src/arm/decoder.o
./src/arm/decoder-arm.o
./src/arm/decoder-thumb.o
./src/arm/isa-thumb.o
./src/arm/isa-arm.o
./src/core/bitmap-cache.o
./src/core/cache-set.o
./src/core/cheats.o
./src/core/config.o
./src/core/core.o
./src/core/interface.o
./src/core/lockstep.o
./src/core/log.o
./src/core/map-cache.o
./src/core/sync.o
./src/core/thread.o
./src/core/tile-cache.o
./src/core/core-serialize.o
./src/core/timing.o
./src/gb/audio.o
./src/gb/cheats.o
./src/gb/core.o
./src/gb/gb.o
./src/gb/io.o
./src/gb/mbc.o
./src/gb/mbc/huc-3.o
./src/gb/mbc/licensed.o
./src/gb/mbc/mbc.o
./src/gb/mbc/pocket-cam.o
./src/gb/mbc/tama5.o
./src/gb/mbc/unlicensed.o
./src/gb/memory.o
./src/gb/overrides.o
./src/gb/renderers/cache-set.o
./src/gb/renderers/software.o
./src/gb/serialize.o
./src/gb/sio.o
./src/gb/timer.o
./src/gb/video.o
./src/gba/audio.o
./src/gba/bios.o
./src/gba/cheats.o
./src/gba/cheats/gameshark.o
./src/gba/cheats/parv3.o
./src/gba/cheats/codebreaker.o
./src/gba/core.o
./src/gba/dma.o
./src/gba/gba.o
./src/gba/cart/gpio.o
./src/gba/cart/ereader.o
./src/gba/cart/unlicensed.o
./src/gba/hle-bios.o
./src/gba/input.o
./src/gba/io.o
./src/gba/cart/matrix.o
./src/gba/memory.o
./src/gba/overrides.o
./src/gba/renderers/cache-set.o
./src/gba/renderers/common.o
./src/gba/renderers/software-mode0.o
./src/gba/renderers/software-obj.o
./src/gba/renderers/software-bg.o
./src/gba/renderers/video-software.o
./src/gba/savedata.o
./src/gba/serialize.o
./src/gba/sio.o
./src/gba/sio/gbp.o
./src/gba/timer.o
./src/gba/cart/vfame.o
./src/gba/video.o
./src/platform/libretro/memory.o
./src/platform/libretro/libretro.o
./src/sm83/isa-sm83.o
./src/sm83/sm83.o
./src/third-party/inih/ini.o
./src/util/audio-buffer.o
./src/util/audio-resampler.o
./src/util/interpolator.o
./src/util/circle-buffer.o
./src/util/configuration.o
./src/util/formatting.o
./src/util/gbk-table.o
./src/util/geometry.o
./src/util/hash.o
./src/util/image.o
./src/util/md5.o
./src/util/sha1.o
./src/util/patch.o
./src/util/patch-ips.o
./src/util/patch-ups.o
./src/util/string.o
./src/util/table.o
./src/util/vector.o
./src/util/vfs.o
./src/util/vfs/vfs-mem.o
./src/util/crc32.o
./src/util/vfs/vfs-fd.o
""".split()
)
MGBA_EXPECTED_COMPILE_PAIRS = tuple(
    (
        raw_object.removeprefix("./"),
        raw_object.removeprefix("./").removesuffix(".o") + ".c",
    )
    for raw_object in MGBA_EXPECTED_RAW_LINK_OBJECTS
)
MGBA_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-o",
        MGBA_BUILD_ARTIFACT_NAME,
        "-shared",
        "-Wl,-version-script=link.T",
        *MGBA_EXPECTED_RAW_LINK_OBJECTS,
        "-lm",
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }.items()
}
MGBA_OBJECT_CLEAN_COMMAND = (
    " ".join(("rm", "-f", *MGBA_EXPECTED_RAW_LINK_OBJECTS)) + " "
)
MGBA_ARTIFACT_CLEAN_COMMAND = f"rm -f {MGBA_BUILD_ARTIFACT_NAME}"
MGBA_COMPILER_TOOLCHAINS = {
    "arm64": (
        "aarch64-linux-gnu-gcc",
        "aarch64-linux-gnu-g++",
        "aarch64-linux-gnu-strip",
        "make",
    ),
    "armhf": (
        "arm-a30-linux-gnueabihf-gcc",
        "arm-a30-linux-gnueabihf-g++",
        "arm-a30-linux-gnueabihf-strip",
        "gmake",
    ),
}

MGBA_ARM64_WARNING_LINE = (
    "src/util/vfs/vfs-fd.c:234:2: warning: ignoring return value of "
    "'ftruncate', declared with attribute warn_unused_result [-Wunused-result]"
)
MGBA_ARM64_DIAGNOSTIC_LINES = (
    "src/util/vfs/vfs-fd.c: In function '_vfdTruncate':",
    MGBA_ARM64_WARNING_LINE,
    "  234 |  ftruncate(vfd->fd, size);",
    "      |  ^~~~~~~~~~~~~~~~~~~~~~~~",
)
MGBA_EXPECTED_WARNING_LINES = {
    "arm64": (MGBA_ARM64_WARNING_LINE,),
    "armhf": (),
}
MGBA_EXPECTED_NOTE_LINES = {"arm64": (), "armhf": ()}
MGBA_EXPECTED_DIAGNOSTIC_LINES = {
    "arm64": MGBA_ARM64_DIAGNOSTIC_LINES,
    "armhf": (),
}
MGBA_DIAGNOSTIC_OWNER_SOURCE = {
    "arm64": "src/util/vfs/vfs-fd.c",
    "armhf": None,
}

MGBA_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
MGBA_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def mgba_spec_is_well_formed(spec: object) -> bool:
    """Require mGBA's complete immutable catalog and short-9 identity."""

    identity = MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": MGBA_NATIVE_GIT_VERSION_DERIVATION,
                    "value": MGBA_NATIVE_GIT_VERSION,
                    "compiler_scope": identity["compiler_scope"],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def mgba_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed mGBA tree."""

    identity = MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == MGBA_CORE_ID
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


def mgba_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted mGBA native-version build record."""

    identity = MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and mgba_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": MGBA_NATIVE_GIT_VERSION_DERIVATION,
                "value": MGBA_NATIVE_GIT_VERSION,
                "compiler_scope": identity["compiler_scope"],
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


MGBA_LOG_CONTRACT = COnlyLogContract(
    core_id=MGBA_CORE_ID,
    expected_compile_count=MGBA_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=MGBA_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        MGBA_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MGBA_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=MGBA_EXPECTED_RAW_LINK_OBJECT_SHA256,
    expected_link_invocation_sha256=(
        MGBA_EXPECTED_ORDERED_LINK_ARGV_SHA256
    ),
    expected_raw_compile_invocation_sha256=(
        MGBA_EXPECTED_RAW_COMPILE_INVOCATION_SHA256
    ),
    build_artifact_name=MGBA_BUILD_ARTIFACT_NAME,
    expected_link_options=MGBA_EXPECTED_LINK_OPTIONS,
    source_commit=MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
)


def _mgba_markers_are_exact(
    lines: list[str]
) -> bool:
    source_markers = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    pipeline_markers = tuple(
        line for line in lines if line.startswith("CORE_PIPELINE_")
    )
    expected_pipeline_markers = (
        (MGBA_NATIVE_VERSION_MARKER,)
    )
    return bool(
        source_markers == (MGBA_SOURCE_HEAD_MARKER,)
        and pipeline_markers == expected_pipeline_markers
    )


def _mgba_allowed_compiler_metadata(arch: str) -> frozenset[str]:
    toolchain = MGBA_COMPILER_TOOLCHAINS.get(arch)
    if toolchain is None:
        return frozenset()
    c_compiler, cxx_compiler, _strip, _make = toolchain
    return frozenset(
        {
            f"CC = {c_compiler}",
            f"CXX = {cxx_compiler}",
            f"CXX11 = {cxx_compiler}",
            f"CXX17 = {cxx_compiler}",
            f'Compiler: CC="{c_compiler}" CXX="{cxx_compiler}"',
        }
    )


def _mgba_build_invocation_metadata_is_allowed(
    line: str, arch: str
) -> bool:
    toolchain = MGBA_COMPILER_TOOLCHAINS.get(arch)
    if toolchain is None:
        return False
    c_compiler, cxx_compiler, _strip, make = toolchain
    return bool(
        re.fullmatch(
            re.escape(f'{make} -f Makefile.libretro platform="unix" -j')
            + r"[1-9][0-9]* "
            + re.escape(f'CC="{c_compiler}" CXX="{cxx_compiler}"'),
            line.rstrip(),
        )
    )


def _mgba_compile_and_link_scope_is_exact(
    lines: list[str], arch: str
) -> tuple[tuple[int, ...], dict[str, int], int] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    expected_link_argv = MGBA_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    allowed_metadata = _mgba_allowed_compiler_metadata(arch)
    if (
        expected_compilers is None
        or expected_cxx_compilers is None
        or expected_link_argv is None
        or not allowed_metadata
    ):
        return None
    expected_c_compilers = expected_compilers - expected_cxx_compilers

    compile_positions: list[int] = []
    compile_pairs: list[tuple[str, str]] = []
    source_positions: dict[str, int] = {}
    link_positions: list[int] = []
    for line_number, line in enumerate(lines):
        try:
            tokens = shlex.split(line)
        except ValueError:
            if line_may_name_target_compiler(line, expected_compilers):
                return None
            continue
        if not tokens:
            continue
        if any("@" in token for token in tokens):
            return None
        parsed_output = output_option(tokens)
        command_like = "-c" in tokens or parsed_output is not None
        names_compiler = any(
            COMPILER_COMMAND_RE.fullmatch(_compiler_token_name(token))
            is not None
            for token in tokens
        )
        if not command_like:
            if (
                names_compiler
                and line.rstrip() not in allowed_metadata
                and not _mgba_build_invocation_metadata_is_allowed(
                    line, arch
                )
            ):
                return None
            continue
        if not command_line_is_lexically_safe(line):
            return None
        if tokens[0] not in expected_c_compilers:
            return None
        if "-c" in tokens:
            invocation = c_only_compile_invocation(
                tokens,
                expected_c_compilers,
            )
            if invocation is None:
                return None
            output, source, _raw_tokens = invocation
            version_tokens = [
                token for token in tokens[1:] if "GIT_VERSION" in token
            ]
            if (
                version_tokens != [MGBA_NATIVE_GIT_VERSION_COMPILE_TOKEN]
                or source in source_positions
            ):
                return None
            compile_positions.append(line_number)
            compile_pairs.append((output, source))
            source_positions[source] = line_number
            continue
        if tuple(tokens) != expected_link_argv:
            return None
        if (
            ordered_command_argv_sha256(tokens)
            != MGBA_EXPECTED_ORDERED_LINK_ARGV_SHA256[arch]
        ):
            return None
        link_positions.append(line_number)

    if (
        Counter(compile_pairs) != Counter(MGBA_EXPECTED_COMPILE_PAIRS)
        or len(compile_positions) != MGBA_EXPECTED_COMPILE_COUNT
        or len(link_positions) != 1
    ):
        return None
    first_compile = compile_positions[0]
    if tuple(compile_positions) != tuple(
        range(first_compile, first_compile + MGBA_EXPECTED_COMPILE_COUNT)
    ):
        return None
    return tuple(compile_positions), source_positions, link_positions[0]


def _mgba_log_envelope_is_exact(
    lines: list[str], arch: str
) -> bool:
    if not _mgba_markers_are_exact(
        lines
    ):
        return False
    commands = _mgba_compile_and_link_scope_is_exact(lines, arch)
    expected_diagnostics = MGBA_EXPECTED_DIAGNOSTIC_LINES.get(arch)
    if commands is None or expected_diagnostics is None:
        return False
    compile_positions, source_positions, link_position = commands
    success_positions = _sequence_positions(lines, MGBA_SUCCESS_MARKER)
    object_clean_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line == MGBA_OBJECT_CLEAN_COMMAND
    )
    artifact_clean_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line == MGBA_ARTIFACT_CLEAN_COMMAND
    )
    copy_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line == MGBA_COPY_COMMAND
    )
    artifact_positions = tuple(
        position
        for position, line in enumerate(lines)
        if MGBA_BUILD_ARTIFACT_NAME in line
    )
    semantic_objects = tuple(
        raw_object.removeprefix("./")
        for raw_object in MGBA_EXPECTED_RAW_LINK_OBJECTS
    )
    object_positions = tuple(
        position
        for position, line in enumerate(lines)
        if any(object_name in line for object_name in semantic_objects)
    )
    if (
        tuple(lines[-len(MGBA_SUCCESS_TRAILER) :])
        != MGBA_SUCCESS_TRAILER
        or len(success_positions) != 2
        or len(object_clean_positions) != 1
        or len(artifact_clean_positions) != 1
        or len(copy_positions) != 1
        or artifact_positions
        != (artifact_clean_positions[0], link_position, copy_positions[0])
        or object_positions
        != (object_clean_positions[0], *compile_positions, link_position)
    ):
        return False

    source_position = lines.index(MGBA_SOURCE_HEAD_MARKER)
    marker_position = lines.index(MGBA_NATIVE_VERSION_MARKER)
    if marker_position != source_position + 1:
        return False

    toolchain = MGBA_COMPILER_TOOLCHAINS.get(arch)
    if toolchain is None:
        return False
    c_compiler, cxx_compiler, strip, make = toolchain
    pipeline_markers = (MGBA_NATIVE_VERSION_MARKER,)
    expected_prefix = (
        *MGBA_FETCH_PREFIX,
        *MGBA_SUCCESS_MARKER,
        MGBA_SOURCE_HEAD_MARKER,
        *pipeline_markers,
        "PLATFORM: Linux",
        "ARCHITECTURE: x86_64",
        "TARGET: unix",
        f"CC = {c_compiler}",
        f"CXX = {cxx_compiler}",
        f"CXX11 = {cxx_compiler}",
        f"CXX17 = {cxx_compiler}",
        f"STRIP = {strip}",
        f'Compiler: CC="{c_compiler}" CXX="{cxx_compiler}"',
        "=== x86 CPU detected... ===",
        "=== x86_64 CPU detected... ===",
        "unix",
        "unix",
        "=== mGBA",
        "Building mgba...",
        'cd "/libretro-super/libretro-mgba"',
    )
    clean_invocation_position = len(expected_prefix)
    if (
        tuple(lines[:clean_invocation_position]) != expected_prefix
        or object_clean_positions[0] != clean_invocation_position + 1
        or artifact_clean_positions[0] != object_clean_positions[0] + 1
        or compile_positions[0] != artifact_clean_positions[0] + 2
    ):
        return False
    clean_match = re.fullmatch(
        re.escape(f'{make} -f Makefile.libretro platform="unix" -j')
        + r"([1-9][0-9]*)  clean",
        lines[clean_invocation_position],
    )
    if clean_match is None:
        return False
    jobs = clean_match.group(1)
    expected_build_invocation = (
        f'{make} -f Makefile.libretro platform="unix" -j{jobs} '
        f'CC="{c_compiler}" CXX="{cxx_compiler}" '
    )
    if lines[artifact_clean_positions[0] + 1] != expected_build_invocation:
        return False

    diagnostic_position = compile_positions[-1] + 1
    if (
        tuple(
            lines[
                diagnostic_position : diagnostic_position
                + len(expected_diagnostics)
            ]
        )
        != expected_diagnostics
        or link_position != diagnostic_position + len(expected_diagnostics)
    ):
        return False
    owner_source = MGBA_DIAGNOSTIC_OWNER_SOURCE[arch]
    if owner_source is not None:
        owner_position = source_positions.get(owner_source)
        if owner_position is None or owner_position >= diagnostic_position:
            return False

    return bool(
        success_positions[0] + len(MGBA_SUCCESS_MARKER) == source_position
        and source_position <= marker_position < object_clean_positions[0]
        and object_clean_positions[0] < compile_positions[0]
        and copy_positions[0] == link_position + 1
        and success_positions[1] == link_position + 2
    )


def _mgba_diagnostics_and_version_are_exact(
    build_log_text: str, arch: str
) -> bool:
    expected_warning_lines = MGBA_EXPECTED_WARNING_LINES.get(arch)
    expected_note_lines = MGBA_EXPECTED_NOTE_LINES.get(arch)
    if expected_warning_lines is None or expected_note_lines is None:
        return False
    lowered_log = build_log_text.casefold()
    lines = build_log_text.splitlines()
    return bool(
        not any(
            marker in lowered_log
            for marker in MGBA_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        and MGBA_MAKE_FAILURE_RE.search(build_log_text) is None
        and Counter(
            line for line in lines if "warning:" in line.casefold()
        )
        == Counter(expected_warning_lines)
        and Counter(line for line in lines if "note:" in line.casefold())
        == Counter(expected_note_lines)
        and "CORE_PIPELINE_GIT_VERSION" not in build_log_text
        and build_log_text.count("-DGIT_VERSION=")
        == MGBA_EXPECTED_COMPILE_COUNT
        and build_log_text.count(MGBA_NATIVE_GIT_VERSION_LOG_TOKEN)
        == MGBA_EXPECTED_COMPILE_COUNT
    )


def _mgba_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    if not isinstance(build_log_text, str):
        return False
    return bool(
        _mgba_diagnostics_and_version_are_exact(build_log_text, arch)
        and _mgba_log_envelope_is_exact(
            build_log_text.splitlines(),
            arch,
            )
        and c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            MGBA_LOG_CONTRACT,
        )
    )


def mgba_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the active marker-backed mGBA build contract."""

    return _mgba_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
    )
