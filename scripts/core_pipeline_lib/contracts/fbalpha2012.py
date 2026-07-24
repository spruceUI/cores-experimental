"""Exact FB Alpha 2012 (libretro arcade) mixed-language build-log contract.

fbalpha2012 is a large mixed C/C++ libretro-super core built from the source
root with no ``../../`` object prefixes and no CMake. Its 524 translation units
(464 C++, 60 C) are each compiled once with a commit-derived ``-DGIT_VERSION``
token and linked by the C++ driver; the per-architecture compile invocation
sha256 pins the exact argv and the link references precisely the compiled
object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


FBALPHA2012_CORE_ID = "fbalpha2012"
FBALPHA2012_BUILD_ARTIFACT_NAME = "fbalpha2012_libretro.so"

FBALPHA2012_SOURCE_COMMIT = "95fa35582b1ca7ce68de3313615794c8c9d8d7c0"
FBALPHA2012_SOURCE_TREE = "5547237bb6746764ca692e765cbe737339f65364"

FBALPHA2012_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-fbalpha2012.yml",
    "source_url": "https://github.com/libretro/fbalpha2012.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": FBALPHA2012_SOURCE_COMMIT,
    "source_tree": FBALPHA2012_SOURCE_TREE,
    "source_key": FBALPHA2012_CORE_ID,
    "source_dir": "libretro-fbalpha2012",
    "output_path": "dist/unix/fbalpha2012_libretro.so",
    "artifact_name": FBALPHA2012_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/fbalpha2012_libretro.info"
    ),
    "metadata_artifact_name": "fbalpha2012_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the fbalpha2012 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


FBALPHA2012_SORT_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/fbalpha2012/makefile-sort-wildcard-sources.patch",
    "patch_sha256": (
        "9dbe1009ffb89b8eb502aab8bd42b7220622c8c56633c60f1a63473ef036de8c"
    ),
    "source_path": "svn-current/trunk/makefile.libretro",
    "preimage_sha256": (
        "166aa6cedbbd84c7daa378a9e4f6e135183590644bb9e0014f5063718dfc7e45"
    ),
    "postimage_sha256": (
        "cd53fdeae5bd23b26f348c4cd0d2b64f5d3b2e8695a976950ae620e41310e349"
    ),
}


def fbalpha2012_spec_is_well_formed(spec: object) -> bool:
    """Require FB Alpha 2012's exact immutable catalog identity."""

    identity = FBALPHA2012_SPEC_IDENTITY
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
                "overlays": {
                    "arm64": [dict(FBALPHA2012_SORT_OVERLAY)],
                    "armhf": [dict(FBALPHA2012_SORT_OVERLAY)],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


FBALPHA2012_LOG_CONTRACT_ID = "fbalpha2012-mixed-language-v1"
FBALPHA2012_EXPECTED_COMPILE_COUNT = 524
FBALPHA2012_EXPECTED_LANGUAGE_COUNTS = {"c": 60, "cxx": 464}
FBALPHA2012_EXPECTED_COMPILE_PAIR_SHA256 = (
    "c6d2ef62c0524c5323f9a952f7f777ff284add688f8be3aad787143af5c076ec"
)
FBALPHA2012_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "337482dc9b3c88f3d1f769263b295135798cd3117aca36b2156f8b58aa6bd39c",
    "armhf": "15b5461102fa8b24e5bad2685438a034e727800c147097ecbd44bd124a54d81d",
}
FBALPHA2012_EXPECTED_LINK_OBJECT_SHA256 = (
    "1e4932eb1ae3a8eba31d2106c7db87c9ef04e57e4823cfe2cbb2ff3aa603c2e4"
)
FBALPHA2012_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "1e4932eb1ae3a8eba31d2106c7db87c9ef04e57e4823cfe2cbb2ff3aa603c2e4"
)
FBALPHA2012_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-no-undefined",
    "-Wl,--version-script=src/burner/libretro/link.T",
    "-fPIC",
)

FBALPHA2012_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=FBALPHA2012_CORE_ID,
    expected_compile_count=FBALPHA2012_EXPECTED_COMPILE_COUNT,
    expected_language_counts=FBALPHA2012_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=FBALPHA2012_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        FBALPHA2012_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=FBALPHA2012_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        FBALPHA2012_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=FBALPHA2012_BUILD_ARTIFACT_NAME,
    expected_link_options=FBALPHA2012_EXPECTED_LINK_OPTIONS,
    source_commit=FBALPHA2012_SOURCE_COMMIT,
    source_tree=FBALPHA2012_SOURCE_TREE,
    expected_link_language="cxx",
)


def fbalpha2012_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove FB Alpha 2012's exact mixed C/C++ compile set and C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FBALPHA2012_LOG_CONTRACT,
    )


__all__ = [
    "FBALPHA2012_BUILD_ARTIFACT_NAME",
    "FBALPHA2012_CORE_ID",
    "FBALPHA2012_LOG_CONTRACT_ID",
    "FBALPHA2012_SOURCE_COMMIT",
    "FBALPHA2012_SOURCE_TREE",
    "FBALPHA2012_SPEC_IDENTITY",
    "fbalpha2012_log_proves_contract",
    "fbalpha2012_spec_is_well_formed",
]
