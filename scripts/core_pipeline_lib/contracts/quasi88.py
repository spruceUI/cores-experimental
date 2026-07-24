"""Exact QUASI88 (libretro PC-8801) mixed-language build-log contract.

QUASI88 is a mixed C/C++ libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its 70 translation units (6 C++, 64 C)
are each compiled once with a commit-derived ``-DGIT_VERSION`` token and linked
by the C++ driver; the per-architecture compile invocation sha256 pins that
exact token and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


QUASI88_CORE_ID = "quasi88"
QUASI88_BUILD_ARTIFACT_NAME = "quasi88_libretro.so"

QUASI88_SOURCE_COMMIT = "520e0a37ac0e9cf8b0536fe83fda3aacc9ba73bb"
QUASI88_SOURCE_TREE = "2e2ab44397253236e3b87ee2534cb7483ca90ce9"

QUASI88_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-quasi88.yml",
    "source_url": "https://github.com/libretro/quasi88-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": QUASI88_SOURCE_COMMIT,
    "source_tree": QUASI88_SOURCE_TREE,
    "source_key": QUASI88_CORE_ID,
    "source_dir": "libretro-quasi88",
    "output_path": "dist/unix/quasi88_libretro.so",
    "artifact_name": QUASI88_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/quasi88_libretro.info"
    ),
    "metadata_artifact_name": "quasi88_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the quasi88 core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def quasi88_spec_is_well_formed(spec: object) -> bool:
    """Require QUASI88's exact immutable catalog identity."""

    identity = QUASI88_SPEC_IDENTITY
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


QUASI88_LOG_CONTRACT_ID = "quasi88-mixed-language-v1"
QUASI88_EXPECTED_COMPILE_COUNT = 70
QUASI88_EXPECTED_LANGUAGE_COUNTS = {"cxx": 6, "c": 64}
QUASI88_EXPECTED_COMPILE_PAIR_SHA256 = (
    "f6470d91f6aee283e24eb787a120948c726c89295cab8e8c969cba9f85f900fa"
)
QUASI88_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "7e79268300f9fc99c00125ea2a4297c297c17743430265a7c2317ca1b0743ee8",
    "armhf": "18e6ac4a44d4c65f9b879ad6e100010cde17eb6ab4fadb2030b8aba6f0b3d2db",
}
QUASI88_EXPECTED_LINK_OBJECT_SHA256 = (
    "9692313ec04c1a327c56fbe5ca6d85dcf71051c9669eaecd4693b92e8d04d910"
)
QUASI88_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9692313ec04c1a327c56fbe5ca6d85dcf71051c9669eaecd4693b92e8d04d910"
)
QUASI88_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)

QUASI88_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=QUASI88_CORE_ID,
    expected_compile_count=QUASI88_EXPECTED_COMPILE_COUNT,
    expected_language_counts=QUASI88_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=QUASI88_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        QUASI88_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=QUASI88_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=QUASI88_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=QUASI88_BUILD_ARTIFACT_NAME,
    expected_link_options=QUASI88_EXPECTED_LINK_OPTIONS,
    source_commit=QUASI88_SOURCE_COMMIT,
    source_tree=QUASI88_SOURCE_TREE,
    expected_link_language="cxx",
)


def quasi88_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove QUASI88's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        QUASI88_LOG_CONTRACT,
    )


__all__ = [
    "QUASI88_BUILD_ARTIFACT_NAME",
    "QUASI88_CORE_ID",
    "QUASI88_LOG_CONTRACT_ID",
    "QUASI88_SOURCE_COMMIT",
    "QUASI88_SOURCE_TREE",
    "QUASI88_SPEC_IDENTITY",
    "quasi88_log_proves_contract",
    "quasi88_spec_is_well_formed",
]
