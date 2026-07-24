"""Exact Opera (libretro 3DO) C-only build-log contract.

Opera is a C-only libretro-super core (libretro/opera-libretro) built from the
source root with no ``../../`` object prefixes and no CMake. Its 78 translation
units are compiled by the C driver with a commit-derived ``-DGIT_VERSION``
token; the link passes ``-fPIC`` twice (the multiset is preserved). The
per-architecture compile invocation sha256 pins the exact argv and the link
references precisely the compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


OPERA_CORE_ID = "opera"
OPERA_BUILD_ARTIFACT_NAME = "opera_libretro.so"

OPERA_SOURCE_COMMIT = "5a4eb964e687ad029f3df51cf535a6e63b414181"
OPERA_SOURCE_TREE = "33540262f3a4cd88ffe537c303d947178a7da95d"

OPERA_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-opera.yml",
    "source_url": "https://github.com/libretro/opera-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": OPERA_SOURCE_COMMIT,
    "source_tree": OPERA_SOURCE_TREE,
    "source_key": OPERA_CORE_ID,
    "source_dir": "libretro-opera",
    "output_path": "dist/unix/opera_libretro.so",
    "artifact_name": OPERA_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/opera_libretro.info",
    "metadata_artifact_name": "opera_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the opera core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def opera_spec_is_well_formed(spec: object) -> bool:
    """Require Opera's exact immutable catalog identity."""

    identity = OPERA_SPEC_IDENTITY
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


OPERA_LOG_CONTRACT_ID = "opera-c-only-v1"
OPERA_EXPECTED_COMPILE_COUNT = 78
OPERA_EXPECTED_COMPILE_PAIR_SHA256 = (
    "d0afcfadefe39afd99a66c95a7659192528aeb6a40afa021f6424c1c10e69448"
)
OPERA_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "2903158f7ea52d339807cd0a79a24cae688ccfce273cd4ec0a056298c27b44f2",
    "armhf": "4f9887feaa00e31449b0307c6b4f1e41a6a626af434c0532f683b8d3fafc97f3",
}
OPERA_EXPECTED_LINK_OBJECT_SHA256 = (
    "5c5da56b6355dd75b35ef4c40e5b833eaa2f44a60d039288aaa2c46f16f78b80"
)
OPERA_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "5c5da56b6355dd75b35ef4c40e5b833eaa2f44a60d039288aaa2c46f16f78b80"
)
OPERA_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-fPIC",
    "-lpthread",
    "-lm",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)

OPERA_LOG_CONTRACT = COnlyLogContract(
    core_id=OPERA_CORE_ID,
    expected_compile_count=OPERA_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=OPERA_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        OPERA_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=OPERA_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=OPERA_BUILD_ARTIFACT_NAME,
    expected_link_options=OPERA_EXPECTED_LINK_OPTIONS,
    source_commit=OPERA_SOURCE_COMMIT,
    source_tree=OPERA_SOURCE_TREE,
    expected_raw_link_object_sha256=OPERA_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def opera_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Opera's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        OPERA_LOG_CONTRACT,
    )


__all__ = [
    "OPERA_BUILD_ARTIFACT_NAME",
    "OPERA_CORE_ID",
    "OPERA_LOG_CONTRACT_ID",
    "OPERA_SOURCE_COMMIT",
    "OPERA_SOURCE_TREE",
    "OPERA_SPEC_IDENTITY",
    "opera_log_proves_contract",
    "opera_spec_is_well_formed",
]
