"""Exact NP2kai (libretro PC-98) mixed-language build-log contract.

np2kai is a libretro-super core built from the ``sdl`` subdirectory with
``Makefile.libretro``; its objects therefore live one directory up
(``../sound/…``, ``../sdl/…``), so a single ``("../","")`` alias contains them.
It is a mixed C/C++ build (344 C, 7 C++ — the fmgen FM synth) linked by the C++
driver. Commit-derived ``-DNP2KAI_GIT_TAG``/``-DNP2KAI_GIT_HASH`` are pinned by
the per-arch compile invocation sha256; the link runs verbose (``-v``), so its
internal ``collect2`` line appears in the log but never names the target
compiler and is ignored by the proof.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


NP2KAI_CORE_ID = "np2kai"
NP2KAI_BUILD_ARTIFACT_NAME = "np2kai_libretro.so"

NP2KAI_SOURCE_COMMIT = "54ec39f50d197cc02909cd4fd2a8591bb38651b0"
NP2KAI_SOURCE_TREE = "dfb9119f775cdba8a5b0eed464ddfe04dffd7c1a"

NP2KAI_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-np2kai.yml",
    "source_url": "https://github.com/libretro/NP2kai.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": NP2KAI_SOURCE_COMMIT,
    "source_tree": NP2KAI_SOURCE_TREE,
    "source_key": NP2KAI_CORE_ID,
    "source_dir": "libretro-np2kai",
    "output_path": "dist/unix/np2kai_libretro.so",
    "artifact_name": NP2KAI_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/np2kai_libretro.info",
    "metadata_artifact_name": "np2kai_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the np2kai core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def np2kai_spec_is_well_formed(spec: object) -> bool:
    """Require NP2kai's exact immutable catalog identity."""

    identity = NP2KAI_SPEC_IDENTITY
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


NP2KAI_LOG_CONTRACT_ID = "np2kai-mixed-language-v1"
NP2KAI_EXPECTED_COMPILE_COUNT = 351
NP2KAI_EXPECTED_LANGUAGE_COUNTS = {"c": 344, "cxx": 7}
NP2KAI_EXPECTED_COMPILE_PAIR_SHA256 = (
    "a6f3158dd5f458aaf5dafc400e75eae10e54bbc42b4532ddea2a5d06d8ef75cb"
)
NP2KAI_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "2e3d23b28e14df8954f10ba12fba3c11a3ec5038da8c0f76c4657aad0374c943",
    "armhf": "3905b32da44fb3c195b8d8d1a5610e5be3dbdc557edd763a77b30c8e4973b9fc",
}
NP2KAI_EXPECTED_LINK_OBJECT_SHA256 = (
    "d00ac7de711a165ed1a570754e19d98084af0d09a7cda07fd29454953f6b1b45"
)
NP2KAI_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "7d78cd36fa2835c6a9d974b58f948b02a84d712ab4fb5443732c9b9dcccb7b34"
)
NP2KAI_SEMANTIC_PATH_ALIASES = (("../", ""),)
NP2KAI_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-fPIC",
    "-lm",
    "-lpthread",
    "-v",
)

NP2KAI_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=NP2KAI_CORE_ID,
    expected_compile_count=NP2KAI_EXPECTED_COMPILE_COUNT,
    expected_language_counts=NP2KAI_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=NP2KAI_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        NP2KAI_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=NP2KAI_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=NP2KAI_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=NP2KAI_BUILD_ARTIFACT_NAME,
    expected_link_options=NP2KAI_EXPECTED_LINK_OPTIONS,
    source_commit=NP2KAI_SOURCE_COMMIT,
    source_tree=NP2KAI_SOURCE_TREE,
    semantic_path_aliases=NP2KAI_SEMANTIC_PATH_ALIASES,
    expected_link_language="cxx",
)


def np2kai_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove NP2kai's exact mixed C/C++ compile set and C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        NP2KAI_LOG_CONTRACT,
    )


__all__ = [
    "NP2KAI_BUILD_ARTIFACT_NAME",
    "NP2KAI_CORE_ID",
    "NP2KAI_LOG_CONTRACT_ID",
    "NP2KAI_SOURCE_COMMIT",
    "NP2KAI_SOURCE_TREE",
    "NP2KAI_SPEC_IDENTITY",
    "np2kai_log_proves_contract",
    "np2kai_spec_is_well_formed",
]
