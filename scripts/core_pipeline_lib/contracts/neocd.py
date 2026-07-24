"""Exact NeoCD mixed-language compile/link build-log contract.

NeoCD is a mixed C/C++ libretro core with no catalog ``git_version``; it builds
from the source root (objects and the version script are referenced without a
``../../`` prefix, so no semantic path alias is needed). ARMHF carries four
HWCAP2 compile definitions that neutralize CPU-feature probes on the A30
sysroot; they are part of the exact ARMHF compile argv the oracle pins. The
oracle uses the shared mixed-language compile/link proof standard directly.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


NEOCD_CORE_ID = "neocd"
NEOCD_BUILD_ARTIFACT_NAME = "neocd_libretro.so"

NEOCD_SOURCE_COMMIT = "9e9ad181bed60f84f9cff02c03617b41e8a31cfe"
NEOCD_SOURCE_TREE = "c82440c78b368bbd4c58122d796e4d9beb40c22a"

# The A30 armhf sysroot predates these asm/hwcap.h names; defining them to zero
# supplies the missing header vocabulary without claiming any CPU feature.
NEOCD_ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=0",
    "HWCAP2_CRC32=0",
    "HWCAP2_SHA1=0",
    "HWCAP2_SHA2=0",
]

NEOCD_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-neocd.yml",
    "source_url": "https://github.com/libretro/neocd_libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": NEOCD_SOURCE_COMMIT,
    "source_tree": NEOCD_SOURCE_TREE,
    "source_key": NEOCD_CORE_ID,
    "source_dir": "libretro-neocd",
    "output_path": "dist/unix/neocd_libretro.so",
    "artifact_name": NEOCD_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/neocd_libretro.info",
    "metadata_artifact_name": "neocd_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the neocd core must preserve its exact source, "
    "recipe, compile-definitions, metadata, and target "
    "contract"
)


def neocd_spec_is_well_formed(spec: object) -> bool:
    """Require NeoCD's exact immutable catalog identity."""

    identity = NEOCD_SPEC_IDENTITY
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
                "compile_definitions": {
                    "armhf": NEOCD_ARMHF_COMPILE_DEFINITIONS,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


NEOCD_LOG_CONTRACT_ID = "neocd-mixed-language-v1"
NEOCD_EXPECTED_COMPILE_COUNT = 129
NEOCD_EXPECTED_LANGUAGE_COUNTS = {"c": 86, "cxx": 43}
NEOCD_EXPECTED_COMPILE_PAIR_SHA256 = (
    "abce90e07d99e40b45f58ef8ba41b3cbb172ec565c9f8d0577446cf4342c25c5"
)
NEOCD_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "3e39917035daa98e489aa1e73e5d797c5590413479f9112d775fc783ee9b8422",
    "armhf": "3fba165f70d21d65b2c4c103fa566e34e8ec488c3d47dd8d1e70aeaff33344d8",
}
NEOCD_EXPECTED_LINK_OBJECT_SHA256 = (
    "4f02157ebe20115ea36f1f530d6feeb6d41504b8d9c495231fd9ace641bfe737"
)
NEOCD_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9201185d8b41c1e69a390a04856dc3db49015699ad6407c1951c00ea00323d40"
)
NEOCD_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./link.T",
    "-Wl,--no-undefined",
    "-lpthread",
    "-lm",
)


def neocd_mixed_language_contract() -> MixedLanguageLogContract:
    """Return NeoCD's exact mixed-language compile/link proof parameters."""

    return MixedLanguageLogContract(
        core_id=NEOCD_CORE_ID,
        expected_compile_count=NEOCD_EXPECTED_COMPILE_COUNT,
        expected_language_counts=NEOCD_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=NEOCD_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            NEOCD_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=NEOCD_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=NEOCD_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=NEOCD_BUILD_ARTIFACT_NAME,
        expected_link_options=NEOCD_EXPECTED_LINK_OPTIONS,
        source_commit=NEOCD_SOURCE_COMMIT,
        source_tree=NEOCD_SOURCE_TREE,
        semantic_path_aliases=(),
        expected_link_language="cxx",
    )


def neocd_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove NeoCD's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        neocd_mixed_language_contract(),
    )


__all__ = [
    "NEOCD_ARMHF_COMPILE_DEFINITIONS",
    "NEOCD_BUILD_ARTIFACT_NAME",
    "NEOCD_CORE_ID",
    "NEOCD_EXPECTED_COMPILE_COUNT",
    "NEOCD_EXPECTED_LANGUAGE_COUNTS",
    "NEOCD_LOG_CONTRACT_ID",
    "NEOCD_SOURCE_COMMIT",
    "NEOCD_SOURCE_TREE",
    "NEOCD_SPEC_IDENTITY",
    "neocd_log_proves_contract",
    "neocd_mixed_language_contract",
    "neocd_spec_is_well_formed",
]
