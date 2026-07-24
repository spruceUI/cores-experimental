"""Exact X1 (libretro Sharp X1 / xmil) mixed-language build-log contract.

x1 is a libretro-super core whose 102 translation units are all C but are linked
by the C++ driver, and whose Makefile runs from a subdirectory so every object
is written one directory up (``../``); a single semantic path alias contains
that. The per-architecture compile invocation sha256 pins the exact argv and the
link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


X1_CORE_ID = "x1"
X1_BUILD_ARTIFACT_NAME = "x1_libretro.so"

X1_SOURCE_COMMIT = "3e7960a433c3bca820f8b8f5511a2b92bd666829"
X1_SOURCE_TREE = "dc2993fae86d48789557a4f10295243ea40f3d75"

X1_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-x1.yml",
    "source_url": "https://github.com/libretro/xmil-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": X1_SOURCE_COMMIT,
    "source_tree": X1_SOURCE_TREE,
    "source_key": X1_CORE_ID,
    "source_dir": "libretro-x1",
    "output_path": "dist/unix/x1_libretro.so",
    "artifact_name": X1_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/x1_libretro.info",
    "metadata_artifact_name": "x1_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the x1 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def x1_spec_is_well_formed(spec: object) -> bool:
    """Require X1's exact immutable catalog identity."""

    identity = X1_SPEC_IDENTITY
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


X1_LOG_CONTRACT_ID = "x1-mixed-language-v1"
X1_EXPECTED_COMPILE_COUNT = 102
X1_EXPECTED_LANGUAGE_COUNTS = {"c": 102}
X1_EXPECTED_COMPILE_PAIR_SHA256 = (
    "68a9bf94eb83410e7d141dd5c56116bebdf135fb0dcfe008eb07e5f0487ee4ee"
)
X1_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "c16d434c4b7c21eba5451b00221bda64f6c8980309013ce83bf58355c056b771",
    "armhf": "7c6a1952cd85be9c135425ca8e5c80ef9a64a59887494a6b140df9882174e1c7",
}
X1_EXPECTED_LINK_OBJECT_SHA256 = (
    "7a82ad1c18f8bf592cd0394ede2c61c978895695037099bdd4754b39942d42f1"
)
X1_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "3b2361a4fc432d67e4161e83901cca69170f33812091e282273d07660e7723de"
)
X1_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
X1_SEMANTIC_PATH_ALIASES = (("../", ""),)

X1_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=X1_CORE_ID,
    expected_compile_count=X1_EXPECTED_COMPILE_COUNT,
    expected_language_counts=X1_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=X1_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=X1_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=X1_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=X1_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=X1_BUILD_ARTIFACT_NAME,
    expected_link_options=X1_EXPECTED_LINK_OPTIONS,
    source_commit=X1_SOURCE_COMMIT,
    source_tree=X1_SOURCE_TREE,
    expected_link_language="cxx",
    semantic_path_aliases=X1_SEMANTIC_PATH_ALIASES,
)


def x1_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove X1's exact all-C compile set and matching C++-driver link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        X1_LOG_CONTRACT,
    )


__all__ = [
    "X1_BUILD_ARTIFACT_NAME",
    "X1_CORE_ID",
    "X1_LOG_CONTRACT_ID",
    "X1_SOURCE_COMMIT",
    "X1_SOURCE_TREE",
    "X1_SPEC_IDENTITY",
    "x1_log_proves_contract",
    "x1_spec_is_well_formed",
]
