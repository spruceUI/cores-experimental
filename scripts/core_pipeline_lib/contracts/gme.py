"""Exact Game Music Emu (libretro) mixed-language build-log contract.

gme is a mixed C/C++ libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its 78 translation units (46 C++, 32 C)
are each compiled once and linked by the C++ driver; the per-architecture
compile invocation sha256 and the exact link object set pin the build.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


GME_CORE_ID = "gme"
GME_BUILD_ARTIFACT_NAME = "gme_libretro.so"

GME_SOURCE_COMMIT = "818629a9fbb9f99bd9c585395318834ae5c6434e"
GME_SOURCE_TREE = "dd10fdad6ccd383a7fa163ac76ad3d952e9842a5"

GME_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gme.yml",
    "source_url": "https://github.com/libretro/libretro-gme.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": GME_SOURCE_COMMIT,
    "source_tree": GME_SOURCE_TREE,
    "source_key": GME_CORE_ID,
    "source_dir": "libretro-gme",
    "output_path": "dist/unix/gme_libretro.so",
    "artifact_name": GME_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/gme_libretro.info",
    "metadata_artifact_name": "gme_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the gme core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def gme_spec_is_well_formed(spec: object) -> bool:
    """Require gme's exact immutable catalog identity."""

    identity = GME_SPEC_IDENTITY
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


GME_LOG_CONTRACT_ID = "gme-mixed-language-v1"
GME_EXPECTED_COMPILE_COUNT = 78
GME_EXPECTED_LANGUAGE_COUNTS = {"cxx": 46, "c": 32}
GME_EXPECTED_COMPILE_PAIR_SHA256 = (
    "fb52042ecf4807b145ba3be3cad19dcf5c190c30659fb09dbcd0f12c59d3feda"
)
GME_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "0eca468fdbea1379fd2ead3b60ddb94b62d009135ac4e42432f0c7119fc9c98e",
    "armhf": "ccb874b40896b3dc2aefdc90ae2cdbb31acef6304c4f477af6b619b741067224",
}
GME_EXPECTED_LINK_OBJECT_SHA256 = (
    "bdb3c74282f42ab66e97439b381afd2b5bd6d37ec837da63fece0992797f6fa0"
)
GME_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "f81075601f4cd5e96a3096371ed20c2167654d0b606284ee2b70d21a78974185"
)
GME_EXPECTED_LINK_OPTIONS = ("-shared",)

GME_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=GME_CORE_ID,
    expected_compile_count=GME_EXPECTED_COMPILE_COUNT,
    expected_language_counts=GME_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=GME_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        GME_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=GME_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=GME_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=GME_BUILD_ARTIFACT_NAME,
    expected_link_options=GME_EXPECTED_LINK_OPTIONS,
    source_commit=GME_SOURCE_COMMIT,
    source_tree=GME_SOURCE_TREE,
    expected_link_language="cxx",
)


def gme_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove gme's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        GME_LOG_CONTRACT,
    )


__all__ = [
    "GME_BUILD_ARTIFACT_NAME",
    "GME_CORE_ID",
    "GME_LOG_CONTRACT_ID",
    "GME_SOURCE_COMMIT",
    "GME_SOURCE_TREE",
    "GME_SPEC_IDENTITY",
    "gme_log_proves_contract",
    "gme_spec_is_well_formed",
]
