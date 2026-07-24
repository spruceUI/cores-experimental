"""Exact GW (libretro Game & Watch) C-only build-log contract.

gw is a C-only libretro-super core built from the source root with no ``../../``
object prefixes and no CMake. Every translation unit is compiled by the C
driver; the per-architecture compile invocation sha256 pins the exact compile
argv and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


GW_CORE_ID = "gw"
GW_BUILD_ARTIFACT_NAME = "gw_libretro.so"

GW_SOURCE_COMMIT = "91d599b951e7bfe7e040347f58667cba20074adc"
GW_SOURCE_TREE = "3e047c44fe4828599aaf72708a5cea25730bc824"

GW_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gw.yml",
    "source_url": "https://github.com/libretro/gw-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": GW_SOURCE_COMMIT,
    "source_tree": GW_SOURCE_TREE,
    "source_key": GW_CORE_ID,
    "source_dir": "libretro-gw",
    "output_path": "dist/unix/gw_libretro.so",
    "artifact_name": GW_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/gw_libretro.info",
    "metadata_artifact_name": "gw_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the gw core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def gw_spec_is_well_formed(spec: object) -> bool:
    """Require gw's exact immutable catalog identity."""

    identity = GW_SPEC_IDENTITY
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


GW_LOG_CONTRACT_ID = "gw-c-only-v1"
GW_EXPECTED_COMPILE_COUNT = 56
GW_EXPECTED_COMPILE_PAIR_SHA256 = (
    "90b4900bac49dd6a8556bb766dfb9e03fa51e523cd46c9186e8787909b78e4bd"
)
GW_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "4730cfe0a805c077008e756791dccbbdeac7011bd6d969633b91a781b15ad67f",
    "armhf": "9f854ea7f78c4e0b4c0cc58ed73e0ba2e46a8d308f37f4515196b349a3a21891",
}
GW_EXPECTED_LINK_OBJECT_SHA256 = (
    "d67a47e84feac47b4f0c2ffa1a22b989c0730281e93f11f51613290a0161c61a"
)
GW_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "cb40238e75f0255ee58f7a39dda840b0d568cb7579405c8ddda547612d520f0f"
)
GW_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=build/link.T",
    "-Wl,-no-undefined",
    "-lm",
)

GW_LOG_CONTRACT = COnlyLogContract(
    core_id=GW_CORE_ID,
    expected_compile_count=GW_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=GW_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=GW_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=GW_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=GW_BUILD_ARTIFACT_NAME,
    expected_link_options=GW_EXPECTED_LINK_OPTIONS,
    source_commit=GW_SOURCE_COMMIT,
    source_tree=GW_SOURCE_TREE,
    expected_raw_link_object_sha256=GW_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def gw_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove gw's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        GW_LOG_CONTRACT,
    )


__all__ = [
    "GW_BUILD_ARTIFACT_NAME",
    "GW_CORE_ID",
    "GW_LOG_CONTRACT_ID",
    "GW_SOURCE_COMMIT",
    "GW_SOURCE_TREE",
    "GW_SPEC_IDENTITY",
    "gw_log_proves_contract",
    "gw_spec_is_well_formed",
]
