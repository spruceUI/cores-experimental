"""Exact FBNeo source, version, build-shell, and compile/link contract.

The build-log oracle uses the shared mixed-language compile/link proof standard
(FBNeo is predominantly C++). Object and source paths are referenced from the
libretro build directory as ``../../<top>/...``; a semantic path alias contains
them for normalization while the sha256 identities still pin the exact raw argv.
"""

from __future__ import annotations

import re
import shlex

from ..errors import PipelineError
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


FBNEO_CORE_ID = "fbneo"
FBNEO_BUILD_ARTIFACT_NAME = "fbneo_libretro.so"

FBNEO_SOURCE_COMMIT = "9d7716aa20cbdf49024f42980c33c7cd366e784f"
FBNEO_SOURCE_TREE = "e533af34d2db18f11cefadbb93e509579580d0b7"
FBNEO_SOURCE_DATE_EPOCH = 1777823586

FBNEO_GIT_VERSION_DERIVATION = "fbneo-native-short9-date-v1"
FBNEO_GIT_VERSION_VALUE = "9d7716aa2"
FBNEO_GIT_DATE = "260503"
FBNEO_GIT_VERSION = {
    "derivation": FBNEO_GIT_VERSION_DERIVATION,
    "value": FBNEO_GIT_VERSION_VALUE,
    "git_date": FBNEO_GIT_DATE,
    "compiler_scope": "cxx",
}

# Make receives the raw abbreviated object name. Upstream prepends ``GIT``
# while forming the C++ preprocessor definition.
FBNEO_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"GIT9d7716aa2\"'
)
FBNEO_GIT_DATE_LOG_TOKEN = r'-DGIT_DATE=\"260503\"'
FBNEO_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION="GIT9d7716aa2"'
FBNEO_GIT_DATE_COMPILE_TOKEN = '-DGIT_DATE="260503"'

# Linux assigns these four ARM HWCAP2 bits as a stable userspace ABI.  The
# A30 armhf sysroot predates the corresponding asm/hwcap.h names, while the
# bundled lib7z CpuArch.c expects them to exist.  Supplying the canonical
# values restores the missing header vocabulary without patching upstream
# source or claiming a CPU feature that getauxval(AT_HWCAP2) does not report.
FBNEO_ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=1",
    "HWCAP2_CRC32=16",
    "HWCAP2_SHA1=4",
    "HWCAP2_SHA2=8",
]

FBNEO_FORBIDDEN_NEEDED_PREFIXES = [
    "libEGL",
    "libGL",
    "libGLES",
    "libOpenGL",
    "libSDL",
    "libz",
]
FBNEO_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-fbneo.yml",
    "source_url": "https://github.com/libretro/FBNeo.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": FBNEO_SOURCE_COMMIT,
    "source_tree": FBNEO_SOURCE_TREE,
    "source_key": FBNEO_CORE_ID,
    "source_dir": "libretro-fbneo",
    "output_path": "dist/unix/fbneo_libretro.so",
    "artifact_name": FBNEO_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/fbneo_libretro.info"
    ),
    "metadata_artifact_name": "fbneo_libretro.info",
    "targets": ["arm64", "armhf"],
}

FBNEO_SOURCE_IDENTITY_MARKER = (
    "CORE_PIPELINE_SOURCE_IDENTITY|fbneo|"
    f"{FBNEO_SOURCE_COMMIT}|{FBNEO_SOURCE_TREE}|catalog"
)
FBNEO_COMMAND_SCOPED_MAKEFLAGS = (
    "-- GIT_VERSION=9d7716aa2 GIT_DATE=260503 HIDE="
)
FBNEO_NATIVE_GIT_VERSION_MARKERS = (
    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
    '"9d7716aa2"|command-scoped-makeflags',
    "CORE_PIPELINE_NATIVE_GIT_DATE_BUILD_ARG|"
    '"260503"|command-scoped-makeflags',
    "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
    "-- GIT_VERSION=9d7716aa2 GIT_DATE=260503 HIDE=",
    'CORE_PIPELINE_NATIVE_GIT_VERSION|"9d7716aa2"|command line',
    'CORE_PIPELINE_NATIVE_GIT_DATE|"260503"|command line',
)
FBNEO_RECIPE_MARKER = (
    "CORE_PIPELINE_FBNEO_RECIPE|fbneo-native-short9-date-v1|"
    '"9d7716aa2"|"260503"|command-scoped-makeflags|HIDE='
)
FBNEO_BUILD_BEGIN_MARKER = {
    arch: f"CORE_PIPELINE_FBNEO_BUILD_BEGIN|{arch}"
    for arch in ("arm64", "armhf")
}
FBNEO_BUILD_END_MARKER = {
    arch: f"CORE_PIPELINE_FBNEO_BUILD_END|{arch}"
    for arch in ("arm64", "armhf")
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _exact_spec() -> dict:
    identity = FBNEO_SPEC_IDENTITY
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
        "overlays": {
            "arm64": [dict(FBNEO_SORT_OVERLAY)],
            "armhf": [dict(FBNEO_SORT_OVERLAY)],
        },
            "compile_definitions": {
                "armhf": FBNEO_ARMHF_COMPILE_DEFINITIONS,
            },
            "source_date_epoch": FBNEO_SOURCE_DATE_EPOCH,
            "git_version": FBNEO_GIT_VERSION,
        },
        "metadata": {
            "source_path": identity["metadata_source_path"],
            "artifact_name": identity["metadata_artifact_name"],
        },
        "validation": {
            "forbidden_needed_prefixes": FBNEO_FORBIDDEN_NEEDED_PREFIXES,
        },
        "targets": identity["targets"],
    }


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the fbneo core must preserve its exact native short9 "
    "version/date, command-scoped Make recipe, source, "
    "epoch, metadata, target, and dependency contract"
)


FBNEO_SORT_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/fbneo/makefile-sort-wildcard-sources.patch",
    "patch_sha256": (
        "36359710caa6b337253ea7acf3cc0fe43083a3eb1977f62cc764fd888eceb54e"
    ),
    "source_path": "src/burner/libretro/Makefile.all",
    "preimage_sha256": (
        "b7030bbeb7c69a46e846084a1a852c972d5360b8f319caca987dc1ec9dfefb73"
    ),
    "postimage_sha256": (
        "d7e2bd630fffafb6def25a52295e2b582fe5bcf31b8e246dcadc53f2f437bc0b"
    ),
}


def fbneo_spec_is_well_formed(spec: object) -> bool:
    """Require FBNeo's complete immutable catalog contract."""

    return bool(isinstance(spec, dict) and spec == _exact_spec())


def fbneo_identity_is_well_formed(spec: object) -> bool:
    """Bind shared integration to FBNeo's exact catalog identity."""

    return fbneo_spec_is_well_formed(spec)


def _git_version_from(value: object) -> object:
    if isinstance(value, dict) and "build" in value:
        build = value.get("build")
        return build.get("git_version") if isinstance(build, dict) else None
    return value


def fbneo_git_version_contract_is_well_formed(value: object) -> bool:
    """Recognize only the reviewed native hash-and-date contract."""

    return bool(
        isinstance(value, dict)
        and value == FBNEO_GIT_VERSION
    )


def fbneo_git_version_markers(value: object) -> tuple[str, ...]:
    """Return exact provenance markers for the reviewed version tuple."""

    if not fbneo_git_version_contract_is_well_formed(
        _git_version_from(value)
    ):
        return ()
    return FBNEO_NATIVE_GIT_VERSION_MARKERS


def fbneo_compile_tokens(value: object) -> tuple[str, ...]:
    """Return the two exact preprocessor tokens on each C++ compile."""

    if not fbneo_git_version_contract_is_well_formed(
        _git_version_from(value)
    ):
        return ()
    return (
        FBNEO_GIT_VERSION_COMPILE_TOKEN,
        FBNEO_GIT_DATE_COMPILE_TOKEN,
    )


def fbneo_command_scoped_makeflags(spec: object) -> str:
    """Derive non-exported MAKEFLAGS for FBNeo's single build command."""

    if not fbneo_spec_is_well_formed(spec):
        raise PipelineError("FBNeo MAKEFLAGS requires its exact reviewed spec")
    return FBNEO_COMMAND_SCOPED_MAKEFLAGS


def fbneo_build_shell(
    spec: object,
    source_key: object,
    arch: str,
) -> str:
    """Render FBNeo's exact source/version framing and scoped build."""

    if (
        not fbneo_spec_is_well_formed(spec)
        or source_key != FBNEO_CORE_ID
        or arch not in FBNEO_BUILD_BEGIN_MARKER
    ):
        raise PipelineError(
            "FBNeo build shell requires its exact spec and target"
        )
    makeflags = fbneo_command_scoped_makeflags(spec)
    command = (
        f"MAKEFLAGS={shlex.quote(makeflags)} "
        f"./libretro-build.sh {FBNEO_CORE_ID}"
    )
    markers = (
        FBNEO_SOURCE_IDENTITY_MARKER,
        *FBNEO_NATIVE_GIT_VERSION_MARKERS,
        FBNEO_RECIPE_MARKER,
        FBNEO_BUILD_BEGIN_MARKER[arch],
    )
    marker_commands = tuple(
        f"printf '%s\\n' {shlex.quote(marker)}" for marker in markers
    )
    return "\n".join(
        (
            *marker_commands,
            command,
            (
                "printf '%s\\n' "
                + shlex.quote(FBNEO_BUILD_END_MARKER[arch])
            ),
        )
    )


def fbneo_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind evidence to the exact pristine source with no submodules."""

    identity = FBNEO_SPEC_IDENTITY
    return bool(
        core_id == FBNEO_CORE_ID
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


def fbneo_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
    arch: object,
) -> bool:
    """Require FBNeo's exact epoch, version, target, and log shape."""

    expected_definitions = {
        "arm64": [],
        "armhf": FBNEO_ARMHF_COMPILE_DEFINITIONS,
    }.get(arch)

    return bool(
        expected_definitions is not None
        and isinstance(build, dict)
        and source_commit == FBNEO_SOURCE_COMMIT
        and fbneo_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": expected_definitions,
            "git_version": FBNEO_GIT_VERSION,
            "source_date_epoch": FBNEO_SOURCE_DATE_EPOCH,
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


FBNEO_LOG_CONTRACT_ID = "fbneo-mixed-language-v1"
FBNEO_SEMANTIC_PATH_ALIASES = (("../../", ""),)
FBNEO_EXPECTED_COMPILE_COUNT = 1090
FBNEO_EXPECTED_LANGUAGE_COUNTS = {"c": 61, "cxx": 1029}
FBNEO_EXPECTED_COMPILE_PAIR_SHA256 = (
    "8ed33f2a62f1bc3d942f5c787b05c393552e5a87e7735100afde130f3eb76541"
)
FBNEO_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "6ecb812bfc3223c94a7a52fc68423028e3bf117d0fa659a458521885e28d0205",
    "armhf": "591f500770d1cf61617526deef74d802c8a459fdf125d78695c539e37149242b",
}
FBNEO_EXPECTED_LINK_OBJECT_SHA256 = (
    "abb10fc055016eb2dc5fc9c0146d5133f4435039bb1dbd67c1f9b56a276f9c36"
)
FBNEO_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "337cd999ba1e4e438ded6cadc96935b03211adcc086943b3fbd900c2fc2c7a3e"
)
FBNEO_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-no-undefined",
    "-Wl,--version-script=../../burner/libretro/link.T",
    "-lpthread",
    "-fPIC",
)


def fbneo_mixed_language_contract() -> MixedLanguageLogContract:
    """Return FBNeo's exact mixed-language compile/link proof parameters."""

    return MixedLanguageLogContract(
        core_id=FBNEO_CORE_ID,
        expected_compile_count=FBNEO_EXPECTED_COMPILE_COUNT,
        expected_language_counts=FBNEO_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=FBNEO_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            FBNEO_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=FBNEO_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=FBNEO_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=FBNEO_BUILD_ARTIFACT_NAME,
        expected_link_options=FBNEO_EXPECTED_LINK_OPTIONS,
        source_commit=FBNEO_SOURCE_COMMIT,
        source_tree=FBNEO_SOURCE_TREE,
        semantic_path_aliases=FBNEO_SEMANTIC_PATH_ALIASES,
        expected_link_language="cxx",
    )


def fbneo_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove FBNeo's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        fbneo_mixed_language_contract(),
    )


__all__ = [
    "FBNEO_ARMHF_COMPILE_DEFINITIONS",
    "FBNEO_BUILD_ARTIFACT_NAME",
    "FBNEO_BUILD_BEGIN_MARKER",
    "FBNEO_BUILD_END_MARKER",
    "FBNEO_COMMAND_SCOPED_MAKEFLAGS",
    "FBNEO_CORE_ID",
    "FBNEO_FORBIDDEN_NEEDED_PREFIXES",
    "FBNEO_GIT_DATE",
    "FBNEO_GIT_DATE_COMPILE_TOKEN",
    "FBNEO_GIT_DATE_LOG_TOKEN",
    "FBNEO_GIT_VERSION",
    "FBNEO_GIT_VERSION_COMPILE_TOKEN",
    "FBNEO_GIT_VERSION_DERIVATION",
    "FBNEO_GIT_VERSION_LOG_TOKEN",
    "FBNEO_GIT_VERSION_VALUE",
    "FBNEO_LOG_CONTRACT_ID",
    "FBNEO_NATIVE_GIT_VERSION_MARKERS",
    "FBNEO_RECIPE_MARKER",
    "FBNEO_SOURCE_COMMIT",
    "FBNEO_SOURCE_DATE_EPOCH",
    "FBNEO_SOURCE_IDENTITY_MARKER",
    "FBNEO_SOURCE_TREE",
    "FBNEO_SPEC_IDENTITY",
    "fbneo_build_shell",
    "fbneo_command_scoped_makeflags",
    "fbneo_compile_tokens",
    "fbneo_git_version_contract_is_well_formed",
    "fbneo_git_version_markers",
    "fbneo_golden_build_contract_is_well_formed",
    "fbneo_golden_source_is_well_formed",
    "fbneo_identity_is_well_formed",
    "fbneo_log_proves_contract",
    "fbneo_mixed_language_contract",
    "fbneo_spec_is_well_formed",
]
