"""Exact Daphne (libretro laserdisc) mixed-language build-log contract.

daphne is a mixed C/C++ libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its 178 translation units (95 C++,
83 C) are each compiled once with a commit-derived ``-DGIT_VERSION`` token and
linked by the C++ driver; the per-architecture compile invocation sha256 pins
the exact argv and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


DAPHNE_CORE_ID = "daphne"
DAPHNE_BUILD_ARTIFACT_NAME = "daphne_libretro.so"

DAPHNE_SOURCE_COMMIT = "6f1695dd1f376060666eec0a416ff56bb6c9cccc"
DAPHNE_SOURCE_TREE = "99813647ee65593613181fcec730660f417035a3"

DAPHNE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-daphne.yml",
    "source_url": "https://github.com/libretro/daphne.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": DAPHNE_SOURCE_COMMIT,
    "source_tree": DAPHNE_SOURCE_TREE,
    "source_key": DAPHNE_CORE_ID,
    "source_dir": "libretro-daphne",
    "output_path": "dist/unix/daphne_libretro.so",
    "artifact_name": DAPHNE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/daphne_libretro.info",
    "metadata_artifact_name": "daphne_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the daphne core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def daphne_spec_is_well_formed(spec: object) -> bool:
    """Require Daphne's exact immutable catalog identity."""

    identity = DAPHNE_SPEC_IDENTITY
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


DAPHNE_LOG_CONTRACT_ID = "daphne-mixed-language-v1"
DAPHNE_EXPECTED_COMPILE_COUNT = 178
DAPHNE_EXPECTED_LANGUAGE_COUNTS = {"c": 83, "cxx": 95}
DAPHNE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e48d963c0553bf0b0f06b94838fbfb43d81853a3f3ec4cc7e1f27c53e58892b9"
)
DAPHNE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "31656c1c7a35fa6cc818e853b104c277cf982e90a9e88e2fe2b4e4c8cc28b8e3",
    "armhf": "231dc3191e068afd6dcaa133d90f761dac52001074c0483f1513b65c192566f9",
}
DAPHNE_EXPECTED_LINK_OBJECT_SHA256 = (
    "85ff125d66c1aa53689c21d0ceb792863138ec7e634f180e11c2a09d0a49720e"
)
DAPHNE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "87a795399fb203e547283aedf6c43ec9cf39624ca6c8cce58d06207dffd16c65"
)
DAPHNE_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-Wl,--no-undefined",
    "-lpthread",
    "-ldl",
    "-lm",
)

DAPHNE_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=DAPHNE_CORE_ID,
    expected_compile_count=DAPHNE_EXPECTED_COMPILE_COUNT,
    expected_language_counts=DAPHNE_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=DAPHNE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=DAPHNE_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=DAPHNE_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=DAPHNE_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=DAPHNE_BUILD_ARTIFACT_NAME,
    expected_link_options=DAPHNE_EXPECTED_LINK_OPTIONS,
    source_commit=DAPHNE_SOURCE_COMMIT,
    source_tree=DAPHNE_SOURCE_TREE,
    expected_link_language="cxx",
)


def daphne_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Daphne's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        DAPHNE_LOG_CONTRACT,
    )


__all__ = [
    "DAPHNE_BUILD_ARTIFACT_NAME",
    "DAPHNE_CORE_ID",
    "DAPHNE_LOG_CONTRACT_ID",
    "DAPHNE_SOURCE_COMMIT",
    "DAPHNE_SOURCE_TREE",
    "DAPHNE_SPEC_IDENTITY",
    "daphne_log_proves_contract",
    "daphne_spec_is_well_formed",
]
