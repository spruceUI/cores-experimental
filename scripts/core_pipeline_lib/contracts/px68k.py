"""Exact PX68K (libretro Sharp X68000) mixed-language build-log contract.

px68k is a mixed C/C++ libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its 61 translation units (6 C++, 55 C)
are each compiled once with a commit-derived ``-DGIT_VERSION`` token and linked
by the C++ driver; the per-architecture compile invocation sha256 pins the exact
argv and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


PX68K_CORE_ID = "px68k"
PX68K_BUILD_ARTIFACT_NAME = "px68k_libretro.so"

PX68K_SOURCE_COMMIT = "cc45b55983b4d30c961a313a77df9bcf9461dc63"
PX68K_SOURCE_TREE = "eeb7afbc7ec5480788a29fa335f7be5802b0580f"

PX68K_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-px68k.yml",
    "source_url": "https://github.com/libretro/px68k-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": PX68K_SOURCE_COMMIT,
    "source_tree": PX68K_SOURCE_TREE,
    "source_key": PX68K_CORE_ID,
    "source_dir": "libretro-px68k",
    "output_path": "dist/unix/px68k_libretro.so",
    "artifact_name": PX68K_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/px68k_libretro.info",
    "metadata_artifact_name": "px68k_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the px68k core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def px68k_spec_is_well_formed(spec: object) -> bool:
    """Require PX68K's exact immutable catalog identity."""

    identity = PX68K_SPEC_IDENTITY
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


PX68K_LOG_CONTRACT_ID = "px68k-mixed-language-v1"
PX68K_EXPECTED_COMPILE_COUNT = 61
PX68K_EXPECTED_LANGUAGE_COUNTS = {"cxx": 6, "c": 55}
PX68K_EXPECTED_COMPILE_PAIR_SHA256 = (
    "6758e4fc5e17179d0b9a2f4b0e93fdd5355adf50ca3c66a1683e94a88eb41d92"
)
PX68K_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "957e7342b5d98ab89b1a9b29cecfac740d22b8dc4e8a1d2b149553a4603a661c",
    "armhf": "ecac90e29f1a7da81ccd4bcfe7509452df524659fa0664959f2eba96237d412b",
}
PX68K_EXPECTED_LINK_OBJECT_SHA256 = (
    "131b4c6f92424add97acc99bdca9f69936d9f5bcd78e02a0e73b151f9d8f01f5"
)
PX68K_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "131b4c6f92424add97acc99bdca9f69936d9f5bcd78e02a0e73b151f9d8f01f5"
)
PX68K_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)

PX68K_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=PX68K_CORE_ID,
    expected_compile_count=PX68K_EXPECTED_COMPILE_COUNT,
    expected_language_counts=PX68K_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=PX68K_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=PX68K_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=PX68K_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=PX68K_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=PX68K_BUILD_ARTIFACT_NAME,
    expected_link_options=PX68K_EXPECTED_LINK_OPTIONS,
    source_commit=PX68K_SOURCE_COMMIT,
    source_tree=PX68K_SOURCE_TREE,
    expected_link_language="cxx",
)


def px68k_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove PX68K's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        PX68K_LOG_CONTRACT,
    )


__all__ = [
    "PX68K_BUILD_ARTIFACT_NAME",
    "PX68K_CORE_ID",
    "PX68K_LOG_CONTRACT_ID",
    "PX68K_SOURCE_COMMIT",
    "PX68K_SOURCE_TREE",
    "PX68K_SPEC_IDENTITY",
    "px68k_log_proves_contract",
    "px68k_spec_is_well_formed",
]
