"""Exact VecX software-renderer build and evidence contract."""

from __future__ import annotations

import re
from pathlib import Path
import shlex

from .c_only import COnlyLogContract, c_only_log_proves_contract


VECX_CORE_ID = "vecx"
VECX_SOFTWARE_MAKE_VARIABLES = {"HAS_GPU": 0}
VECX_SOFTWARE_MAKE_PROFILE = "vecx-software-v1"
VECX_SOFTWARE_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "git_version",
        "make_variables",
        "output_path",
        "source_dir",
        "source_key",
    }
)
VECX_SOFTWARE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-vecx.yml",
    "source_url": "https://github.com/libretro/libretro-vecx.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "8f671cc9d737f2890c3ce19e177e2984dcae121f",
    "source_tree": "49ae584713edede2a70792ecf6cb744b11fff2e6",
    "source_key": VECX_CORE_ID,
    "source_dir": "libretro-vecx",
    "output_path": "dist/unix/vecx_libretro.so",
    "artifact_name": "vecx_libretro.so",
    "metadata_source_path": "/libretro-super/dist/info/vecx_libretro.info",
    "metadata_artifact_name": "vecx_libretro.info",
    "targets": ["arm64", "armhf"],
    "forbidden_needed_prefixes": ["libEGL", "libGL", "libGLES", "libOpenGL"],
}

VECX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
VECX_NATIVE_GIT_VERSION = " 8f671cc"
VECX_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" 8f671cc"\"'
VECX_METADATA_REPLACEMENT_KIND = "whole-file-v1"
VECX_METADATA_REPLACEMENT_PATH = "metadata/vecx/software-v1.info"
VECX_METADATA_PREIMAGE_SHA256 = (
    "9eec259b2b84256aca32cdcd37b084732b17d2fce829dac01bab9a84ea01b4e3"
)
VECX_METADATA_REPLACEMENT_SHA256 = (
    "2f22e8069a304878b52aeb5d7f789812bf271c61e5c41e0cb0fbd6acb5d28c1a"
)
VECX_METADATA_REPLACEMENT = {
    "kind": VECX_METADATA_REPLACEMENT_KIND,
    "path": VECX_METADATA_REPLACEMENT_PATH,
    "preimage_sha256": VECX_METADATA_PREIMAGE_SHA256,
    "replacement_sha256": VECX_METADATA_REPLACEMENT_SHA256,
}

VECX_EXPECTED_COMPILE_COUNT = 4
VECX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "39905b2d028478c05ffe4a2b4d7f03e892f7845933dc3a8be6c407a6142a3aae"
)
VECX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "d63d3aba7f2694f65f37c40eb2c04fd04433dcbc3478b366842ffdb4778c5873",
    "armhf": "5707d899d95551fdc463ef5e1662a814a15a948c3102b9f06593db92abe9f2ef",
}
VECX_EXPECTED_LINK_OBJECT_SHA256 = (
    "86d0130401d97f043d0fce3c6482b63a409d8863373bb7e7500e0c2405df5e95"
)
VECX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "99360c3f4e52c1d7a1e85c63ebecf19d9c854aa2016360f650a16d63272d9461"
)
VECX_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./link.T",
    "-lm",
)
VECX_EXPECTED_ORDERED_LINK_ARGV = {
    architecture: (
        compiler,
        "-ovecx_libretro.so",
        "-fPIC",
        "-shared",
        "-Wl,--version-script=./link.T",
        "./e6809.o",
        "./vecx_psg.o",
        "./libretro.o",
        "./vecx.o",
        "-lm",
    )
    for architecture, compiler in {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }.items()
}

VECX_SOURCE_HEAD_MARKER = (
    "HEAD is now at 8f671cc libretro: add webOS to CI (#66)"
)
VECX_MAKE_MARKERS = (
    "CORE_PIPELINE_MAKEFLAGS|HAS_GPU=0",
    "CORE_PIPELINE_MAKE_VARIABLE|HAS_GPU|0|command line",
)
VECX_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 8f671cc"|file'
)
VECX_METADATA_REPLACEMENT_MARKER = (
    "CORE_PIPELINE_METADATA_REPLACEMENT|whole-file-v1|"
    f"{VECX_METADATA_PREIMAGE_SHA256}|{VECX_METADATA_REPLACEMENT_SHA256}"
)
VECX_FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "warning:",
    "error:",
    "fatal:",
    "note:",
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
VECX_FORBIDDEN_GPU_LOG_MARKERS = (
    "glsym",
    "rglgen",
    "-legl",
    "-lgl",
    "-lgles",
    "-lopengl",
    "libegl",
    "libgl",
    "libgles",
    "libopengl",
)
VECX_FORBIDDEN_COMPILE_MACROS = frozenset(
    {
        "HAS_GPU",
        "HAVE_EGL",
        "HAVE_GL",
        "HAVE_GLES",
        "HAVE_OPENGL",
        "HAVE_OPENGLES",
        "HAVE_OPENGLES2",
        "HAVE_OPENGLES3",
        "OPENGL",
    }
)
VECX_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def vecx_software_spec_is_well_formed(spec: object) -> bool:
    """Require the complete VecX software-renderer catalog identity."""

    identity = VECX_SOFTWARE_SPEC_IDENTITY
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
                "make_variables": VECX_SOFTWARE_MAKE_VARIABLES,
                "git_version": {
                    "derivation": VECX_NATIVE_GIT_VERSION_DERIVATION,
                    "value": VECX_NATIVE_GIT_VERSION,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
                "replacement": VECX_METADATA_REPLACEMENT,
            },
            "targets": identity["targets"],
            "validation": {
                "forbidden_needed_prefixes": identity[
                    "forbidden_needed_prefixes"
                ]
            },
        }
    )


def vecx_software_identity_is_well_formed(spec: object) -> bool:
    """Recognize VecX while detailed validators inspect mutable subcontracts."""

    if not isinstance(spec, dict):
        return False
    identity = VECX_SOFTWARE_SPEC_IDENTITY
    source = spec.get("source", {})
    build = spec.get("build", {})
    metadata = spec.get("metadata", {})
    validation = spec.get("validation", {})
    return bool(
        isinstance(source, dict)
        and isinstance(build, dict)
        and isinstance(metadata, dict)
        and isinstance(validation, dict)
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
        and validation.get("forbidden_needed_prefixes")
        == identity["forbidden_needed_prefixes"]
    )


def vecx_metadata_replacement_contract_is_well_formed(
    value: object,
) -> bool:
    """Recognize only the reviewed VecX whole-file metadata replacement."""

    return bool(isinstance(value, dict) and value == VECX_METADATA_REPLACEMENT)


def vecx_command_tokens_are_software_only(tokens: list[str]) -> bool:
    """Reject VecX compiler/linker argv that names a GPU implementation."""

    lowered_tokens = [token.casefold() for token in tokens]
    return not (
        any(
            token.startswith(("-lgl", "-legl", "-lgles", "-lopengl"))
            for token in lowered_tokens
        )
        or any(
            Path(token).name.casefold().startswith(
                ("libgl", "libegl", "libgles", "libopengl")
            )
            for token in tokens
        )
        or any(
            "glsym" in token.casefold()
            or Path(token).name.casefold().startswith("rglgen")
            for token in tokens
        )
    )


def vecx_software_golden_source_is_well_formed(
    core_id: object, source: object
) -> bool:
    """Bind a promoted VecX source record to the exact reviewed tree."""

    identity = VECX_SOFTWARE_SPEC_IDENTITY
    return bool(
        core_id == VECX_CORE_ID
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


def vecx_combined_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted make/version/metadata VecX contract."""

    return bool(
        isinstance(build, dict)
        and core_id == VECX_CORE_ID
        and source_commit == VECX_SOFTWARE_SPEC_IDENTITY["source_commit"]
        and vecx_software_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "make_variables": VECX_SOFTWARE_MAKE_VARIABLES,
            "git_version": {
                "derivation": VECX_NATIVE_GIT_VERSION_DERIVATION,
                "value": VECX_NATIVE_GIT_VERSION,
            },
            "metadata_replacement": VECX_METADATA_REPLACEMENT,
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


VECX_LOG_CONTRACT = COnlyLogContract(
    core_id=VECX_CORE_ID,
    expected_compile_count=VECX_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=VECX_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        VECX_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=VECX_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=VECX_SOFTWARE_SPEC_IDENTITY["artifact_name"],
    expected_link_options=VECX_EXPECTED_LINK_OPTIONS,
    source_commit=VECX_SOFTWARE_SPEC_IDENTITY["source_commit"],
    source_tree=VECX_SOFTWARE_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=VECX_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def vecx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove VecX source, software markers, diagnostics, compile, and link."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    lines = build_log_text.splitlines()
    ordered_markers = (
        VECX_SOURCE_HEAD_MARKER,
        *VECX_MAKE_MARKERS,
        VECX_NATIVE_VERSION_MARKER,
    )
    if (
        any(
            marker in lowered_log
            for marker in VECX_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or any(
            marker in lowered_log
            for marker in VECX_FORBIDDEN_GPU_LOG_MARKERS
        )
        or VECX_MAKE_FAILURE_RE.search(build_log_text) is not None
        or any(lines.count(marker) != 1 for marker in ordered_markers)
        or lines.count(VECX_METADATA_REPLACEMENT_MARKER) != 1
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != VECX_EXPECTED_COMPILE_COUNT
        or build_log_text.count(VECX_NATIVE_GIT_VERSION_LOG_TOKEN)
        != VECX_EXPECTED_COMPILE_COUNT
    ):
        return False
    marker_positions = [lines.index(marker) for marker in ordered_markers]
    compile_positions = [
        index
        for index, line in enumerate(lines)
        if VECX_NATIVE_GIT_VERSION_LOG_TOKEN in line and " -c " in line
    ]
    link_positions = [
        index
        for index, line in enumerate(lines)
        if " -ovecx_libretro.so " in line and " -c " not in line
    ]
    metadata_position = lines.index(VECX_METADATA_REPLACEMENT_MARKER)
    try:
        ordered_link_argv = tuple(shlex.split(lines[link_positions[0]]))
    except (IndexError, ValueError):
        return False
    if (
        marker_positions != sorted(marker_positions)
        or len(compile_positions) != VECX_EXPECTED_COMPILE_COUNT
        or len(link_positions) != 1
        or marker_positions[-1] >= min(compile_positions)
        or max(compile_positions) >= link_positions[0]
        or link_positions[0] >= metadata_position
        or ordered_link_argv != VECX_EXPECTED_ORDERED_LINK_ARGV.get(arch)
    ):
        return False
    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        VECX_LOG_CONTRACT,
    )
