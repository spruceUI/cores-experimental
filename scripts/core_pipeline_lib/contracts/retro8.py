"""Exact retro8 (libretro PICO-8) mixed-language build-log contract.

retro8 is a mixed C/C++ libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its 44 translation units (10 C++, 34 C)
are each compiled once with a commit-derived ``-DGIT_VERSION`` token and linked
by the C++ driver; the per-architecture compile invocation sha256 pins that
exact token and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


RETRO8_CORE_ID = "retro8"
RETRO8_BUILD_ARTIFACT_NAME = "retro8_libretro.so"

RETRO8_SOURCE_COMMIT = "ddc06a142398ee9755894b3f0bb17c8dc428151d"
RETRO8_SOURCE_TREE = "b2d7603bffe84e98130bc62365d65d347d22521e"

RETRO8_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-retro8.yml",
    "source_url": "https://github.com/libretro/retro8.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": RETRO8_SOURCE_COMMIT,
    "source_tree": RETRO8_SOURCE_TREE,
    "source_key": RETRO8_CORE_ID,
    "source_dir": "libretro-retro8",
    "output_path": "dist/unix/retro8_libretro.so",
    "artifact_name": RETRO8_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/retro8_libretro.info",
    "metadata_artifact_name": "retro8_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the retro8 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def retro8_spec_is_well_formed(spec: object) -> bool:
    """Require retro8's exact immutable catalog identity."""

    identity = RETRO8_SPEC_IDENTITY
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


RETRO8_LOG_CONTRACT_ID = "retro8-mixed-language-v1"
RETRO8_EXPECTED_COMPILE_COUNT = 44
RETRO8_EXPECTED_LANGUAGE_COUNTS = {"c": 34, "cxx": 10}
RETRO8_EXPECTED_COMPILE_PAIR_SHA256 = (
    "6dc0dccc9b5aee167f982bc3a4b63dca5a8d8aa6b75fd4b51ed5bc69f3cda210"
)
RETRO8_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "3c4fd4a1fcd3a4e7bc8a27df9e4afd2e70b78975eb9e69176701be8d91afa51b",
    "armhf": "a9443f78bf373080a117c624ecc0e89896bf6c0e4928e655d0db94eab2539420",
}
RETRO8_EXPECTED_LINK_OBJECT_SHA256 = (
    "87b51539091a502dec86b811204580a3a9942c779f42e8f7582e36511862651a"
)
RETRO8_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "a315ca24ffe90603e81d7c7a58d83628b6f27931c9e2143e0c04459c4c2bfc5a"
)
RETRO8_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./link.T",
    "-Wl,--no-undefined",
    "-lpthread",
    "-lm",
)

RETRO8_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=RETRO8_CORE_ID,
    expected_compile_count=RETRO8_EXPECTED_COMPILE_COUNT,
    expected_language_counts=RETRO8_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=RETRO8_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        RETRO8_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=RETRO8_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=RETRO8_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=RETRO8_BUILD_ARTIFACT_NAME,
    expected_link_options=RETRO8_EXPECTED_LINK_OPTIONS,
    source_commit=RETRO8_SOURCE_COMMIT,
    source_tree=RETRO8_SOURCE_TREE,
    expected_link_language="cxx",
)


def retro8_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove retro8's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        RETRO8_LOG_CONTRACT,
    )


__all__ = [
    "RETRO8_BUILD_ARTIFACT_NAME",
    "RETRO8_CORE_ID",
    "RETRO8_LOG_CONTRACT_ID",
    "RETRO8_SOURCE_COMMIT",
    "RETRO8_SOURCE_TREE",
    "RETRO8_SPEC_IDENTITY",
    "retro8_log_proves_contract",
    "retro8_spec_is_well_formed",
]
