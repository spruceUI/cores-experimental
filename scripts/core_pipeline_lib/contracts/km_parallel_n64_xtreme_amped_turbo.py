"""Exact KM parallel-n64 fork contract (direct-make, armhf GLES2).

The KMFDManic fork was broken at its pinned HEAD under the v2 toolchain for
reasons the fork itself introduced or that postdate its era: a commented-out
``GLdouble`` typedef in the bundled glsm header, a missing ``<stdexcept>``
include, a tentative-definition ``_gSPVertex`` in a shared header, and the
pre-GCC10 commons model its C sources rely on. Five reviewed overlays under
``patches/km_parallel_n64_xtreme_amped_turbo/`` restore buildability without
changing behavior; ``-fcommon`` restores the commons semantics the fork was
written for rather than editing dozens of translation units.

The Makefile's product keeps upstream's ``parallel_n64_libretro.so`` name;
the direct-make driver stages it under the core's own canonical artifact
name, the same rebrand rule the km_duckswanstation fork uses.
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


KM_PARALLEL_N64_CORE_ID = "km_parallel_n64_xtreme_amped_turbo"
KM_PARALLEL_N64_BUILD_ARTIFACT_NAME = (
    "km_parallel_n64_xtreme_amped_turbo_libretro.so"
)

KM_PARALLEL_N64_SOURCE_COMMIT = "be8d13e6fddec4eaf705cb04e755e0cf3687d842"
KM_PARALLEL_N64_SOURCE_TREE = "2cec86f7b29182ab8c22481ccaf143f37b97cf0f"

KM_PARALLEL_N64_LOG_CONTRACT_ID = "km-parallel-n64-c-asm-v1"
KM_PARALLEL_N64_EXPECTED_C_COMPILE_COUNT = {"armhf": 167}
KM_PARALLEL_N64_EXPECTED_CXX_COMPILE_COUNT = {"armhf": 44}
KM_PARALLEL_N64_EXPECTED_ASM_COMPILE_COUNT = {"armhf": 1}
KM_PARALLEL_N64_EXPECTED_COMPILE_PAIR_SHA256 = {
    "armhf": (
        "59e09c4063d1ab5f25a8e9054c8255b5ad686a98cbf9e5277416922acb521321"
    ),
}
KM_PARALLEL_N64_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "armhf": (
        "b9f165909f9afa83e334f00be24037db90595342d4ade123eb039fcec85a3955"
    ),
}
KM_PARALLEL_N64_EXPECTED_LINK_OBJECT_SHA256 = {
    "armhf": (
        "7f3954052aefede11080faec91b8771439eb8d69e23d01e2171ce74127802e35"
    ),
}
KM_PARALLEL_N64_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "armhf": (
        "ac9c78fbc82274bb70c77113c2b2d6298967c205cd3fee6dee4833896beb88e7"
    ),
}
# `-lGLESv2` is what FORCE_GLES=1 exists to produce, pinned like the other
# GLES cores: a build that silently lost the GLES renderer no longer proves
# this contract.
KM_PARALLEL_N64_EXPECTED_LINK_OPTIONS = {
    "armhf": (
        "-shared",
        "-Wl,--no-undefined",
        "-Wl,--version-script=./libretro/link.T",
        "-pthread",
        "-lm",
        "-fPIC",
        "-lGLESv2",
    ),
}

KM_PARALLEL_N64_LOG_CONTRACT = CAsmLogContract(
    core_id=KM_PARALLEL_N64_CORE_ID,
    expected_c_compile_count=KM_PARALLEL_N64_EXPECTED_C_COMPILE_COUNT,
    expected_asm_compile_count=KM_PARALLEL_N64_EXPECTED_ASM_COMPILE_COUNT,
    expected_compile_pair_sha256=KM_PARALLEL_N64_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        KM_PARALLEL_N64_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=KM_PARALLEL_N64_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name="parallel_n64_libretro.so",
    expected_link_options=KM_PARALLEL_N64_EXPECTED_LINK_OPTIONS,
    source_commit=KM_PARALLEL_N64_SOURCE_COMMIT,
    source_tree=KM_PARALLEL_N64_SOURCE_TREE,
    expected_cxx_compile_count=KM_PARALLEL_N64_EXPECTED_CXX_COMPILE_COUNT,
    expected_link_language="cxx",
    expected_raw_link_object_sha256=(
        KM_PARALLEL_N64_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def km_parallel_n64_xtreme_amped_turbo_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the KM fork's exact compile set and ordered GLES C++ link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        KM_PARALLEL_N64_LOG_CONTRACT,
    )


__all__ = [
    "KM_PARALLEL_N64_BUILD_ARTIFACT_NAME",
    "KM_PARALLEL_N64_CORE_ID",
    "KM_PARALLEL_N64_LOG_CONTRACT_ID",
    "KM_PARALLEL_N64_SOURCE_COMMIT",
    "KM_PARALLEL_N64_SOURCE_TREE",
    "km_parallel_n64_xtreme_amped_turbo_log_proves_contract",
]
