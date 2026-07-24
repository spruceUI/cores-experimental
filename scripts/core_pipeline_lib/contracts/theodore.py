"""Exact Theodore (libretro Thomson MO/TO) C-only build-log contract.

Theodore is a C-only libretro-super core built from the source root (upstream
Zlika/theodore) with no ``../../`` object prefixes and no CMake. Each of its 15
translation units is compiled by the C driver with a commit-derived
``-DGIT_VERSION`` (``git describe``) token; the per-architecture compile
invocation sha256 pins that exact token and the link references precisely the
compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


THEODORE_CORE_ID = "theodore"
THEODORE_BUILD_ARTIFACT_NAME = "theodore_libretro.so"

THEODORE_SOURCE_COMMIT = "121ae2513d3ee29f0aaf765a64dc086d57e7a4c7"
THEODORE_SOURCE_TREE = "431edd6ada0b1dc0ff148fa57afdf0d9d6da1260"

THEODORE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-theodore.yml",
    "source_url": "https://github.com/Zlika/theodore.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": THEODORE_SOURCE_COMMIT,
    "source_tree": THEODORE_SOURCE_TREE,
    "source_key": THEODORE_CORE_ID,
    "source_dir": "libretro-theodore",
    "output_path": "dist/unix/theodore_libretro.so",
    "artifact_name": THEODORE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/theodore_libretro.info"
    ),
    "metadata_artifact_name": "theodore_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the theodore core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def theodore_spec_is_well_formed(spec: object) -> bool:
    """Require Theodore's exact immutable catalog identity."""

    identity = THEODORE_SPEC_IDENTITY
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


THEODORE_LOG_CONTRACT_ID = "theodore-c-only-v1"
THEODORE_EXPECTED_COMPILE_COUNT = 15
THEODORE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "1d58f95fceb7a093b489bbaddb446e3cd4828f2b73f3284391e9ffa280540f7f"
)
THEODORE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "815c33f4d04efcca9acf27ae9a22f5aafdc2d2d337f5bfef5a52c2f6e62f9590",
    "armhf": "4901f9eff9493d41c4b6b47f4bdd76e35952e7621b6aece408b3c6d2d3204c76",
}
THEODORE_EXPECTED_LINK_OBJECT_SHA256 = (
    "46ac12c23dade9898ae375b4a9c41d0e28f6e661f19c1a284d3d91c157af5715"
)
THEODORE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "e79bad77203cea2f849bb05089ffe233506aece0b4430d7cce09f6737a64e166"
)
THEODORE_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
)

THEODORE_LOG_CONTRACT = COnlyLogContract(
    core_id=THEODORE_CORE_ID,
    expected_compile_count=THEODORE_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=THEODORE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        THEODORE_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=THEODORE_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=THEODORE_BUILD_ARTIFACT_NAME,
    expected_link_options=THEODORE_EXPECTED_LINK_OPTIONS,
    source_commit=THEODORE_SOURCE_COMMIT,
    source_tree=THEODORE_SOURCE_TREE,
    expected_raw_link_object_sha256=THEODORE_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def theodore_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Theodore's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        THEODORE_LOG_CONTRACT,
    )


__all__ = [
    "THEODORE_BUILD_ARTIFACT_NAME",
    "THEODORE_CORE_ID",
    "THEODORE_LOG_CONTRACT_ID",
    "THEODORE_SOURCE_COMMIT",
    "THEODORE_SOURCE_TREE",
    "THEODORE_SPEC_IDENTITY",
    "theodore_log_proves_contract",
    "theodore_spec_is_well_formed",
]
