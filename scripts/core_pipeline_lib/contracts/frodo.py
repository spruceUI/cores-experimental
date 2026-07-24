"""Exact Frodo (libretro C64) mixed-language build-log contract.

Frodo is a mixed C/C++ libretro-super core built from the source root with no
``../../`` object prefixes and no CMake. Its 62 translation units (35 C++, 27 C)
are each compiled once with a commit-derived ``-DGIT_VERSION`` token and linked
by the C++ driver; the per-architecture compile invocation sha256 pins that
exact token and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


FRODO_CORE_ID = "frodo"
FRODO_BUILD_ARTIFACT_NAME = "frodo_libretro.so"

FRODO_SOURCE_COMMIT = "29dd1864b89d903ed93f1d86d85636ef9e194359"
FRODO_SOURCE_TREE = "55052ca464a04805b21b6bae7ec9c00741644ded"

FRODO_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-frodo.yml",
    "source_url": "https://github.com/libretro/frodo-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": FRODO_SOURCE_COMMIT,
    "source_tree": FRODO_SOURCE_TREE,
    "source_key": FRODO_CORE_ID,
    "source_dir": "libretro-frodo",
    "output_path": "dist/unix/frodo_libretro.so",
    "artifact_name": FRODO_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/frodo_libretro.info",
    "metadata_artifact_name": "frodo_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the frodo core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def frodo_spec_is_well_formed(spec: object) -> bool:
    """Require Frodo's exact immutable catalog identity."""

    identity = FRODO_SPEC_IDENTITY
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


FRODO_LOG_CONTRACT_ID = "frodo-mixed-language-v1"
FRODO_EXPECTED_COMPILE_COUNT = 62
FRODO_EXPECTED_LANGUAGE_COUNTS = {"cxx": 35, "c": 27}
FRODO_EXPECTED_COMPILE_PAIR_SHA256 = (
    "991121ad02e9f1a6a94a75a538f500e65041e948acd86e83df12bd6f24ef59e8"
)
FRODO_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "08335858b9213f501e71f20372afee67b7691fb28fa9a3f8d4ce59251ac229ab",
    "armhf": "f146f7d9e8d70dcec07539e8c2daa69296a4efc3029a3ee981f4e38a0bfff804",
}
FRODO_EXPECTED_LINK_OBJECT_SHA256 = (
    "d914676a546079cf4ea040aac1787d2996154b3b4e05102365e37409bc6ab790"
)
FRODO_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "950c8850a3e45ada490ed4316719d3d05ce9909b934b8a9e78c9db5db2882da2"
)
FRODO_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=libretro/link.T",
    "-lm",
    "-fPIC",
)

FRODO_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=FRODO_CORE_ID,
    expected_compile_count=FRODO_EXPECTED_COMPILE_COUNT,
    expected_language_counts=FRODO_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=FRODO_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        FRODO_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=FRODO_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=FRODO_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=FRODO_BUILD_ARTIFACT_NAME,
    expected_link_options=FRODO_EXPECTED_LINK_OPTIONS,
    source_commit=FRODO_SOURCE_COMMIT,
    source_tree=FRODO_SOURCE_TREE,
    expected_link_language="cxx",
)


def frodo_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Frodo's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FRODO_LOG_CONTRACT,
    )


__all__ = [
    "FRODO_BUILD_ARTIFACT_NAME",
    "FRODO_CORE_ID",
    "FRODO_LOG_CONTRACT_ID",
    "FRODO_SOURCE_COMMIT",
    "FRODO_SOURCE_TREE",
    "FRODO_SPEC_IDENTITY",
    "frodo_log_proves_contract",
    "frodo_spec_is_well_formed",
]
