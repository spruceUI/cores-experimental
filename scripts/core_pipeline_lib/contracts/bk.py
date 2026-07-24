"""Exact BK (libretro BK-0010) C-only build-log contract.

bk is a C-only libretro-super core (libretro/bk-emulator) built from the source
root with no ``../../`` object prefixes and no CMake. Each of its 27 translation
units is compiled by the C driver with a commit-derived ``-DGIT_VERSION`` token;
the per-architecture compile invocation sha256 pins that exact token and the
link references precisely the compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


BK_CORE_ID = "bk"
BK_BUILD_ARTIFACT_NAME = "bk_libretro.so"

BK_SOURCE_COMMIT = "fe64da42ee463c1b2f4d0566e4d0f7a9667506f6"
BK_SOURCE_TREE = "7936963f4fcfbd4961f49b2d9ae722a7ab31b85f"

BK_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-bk.yml",
    "source_url": "https://github.com/libretro/bk-emulator.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": BK_SOURCE_COMMIT,
    "source_tree": BK_SOURCE_TREE,
    "source_key": BK_CORE_ID,
    "source_dir": "libretro-bk",
    "output_path": "dist/unix/bk_libretro.so",
    "artifact_name": BK_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/bk_libretro.info",
    "metadata_artifact_name": "bk_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the bk core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def bk_spec_is_well_formed(spec: object) -> bool:
    """Require BK's exact immutable catalog identity."""

    identity = BK_SPEC_IDENTITY
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


BK_LOG_CONTRACT_ID = "bk-c-only-v1"
BK_EXPECTED_COMPILE_COUNT = 27
BK_EXPECTED_COMPILE_PAIR_SHA256 = (
    "2bb322b8f66c5f874d8460710863b15b052656dbe0f1d6bace0f2ad2f5c1656c"
)
BK_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "cc9122ad9efd80be3c0ec50a483d582901d00e34d9a09ac5ed7482a84ae2c64a",
    "armhf": "9fb7dbe0f5ba638b215aef8cfcd51f08dbe8b97583c3fad2b568a9ae18ff3a72",
}
BK_EXPECTED_LINK_OBJECT_SHA256 = (
    "1baad686f267935bb87ad4a78b319e0dad61b9d92c98f621b3cba9a0ce2e5a9b"
)
BK_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "ee4ebcc53da6e31e8370106d5fcefaa6b324696c5af180b6be17c3d31c0b2c14"
)
BK_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-lm",
)

BK_LOG_CONTRACT = COnlyLogContract(
    core_id=BK_CORE_ID,
    expected_compile_count=BK_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=BK_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=BK_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=BK_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=BK_BUILD_ARTIFACT_NAME,
    expected_link_options=BK_EXPECTED_LINK_OPTIONS,
    source_commit=BK_SOURCE_COMMIT,
    source_tree=BK_SOURCE_TREE,
    expected_raw_link_object_sha256=BK_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def bk_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove BK's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        BK_LOG_CONTRACT,
    )


__all__ = [
    "BK_BUILD_ARTIFACT_NAME",
    "BK_CORE_ID",
    "BK_LOG_CONTRACT_ID",
    "BK_SOURCE_COMMIT",
    "BK_SOURCE_TREE",
    "BK_SPEC_IDENTITY",
    "bk_log_proves_contract",
    "bk_spec_is_well_formed",
]
