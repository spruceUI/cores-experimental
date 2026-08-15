"""Build-contract normalization and build-log proof primitives.

The launcher remains the composition root: it supplies patchable core-owned
validators and repository I/O services at each compatibility wrapper.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
from typing import NamedTuple

from .errors import PipelineError
from .contracts.compiler import (
    COMPILER_COMMAND_RE,
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from .contracts.command_line import command_line_is_lexically_safe
from .contracts.c_asm import c_asm_compile_invocation
from .contracts.mednafen_wswan import (
    MEDNAFEN_WSWAN_CORE_ID,
    MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.mednafen_pcfx import (
    MEDNAFEN_PCFX_CORE_ID,
    MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS,
    MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    PCFX_PORTABLE_MAKE_PROFILE,
    PCFX_PORTABLE_MAKE_VARIABLES,
)
from .contracts.mednafen_supergrafx import (
    MEDNAFEN_SUPERGRAFX_CORE_ID,
    MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.pokemini import (
    POKEMINI_CORE_ID,
    POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.mgba import (
    MGBA_CORE_ID,
    MGBA_NATIVE_GIT_VERSION,
    MGBA_NATIVE_GIT_VERSION_DERIVATION,
    MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.uzem import UZEM_CORE_ID, UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.vemulator import VEMULATOR_CORE_ID
from .contracts.freeintv import FREEINTV_CORE_ID
from .contracts.gearboy import (
    GEARBOY_CORE_ID,
    GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
)
from .contracts.gearsystem import (
    GEARSYSTEM_CORE_ID,
    GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
)
from .contracts.gearcoleco import (
    GEARCOLECO_CORE_ID,
    GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
)
from .contracts.fmsx import FMSX_CORE_ID, FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.bluemsx import (
    BLUEMSX_CORE_ID,
    BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.vice_x64 import (
    VICE_X64_CORE_ID,
    VICE_X64_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.vice_xvic import (
    VICE_XVIC_CORE_ID,
    VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.vecx import (
    VECX_CORE_ID,
    VECX_FORBIDDEN_COMPILE_MACROS,
    VECX_SOFTWARE_BUILD_KEYS,
    VECX_SOFTWARE_MAKE_PROFILE,
    VECX_SOFTWARE_MAKE_VARIABLES,
    VECX_SOFTWARE_SPEC_IDENTITY,
    vecx_command_tokens_are_software_only,
)
from .contracts.lowresnx import (
    LOWRESNX_CORE_ID,
    LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.potator import (
    POTATOR_CORE_ID,
    POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.race import RACE_CORE_ID, RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.core_2048 import (
    CORE_2048_ID,
    CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.fceumm import FCEUMM_CORE_ID, FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.atari800 import (
    ATARI800_CORE_ID,
    ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.picodrive import PICODRIVE_CORE_ID
from .contracts.mame2003_plus import (
    MAME2003_PLUS_CORE_ID,
    MAME2003_PLUS_GIT_VERSION,
    MAME2003_PLUS_NATIVE_GIT_VERSION,
    MAME2003_PLUS_NATIVE_GIT_VERSION_DERIVATION,
    MAME2003_PLUS_SOURCE_COMMIT,
    mame2003_plus_git_version_markers,
)
from .contracts.fbneo import (
    FBNEO_CORE_ID,
    FBNEO_GIT_VERSION,
    FBNEO_GIT_VERSION_DERIVATION,
    FBNEO_SOURCE_COMMIT,
    fbneo_compile_tokens,
    fbneo_git_version_markers,
)
from .contracts.parallel_n64 import (
    PARALLEL_N64_MAKE_PROFILE,
    PARALLEL_N64_MAKE_VARIABLES,
)
from .contracts.mupen64plus_next import (
    MUPEN64PLUS_NEXT_MAKE_PROFILE,
    MUPEN64PLUS_NEXT_MAKE_VARIABLES,
)
from .contracts.gambatte import (
    GAMBATTE_CORE_ID,
    GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.tgbdual import TGBDUAL_CORE_ID, TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.snes9x2005 import (
    SNES9X2005_CORE_ID,
    SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.snes9x2005_plus import (
    SNES9X2005_PLUS_CORE_ID,
    SNES9X2005_PLUS_MAKE_PROFILE,
    SNES9X2005_PLUS_MAKE_VARIABLES,
    SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.cap32 import CAP32_CORE_ID, CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.crocods import (
    CROCODS_CORE_ID,
    CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.genesis_plus_gx import (
    GENESIS_PLUS_GX_CORE_ID,
    GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.genesis_plus_gx_wide import (
    GENESIS_PLUS_GX_WIDE_CORE_ID,
    GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from .contracts.handy import HANDY_CORE_ID, HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY
from .contracts.stella2014 import (
    STELLA2014_CORE_ID,
    STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)


@dataclass(frozen=True, slots=True)
class BuildContractResolvers:
    """Call-time bindings for launcher-owned, patchable contract validators."""

    spec_validators: Mapping[str, Callable[..., bool]]
    git_version_validators: Mapping[str, Callable[..., bool]]


@dataclass(frozen=True, slots=True)
class BuildContractIO:
    """Repository services needed by overlay validation."""

    repository_root: Path
    reference_path: Callable[[dict, Path, str], Path]
    verified_text: Callable[[Path, str, str], str]
    run_command: Callable[..., object]


ARCH_LAYOUT = {
    "arm64": {
        "directory": "RetroArch/.retroarch/cores64",
        "package_directory": "cores64",
        "elf_class": "ELF64",
        "machine": "AArch64",
    },
    "armhf": {
        "directory": "RetroArch/.retroarch/cores",
        "package_directory": "cores",
        "elf_class": "ELF32",
        "machine": "ARM",
    },
}
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
GENERATED_SOURCE_PATH_RE = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))"
    r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$"
)
COMPILE_DEFINITION_RE = re.compile(
    r"^([A-Z_][A-Z0-9_]*)=(0|[1-9][0-9]{0,9})$"
)
PORTABLE_FFMPEG_MAKE_VARIABLES = {
    "ARCH_AARCH64": 0,
    "ARCH_ARM": 0,
    "ARCH_X86": 0,
    "ARCH_X86_64": 0,
    "HAVE_SSA": 0,
    "LIBRETRO_EMBED_FFMPEG": 1,
    "OPENGL": 0,
}
PORTABLE_FFMPEG_MAKE_PROFILE = "portable-ffmpeg-v1"
PORTABLE_FFMPEG_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/ffmpeg/makefile-ffmpeg-sort-wildcard-sources.patch",
    "patch_sha256": (
        "81e3f8b8722e048eda0749588482257351960862bdcc82c89ac94448e8e280c0"
    ),
    "source_path": "libretro/Makefile.ffmpeg",
    "preimage_sha256": (
        "d5734bff3fdda57246a4cb5b801fe1d97491ccfdb4324582ca9443957ee827e4"
    ),
    "postimage_sha256": (
        "2d223630fb9f7b21827ba848ce2e5d46e408d268dbabd2f3227d82d48821f8c4"
    ),
}
PORTABLE_FFMPEG_OVERLAYS = {
    "arm64": [dict(PORTABLE_FFMPEG_OVERLAY)],
    "armhf": [dict(PORTABLE_FFMPEG_OVERLAY)],
}
PORTABLE_FFMPEG_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "make_variables",
        "output_path",
        "source_date_epoch",
        "source_dir",
        "source_key",
    }
)
GL_DYNAREC_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "make_variables",
        "output_path",
        "source_dir",
        "source_key",
    }
)
UZEM_NATIVE_GIT_VERSION_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "git_version",
        "output_path",
        "source_dir",
        "source_key",
    }
)
NATIVE_GIT_VERSION_SHORT10_BUILD_KEYS = UZEM_NATIVE_GIT_VERSION_BUILD_KEYS.union(
    {"source_date_epoch"}
)
NATIVE_GIT_MAKE_BUILD_KEYS = UZEM_NATIVE_GIT_VERSION_BUILD_KEYS.union(
    {"make_variables"}
)
COMBINED_NATIVE_MAKE_CORE_IDS = frozenset(
    {MEDNAFEN_PCFX_CORE_ID, "snes9x2005_plus", VECX_CORE_ID}
)
NATIVE_GIT_VERSION_C_SCOPE_CORE_IDS = frozenset(
    {
        ATARI800_CORE_ID,
        BLUEMSX_CORE_ID,
        "cap32",
        "crocods",
        FCEUMM_CORE_ID,
        "genesis_plus_gx",
        "genesis_plus_gx_wide",
        CORE_2048_ID,
        LOWRESNX_CORE_ID,
        MAME2003_PLUS_CORE_ID,
        MGBA_CORE_ID,
        POTATOR_CORE_ID,
        RACE_CORE_ID,
        "snes9x2005",
        "snes9x2005_plus",
    }
)
RESERVED_MAKE_VARIABLE_NAMES = frozenset(
    {
        "AR",
        "ARCH",
        "CC",
        "CFLAGS",
        "CHOST",
        "CMAKE_BUILD_PARALLEL_LEVEL",
        "CMAKE_GENERATOR",
        "CMAKE_GENERATOR_PLATFORM",
        "CMAKE_GENERATOR_TOOLSET",
        "CMAKE_TOOLCHAIN_FILE",
        "CPPFLAGS",
        "CROSS_COMPILE",
        "CXX",
        "CXXFLAGS",
        "LDFLAGS",
        "MAKE",
        "MAKEFILES",
        "MAKEFLAGS",
        "MAKEOVERRIDES",
        "GNUMAKEFLAGS",
        "MFLAGS",
        "RANLIB",
        "SHELL",
        "SOURCE_DATE_EPOCH",
        "STRIP",
    }
)
PORTABLE_FFMPEG_COMPILE_DEFINITIONS = (
    "ARCH_AARCH64=0",
    "ARCH_ARM=0",
    "ARCH_X86=0",
    "ARCH_X86_64=0",
    "LIBRETRO_EMBED_FFMPEG=1",
)
PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS = frozenset(
    {"HAVE_GL_FFT", "HAVE_OPENGL", "HAVE_OPENGLES", "HAVE_SSA", "OPENGL"}
)
GIT_VERSION_DERIVATION = "hyphen-short7-v1"
GIT_VERSION_RE = re.compile(r"^-[0-9a-f]{7}$")
GIT_VERSION_C_SCOPE = "c"
GIT_VERSION_CXX_SCOPE = "cxx"
GIT_VERSION_COMPILER_SCOPES = frozenset(
    {GIT_VERSION_C_SCOPE, GIT_VERSION_CXX_SCOPE}
)
NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
NATIVE_GIT_VERSION_RE = re.compile(r"^ [0-9a-f]{7}$")
NATIVE_GIT_VERSION_SHORT8_DERIVATION = (
    MAME2003_PLUS_NATIVE_GIT_VERSION_DERIVATION
)
NATIVE_GIT_VERSION_SHORT9_DERIVATION = MGBA_NATIVE_GIT_VERSION_DERIVATION
NATIVE_GIT_VERSION_SHORT9_RE = re.compile(r"^ [0-9a-f]{9}$")
NATIVE_GIT_VERSION_SHORT10_DERIVATION = "native-space-short10-v1"
NATIVE_GIT_VERSION_SHORT10_RE = re.compile(r"^ [0-9a-f]{10}$")
NATIVE_GIT_DESCRIBE_DERIVATION = "native-git-describe-v1"
NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES = {
    MGBA_CORE_ID: MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
}
NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES = {
    VICE_X64_CORE_ID: VICE_X64_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    VICE_XVIC_CORE_ID: VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY,
}
NATIVE_GIT_VERSION_SPEC_IDENTITIES = {
    ATARI800_CORE_ID: ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    UZEM_CORE_ID: UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    MEDNAFEN_WSWAN_CORE_ID: MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    MEDNAFEN_PCFX_CORE_ID: MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    MEDNAFEN_SUPERGRAFX_CORE_ID: (
        MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    ),
    POKEMINI_CORE_ID: POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    FMSX_CORE_ID: FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    BLUEMSX_CORE_ID: BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    CORE_2048_ID: CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    LOWRESNX_CORE_ID: LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    POTATOR_CORE_ID: POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    RACE_CORE_ID: RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    FCEUMM_CORE_ID: FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    GAMBATTE_CORE_ID: GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    TGBDUAL_CORE_ID: TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    CAP32_CORE_ID: CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    CROCODS_CORE_ID: CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    GENESIS_PLUS_GX_CORE_ID: GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    GENESIS_PLUS_GX_WIDE_CORE_ID: (
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY
    ),
    HANDY_CORE_ID: HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    STELLA2014_CORE_ID: STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    SNES9X2005_CORE_ID: SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    SNES9X2005_PLUS_CORE_ID: (
        SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
    ),
}
ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS = frozenset(
    {
        GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY[
            "source_commit"
        ],
    }
)
MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS = frozenset(
    {
        ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    }
)
COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS = (
    ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS
    | MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS
    | {FBNEO_SOURCE_COMMIT, MAME2003_PLUS_SOURCE_COMMIT}
)
EXACT_NATIVE_GIT_VERSION_CORE_IDS = frozenset(
    NATIVE_GIT_VERSION_SPEC_IDENTITIES
).union(
    {FBNEO_CORE_ID, MAME2003_PLUS_CORE_ID},
    NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES
)
NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES = {
    GEARBOY_CORE_ID: GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    GEARSYSTEM_CORE_ID: GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    GEARCOLECO_CORE_ID: GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
}
NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT = {
    identity["source_commit"]: identity["git_version_value"]
    for identity in NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.values()
}
NATIVE_GIT_DESCRIBE_COMPILE_MACROS_BY_COMMIT = {
    identity["source_commit"]: identity["compile_macro"]
    for identity in NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.values()
}
EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS = frozenset(
    NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES
)
EXACT_GIT_VERSION_CORE_IDS = (
    EXACT_NATIVE_GIT_VERSION_CORE_IDS | EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS
)
EXACT_SOURCE_NATIVE_CORE_IDS = frozenset(
    {FREEINTV_CORE_ID, VEMULATOR_CORE_ID}
)
MAX_SOURCE_DATE_EPOCH = 253402300799
TARGET_CMAKE_TOOL_NAMES = {
    "arm64": {
        "ar": "aarch64-linux-gnu-ar",
        "c": "aarch64-linux-gnu-gcc",
        "cxx": "aarch64-linux-gnu-g++",
        "ranlib": "aarch64-linux-gnu-ranlib",
        "strip": "aarch64-linux-gnu-strip",
    },
    "armhf": {
        "ar": "arm-a30-linux-gnueabihf-ar",
        "c": "arm-a30-linux-gnueabihf-gcc",
        "cxx": "arm-a30-linux-gnueabihf-g++",
        "ranlib": "arm-a30-linux-gnueabihf-ranlib",
        "strip": "arm-a30-linux-gnueabihf-strip",
    },
}


def validated_compile_definitions(
    spec: dict,
    *,
    resolvers: BuildContractResolvers,
) -> dict[str, list[str]]:
    build = spec.get("build", {})
    if "compile_definitions" not in build:
        return {}
    if "git_version" in build and not resolvers.spec_validators[
        "fbneo_spec_is_well_formed"
    ](spec):
        raise PipelineError(
            "build.compile_definitions cannot be combined with git_version "
            "outside the exact reviewed FBNeo contract"
        )
    raw = build["compile_definitions"]
    if not isinstance(raw, dict) or not raw:
        raise PipelineError("build.compile_definitions must be a non-empty object")
    targets = spec.get("targets", [])
    if not isinstance(targets, list):
        raise PipelineError("build.compile_definitions requires valid core targets")
    unexpected = sorted(set(raw) - set(targets))
    if unexpected:
        raise PipelineError(
            "build.compile_definitions contains a non-target architecture: "
            + ", ".join(unexpected)
        )
    normalized: dict[str, list[str]] = {}
    for arch, definitions in raw.items():
        if arch not in ARCH_LAYOUT:
            raise PipelineError(
                f"build.compile_definitions architecture is invalid: {arch}"
            )
        if not isinstance(definitions, list) or not definitions:
            raise PipelineError(
                f"build.compile_definitions.{arch} must be a non-empty array"
            )
        if any(not isinstance(definition, str) for definition in definitions):
            raise PipelineError(
                f"build.compile_definitions.{arch} entries must be strings"
            )
        if definitions != sorted(definitions):
            raise PipelineError(
                f"build.compile_definitions.{arch} must be sorted"
            )
        names: set[str] = set()
        for definition in definitions:
            match = COMPILE_DEFINITION_RE.fullmatch(definition)
            if match is None or int(match.group(2)) > 0xFFFFFFFF:
                raise PipelineError(
                    f"build.compile_definitions.{arch} entry is invalid: {definition}"
                )
            if match.group(1) in names:
                raise PipelineError(
                    f"build.compile_definitions.{arch} repeats {match.group(1)}"
                )
            names.add(match.group(1))
        normalized[arch] = list(definitions)
    return normalized


def compile_definitions_for_target(
    spec: dict,
    arch: str,
    *,
    resolvers: BuildContractResolvers,
) -> list[str]:
    if arch not in ARCH_LAYOUT:
        raise PipelineError(f"unknown architecture: {arch}")
    return validated_compile_definitions(spec, resolvers=resolvers).get(arch, [])


class MakeVariableProfileFacts(NamedTuple):
    """Everything bookkeeping-shaped about one reviewed make-variable profile.

    Adding a profile is one entry here (plus its contract-module constants);
    the resolver, contract-name map, validated_make_variables rules, make
    shell, golden-record keys, and snapshot/macro policies all read this
    registry. Profile-specific *behavior* (the FFmpeg marker-ordering proof,
    the Snes9x 2005 Plus macro proof, VecX's divergence diagnostics) stays in
    code -- this table holds only facts. ``expected_build_keys is None`` marks
    the one bespoke profile (VecX) whose validation body remains inline.
    ``spec_validator`` is a name bound by the launcher's call-time resolver,
    preserving its mock.patch.object seam without a launcher import.
    """

    variables: Mapping[str, object]
    contract_name: str
    expected_build_keys: frozenset[str] | None
    spec_validator: str | None = None
    spec_validator_args: tuple = ()
    restriction_message: str | None = None
    forbid_rules: tuple = ()
    requires_epoch: bool = False
    make_subdir_libretro: bool = False
    makefile: str = "Makefile"
    golden_epoch: bool | None = None
    forbidden_compile_macros: frozenset[str] = frozenset()
    expected_overlays: dict | None = None


def _make_variable_profile_facts() -> dict[str, MakeVariableProfileFacts]:
    return {
        PORTABLE_FFMPEG_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=PORTABLE_FFMPEG_MAKE_VARIABLES,
            contract_name="portable FFmpeg",
            expected_build_keys=PORTABLE_FFMPEG_BUILD_KEYS,
            forbid_rules=(
                (
                    ("git_version",),
                    "build.make_variables cannot be combined with git_version "
                    "for the portable FFmpeg contract",
                ),
            ),
            requires_epoch=True,
            make_subdir_libretro=True,
            golden_epoch=True,
            forbidden_compile_macros=PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS,
            expected_overlays=PORTABLE_FFMPEG_OVERLAYS,
        ),
        VECX_SOFTWARE_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=VECX_SOFTWARE_MAKE_VARIABLES,
            contract_name="VecX software",
            expected_build_keys=None,
            makefile="Makefile.libretro",
            forbidden_compile_macros=VECX_FORBIDDEN_COMPILE_MACROS,
        ),
        PCFX_PORTABLE_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=PCFX_PORTABLE_MAKE_VARIABLES,
            contract_name="PC-FX portable",
            expected_build_keys=NATIVE_GIT_MAKE_BUILD_KEYS,
            spec_validator="mednafen_pcfx_spec_is_well_formed",
            restriction_message=(
                "the PC-FX portable make-variable contract is restricted to "
                "the exact reviewed source, native version, and recipe"
            ),
            forbid_rules=(
                (
                    ("source_date_epoch",),
                    "the PC-FX portable make-variable contract forbids "
                    "source_date_epoch",
                ),
            ),
            forbidden_compile_macros=MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS,
        ),
        SNES9X2005_PLUS_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=SNES9X2005_PLUS_MAKE_VARIABLES,
            contract_name="Snes9x 2005 Plus",
            expected_build_keys=NATIVE_GIT_MAKE_BUILD_KEYS,
            spec_validator="native_git_version_spec_is_well_formed",
            spec_validator_args=("snes9x2005_plus",),
            restriction_message=(
                "the Snes9x 2005 Plus make-variable contract is restricted to "
                "the exact reviewed source, native version, and recipe"
            ),
            forbid_rules=(
                (
                    ("source_date_epoch",),
                    "the Snes9x 2005 Plus make-variable contract forbids "
                    "source_date_epoch",
                ),
            ),
        ),
        PARALLEL_N64_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=PARALLEL_N64_MAKE_VARIABLES,
            contract_name="Parallel N64 aarch64 GLES",
            # source_date_epoch is REQUIRED here, not forbidden: the original
            # "no date-embedding source" assumption was disproven by the v2
            # re-promote wave -- Glide64mk2 embeds __DATE__, which same-day
            # dual builds can never catch and any cross-day rebuild trips.
            expected_build_keys=GL_DYNAREC_BUILD_KEYS | {"source_date_epoch"},
            spec_validator="parallel_n64_spec_is_well_formed",
            restriction_message=(
                "the Parallel N64 make-variable contract is restricted to the "
                "exact reviewed source, recipe, and arm64-only target"
            ),
            forbid_rules=(
                (
                    ("git_version",),
                    "the Parallel N64 make-variable contract forbids "
                    "git_version",
                ),
            ),
            requires_epoch=True,
            golden_epoch=True,
        ),
        MUPEN64PLUS_NEXT_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=MUPEN64PLUS_NEXT_MAKE_VARIABLES,
            contract_name="Mupen64Plus-Next aarch64 GLES",
            # Its tree declares NO submodules yet carries a stray gnulib
            # gitlink with no URL, so `submodule update --init` fails either
            # way. HAVE_PARALLEL_RSP defaults to 0, so none of those sources
            # are compiled anyway.
            expected_build_keys=GL_DYNAREC_BUILD_KEYS | {"submodules"},
            spec_validator="mupen64plus_next_spec_is_well_formed",
            restriction_message=(
                "the Mupen64Plus-Next make-variable contract is restricted to "
                "the exact reviewed source, recipe, and arm64-only target"
            ),
            forbid_rules=(
                (
                    ("git_version", "source_date_epoch"),
                    "the Mupen64Plus-Next make-variable contract forbids "
                    "git_version and source_date_epoch",
                ),
            ),
            golden_epoch=False,
        ),
    }


def make_variable_profile(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    keys = list(value)
    if any(not isinstance(name, str) for name in keys):
        return None
    if keys != sorted(keys):
        return None
    # Values are the exact integer 0/1 for every switch-shaped variable. A
    # reviewed profile may also carry a short identifier-shaped string
    # (parallel_n64 selects its dynarec with WITH_DYNAREC=aarch64); the profile
    # equality below is what actually admits it, so no free-form string ever
    # reaches the make command line.
    if any(
        not (
            (type(item) is int and item in {0, 1})
            or (
                type(item) is str
                and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", item)
                is not None
            )
        )
        for item in value.values()
    ):
        return None
    for profile_id, facts in _make_variable_profile_facts().items():
        if value == facts.variables:
            return profile_id
    return None


def make_variable_mapping_is_well_formed(value: object) -> bool:
    return make_variable_profile(value) is not None


def make_variable_contract_name(value: object) -> str:
    profile = make_variable_profile(value)
    facts = _make_variable_profile_facts().get(profile or "")
    return facts.contract_name if facts is not None else "unsupported"


def validated_make_variables(
    spec: dict,
    *,
    resolvers: BuildContractResolvers,
) -> dict[str, int]:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    raw_make_controls = sorted(
        str(key)
        for key in build
        if isinstance(key, str)
        and key.upper()
        in {"GNUMAKEFLAGS", "MAKEFILES", "MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS"}
    )
    if raw_make_controls:
        raise PipelineError(
            "build raw GNU Make control variables are forbidden: "
            + ", ".join(raw_make_controls)
            + "; use typed build.make_variables"
        )
    if "make_variables" not in build:
        return {}
    if build.get("driver") != "libretro-super":
        raise PipelineError(
            "build.make_variables requires driver libretro-super"
        )
    if "compile_definitions" in build:
        raise PipelineError(
            "build.make_variables cannot be combined with compile_definitions"
        )
    raw = build["make_variables"]
    if not isinstance(raw, dict):
        raise PipelineError("build.make_variables must be an object")
    if any(not isinstance(name, str) for name in raw):
        raise PipelineError("build.make_variables names must be strings")
    reserved = sorted(set(raw).intersection(RESERVED_MAKE_VARIABLE_NAMES))
    if reserved:
        raise PipelineError(
            "build.make_variables contains reserved names: " + ", ".join(reserved)
        )
    keys = list(raw)
    if keys != sorted(keys):
        raise PipelineError("build.make_variables keys must be sorted")
    for name, value in raw.items():
        if type(value) is int and value in {0, 1}:
            continue
        if (
            type(value) is str
            and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value) is not None
        ):
            continue
        raise PipelineError(
            f"build.make_variables.{name} must be the exact integer 0 or 1, or "
            "a reviewed identifier-shaped string"
        )
    profile = make_variable_profile(raw)
    vecx_identity_proof = resolvers.spec_validators[
        "vecx_software_identity_is_well_formed"
    ]
    looks_like_vecx = vecx_identity_proof(spec) or "HAS_GPU" in raw
    if profile is None and looks_like_vecx:
        missing = sorted(set(VECX_SOFTWARE_MAKE_VARIABLES) - set(raw))
        extra = sorted(set(raw) - set(VECX_SOFTWARE_MAKE_VARIABLES))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        if not details:
            details.append("HAS_GPU must be the exact integer 0")
        raise PipelineError(
            "build.make_variables must match the exact VecX software contract: "
            + "; ".join(details)
        )
    looks_like_snes9x2005_plus = (
        build.get("source_key") == "snes9x2005_plus"
        or "USE_BLARGG_APU" in raw
    )
    if profile is None and looks_like_snes9x2005_plus:
        missing = sorted(set(SNES9X2005_PLUS_MAKE_VARIABLES) - set(raw))
        extra = sorted(set(raw) - set(SNES9X2005_PLUS_MAKE_VARIABLES))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        if not details:
            details.append("USE_BLARGG_APU must be the exact integer 1")
        raise PipelineError(
            "build.make_variables must match the exact Snes9x 2005 Plus "
            "contract: " + "; ".join(details)
        )
    if profile is None:
        expected_names = set(PORTABLE_FFMPEG_MAKE_VARIABLES)
        missing = sorted(expected_names - set(raw))
        extra = sorted(set(raw) - expected_names)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        if not details:
            mismatched = sorted(
                name
                for name, value in raw.items()
                if value != PORTABLE_FFMPEG_MAKE_VARIABLES[name]
            )
            details.append("wrong value for " + ", ".join(mismatched))
        raise PipelineError(
            "build.make_variables must contain exactly the portable FFmpeg keys: "
            + "; ".join(details)
        )
    facts = _make_variable_profile_facts()[profile]
    if facts.expected_build_keys is not None:
        if facts.spec_validator is not None and not resolvers.spec_validators[
            facts.spec_validator
        ](spec, *facts.spec_validator_args):
            raise PipelineError(facts.restriction_message)
        for forbidden_keys, message in facts.forbid_rules:
            if any(key in build for key in forbidden_keys):
                raise PipelineError(message)
        if facts.requires_epoch and not source_date_epoch_is_well_formed(
            build.get("source_date_epoch")
        ):
            raise PipelineError(
                "build.source_date_epoch is required with build.make_variables"
            )
        expected_build_keys = facts.expected_build_keys
        if facts.expected_overlays is not None:
            # A profile may declare exact reviewed overlays; the build must
            # then carry precisely that mapping.
            expected_build_keys = frozenset(expected_build_keys) | {"overlays"}
            if build.get("overlays") != facts.expected_overlays:
                raise PipelineError(
                    f"build.overlays must equal the exact reviewed "
                    f"{facts.contract_name} overlay contract"
                )
        contract_name = facts.contract_name
    else:
        if not vecx_identity_proof(spec):
            source = spec.get("source", {})
            expected_source = {
                "url": VECX_SOFTWARE_SPEC_IDENTITY["source_url"],
                "requested_ref": VECX_SOFTWARE_SPEC_IDENTITY[
                    "source_requested_ref"
                ],
                "commit": VECX_SOFTWARE_SPEC_IDENTITY["source_commit"],
                "tree": VECX_SOFTWARE_SPEC_IDENTITY["source_tree"],
            }
            if source != expected_source:
                raise PipelineError(
                    "the VecX software source identity must match the exact "
                    "reviewed commit and tree"
                )
            validation = spec.get("validation", {})
            if not isinstance(validation, dict) or validation.get(
                "forbidden_needed_prefixes"
            ) != VECX_SOFTWARE_SPEC_IDENTITY["forbidden_needed_prefixes"]:
                raise PipelineError(
                    "the VecX software dependency policy must forbid the exact "
                    "GL/EGL/GLES/OpenGL library prefixes"
                )
            raise PipelineError(
                "the VecX software make-variable contract is restricted to the "
                "exact VecX libretro-super recipe"
            )
        if "source_date_epoch" in build:
            raise PipelineError(
                "the VecX software make-variable contract forbids source_date_epoch"
            )
        expected_build_keys = VECX_SOFTWARE_BUILD_KEYS
        contract_name = "VecX software"
    unexpected_build_keys = sorted(set(build) - expected_build_keys)
    missing_build_keys = sorted(expected_build_keys - set(build))
    if unexpected_build_keys or missing_build_keys:
        details = []
        if missing_build_keys:
            details.append("missing " + ", ".join(missing_build_keys))
        if unexpected_build_keys:
            details.append("extra " + ", ".join(unexpected_build_keys))
        raise PipelineError(
            f"build with make_variables must contain exactly the {contract_name} "
            "build keys: " + "; ".join(details)
        )
    if profile == VECX_SOFTWARE_MAKE_PROFILE:
        source_commit = spec.get("source", {}).get("commit")
        raw_git_version = build.get("git_version")
        if not isinstance(raw_git_version, dict) or raw_git_version.get(
            "derivation"
        ) != NATIVE_GIT_VERSION_DERIVATION:
            raise PipelineError(
                "the VecX software make-variable contract requires the exact "
                "native-space-short7-v1 git_version contract"
            )
        expected_native_value = f" {source_commit[:7]}"
        if raw_git_version.get("value") != expected_native_value:
            raise PipelineError(
                "build.git_version.value must equal a space plus the first seven "
                f"source commit characters: {expected_native_value!r}"
            )
        if not git_version_contract_is_well_formed(
            raw_git_version,
            source_commit,
            resolvers=resolvers,
        ):
            raise PipelineError(
                "the VecX software make-variable contract requires the exact "
                "native-space-short7-v1 git_version contract"
            )
    return {name: raw[name] for name in sorted(raw)}


def git_version_contract_is_well_formed(
    value: object,
    source_commit: object,
    *,
    resolvers: BuildContractResolvers,
) -> bool:
    if not isinstance(source_commit, str) or not SHA1_RE.fullmatch(source_commit):
        return False
    if (
        isinstance(value, dict)
        and value.get("derivation") == FBNEO_GIT_VERSION_DERIVATION
    ):
        return bool(
            source_commit == FBNEO_SOURCE_COMMIT
            and resolvers.git_version_validators[
                "fbneo_git_version_contract_is_well_formed"
            ](value)
        )
    required_keys = {"derivation", "value"}
    allowed_keys = required_keys.union({"compiler_scope"})
    if not (
        isinstance(value, dict)
        and required_keys.issubset(value)
        and set(value).issubset(allowed_keys)
    ):
        return False
    derivation = value.get("derivation")
    raw_value = value.get("value")
    if derivation == GIT_VERSION_DERIVATION:
        return bool(
            isinstance(raw_value, str)
            and GIT_VERSION_RE.fullmatch(raw_value)
            and raw_value == f"-{source_commit[:7]}"
            and (
                "compiler_scope" not in value
                or value.get("compiler_scope") == GIT_VERSION_CXX_SCOPE
            )
        )
    if derivation == NATIVE_GIT_VERSION_DERIVATION:
        return bool(
            isinstance(raw_value, str)
            and NATIVE_GIT_VERSION_RE.fullmatch(raw_value)
            and raw_value == f" {source_commit[:7]}"
            and (
                "compiler_scope" not in value
                or value.get("compiler_scope") in GIT_VERSION_COMPILER_SCOPES
            )
        )
    if derivation == NATIVE_GIT_VERSION_SHORT8_DERIVATION:
        return bool(
            source_commit == MAME2003_PLUS_SOURCE_COMMIT
            and resolvers.git_version_validators[
                "mame2003_plus_git_version_contract_is_well_formed"
            ](value)
        )
    if derivation == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
        identity = NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES[MGBA_CORE_ID]
        return bool(
            set(value) == allowed_keys
            and source_commit == identity["source_commit"]
            and isinstance(raw_value, str)
            and NATIVE_GIT_VERSION_SHORT9_RE.fullmatch(raw_value)
            and raw_value == MGBA_NATIVE_GIT_VERSION
            and value.get("compiler_scope") == identity["compiler_scope"]
        )
    if derivation == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
        return bool(
            set(value) == required_keys
            and isinstance(raw_value, str)
            and NATIVE_GIT_VERSION_SHORT10_RE.fullmatch(raw_value)
            and raw_value == f" {source_commit[:10]}"
        )
    if derivation == NATIVE_GIT_DESCRIBE_DERIVATION:
        return bool(
            set(value) == required_keys
            and isinstance(raw_value, str)
            and raw_value
            == NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT.get(source_commit)
        )
    return False


def validated_git_version(
    spec: dict,
    *,
    resolvers: BuildContractResolvers,
) -> dict | None:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    if "git_version" not in build:
        return None
    if build.get("driver") != "libretro-super":
        raise PipelineError("build.git_version requires driver libretro-super")
    if (
        "compile_definitions" in build
        and not resolvers.spec_validators["fbneo_spec_is_well_formed"](spec)
    ):
        raise PipelineError(
            "build.git_version cannot be combined with compile_definitions "
            "outside the exact reviewed FBNeo contract"
        )
    raw = build["git_version"]
    if not isinstance(raw, dict):
        raise PipelineError("build.git_version must be an object")
    derivation = raw.get("derivation")
    if derivation == FBNEO_GIT_VERSION_DERIVATION:
        if not resolvers.spec_validators["fbneo_spec_is_well_formed"](spec):
            raise PipelineError(
                "fbneo-native-short9-date-v1 is restricted to the exact "
                "reviewed FBNeo source, epoch, recipe, metadata, target, "
                "compiler scope, Git date, and command-scoped Make contract"
            )
        return copy.deepcopy(FBNEO_GIT_VERSION)
    required_keys = {"derivation", "value"}
    allowed_keys = required_keys.union({"compiler_scope"})
    if not required_keys.issubset(raw) or not set(raw).issubset(allowed_keys):
        raise PipelineError(
            "build.git_version must contain exactly derivation and value, "
            "with optional compiler_scope"
        )
    if derivation not in {
        GIT_VERSION_DERIVATION,
        NATIVE_GIT_VERSION_DERIVATION,
        NATIVE_GIT_VERSION_SHORT8_DERIVATION,
        NATIVE_GIT_VERSION_SHORT9_DERIVATION,
        NATIVE_GIT_VERSION_SHORT10_DERIVATION,
        NATIVE_GIT_DESCRIBE_DERIVATION,
    }:
        raise PipelineError(
            "build.git_version.derivation must be hyphen-short7-v1, "
            "native-space-short7-v1, native-space-short8-v1, "
            "native-space-short9-v1, "
            "native-space-short10-v1, or native-git-describe-v1"
        )
    source_commit = spec.get("source", {}).get("commit")
    if not isinstance(source_commit, str) or not SHA1_RE.fullmatch(source_commit):
        raise PipelineError(
            "build.git_version requires a full lowercase source commit SHA"
        )
    is_native = derivation == NATIVE_GIT_VERSION_DERIVATION
    is_native_short8 = derivation == NATIVE_GIT_VERSION_SHORT8_DERIVATION
    is_native_short9 = derivation == NATIVE_GIT_VERSION_SHORT9_DERIVATION
    is_native_short10 = derivation == NATIVE_GIT_VERSION_SHORT10_DERIVATION
    is_native_describe = derivation == NATIVE_GIT_DESCRIBE_DERIVATION
    if is_native_describe:
        expected_value = NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT.get(source_commit)
        if expected_value is None:
            raise PipelineError(
                "native-git-describe-v1 is restricted to an exact reviewed "
                "source commit and describe value"
            )
    elif is_native_short8:
        expected_value = MAME2003_PLUS_NATIVE_GIT_VERSION
    elif is_native_short9:
        if build.get("source_key") != MGBA_CORE_ID:
            raise PipelineError(
                "native-space-short9-v1 is restricted to the exact reviewed "
                "mGBA source and recipe"
            )
        expected_value = MGBA_NATIVE_GIT_VERSION
    elif is_native_short10:
        expected_value = f" {source_commit[:10]}"
    else:
        expected_value = (
            f" {source_commit[:7]}" if is_native else f"-{source_commit[:7]}"
        )
    value = raw.get("value")
    if is_native_describe:
        value_is_valid = value == expected_value
    elif is_native_short8:
        value_is_valid = bool(
            source_commit == MAME2003_PLUS_SOURCE_COMMIT
            and resolvers.git_version_validators[
                "mame2003_plus_git_version_contract_is_well_formed"
            ](raw)
        )
    elif is_native_short9:
        value_is_valid = bool(
            isinstance(value, str)
            and NATIVE_GIT_VERSION_SHORT9_RE.fullmatch(value)
            and value == expected_value
        )
    elif is_native_short10:
        value_is_valid = bool(
            isinstance(value, str)
            and NATIVE_GIT_VERSION_SHORT10_RE.fullmatch(value)
            and value == expected_value
        )
    else:
        value_is_valid = bool(
            isinstance(value, str)
            and (NATIVE_GIT_VERSION_RE if is_native else GIT_VERSION_RE).fullmatch(
                value
            )
            and value == expected_value
        )
    if not value_is_valid:
        if is_native_describe:
            raise PipelineError(
                "build.git_version.value must equal the exact reviewed native "
                f"git describe value: {expected_value!r}"
            )
        prefix = (
            "a space"
            if (
                is_native
                or is_native_short8
                or is_native_short9
                or is_native_short10
            )
            else "'-'"
        )
        length = (
            "eight"
            if is_native_short8
            else "nine"
            if is_native_short9
            else "ten"
            if is_native_short10
            else "seven"
        )
        raise PipelineError(
            f"build.git_version.value must equal {prefix} plus the first {length} "
            f"source commit characters: {expected_value!r}"
        )
    has_compiler_scope = "compiler_scope" in raw
    compiler_scope = raw.get("compiler_scope")
    allowed_compiler_scopes = (
        GIT_VERSION_COMPILER_SCOPES
        if is_native or is_native_short8 or is_native_short9
        else frozenset({GIT_VERSION_CXX_SCOPE})
    )
    if has_compiler_scope and compiler_scope not in allowed_compiler_scopes:
        allowed_scope_text = (
            "c or cxx"
            if is_native or is_native_short8 or is_native_short9
            else "cxx"
        )
        raise PipelineError(
            "build.git_version.compiler_scope must be "
            f"{allowed_scope_text} when present"
        )
    if compiler_scope == GIT_VERSION_C_SCOPE and not (
        (is_native or is_native_short8 or is_native_short9)
        and build.get("source_key") in NATIVE_GIT_VERSION_C_SCOPE_CORE_IDS
    ):
        raise PipelineError(
            "build.git_version.compiler_scope c is restricted to the exact "
            "reviewed C-scoped native version contracts"
        )
    if (is_native_short10 or is_native_describe) and has_compiler_scope:
        contract_name = (
            NATIVE_GIT_VERSION_SHORT10_DERIVATION
            if is_native_short10
            else NATIVE_GIT_DESCRIBE_DERIVATION
        )
        raise PipelineError(
            f"{contract_name} requires its compile token on all C and C++ "
            "target compiler commands"
        )
    if "make_variables" in build:
        is_vecx_combined = (
            is_native
            and make_variable_profile(build.get("make_variables"))
            == VECX_SOFTWARE_MAKE_PROFILE
            and resolvers.spec_validators[
                "vecx_software_identity_is_well_formed"
            ](spec)
        )
        is_pcfx_combined = (
            is_native
            and make_variable_profile(build.get("make_variables"))
            == PCFX_PORTABLE_MAKE_PROFILE
            and resolvers.spec_validators[
                "mednafen_pcfx_spec_is_well_formed"
            ](spec)
        )
        is_snes9x2005_plus_combined = (
            is_native
            and make_variable_profile(build.get("make_variables"))
            == SNES9X2005_PLUS_MAKE_PROFILE
            and resolvers.spec_validators[
                "native_git_version_spec_is_well_formed"
            ](
                spec, "snes9x2005_plus"
            )
        )
        if not (
            is_vecx_combined
            or is_pcfx_combined
            or is_snes9x2005_plus_combined
        ):
            raise PipelineError(
                "build.git_version cannot be combined with make_variables "
                "outside an exact reviewed combined native contract"
            )
    elif is_native and not resolvers.spec_validators[
        "native_git_version_spec_is_well_formed"
    ](spec, build.get("source_key")):
        raise PipelineError(
            "native-space-short7-v1 is restricted to an exact reviewed "
            "combined make-variable contract or standalone native version "
            "contract"
        )
    elif is_native_short8 and not resolvers.spec_validators[
        "mame2003_plus_spec_is_well_formed"
    ](spec):
        raise PipelineError(
            "native-space-short8-v1 is restricted to the exact reviewed "
            "MAME2003+ source, epoch, recipe, metadata, target, compiler "
            "scope, and command-scoped Make contract"
        )
    elif is_native_short9 and not resolvers.spec_validators[
        "native_git_version_short9_spec_is_well_formed"
    ](spec, build.get("source_key")):
        raise PipelineError(
            "native-space-short9-v1 is restricted to the exact reviewed mGBA "
            "source, recipe, metadata, target, compiler scope, and Git "
            "abbreviation contract"
        )
    elif is_native_short10 and not resolvers.spec_validators[
        "native_git_version_short10_spec_is_well_formed"
    ](spec, build.get("source_key")):
        raise PipelineError(
            "native-space-short10-v1 is restricted to the exact reviewed VICE "
            "source, epoch, recipe, metadata, target, and Git abbreviation "
            "contract"
        )
    elif is_native_describe and not resolvers.spec_validators[
        "native_git_describe_spec_is_well_formed"
    ](spec, build.get("source_key")):
        raise PipelineError(
            "native-git-describe-v1 is restricted to an exact reviewed source, "
            "recipe, metadata, target, and compiler-macro contract"
        )
    if is_native_short8:
        return copy.deepcopy(MAME2003_PLUS_GIT_VERSION)
    contract = {"derivation": derivation, "value": expected_value}
    if has_compiler_scope:
        contract["compiler_scope"] = compiler_scope
    return contract


def make_output_sync_prefix(variables: object) -> str:
    """Make flags that force deterministic parallel output for a profile.

    The portable FFmpeg build fans out ~1268 concurrent compiles whose stderr
    (compiler diagnostics and the long -DCONFIG_* command echoes) otherwise
    interleaves at non-reproducible line boundaries, defeating the reproduction
    log comparison even though the produced binary is byte-identical.
    ``--output-sync=recurse`` emits each recipe's output as one atomic block, so
    the log line multiset is reproducible (block order may still vary). No other
    make-variable profile requests it, keeping their frozen recipes unchanged.
    """

    if make_variable_profile(variables) == PORTABLE_FFMPEG_MAKE_PROFILE:
        return "--output-sync=recurse "
    return ""


def canonical_makeflags(
    spec: dict,
    *,
    resolvers: BuildContractResolvers,
) -> str:
    variables = validated_make_variables(spec, resolvers=resolvers)
    return make_output_sync_prefix(variables) + " ".join(
        f"{name}={value}" for name, value in variables.items()
    )


def validated_source_date_epoch(spec: dict) -> int | None:
    build = spec.get("build", {})
    if "source_date_epoch" not in build:
        return None
    value = build["source_date_epoch"]
    if not source_date_epoch_is_well_formed(value):
        raise PipelineError(
            "build.source_date_epoch must be an exact integer between 1 and "
            f"{MAX_SOURCE_DATE_EPOCH}"
        )
    return value


def validated_recipe_profile(
    spec: dict,
    *,
    resolvers: BuildContractResolvers,
) -> dict | None:
    """Return the one reviewed non-generic libretro-super recipe profile."""

    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    raw = build.get("recipe_profile")
    looks_like_picodrive = build.get("source_key") == PICODRIVE_CORE_ID
    if raw is None:
        if looks_like_picodrive:
            raise PipelineError(
                "build.recipe_profile is required by the Picodrive source contract"
            )
        return None
    if build.get("driver") != "libretro-super":
        raise PipelineError(
            "build.recipe_profile requires driver libretro-super"
        )
    forbidden_combinations = sorted(
        {
            "cmake",
            "generated_source",
            "git_version",
            "make_variables",
            "platforms",
        }.intersection(build)
    )
    if forbidden_combinations:
        raise PipelineError(
            "build.recipe_profile cannot be combined with: "
            + ", ".join(forbidden_combinations)
        )
    if (
        not resolvers.spec_validators[
            "picodrive_recipe_profile_is_well_formed"
        ](raw)
        or not resolvers.spec_validators["picodrive_identity_is_well_formed"](
            spec
        )
    ):
        raise PipelineError(
            "build.recipe_profile is restricted to the exact reviewed "
            "Picodrive source-root recipe"
        )
    return copy.deepcopy(raw)


def source_date_epoch_is_well_formed(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_SOURCE_DATE_EPOCH


def build_source_date_epoch_matches(build: object, expected: int | None) -> bool:
    if not isinstance(build, dict):
        return False
    if expected is None:
        return "source_date_epoch" not in build
    return (
        "source_date_epoch" in build
        and source_date_epoch_is_well_formed(build["source_date_epoch"])
        and build["source_date_epoch"] == expected
    )


def exact_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PipelineError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative path")
    return value


def validate_build_overlays(
    overlays: object,
    core_id: str | None,
    source_dir: str,
    targets: object,
    *,
    io: BuildContractIO,
) -> dict:
    """Validate driver-agnostic git-apply patch overlays declared on a build.

    Overlays are a per-target map of single-file git-apply-v1 patches under
    patches/<core>/, each pinned by patch/preimage/postimage sha256. Any build
    type may carry overlays; the driver's build script applies them after
    checkout via overlay_apply_shell(). Returns a deep copy of the validated
    overlays (an empty dict when none are declared).
    """

    if not isinstance(overlays, dict):
        raise PipelineError("build.overlays must be an object")
    unexpected_overlay_targets = sorted(set(overlays) - set(targets))
    if unexpected_overlay_targets:
        raise PipelineError(
            "build.overlays contains a non-target architecture: "
            + ", ".join(unexpected_overlay_targets)
        )
    overlay_keys = {
        "kind",
        "patch_path",
        "patch_sha256",
        "source_path",
        "preimage_sha256",
        "postimage_sha256",
    }
    # `submodule_path` is optional and reviewed: it names the checked-out
    # submodule that owns source_path, because git apply and git diff at the
    # superproject cannot see or mutate files behind a gitlink (flycast's
    # vendored libchdr/lzma is the first consumer).
    optional_overlay_keys = {"submodule_path"}
    for arch, target_overlays in overlays.items():
        if not isinstance(target_overlays, list) or not target_overlays:
            raise PipelineError(f"build.overlays.{arch} must be a non-empty array")
        raw_source_paths = [
            overlay.get("source_path") if isinstance(overlay, dict) else None
            for overlay in target_overlays
        ]
        if any(not isinstance(path, str) for path in raw_source_paths) or (
            raw_source_paths != sorted(raw_source_paths)
        ):
            raise PipelineError(
                f"build.overlays.{arch} must be sorted by source_path"
            )
        seen_source_paths: set[str] = set()
        seen_patch_paths: set[str] = set()
        for index, overlay in enumerate(target_overlays):
            label = f"build.overlays.{arch}[{index}]"
            if not isinstance(overlay, dict) or not (
                overlay_keys <= set(overlay)
                and set(overlay) <= overlay_keys | optional_overlay_keys
            ):
                raise PipelineError(f"{label} must contain the exact overlay fields")
            if "submodule_path" in overlay:
                overlay_submodule = exact_relative_path(
                    overlay["submodule_path"], f"{label}.submodule_path"
                )
                if not str(overlay.get("source_path", "")).startswith(
                    overlay_submodule + "/"
                ):
                    raise PipelineError(
                        f"{label}.submodule_path must be a prefix of source_path"
                    )
            if overlay.get("kind") != "git-apply-v1":
                raise PipelineError(f"{label}.kind must be git-apply-v1")
            patch_path = exact_relative_path(
                overlay.get("patch_path"), f"{label}.patch_path"
            )
            expected_patch_prefix = f"patches/{core_id or source_dir}/"
            if not patch_path.startswith(expected_patch_prefix) or not patch_path.endswith(
                ".patch"
            ):
                raise PipelineError(
                    f"{label}.patch_path must name a core-scoped tracked patch"
                )
            source_path = exact_relative_path(
                overlay.get("source_path"), f"{label}.source_path"
            )
            if source_path in seen_source_paths or patch_path in seen_patch_paths:
                raise PipelineError(f"{label} repeats an overlay path")
            seen_source_paths.add(source_path)
            seen_patch_paths.add(patch_path)
            for digest_key in (
                "patch_sha256",
                "preimage_sha256",
                "postimage_sha256",
            ):
                if not isinstance(overlay.get(digest_key), str) or not SHA256_RE.fullmatch(
                    overlay[digest_key]
                ):
                    raise PipelineError(f"{label}.{digest_key} is invalid")
            if overlay["preimage_sha256"] == overlay["postimage_sha256"]:
                raise PipelineError(f"{label} preimage and postimage must differ")
            patch_file = io.reference_path(
                {"path": patch_path},
                io.repository_root / "patches",
                f"{label}.patch",
            )
            try:
                patch_text = io.verified_text(
                    patch_file,
                    overlay["patch_sha256"],
                    f"{label}.patch",
                )
            except PipelineError as exc:
                raise PipelineError(f"{label}.patch_sha256 does not match") from exc
            expected_header = f"diff --git a/{source_path} b/{source_path}\n"
            if (
                not patch_text.startswith(expected_header)
                or patch_text.count("diff --git ") != 1
                or patch_text.count(f"--- a/{source_path}\n") != 1
                or patch_text.count(f"+++ b/{source_path}\n") != 1
            ):
                raise PipelineError(
                    f"{label}.patch must be a single-file git-apply-v1 patch"
                )
            numstat = io.run_command(
                [
                    "git",
                    "apply",
                    "--numstat",
                    "-z",
                    "--whitespace=error-all",
                    str(patch_file),
                ],
                cwd=io.repository_root,
            ).stdout
            numstat_entries = [entry for entry in numstat.split("\0") if entry]
            if len(numstat_entries) != 1:
                raise PipelineError(f"{label}.patch changes more than one path")
            fields = numstat_entries[0].split("\t", 2)
            if (
                len(fields) != 3
                or fields[0] == "-"
                or fields[1] == "-"
                or fields[2] != source_path
            ):
                raise PipelineError(
                    f"{label}.patch is binary or changes an unexpected path"
                )
    return copy.deepcopy(overlays)


def validated_direct_cmake(
    spec: dict,
    core_id: str | None = None,
    *,
    io: BuildContractIO,
) -> dict | None:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    if build.get("driver") != "direct-cmake":
        if "cmake" in build:
            raise PipelineError(
                "build direct-CMake fields require driver direct-cmake: cmake"
            )
        return None

    allowed_build_keys = {
        "driver",
        "source_dir",
        "output_path",
        "artifact_name",
        "source_date_epoch",
        "cmake",
        "overlays",
    }
    unexpected_build_keys = sorted(set(build) - allowed_build_keys)
    if unexpected_build_keys:
        raise PipelineError(
            "build direct-cmake contains unsupported fields: "
            + ", ".join(unexpected_build_keys)
        )
    source_dir = build.get("source_dir")
    if not isinstance(source_dir, str) or not LOCAL_ID_RE.fullmatch(source_dir):
        raise PipelineError("build.source_dir is invalid for direct-cmake")
    if core_id is not None and source_dir != core_id:
        raise PipelineError("build.source_dir must match its direct-cmake core ID")
    output_path = exact_relative_path(
        build.get("output_path"), "build.output_path"
    )
    artifact_name = build.get("artifact_name")
    # The artifact may sit in a contained build subdirectory (e.g. CMake that
    # emits into `bin/<target>.so`, like tic80); require only that the basename
    # is the artifact name (exact_relative_path already forbids `..`/absolute).
    # A rebranded fork may rename -- but only to its OWN canonical core name
    # (KMFDManic/swanstation builds `swanstation_libretro.so` and ships as
    # `km_duckswanstation_xtreme_amped_libretro.so`). Renaming to anything else
    # stays rejected, so an artifact can never impersonate another core.
    # `source_dir` is the identity anchor here: catalog validation enforces
    # source_dir == core_id for direct-cmake, and unlike core_id it is present
    # in the spec at every call site (the build path validates without the
    # catalog key in hand).
    if Path(output_path).name != artifact_name and (
        artifact_name != f"{build.get('source_dir')}_libretro.so"
    ):
        raise PipelineError(
            "build.output_path basename must equal build.artifact_name for direct-cmake"
        )
    if validated_source_date_epoch(spec) is None:
        raise PipelineError("build.source_date_epoch is required for direct-cmake")

    cmake = build.get("cmake")
    required_cmake_keys = {"generator", "build_type", "target", "systems"}
    # Optional reviewed fields: `source_subdir` is an in-tree CMakeLists directory
    # relative to the clone root (tic80's `core`, squirreljme's `nanocoat`);
    # `defines` are the exact `-D<name>=<value>` configure flags that select the
    # libretro-only build and disable the desktop/SDL/GL frontend (tic80 and
    # ardens both pull SDL2/X11 without them). When absent, CMake configures at
    # the clone root with no extra defines, as before.
    if (
        not isinstance(cmake, dict)
        or not required_cmake_keys <= set(cmake)
        or not set(cmake) <= required_cmake_keys | {"source_subdir", "defines"}
    ):
        raise PipelineError("build.cmake must contain the exact direct-CMake fields")
    cmake_source_subdir = None
    if "source_subdir" in cmake:
        cmake_source_subdir = exact_relative_path(
            cmake["source_subdir"], "build.cmake.source_subdir"
        )
    cmake_defines = None
    if "defines" in cmake:
        defines = cmake["defines"]
        if not isinstance(defines, dict) or not defines:
            raise PipelineError("build.cmake.defines must be a non-empty object")
        for name, value in defines.items():
            if (
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                or not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z0-9_./+=-]+", value) is None
            ):
                raise PipelineError("build.cmake.defines has an invalid entry")
        cmake_defines = dict(defines)
    if cmake.get("generator") != "Unix Makefiles":
        raise PipelineError("build.cmake.generator must be Unix Makefiles")
    if cmake.get("build_type") != "Release":
        raise PipelineError("build.cmake.build_type must be Release")
    target = cmake.get("target")
    # The target is validated against what the build PRODUCES (the output_path
    # basename), which equals the artifact name everywhere except a rebranded
    # fork, where the rename above already restricts the artifact to the core's
    # own canonical name.
    if (
        not isinstance(target, str)
        or not re.fullmatch(r"[A-Za-z0-9_+-]+", target)
        or Path(output_path).name != f"{target}.so"
    ):
        raise PipelineError(
            "build.cmake.target must be a safe target matching the artifact name"
        )
    systems = cmake.get("systems")
    targets = spec.get("targets")
    if not isinstance(targets, list) or not isinstance(systems, dict):
        raise PipelineError("build.cmake.systems requires valid core targets")
    if set(systems) != set(targets):
        raise PipelineError("build.cmake.systems must exactly cover core targets")
    expected_processors = {"arm64": "aarch64", "armhf": "arm"}
    for arch, system in systems.items():
        if arch not in expected_processors:
            raise PipelineError(f"build.cmake.systems architecture is invalid: {arch}")
        # Optional reviewed per-architecture `defines` (flycast selects GLES3 on
        # arm64 and GLES2 on armhf); they merge over the common defines in the
        # per-target projection. Everything else in the system block stays the
        # exact target identity.
        if not isinstance(system, dict) or not (
            set(system) == {"name", "processor"}
            or set(system) == {"name", "processor", "defines"}
        ):
            raise PipelineError(
                f"build.cmake.systems.{arch} must contain name and processor"
            )
        if {
            "name": system.get("name"),
            "processor": system.get("processor"),
        } != {
            "name": "Linux",
            "processor": expected_processors[arch],
        }:
            raise PipelineError(
                f"build.cmake.systems.{arch} does not identify the target system"
            )
        if "defines" in system:
            arch_defines = system["defines"]
            if not isinstance(arch_defines, dict) or not arch_defines:
                raise PipelineError(
                    f"build.cmake.systems.{arch}.defines must be a non-empty object"
                )
            for name, value in arch_defines.items():
                if (
                    not isinstance(name, str)
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                    or not isinstance(value, str)
                    or re.fullmatch(r"[A-Za-z0-9_./+=-]+", value) is None
                ):
                    raise PipelineError(
                        f"build.cmake.systems.{arch}.defines has an invalid entry"
                    )

    overlays = validate_build_overlays(
        build.get("overlays", {}),
        core_id,
        source_dir,
        targets,
        io=io,
    )
    result = {
        "generator": cmake["generator"],
        "build_type": cmake["build_type"],
        "target": cmake["target"],
        "systems": copy.deepcopy(systems),
        "overlays": copy.deepcopy(overlays),
    }
    # Only surface the optional fields when set, so cores without them keep a
    # byte-identical contract (and stored golden) to before they existed.
    if cmake_source_subdir is not None:
        result["source_subdir"] = cmake_source_subdir
    if cmake_defines is not None:
        result["defines"] = cmake_defines
    return result


def direct_cmake_contract_for_target(
    spec: dict,
    arch: str,
    *,
    io: BuildContractIO,
) -> dict | None:
    contract = validated_direct_cmake(spec, io=io)
    if contract is None:
        return None
    if arch not in spec.get("targets", []):
        raise PipelineError(f"direct-CMake architecture is not enabled: {arch}")
    system = copy.deepcopy(contract["systems"][arch])
    arch_defines = system.pop("defines", None)
    projected_cmake = {
        "generator": contract["generator"],
        "build_type": contract["build_type"],
        "target": contract["target"],
        "system": system,
    }
    if contract.get("source_subdir") is not None:
        projected_cmake["source_subdir"] = contract["source_subdir"]
    merged_defines = dict(contract.get("defines") or {})
    if arch_defines:
        merged_defines.update(arch_defines)
    if merged_defines:
        projected_cmake["defines"] = merged_defines
    return {
        "cmake": projected_cmake,
        "overlays": copy.deepcopy(contract["overlays"].get(arch, [])),
    }


def validated_direct_cargo(spec: dict, core_id: str | None = None) -> dict | None:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    if build.get("driver") != "direct-cargo":
        if "cargo" in build:
            raise PipelineError(
                "build direct-cargo fields require driver direct-cargo: cargo"
            )
        return None

    allowed_build_keys = {
        "driver",
        "source_dir",
        "output_path",
        "artifact_name",
        "source_date_epoch",
        "cargo",
    }
    unexpected_build_keys = sorted(set(build) - allowed_build_keys)
    if unexpected_build_keys:
        raise PipelineError(
            "build direct-cargo contains unsupported fields: "
            + ", ".join(unexpected_build_keys)
        )
    source_dir = build.get("source_dir")
    if not isinstance(source_dir, str) or not LOCAL_ID_RE.fullmatch(source_dir):
        raise PipelineError("build.source_dir is invalid for direct-cargo")
    if core_id is not None and source_dir != core_id:
        raise PipelineError("build.source_dir must match its direct-cargo core ID")
    # Cargo names its cdylib itself; `output_path` is that bare product file
    # name and must equal the artifact -- no rebrand support until a fork
    # needs one, and no subdirectory: the driver derives the full
    # `target/<triple>/release/` location from the reviewed target map.
    output_path = build.get("output_path")
    if (
        not isinstance(output_path, str)
        or "/" in output_path
        or output_path != build.get("artifact_name")
    ):
        raise PipelineError(
            "build.output_path must equal build.artifact_name for direct-cargo"
        )
    if validated_source_date_epoch(spec) is None:
        raise PipelineError("build.source_date_epoch is required for direct-cargo")

    cargo = build.get("cargo")
    if not isinstance(cargo, dict) or set(cargo) != {
        "subdir",
        "profile",
        "lock_sha256",
        "targets",
    }:
        raise PipelineError("build.cargo must contain the exact direct-cargo fields")
    subdir = exact_relative_path(cargo.get("subdir"), "build.cargo.subdir")
    if cargo.get("profile") != "release":
        raise PipelineError("build.cargo.profile must be release")
    lock_sha256 = cargo.get("lock_sha256")
    if not isinstance(lock_sha256, str) or not SHA256_RE.fullmatch(lock_sha256):
        raise PipelineError("build.cargo.lock_sha256 is invalid")
    targets = cargo.get("targets")
    # The triple prefixes are pinned per architecture; an optional dotted
    # suffix is cargo-zigbuild's glibc floor (e.g. `.2.23`).
    expected_triple_prefixes = {
        "arm64": "aarch64-unknown-linux-gnu",
        "armhf": "armv7-unknown-linux-gnueabihf",
    }
    if not isinstance(targets, dict) or set(targets) != set(expected_triple_prefixes):
        raise PipelineError("build.cargo.targets must name exactly arm64 and armhf")
    for target_arch, triple in targets.items():
        prefix = expected_triple_prefixes[target_arch]
        if not isinstance(triple, str) or not re.fullmatch(
            re.escape(prefix) + r"(\.[0-9]+(\.[0-9]+)*)?", triple
        ):
            raise PipelineError(
                f"build.cargo.targets.{target_arch} is not the pinned triple"
            )
    return {
        "subdir": subdir,
        "profile": "release",
        "lock_sha256": lock_sha256,
        "targets": dict(targets),
    }


def direct_cargo_contract_for_target(spec: dict, arch: str) -> dict | None:
    contract = validated_direct_cargo(spec)
    if contract is None:
        return None
    if arch not in spec.get("targets", []):
        raise PipelineError(f"direct-cargo architecture is not enabled: {arch}")
    return {
        "cargo": {
            "subdir": contract["subdir"],
            "profile": contract["profile"],
            "lock_sha256": contract["lock_sha256"],
            "target": contract["targets"][arch],
        }
    }


def recorded_build_contract(build: object) -> dict:
    if not isinstance(build, dict):
        return {}
    keys = (
        "driver",
        "environment",
        "compile_definitions",
        "generated_source",
        "git_version",
        "make_variables",
        "recipe_profile",
        "source_date_epoch",
        "metadata_replacement",
        "cmake",
        "cargo",
        "overlays",
    )
    return {key: copy.deepcopy(build[key]) for key in keys if key in build}


def validated_forbidden_needed_prefixes(spec: dict) -> list[str]:
    validation = spec.get("validation")
    if validation is None:
        return []
    if not isinstance(validation, dict) or set(validation) != {
        "forbidden_needed_prefixes"
    }:
        raise PipelineError(
            "validation must contain only forbidden_needed_prefixes"
        )
    prefixes = validation["forbidden_needed_prefixes"]
    if (
        not isinstance(prefixes, list)
        or not prefixes
        or any(not isinstance(prefix, str) for prefix in prefixes)
        or prefixes != sorted(set(prefixes))
    ):
        raise PipelineError(
            "validation.forbidden_needed_prefixes must be a non-empty sorted unique array"
        )
    for prefix in prefixes:
        if not re.fullmatch(r"lib[A-Za-z0-9_+.-]+", prefix):
            raise PipelineError(
                "validation.forbidden_needed_prefixes contains an unsafe token"
            )
    return list(prefixes)


def forbidden_needed_dependencies(spec: dict, needed: object) -> list[str]:
    prefixes = validated_forbidden_needed_prefixes(spec)
    if not prefixes:
        return []
    if not isinstance(needed, list) or any(
        not isinstance(dependency, str) for dependency in needed
    ):
        raise PipelineError("artifact dynamic dependency list is invalid")
    return sorted(
        dependency
        for dependency in set(needed)
        if any(dependency.startswith(prefix) for prefix in prefixes)
    )


def apply_artifact_dependency_policy(validation: dict, spec: dict) -> dict:
    forbidden = forbidden_needed_dependencies(spec, validation.get("needed", []))
    if forbidden:
        validation.setdefault("errors", []).append(
            "forbidden dynamic dependencies: " + ", ".join(forbidden)
        )
        validation["status"] = "invalid"
    return validation


def make_variable_golden_build_contract_is_well_formed(build: object) -> bool:
    if not isinstance(build, dict):
        return False
    profile = make_variable_profile(build.get("make_variables"))
    facts = _make_variable_profile_facts().get(profile or "")
    # golden_epoch encodes whether the record pins a source_date_epoch (the
    # portable FFmpeg profile does; the GL/dynarec profiles have no
    # date-embedding source and forbid one). None means the profile's golden
    # record is validated elsewhere (the combined native+make validators).
    if facts is None or facts.golden_epoch is None:
        return False
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "make_variables",
        "log",
        "log_sha256",
    }
    if facts.golden_epoch:
        required_keys.add("source_date_epoch")
    return bool(
        set(build) == required_keys
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and (
            profile != PORTABLE_FFMPEG_MAKE_PROFILE
            or source_date_epoch_is_well_formed(build.get("source_date_epoch"))
        )
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"])
    )


# Rebranded direct-cmake forks: the CMake target the upstream tree builds,
# reviewed per core. The artifact still ships under the core's own canonical
# name; everything not listed here keeps target == <core_id>_libretro exactly.
DIRECT_CMAKE_RENAMED_TARGETS = {
    "km_duckswanstation_xtreme_amped": "swanstation_libretro",
}


def direct_cmake_golden_build_contract_is_well_formed(
    build: object, core_id: str, arch: str
) -> bool:
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "source_date_epoch",
        "cmake",
        "overlays",
        "log",
        "log_sha256",
    }
    if not isinstance(build, dict) or set(build) != required_keys:
        return False
    expected_processor = {"arm64": "aarch64", "armhf": "arm"}.get(arch)
    cmake = build.get("cmake")
    if (
        build.get("driver") != "direct-cmake"
        or build.get("environment") != "sanitized-v1"
        or build.get("compile_definitions") != []
        or not source_date_epoch_is_well_formed(build.get("source_date_epoch"))
        or build.get("log") != "build.log"
        or not isinstance(build.get("log_sha256"), str)
        or not SHA256_RE.fullmatch(build["log_sha256"])
        or expected_processor is None
        or not isinstance(cmake, dict)
        or not {"generator", "build_type", "target", "system"} <= set(cmake)
        or not set(cmake)
        <= {"generator", "build_type", "target", "system", "source_subdir", "defines"}
        or cmake.get("generator") != "Unix Makefiles"
        or cmake.get("build_type") != "Release"
        or cmake.get("target")
        != DIRECT_CMAKE_RENAMED_TARGETS.get(core_id, f"{core_id}_libretro")
        or cmake.get("system")
        != {"name": "Linux", "processor": expected_processor}
    ):
        return False
    # Optional reviewed extensions (tic80/squirreljme/ardens): validate shape.
    if "source_subdir" in cmake and not (
        isinstance(cmake["source_subdir"], str) and cmake["source_subdir"]
    ):
        return False
    if "defines" in cmake and not (
        isinstance(cmake["defines"], dict)
        and cmake["defines"]
        and all(
            isinstance(name, str) and isinstance(value, str)
            for name, value in cmake["defines"].items()
        )
    ):
        return False
    overlays = build.get("overlays")
    if not isinstance(overlays, list):
        return False
    source_paths = [
        overlay.get("source_path") if isinstance(overlay, dict) else None
        for overlay in overlays
    ]
    if any(not isinstance(path, str) for path in source_paths) or source_paths != sorted(
        source_paths
    ):
        return False
    overlay_keys = {
        "kind",
        "patch_path",
        "patch_sha256",
        "source_path",
        "preimage_sha256",
        "postimage_sha256",
    }
    seen_sources: set[str] = set()
    seen_patches: set[str] = set()
    for overlay in overlays:
        if not isinstance(overlay, dict) or not (
            overlay_keys <= set(overlay)
            and set(overlay) <= overlay_keys | {"submodule_path"}
        ):
            return False
        if "submodule_path" in overlay and not (
            isinstance(overlay["submodule_path"], str)
            and str(overlay.get("source_path", "")).startswith(
                overlay["submodule_path"] + "/"
            )
        ):
            return False
        try:
            patch_path = exact_relative_path(
                overlay.get("patch_path"), "promoted overlay patch_path"
            )
            source_path = exact_relative_path(
                overlay.get("source_path"), "promoted overlay source_path"
            )
        except PipelineError:
            return False
        if (
            overlay.get("kind") != "git-apply-v1"
            or not patch_path.startswith(f"patches/{core_id}/")
            or not patch_path.endswith(".patch")
            or patch_path in seen_patches
            or source_path in seen_sources
        ):
            return False
        seen_patches.add(patch_path)
        seen_sources.add(source_path)
        for digest_key in (
            "patch_sha256",
            "preimage_sha256",
            "postimage_sha256",
        ):
            digest = overlay.get(digest_key)
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                return False
        if overlay["preimage_sha256"] == overlay["postimage_sha256"]:
            return False
    return True



def direct_cargo_golden_build_contract_is_well_formed(
    build: object, core_id: str, arch: str
) -> bool:
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "source_date_epoch",
        "cargo",
        "log",
        "log_sha256",
    }
    if not isinstance(build, dict) or set(build) != required_keys:
        return False
    expected_triple_prefix = {
        "arm64": "aarch64-unknown-linux-gnu",
        "armhf": "armv7-unknown-linux-gnueabihf",
    }.get(arch)
    cargo = build.get("cargo")
    return (
        build.get("driver") == "direct-cargo"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and source_date_epoch_is_well_formed(build.get("source_date_epoch"))
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
        and expected_triple_prefix is not None
        and isinstance(cargo, dict)
        and set(cargo) == {"subdir", "profile", "lock_sha256", "target"}
        and isinstance(cargo.get("subdir"), str)
        and bool(cargo["subdir"])
        and cargo.get("profile") == "release"
        and isinstance(cargo.get("lock_sha256"), str)
        and SHA256_RE.fullmatch(cargo["lock_sha256"]) is not None
        and isinstance(cargo.get("target"), str)
        and re.fullmatch(
            re.escape(expected_triple_prefix) + r"(\.[0-9]+(\.[0-9]+)*)?",
            cargo["target"],
        )
        is not None
    )


def compile_definition_list_is_well_formed(definitions: object) -> bool:
    if not isinstance(definitions, list) or any(
        not isinstance(definition, str) for definition in definitions
    ):
        return False
    if definitions != sorted(definitions):
        return False
    definition_names: set[str] = set()
    for definition in definitions:
        match = COMPILE_DEFINITION_RE.fullmatch(definition)
        if (
            match is None
            or int(match.group(2)) > 0xFFFFFFFF
            or match.group(1) in definition_names
        ):
            return False
        definition_names.add(match.group(1))
    return True


def _compile_log_definition_proof(
    build_log_text: str,
    definitions: object,
    arch: str,
    *,
    forbidden_names: frozenset[str] = frozenset(),
) -> tuple[bool, int | None]:
    if not compile_definition_list_is_well_formed(definitions):
        return False, None
    assert isinstance(definitions, list)
    expected = {f"-D{definition}" for definition in definitions}
    expected_by_name = {
        definition.split("=", 1)[0]: f"-D{definition}" for definition in definitions
    }
    if not expected:
        return True, None
    expected_compilers = TARGET_COMPILERS.get(arch)
    if expected_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    target_compile_count = 0
    first_target_compile: int | None = None
    tracked_names = set(expected_by_name).union(forbidden_names)
    for line_number, line in enumerate(build_log_text.splitlines()):
        # Large verbose Make logs can contain hundreds of thousands of unrelated
        # lines.  A real target command must contain a target compiler spelling,
        # so reject other lines cheaply, then retain shell parsing for candidate
        # commands.  Quoting or escaping can otherwise turn spellings such as
        # ``-""c`` into the exact ``-c`` token.
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False, first_target_compile
        if not tokens or "-c" not in tokens:
            continue
        compiler = Path(tokens[0]).name
        if (
            not COMPILER_COMMAND_RE.fullmatch(compiler)
            or compiler not in expected_compilers
        ):
            continue
        target_compile_count += 1
        if first_target_compile is None:
            first_target_compile = line_number
        if not expected.issubset(tokens):
            return False, first_target_compile
        if any(token.startswith("@") for token in tokens):
            return False, first_target_compile
        macro_tokens: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            token = tokens[token_index]
            if token == "-Xpreprocessor":
                if token_index + 1 >= len(tokens):
                    return False, first_target_compile
                macro_tokens.append(tokens[token_index + 1])
                token_index += 2
                continue
            if token.startswith("-Xpreprocessor="):
                return False, first_target_compile
            if token.startswith("-Wp,"):
                macro_tokens.extend(token.removeprefix("-Wp,").split(","))
            else:
                macro_tokens.append(token)
            token_index += 1
        if any(token.startswith("@") for token in macro_tokens):
            return False, first_target_compile
        for index, token in enumerate(macro_tokens):
            candidate = ""
            if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                candidate = token[2:]
            elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                candidate = macro_tokens[index + 1]
            candidate_name = re.split(r"[=(]", candidate, maxsplit=1)[0]
            if candidate_name not in tracked_names:
                continue
            if (
                candidate_name in forbidden_names
                or token != expected_by_name.get(candidate_name)
            ):
                return False, first_target_compile
    return target_compile_count > 0, first_target_compile


def compile_log_proves_definitions(
    build_log_text: str, definitions: object, arch: str
) -> bool:
    proven, _first_target_compile = _compile_log_definition_proof(
        build_log_text, definitions, arch
    )
    return proven


def _chipset_tuning_log_proves_resolved(
    build_log_text: str,
    tuning: Mapping[str, object],
    arch: str,
    *,
    allow_no_target_compile: bool = False,
) -> bool:
    """Prove an already validated embedded resolved profile."""

    if tuning.get("architecture") not in {"any", arch}:
        return False
    marker = "CORE_PIPELINE_CHIPSET_TUNING|" + json.dumps(
        {
            "profile_id": tuning["profile_id"],
            "content_sha256": tuning["content_sha256"],
            "compiler_argument_mapping_version": tuning[
                "compiler_argument_mapping_version"
            ],
            "compiler_arguments": tuning["compiler_arguments"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if build_log_text.splitlines().count(marker) != 1:
        return False
    expected_arguments = set(tuning["compiler_arguments"])
    compilers = tuple(
        sorted(
            set(TARGET_COMPILERS.get(arch, ())).union(
                TARGET_CXX_COMPILERS.get(arch, ())
            )
        )
    )
    if not compilers:
        raise PipelineError(f"unknown architecture: {arch}")
    # Architecture/ABI selection is distinct from chipset tuning.  The exact
    # baseline values below are portable within the pipeline's two target
    # architectures; every other value remains fail-closed.  In particular,
    # ARMHF's hard-float calling convention is also enforced on the produced
    # ELF by validate_artifact(), while CPU, tune, and FPU selection remain
    # exclusively registry-owned.
    architecture_baseline_arguments = {
        "arm64": frozenset({"-march=armv8-a"}),
        "armhf": frozenset({"-march=armv7-a", "-mfloat-abi=hard"}),
    }[arch]
    machine_prefixes = (
        "-march=",
        "-mcpu=",
        "-mtune=",
        "-mfpu=",
        "-mfloat-abi=",
    )
    allowed_machine_arguments = expected_arguments.union(
        architecture_baseline_arguments
    )
    target_compile_count = 0
    for line in build_log_text.splitlines():
        if not line_may_name_target_compiler(line, compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        compiler_indexes = [
            index
            for index, token in enumerate(tokens)
            if Path(token).name in compilers
            and COMPILER_COMMAND_RE.fullmatch(Path(token).name)
        ]
        if not compiler_indexes:
            continue
        compiler_index = compiler_indexes[0]
        command_shaped = len(compiler_indexes) == 1 and (
            compiler_index == 0
            or (
                compiler_index == 3
                and tokens[0] == "cd"
                and tokens[2] == "&&"
            )
        )
        if not command_shaped:
            if (
                "-c" in tokens
                or any(token.startswith(machine_prefixes) for token in tokens)
                or any(token.startswith("@") for token in tokens)
            ):
                return False
            continue
        tokens = tokens[compiler_index:]
        if any(
            token.startswith(machine_prefixes)
            and token not in allowed_machine_arguments
            for token in tokens
        ):
            return False
        normalized_compiler_tokens = [Path(tokens[0]).name, *tokens[1:]]
        parsed_compile = c_asm_compile_invocation(
            normalized_compiler_tokens,
            set(TARGET_COMPILERS[arch]) - set(TARGET_CXX_COMPILERS[arch]),
            expected_cxx_compilers=frozenset(TARGET_CXX_COMPILERS[arch]),
        )
        armhf_assembly_compile = (
            arch == "armhf"
            and parsed_compile is not None
            and parsed_compile[1].endswith((".s", ".S"))
        )
        if any(
            tokens.count(argument)
            > (
                2
                if armhf_assembly_compile
                and argument == "-mfloat-abi=hard"
                else 1
            )
            for argument in allowed_machine_arguments
        ):
            return False
        if any(token.startswith("@") for token in tokens):
            return False
        if "-c" not in tokens:
            continue
        target_compile_count += 1
        if any(tokens.count(argument) != 1 for argument in expected_arguments):
            return False
    return target_compile_count > 0 or (
        allow_no_target_compile and not expected_arguments
    )


def core_contract_log_without_tuning_arguments(
    build_log_text: str,
    tuning: Mapping[str, object],
    arch: str,
) -> str | None:
    """Project a proven tuned log onto the core-owned untuned argv contract.

    Only the exact registry-owned machine arguments are removed, and only from
    recognized target-compiler command lines. The full tuning proof runs first,
    so count, duplication, conflicting machine flags, response files, and the
    registry marker remain fail-closed before the existing core proof sees its
    original argv shape.
    """

    if not _chipset_tuning_log_proves_resolved(
        build_log_text,
        tuning,
        arch,
        allow_no_target_compile=not tuning.get("compiler_arguments"),
    ):
        return None
    expected_arguments = tuple(tuning.get("compiler_arguments", ()))
    tuning_marker = "CORE_PIPELINE_CHIPSET_TUNING|" + json.dumps(
        {
            "profile_id": tuning["profile_id"],
            "content_sha256": tuning["content_sha256"],
            "compiler_argument_mapping_version": tuning[
                "compiler_argument_mapping_version"
            ],
            "compiler_arguments": tuning["compiler_arguments"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if not expected_arguments:
        return "\n".join(
            line
            for line in build_log_text.splitlines()
            if line != tuning_marker
        )
    compilers = set(TARGET_COMPILERS.get(arch, ())).union(
        TARGET_CXX_COMPILERS.get(arch, ())
    )
    if not compilers:
        raise PipelineError(f"unknown architecture: {arch}")
    projected: list[str] = []
    for line in build_log_text.splitlines():
        if line == tuning_marker:
            continue
        if not line_may_name_target_compiler(line, compilers):
            projected.append(line)
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return None
        compiler_indexes = [
            index
            for index, token in enumerate(tokens)
            if Path(token).name in compilers
            and COMPILER_COMMAND_RE.fullmatch(Path(token).name)
        ]
        if not compiler_indexes:
            projected.append(line)
            continue
        if len(compiler_indexes) != 1:
            if "-c" in tokens:
                return None
            projected.append(line)
            continue
        compiler_index = compiler_indexes[0]
        if compiler_index not in {0, 3} or (
            compiler_index == 3
            and not (tokens[0] == "cd" and tokens[2] == "&&")
        ):
            if "-c" in tokens:
                return None
            projected.append(line)
            continue
        command_tokens = tokens[compiler_index:]
        normalized = line
        for argument in expected_arguments:
            occurrences = list(
                re.finditer(r"(?<!\S)" + re.escape(argument) + r"(?!\S)", normalized)
            )
            if command_tokens.count(argument) == 0:
                continue
            if command_tokens.count(argument) != 1 or len(occurrences) != 1:
                return None
            normalized = (
                normalized[: occurrences[0].start()]
                + normalized[occurrences[0].end() :]
            )
        projected.append(normalized)
    return "\n".join(projected)


def make_variable_log_proves_contract(
    build_log_text: str, make_variables: object, arch: str
) -> bool:
    profile = make_variable_profile(make_variables)
    if profile is None:
        return False
    expected_markers = make_variable_markers(make_variables)
    if not expected_markers:
        return False
    marker_lines = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_MAKEFLAGS|")
        or line.startswith("CORE_PIPELINE_MAKE_VARIABLE|")
    ]
    if marker_lines != expected_markers:
        return False
    portable_first_target_compile: int | None = None
    if profile == PORTABLE_FFMPEG_MAKE_PROFILE:
        portable_proven, portable_first_target_compile = (
            _compile_log_definition_proof(
                build_log_text,
                list(PORTABLE_FFMPEG_COMPILE_DEFINITIONS),
                arch,
                forbidden_names=PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS,
            )
        )
        if not portable_proven:
            return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    if expected_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    lines = build_log_text.splitlines()
    marker_positions = [lines.index(marker) for marker in expected_markers]
    if profile == PORTABLE_FFMPEG_MAKE_PROFILE:
        return bool(
            portable_first_target_compile is not None
            and max(marker_positions) < portable_first_target_compile
        )
    first_target_compile: int | None = None
    snes9x2005_plus_macro = "USE_BLARGG_APU"
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        if not tokens:
            continue
        compiler = Path(tokens[0]).name
        if (
            not COMPILER_COMMAND_RE.fullmatch(compiler)
            or compiler not in expected_compilers
        ):
            continue
        if any(token.startswith("@") for token in tokens):
            return False
        if profile == VECX_SOFTWARE_MAKE_PROFILE:
            if not vecx_command_tokens_are_software_only(tokens):
                return False
        if "-c" not in tokens:
            continue
        if (
            profile == SNES9X2005_PLUS_MAKE_PROFILE
            and compiler in expected_cxx_compilers
        ):
            return False
        if first_target_compile is None:
            first_target_compile = line_number
        macro_tokens: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            token = tokens[token_index]
            if token == "-Xpreprocessor":
                if token_index + 1 >= len(tokens):
                    return False
                macro_tokens.append(tokens[token_index + 1])
                token_index += 2
                continue
            if token.startswith("-Xpreprocessor="):
                return False
            if token.startswith("-Wp,"):
                macro_tokens.extend(token.removeprefix("-Wp,").split(","))
            else:
                macro_tokens.append(token)
            token_index += 1
        for index, token in enumerate(macro_tokens):
            candidate = ""
            if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                candidate = token[2:]
            elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                candidate = macro_tokens[index + 1]
            name = re.split(r"[=(]", candidate, maxsplit=1)[0]
            profile_facts = _make_variable_profile_facts().get(profile or "")
            forbidden_macros = (
                profile_facts.forbidden_compile_macros
                if profile_facts is not None
                else frozenset()
            )
            if name in forbidden_macros:
                return False
        if profile == SNES9X2005_PLUS_MAKE_PROFILE:
            if any(
                token == "-Xpreprocessor"
                or token.startswith("-Xpreprocessor=")
                for token in tokens
            ):
                return False
            plus_tokens = []
            for index, token in enumerate(macro_tokens):
                candidate = ""
                if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                    candidate = token[2:]
                elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                    candidate = macro_tokens[index + 1]
                if re.split(r"[=(]", candidate, maxsplit=1)[0] == snes9x2005_plus_macro:
                    plus_tokens.append(token)
            if (
                plus_tokens != ["-DUSE_BLARGG_APU"]
                or tokens.count("-DUSE_BLARGG_APU") != 1
            ):
                return False
    return (
        first_target_compile is not None
        and max(marker_positions) < first_target_compile
    )


def git_version_markers(
    git_version: object,
    source_commit: object,
    *,
    resolvers: BuildContractResolvers,
) -> list[str]:
    if not git_version_contract_is_well_formed(
        git_version,
        source_commit,
        resolvers=resolvers,
    ):
        return []
    assert isinstance(git_version, dict)
    value = git_version["value"]
    if git_version["derivation"] == FBNEO_GIT_VERSION_DERIVATION:
        return list(fbneo_git_version_markers(git_version))
    if git_version["derivation"] == NATIVE_GIT_VERSION_DERIVATION:
        if source_commit in MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS:
            makeflags = f'-- GIT_VERSION="\\{value}"'
            return [
                (
                    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                    f'"{value}"|command-scoped-makeflags'
                ),
                f"CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|{makeflags}",
                f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|command line',
            ]
        if source_commit in ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS:
            return [
                (
                    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                    f'"{value}"|command-scoped-environment'
                ),
                f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|environment',
            ]
        return [f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|file']
    if git_version["derivation"] == NATIVE_GIT_VERSION_SHORT8_DERIVATION:
        return list(mame2003_plus_git_version_markers(git_version))
    if git_version["derivation"] == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
        return [f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|file']
    if git_version["derivation"] == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
        return [
            "CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV|command line:|10",
            f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|file',
        ]
    if git_version["derivation"] == NATIVE_GIT_DESCRIBE_DERIVATION:
        return [f"CORE_PIPELINE_NATIVE_GIT_VERSION|{value}|file"]
    return [
        f"CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION={value}",
        f"CORE_PIPELINE_GIT_VERSION|{value}|command line",
    ]


def git_version_log_proves_contract(
    build_log_text: str,
    git_version: object,
    source_commit: object,
    arch: str,
    *,
    resolvers: BuildContractResolvers,
) -> bool:
    if source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS:
        lowered_log = build_log_text.lower()
        if "fatal:" in lowered_log or "dubious ownership" in lowered_log:
            return False
    expected_markers = git_version_markers(
        git_version,
        source_commit,
        resolvers=resolvers,
    )
    if not expected_markers:
        return False
    marker_lines = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|")
        or line.startswith("CORE_PIPELINE_GIT_VERSION|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_DATE|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_DATE_BUILD_ARG|")
        or line.startswith("CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV|")
    ]
    if marker_lines != expected_markers:
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    assert isinstance(git_version, dict)
    derivation = git_version.get("derivation")
    if derivation == FBNEO_GIT_VERSION_DERIVATION:
        expected_tokens = fbneo_compile_tokens(git_version)
        if len(expected_tokens) != 2:
            return False
        protected_macro_names = {"GIT_DATE", "GIT_VERSION"}
    elif derivation == NATIVE_GIT_DESCRIBE_DERIVATION:
        compile_macro = NATIVE_GIT_DESCRIBE_COMPILE_MACROS_BY_COMMIT.get(
            source_commit
        )
        if not isinstance(compile_macro, str):
            return False
        expected_tokens = (
            f'-D{compile_macro}="{git_version["value"]}"',
        )
        protected_macro_names = {compile_macro, "GIT_VERSION"}
    else:
        compile_macro = "GIT_VERSION"
        expected_tokens = (
            f'-D{compile_macro}="{git_version["value"]}"',
        )
        protected_macro_names = {compile_macro}
    compiler_scope = git_version.get("compiler_scope")
    lines = build_log_text.splitlines()
    marker_positions = [lines.index(marker) for marker in expected_markers]
    first_target_compile: int | None = None
    bound_compile_count = 0
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        if (
            source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
            and not command_line_is_lexically_safe(line)
        ):
            return False
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        if not tokens or "-c" not in tokens:
            continue
        raw_compiler = tokens[0]
        compiler = Path(raw_compiler).name
        if (
            source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
            and raw_compiler not in expected_compilers
        ):
            return False
        if (
            not COMPILER_COMMAND_RE.fullmatch(compiler)
            or compiler not in expected_compilers
        ):
            continue
        if first_target_compile is None:
            first_target_compile = line_number
        if compiler_scope == GIT_VERSION_CXX_SCOPE:
            requires_token = compiler in expected_cxx_compilers
        elif compiler_scope == GIT_VERSION_C_SCOPE:
            requires_token = compiler not in expected_cxx_compilers
        else:
            requires_token = True
        expected_count = 1 if requires_token else 0
        if (
            any(
                tokens.count(expected_token) != expected_count
                for expected_token in expected_tokens
            )
            or any(token.startswith("@") for token in tokens)
            or (
                source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
                and any("@" in token for token in tokens[1:])
            )
        ):
            return False
        if requires_token:
            bound_compile_count += 1
        macro_tokens: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            token = tokens[token_index]
            if token == "-Xpreprocessor":
                if token_index + 1 >= len(tokens):
                    return False
                macro_tokens.append(tokens[token_index + 1])
                token_index += 2
                continue
            if token.startswith("-Xpreprocessor="):
                return False
            if token.startswith("-Wp,"):
                macro_tokens.extend(token.removeprefix("-Wp,").split(","))
            else:
                macro_tokens.append(token)
            token_index += 1
        for index, token in enumerate(macro_tokens):
            if token in expected_tokens:
                continue
            candidate = ""
            if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                candidate = token[2:]
            elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                candidate = macro_tokens[index + 1]
            candidate_name = re.split(r"[=(]", candidate, maxsplit=1)[0]
            if candidate_name in protected_macro_names:
                return False
    return bool(
        bound_compile_count
        and first_target_compile is not None
        and max(marker_positions) < first_target_compile
    )


def make_variable_markers(variables: object) -> list[str]:
    if not make_variable_mapping_is_well_formed(variables):
        return []
    assert isinstance(variables, dict)
    canonical = make_output_sync_prefix(variables) + " ".join(
        f"{name}={value}" for name, value in variables.items()
    )
    return [
        "CORE_PIPELINE_MAKEFLAGS|" + canonical,
        *[
            f"CORE_PIPELINE_MAKE_VARIABLE|{name}|{value}|command line"
            for name, value in variables.items()
        ],
    ]
