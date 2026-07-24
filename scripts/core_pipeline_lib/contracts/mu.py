"""Exact Mu (libretro Palm) mixed-language build-log contract.

Mu is a mixed C/C++ libretro-super core (50 C, 4 C++11) whose objects are built
one directory above the libretro wrapper, so the compile outputs carry ``../``
prefixes and the link operands carry ``./../`` prefixes; two explicit semantic
path aliases contain both forms. Every C++ object is free of libstdc++ symbols,
so the C driver performs the final link. The per-architecture compile invocation
sha256 pins each compile (including the commit-derived ``-DGIT_VERSION`` token)
and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


MU_CORE_ID = "mu"
MU_BUILD_ARTIFACT_NAME = "mu_libretro.so"

MU_SOURCE_COMMIT = "de05588fcb1adca6738dc4cf6a2e6e6c447bf2f2"
MU_SOURCE_TREE = "e99eae2df1b0564c808663d6a398d597fb5f42b9"

MU_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mu.yml",
    "source_url": "https://github.com/libretro/Mu.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": MU_SOURCE_COMMIT,
    "source_tree": MU_SOURCE_TREE,
    "source_key": MU_CORE_ID,
    "source_dir": "libretro-mu",
    "output_path": "dist/unix/mu_libretro.so",
    "artifact_name": MU_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/mu_libretro.info",
    "metadata_artifact_name": "mu_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mu core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def mu_spec_is_well_formed(spec: object) -> bool:
    """Require Mu's exact immutable catalog identity."""

    identity = MU_SPEC_IDENTITY
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


MU_LOG_CONTRACT_ID = "mu-mixed-language-v1"
MU_EXPECTED_COMPILE_COUNT = 54
MU_EXPECTED_LANGUAGE_COUNTS = {"c": 50, "cxx": 4}
MU_EXPECTED_COMPILE_PAIR_SHA256 = (
    "8723eff8eb1f6ef0f67176bb924b7e2191e0e5e0da5e532abec65039893f20f1"
)
MU_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "e51ec51a74c4245b45105e8d125c2ec714705f4b63775a105c1ec2ae83516953",
    "armhf": "03bb3cb6844743856901cee55ede7e39c81d1a0544e78dcb65b9e7ef27eb2e7a",
}
MU_EXPECTED_LINK_OBJECT_SHA256 = (
    "4396ab3c0a8dbcf82860e2bbf5da63d598a8edf482e6050877e846a4abee05d8"
)
MU_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "2062057bc8bc08e463b9d46524e584131092a758df01bc0b3e62b25900226c5c"
)
MU_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=build/link.T",
    "-I./../include",
    "-I./libretro-common/include",
    "-lm",
)
MU_SEMANTIC_PATH_ALIASES = (
    ("./../", ""),
    ("../", ""),
)

MU_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MU_CORE_ID,
    expected_compile_count=MU_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MU_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=MU_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=MU_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=MU_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=MU_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=MU_BUILD_ARTIFACT_NAME,
    expected_link_options=MU_EXPECTED_LINK_OPTIONS,
    source_commit=MU_SOURCE_COMMIT,
    source_tree=MU_SOURCE_TREE,
    expected_link_language="c",
    semantic_path_aliases=MU_SEMANTIC_PATH_ALIASES,
)


def mu_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Mu's exact mixed C/C++ compile set and matching C link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        MU_LOG_CONTRACT,
    )


__all__ = [
    "MU_BUILD_ARTIFACT_NAME",
    "MU_CORE_ID",
    "MU_LOG_CONTRACT_ID",
    "MU_SOURCE_COMMIT",
    "MU_SOURCE_TREE",
    "MU_SPEC_IDENTITY",
    "mu_log_proves_contract",
    "mu_spec_is_well_formed",
]
