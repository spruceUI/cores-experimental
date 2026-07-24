"""Exact uw8 (libretro MicroW8) C-only build-log contract.

uw8 is a small C-only libretro-super core: it embeds the wasm3 WebAssembly
interpreter (a portable C library, fetched as the ``wasm3`` submodule) plus the
MicroW8 libretro glue — 15 C translation units total, compiled from the source
root with standard ``<stem>.o`` object naming (no alias) and linked by the C
driver. The per-architecture compile invocation sha256 pins the exact argv.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


UW8_CORE_ID = "uw8"
UW8_BUILD_ARTIFACT_NAME = "uw8_libretro.so"

UW8_SOURCE_COMMIT = "92e0f7a7678de9955002ecce8501eb1be5e46d35"
UW8_SOURCE_TREE = "b0abb1ab7a2905e1f67df521a800014f7ca89fac"

UW8_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-uw8.yml",
    "source_url": "https://github.com/libretro/uw8-libretro.git",
    "source_requested_ref": "refs/heads/main",
    "source_commit": UW8_SOURCE_COMMIT,
    "source_tree": UW8_SOURCE_TREE,
    "source_key": UW8_CORE_ID,
    "source_dir": "libretro-uw8",
    "output_path": "dist/unix/uw8_libretro.so",
    "artifact_name": UW8_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/uw8_libretro.info",
    "metadata_artifact_name": "uw8_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the uw8 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def uw8_spec_is_well_formed(spec: object) -> bool:
    """Require uw8's exact immutable catalog identity."""

    identity = UW8_SPEC_IDENTITY
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


UW8_LOG_CONTRACT_ID = "uw8-c-only-v1"
UW8_EXPECTED_COMPILE_COUNT = 15
UW8_EXPECTED_COMPILE_PAIR_SHA256 = (
    "829e803fbeb2dda164c1040d2a706956d447f76f5ccbc58d51b28844bbf616bb"
)
UW8_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "a7667b5a48facc810ceafd36c244d15daec3d3713e0e489c0b621fd7409b4419",
    "armhf": "32dbaa312455b13e564faf1faaa394f03e32191588d160d96c5033609c751fe2",
}
UW8_EXPECTED_LINK_OBJECT_SHA256 = (
    "989c587c357bb3c7ee3bf70589dfd116e3a00a5f74d34af7ceb2ce08ce79b96f"
)
UW8_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "d7cc6897a062e1168dcddcbb976b82c5631f21c0fe6d4f0d29c7ba5e90c14f45"
)
UW8_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-no-undefined",
    "-lm",
)

UW8_LOG_CONTRACT = COnlyLogContract(
    core_id=UW8_CORE_ID,
    expected_compile_count=UW8_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=UW8_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=UW8_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=UW8_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=UW8_BUILD_ARTIFACT_NAME,
    expected_link_options=UW8_EXPECTED_LINK_OPTIONS,
    source_commit=UW8_SOURCE_COMMIT,
    source_tree=UW8_SOURCE_TREE,
    expected_raw_link_object_sha256=UW8_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def uw8_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove uw8's exact C compile set and matching C link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        UW8_LOG_CONTRACT,
    )


__all__ = [
    "UW8_BUILD_ARTIFACT_NAME",
    "UW8_CORE_ID",
    "UW8_LOG_CONTRACT_ID",
    "UW8_SOURCE_COMMIT",
    "UW8_SOURCE_TREE",
    "UW8_SPEC_IDENTITY",
    "uw8_log_proves_contract",
    "uw8_spec_is_well_formed",
]
