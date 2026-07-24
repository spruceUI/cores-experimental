"""Exact TyrQuake C-only build-log contract.

TyrQuake is a C-only libretro-super core built from the source root (no
``../../`` object prefixes). Its bundled libvorbis compiles with a forced
``-include`` symbol-rename header, which the shared c_only parser now skips as a
file operand. The Makefile embeds a commit-derived ``GIT_VERSION`` on each
compile; the per-architecture compile invocation sha256 pins that exact token.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


TYRQUAKE_CORE_ID = "tyrquake"
TYRQUAKE_BUILD_ARTIFACT_NAME = "tyrquake_libretro.so"

TYRQUAKE_SOURCE_COMMIT = "e57bb11597e8a00380f30f2627d219da960cf69a"
TYRQUAKE_SOURCE_TREE = "796dfc170786fcb21a5fd5f5cc9a44f5dd9e1853"
# TyrQuake embeds __DATE__/__TIME__ in the binary; pinning SOURCE_DATE_EPOCH
# (the commit's committer timestamp) makes those deterministic so the build is
# byte-reproducible. It is an environment variable, not a compile flag, so the
# pinned compile invocation sha256 is unaffected.
TYRQUAKE_SOURCE_DATE_EPOCH = 1784135314

TYRQUAKE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-tyrquake.yml",
    "source_url": "https://github.com/libretro/tyrquake.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": TYRQUAKE_SOURCE_COMMIT,
    "source_tree": TYRQUAKE_SOURCE_TREE,
    "source_key": TYRQUAKE_CORE_ID,
    "source_dir": "libretro-tyrquake",
    "output_path": "dist/unix/tyrquake_libretro.so",
    "artifact_name": TYRQUAKE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/tyrquake_libretro.info"
    ),
    "metadata_artifact_name": "tyrquake_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the tyrquake core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def tyrquake_spec_is_well_formed(spec: object) -> bool:
    """Require TyrQuake's exact immutable catalog identity."""

    identity = TYRQUAKE_SPEC_IDENTITY
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
                "source_date_epoch": TYRQUAKE_SOURCE_DATE_EPOCH,
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


TYRQUAKE_LOG_CONTRACT_ID = "tyrquake-c-only-v1"
TYRQUAKE_EXPECTED_COMPILE_COUNT = 150
TYRQUAKE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "7c9e7af9331de4825e72aec41c4817bb52178e0f1ce4144a498d8c8a2293eb24"
)
TYRQUAKE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "9136e2d9dc8577da86951122aa4aa31d6b43ace67cceb79be537915fd30b3206",
    "armhf": "172da9e6b86c92ee144eeb201eee5e2dce46a475f1a60dd85e889a5587b2b9a3",
}
TYRQUAKE_EXPECTED_LINK_OBJECT_SHA256 = (
    "9dfe21c5af18a5e8fd09629aa32370aa0ac2794f8c179c83af9a5c14237f2150"
)
TYRQUAKE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "5d7a583f985789c7f637d514e84877452f7d9c556c6fca79c145a4434e9771ec"
)
TYRQUAKE_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=common/libretro-link.T",
    "-lm",
)

TYRQUAKE_LOG_CONTRACT = COnlyLogContract(
    core_id=TYRQUAKE_CORE_ID,
    expected_compile_count=TYRQUAKE_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=TYRQUAKE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        TYRQUAKE_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=TYRQUAKE_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=TYRQUAKE_BUILD_ARTIFACT_NAME,
    expected_link_options=TYRQUAKE_EXPECTED_LINK_OPTIONS,
    source_commit=TYRQUAKE_SOURCE_COMMIT,
    source_tree=TYRQUAKE_SOURCE_TREE,
    expected_raw_link_object_sha256=TYRQUAKE_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def tyrquake_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove TyrQuake's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        TYRQUAKE_LOG_CONTRACT,
    )


__all__ = [
    "TYRQUAKE_BUILD_ARTIFACT_NAME",
    "TYRQUAKE_CORE_ID",
    "TYRQUAKE_LOG_CONTRACT_ID",
    "TYRQUAKE_SOURCE_COMMIT",
    "TYRQUAKE_SOURCE_TREE",
    "TYRQUAKE_SPEC_IDENTITY",
    "tyrquake_log_proves_contract",
    "tyrquake_spec_is_well_formed",
]
