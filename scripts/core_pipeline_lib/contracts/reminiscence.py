"""Exact REminiscence (libretro Flashback) mixed-language build-log contract.

reminiscence is a mixed C/C++ libretro-super core built from the source root
with no ``../../`` object prefixes and no CMake. Its 41 translation units are
each compiled once: all 30 C++ commands carry the commit-derived
``-DGIT_VERSION`` token, while the 11 C commands are hash-bound to its absence.
The C++ driver links the exact compiled object set, and the per-architecture
compile invocation sha256 pins those command-level details.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


REMINISCENCE_CORE_ID = "reminiscence"
REMINISCENCE_BUILD_ARTIFACT_NAME = "reminiscence_libretro.so"

REMINISCENCE_SOURCE_COMMIT = "b0eb4ff6479d3a0f9e327ba595533604713cdb27"
REMINISCENCE_SOURCE_TREE = "f5fef5de7e6213d6512b8a6036e21f93f237e985"

REMINISCENCE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-reminiscence.yml",
    "source_url": "https://github.com/libretro/REminiscence.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": REMINISCENCE_SOURCE_COMMIT,
    "source_tree": REMINISCENCE_SOURCE_TREE,
    "source_key": REMINISCENCE_CORE_ID,
    "source_dir": "libretro-reminiscence",
    "output_path": "dist/unix/reminiscence_libretro.so",
    "artifact_name": REMINISCENCE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/reminiscence_libretro.info"
    ),
    "metadata_artifact_name": "reminiscence_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the reminiscence core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def reminiscence_spec_is_well_formed(spec: object) -> bool:
    """Require REminiscence's exact immutable catalog identity."""

    identity = REMINISCENCE_SPEC_IDENTITY
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


REMINISCENCE_LOG_CONTRACT_ID = "reminiscence-mixed-language-v1"
REMINISCENCE_EXPECTED_COMPILE_COUNT = 41
REMINISCENCE_EXPECTED_LANGUAGE_COUNTS = {"cxx": 30, "c": 11}
REMINISCENCE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "f10c8b394cafcc5e546973feafc0de9211264a4fc7a13702e0de5cf7c3a2f4f7"
)
REMINISCENCE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "4a6f4c1b0ea37572ae68b7f55af4fc207078e772ef6d19e0262daa6d545d6162",
    "armhf": "52f84c572a3aa358e25ed18edd8b33cdb6bde7177f55b912e35c463c3042a09a",
}
REMINISCENCE_EXPECTED_LINK_OBJECT_SHA256 = (
    "82bfc953baf0e0636c0cd6574af4076048313246ac6692778ca3cd6e3f1c1f2c"
)
REMINISCENCE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "82bfc953baf0e0636c0cd6574af4076048313246ac6692778ca3cd6e3f1c1f2c"
)
REMINISCENCE_EXPECTED_LINK_OPTIONS = (
    "-lrt",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)

REMINISCENCE_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=REMINISCENCE_CORE_ID,
    expected_compile_count=REMINISCENCE_EXPECTED_COMPILE_COUNT,
    expected_language_counts=REMINISCENCE_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=REMINISCENCE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        REMINISCENCE_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=REMINISCENCE_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        REMINISCENCE_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=REMINISCENCE_BUILD_ARTIFACT_NAME,
    expected_link_options=REMINISCENCE_EXPECTED_LINK_OPTIONS,
    source_commit=REMINISCENCE_SOURCE_COMMIT,
    source_tree=REMINISCENCE_SOURCE_TREE,
    expected_link_language="cxx",
)


def reminiscence_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove REminiscence's exact mixed C/C++ compile set and C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        REMINISCENCE_LOG_CONTRACT,
    )


__all__ = [
    "REMINISCENCE_BUILD_ARTIFACT_NAME",
    "REMINISCENCE_CORE_ID",
    "REMINISCENCE_LOG_CONTRACT_ID",
    "REMINISCENCE_SOURCE_COMMIT",
    "REMINISCENCE_SOURCE_TREE",
    "REMINISCENCE_SPEC_IDENTITY",
    "reminiscence_log_proves_contract",
    "reminiscence_spec_is_well_formed",
]
