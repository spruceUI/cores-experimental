"""Exact VEmulator source-native mixed-language build-log contract."""

from __future__ import annotations

from collections import Counter
import re
import shlex

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
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_compile_invocation,
    mixed_language_log_proves_contract,
)
from .log_checks import sequence_positions as _sequence_positions, compiler_token_name as _compiler_token_name


VEMULATOR_CORE_ID = "vemulator"
VEMULATOR_BUILD_ARTIFACT_NAME = "vemulator_libretro.so"
VEMULATOR_LOG_CONTRACT_ID = "vemulator-mixed-language-v1"
VEMULATOR_LOG_PROOF_KIND = "core-arch-source"

# VEmulator does not accept an injected git-version macro. Its source and
# canonical metadata both report this literal runtime version instead.
VEMULATOR_NATIVE_RUNTIME_VERSION_DERIVATION = "source-literal-v1"
VEMULATOR_NATIVE_RUNTIME_VERSION = "0.1"
VEMULATOR_NATIVE_RUNTIME_VERSION_SOURCE = "main.cpp"
VEMULATOR_METADATA_DISPLAY_VERSION_SOURCE = "vemulator_libretro.info"

VEMULATOR_SOURCE_HEAD_MARKER = (
    "HEAD is now at 7fade95 Merge pull request #5 from cscd98/webos-ci"
)
VEMULATOR_SOURCE_IDENTITY_MARKER = (
    "CORE_PIPELINE_SOURCE_IDENTITY|vemulator|"
    "7fade95506201aed83316cc3f2efe3d7cecf75a7|"
    "09e8c0ec31c874ea555288c53c975e289e865c0a|catalog"
)
VEMULATOR_JOBS_MARKER_PREFIX = "CORE_PIPELINE_JOBS"
VEMULATOR_COPY_COMMAND = (
    'cp "vemulator_libretro.so" '
    '"/libretro-super/dist/unix/vemulator_libretro.so"'
)
VEMULATOR_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{VEMULATOR_CORE_ID}",
)
VEMULATOR_SUCCESS_TRAILER = (
    VEMULATOR_COPY_COMMAND,
    *VEMULATOR_SUCCESS_MARKER,
)
VEMULATOR_FETCH_PREFIX = (
    "PLATFORM: Linux",
    "ARCHITECTURE: x86_64",
    "TARGET: unix",
    "=== VEmulator",
    "Fetching vemulator...",
    'git clone "https://github.com/libretro/vemulator-libretro.git" '
    '"/libretro-super/libretro-vemulator"',
    "Cloning into '/libretro-super/libretro-vemulator'...",
)

VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-vemulator.yml",
    "source_url": "https://github.com/libretro/vemulator-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "7fade95506201aed83316cc3f2efe3d7cecf75a7",
    "source_tree": "09e8c0ec31c874ea555288c53c975e289e865c0a",
    "source_key": VEMULATOR_CORE_ID,
    "source_dir": "libretro-vemulator",
    "output_path": "dist/unix/vemulator_libretro.so",
    "artifact_name": VEMULATOR_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/vemulator_libretro.info"
    ),
    "metadata_artifact_name": "vemulator_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
    "native_runtime_version_derivation": (
        VEMULATOR_NATIVE_RUNTIME_VERSION_DERIVATION
    ),
    "native_runtime_version": VEMULATOR_NATIVE_RUNTIME_VERSION,
    "native_runtime_version_source": VEMULATOR_NATIVE_RUNTIME_VERSION_SOURCE,
    "metadata_display_version_source": (
        VEMULATOR_METADATA_DISPLAY_VERSION_SOURCE
    ),
}
VEMULATOR_EXPECTED_COMPILE_COUNT = 27
VEMULATOR_EXPECTED_LANGUAGE_COUNTS = {"c": 13, "cxx": 14}
VEMULATOR_EXPECTED_COMPILE_PAIR_SHA256 = (
    "70c3129d7e368711dc20ff5cf707ca7c3f113bbcca97e0109725e2a294776589"
)
VEMULATOR_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "d34b29b8065e7e52931dd5694cd7970e15644116b963fb0714bc5a8bfd3b937b",
    "armhf": "8836fa35c7bdecec66659dd341506287fc1b261c38e5c61ed514c55d585311f4",
}
VEMULATOR_EXPECTED_RAW_COMPILE_INVOCATION_SHA256 = {
    "arm64": "c3def28da3661441df0168c83520f8acaca4363e258d3d4bb48a2fdb6e55d049",
    "armhf": "86248f147656e3289e9c229f27a2ca9b67e61f590c4a164214f11975844ea4c4",
}
VEMULATOR_EXPECTED_LINK_OBJECT_SHA256 = (
    "e8fdd11a7c73d751e0da3a4e2fb951e4d1973573668837db212ae42f2a59dd26"
)
VEMULATOR_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "55e6befaf03db8fbb1be09ad71ac27645f6a27b03ee0d10cc598335ba33d772b"
)
VEMULATOR_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-Wl,--no-undefined",
    "-lm",
)
VEMULATOR_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "a51ef9985f3e5a6cf3cead7f02fede48506ea65096cf60280afb2a6823991231",
    "armhf": "789b959170c7aba029ed3c15cdc5912c18a709abefec39a49300489ac6160eaf",
}
VEMULATOR_EXPECTED_CLEAN_ARGV_SHA256 = (
    "7b6e462d7e2cad383ab400ca8901c90853ad8592086bc098b6c586e9773addb3"
)

VEMULATOR_EXPECTED_COMPILE_PAIRS = (
    (
        "libretro-common/compat/compat_posix_string.o",
        "libretro-common/compat/compat_posix_string.c",
    ),
    (
        "libretro-common/compat/compat_strcasestr.o",
        "libretro-common/compat/compat_strcasestr.c",
    ),
    (
        "libretro-common/compat/compat_snprintf.o",
        "libretro-common/compat/compat_snprintf.c",
    ),
    (
        "libretro-common/compat/compat_strl.o",
        "libretro-common/compat/compat_strl.c",
    ),
    (
        "libretro-common/compat/fopen_utf8.o",
        "libretro-common/compat/fopen_utf8.c",
    ),
    (
        "libretro-common/encodings/encoding_utf.o",
        "libretro-common/encodings/encoding_utf.c",
    ),
    (
        "libretro-common/file/file_path.o",
        "libretro-common/file/file_path.c",
    ),
    (
        "libretro-common/file/file_path_io.o",
        "libretro-common/file/file_path_io.c",
    ),
    (
        "libretro-common/time/rtime.o",
        "libretro-common/time/rtime.c",
    ),
    (
        "libretro-common/streams/file_stream.o",
        "libretro-common/streams/file_stream.c",
    ),
    (
        "libretro-common/streams/file_stream_transforms.o",
        "libretro-common/streams/file_stream_transforms.c",
    ),
    (
        "libretro-common/string/stdstring.o",
        "libretro-common/string/stdstring.c",
    ),
    (
        "libretro-common/vfs/vfs_implementation.o",
        "libretro-common/vfs/vfs_implementation.c",
    ),
    ("audio.o", "audio.cpp"),
    ("basetimer.o", "basetimer.cpp"),
    ("bitwisemath.o", "bitwisemath.cpp"),
    ("cpu.o", "cpu.cpp"),
    ("flash.o", "flash.cpp"),
    ("flashfile.o", "flashfile.cpp"),
    ("interrupts.o", "interrupts.cpp"),
    ("main.o", "main.cpp"),
    ("ram.o", "ram.cpp"),
    ("rom.o", "rom.cpp"),
    ("t0.o", "t0.cpp"),
    ("t1.o", "t1.cpp"),
    ("video.o", "video.cpp"),
    ("vmu.o", "vmu.cpp"),
)
VEMULATOR_EXPECTED_RAW_LINK_OBJECTS = tuple(
    f"./{output}" for output, _source in VEMULATOR_EXPECTED_COMPILE_PAIRS
)
VEMULATOR_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-fPIC",
        "-shared",
        "-Wl,--version-script=link.T",
        "-Wl,--no-undefined",
        "-o",
        VEMULATOR_BUILD_ARTIFACT_NAME,
        *VEMULATOR_EXPECTED_RAW_LINK_OBJECTS,
        "-lm",
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-g++",
        "armhf": "arm-a30-linux-gnueabihf-g++",
    }.items()
}
VEMULATOR_CLEAN_COMMAND = " ".join(
    (
        "rm",
        "-f",
        VEMULATOR_BUILD_ARTIFACT_NAME,
        *VEMULATOR_EXPECTED_RAW_LINK_OBJECTS,
    )
)
VEMULATOR_COMPILER_TOOLCHAINS = {
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
VEMULATOR_EXPECTED_PRE_CLEAN_LINES = {
    architecture: (
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
        "=== VEmulator",
        "Building vemulator...",
        'cd "/libretro-super/libretro-vemulator"',
        f'{make} -f Makefile platform="unix" -j24  clean',
    )
    for architecture, (
        c_compiler,
        cxx_compiler,
        strip,
        make,
    ) in VEMULATOR_COMPILER_TOOLCHAINS.items()
}

VEMULATOR_ARM64_COMPAT_WARNING_LINE = (
    "libretro-common/compat/compat_snprintf.c:83: warning: ISO C forbids "
    "an empty translation unit [-Wpedantic]"
)
VEMULATOR_ARM64_COMPAT_DIAGNOSTIC_BLOCK = "\n".join(
    (
        VEMULATOR_ARM64_COMPAT_WARNING_LINE,
        "   83 | #endif",
        "      | ",
    )
)
VEMULATOR_ARMHF_COMPAT_WARNING_LINE = (
    "libretro-common/compat/compat_snprintf.c:84: warning: ISO C forbids "
    "an empty translation unit [-Wpedantic]"
)
VEMULATOR_ARMHF_COMPAT_DIAGNOSTIC_BLOCK = (
    VEMULATOR_ARMHF_COMPAT_WARNING_LINE
)
VEMULATOR_ARMHF_FLASH_WARNING_LINE = (
    "flash.cpp:395:45: warning: 'void* __builtin_memcpy(void*, const void*, "
    "unsigned int)' forming offset 12 is out of the bounds [0, 12] "
    "[-Warray-bounds=]"
)
VEMULATOR_ARMHF_FLASH_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "flash.cpp: In member function "
        "'VE_VMS_FLASH_FILE VE_VMS_FLASH::getFileAt(int)':",
        VEMULATOR_ARMHF_FLASH_WARNING_LINE,
        "  395 |         for(i = 0; i < 12; i++, fileName[i] = nameArray[i]);",
        "      |                                 ~~~~~~~~~~~~^~~~~~~~~~~~~~",
    )
)
VEMULATOR_EXPECTED_WARNING_LINES = {
    "arm64": (VEMULATOR_ARM64_COMPAT_WARNING_LINE,),
    "armhf": (
        VEMULATOR_ARMHF_COMPAT_WARNING_LINE,
        VEMULATOR_ARMHF_FLASH_WARNING_LINE,
    ),
}
VEMULATOR_EXPECTED_NOTE_LINES = {"arm64": (), "armhf": ()}
VEMULATOR_EXPECTED_DIAGNOSTICS = {
    "arm64": (
        (
            VEMULATOR_ARM64_COMPAT_DIAGNOSTIC_BLOCK,
            "libretro-common/compat/compat_snprintf.c",
        ),
    ),
    "armhf": (
        (
            VEMULATOR_ARMHF_COMPAT_DIAGNOSTIC_BLOCK,
            "libretro-common/compat/compat_snprintf.c",
        ),
        (VEMULATOR_ARMHF_FLASH_DIAGNOSTIC_BLOCK, "flash.cpp"),
    ),
}

VEMULATOR_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
VEMULATOR_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the vemulator core must preserve its exact source-native "
    "runtime, source, recipe, metadata, and target contract"
)


def vemulator_spec_is_well_formed(spec: object) -> bool:
    """Require VEmulator's immutable catalog and source-native recipe."""

    identity = VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY
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


def vemulator_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed VEmulator tree."""

    identity = VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY
    return bool(
        core_id == VEMULATOR_CORE_ID
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


def vemulator_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require VEmulator's plain source-native promoted build record."""

    identity = VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and vemulator_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


VEMULATOR_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=VEMULATOR_CORE_ID,
    expected_compile_count=VEMULATOR_EXPECTED_COMPILE_COUNT,
    expected_language_counts=VEMULATOR_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=VEMULATOR_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        VEMULATOR_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=VEMULATOR_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        VEMULATOR_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=VEMULATOR_BUILD_ARTIFACT_NAME,
    expected_link_options=VEMULATOR_EXPECTED_LINK_OPTIONS,
    source_commit=VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY["source_commit"],
    source_tree=VEMULATOR_SOURCE_NATIVE_SPEC_IDENTITY["source_tree"],
    expected_ordered_link_argv_sha256=(
        VEMULATOR_EXPECTED_ORDERED_LINK_ARGV_SHA256
    ),
    expected_raw_compile_invocation_sha256=(
        VEMULATOR_EXPECTED_RAW_COMPILE_INVOCATION_SHA256
    ),
)


def _vemulator_runner_prefix(
    lines: list[str],
) -> tuple[list[str], str | None] | None:
    jobs_markers = tuple(
        (position, line)
        for position, line in enumerate(lines)
        if line.startswith(VEMULATOR_JOBS_MARKER_PREFIX)
    )
    if not jobs_markers:
        return lines, None
    if len(jobs_markers) != 1 or jobs_markers[0][0] != 0:
        return None
    match = re.fullmatch(
        re.escape(VEMULATOR_JOBS_MARKER_PREFIX) + r"\|([1-9][0-9]*)",
        jobs_markers[0][1],
    )
    if match is None:
        return None
    return lines[1:], match.group(1)


def _vemulator_markers_are_exact(
    lines: list[str]
) -> bool:
    source_markers = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    pipeline_markers = tuple(
        line for line in lines if line.startswith("CORE_PIPELINE_")
    )
    expected_pipeline_markers = (VEMULATOR_SOURCE_IDENTITY_MARKER,)
    return bool(
        source_markers == (VEMULATOR_SOURCE_HEAD_MARKER,)
        and pipeline_markers == expected_pipeline_markers
    )


def _vemulator_allowed_compiler_metadata(arch: str) -> frozenset[str]:
    toolchain = VEMULATOR_COMPILER_TOOLCHAINS.get(arch)
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


def _vemulator_build_invocation_metadata_is_allowed(
    line: str, arch: str
) -> bool:
    toolchain = VEMULATOR_COMPILER_TOOLCHAINS.get(arch)
    if toolchain is None:
        return False
    c_compiler, cxx_compiler, _strip, make = toolchain
    return bool(
        re.fullmatch(
            re.escape(f'{make} -f Makefile platform="unix" -j')
            + r"[1-9][0-9]* "
            + re.escape(f'CC="{c_compiler}" CXX="{cxx_compiler}"'),
            line.rstrip(),
        )
    )


def _vemulator_compile_and_link_scope_is_exact(
    lines: list[str], arch: str
) -> tuple[tuple[int, ...], dict[str, int], int] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    expected_link_argv = VEMULATOR_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    allowed_metadata = _vemulator_allowed_compiler_metadata(arch)
    if (
        expected_compilers is None
        or expected_cxx_compilers is None
        or expected_link_argv is None
        or not allowed_metadata
    ):
        return None

    compile_positions: list[int] = []
    compile_pairs: list[tuple[str, str]] = []
    source_positions: dict[str, int] = {}
    link_positions: list[int] = []
    language_counts: Counter[str] = Counter()
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
                and not _vemulator_build_invocation_metadata_is_allowed(
                    line, arch
                )
            ):
                return None
            continue
        if not command_line_is_lexically_safe(line):
            return None
        if tokens[0] not in expected_compilers:
            return None
        if "-c" in tokens:
            invocation = mixed_language_compile_invocation(
                tokens,
                expected_compilers,
                expected_cxx_compilers,
            )
            if invocation is None:
                return None
            if any(
                "GIT_VERSION" in token or "EMULATOR_BUILD" in token
                for token in tokens[1:]
            ):
                return None
            output, source, language, raw_output, raw_source, _raw_tokens = (
                invocation
            )
            if source in source_positions:
                return None
            compile_positions.append(line_number)
            compile_pairs.append((raw_output, raw_source))
            source_positions[source] = line_number
            language_counts[language] += 1
            continue
        if tuple(tokens) != expected_link_argv:
            return None
        if (
            tokens[0] not in expected_cxx_compilers
            or ordered_command_argv_sha256(tokens)
            != VEMULATOR_EXPECTED_ORDERED_LINK_ARGV_SHA256[arch]
        ):
            return None
        link_positions.append(line_number)

    if (
        Counter(compile_pairs) != Counter(VEMULATOR_EXPECTED_COMPILE_PAIRS)
        or len(compile_positions) != VEMULATOR_EXPECTED_COMPILE_COUNT
        or dict(language_counts) != VEMULATOR_EXPECTED_LANGUAGE_COUNTS
        or len(link_positions) != 1
    ):
        return None
    return tuple(compile_positions), source_positions, link_positions[0]


def _vemulator_log_envelope_is_exact(
    lines: list[str], arch: str
) -> bool:
    runner_prefix = _vemulator_runner_prefix(lines)
    if runner_prefix is None:
        return False
    lines, runner_jobs = runner_prefix
    if not _vemulator_markers_are_exact(lines):
        return False
    commands = _vemulator_compile_and_link_scope_is_exact(lines, arch)
    expected_diagnostics = VEMULATOR_EXPECTED_DIAGNOSTICS.get(arch)
    if commands is None or expected_diagnostics is None:
        return False
    compile_positions, source_positions, link_position = commands

    success_positions = _sequence_positions(lines, VEMULATOR_SUCCESS_MARKER)
    clean_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line == VEMULATOR_CLEAN_COMMAND
    )
    copy_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line == VEMULATOR_COPY_COMMAND
    )
    artifact_positions = tuple(
        position
        for position, line in enumerate(lines)
        if VEMULATOR_BUILD_ARTIFACT_NAME in line
    )
    if (
        tuple(lines[-len(VEMULATOR_SUCCESS_TRAILER) :])
        != VEMULATOR_SUCCESS_TRAILER
        or len(success_positions) != 2
        or len(clean_positions) != 1
        or len(copy_positions) != 1
        or artifact_positions
        != (clean_positions[0], link_position, copy_positions[0])
    ):
        return False

    pipeline_markers = (VEMULATOR_SOURCE_IDENTITY_MARKER,)
    expected_pre_clean = VEMULATOR_EXPECTED_PRE_CLEAN_LINES.get(arch)
    toolchain = VEMULATOR_COMPILER_TOOLCHAINS.get(arch)
    if expected_pre_clean is None or toolchain is None:
        return False
    expected_prefix = (
        *VEMULATOR_FETCH_PREFIX,
        *VEMULATOR_SUCCESS_MARKER,
        VEMULATOR_SOURCE_HEAD_MARKER,
        *pipeline_markers,
        *expected_pre_clean[:-1],
    )
    clean_invocation_position = len(expected_prefix)
    if (
        tuple(lines[:clean_invocation_position]) != expected_prefix
        or clean_positions[0] != clean_invocation_position + 1
    ):
        return False

    c_compiler, cxx_compiler, _strip, make = toolchain
    clean_match = re.fullmatch(
        re.escape(f'{make} -f Makefile platform="unix" -j')
        + r"([1-9][0-9]*)  clean",
        lines[clean_invocation_position],
    )
    if (
        clean_match is None
        or runner_jobs is not None
        and clean_match.group(1) != runner_jobs
    ):
        return False
    try:
        clean_argv = shlex.split(lines[clean_positions[0]])
    except ValueError:
        return False
    if (
        ordered_command_argv_sha256(clean_argv)
        != VEMULATOR_EXPECTED_CLEAN_ARGV_SHA256
    ):
        return False
    jobs = clean_match.group(1)
    expected_build_invocation = (
        f'{make} -f Makefile platform="unix" -j{jobs} '
        f'CC="{c_compiler}" CXX="{cxx_compiler}" '
    )
    build_invocation_position = clean_positions[0] + 1
    if (
        lines[build_invocation_position] != expected_build_invocation
        or min(compile_positions) != build_invocation_position + 1
    ):
        return False

    diagnostic_line_positions: set[int] = set()
    for block, owner_source in expected_diagnostics:
        sequence = tuple(block.splitlines())
        positions = _sequence_positions(lines, sequence)
        if len(positions) != 1:
            return False
        block_position = positions[0]
        owner_position = source_positions.get(owner_source)
        if (
            owner_position is None
            or owner_position >= block_position
            or block_position + len(sequence) > link_position
        ):
            return False
        block_lines = set(
            range(block_position, block_position + len(sequence))
        )
        if diagnostic_line_positions & block_lines:
            return False
        diagnostic_line_positions.update(block_lines)
    compile_line_positions = set(compile_positions)
    if (
        compile_line_positions & diagnostic_line_positions
        or compile_line_positions | diagnostic_line_positions
        != set(range(min(compile_positions), link_position))
        or max(compile_positions) >= link_position
    ):
        return False

    source_position = lines.index(VEMULATOR_SOURCE_HEAD_MARKER)
    marker_position = lines.index(VEMULATOR_SOURCE_IDENTITY_MARKER)
    if marker_position != source_position + 1:
        return False
    return bool(
        success_positions[0] + len(VEMULATOR_SUCCESS_MARKER)
        == source_position
        and source_position <= marker_position < clean_positions[0]
        and clean_positions[0] < min(compile_positions)
        and copy_positions[0] == link_position + 1
        and success_positions[1] == link_position + 2
    )


def _vemulator_diagnostics_and_version_are_exact(
    build_log_text: str, arch: str
) -> bool:
    expected_warning_lines = VEMULATOR_EXPECTED_WARNING_LINES.get(arch)
    expected_note_lines = VEMULATOR_EXPECTED_NOTE_LINES.get(arch)
    if expected_warning_lines is None or expected_note_lines is None:
        return False
    lowered_log = build_log_text.casefold()
    lines = build_log_text.splitlines()
    return bool(
        not any(
            marker in lowered_log
            for marker in VEMULATOR_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        and VEMULATOR_MAKE_FAILURE_RE.search(build_log_text) is None
        and Counter(
            line for line in lines if "warning:" in line.casefold()
        )
        == Counter(expected_warning_lines)
        and Counter(line for line in lines if "note:" in line.casefold())
        == Counter(expected_note_lines)
        and "CORE_PIPELINE_GIT_VERSION" not in build_log_text
        and "CORE_PIPELINE_NATIVE_GIT_VERSION" not in build_log_text
        and "-DGIT_VERSION=" not in build_log_text
        and "-DEMULATOR_BUILD=" not in build_log_text
    )


def _vemulator_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    if not isinstance(build_log_text, str):
        return False
    return bool(
        _vemulator_diagnostics_and_version_are_exact(build_log_text, arch)
        and _vemulator_log_envelope_is_exact(
            build_log_text.splitlines(),
            arch,
        )
        and mixed_language_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            VEMULATOR_LOG_CONTRACT,
        )
    )


def vemulator_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the active VEmulator source, argv, link, and diagnostics."""

    return _vemulator_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
    )
