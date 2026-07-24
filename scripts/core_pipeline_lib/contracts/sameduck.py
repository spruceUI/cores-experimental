"""Exact SameDuck (libretro Game Boy) C-only build-log contract.

sameduck builds from the ``libretro`` subdirectory, so its objects and the
version-script live one directory up with a doubled separator (``..//Core/…``);
a single ``("..//","")`` alias contains them. Its Makefile names each object
``build/obj/<path>/<name>_libretro.c.o`` for source ``<path>/<name>.c`` — a
non-standard scheme the strict ``<stem>.o`` check rejects, so this contract sets
``sha_pinned_object_names`` (the exact per-compile object/source pairing stays
pinned by the compile pair and invocation sha256). 13 C translation units,
C-driver link; commit-derived ``-DGIT_VERSION`` is pinned by the per-arch
invocation sha256.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


SAMEDUCK_CORE_ID = "sameduck"
SAMEDUCK_BUILD_ARTIFACT_NAME = "sameduck_libretro.so"

SAMEDUCK_SOURCE_COMMIT = "f0286ee9d6c44950d9a442463ffdb1ff014a5d5b"
SAMEDUCK_SOURCE_TREE = "c04c4f24a078b55386a1c62ae3619dde5b5087d9"

SAMEDUCK_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-sameduck.yml",
    "source_url": "https://github.com/libretro/sameduck.git",
    "source_requested_ref": "refs/heads/SameDuck-libretro",
    "source_commit": SAMEDUCK_SOURCE_COMMIT,
    "source_tree": SAMEDUCK_SOURCE_TREE,
    "source_key": SAMEDUCK_CORE_ID,
    "source_dir": "libretro-sameduck",
    "output_path": "dist/unix/sameduck_libretro.so",
    "artifact_name": SAMEDUCK_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/sameduck_libretro.info",
    "metadata_artifact_name": "sameduck_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the sameduck core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def sameduck_spec_is_well_formed(spec: object) -> bool:
    """Require SameDuck's exact immutable catalog identity."""

    identity = SAMEDUCK_SPEC_IDENTITY
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


SAMEDUCK_LOG_CONTRACT_ID = "sameduck-c-only-v1"
SAMEDUCK_EXPECTED_COMPILE_COUNT = 13
SAMEDUCK_EXPECTED_COMPILE_PAIR_SHA256 = (
    "5c75218776e6195328ea45512864d9b1d02ea511958598fe8386f14d70cf1b46"
)
SAMEDUCK_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "1120d4ce63e3daab8db31bcfdfa9dfc0012fe332f981ba95faaffb1421ec0a51",
    "armhf": "4864300eb23d012b1d116b821942e161196745adba655be16478fae7a7025309",
}
SAMEDUCK_EXPECTED_LINK_OBJECT_SHA256 = (
    "763269a024bcbcc2af66caf586852b7eba9f80207cd9034ad9f7f9fc54272198"
)
SAMEDUCK_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "3468bd325cdcd0ba901d509489d42d2a71b203cb257f1a6ebbb148802628e7c6"
)
SAMEDUCK_SEMANTIC_PATH_ALIASES = (("..//", ""),)
SAMEDUCK_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=..//libretro/link.T",
    "-Wl,--no-undefined",
    "-I../",
    "-lm",
)

SAMEDUCK_LOG_CONTRACT = COnlyLogContract(
    core_id=SAMEDUCK_CORE_ID,
    expected_compile_count=SAMEDUCK_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=SAMEDUCK_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        SAMEDUCK_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=SAMEDUCK_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=SAMEDUCK_BUILD_ARTIFACT_NAME,
    expected_link_options=SAMEDUCK_EXPECTED_LINK_OPTIONS,
    source_commit=SAMEDUCK_SOURCE_COMMIT,
    source_tree=SAMEDUCK_SOURCE_TREE,
    expected_raw_link_object_sha256=SAMEDUCK_EXPECTED_RAW_LINK_OBJECT_SHA256,
    semantic_path_aliases=SAMEDUCK_SEMANTIC_PATH_ALIASES,
    sha_pinned_object_names=True,
)


def sameduck_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove SameDuck's exact C compile set and matching C link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        SAMEDUCK_LOG_CONTRACT,
    )


__all__ = [
    "SAMEDUCK_BUILD_ARTIFACT_NAME",
    "SAMEDUCK_CORE_ID",
    "SAMEDUCK_LOG_CONTRACT_ID",
    "SAMEDUCK_SOURCE_COMMIT",
    "SAMEDUCK_SOURCE_TREE",
    "SAMEDUCK_SPEC_IDENTITY",
    "sameduck_log_proves_contract",
    "sameduck_spec_is_well_formed",
]
