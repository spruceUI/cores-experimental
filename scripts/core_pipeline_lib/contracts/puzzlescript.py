"""Exact PuzzleScript (libretro pzretro) mixed-language build-log contract.

puzzlescript embeds the QuickJS engine and its libretro glue from five top-level
submodules. Its ``quickjs-ng`` submodule carries an unneeded relative-URL
``test262`` conformance-suite submodule that breaks a recursive fetch, so the
catalog pins ``build.recursive_submodules: false`` (top-level fetch only, still
recorded/pinned). It is a mixed C/C++ build (6 C — the QuickJS core — and 11 C++
— the pzretro glue) linked by the C++ driver from the source root; objects are
named ``<stem>.o`` and the link references them with a ``./`` prefix that the
engine normalizes, so no alias is needed. The per-architecture compile
invocation sha256 pins the exact argv.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


PUZZLESCRIPT_CORE_ID = "puzzlescript"
PUZZLESCRIPT_BUILD_ARTIFACT_NAME = "puzzlescript_libretro.so"

PUZZLESCRIPT_SOURCE_COMMIT = "6d859b47092f585a7ec05804c1d51a1676a06531"
PUZZLESCRIPT_SOURCE_TREE = "5e215b3f00ceba47f14b81c0b67d6a3d879a08af"

PUZZLESCRIPT_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-puzzlescript.yml",
    "source_url": "https://github.com/nwhitehead/pzretro.git",
    "source_requested_ref": "refs/heads/main",
    "source_commit": PUZZLESCRIPT_SOURCE_COMMIT,
    "source_tree": PUZZLESCRIPT_SOURCE_TREE,
    "source_key": PUZZLESCRIPT_CORE_ID,
    "source_dir": "libretro-puzzlescript",
    "output_path": "dist/unix/puzzlescript_libretro.so",
    "artifact_name": PUZZLESCRIPT_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/puzzlescript_libretro.info"
    ),
    "metadata_artifact_name": "puzzlescript_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the puzzlescript core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def puzzlescript_spec_is_well_formed(spec: object) -> bool:
    """Require PuzzleScript's exact immutable catalog identity."""

    identity = PUZZLESCRIPT_SPEC_IDENTITY
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
                "recursive_submodules": False,
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


PUZZLESCRIPT_LOG_CONTRACT_ID = "puzzlescript-mixed-language-v1"
PUZZLESCRIPT_EXPECTED_COMPILE_COUNT = 17
PUZZLESCRIPT_EXPECTED_LANGUAGE_COUNTS = {"c": 6, "cxx": 11}
PUZZLESCRIPT_EXPECTED_COMPILE_PAIR_SHA256 = (
    "a3602fe0964ec65c308681166cff9d3384e99f600b441da72fac73a9ff2f6ffb"
)
PUZZLESCRIPT_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "8dfb9d94ed0c31cc1515443a00fa98025dc3418ee77eca611cf8ba7d781d9dac",
    "armhf": "1862a154902f33876f69392927f45720274a84ad406692aa0532ae402db7215e",
}
PUZZLESCRIPT_EXPECTED_LINK_OBJECT_SHA256 = (
    "c6f37b117f9024a9f69ca9339e68964e8222676cf99113be502deba997a48c87"
)
PUZZLESCRIPT_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "7c1a7fa594d283f3d64cea2747c403dfc36e1343a0c90da9df6431d45dbd4b92"
)
PUZZLESCRIPT_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
    "-lpthread",
    "-ldl",
)

PUZZLESCRIPT_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=PUZZLESCRIPT_CORE_ID,
    expected_compile_count=PUZZLESCRIPT_EXPECTED_COMPILE_COUNT,
    expected_language_counts=PUZZLESCRIPT_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=PUZZLESCRIPT_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        PUZZLESCRIPT_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=PUZZLESCRIPT_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        PUZZLESCRIPT_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=PUZZLESCRIPT_BUILD_ARTIFACT_NAME,
    expected_link_options=PUZZLESCRIPT_EXPECTED_LINK_OPTIONS,
    source_commit=PUZZLESCRIPT_SOURCE_COMMIT,
    source_tree=PUZZLESCRIPT_SOURCE_TREE,
    expected_link_language="cxx",
)


def puzzlescript_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove PuzzleScript's exact mixed C/C++ compile set and C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        PUZZLESCRIPT_LOG_CONTRACT,
    )


__all__ = [
    "PUZZLESCRIPT_BUILD_ARTIFACT_NAME",
    "PUZZLESCRIPT_CORE_ID",
    "PUZZLESCRIPT_LOG_CONTRACT_ID",
    "PUZZLESCRIPT_SOURCE_COMMIT",
    "PUZZLESCRIPT_SOURCE_TREE",
    "PUZZLESCRIPT_SPEC_IDENTITY",
    "puzzlescript_log_proves_contract",
    "puzzlescript_spec_is_well_formed",
]
