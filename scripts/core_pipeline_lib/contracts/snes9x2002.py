"""Exact Snes9x 2002 C-only build-log contract.

Snes9x 2002 is a C-only libretro-super core built from the source root (no
``../../`` object prefixes, so no semantic path alias). Its Makefile embeds a
commit-derived ``GIT_VERSION`` on each compile; the per-architecture compile
invocation sha256 pins that exact token, so no separate version guard is needed.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


SNES9X2002_CORE_ID = "snes9x2002"
SNES9X2002_BUILD_ARTIFACT_NAME = "snes9x2002_libretro.so"

SNES9X2002_SOURCE_COMMIT = "5bd8bd6d449be8a2ef7909e1aeb2bd8c9c0da8cb"
SNES9X2002_SOURCE_TREE = "ba0f22bc1e0eb80c21b6796326704cfe9af80465"

SNES9X2002_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-snes9x2002.yml",
    "source_url": "https://github.com/libretro/snes9x2002.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": SNES9X2002_SOURCE_COMMIT,
    "source_tree": SNES9X2002_SOURCE_TREE,
    "source_key": SNES9X2002_CORE_ID,
    "source_dir": "libretro-snes9x2002",
    "output_path": "dist/unix/snes9x2002_libretro.so",
    "artifact_name": SNES9X2002_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/snes9x2002_libretro.info"
    ),
    "metadata_artifact_name": "snes9x2002_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the snes9x2002 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def snes9x2002_spec_is_well_formed(spec: object) -> bool:
    """Require Snes9x 2002's exact immutable catalog identity."""

    identity = SNES9X2002_SPEC_IDENTITY
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


SNES9X2002_LOG_CONTRACT_ID = "snes9x2002-c-only-v1"
SNES9X2002_EXPECTED_COMPILE_COUNT = 30
SNES9X2002_EXPECTED_COMPILE_PAIR_SHA256 = (
    "b5cd97865178bd3e9f6954f15e7ac28c4351b40e56de72285aa83abc7f2681ab"
)
SNES9X2002_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "3254c8a7c8d8bd406e9eb56584d5265db8859e55b5661dc7cf3c18129a2c3136",
    "armhf": "38eb0c6dabbfa712c6d9730d5d2ed6b443fabbbb8243116b36933e7ef93b5b71",
}
SNES9X2002_EXPECTED_LINK_OBJECT_SHA256 = (
    "17535255732738f6c3658d1b2ef4f34516893017507ec3a5b8479a681b8b34fa"
)
SNES9X2002_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "22cea4d178cb40bc93bb9669a9b59bddfae0705d7c5db1bcd74a8e94d607bbf3"
)
SNES9X2002_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=libretro/link.T",
    "-Wl,--no-undefined",
    "-lm",
    "-fPIC",
)

SNES9X2002_LOG_CONTRACT = COnlyLogContract(
    core_id=SNES9X2002_CORE_ID,
    expected_compile_count=SNES9X2002_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=SNES9X2002_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        SNES9X2002_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=SNES9X2002_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=SNES9X2002_BUILD_ARTIFACT_NAME,
    expected_link_options=SNES9X2002_EXPECTED_LINK_OPTIONS,
    source_commit=SNES9X2002_SOURCE_COMMIT,
    source_tree=SNES9X2002_SOURCE_TREE,
    expected_raw_link_object_sha256=SNES9X2002_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def snes9x2002_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Snes9x 2002's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        SNES9X2002_LOG_CONTRACT,
    )


__all__ = [
    "SNES9X2002_BUILD_ARTIFACT_NAME",
    "SNES9X2002_CORE_ID",
    "SNES9X2002_LOG_CONTRACT_ID",
    "SNES9X2002_SOURCE_COMMIT",
    "SNES9X2002_SOURCE_TREE",
    "SNES9X2002_SPEC_IDENTITY",
    "snes9x2002_log_proves_contract",
    "snes9x2002_spec_is_well_formed",
]
