"""Exact Hatari (libretro Atari ST) C-only build-log contract.

Hatari is a C-only libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its Makefile passes the full CFLAGS
set (including the commit-derived ``-DGIT_VERSION`` token and a duplicated
``-I./src``) to the final link, so the expected link options mirror that exact
multiset. The per-architecture compile invocation sha256 pins each compile and
the link references precisely the compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


HATARI_CORE_ID = "hatari"
HATARI_BUILD_ARTIFACT_NAME = "hatari_libretro.so"

HATARI_SOURCE_COMMIT = "c605d3aa342f2ad8f915f94bf03bae018e1be7b7"
HATARI_SOURCE_TREE = "e7d1a78a01d56b0a31baa2fdf32564e00b33c566"

# Hatari embeds ``__DATE__``/``__TIME__`` ("Hatari <file>.c : <date> <time>")
# in the binary and its GNU build-id derives from that content; pinning
# SOURCE_DATE_EPOCH to the commit's committer date (2026-06-10) makes both deterministic.
HATARI_SOURCE_DATE_EPOCH = 1781097623

HATARI_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-hatari.yml",
    "source_url": "https://github.com/libretro/hatari.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": HATARI_SOURCE_COMMIT,
    "source_tree": HATARI_SOURCE_TREE,
    "source_key": HATARI_CORE_ID,
    "source_dir": "libretro-hatari",
    "output_path": "dist/unix/hatari_libretro.so",
    "artifact_name": HATARI_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/hatari_libretro.info",
    "metadata_artifact_name": "hatari_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the hatari core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def hatari_spec_is_well_formed(spec: object) -> bool:
    """Require Hatari's exact immutable catalog identity."""

    identity = HATARI_SPEC_IDENTITY
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
                "source_date_epoch": HATARI_SOURCE_DATE_EPOCH,
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


HATARI_LOG_CONTRACT_ID = "hatari-c-only-v1"
HATARI_EXPECTED_COMPILE_COUNT = 134
HATARI_EXPECTED_COMPILE_PAIR_SHA256 = (
    "a0fa3a771719af226eda57e56b8ce9fb35ad1095ac6cfd4cb00706bbad8f1b8f"
)
HATARI_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "e112b2bbe522f0ede5f44b2589b73e373782a5f5b07b5a0bef7294b42ac437eb",
    "armhf": "097e11d5228d292b876362ad40eff44ed7ecb847d9567716afb898576b801a63",
}
HATARI_EXPECTED_LINK_OBJECT_SHA256 = (
    "a9bfff35f0e1bf013299030f73c661dff71e0223286b7e1b58fb49b52766c736"
)
HATARI_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9e972889b3e30afafccb2db179cac90d983c7705fa52f627c406bba3c0ddb2b5"
)
HATARI_EXPECTED_LINK_OPTIONS = (
    '-DGIT_VERSION=" c605d3aa"',
    "-funroll-loops",
    "-ffast-math",
    "-fomit-frame-pointer",
    "-O3",
    "-fsigned-char",
    "-D__LIBRETRO__",
    "-fno-builtin",
    "-fPIC",
    "-DLSB_FIRST",
    "-DALIGN_DWORD",
    "-I./src",
    "-I./src/uae-cpu",
    "-I./src/falcon",
    "-I./src/includes",
    "-I./src/debug",
    "-I./src",
    "-I./libretro",
    "-I./libretro/libretro-common/include",
    "-I./libretro/libretro-common/include/compat/zlib",
    "-I./libretro/include",
    "-I./libretro/utils",
    "-I./libretro/uae-cpu-pregen",
    "-lm",
    "-lz",
    "-lpthread",
    "-shared",
    "-Wl,--version-script=./libretro/link.T",
    "-Wl,--no-undefined",
    "-Wl,--as-needed",
)

HATARI_LOG_CONTRACT = COnlyLogContract(
    core_id=HATARI_CORE_ID,
    expected_compile_count=HATARI_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=HATARI_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        HATARI_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=HATARI_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=HATARI_BUILD_ARTIFACT_NAME,
    expected_link_options=HATARI_EXPECTED_LINK_OPTIONS,
    source_commit=HATARI_SOURCE_COMMIT,
    source_tree=HATARI_SOURCE_TREE,
    expected_raw_link_object_sha256=HATARI_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def hatari_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Hatari's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        HATARI_LOG_CONTRACT,
    )


__all__ = [
    "HATARI_BUILD_ARTIFACT_NAME",
    "HATARI_CORE_ID",
    "HATARI_LOG_CONTRACT_ID",
    "HATARI_SOURCE_COMMIT",
    "HATARI_SOURCE_TREE",
    "HATARI_SPEC_IDENTITY",
    "hatari_log_proves_contract",
    "hatari_spec_is_well_formed",
]
