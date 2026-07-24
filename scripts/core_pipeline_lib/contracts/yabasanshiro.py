"""Exact YabaSanshiro generic-GLES3 direct-make contract.

YabaSanshiro shipped as three device-tuned vendor builds: the plain and
``_a133p`` artifacts link the PowerVR userspace directly (libIMGegl,
libsrv_um, ...) and ``_smartpros`` links the Mali blob (libmali.so.0). The
2026-07-23 variant probe replaced all three with ONE generic build: the
upstream ``arm64_cortex_a53_gles3`` platform links only the VERSIONED
``libGLESv2.so.2``, which the fleet capture records present on every probed
arm64 device family, so vendor-specific duplicates add nothing loader
evidence can see. GPU rendering correctness stays a per-device runtime gate.

The libretro-super driver cannot deliver this platform: its build script
hardcodes ``platform="unix"`` on the make command line, which overrides any
MAKEFLAGS value. The direct-make driver passes the platform per architecture
(the gpsp precedent), with ``make_subdir`` naming the in-tree libretro
Makefile directory (the fake08 precedent).
"""

from __future__ import annotations


YABASANSHIRO_CORE_ID = "yabasanshiro"
YABASANSHIRO_BUILD_ARTIFACT_NAME = "yabasanshiro_libretro.so"

YABASANSHIRO_SOURCE_COMMIT = "f448097b69a6037246a08e9dc09eabaa420d7893"
YABASANSHIRO_SOURCE_TREE = "44271b2e50ba9d9149cefc0285b09dcf6a4b099b"

YABASANSHIRO_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-yabasanshiro.yml",
    "source_url": "https://github.com/libretro/yabause.git",
    "source_requested_ref": "refs/heads/yabasanshiro",
    "source_commit": YABASANSHIRO_SOURCE_COMMIT,
    "source_tree": YABASANSHIRO_SOURCE_TREE,
    "source_dir": "yabasanshiro",
    "output_path": "yabause/src/libretro/yabasanshiro_libretro.so",
    "artifact_name": YABASANSHIRO_BUILD_ARTIFACT_NAME,
    "make_subdir": "yabause/src/libretro",
    "platforms": {"arm64": "arm64_cortex_a53_gles3"},
    "metadata_source_path": (
        "/libretro-super/dist/info/yabasanshiro_libretro.info"
    ),
    "metadata_artifact_name": "yabasanshiro_libretro.info",
    "targets": ["arm64"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the yabasanshiro core must preserve its exact source, "
    "direct-make recipe, platform, metadata, and target contract"
)


def yabasanshiro_spec_is_well_formed(spec: object) -> bool:
    """Require YabaSanshiro's exact immutable direct-make catalog identity."""

    identity = YABASANSHIRO_SPEC_IDENTITY
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
                "driver": "direct-make",
                "source_dir": identity["source_dir"],
                "output_path": identity["output_path"],
                "artifact_name": identity["artifact_name"],
                "make_subdir": identity["make_subdir"],
                "platforms": identity["platforms"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


from .c_asm import CAsmLogContract, c_asm_log_proves_contract


YABASANSHIRO_LOG_CONTRACT_ID = "yabasanshiro-c-asm-v1"
YABASANSHIRO_EXPECTED_C_COMPILE_COUNT = {"arm64": 83}
YABASANSHIRO_EXPECTED_CXX_COMPILE_COUNT = {"arm64": 6}
YABASANSHIRO_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 1}
YABASANSHIRO_EXPECTED_COMPILE_PAIR_SHA256 = {
    "arm64": (
        "7d4b35b01d396b9d9c96ee1ca20e3a389d57b79c4b20a19112be705b90693096"
    ),
}
YABASANSHIRO_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": (
        "d8493fd752b532541f3817eb834e86f4c2a26035f67934d6be16c756af79b69d"
    ),
}
YABASANSHIRO_EXPECTED_LINK_OBJECT_SHA256 = {
    "arm64": (
        "7b0c18be87ad6e30918170d13c0b9b1d71f3507857cc0fe9ce6674079ff8caef"
    ),
}
YABASANSHIRO_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "arm64": (
        "d440ddc6c7c3026f16c6f2a1629ba40b57297ec1e8aacee3a69f03304cfde2dc"
    ),
}
# `-lGLESv2` is the whole point of the generic GLES3 platform, pinned the
# same way parallel_n64 pins its renderer: a build that silently lost the
# GLES renderer would no longer prove this contract.
YABASANSHIRO_EXPECTED_LINK_OPTIONS = {
    "arm64": (
        "-lpthread",
        "-lGLESv2",
        "-fPIC",
        "-shared",
        "-Wl,--no-undefined",
        "-Wl,--version-script=link.T",
    ),
}

YABASANSHIRO_LOG_CONTRACT = CAsmLogContract(
    core_id=YABASANSHIRO_CORE_ID,
    expected_c_compile_count=YABASANSHIRO_EXPECTED_C_COMPILE_COUNT,
    expected_asm_compile_count=YABASANSHIRO_EXPECTED_ASM_COMPILE_COUNT,
    expected_compile_pair_sha256=YABASANSHIRO_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        YABASANSHIRO_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=YABASANSHIRO_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=YABASANSHIRO_BUILD_ARTIFACT_NAME,
    expected_link_options=YABASANSHIRO_EXPECTED_LINK_OPTIONS,
    source_commit=YABASANSHIRO_SOURCE_COMMIT,
    source_tree=YABASANSHIRO_SOURCE_TREE,
    expected_cxx_compile_count=YABASANSHIRO_EXPECTED_CXX_COMPILE_COUNT,
    expected_link_language="cxx",
    expected_raw_link_object_sha256=(
        YABASANSHIRO_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    semantic_path_aliases=(("../", ""),),
    source_suffixed_object_names=True,
)


def yabasanshiro_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove YabaSanshiro's exact compile set and ordered GLES C++ link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        YABASANSHIRO_LOG_CONTRACT,
    )


__all__ = [
    "YABASANSHIRO_BUILD_ARTIFACT_NAME",
    "YABASANSHIRO_CORE_ID",
    "YABASANSHIRO_SOURCE_COMMIT",
    "YABASANSHIRO_SOURCE_TREE",
    "YABASANSHIRO_SPEC_IDENTITY",
    "SPEC_GUARD_MESSAGE",
    "YABASANSHIRO_LOG_CONTRACT_ID",
    "yabasanshiro_log_proves_contract",
    "yabasanshiro_spec_is_well_formed",
]
