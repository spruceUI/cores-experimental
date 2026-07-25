"""Exact ECWolf mixed-language compile/link build-log contract.

ECWolf is a predominantly C++ libretro core with no catalog ``git_version``
derivation. It builds from the ``libretro/`` subdirectory, so object and source
paths are referenced as ``../../<top>/...``; a semantic path alias contains them
for normalization while the sha256 identities still pin the exact raw argv. The
oracle uses the shared mixed-language compile/link proof standard directly:
compiler warnings and notes in the reproducible log are non-compile lines and
are intentionally not constrained.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


ECWOLF_CORE_ID = "ecwolf"
ECWOLF_BUILD_ARTIFACT_NAME = "ecwolf_libretro.so"

ECWOLF_SOURCE_COMMIT = "4731f0075d6c225921b40b341b23971e73dd9dfc"
ECWOLF_SOURCE_TREE = "4e651e299a236ecfbbb4e44427e0087790ff1c64"

ECWOLF_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-ecwolf.yml",
    "source_url": "https://github.com/libretro/ecwolf.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": ECWOLF_SOURCE_COMMIT,
    "source_tree": ECWOLF_SOURCE_TREE,
    "source_key": ECWOLF_CORE_ID,
    "source_dir": "libretro-ecwolf",
    "output_path": "dist/unix/ecwolf_libretro.so",
    "artifact_name": ECWOLF_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/ecwolf_libretro.info",
    "metadata_artifact_name": "ecwolf_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the ecwolf core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def ecwolf_spec_is_well_formed(spec: object) -> bool:
    """Require ECWolf's exact immutable catalog identity."""

    identity = ECWOLF_SPEC_IDENTITY
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
                "submodules": [
                    {"path": "src/libretro/libretro-common", "commit": "996376e36d3f4f56eba202cb96230568628d2583"},
                ],
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


ECWOLF_LOG_CONTRACT_ID = "ecwolf-mixed-language-v1"
ECWOLF_SEMANTIC_PATH_ALIASES = (("../../", ""),)
ECWOLF_EXPECTED_COMPILE_COUNT = 213
ECWOLF_EXPECTED_LANGUAGE_COUNTS = {"c": 79, "cxx": 134}
ECWOLF_EXPECTED_COMPILE_PAIR_SHA256 = (
    "1adb519b4885d91acb02b955a9aca2f27694355db3c5b3ee81090900d9edb9e3"
)
ECWOLF_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "893987f5e705bc12b82363757419862bdbe3b03e1be890914115acd9833442dc",
    "armhf": "beb6ece9f736367bd3c649923af72f2d5fcf606c12cfc4701f91212e1cd9c7b4",
}
ECWOLF_EXPECTED_LINK_OBJECT_SHA256 = (
    "9f98f274df3c5674a231081bfc80eaf2b8e8b82e4da598d83487d4763986d348"
)
ECWOLF_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "03ce25f26277731a183e01b7bc655b6e1adc90d4f8bf06fba4a1fa588203fc72"
)
ECWOLF_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=../../link.T",
    "-Wl,--no-undefined",
    "-lm",
    "-ldl",
    "-lpthread",
)


def ecwolf_mixed_language_contract() -> MixedLanguageLogContract:
    """Return ECWolf's exact mixed-language compile/link proof parameters."""

    return MixedLanguageLogContract(
        core_id=ECWOLF_CORE_ID,
        expected_compile_count=ECWOLF_EXPECTED_COMPILE_COUNT,
        expected_language_counts=ECWOLF_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=ECWOLF_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            ECWOLF_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=ECWOLF_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=ECWOLF_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=ECWOLF_BUILD_ARTIFACT_NAME,
        expected_link_options=ECWOLF_EXPECTED_LINK_OPTIONS,
        source_commit=ECWOLF_SOURCE_COMMIT,
        source_tree=ECWOLF_SOURCE_TREE,
        semantic_path_aliases=ECWOLF_SEMANTIC_PATH_ALIASES,
        expected_link_language="cxx",
    )


def ecwolf_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove ECWolf's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        ecwolf_mixed_language_contract(),
    )


__all__ = [
    "ECWOLF_BUILD_ARTIFACT_NAME",
    "ECWOLF_CORE_ID",
    "ECWOLF_EXPECTED_COMPILE_COUNT",
    "ECWOLF_EXPECTED_LANGUAGE_COUNTS",
    "ECWOLF_LOG_CONTRACT_ID",
    "ECWOLF_SEMANTIC_PATH_ALIASES",
    "ECWOLF_SOURCE_COMMIT",
    "ECWOLF_SOURCE_TREE",
    "ECWOLF_SPEC_IDENTITY",
    "ecwolf_log_proves_contract",
    "ecwolf_mixed_language_contract",
    "ecwolf_spec_is_well_formed",
]
