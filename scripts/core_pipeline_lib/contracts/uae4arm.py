"""Exact UAE4ARM (libretro Amiga, armhf-only) mixed-language build-log contract.

uae4arm is an ARM-optimized Amiga core. Its arm64 build fails to assemble the
armv7 inline assembly, so it is an **armhf-only** core (arm64 devices use the
portable puae/puae2021 instead). The armhf build is a mixed C/C++ libretro-super
build (98 C++, 15 C) linked by the C++ driver; the Makefile passes the full
CFLAGS (with duplicated ``-I`` includes) to the link, so the expected link
options mirror that exact multiset. The armhf compile invocation sha256 pins the
exact argv.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


UAE4ARM_CORE_ID = "uae4arm"
UAE4ARM_BUILD_ARTIFACT_NAME = "uae4arm_libretro.so"

UAE4ARM_SOURCE_COMMIT = "dafd48fad7510ebc2f90ebdee8331bbdcf65fd49"
UAE4ARM_SOURCE_TREE = "7d99605e9faecc7c154c30861ebee2a36b9fde18"

UAE4ARM_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-uae4arm.yml",
    "source_url": "https://github.com/libretro/uae4arm-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": UAE4ARM_SOURCE_COMMIT,
    "source_tree": UAE4ARM_SOURCE_TREE,
    "source_key": UAE4ARM_CORE_ID,
    "source_dir": "libretro-uae4arm",
    "output_path": "dist/unix/uae4arm_libretro.so",
    "artifact_name": UAE4ARM_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/uae4arm_libretro.info",
    "metadata_artifact_name": "uae4arm_libretro.info",
    "targets": ["armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the uae4arm core must preserve its exact armhf-only "
    "source, recipe, metadata, and target contract"
)


def uae4arm_spec_is_well_formed(spec: object) -> bool:
    """Require UAE4ARM's exact immutable armhf-only catalog identity."""

    identity = UAE4ARM_SPEC_IDENTITY
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


UAE4ARM_LOG_CONTRACT_ID = "uae4arm-mixed-language-v1"
UAE4ARM_EXPECTED_COMPILE_COUNT = 113
UAE4ARM_EXPECTED_LANGUAGE_COUNTS = {"c": 15, "cxx": 98}
UAE4ARM_EXPECTED_COMPILE_PAIR_SHA256 = (
    "763e040901d2bb4c83c4b9d28d29d61f8ff0dde1151cf19ff0106c3b2ac04510"
)
UAE4ARM_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "armhf": "3b58e03a9cf3a2c0e90020933911e121281c22ebc3a6ac0c63ab73a2eef2f559",
}
UAE4ARM_EXPECTED_LINK_OBJECT_SHA256 = (
    "6d0aa76545dce151b8892caa7a684369e4fcaf41f03969ddf3f226058b05330d"
)
UAE4ARM_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "22e0bff2cd69e75828e437a429225102fb91f2f00454aac59292ab04de08cdda"
)
UAE4ARM_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./libretro/link.T",
    "-I./src",
    "-I./libretro/osdep",
    "-I./src/include",
    "-I./libretro",
    "-I./libretro",
    "-I./libretro/libco",
    "-I./libretro/libco",
    "-I./libretro/core",
    "-I./libretro/core",
    "-I./utils",
    "-I./deps/zlib",
    "-I./libretro/include",
    "-I.",
    "-lpthread",
)

UAE4ARM_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=UAE4ARM_CORE_ID,
    expected_compile_count=UAE4ARM_EXPECTED_COMPILE_COUNT,
    expected_language_counts=UAE4ARM_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=UAE4ARM_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        UAE4ARM_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=UAE4ARM_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=UAE4ARM_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=UAE4ARM_BUILD_ARTIFACT_NAME,
    expected_link_options=UAE4ARM_EXPECTED_LINK_OPTIONS,
    source_commit=UAE4ARM_SOURCE_COMMIT,
    source_tree=UAE4ARM_SOURCE_TREE,
    expected_link_language="cxx",
)


def uae4arm_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove UAE4ARM's exact armhf mixed C/C++ compile set and C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        UAE4ARM_LOG_CONTRACT,
    )


__all__ = [
    "UAE4ARM_BUILD_ARTIFACT_NAME",
    "UAE4ARM_CORE_ID",
    "UAE4ARM_LOG_CONTRACT_ID",
    "UAE4ARM_SOURCE_COMMIT",
    "UAE4ARM_SOURCE_TREE",
    "UAE4ARM_SPEC_IDENTITY",
    "uae4arm_log_proves_contract",
    "uae4arm_spec_is_well_formed",
]
