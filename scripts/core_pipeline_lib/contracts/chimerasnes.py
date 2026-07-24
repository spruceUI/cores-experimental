"""Exact ChimeraSNES (libretro SNES) C-only build-log contract.

ChimeraSNES (upstream jamsilva/chimerasnes, a snes9x-family fork) is a C-only
libretro-super core whose Makefile builds to an **absolute** object root
(``/libretro-super/libretro-chimerasnes/``) and passes ``-Wl,--gc-sections`` in
CFLAGS. A single reviewed semantic path alias maps that build root to a
contained relative path; the ``-Wl,...`` token is inert under ``-c`` and pinned
verbatim by the per-architecture compile invocation sha256. Its 50 translation
units are each compiled once and linked (with LTO) by the C driver.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


CHIMERASNES_CORE_ID = "chimerasnes"
CHIMERASNES_BUILD_ARTIFACT_NAME = "chimerasnes_libretro.so"

CHIMERASNES_SOURCE_COMMIT = "04c57c2902c25f36ae5a5d9c57aff851a772c868"
CHIMERASNES_SOURCE_TREE = "243afd13215337662b2e3e69a802a2bccf38ecd8"

CHIMERASNES_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-chimerasnes.yml",
    "source_url": "https://github.com/jamsilva/chimerasnes.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": CHIMERASNES_SOURCE_COMMIT,
    "source_tree": CHIMERASNES_SOURCE_TREE,
    "source_key": CHIMERASNES_CORE_ID,
    "source_dir": "libretro-chimerasnes",
    "output_path": "dist/unix/chimerasnes_libretro.so",
    "artifact_name": CHIMERASNES_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/chimerasnes_libretro.info"
    ),
    "metadata_artifact_name": "chimerasnes_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the chimerasnes core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def chimerasnes_spec_is_well_formed(spec: object) -> bool:
    """Require ChimeraSNES's exact immutable catalog identity."""

    identity = CHIMERASNES_SPEC_IDENTITY
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


CHIMERASNES_LOG_CONTRACT_ID = "chimerasnes-c-only-v1"
CHIMERASNES_EXPECTED_COMPILE_COUNT = 50
CHIMERASNES_EXPECTED_COMPILE_PAIR_SHA256 = (
    "05ff8774574b093b6d0f676e7d0b46150ca6f8b1f14b8dc8ff140bafecef1dcc"
)
CHIMERASNES_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "9aeccb8405e1d22481bfa63a332989dfc589819b35e67f537cc1b6eaab58fc6d",
    "armhf": "a1d715dbcac936886d2063bd11d809631d3ec841e3297a79540e081b70115866",
}
CHIMERASNES_EXPECTED_LINK_OBJECT_SHA256 = (
    "5bbc15dd43b1d3d255eb9d324c25b48a44cae474ae8124fb7a1ba05b4ad03bb9"
)
CHIMERASNES_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "c65353484b37b57f4dfa5066a556c1ee31b75b185f9a1852fd64050a101ae8e0"
)
CHIMERASNES_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=libretro-common/link.T",
    "-Wl,--no-undefined",
    "-flto=4",
    "-fuse-linker-plugin",
    "-lm",
)
CHIMERASNES_SEMANTIC_PATH_ALIASES = (
    ("/libretro-super/libretro-chimerasnes/", ""),
)

CHIMERASNES_LOG_CONTRACT = COnlyLogContract(
    core_id=CHIMERASNES_CORE_ID,
    expected_compile_count=CHIMERASNES_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=CHIMERASNES_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        CHIMERASNES_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=CHIMERASNES_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=CHIMERASNES_BUILD_ARTIFACT_NAME,
    expected_link_options=CHIMERASNES_EXPECTED_LINK_OPTIONS,
    source_commit=CHIMERASNES_SOURCE_COMMIT,
    source_tree=CHIMERASNES_SOURCE_TREE,
    expected_raw_link_object_sha256=(
        CHIMERASNES_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    semantic_path_aliases=CHIMERASNES_SEMANTIC_PATH_ALIASES,
)


def chimerasnes_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove ChimeraSNES's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        CHIMERASNES_LOG_CONTRACT,
    )


__all__ = [
    "CHIMERASNES_BUILD_ARTIFACT_NAME",
    "CHIMERASNES_CORE_ID",
    "CHIMERASNES_LOG_CONTRACT_ID",
    "CHIMERASNES_SOURCE_COMMIT",
    "CHIMERASNES_SOURCE_TREE",
    "CHIMERASNES_SPEC_IDENTITY",
    "chimerasnes_log_proves_contract",
    "chimerasnes_spec_is_well_formed",
]
