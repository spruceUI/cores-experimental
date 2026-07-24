"""Exact PrBoom C-only build-log contract.

PrBoom is a C-only libretro-super core built from the source root (no ``../../``
object prefixes). The Makefile embeds a commit-derived ``GIT_VERSION`` on each
compile; the per-architecture compile invocation sha256 pins that exact token.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


PRBOOM_CORE_ID = "prboom"
PRBOOM_BUILD_ARTIFACT_NAME = "prboom_libretro.so"

PRBOOM_SOURCE_COMMIT = "94adc0554cafbe6628e86408ced27fd8f92bd57d"
PRBOOM_SOURCE_TREE = "e94b8e9691eb9d712fdc588109b7919ed27b252b"

PRBOOM_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-prboom.yml",
    "source_url": "https://github.com/libretro/libretro-prboom.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": PRBOOM_SOURCE_COMMIT,
    "source_tree": PRBOOM_SOURCE_TREE,
    "source_key": PRBOOM_CORE_ID,
    "source_dir": "libretro-prboom",
    "output_path": "dist/unix/prboom_libretro.so",
    "artifact_name": PRBOOM_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/prboom_libretro.info",
    "metadata_artifact_name": "prboom_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the prboom core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def prboom_spec_is_well_formed(spec: object) -> bool:
    """Require PrBoom's exact immutable catalog identity."""

    identity = PRBOOM_SPEC_IDENTITY
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


PRBOOM_LOG_CONTRACT_ID = "prboom-c-only-v1"
PRBOOM_EXPECTED_COMPILE_COUNT = 159
PRBOOM_EXPECTED_COMPILE_PAIR_SHA256 = (
    "98e218d26606c553e171b8edbd96a04ec632fa2beffb26d4d903f68f50736217"
)
PRBOOM_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "ed61c031013b0b2e9aaf561101c2a1a185f49b3c2d111cd9e15cbcb2a865c92c",
    "armhf": "bdf3ec23ccf34b4cade3130c36d2cfcc289b8e0628d031fd1434feb624d0a998",
}
PRBOOM_EXPECTED_LINK_OBJECT_SHA256 = (
    "d1e4b62571d200d714a195b8d1d11d9ddb40c8b5297041496a8426ad72c577dd"
)
PRBOOM_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "eb0a7af6f0834de47328f4e96d63f22ee6bc56176dce203bfbba9144fcbf53fe"
)
PRBOOM_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=libretro/link.T",
    "-Wl,--no-undefined",
    "-Wl,--as-needed",
    "-lm",
)

PRBOOM_LOG_CONTRACT = COnlyLogContract(
    core_id=PRBOOM_CORE_ID,
    expected_compile_count=PRBOOM_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=PRBOOM_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        PRBOOM_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=PRBOOM_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=PRBOOM_BUILD_ARTIFACT_NAME,
    expected_link_options=PRBOOM_EXPECTED_LINK_OPTIONS,
    source_commit=PRBOOM_SOURCE_COMMIT,
    source_tree=PRBOOM_SOURCE_TREE,
    expected_raw_link_object_sha256=PRBOOM_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def prboom_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove PrBoom's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        PRBOOM_LOG_CONTRACT,
    )


__all__ = [
    "PRBOOM_BUILD_ARTIFACT_NAME",
    "PRBOOM_CORE_ID",
    "PRBOOM_LOG_CONTRACT_ID",
    "PRBOOM_SOURCE_COMMIT",
    "PRBOOM_SOURCE_TREE",
    "PRBOOM_SPEC_IDENTITY",
    "prboom_log_proves_contract",
    "prboom_spec_is_well_formed",
]
