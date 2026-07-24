"""Exact ChaiLove (libretro ChaiScript game framework) C/C++/asm contract.

chailove bundles the ChaiScript engine, PhysicsFS, libz and libretro-common, so
its build mixes 71 C, 30 C++ and one NEON assembly translation unit
(``sinc_resampler_neon.S``) — the ``c_asm`` standard, linked by the C++ driver.

Two build-shape notes:

* Its Makefile silences every recipe with an unconditional ``Q=@`` (guarded by
  an unused ``VERBOSE`` switch), so the compile argv never reaches the log. A
  reviewed ``build.overlays`` patch flips that guard to ``Q=`` — echo only, the
  artifact is byte-identical.
* Every compile carries ``-include retro_endianness.h``. That forced-include
  operand must not be mistaken for a second source; ``c_asm`` (like ``c_only``)
  already excludes ``FILE_OPERAND_FLAGS`` operands.

Objects are plain ``<stem>.o`` beside their sources, so no alias is needed, and
the per-architecture compile invocation sha256 pins the exact argv.
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


CHAILOVE_CORE_ID = "chailove"
CHAILOVE_BUILD_ARTIFACT_NAME = "chailove_libretro.so"

CHAILOVE_SOURCE_COMMIT = "5fa2014d9a1359836f165ab251831bce878ec2be"
CHAILOVE_SOURCE_TREE = "6d11c7be6a39132d97e99bb81588d581613222ae"

CHAILOVE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-chailove.yml",
    "source_url": "https://github.com/libretro/ChaiLove.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": CHAILOVE_SOURCE_COMMIT,
    "source_tree": CHAILOVE_SOURCE_TREE,
    "source_key": CHAILOVE_CORE_ID,
    "source_dir": "libretro-chailove",
    "output_path": "dist/unix/chailove_libretro.so",
    "artifact_name": CHAILOVE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/chailove_libretro.info",
    "metadata_artifact_name": "chailove_libretro.info",
    "targets": ["arm64", "armhf"],
}

CHAILOVE_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/chailove/makefile-echo-compile.patch",
    "patch_sha256": (
        "e391fdc171a3a937212a43c9aba862e508ac0993d66826d05f54bac9fd361745"
    ),
    "source_path": "Makefile",
    "preimage_sha256": (
        "515528ffdbd85a03926be47b64cb7eae7775a2e7dc03460fb78b3e62270a64ff"
    ),
    "postimage_sha256": (
        "bcf6ca88fae9f569eb524793d7ca32eee414e5c6da7a164019cc59212a455deb"
    ),
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the chailove core must preserve its exact source, "
    "recipe, overlay, metadata, and target contract"
)


CHAILOVE_SORT_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/chailove/makefile-sort-wildcard-sources.patch",
    "patch_sha256": (
        "b884ba1e7eaf87a2b6b4dbb86a0dd32634a96ac63e00267895dfb436bd9672a7"
    ),
    "source_path": "Makefile.common",
    "preimage_sha256": (
        "102b5bdd1cde3dbc351c9adf2a980c1366178188de84a3cdbdc38177408624e3"
    ),
    "postimage_sha256": (
        "41fb5860c3604d83d5ea9551bc34e7f689ec69a2e87f3c5f3d8b5d59ac0b77d0"
    ),
}


def chailove_spec_is_well_formed(spec: object) -> bool:
    """Require ChaiLove's exact immutable catalog identity."""

    identity = CHAILOVE_SPEC_IDENTITY
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
                "overlays": {
                    "arm64": [dict(CHAILOVE_OVERLAY), dict(CHAILOVE_SORT_OVERLAY)],
                    "armhf": [dict(CHAILOVE_OVERLAY), dict(CHAILOVE_SORT_OVERLAY)],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


CHAILOVE_LOG_CONTRACT_ID = "chailove-c-asm-v1"
CHAILOVE_EXPECTED_C_COMPILE_COUNT = {"arm64": 71, "armhf": 71}
CHAILOVE_EXPECTED_CXX_COMPILE_COUNT = {"arm64": 30, "armhf": 30}
CHAILOVE_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 1, "armhf": 1}
_PAIR = "541aa89d6b70ae787bbe284140321b0014ec546846965d6d8e5e4ab62b5672b2"
CHAILOVE_EXPECTED_COMPILE_PAIR_SHA256 = {"arm64": _PAIR, "armhf": _PAIR}
CHAILOVE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "3da5d37977aa77aeafb9919cc7113a81ae0b85b48384584f55398b763d19659f",
    "armhf": "c00ef6630967a8f1b4ae178c109dd2c0b3dfb59a84fdbc92efed20a1d2b962b9",
}
_LINK_OBJ = "a5be3335b273e468942a037c99546d168131d28c310d89941f0aabbbd3cb2368"
CHAILOVE_EXPECTED_LINK_OBJECT_SHA256 = {"arm64": _LINK_OBJ, "armhf": _LINK_OBJ}
CHAILOVE_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "arm64": _LINK_OBJ,
    "armhf": _LINK_OBJ,
}
_LINK_OPTIONS = (
    "-lpthread",
    "-lpthread",
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-Wl,-no-undefined",
    "-lm",
)
CHAILOVE_EXPECTED_LINK_OPTIONS = {
    "arm64": _LINK_OPTIONS,
    "armhf": _LINK_OPTIONS,
}

CHAILOVE_LOG_CONTRACT = CAsmLogContract(
    core_id=CHAILOVE_CORE_ID,
    expected_c_compile_count=CHAILOVE_EXPECTED_C_COMPILE_COUNT,
    expected_asm_compile_count=CHAILOVE_EXPECTED_ASM_COMPILE_COUNT,
    expected_compile_pair_sha256=CHAILOVE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        CHAILOVE_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=CHAILOVE_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=CHAILOVE_BUILD_ARTIFACT_NAME,
    expected_link_options=CHAILOVE_EXPECTED_LINK_OPTIONS,
    source_commit=CHAILOVE_SOURCE_COMMIT,
    source_tree=CHAILOVE_SOURCE_TREE,
    expected_cxx_compile_count=CHAILOVE_EXPECTED_CXX_COMPILE_COUNT,
    expected_link_language="cxx",
    expected_raw_link_object_sha256=CHAILOVE_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def chailove_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove ChaiLove's exact C/C++/assembly compile set and C++ link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        CHAILOVE_LOG_CONTRACT,
    )


__all__ = [
    "CHAILOVE_BUILD_ARTIFACT_NAME",
    "CHAILOVE_CORE_ID",
    "CHAILOVE_LOG_CONTRACT_ID",
    "CHAILOVE_SOURCE_COMMIT",
    "CHAILOVE_SOURCE_TREE",
    "CHAILOVE_SPEC_IDENTITY",
    "chailove_log_proves_contract",
    "chailove_spec_is_well_formed",
]
