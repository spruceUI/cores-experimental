"""Exact GearColeco native-describe mixed-language build contract."""

from __future__ import annotations

from collections import Counter
import re
import shlex

from .compiler import TARGET_COMPILERS, TARGET_CXX_COMPILERS
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_compile_invocation,
    mixed_language_log_proves_contract,
)


GEARCOLECO_CORE_ID = "gearcoleco"
GEARCOLECO_BUILD_ARTIFACT_NAME = "gearcoleco_libretro.so"
GEARCOLECO_NATIVE_GIT_DESCRIBE_DERIVATION = "native-git-describe-v1"
GEARCOLECO_NATIVE_GIT_DESCRIBE_VALUE = "1.6.6-11-g1123457"
GEARCOLECO_NATIVE_GIT_DESCRIBE_LOG_TOKEN = (
    r'-DEMULATOR_BUILD=\"1.6.6-11-g1123457\"'
)
GEARCOLECO_SOURCE_HEAD_MARKER = (
    "HEAD is now at 1123457 Add configurable screen saver behavior option"
)
GEARCOLECO_NATIVE_VERSION_MARKER = (
    "CORE_PIPELINE_NATIVE_GIT_VERSION|1.6.6-11-g1123457|file"
)
GEARCOLECO_BUILD_COMPLETE_MARKER = (
    "Build complete: gearcoleco Release - 1.6.6-11-g1123457 - unix"
)
GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gearcoleco.yml",
    "source_url": "https://github.com/drhelius/Gearcoleco.git",
    "source_requested_ref": "refs/heads/main",
    "source_commit": "112345747c04eb7752d1939258881aa10319e32e",
    "source_tree": "0afbed445cf4689daa878816f961ea4bcb4832a3",
    "source_key": GEARCOLECO_CORE_ID,
    "source_dir": "libretro-gearcoleco",
    "output_path": "dist/unix/gearcoleco_libretro.so",
    "artifact_name": GEARCOLECO_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/gearcoleco_libretro.info"
    ),
    "metadata_artifact_name": "gearcoleco_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "platforms/libretro/Makefile",
    "git_version_value": GEARCOLECO_NATIVE_GIT_DESCRIBE_VALUE,
    "compile_macro": "EMULATOR_BUILD",
}

GEARCOLECO_SEMANTIC_PATH_ALIASES = (
    ("../shared/dependencies/", "shared/dependencies/"),
    ("../../src/", "src/"),
)
GEARCOLECO_PROCESSOR_SOURCE = "../../src/Processor.cpp"
GEARCOLECO_EXPECTED_COMPILE_COUNT = 20
GEARCOLECO_EXPECTED_LANGUAGE_COUNTS = {"c": 1, "cxx": 19}
GEARCOLECO_EXPECTED_COMPILE_PAIR_SHA256 = (
    "24e913a58533476d47c48d8be419fdd3299cadafecaeb4f75d39ff76db961d04"
)
GEARCOLECO_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "7122f6c14c1b5e68052468da30352b34423a043305dd19200877cf6ae01f2546",
    "armhf": "ed3194ceb34f9bd26d26c0e7d12cf053c578f653fbe2eca713eec5716f9855a8",
}
GEARCOLECO_EXPECTED_LINK_OBJECT_SHA256 = (
    "bc0844b1eb74f53fadb8f490e25f17ccccd81af424505c3dc42318096fee4e5f"
)
GEARCOLECO_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "bf07a3069bb96b2a89d340c849e17e8c009d1dc4873ab336a23ac74cbfa1a07a"
)
GEARCOLECO_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,-version-script=./link.T",
    "-lm",
)
GEARCOLECO_EXPECTED_RAW_LINK_OBJECTS = (
    "../shared/dependencies/miniz/miniz.o",
    "./libretro.o",
    "../../src/GearcolecoCore.o",
    "../../src/Memory.o",
    "../../src/Processor.o",
    "../../src/Video.o",
    "../../src/Audio.o",
    "../../src/AY8910.o",
    "../../src/Input.o",
    "../../src/Cartridge.o",
    "../../src/ColecoVisionIOPorts.o",
    "../../src/opcodes.o",
    "../../src/opcodes_cb.o",
    "../../src/opcodes_ed.o",
    "../../src/TraceLogger.o",
    "../../src/VgmRecorder.o",
    "../../src/audio/Blip_Buffer.o",
    "../../src/audio/Effects_Buffer.o",
    "../../src/audio/Sms_Apu.o",
    "../../src/audio/Multi_Buffer.o",
)
GEARCOLECO_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-fPIC",
        "-shared",
        "-Wl,-version-script=./link.T",
        "-o",
        GEARCOLECO_BUILD_ARTIFACT_NAME,
        *GEARCOLECO_EXPECTED_RAW_LINK_OBJECTS,
        "-lm",
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-g++",
        "armhf": "arm-a30-linux-gnueabihf-g++",
    }.items()
}

GEARCOLECO_EXPECTED_WARNING_LINES = (
    "../../src/opcodefdcb_names.h:23:21: warning: 'kOPCodeFDCBNames' "
    "defined but not used [-Wunused-variable]",
    "../../src/opcodeddcb_names.h:23:21: warning: 'kOPCodeDDCBNames' "
    "defined but not used [-Wunused-variable]",
    "../../src/opcodefd_names.h:23:21: warning: 'kOPCodeFDNames' defined "
    "but not used [-Wunused-variable]",
    "../../src/opcodedd_names.h:23:21: warning: 'kOPCodeDDNames' defined "
    "but not used [-Wunused-variable]",
    "../../src/opcodeed_names.h:23:21: warning: 'kOPCodeEDNames' defined "
    "but not used [-Wunused-variable]",
    "../../src/opcodecb_names.h:23:21: warning: 'kOPCodeCBNames' defined "
    "but not used [-Wunused-variable]",
    "../../src/opcodexx_names.h:23:21: warning: 'kOPCodeNames' defined but "
    "not used [-Wunused-variable]",
)

GEARCOLECO_ARM64_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "In file included from ../../src/opcode_names.h:51,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[0],
        "   23 | static stOPCodeInfo kOPCodeFDCBNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:50,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[1],
        "   23 | static stOPCodeInfo kOPCodeDDCBNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:49,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[2],
        "   23 | static stOPCodeInfo kOPCodeFDNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:48,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[3],
        "   23 | static stOPCodeInfo kOPCodeDDNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:47,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[4],
        "   23 | static stOPCodeInfo kOPCodeEDNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:46,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[5],
        "   23 | static stOPCodeInfo kOPCodeCBNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:45,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[6],
        "   23 | static stOPCodeInfo kOPCodeNames[256] = {",
        "      |                     ^~~~~~~~~~~~",
    )
)
GEARCOLECO_ARMHF_DIAGNOSTIC_BLOCK = "\n".join(
    (
        "In file included from ../../src/opcode_names.h:51,",
        "                 from ../../src/Processor.cpp:27:",
        GEARCOLECO_EXPECTED_WARNING_LINES[0],
        "   23 | static stOPCodeInfo kOPCodeFDCBNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:50:",
        GEARCOLECO_EXPECTED_WARNING_LINES[1],
        "   23 | static stOPCodeInfo kOPCodeDDCBNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:49:",
        GEARCOLECO_EXPECTED_WARNING_LINES[2],
        "   23 | static stOPCodeInfo kOPCodeFDNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:48:",
        GEARCOLECO_EXPECTED_WARNING_LINES[3],
        "   23 | static stOPCodeInfo kOPCodeDDNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:47:",
        GEARCOLECO_EXPECTED_WARNING_LINES[4],
        "   23 | static stOPCodeInfo kOPCodeEDNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:46:",
        GEARCOLECO_EXPECTED_WARNING_LINES[5],
        "   23 | static stOPCodeInfo kOPCodeCBNames[256] = {",
        "      |                     ^~~~~~~~~~~~~~",
        "In file included from ../../src/opcode_names.h:45:",
        GEARCOLECO_EXPECTED_WARNING_LINES[6],
        "   23 | static stOPCodeInfo kOPCodeNames[256] = {",
        "      |                     ^~~~~~~~~~~~",
    )
)
GEARCOLECO_EXPECTED_DIAGNOSTIC_BLOCKS = {
    "arm64": GEARCOLECO_ARM64_DIAGNOSTIC_BLOCK,
    "armhf": GEARCOLECO_ARMHF_DIAGNOSTIC_BLOCK,
}
GEARCOLECO_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
GEARCOLECO_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def gearcoleco_spec_is_well_formed(spec: object) -> bool:
    """Require GearColeco's complete catalog and native-describe identity."""

    identity = GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
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
                    "derivation": GEARCOLECO_NATIVE_GIT_DESCRIBE_DERIVATION,
                    "value": GEARCOLECO_NATIVE_GIT_DESCRIBE_VALUE,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def gearcoleco_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed GearColeco tree."""

    identity = GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
    return bool(
        core_id == GEARCOLECO_CORE_ID
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


def gearcoleco_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted GearColeco native-describe build record."""

    return bool(
        isinstance(build, dict)
        and source_commit
        == GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_commit"]
        and gearcoleco_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": GEARCOLECO_NATIVE_GIT_DESCRIBE_DERIVATION,
                "value": GEARCOLECO_NATIVE_GIT_DESCRIBE_VALUE,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


GEARCOLECO_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=GEARCOLECO_CORE_ID,
    expected_compile_count=GEARCOLECO_EXPECTED_COMPILE_COUNT,
    expected_language_counts=GEARCOLECO_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=GEARCOLECO_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        GEARCOLECO_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=GEARCOLECO_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        GEARCOLECO_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=GEARCOLECO_BUILD_ARTIFACT_NAME,
    expected_link_options=GEARCOLECO_EXPECTED_LINK_OPTIONS,
    source_commit=(
        GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_commit"]
    ),
    source_tree=GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_tree"],
    semantic_path_aliases=GEARCOLECO_SEMANTIC_PATH_ALIASES,
)


def _exact_diagnostic_block_position(
    lines: list[str], expected_block: str
) -> int | None:
    expected_lines = tuple(expected_block.splitlines())
    positions = [
        index
        for index in range(len(lines) - len(expected_lines) + 1)
        if tuple(lines[index : index + len(expected_lines)])
        == expected_lines
    ]
    if len(positions) != 1:
        return None
    return positions[0]


def gearcoleco_log_proves_contract(
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
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    expected_link_argv = GEARCOLECO_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    expected_diagnostic_block = GEARCOLECO_EXPECTED_DIAGNOSTIC_BLOCKS.get(
        arch
    )
    if (
        expected_compilers is None
        or expected_cxx_compilers is None
        or expected_link_argv is None
        or expected_diagnostic_block is None
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
    build_complete_lines = tuple(
        line for line in lines if line.startswith("Build complete: gearcoleco ")
    )
    warning_lines = tuple(
        line for line in lines if "warning:" in line.casefold()
    )
    note_lines = tuple(line for line in lines if "note:" in line.casefold())
    if (
        any(
            marker in lowered_log
            for marker in GEARCOLECO_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or GEARCOLECO_MAKE_FAILURE_RE.search(build_log_text) is not None
        or Counter(warning_lines)
        != Counter(GEARCOLECO_EXPECTED_WARNING_LINES)
        or note_lines
        or source_head_lines != (GEARCOLECO_SOURCE_HEAD_MARKER,)
        or native_version_lines != (GEARCOLECO_NATIVE_VERSION_MARKER,)
        or build_complete_lines != (GEARCOLECO_BUILD_COMPLETE_MARKER,)
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=") != 0
        or build_log_text.count("-DEMULATOR_BUILD=")
        != GEARCOLECO_EXPECTED_COMPILE_COUNT
        or build_log_text.count(GEARCOLECO_NATIVE_GIT_DESCRIBE_LOG_TOKEN)
        != GEARCOLECO_EXPECTED_COMPILE_COUNT
    ):
        return False

    compile_positions: list[int] = []
    processor_compile_positions: list[int] = []
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
                GEARCOLECO_SEMANTIC_PATH_ALIASES,
            )
            if (
                invocation is not None
                and invocation[4] == GEARCOLECO_PROCESSOR_SOURCE
            ):
                processor_compile_positions.append(line_number)
        elif GEARCOLECO_BUILD_ARTIFACT_NAME in tokens:
            link_invocations.append((line_number, tuple(tokens)))
    if (
        len(compile_positions) != GEARCOLECO_EXPECTED_COMPILE_COUNT
        or len(processor_compile_positions) != 1
        or len(link_invocations) != 1
        or link_invocations[0][1] != expected_link_argv
    ):
        return False

    diagnostic_position = _exact_diagnostic_block_position(
        lines, expected_diagnostic_block
    )
    if diagnostic_position is None:
        return False
    diagnostic_end = diagnostic_position + len(
        expected_diagnostic_block.splitlines()
    )
    source_position = lines.index(GEARCOLECO_SOURCE_HEAD_MARKER)
    version_position = lines.index(GEARCOLECO_NATIVE_VERSION_MARKER)
    processor_compile_position = processor_compile_positions[0]
    link_position = link_invocations[0][0]
    build_complete_position = lines.index(GEARCOLECO_BUILD_COMPLETE_MARKER)
    if not (
        source_position < version_position < min(compile_positions)
        and processor_compile_position < diagnostic_position
        and max(compile_positions) < link_position
        and diagnostic_end <= link_position
        and link_position < build_complete_position
    ):
        return False

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        GEARCOLECO_LOG_CONTRACT,
    )
