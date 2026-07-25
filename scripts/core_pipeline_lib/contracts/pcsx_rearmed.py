"""Exact PCSX ReARMed C-plus-assembly build-log contract.

PCSX ReARMed selects a different GPU backend and dynarec per ABI (GPU_NEON on
arm64, GPU_PEOPS on armhf), so its object set, options, and even C compile count
differ per architecture; every expectation is captured per arch on the shared
c_asm standard. It embeds a commit-derived GIT_VERSION on every compile and the
link, which the pinned invocation sha256 fixes. ARMHF adds four HWCAP2=0 compile
definitions for the A30 sysroot.
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


PCSX_REARMED_CORE_ID = "pcsx_rearmed"
PCSX_REARMED_BUILD_ARTIFACT_NAME = "pcsx_rearmed_libretro.so"

PCSX_REARMED_SOURCE_COMMIT = "050981b6eeb715f142854f57c68086f62921f027"
PCSX_REARMED_SOURCE_TREE = "a6bf9ddaaf02f0b163996a195edf1bfcbd89b01c"
PCSX_REARMED_SOURCE_DATE_EPOCH = 1782602899

PCSX_REARMED_ARMHF_COMPILE_DEFINITIONS = [
    "HWCAP2_AES=0",
    "HWCAP2_CRC32=0",
    "HWCAP2_SHA1=0",
    "HWCAP2_SHA2=0",
]

PCSX_REARMED_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-pcsx_rearmed.yml",
    "source_url": "https://github.com/libretro/pcsx_rearmed.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": PCSX_REARMED_SOURCE_COMMIT,
    "source_tree": PCSX_REARMED_SOURCE_TREE,
    "source_key": PCSX_REARMED_CORE_ID,
    "source_dir": "libretro-pcsx_rearmed",
    "output_path": "dist/unix/pcsx_rearmed_libretro.so",
    "artifact_name": PCSX_REARMED_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/pcsx_rearmed_libretro.info"
    ),
    "metadata_artifact_name": "pcsx_rearmed_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the pcsx_rearmed core must preserve its exact source, "
    "recipe, epoch, compile-definitions, metadata, and "
    "target contract"
)


def pcsx_rearmed_spec_is_well_formed(spec: object) -> bool:
    """Require PCSX ReARMed's exact immutable catalog identity."""

    identity = PCSX_REARMED_SPEC_IDENTITY
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
                "submodules": [
                    {"path": "frontend/libpicofe", "commit": "dd11f2d723162eb1cf8e6db9f40de7db0d0b6bba"},
                ],
            },
            "build": {
                "driver": "libretro-super",
                "source_key": identity["source_key"],
                "source_dir": identity["source_dir"],
                "output_path": identity["output_path"],
                "artifact_name": identity["artifact_name"],
                "source_date_epoch": PCSX_REARMED_SOURCE_DATE_EPOCH,
                "compile_definitions": {
                    "armhf": PCSX_REARMED_ARMHF_COMPILE_DEFINITIONS,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


PCSX_REARMED_LOG_CONTRACT_ID = "pcsx-rearmed-c-asm-v1"
PCSX_REARMED_EXPECTED_C_COMPILE_COUNT = {"arm64": 97, "armhf": 96}
PCSX_REARMED_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 4, "armhf": 6}
PCSX_REARMED_EXPECTED_COMPILE_PAIR_SHA256 = {
    "arm64": "31492176230383dd9912f19f131ce4dd510523f369f64e9b73d4f3c54aa16adc",
    "armhf": "ce2e1d5f77f6f253e89791bec6d9a47f8deeb5e19427856f5c82414a7e79cad1",
}
PCSX_REARMED_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "c10f23fb277f328b49f5e853caa76161d7c390cbbc3522aae3575c727b00549d",
    "armhf": "61a85de3c61cccec35ecec8909f0f49ff6f647631ce05261afba79ca68ab739c",
}
PCSX_REARMED_EXPECTED_LINK_OBJECT_SHA256 = {
    "arm64": "370d028b12c96b8fc77241768cc5c51c7a3c4ec7da201419e0c90ecef233a3eb",
    "armhf": "9bd2a5b3bc9c21e8c1ea56390fa061c62985f5c6c48f3a297daaa5f723e95feb",
}
PCSX_REARMED_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "arm64": "370d028b12c96b8fc77241768cc5c51c7a3c4ec7da201419e0c90ecef233a3eb",
    "armhf": "9bd2a5b3bc9c21e8c1ea56390fa061c62985f5c6c48f3a297daaa5f723e95feb",
}
PCSX_REARMED_EXPECTED_LINK_OPTIONS = {
    "arm64": (
        '-DGIT_VERSION=" 050981b6"',
        "-fPIC",
        "-Wall",
        "-Iinclude",
        "-ffast-math",
        "-Ofast",
        "-DNDEBUG",
        "-ffunction-sections",
        "-fdata-sections",
        "-DP_HAVE_MMAP=1",
        "-DP_HAVE_POSIX_MEMALIGN=1",
        "-DDISABLE_MEM_LUTS=0",
        "-Ideps/libchdr/deps/zlib-1.3.1",
        "-DGPU_NEON",
        "-DHAVE_CHD",
        "-Ideps/libchdr/include",
        "-DHAVE_CDROM",
        "-DUSE_LIBRETRO_VFS",
        "-DHAVE_LIBRETRO",
        "-Ideps/libretro-common/include",
        "-DNO_FRONTEND",
        "-shared",
        "-Wl,-version-script=frontend/libretro-version-script",
        "-Wl,--no-undefined",
        "-Wl,--gc-sections",
        "-lpthread",
        "-lm",
        "-ldl",
    ),
    "armhf": (
        "-DHWCAP2_AES=0",
        "-DHWCAP2_CRC32=0",
        "-DHWCAP2_SHA1=0",
        "-DHWCAP2_SHA2=0",
        '-DGIT_VERSION=" 050981b6"',
        "-fPIC",
        "-D_FILE_OFFSET_BITS=64",
        "-Wall",
        "-Iinclude",
        "-ffast-math",
        "-Ofast",
        "-DNDEBUG",
        "-ffunction-sections",
        "-fdata-sections",
        "-DP_HAVE_MMAP=1",
        "-DP_HAVE_POSIX_MEMALIGN=1",
        "-DDISABLE_MEM_LUTS=0",
        "-Ideps/libchdr/deps/zlib-1.3.1",
        "-DGPU_PEOPS",
        "-DHAVE_CHD",
        "-Ideps/libchdr/include",
        "-DHAVE_CDROM",
        "-DUSE_LIBRETRO_VFS",
        "-DHAVE_LIBRETRO",
        "-Ideps/libretro-common/include",
        "-DNO_FRONTEND",
        "-shared",
        "-Wl,-version-script=frontend/libretro-version-script",
        "-Wl,--no-undefined",
        "-Wl,--gc-sections",
        "-lpthread",
        "-lm",
        "-ldl",
    ),
}


def pcsx_rearmed_c_asm_contract() -> CAsmLogContract:
    """Return PCSX ReARMed's exact per-arch C+assembly proof parameters."""

    return CAsmLogContract(
        core_id=PCSX_REARMED_CORE_ID,
        expected_c_compile_count=PCSX_REARMED_EXPECTED_C_COMPILE_COUNT,
        expected_asm_compile_count=PCSX_REARMED_EXPECTED_ASM_COMPILE_COUNT,
        expected_compile_pair_sha256=PCSX_REARMED_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            PCSX_REARMED_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=PCSX_REARMED_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=PCSX_REARMED_BUILD_ARTIFACT_NAME,
        expected_link_options=PCSX_REARMED_EXPECTED_LINK_OPTIONS,
        source_commit=PCSX_REARMED_SOURCE_COMMIT,
        source_tree=PCSX_REARMED_SOURCE_TREE,
        expected_raw_link_object_sha256=(
            PCSX_REARMED_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        semantic_path_aliases=(),
    )


def pcsx_rearmed_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove PCSX ReARMed's exact C+assembly compiles and link for one arch."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        pcsx_rearmed_c_asm_contract(),
    )


__all__ = [
    "PCSX_REARMED_ARMHF_COMPILE_DEFINITIONS",
    "PCSX_REARMED_BUILD_ARTIFACT_NAME",
    "PCSX_REARMED_CORE_ID",
    "PCSX_REARMED_LOG_CONTRACT_ID",
    "PCSX_REARMED_SOURCE_COMMIT",
    "PCSX_REARMED_SOURCE_DATE_EPOCH",
    "PCSX_REARMED_SOURCE_TREE",
    "PCSX_REARMED_SPEC_IDENTITY",
    "pcsx_rearmed_c_asm_contract",
    "pcsx_rearmed_log_proves_contract",
    "pcsx_rearmed_spec_is_well_formed",
]
