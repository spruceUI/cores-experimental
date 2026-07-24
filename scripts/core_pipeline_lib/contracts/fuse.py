"""Exact Fuse (libretro ZX Spectrum) C-only build-log contract.

Fuse is a C-only libretro-super core built from the source root via
``Makefile.libretro`` with no ``../../`` object prefixes. Every translation
unit is compiled by the C driver (the ``CXX`` variables the Makefile echoes are
never invoked); the per-architecture compile invocation sha256 pins the exact
compile argv and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


FUSE_CORE_ID = "fuse"
FUSE_BUILD_ARTIFACT_NAME = "fuse_libretro.so"

FUSE_SOURCE_COMMIT = "bce196fb774835fe65b3e5b821887a4ccf657167"
FUSE_SOURCE_TREE = "416338297e3923163ea2ce6f5e0347502368207c"

FUSE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-fuse.yml",
    "source_url": "https://github.com/libretro/fuse-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": FUSE_SOURCE_COMMIT,
    "source_tree": FUSE_SOURCE_TREE,
    "source_key": FUSE_CORE_ID,
    "source_dir": "libretro-fuse",
    "output_path": "dist/unix/fuse_libretro.so",
    "artifact_name": FUSE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/fuse_libretro.info",
    "metadata_artifact_name": "fuse_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the fuse core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def fuse_spec_is_well_formed(spec: object) -> bool:
    """Require Fuse's exact immutable catalog identity."""

    identity = FUSE_SPEC_IDENTITY
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


FUSE_LOG_CONTRACT_ID = "fuse-c-only-v1"
FUSE_EXPECTED_COMPILE_COUNT = 204
FUSE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "78bd917b33f68c50b4c17699d374077809d1ba75b2d1893cbda49b48c802fc9d"
)
FUSE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "19dab2817b5547a02aa369a86876b1359a7954a287f7a28989e9efb4e3904214",
    "armhf": "a425535bf3828be723a888ce80f49048021e92b3a3d4cb0d1d51a58d5e646a67",
}
FUSE_EXPECTED_LINK_OBJECT_SHA256 = (
    "d9adced5cd0b4ae7cc9feb263d9de38c4b47e53ce9818a63c00ba89dff5c4b02"
)
FUSE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "884b8ec17a915a5590c6d3af7c4e04efc5c35b4104e82ebc4c59e1cae441b3f6"
)
FUSE_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=build/link.T",
    "-Wl,-no-undefined",
    "-lm",
)

FUSE_LOG_CONTRACT = COnlyLogContract(
    core_id=FUSE_CORE_ID,
    expected_compile_count=FUSE_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=FUSE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        FUSE_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=FUSE_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=FUSE_BUILD_ARTIFACT_NAME,
    expected_link_options=FUSE_EXPECTED_LINK_OPTIONS,
    source_commit=FUSE_SOURCE_COMMIT,
    source_tree=FUSE_SOURCE_TREE,
    expected_raw_link_object_sha256=FUSE_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def fuse_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Fuse's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FUSE_LOG_CONTRACT,
    )


__all__ = [
    "FUSE_BUILD_ARTIFACT_NAME",
    "FUSE_CORE_ID",
    "FUSE_LOG_CONTRACT_ID",
    "FUSE_SOURCE_COMMIT",
    "FUSE_SOURCE_TREE",
    "FUSE_SPEC_IDENTITY",
    "fuse_log_proves_contract",
    "fuse_spec_is_well_formed",
]
