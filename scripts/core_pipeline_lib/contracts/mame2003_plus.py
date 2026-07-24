"""Exact MAME 2003-Plus native-version C-only compile/link contract.

Uses the shared C-only compile/link proof standard; the former
full-log-envelope proof (exact command trace, clean invocation, framing, and
reviewed diagnostics) was dropped in favour of that single shared standard.
Its command-scoped-makeflags build shell and promoted-record predicates are
kept for the pipeline.
"""

from __future__ import annotations

import re
import shlex

from ..errors import PipelineError
from .c_only import COnlyLogContract, c_only_log_proves_contract


MAME2003_PLUS_CORE_ID = "mame2003_plus"
MAME2003_PLUS_BUILD_ARTIFACT_NAME = "mame2003_plus_libretro.so"
MAME2003_PLUS_LOG_CONTRACT_ID = "mame2003-plus-c-only-v1"
MAME2003_PLUS_LOG_PROOF_KIND = "core-arch-source"

MAME2003_PLUS_SOURCE_COMMIT = (
    "5373e38e1091eb28f075513ecdc2575bafc8a5e3"
)
MAME2003_PLUS_SOURCE_TREE = "990e22f33a33cbfe733e22b3b5fef6cda76056fb"
MAME2003_PLUS_SOURCE_DATE_EPOCH = 1777763287
MAME2003_PLUS_NATIVE_GIT_VERSION_DERIVATION = "native-space-short8-v1"
MAME2003_PLUS_NATIVE_GIT_VERSION = " 5373e38e"
MAME2003_PLUS_GIT_VERSION = {
    "derivation": MAME2003_PLUS_NATIVE_GIT_VERSION_DERIVATION,
    "value": MAME2003_PLUS_NATIVE_GIT_VERSION,
    "compiler_scope": "c",
}
MAME2003_PLUS_FORBIDDEN_NEEDED_PREFIXES = [
    "libEGL",
    "libGL",
    "libGLES",
    "libOpenGL",
    "libSDL",
    "libstdc++",
    "libz",
]
MAME2003_PLUS_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mame2003_plus.yml",
    "source_url": (
        "https://github.com/libretro/mame2003-plus-libretro.git"
    ),
    "source_requested_ref": "refs/heads/master",
    "source_commit": MAME2003_PLUS_SOURCE_COMMIT,
    "source_tree": MAME2003_PLUS_SOURCE_TREE,
    "source_key": MAME2003_PLUS_CORE_ID,
    "source_dir": "libretro-mame2003_plus",
    "output_path": "dist/unix/mame2003_plus_libretro.so",
    "artifact_name": MAME2003_PLUS_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mame2003_plus_libretro.info"
    ),
    "metadata_artifact_name": "mame2003_plus_libretro.info",
    "targets": ["arm64", "armhf"],
}

MAME2003_PLUS_SOURCE_IDENTITY_MARKER = (
    "CORE_PIPELINE_SOURCE_IDENTITY|mame2003_plus|"
    "5373e38e1091eb28f075513ecdc2575bafc8a5e3|"
    "990e22f33a33cbfe733e22b3b5fef6cda76056fb|catalog"
)
MAME2003_PLUS_COMMAND_SCOPED_MAKEFLAGS = (
    '-- GIT_VERSION="\\ 5373e38e" HIDE='
)
MAME2003_PLUS_NATIVE_GIT_VERSION_MARKERS = (
    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
    '" 5373e38e"|command-scoped-makeflags',
    "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
    '-- GIT_VERSION="\\ 5373e38e" HIDE=',
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 5373e38e"|command line',
)
MAME2003_PLUS_RECIPE_MARKER = (
    "CORE_PIPELINE_MAME2003_PLUS_RECIPE|native-space-short8-v1|"
    '" 5373e38e"|command-scoped-makeflags|HIDE='
)
MAME2003_PLUS_BUILD_BEGIN_MARKER = {
    arch: f"CORE_PIPELINE_MAME2003_PLUS_BUILD_BEGIN|{arch}"
    for arch in ("arm64", "armhf")
}
MAME2003_PLUS_BUILD_END_MARKER = {
    arch: f"CORE_PIPELINE_MAME2003_PLUS_BUILD_END|{arch}"
    for arch in ("arm64", "armhf")
}

MAME2003_PLUS_TARGET_CC = {
    "arm64": "aarch64-linux-gnu-gcc",
    "armhf": "arm-a30-linux-gnueabihf-gcc",
}
MAME2003_PLUS_EXPECTED_COMPILE_COUNT = 1807
MAME2003_PLUS_EXPECTED_COMPILE_PAIR_SHA256 = (
    "c7fc0ae0d5b80dc0ddf3a5f75a44b8a93adc9dbed482bf8d776d8e94f78ebf6e"
)
MAME2003_PLUS_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "1cd718fcece2ea27a1a321e0cf7e412182bbc59439eb14004a0a742f61a3d470",
    "armhf": "b244e04140ea1fed40628f58ad916bd1a6be32d0a3eeec7ef2f6fdb9d8aeefaf",
}
MAME2003_PLUS_EXPECTED_LINK_OBJECT_SHA256 = (
    "1c9727a4afe851a8f32f3e021f4af08b4fc00c959b8960df17ee042988eb2815"
)
MAME2003_PLUS_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-lm",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _exact_spec() -> dict:
    identity = MAME2003_PLUS_SPEC_IDENTITY
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
            "source_date_epoch": MAME2003_PLUS_SOURCE_DATE_EPOCH,
            "git_version": MAME2003_PLUS_GIT_VERSION,
        },
        "metadata": {
            "source_path": identity["metadata_source_path"],
            "artifact_name": identity["metadata_artifact_name"],
        },
        "validation": {
            "forbidden_needed_prefixes": (
                MAME2003_PLUS_FORBIDDEN_NEEDED_PREFIXES
            ),
        },
        "targets": identity["targets"],
    }


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mame2003_plus core must preserve its exact native "
    "short8 version, command-scoped Make recipe, source, "
    "epoch, metadata, target, and dependency contract"
)


def mame2003_plus_spec_is_well_formed(spec: object) -> bool:
    """Require MAME 2003-Plus's complete immutable catalog contract."""

    return bool(isinstance(spec, dict) and spec == _exact_spec())


def mame2003_plus_identity_is_well_formed(spec: object) -> bool:
    """Bind shared integration to MAME 2003-Plus's exact catalog identity."""

    return mame2003_plus_spec_is_well_formed(spec)


def mame2003_plus_git_version_contract_is_well_formed(
    value: object,
) -> bool:
    """Recognize only the reviewed eight-character native version contract."""

    return bool(isinstance(value, dict) and value == MAME2003_PLUS_GIT_VERSION)


def mame2003_plus_git_version_markers(value: object) -> tuple[str, ...]:
    """Return exact provenance markers for the reviewed git-version input."""

    if isinstance(value, dict) and "build" in value:
        build = value.get("build")
        value = build.get("git_version") if isinstance(build, dict) else None
    if not mame2003_plus_git_version_contract_is_well_formed(value):
        return ()
    return MAME2003_PLUS_NATIVE_GIT_VERSION_MARKERS


def mame2003_plus_command_scoped_makeflags(spec: object) -> str:
    """Derive the exact non-exported MAKEFLAGS value used by the build."""

    if not mame2003_plus_spec_is_well_formed(spec):
        raise PipelineError(
            "MAME 2003-Plus MAKEFLAGS requires its exact reviewed spec"
        )
    return MAME2003_PLUS_COMMAND_SCOPED_MAKEFLAGS


def mame2003_plus_build_shell(
    spec: object,
    source_key: object,
    arch: str,
) -> str:
    """Render the exact command-scoped visible MAME 2003-Plus build."""

    if (
        not mame2003_plus_spec_is_well_formed(spec)
        or source_key != MAME2003_PLUS_CORE_ID
        or arch not in MAME2003_PLUS_BUILD_BEGIN_MARKER
    ):
        raise PipelineError(
            "MAME 2003-Plus build shell requires its exact spec and target"
        )
    makeflags = mame2003_plus_command_scoped_makeflags(spec)
    command = (
        f"MAKEFLAGS={shlex.quote(makeflags)} "
        f"./libretro-build.sh {MAME2003_PLUS_CORE_ID}"
    )
    marker_commands = tuple(
        f"printf '%s\\n' {shlex.quote(marker)}"
        for marker in MAME2003_PLUS_NATIVE_GIT_VERSION_MARKERS
    )
    return "\n".join(
        (
            *marker_commands,
            f"printf '%s\\n' {shlex.quote(MAME2003_PLUS_RECIPE_MARKER)}",
            (
                "printf '%s\\n' "
                + shlex.quote(MAME2003_PLUS_BUILD_BEGIN_MARKER[arch])
            ),
            command,
            (
                "printf '%s\\n' "
                + shlex.quote(MAME2003_PLUS_BUILD_END_MARKER[arch])
            ),
        )
    )


def mame2003_plus_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind promoted evidence to the exact source with no submodules."""

    identity = MAME2003_PLUS_SPEC_IDENTITY
    return bool(
        core_id == MAME2003_PLUS_CORE_ID
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


def mame2003_plus_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
    arch: object,
) -> bool:
    """Require the exact epoch, native version, architecture, and log shape."""

    return bool(
        arch in MAME2003_PLUS_TARGET_CC
        and isinstance(build, dict)
        and source_commit == MAME2003_PLUS_SOURCE_COMMIT
        and mame2003_plus_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": MAME2003_PLUS_GIT_VERSION,
            "source_date_epoch": MAME2003_PLUS_SOURCE_DATE_EPOCH,
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def mame2003_plus_c_only_contract() -> COnlyLogContract:
    """Return MAME 2003-Plus's exact compile/link proof parameters."""

    return COnlyLogContract(
        core_id=MAME2003_PLUS_CORE_ID,
        expected_compile_count=MAME2003_PLUS_EXPECTED_COMPILE_COUNT,
        expected_compile_pair_sha256=(
            MAME2003_PLUS_EXPECTED_COMPILE_PAIR_SHA256
        ),
        expected_compile_invocation_sha256=(
            MAME2003_PLUS_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=MAME2003_PLUS_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=MAME2003_PLUS_BUILD_ARTIFACT_NAME,
        expected_link_options=MAME2003_PLUS_EXPECTED_LINK_OPTIONS,
        source_commit=MAME2003_PLUS_SOURCE_COMMIT,
        source_tree=MAME2003_PLUS_SOURCE_TREE,
        expected_raw_link_object_sha256=(
            MAME2003_PLUS_EXPECTED_LINK_OBJECT_SHA256
        ),
    )


def mame2003_plus_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove MAME 2003-Plus's exact compile and link commands for one arch.

    Uses the shared C-only compile/link proof standard (order-tolerant); the
    former full-log-envelope proof over the exact 1807-command trace, clean
    invocation, source framing, and reviewed diagnostics was dropped in favour
    of that single shared standard.
    """

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        mame2003_plus_c_only_contract(),
    )
