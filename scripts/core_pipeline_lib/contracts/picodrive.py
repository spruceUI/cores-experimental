"""Exact Picodrive source-root build, host-generator, and log contract."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import PurePosixPath
import re
import shlex

from ..errors import PipelineError
from ..foundation import sha256_bytes
from .command_line import (
    command_line_is_lexically_safe,
    ordered_command_argv_sha256,
    output_option,
)
from .compiler import TARGET_COMPILERS, TARGET_CXX_COMPILERS
from .log_checks import lines_sha256 as _lines_sha256, multiset_lines_sha256 as _multiset_lines_sha256


PICODRIVE_CORE_ID = "picodrive"
PICODRIVE_BUILD_ARTIFACT_NAME = "picodrive_libretro.so"
PICODRIVE_LOG_CONTRACT_ID = "picodrive-source-root-v1"
PICODRIVE_LOG_PROOF_KIND = "core-arch-source"

PICODRIVE_SOURCE_COMMIT = "f0d4a0118a9733a1f10bce5a4ac772c474f9300d"
PICODRIVE_SOURCE_TREE = "a9e95a725edb219535032f18d03677361d5657bc"
PICODRIVE_SOURCE_DATE_EPOCH = 1775134253
PICODRIVE_GIT_REVISION = "-f0d4a011"
PICODRIVE_RECIPE_PROFILE_KIND = "picodrive-v1"
PICODRIVE_ARMHF_HOST_TOOLS = {
    "CYCLONE_CC": "gcc",
    "CYCLONE_CXX": "g++",
}
PICODRIVE_RECIPE_PROFILE = {
    "kind": PICODRIVE_RECIPE_PROFILE_KIND,
    "git_revision": PICODRIVE_GIT_REVISION,
    "armhf_host_tools": PICODRIVE_ARMHF_HOST_TOOLS,
}
PICODRIVE_ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=1",
    "HWCAP2_CRC32=16",
    "HWCAP2_SHA1=4",
    "HWCAP2_SHA2=8",
]
PICODRIVE_FORBIDDEN_NEEDED_PREFIXES = [
    "libEGL",
    "libGL",
    "libGLES",
    "libOpenGL",
    "libSDL",
    "libstdc++",
    "libz",
]

PICODRIVE_METADATA_REPLACEMENT_KIND = "whole-file-v1"
PICODRIVE_METADATA_REPLACEMENT_PATH = "metadata/picodrive/source-v1.info"
PICODRIVE_METADATA_PREIMAGE_SHA256 = (
    "35cef57b4b61d95a86e1ceee3a7c325d9d16bbdc136b4b3a556e808864de06c5"
)
PICODRIVE_METADATA_REPLACEMENT_SHA256 = (
    "ee4443f075c57c90b4d7a99c3a7c7e54ee141b21899dc88a3c8c52152556e181"
)
PICODRIVE_METADATA_REPLACEMENT = {
    "kind": PICODRIVE_METADATA_REPLACEMENT_KIND,
    "path": PICODRIVE_METADATA_REPLACEMENT_PATH,
    "preimage_sha256": PICODRIVE_METADATA_PREIMAGE_SHA256,
    "replacement_sha256": PICODRIVE_METADATA_REPLACEMENT_SHA256,
}

PICODRIVE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-picodrive.yml",
    "source_url": "https://github.com/libretro/picodrive.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": PICODRIVE_SOURCE_COMMIT,
    "source_tree": PICODRIVE_SOURCE_TREE,
    "source_key": PICODRIVE_CORE_ID,
    "source_dir": "libretro-picodrive",
    "output_path": "libretro-picodrive/picodrive_libretro.so",
    "artifact_name": PICODRIVE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/picodrive_libretro.info"
    ),
    "metadata_artifact_name": "picodrive_libretro.info",
    "targets": ["arm64", "armhf"],
}

PICODRIVE_SUBMODULES = [
    {
        "state": " ",
        "commit": "3ac7cf1bdeecb60e2414980e8dc72ff092f69769",
        "path": "cpu/cyclone",
    },
    {
        "state": " ",
        "commit": "e62ac5995b1c7ef65ece35293914843b8ee57d49",
        "path": "pico/cd/libchdr",
    },
    {
        "state": " ",
        "commit": "a2dfc20ff507e4fd075cd325620bcea655e2c1f7",
        "path": "pico/sound/emu2413",
    },
    {
        "state": " ",
        "commit": "dd762b861ecadf5ddd5fb03e9ca1db6707b54fbb",
        "path": "platform/common/dr_libs",
    },
    {
        "state": " ",
        "commit": "d1a166c83ab445b1c14bc83d37c84e18d172e5f5",
        "path": "platform/common/dr_libs/tests/external/miniaudio",
    },
    {
        "state": " ",
        "commit": "9ed5822606dd7ff20a782a882e8fd611cb53ba88",
        "path": "platform/libpicofe",
    },
]

PICODRIVE_MAKE_PROGRAM = {
    "arm64": "/usr/bin/make",
    "armhf": "/usr/bin/gmake",
}
PICODRIVE_TARGET_CC = {
    "arm64": "aarch64-linux-gnu-gcc",
    "armhf": "arm-a30-linux-gnueabihf-gcc",
}
PICODRIVE_TARGET_CXX = {
    "arm64": "aarch64-linux-gnu-g++",
    "armhf": "arm-a30-linux-gnueabihf-g++",
}
PICODRIVE_RECIPE_MARKER = {
    "arm64": (
        "CORE_PIPELINE_PICODRIVE_RECIPE|picodrive-v1|-f0d4a011|"
        "/usr/bin/make|none|none"
    ),
    "armhf": (
        "CORE_PIPELINE_PICODRIVE_RECIPE|picodrive-v1|-f0d4a011|"
        "/usr/bin/gmake|gcc|g++"
    ),
}
PICODRIVE_BUILD_BEGIN_MARKER = {
    arch: f"CORE_PIPELINE_PICODRIVE_BUILD_BEGIN|{arch}"
    for arch in PICODRIVE_MAKE_PROGRAM
}
PICODRIVE_BUILD_END_MARKER = {
    arch: f"CORE_PIPELINE_PICODRIVE_BUILD_END|{arch}"
    for arch in PICODRIVE_MAKE_PROGRAM
}
PICODRIVE_METADATA_REPLACEMENT_MARKER = (
    "CORE_PIPELINE_METADATA_REPLACEMENT|whole-file-v1|"
    f"{PICODRIVE_METADATA_PREIMAGE_SHA256}|"
    f"{PICODRIVE_METADATA_REPLACEMENT_SHA256}"
)

# Each SHA is over sorted body lines, with one trailing newline per line. This
# accepts harmless ``-j7`` line scheduling differences while binding every
# emitted compiler, generator, diagnostic, and link line (including blanks).
PICODRIVE_EXPECTED_BUILD_BODY_LINE_COUNT = {"arm64": 129, "armhf": 168}
PICODRIVE_EXPECTED_BUILD_BODY_MULTISET_SHA256 = {
    "arm64": "8fe37c06d110c90129440d72e0a572135cc743438b76ec2ee86675a59eb92c0e",
    "armhf": "ebf32cdae727fb1422fe896a701aec946748338753b38816d2342449358c11ac",
}
PICODRIVE_EXPECTED_C_COMPILE_COUNT = {"arm64": 124, "armhf": 122}
PICODRIVE_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 0, "armhf": 15}
PICODRIVE_EXPECTED_COMPILE_PAIR_SHA256 = {
    "arm64": "3fd6d56743e6732cf078e73e3c64a376d1b3037adaf16b3d8dd0ed0e9cb375f5",
    "armhf": "0e4462e5f9ebef8c30b217794dd3fbbb8b19b49786933560a6bb809b760e553b",
}
PICODRIVE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "590b8b77f135729699d5fe622ebc76f4e85124453c2af52bc2d34fe0440fc0c0",
    "armhf": "64dc0b4926e9d31a418387a5a5ff5d97cdd71ba37ad7b39c81caabb5e8130d28",
}
PICODRIVE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256 = {
    "arm64": "6e4f27112e568b293f583238e251c6c21735f3fc66c0e70afe73289ebbcefbe7",
    "armhf": "ce80346419f254666884d0daf92bb6e361e2763008a52c76efdd70ce7b05c94b",
}
PICODRIVE_EXPECTED_LINK_INVOCATION_SHA256 = {
    "arm64": "a129541b048dadfaaf6222ea0c0bfda5bc44dc368aa6b80bbcfe7ef196ecfdc6",
    "armhf": "9fa936c54d16254cede62996c9163fc1b7b986e23c9e2a2fa407606283afb788",
}
PICODRIVE_EXPECTED_LINK_OBJECT_COUNT = {"arm64": 124, "armhf": 137}
PICODRIVE_EXPECTED_LINK_OBJECT_SHA256 = {
    "arm64": "86d76b9b0a9c8b542882b79dfe61051d25410d41bbabd674ec6aeb6a852837d4",
    "armhf": "9d2a47a3af3e6dfb1dbdd4a2686152d2b334495fdd9dcabfd1d3bcae45915e86",
}
PICODRIVE_EXPECTED_ARMHF_HOST_COMMAND_SHA256 = (
    "5c96bd231275c475b66d41560f554fc79e148fb83808960023c29e7757ab7840"
)

PICODRIVE_ARM64_DIAGNOSTIC_BLOCK = (
    'cpu/fame/famec.c:27: warning: "FAMEC_NO_GOTOS" redefined',
    "   27 | #define FAMEC_NO_GOTOS",
    "      | ",
    "<command-line>: note: this is the location of the previous definition",
)
PICODRIVE_ARM64_DIAGNOSTIC_BLOCK_SHA256 = (
    "5727ca1b53a09407fa499982fb4303983194c8a56ff3aedf31fdbb715da5cca4"
)
PICODRIVE_ARM64_DIAGNOSTIC_MULTISET_SHA256 = (
    "d1c473daebe3f54694718b1ee58438f27b695192f6c1e6ec5ae7072b98f4dbc0"
)
PICODRIVE_ARMHF_REVIEWED_DIAGNOSTICS = (
    "make[1]: warning: jobserver unavailable: using -j1.  Add '+' to parent make rule.",
    "./mkoffsets.sh: 24: file: not found",
    "make[1]: warning: jobserver unavailable: using -j1.  Add '+' to parent make rule.",
    "lto-wrapper: warning: using serial compilation of 16 LTRANS jobs",
    "lto-wrapper: note: see the '-flto' option documentation for more information",
    (
        "/opt/a30/lib/gcc/arm-a30-linux-gnueabihf/13.2.0/../../../../"
        "arm-a30-linux-gnueabihf/bin/ld: warning: cpu/DrZ80/drz80.o: "
        "missing .note.GNU-stack section implies executable stack"
    ),
    (
        "/opt/a30/lib/gcc/arm-a30-linux-gnueabihf/13.2.0/../../../../"
        "arm-a30-linux-gnueabihf/bin/ld: NOTE: This behaviour is deprecated "
        "and will be removed in a future version of the linker"
    ),
)
PICODRIVE_ARMHF_REVIEWED_DIAGNOSTIC_SHA256 = (
    "02c58c0a03474e419f9b657e03d579ee03125b03543edf57baff2a25076c322c"
)
PICODRIVE_ARMHF_GENERATOR_FACTS = (
    "building Cyclone...",
    (
        "make[1]: Entering directory "
        "'/libretro-super/libretro-picodrive/cpu/cyclone'"
    ),
    "./cyclone_gen",
    "  Cyclone 68000 Emulator v0.099 - Core Creator",
    "Making Cyclone.s...",
    "Creating Opcodes: [0123456789abcdef]",
    "~36426 ARM instructions used for opcode handlers",
    (
        "make[1]: Leaving directory "
        "'/libretro-super/libretro-picodrive/cpu/cyclone'"
    ),
)
PICODRIVE_ARMHF_GENERATOR_FACT_SHA256 = (
    "fc690940418606250f69ce64dff8b677007ceffa2710ba21b250c82ca455652a"
)

PICODRIVE_CONTROL_LOG_SHA256 = {
    "arm64": frozenset(
        {
            "18c3f930873fd3fce98b4bc73de7e247b0af6eab9ab6d717b8337adb4ae0b21b",
            "787f6d795c5eb1416a85407a4d59f991e9ea5ee8a83234e0cc71148874e7c672",
        }
    ),
    "armhf": frozenset(
        {
            "cf0b1bdd1ccc2f010051757154714fa1e22852075efeafedcad8d2f391c53710",
            "0d766928b832197adf978e62df15dcfffc87add5e7fc52728737dbb84000e902",
        }
    ),
}
PICODRIVE_REVIEWED_OUTPUT_FACTS = {
    "artifacts": {
        "arm64": {
            "sha256": (
                "922361592a982d8f6348a0d25128fdf5491b2bb80dc40e094751c9fdc9867296"
            ),
            "size": 2069560,
        },
        "armhf": {
            "sha256": (
                "2356aba1925fef276fe3a0edcac5fa07f5ce81d3bc52a7af597d9c325d0fac3a"
            ),
            "size": 2378860,
        },
    },
    "metadata": {
        "sha256": PICODRIVE_METADATA_REPLACEMENT_SHA256,
        "size": 1892,
    },
}

PICODRIVE_FORBIDDEN_LOG_FRAGMENTS = (
    "aborted",
    "bus error",
    "command not found",
    "core dumped",
    "dubious ownership",
    "error:",
    "fatal:",
    "file format not recognized",
    "illegal instruction",
    "internal compiler error",
    "killed",
    "permission denied",
    "segmentation fault",
    "undefined reference",
)
PICODRIVE_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Build-time patch: collapse tools/Makefile's multi-line offsets recipe to one
# physical line. Declared for armhf only (the arch that carries
# compile_definitions and therefore exercises the compile-definitions checker
# whose shlex.split chokes on the multi-line recipe echo). See
# patches/README.md; revalidate the digests if the pinned source is bumped.
PICODRIVE_TOOLS_MAKEFILE_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/picodrive/tools-makefile-single-line-offsets.patch",
    "patch_sha256": (
        "2c442768b54d5ffd52ab06530e67dc582c4f9b0dac8f2d1d9ccea9739444053c"
    ),
    "source_path": "tools/Makefile",
    "preimage_sha256": (
        "9c738f02c4afb1b13d95421f74092d9af77b8c8f0f8ae55dfa0e9b7b4f6df44d"
    ),
    "postimage_sha256": (
        "2d36ea4092510e7547274ac4361897c9992ccb7db2362c622c6d9e1d76426843"
    ),
}
PICODRIVE_OVERLAYS = {"armhf": [PICODRIVE_TOOLS_MAKEFILE_OVERLAY]}


def _exact_spec(*, include_replacement: bool = True) -> dict:
    identity = PICODRIVE_SPEC_IDENTITY
    metadata = {
        "source_path": identity["metadata_source_path"],
        "artifact_name": identity["metadata_artifact_name"],
    }
    if include_replacement:
        metadata["replacement"] = PICODRIVE_METADATA_REPLACEMENT
    return {
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
            "source_date_epoch": PICODRIVE_SOURCE_DATE_EPOCH,
            "compile_definitions": {
                "armhf": PICODRIVE_ARMHF_COMPILE_DEFINITIONS,
            },
            "recipe_profile": PICODRIVE_RECIPE_PROFILE,
            "overlays": PICODRIVE_OVERLAYS,
        },
        "metadata": metadata,
        "targets": identity["targets"],
        "validation": {
            "forbidden_needed_prefixes": PICODRIVE_FORBIDDEN_NEEDED_PREFIXES,
        },
    }


def picodrive_spec_is_well_formed(spec: object) -> bool:
    """Require Picodrive's complete immutable catalog contract."""

    return bool(isinstance(spec, dict) and spec == _exact_spec())


def picodrive_identity_is_well_formed(spec: object) -> bool:
    """Bind Picodrive while the shared validator diagnoses replacement drift."""

    if not isinstance(spec, dict):
        return False
    expected = _exact_spec(include_replacement=False)
    actual = dict(spec)
    metadata = actual.get("metadata")
    if not isinstance(metadata, dict):
        return False
    actual["metadata"] = {
        key: value for key, value in metadata.items() if key != "replacement"
    }
    return actual == expected


def picodrive_recipe_profile_is_well_formed(value: object) -> bool:
    """Recognize only the reviewed source-root Picodrive build profile."""

    return bool(isinstance(value, dict) and value == PICODRIVE_RECIPE_PROFILE)


def picodrive_metadata_replacement_contract_is_well_formed(
    value: object,
) -> bool:
    """Recognize only the reviewed Picodrive whole-file metadata replacement."""

    return bool(
        isinstance(value, dict) and value == PICODRIVE_METADATA_REPLACEMENT
    )


def picodrive_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind promoted evidence to the exact source and recursive submodules."""

    identity = PICODRIVE_SPEC_IDENTITY
    return bool(
        core_id == PICODRIVE_CORE_ID
        and isinstance(source, dict)
        and source
        == {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": PICODRIVE_SUBMODULES,
        }
    )


def picodrive_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
    arch: object,
) -> bool:
    """Require the normalized recipe, epoch, replacement, and log identity."""

    expected_definitions = {
        "arm64": [],
        "armhf": PICODRIVE_ARMHF_COMPILE_DEFINITIONS,
    }.get(arch)
    if (
        not isinstance(build, dict)
        or source_commit != PICODRIVE_SOURCE_COMMIT
        or not picodrive_golden_source_is_well_formed(core_id, source)
        or expected_definitions is None
    ):
        return False
    return bool(
        build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": expected_definitions,
            "recipe_profile": PICODRIVE_RECIPE_PROFILE,
            "source_date_epoch": PICODRIVE_SOURCE_DATE_EPOCH,
            "metadata_replacement": PICODRIVE_METADATA_REPLACEMENT,
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def picodrive_recipe_shell(spec: object, arch: str) -> str:
    """Return the reviewed direct source-root invocation for one target."""

    if (
        not picodrive_spec_is_well_formed(spec)
        or arch not in PICODRIVE_MAKE_PROGRAM
    ):
        raise PipelineError(
            "Picodrive recipe shell requires its exact reviewed spec"
        )
    make_program = PICODRIVE_MAKE_PROGRAM[arch]
    lines = [
        "unset GIT_REVISION CYCLONE_CC CYCLONE_CXX",
        f"export GIT_REVISION={shlex.quote(PICODRIVE_GIT_REVISION)}",
    ]
    if arch == "armhf":
        lines.extend(
            [
                "export CYCLONE_CC=gcc",
                "export CYCLONE_CXX=g++",
            ]
        )
    lines.extend(
        [
            f"printf '%s\\n' {shlex.quote(PICODRIVE_RECIPE_MARKER[arch])}",
            f"printf '%s\\n' {shlex.quote(PICODRIVE_BUILD_BEGIN_MARKER[arch])}",
            "cd /libretro-super/libretro-picodrive",
            f'{make_program} -f Makefile.libretro platform="unix" -j7',
            f"printf '%s\\n' {shlex.quote(PICODRIVE_BUILD_END_MARKER[arch])}",
            "cd /libretro-super",
        ]
    )
    return "\n".join(lines)


def _normalized_path(value: object, suffixes: tuple[str, ...]) -> str | None:
    if not isinstance(value, str) or not value.endswith(suffixes):
        return None
    normalized = value.removeprefix("./")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or path.as_posix() != normalized
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(
            re.fullmatch(r"[A-Za-z0-9_+.-]+", part) is None
            for part in path.parts
        )
    ):
        return None
    return normalized


def _compile_invocation(
    tokens: list[str],
) -> tuple[str, str, tuple[str, ...]] | None:
    parsed_output = output_option(tokens)
    if tokens.count("-c") != 1 or parsed_output is None:
        return None
    raw_output, output_indexes = parsed_output
    output = _normalized_path(raw_output, (".o",))
    if output is None or "--" in tokens or any("@" in token for token in tokens):
        return None
    option_operand_indexes: set[int] = set()
    for index, token in enumerate(tokens[1:], start=1):
        if token == "-I":
            option_operand_indexes.add(index + 1)
    source_indexes = [
        index
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes
        and index not in option_operand_indexes
        and token != "-c"
        and not token.startswith("-")
    ]
    if len(source_indexes) != 1:
        return None
    source_index = source_indexes[0]
    source = _normalized_path(tokens[source_index], (".c", ".s", ".S"))
    if source is None or source.rsplit(".", 1)[0] + ".o" != output:
        return None
    canonical: list[str] = []
    first_output_index = min(output_indexes)
    for index, token in enumerate(tokens):
        if index == first_output_index:
            canonical.extend(("-o", output))
        elif index in output_indexes:
            continue
        elif index == source_index:
            canonical.append(source)
        else:
            canonical.append(token)
    return output, source, tuple(canonical)


def _compile_pair_sha256(
    invocations: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> str:
    return sha256_bytes(
        "".join(
            f"{output}|{source}\n"
            for output, source, _tokens in sorted(invocations)
        ).encode("utf-8")
    )


def _compile_invocation_sha256(
    invocations: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> str:
    material = [
        [output, source, list(tokens)]
        for output, source, tokens in sorted(invocations)
    ]
    return sha256_bytes(
        json.dumps(material, ensure_ascii=True, separators=(",", ":")).encode(
            "ascii"
        )
    )


def _raw_invocation_sha256(invocations: tuple[tuple[str, ...], ...]) -> str:
    material = sorted([list(tokens) for tokens in invocations])
    return sha256_bytes(
        json.dumps(material, ensure_ascii=True, separators=(",", ":")).encode(
            "ascii"
        )
    )


def _object_sha256(objects: tuple[str, ...]) -> str:
    return sha256_bytes(
        "".join(f"{path}\n" for path in sorted(objects)).encode("utf-8")
    )


def _picodrive_build_body(
    build_log_text: str,
    arch: str,
) -> tuple[str, ...] | None:
    recipe_marker = PICODRIVE_RECIPE_MARKER.get(arch)
    begin_marker = PICODRIVE_BUILD_BEGIN_MARKER.get(arch)
    end_marker = PICODRIVE_BUILD_END_MARKER.get(arch)
    if recipe_marker is None or begin_marker is None or end_marker is None:
        return None
    lines = build_log_text.splitlines()
    observed_markers = tuple(
        line
        for line in lines
        if line.startswith("CORE_PIPELINE_PICODRIVE_")
    )
    if observed_markers != (recipe_marker, begin_marker, end_marker):
        return None
    recipe_position = lines.index(recipe_marker)
    begin_position = lines.index(begin_marker)
    end_position = lines.index(end_marker)
    if begin_position != recipe_position + 1 or end_position <= begin_position + 1:
        return None
    body = tuple(lines[begin_position + 1 : end_position])
    if (
        len(body) != PICODRIVE_EXPECTED_BUILD_BODY_LINE_COUNT.get(arch)
        or _multiset_lines_sha256(body)
        != PICODRIVE_EXPECTED_BUILD_BODY_MULTISET_SHA256.get(arch)
    ):
        return None
    return body


def _picodrive_command_scope_is_exact(
    body: tuple[str, ...], arch: str
) -> bool:
    target_cc = PICODRIVE_TARGET_CC.get(arch)
    target_cxx = PICODRIVE_TARGET_CXX.get(arch)
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if (
        target_cc is None
        or target_cxx is None
        or expected_compilers is None
        or expected_cxx_compilers is None
    ):
        return False
    compile_invocations: list[tuple[str, str, tuple[str, ...]]] = []
    raw_compile_invocations: list[tuple[str, ...]] = []
    compile_positions: list[int] = []
    link_positions: list[int] = []
    link_tokens: list[str] | None = None
    host_commands: list[list[str]] = []
    for position, line in enumerate(body):
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens:
            continue
        command = tokens[0]
        if command == target_cxx or command in expected_cxx_compilers:
            return False
        if command == target_cc:
            if not command_line_is_lexically_safe(line):
                return False
            revision_token = f'-DREVISION="{PICODRIVE_GIT_REVISION}"'
            if tokens.count(revision_token) != 2:
                return False
            for definition in (
                PICODRIVE_ARMHF_COMPILE_DEFINITIONS if arch == "armhf" else []
            ):
                if tokens.count(f"-D{definition}") != 1:
                    return False
            if arch == "arm64" and any(
                token.startswith("-DHWCAP2_") for token in tokens
            ):
                return False
            if "-c" in tokens:
                invocation = _compile_invocation(tokens)
                if invocation is None:
                    return False
                compile_invocations.append(invocation)
                raw_compile_invocations.append(tuple(tokens))
                compile_positions.append(position)
            else:
                parsed_output = output_option(tokens)
                if (
                    parsed_output is None
                    or parsed_output[0] != PICODRIVE_BUILD_ARTIFACT_NAME
                ):
                    return False
                link_positions.append(position)
                link_tokens = tokens
            continue
        if command in expected_compilers:
            return False
        if command in {"gcc", "g++", "./cyclone_gen"}:
            host_commands.append(tokens)

    if len(link_positions) != 1 or link_tokens is None or not compile_positions:
        return False
    c_count = sum(source.endswith(".c") for _output, source, _ in compile_invocations)
    asm_count = len(compile_invocations) - c_count
    if (
        c_count != PICODRIVE_EXPECTED_C_COMPILE_COUNT.get(arch)
        or asm_count != PICODRIVE_EXPECTED_ASM_COMPILE_COUNT.get(arch)
        or max(compile_positions) >= link_positions[0]
        or _compile_pair_sha256(tuple(compile_invocations))
        != PICODRIVE_EXPECTED_COMPILE_PAIR_SHA256.get(arch)
        or _compile_invocation_sha256(tuple(compile_invocations))
        != PICODRIVE_EXPECTED_COMPILE_INVOCATION_SHA256.get(arch)
        or _raw_invocation_sha256(tuple(raw_compile_invocations))
        != PICODRIVE_EXPECTED_RAW_COMPILE_INVOCATION_SHA256.get(arch)
        or ordered_command_argv_sha256(link_tokens)
        != PICODRIVE_EXPECTED_LINK_INVOCATION_SHA256.get(arch)
    ):
        return False

    parsed_link_output = output_option(link_tokens)
    assert parsed_link_output is not None
    output_indexes = parsed_link_output[1]
    link_objects = tuple(
        token.removeprefix("./")
        for index, token in enumerate(link_tokens[1:], start=1)
        if index not in output_indexes and token.endswith(".o")
    )
    if (
        len(link_objects) != PICODRIVE_EXPECTED_LINK_OBJECT_COUNT.get(arch)
        or _object_sha256(link_objects)
        != PICODRIVE_EXPECTED_LINK_OBJECT_SHA256.get(arch)
        or Counter(link_objects)
        != Counter(output for output, _source, _tokens in compile_invocations)
    ):
        return False

    if arch == "arm64":
        return not host_commands
    return bool(
        Counter(tokens[0] for tokens in host_commands)
        == Counter({"g++": 8, "gcc": 1, "./cyclone_gen": 1})
        and _raw_invocation_sha256(tuple(tuple(tokens) for tokens in host_commands))
        == PICODRIVE_EXPECTED_ARMHF_HOST_COMMAND_SHA256
    )


def _picodrive_diagnostics_are_exact(
    body: tuple[str, ...], arch: str
) -> bool:
    if arch == "arm64":
        diagnostics = PICODRIVE_ARM64_DIAGNOSTIC_BLOCK
        observed = tuple(
            line for line in body if line in diagnostics
        )
        return bool(
            Counter(observed) == Counter(diagnostics)
            and _lines_sha256(diagnostics)
            == PICODRIVE_ARM64_DIAGNOSTIC_BLOCK_SHA256
            and _multiset_lines_sha256(observed)
            == PICODRIVE_ARM64_DIAGNOSTIC_MULTISET_SHA256
        )
    if arch != "armhf":
        return False
    observed = tuple(
        line
        for line in body
        if "warning:" in line.casefold()
        or "note:" in line.casefold()
        or "file: not found" in line
    )
    generator_facts = tuple(
        line for line in body if line in PICODRIVE_ARMHF_GENERATOR_FACTS
    )
    return bool(
        observed == PICODRIVE_ARMHF_REVIEWED_DIAGNOSTICS
        and _lines_sha256(observed)
        == PICODRIVE_ARMHF_REVIEWED_DIAGNOSTIC_SHA256
        and generator_facts == PICODRIVE_ARMHF_GENERATOR_FACTS
        and _lines_sha256(generator_facts)
        == PICODRIVE_ARMHF_GENERATOR_FACT_SHA256
    )


def picodrive_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove exact source-root commands, host tools, diagnostics, and framing."""

    if (
        not isinstance(build_log_text, str)
        or core_id != PICODRIVE_CORE_ID
        or source_commit != PICODRIVE_SOURCE_COMMIT
        or source_tree != PICODRIVE_SOURCE_TREE
    ):
        return False
    lowered = build_log_text.casefold()
    if (
        any(fragment in lowered for fragment in PICODRIVE_FORBIDDEN_LOG_FRAGMENTS)
        or PICODRIVE_MAKE_FAILURE_RE.search(build_log_text) is not None
    ):
        return False
    body = _picodrive_build_body(build_log_text, arch)
    return bool(
        body is not None
        and _picodrive_command_scope_is_exact(body, arch)
        and _picodrive_diagnostics_are_exact(body, arch)
    )
