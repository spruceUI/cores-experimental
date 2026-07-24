"""Exact FreeIntv source-native C-only build-log contract."""

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
from .log_checks import lines_sha256 as _lines_sha256, multiset_lines_sha256 as _multiset_lines_sha256, sequence_positions as _sequence_positions, compiler_token_name as _compiler_token_name


FREEINTV_CORE_ID = "freeintv"
FREEINTV_BUILD_ARTIFACT_NAME = "freeintv_libretro.so"
FREEINTV_LOG_CONTRACT_ID = "freeintv-c-only-v1"
FREEINTV_LOG_PROOF_KIND = "core-arch-source"

# FreeIntv's Makefile derives this value from the checked-out git repository;
# the pipeline does not inject it.  The active source-identity marker below
# therefore binds the native version calculation to the reviewed checkout.
FREEINTV_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
FREEINTV_NATIVE_GIT_VERSION = " 428915b"
FREEINTV_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" 428915b"\"'
FREEINTV_NATIVE_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION=" 428915b"'

FREEINTV_SOURCE_HEAD_MARKER = (
    "HEAD is now at 428915b libretro: add webOS to CI (#99)"
)
FREEINTV_SOURCE_IDENTITY_MARKER = (
    "CORE_PIPELINE_SOURCE_IDENTITY|freeintv|"
    "428915baf2bfc032fc03e645f4f8f9c6c3144979|"
    "ca7bcc22845ae696dd0fa011bd7c2486db7990e4|catalog"
)
FREEINTV_COPY_COMMAND = (
    'cp "freeintv_libretro.so" '
    '"/libretro-super/dist/unix/freeintv_libretro.so"'
)
FREEINTV_SUCCESS_MARKER = (
    "1 core(s) successfully processed:",
    f"\t{FREEINTV_CORE_ID}",
)
FREEINTV_SUCCESS_TRAILER = (
    FREEINTV_COPY_COMMAND,
    *FREEINTV_SUCCESS_MARKER,
)
FREEINTV_FETCH_PREFIX = (
    "PLATFORM: Linux",
    "ARCHITECTURE: x86_64",
    "TARGET: unix",
    "=== FreeIntv",
    "Fetching freeintv...",
    'git clone "https://github.com/libretro/FreeIntv.git" '
    '"/libretro-super/libretro-freeintv"',
    "Cloning into '/libretro-super/libretro-freeintv'...",
)

FREEINTV_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-freeintv.yml",
    "source_url": "https://github.com/libretro/FreeIntv.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "428915baf2bfc032fc03e645f4f8f9c6c3144979",
    "source_tree": "ca7bcc22845ae696dd0fa011bd7c2486db7990e4",
    "source_key": FREEINTV_CORE_ID,
    "source_dir": "libretro-freeintv",
    "output_path": "dist/unix/freeintv_libretro.so",
    "artifact_name": FREEINTV_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/freeintv_libretro.info"
    ),
    "metadata_artifact_name": "freeintv_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
    "native_git_version_derivation": (
        FREEINTV_NATIVE_GIT_VERSION_DERIVATION
    ),
    "native_git_version": FREEINTV_NATIVE_GIT_VERSION,
}
FREEINTV_EXPECTED_COMPILE_PAIRS = (
    ("src/libretro.o", "src/libretro.c"),
    ("src/intv.o", "src/intv.c"),
    ("src/memory.o", "src/memory.c"),
    ("src/cp1610.o", "src/cp1610.c"),
    ("src/cart.o", "src/cart.c"),
    ("src/controller.o", "src/controller.c"),
    ("src/osd.o", "src/osd.c"),
    ("src/ivoice.o", "src/ivoice.c"),
    ("src/psg.o", "src/psg.c"),
    ("src/stic.o", "src/stic.c"),
    ("src/stb_image_impl.o", "src/stb_image_impl.c"),
    (
        "src/deps/libretro-common/file/file_path.o",
        "src/deps/libretro-common/file/file_path.c",
    ),
    (
        "src/deps/libretro-common/compat/compat_posix_string.o",
        "src/deps/libretro-common/compat/compat_posix_string.c",
    ),
    (
        "src/deps/libretro-common/compat/compat_snprintf.o",
        "src/deps/libretro-common/compat/compat_snprintf.c",
    ),
    (
        "src/deps/libretro-common/compat/compat_strl.o",
        "src/deps/libretro-common/compat/compat_strl.c",
    ),
    (
        "src/deps/libretro-common/compat/compat_strcasestr.o",
        "src/deps/libretro-common/compat/compat_strcasestr.c",
    ),
    (
        "src/deps/libretro-common/compat/fopen_utf8.o",
        "src/deps/libretro-common/compat/fopen_utf8.c",
    ),
    (
        "src/deps/libretro-common/encodings/encoding_utf.o",
        "src/deps/libretro-common/encodings/encoding_utf.c",
    ),
    (
        "src/deps/libretro-common/string/stdstring.o",
        "src/deps/libretro-common/string/stdstring.c",
    ),
    (
        "src/deps/libretro-common/time/rtime.o",
        "src/deps/libretro-common/time/rtime.c",
    ),
)
FREEINTV_EXPECTED_COMPILE_COUNT = len(FREEINTV_EXPECTED_COMPILE_PAIRS)
FREEINTV_EXPECTED_COMPILE_PAIR_SHA256 = (
    "8496232a97cf400623974cea546bfa9d46764f87f1ac85f4e78e471af3eb7051"
)
FREEINTV_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "daba4a7b9007f5bc05bc02d633dbb19a279b499d3fc733680e31f04e24bc5dd9",
    "armhf": "f9461ece661171eb0e8162bfb9027f3799abbd3a59c88239858f10bd9b1cd32c",
}
FREEINTV_EXPECTED_RAW_COMPILE_INVOCATION_SHA256 = {
    "arm64": "5b128968e5c05e905e19b567d3f780f2d06dbb8529c749937f960bc3c0fed36e",
    "armhf": "91ac5cf251e8cacce47f175b3b6637ef22ab03d5a81ed6e9be6337338dfac1a7",
}

FREEINTV_EXPECTED_RAW_LINK_OBJECTS = tuple(
    output for output, _source in FREEINTV_EXPECTED_COMPILE_PAIRS
)
FREEINTV_EXPECTED_LINK_OBJECT_SHA256 = (
    "682f5f65e1b5599e80bcec4e0a22fb955110da6036e0c23c3bafe864c2a670c4"
)
FREEINTV_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    FREEINTV_EXPECTED_LINK_OBJECT_SHA256
)
FREEINTV_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=./link.T",
    "-Wl,--no-undefined",
    "-lm",
    "-lm",
)
FREEINTV_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-o",
        FREEINTV_BUILD_ARTIFACT_NAME,
        "-shared",
        "-Wl,--version-script=./link.T",
        "-Wl,--no-undefined",
        *FREEINTV_EXPECTED_RAW_LINK_OBJECTS,
        "-lm",
        "-lm",
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }.items()
}
FREEINTV_EXPECTED_LINK_INVOCATION_SHA256 = {
    "arm64": "7371a838f7d5f746f2d830688d4709c49f81d849889451e5f8500f7327da935b",
    "armhf": "68e94915d0b6b3586dee93d3b913e6b93365517e415dd43844e823082c56128e",
}
FREEINTV_CLEAN_COMMAND = " ".join(
    ("rm", "-f", *FREEINTV_EXPECTED_RAW_LINK_OBJECTS)
) + "  " + FREEINTV_BUILD_ARTIFACT_NAME
FREEINTV_EXPECTED_CLEAN_ARGV_SHA256 = (
    "c1bf143e12003275d4513e09fab7a78c708429dba5e8ace6eeb4d6093982fc70"
)

FREEINTV_COMPILER_TOOLCHAINS = {
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
FREEINTV_EXPECTED_BUILD_PREFIX = {
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
        "=== FreeIntv",
        "Building freeintv...",
        'cd "/libretro-super/libretro-freeintv"',
    )
    for architecture, (
        c_compiler,
        cxx_compiler,
        strip,
        _make,
    ) in FREEINTV_COMPILER_TOOLCHAINS.items()
}

# The two reviewed -j24 builds for each ABI use different interleavings but
# exactly the same diagnostic line multiset.  Bind every context line while
# allowing only that scheduling nondeterminism.
FREEINTV_EXPECTED_DIAGNOSTIC_LINE_COUNT = {
    "arm64": 377,
    "armhf": 434,
}
FREEINTV_EXPECTED_WARNING_COUNT = {"arm64": 86, "armhf": 114}
FREEINTV_EXPECTED_NOTE_COUNT = {"arm64": 39, "armhf": 41}
FREEINTV_EXPECTED_DIAGNOSTIC_LINE_SHA256 = {
    "arm64": "3beeddf216967d3abbda4a240292934befa03a35996d84699f34e09116dc47d4",
    "armhf": "5d81c590286e82f12017b7f700a4feebdb79c3f7ca5a380d6ab314e8d8ba6fa9",
}
FREEINTV_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256 = {
    "arm64": "617a78bc824b1283c8041ee78393e0b1040c185d2b0eaf7f7188e858e8c0bbe4",
    "armhf": "5954c91d3f1af01d015c2b27c6607d3caa7e1fd200726b862c603e42755b4a78",
}

FREEINTV_FORBIDDEN_LOG_FRAGMENTS = (
    "aborted",
    "broken pipe",
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
FREEINTV_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Reviewed legacy output and resolver facts.  These are evidence identities,
# not a publication or licensing determination.
FREEINTV_REVIEWED_OUTPUT_FACTS = {
    "artifacts": {
        "arm64": {
            "sha256": (
                "4b919af5109219c2f3ddde2fd34b921b3b9c373df43629e8c"
                "bc4855f0d3c18a5"
            ),
            "size": 617664,
            "needed": ("ld-linux-aarch64.so.1", "libc.so.6", "libm.so.6"),
            "version_requirements": ("GLIBC_2.17", "GLIBC_2.29"),
        },
        "armhf": {
            "sha256": (
                "caa8c772dffd5ee7854f62ae309ca11ac22affd135fc69ada4"
                "009d4e48b3aba0"
            ),
            "size": 597000,
            "needed": ("ld-linux-armhf.so.3", "libc.so.6", "libm.so.6"),
            "version_requirements": ("GLIBC_2.4",),
        },
    },
    "metadata": {
        "sha256": "b5014f6e35471bbbe10b0c8b1191506f8b3d7dd3863b0584d9563440f61d9135",
        "size": 1111,
        "display_version": "2018.1.5",
        "license_declaration": "GPLv3",
        "required_system_files": (
            ("exec.bin", "62e761035cb657903761800f4437b8af"),
            ("grom.bin", "0cd5946c6473e42e8e4c2137785e427f"),
        ),
        "optional_system_files": (),
    },
    "package": {
        "sha256": "83bc98317d790ae31ff58411c91077a3864711457ff0b3b23cc415b1263669a7",
        "size": 993428,
    },
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the freeintv core must preserve its exact source-native "
    "version, source, recipe, metadata, and target contract"
)


def freeintv_spec_is_well_formed(spec: object) -> bool:
    """Require FreeIntv's complete immutable source-native catalog entry."""

    identity = FREEINTV_SPEC_IDENTITY
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


def freeintv_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed FreeIntv tree."""

    identity = FREEINTV_SPEC_IDENTITY
    return bool(
        core_id == FREEINTV_CORE_ID
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


def freeintv_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require FreeIntv's plain source-native promoted build record."""

    identity = FREEINTV_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and freeintv_golden_source_is_well_formed(core_id, source)
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


FREEINTV_LOG_CONTRACT = COnlyLogContract(
    core_id=FREEINTV_CORE_ID,
    expected_compile_count=FREEINTV_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=FREEINTV_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        FREEINTV_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=FREEINTV_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=FREEINTV_BUILD_ARTIFACT_NAME,
    expected_link_options=FREEINTV_EXPECTED_LINK_OPTIONS,
    source_commit=FREEINTV_SPEC_IDENTITY["source_commit"],
    source_tree=FREEINTV_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=(
        FREEINTV_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    expected_link_invocation_sha256=(
        FREEINTV_EXPECTED_LINK_INVOCATION_SHA256
    ),
    expected_raw_compile_invocation_sha256=(
        FREEINTV_EXPECTED_RAW_COMPILE_INVOCATION_SHA256
    ),
)


def _freeintv_allowed_compiler_metadata(arch: str) -> frozenset[str]:
    toolchain = FREEINTV_COMPILER_TOOLCHAINS.get(arch)
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


def _freeintv_build_invocation_metadata_is_allowed(
    line: str, arch: str
) -> bool:
    toolchain = FREEINTV_COMPILER_TOOLCHAINS.get(arch)
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


def _freeintv_compile_and_link_scope_is_exact(
    lines: list[str], arch: str
) -> tuple[tuple[int, ...], int] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    expected_link_argv = FREEINTV_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    allowed_metadata = _freeintv_allowed_compiler_metadata(arch)
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
                and not _freeintv_build_invocation_metadata_is_allowed(
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
                tokens, expected_c_compilers
            )
            if invocation is None:
                return None
            output, source, _canonical_tokens = invocation
            version_tokens = [
                token for token in tokens[1:] if "GIT_VERSION" in token
            ]
            if version_tokens != [
                FREEINTV_NATIVE_GIT_VERSION_COMPILE_TOKEN
            ]:
                return None
            compile_positions.append(line_number)
            compile_pairs.append((output, source))
            continue
        if tuple(tokens) != expected_link_argv:
            return None
        if (
            ordered_command_argv_sha256(tokens)
            != FREEINTV_EXPECTED_LINK_INVOCATION_SHA256[arch]
        ):
            return None
        link_positions.append(line_number)

    if (
        Counter(compile_pairs) != Counter(FREEINTV_EXPECTED_COMPILE_PAIRS)
        or len(compile_positions) != FREEINTV_EXPECTED_COMPILE_COUNT
        or len(link_positions) != 1
    ):
        return None
    return tuple(compile_positions), link_positions[0]


def _freeintv_markers_are_exact(
    lines: list[str]
) -> bool:
    source_markers = tuple(
        line for line in lines if line.startswith("HEAD is now at ")
    )
    pipeline_markers = tuple(
        line for line in lines if line.startswith("CORE_PIPELINE_")
    )
    expected_pipeline_markers = (FREEINTV_SOURCE_IDENTITY_MARKER,)
    return bool(
        source_markers == (FREEINTV_SOURCE_HEAD_MARKER,)
        and pipeline_markers == expected_pipeline_markers
    )


def _freeintv_log_envelope_is_exact(
    lines: list[str], arch: str
) -> bool:
    if not _freeintv_markers_are_exact(lines):
        return False
    commands = _freeintv_compile_and_link_scope_is_exact(lines, arch)
    toolchain = FREEINTV_COMPILER_TOOLCHAINS.get(arch)
    expected_build_prefix = FREEINTV_EXPECTED_BUILD_PREFIX.get(arch)
    if commands is None or toolchain is None or expected_build_prefix is None:
        return False
    compile_positions, link_position = commands

    pipeline_markers = (FREEINTV_SOURCE_IDENTITY_MARKER,)
    expected_prefix = (
        *FREEINTV_FETCH_PREFIX,
        *FREEINTV_SUCCESS_MARKER,
        FREEINTV_SOURCE_HEAD_MARKER,
        *pipeline_markers,
        *expected_build_prefix,
    )
    clean_invocation_position = len(expected_prefix)
    if tuple(lines[:clean_invocation_position]) != expected_prefix:
        return False

    c_compiler, cxx_compiler, _strip, make = toolchain
    clean_match = re.fullmatch(
        re.escape(f'{make} -f Makefile platform="unix" -j')
        + r"([1-9][0-9]*)  clean",
        lines[clean_invocation_position]
        if clean_invocation_position < len(lines)
        else "",
    )
    if clean_match is None:
        return False
    clean_position = clean_invocation_position + 1
    if (
        clean_position >= len(lines)
        or lines[clean_position] != FREEINTV_CLEAN_COMMAND
    ):
        return False
    try:
        clean_argv = shlex.split(lines[clean_position])
    except ValueError:
        return False
    if (
        ordered_command_argv_sha256(clean_argv)
        != FREEINTV_EXPECTED_CLEAN_ARGV_SHA256
    ):
        return False

    jobs = clean_match.group(1)
    expected_build_invocation = (
        f'{make} -f Makefile platform="unix" -j{jobs} '
        f'CC="{c_compiler}" CXX="{cxx_compiler}" '
    )
    build_invocation_position = clean_position + 1
    if (
        build_invocation_position >= len(lines)
        or lines[build_invocation_position]
        != expected_build_invocation
        or min(compile_positions) != build_invocation_position + 1
    ):
        return False

    if (
        tuple(lines[-len(FREEINTV_SUCCESS_TRAILER) :])
        != FREEINTV_SUCCESS_TRAILER
        or link_position != len(lines) - len(FREEINTV_SUCCESS_TRAILER) - 1
        or max(compile_positions) >= link_position
        or _sequence_positions(lines, FREEINTV_SUCCESS_MARKER)
        != (
            len(FREEINTV_FETCH_PREFIX),
            link_position + 2,
        )
    ):
        return False

    compile_position_set = set(compile_positions)
    diagnostics = tuple(
        line
        for position, line in enumerate(lines)
        if min(compile_positions) <= position < link_position
        and position not in compile_position_set
    )
    headlines = tuple(
        line
        for line in diagnostics
        if "warning:" in line.casefold() or "note:" in line.casefold()
    )
    if (
        len(diagnostics)
        != FREEINTV_EXPECTED_DIAGNOSTIC_LINE_COUNT.get(arch)
        or sum("warning:" in line.casefold() for line in headlines)
        != FREEINTV_EXPECTED_WARNING_COUNT.get(arch)
        or sum("note:" in line.casefold() for line in headlines)
        != FREEINTV_EXPECTED_NOTE_COUNT.get(arch)
        or _multiset_lines_sha256(diagnostics)
        != FREEINTV_EXPECTED_DIAGNOSTIC_LINE_SHA256.get(arch)
        or _multiset_lines_sha256(headlines)
        != FREEINTV_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256.get(arch)
    ):
        return False

    artifact_positions = tuple(
        position
        for position, line in enumerate(lines)
        if FREEINTV_BUILD_ARTIFACT_NAME in line
    )
    if artifact_positions != (
        clean_position,
        link_position,
        link_position + 1,
    ):
        return False

    source_position = lines.index(FREEINTV_SOURCE_HEAD_MARKER)
    marker_position = lines.index(FREEINTV_SOURCE_IDENTITY_MARKER)
    return bool(
        source_position
        == len(FREEINTV_FETCH_PREFIX) + len(FREEINTV_SUCCESS_MARKER)
        and marker_position == source_position + 1
        and source_position <= marker_position < clean_invocation_position
        and lines[link_position + 1] == FREEINTV_COPY_COMMAND
    )


def _freeintv_diagnostics_and_version_are_exact(
    build_log_text: str,
) -> bool:
    lowered_log = build_log_text.casefold()
    return bool(
        not any(
            fragment in lowered_log
            for fragment in FREEINTV_FORBIDDEN_LOG_FRAGMENTS
        )
        and FREEINTV_MAKE_FAILURE_RE.search(build_log_text) is None
        and build_log_text.count("-DGIT_VERSION=")
        == FREEINTV_EXPECTED_COMPILE_COUNT
        and build_log_text.count(FREEINTV_NATIVE_GIT_VERSION_LOG_TOKEN)
        == FREEINTV_EXPECTED_COMPILE_COUNT
        and "CORE_PIPELINE_NATIVE_GIT_VERSION" not in build_log_text
        and "CORE_PIPELINE_GIT_VERSION" not in build_log_text
        and "-DEMULATOR_BUILD=" not in build_log_text
    )


def _freeintv_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    if not isinstance(build_log_text, str):
        return False
    return bool(
        _freeintv_diagnostics_and_version_are_exact(build_log_text)
        and _freeintv_log_envelope_is_exact(
            build_log_text.splitlines(),
            arch,
        )
        and c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            FREEINTV_LOG_CONTRACT,
        )
    )


def freeintv_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the active FreeIntv source, argv, diagnostics, and framing."""

    return _freeintv_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
    )
