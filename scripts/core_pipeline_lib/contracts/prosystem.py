"""Exact ProSystem C-only build-log contract."""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


PROSYSTEM_CORE_ID = "prosystem"
PROSYSTEM_EXPECTED_COMPILE_COUNT = 32
PROSYSTEM_EXPECTED_LANGUAGE_COUNTS = {"c": 32}
PROSYSTEM_EXPECTED_COMPILE_PAIR_SHA256 = (
    "152a24ab44adf5d5f5552eb3eb173fbbb0ec93b5c392efb3931cd28c1428aca3"
)
PROSYSTEM_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "e330fb5cbcab579e5a78197df1d29d6605e74af8020e6055aeae307aebeedee3",
    "armhf": "86cd25441a3b2af46dc74beaaaec14e946ed13914d766c9845b9c783603eb9eb",
}
PROSYSTEM_EXPECTED_LINK_OBJECT_SHA256 = (
    "db0a2ede29bcbcb19169a9c52827a837382c887bc46187c12cfbed571f1715c7"
)
PROSYSTEM_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "f9bf0dcb6d10f659b710fb63c7e6e6e7af829c4a687f693598d596f66fce8038"
)
PROSYSTEM_BUILD_ARTIFACT_NAME = "prosystem_libretro.so"
PROSYSTEM_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
    "-lm",
    "-lm",
)
PROSYSTEM_SEMANTIC_PATH_ALIASES = (
    ("core/../bupboop/", "bupboop/"),
    ("core/../libretro-common/", "libretro-common/"),
)
PROSYSTEM_EXPECTED_WARNING_LINE = (
    "core/ProSystem.c:272:10: warning: value computed is not used "
    "[-Wunused-value]"
)
PROSYSTEM_EXPECTED_WARNING_BLOCK = "\n".join(
    (
        "core/ProSystem.c: In function 'prosystem_Load':",
        PROSYSTEM_EXPECTED_WARNING_LINE,
        "  272 |    buffer[offset++];",
        "      |    ~~~~~~^~~~~~~~~~",
    )
)
PROSYSTEM_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-prosystem.yml",
    "source_url": "https://github.com/libretro/prosystem-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "363b6dfbd3e240762e022c2b4897b4fe55722be3",
    "source_tree": "197be1b53019d95ed06658c2a801d0812ef76cf2",
    "source_key": PROSYSTEM_CORE_ID,
    "source_dir": "libretro-prosystem",
    "output_path": "dist/unix/prosystem_libretro.so",
    "artifact_name": PROSYSTEM_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/prosystem_libretro.info",
    "metadata_artifact_name": "prosystem_libretro.info",
    "targets": ["arm64", "armhf"],
    "git_version": {
        "derivation": "hyphen-short7-v1",
        "value": "-363b6df",
    },
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the prosystem core must preserve its exact injected "
    "version, source, recipe, metadata, and target contract"
)


def prosystem_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable ProSystem catalog identity."""

    identity = PROSYSTEM_GIT_VERSION_SPEC_IDENTITY
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
                "git_version": identity["git_version"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


PROSYSTEM_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=PROSYSTEM_CORE_ID,
    expected_compile_count=PROSYSTEM_EXPECTED_COMPILE_COUNT,
    expected_language_counts=PROSYSTEM_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=PROSYSTEM_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        PROSYSTEM_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=PROSYSTEM_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        PROSYSTEM_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=PROSYSTEM_BUILD_ARTIFACT_NAME,
    expected_link_options=PROSYSTEM_EXPECTED_LINK_OPTIONS,
    source_commit=PROSYSTEM_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=PROSYSTEM_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_link_language="c",
    semantic_path_aliases=PROSYSTEM_SEMANTIC_PATH_ALIASES,
)


def prosystem_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove ProSystem's exact C compile, link, and reviewed warning sets."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    if any(
        marker in lowered_log
        for marker in ("error:", "fatal:", "undefined reference")
    ):
        return False
    warning_lines = [
        line
        for line in build_log_text.splitlines()
        if "warning:" in line.casefold()
    ]
    if (
        warning_lines != [PROSYSTEM_EXPECTED_WARNING_LINE]
        or build_log_text.count(PROSYSTEM_EXPECTED_WARNING_BLOCK) != 1
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        PROSYSTEM_LOG_CONTRACT,
    )
