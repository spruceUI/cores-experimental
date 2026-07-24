"""Exact Mupen64Plus-Next C/C++/assembly contract and reviewed make-variable set.

The second core to link a graphics stack directly, and the second to need the
`ARCH`-avoidance pattern established by [parallel_n64]. Shipped **arm64 only**,
and its shipped artifact carries `libGLESv2.so` and `libEGL.so` in `DT_NEEDED`
-- the *unversioned* sonames, not `libGLESv2.so.2`/`libEGL.so.1`.

Like parallel_n64, its Makefile defaults `ARCH` to `uname -m` (`x86_64` on the
cross-build host) and derives `WITH_DYNAREC` from it, so the stock build selects
the wrong dynarec. `ARCH` is a reserved make-variable name, but the two switches
that actually decide the build are not:

* `WITH_DYNAREC=aarch64` -- declared `?=` from `$(ARCH)`, so naming it directly
  makes `ARCH` irrelevant.
* `FORCE_GLES=1` -- the Makefile's own documented switch (line 2) for the GLES2
  renderer, which is what makes the artifact link `-lGLESv2 -lEGL` the way the
  shipped one does.

Verified equivalent rather than assumed: a full build with `ARCH=aarch64
FORCE_GLES=1` and one with `WITH_DYNAREC=aarch64 FORCE_GLES=1` produced a
byte-identical `mupen64plus_next_libretro.so` (`8cfb735c...`).
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


MUPEN64PLUS_NEXT_CORE_ID = "mupen64plus_next"
MUPEN64PLUS_NEXT_BUILD_ARTIFACT_NAME = "mupen64plus_next_libretro.so"

MUPEN64PLUS_NEXT_SOURCE_COMMIT = "98c1b0d877542b01314b3b04272282ba223b65b3"
MUPEN64PLUS_NEXT_SOURCE_TREE = "e82f86deaeb37d3df9ad2673b53738af96848325"

MUPEN64PLUS_NEXT_MAKE_VARIABLES = {
    "FORCE_GLES": 1,
    "WITH_DYNAREC": "aarch64",
}
MUPEN64PLUS_NEXT_MAKE_PROFILE = "mupen64plus-next-aarch64-gles-v1"

MUPEN64PLUS_NEXT_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mupen64plus_next.yml",
    "source_url": "https://github.com/libretro/mupen64plus-libretro-nx.git",
    "source_requested_ref": "refs/heads/develop",
    "source_commit": MUPEN64PLUS_NEXT_SOURCE_COMMIT,
    "source_tree": MUPEN64PLUS_NEXT_SOURCE_TREE,
    "source_key": MUPEN64PLUS_NEXT_CORE_ID,
    "source_dir": "libretro-mupen64plus_next",
    "output_path": "dist/unix/mupen64plus_next_libretro.so",
    "artifact_name": MUPEN64PLUS_NEXT_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mupen64plus_next_libretro.info"
    ),
    "metadata_artifact_name": "mupen64plus_next_libretro.info",
    "targets": ["arm64"],
}


def mupen64plus_next_spec_is_well_formed(spec: object) -> bool:
    """Require Mupen64Plus-Next's exact immutable catalog identity."""

    identity = MUPEN64PLUS_NEXT_SPEC_IDENTITY
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
                "submodules": False,
                "make_variables": dict(MUPEN64PLUS_NEXT_MAKE_VARIABLES),
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


MUPEN64PLUS_NEXT_LOG_CONTRACT_ID = "mupen64plus-next-c-asm-v1"
MUPEN64PLUS_NEXT_EXPECTED_C_COMPILE_COUNT = {"arm64": 141}
MUPEN64PLUS_NEXT_EXPECTED_CXX_COMPILE_COUNT = {"arm64": 130}
MUPEN64PLUS_NEXT_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 1}
MUPEN64PLUS_NEXT_EXPECTED_COMPILE_PAIR_SHA256 = {
    "arm64": (
        "7eff1d06bce6cc95138921bd7a11e50d8e486c74b510b2f952208ab7e164f26f"
    ),
}
MUPEN64PLUS_NEXT_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": (
        "04bb0a6c5ba0d3ee68a9d273392d3a5d4ff154a21c697dca06860a0025d20a69"
    ),
}
MUPEN64PLUS_NEXT_EXPECTED_LINK_OBJECT_SHA256 = {
    "arm64": (
        "ad394c6e21ad78a1a4a98cb188b6bad57f44c088831ec2f67c25fa0568e1c172"
    ),
}
MUPEN64PLUS_NEXT_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "arm64": (
        "5a711713fa1257e5beb43c4f83804d6acb54bbbeb027aa6102f223efdf4d09ff"
    ),
}
# `-lEGL` and `-lGLESv2` are pinned here, so a build that silently lost the
# GLES renderer stops proving this contract. The resulting artifact needs the
# *versioned* sonames (libGLESv2.so.2, libEGL.so.1), unlike the shipped build
# which linked the unversioned dev symlinks.
MUPEN64PLUS_NEXT_EXPECTED_LINK_OPTIONS = {
    "arm64": (
        "-shared",
        "-Wl,--version-script=./libretro/link.T",
        "-Wl,--no-undefined",
        "-lEGL",
        "-lpthread",
        "-fPIC",
        "-O3",
        "-O3",
        "-DNDEBUG",
        "-fsigned-char",
        "-ffast-math",
        "-fno-strict-aliasing",
        "-fomit-frame-pointer",
        "-fvisibility=hidden",
        "-fcommon",
        "-lGLESv2",
    ),
}

MUPEN64PLUS_NEXT_LOG_CONTRACT = CAsmLogContract(
    core_id=MUPEN64PLUS_NEXT_CORE_ID,
    expected_c_compile_count=MUPEN64PLUS_NEXT_EXPECTED_C_COMPILE_COUNT,
    expected_asm_compile_count=MUPEN64PLUS_NEXT_EXPECTED_ASM_COMPILE_COUNT,
    expected_compile_pair_sha256=MUPEN64PLUS_NEXT_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        MUPEN64PLUS_NEXT_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=MUPEN64PLUS_NEXT_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=MUPEN64PLUS_NEXT_BUILD_ARTIFACT_NAME,
    expected_link_options=MUPEN64PLUS_NEXT_EXPECTED_LINK_OPTIONS,
    source_commit=MUPEN64PLUS_NEXT_SOURCE_COMMIT,
    source_tree=MUPEN64PLUS_NEXT_SOURCE_TREE,
    expected_cxx_compile_count=MUPEN64PLUS_NEXT_EXPECTED_CXX_COMPILE_COUNT,
    expected_link_language="cxx",
    expected_raw_link_object_sha256=(
        MUPEN64PLUS_NEXT_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def mupen64plus_next_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Mupen64Plus-Next's exact compile set and ordered GLES C++ link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        MUPEN64PLUS_NEXT_LOG_CONTRACT,
    )


__all__ = [
    "MUPEN64PLUS_NEXT_BUILD_ARTIFACT_NAME",
    "MUPEN64PLUS_NEXT_CORE_ID",
    "MUPEN64PLUS_NEXT_LOG_CONTRACT_ID",
    "MUPEN64PLUS_NEXT_MAKE_PROFILE",
    "MUPEN64PLUS_NEXT_MAKE_VARIABLES",
    "MUPEN64PLUS_NEXT_SOURCE_COMMIT",
    "MUPEN64PLUS_NEXT_SOURCE_TREE",
    "MUPEN64PLUS_NEXT_SPEC_IDENTITY",
    "mupen64plus_next_log_proves_contract",
    "mupen64plus_next_spec_is_well_formed",
]
