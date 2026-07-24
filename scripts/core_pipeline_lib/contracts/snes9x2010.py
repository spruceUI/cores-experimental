"""Exact Snes9x 2010 C-only build-log contract.

Snes9x 2010 is a C-only libretro-super core built from the source root (no
``../../`` object prefixes, so no semantic path alias). Its Makefile embeds a
commit-derived ``GIT_VERSION`` on every compile; the per-architecture compile
invocation sha256 pins that exact token, so no separate version guard is needed.
The link is a C driver with a version script and ``-flto``.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


SNES9X2010_CORE_ID = "snes9x2010"
SNES9X2010_BUILD_ARTIFACT_NAME = "snes9x2010_libretro.so"

SNES9X2010_SOURCE_COMMIT = "33077919157b990578011d2cce462e58c9e5c985"
SNES9X2010_SOURCE_TREE = "b1ce4512418a0629442c9dad0f1341600c6a6b43"

SNES9X2010_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-snes9x2010.yml",
    "source_url": "https://github.com/libretro/snes9x2010.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": SNES9X2010_SOURCE_COMMIT,
    "source_tree": SNES9X2010_SOURCE_TREE,
    "source_key": SNES9X2010_CORE_ID,
    "source_dir": "libretro-snes9x2010",
    "output_path": "dist/unix/snes9x2010_libretro.so",
    "artifact_name": SNES9X2010_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/snes9x2010_libretro.info"
    ),
    "metadata_artifact_name": "snes9x2010_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the snes9x2010 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def snes9x2010_spec_is_well_formed(spec: object) -> bool:
    """Require Snes9x 2010's exact immutable catalog identity."""

    identity = SNES9X2010_SPEC_IDENTITY
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


SNES9X2010_LOG_CONTRACT_ID = "snes9x2010-c-only-v1"
SNES9X2010_EXPECTED_COMPILE_COUNT = 61
SNES9X2010_EXPECTED_COMPILE_PAIR_SHA256 = (
    "9edc9c0158fdd13faa2ad774d14911f3644c439a768a6c3ea2fd51cd17e395bb"
)
SNES9X2010_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "3ed5077056ae05ad25222cae7b5332fc5b11aa291a35a73abd13d99b6f1d3831",
    "armhf": "2d8426dcef431485a833cb48335db3de2da5f9dda55539ea2b4789859c2a2708",
}
SNES9X2010_EXPECTED_LINK_OBJECT_SHA256 = (
    "3ba4260a4653a2fc11daf67622c9a2b900d7ecbf62ce578c69a11cd80c9ac0bc"
)
SNES9X2010_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "d6e9c4276fe956fb97365f75f3753d03df011e8569ad9f214109be5150f7518b"
)
SNES9X2010_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=libretro/link.T",
    "-flto",
)

SNES9X2010_LOG_CONTRACT = COnlyLogContract(
    core_id=SNES9X2010_CORE_ID,
    expected_compile_count=SNES9X2010_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=SNES9X2010_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        SNES9X2010_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=SNES9X2010_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=SNES9X2010_BUILD_ARTIFACT_NAME,
    expected_link_options=SNES9X2010_EXPECTED_LINK_OPTIONS,
    source_commit=SNES9X2010_SOURCE_COMMIT,
    source_tree=SNES9X2010_SOURCE_TREE,
    expected_raw_link_object_sha256=SNES9X2010_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def snes9x2010_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Snes9x 2010's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        SNES9X2010_LOG_CONTRACT,
    )


__all__ = [
    "SNES9X2010_BUILD_ARTIFACT_NAME",
    "SNES9X2010_CORE_ID",
    "SNES9X2010_LOG_CONTRACT_ID",
    "SNES9X2010_SOURCE_COMMIT",
    "SNES9X2010_SOURCE_TREE",
    "SNES9X2010_SPEC_IDENTITY",
    "snes9x2010_log_proves_contract",
    "snes9x2010_spec_is_well_formed",
]
