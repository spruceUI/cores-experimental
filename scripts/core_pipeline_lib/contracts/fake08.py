"""Exact fake-08 (libretro PICO-8) mixed-language build-log contract.

fake08 is not a libretro-super core: the pipeline direct-clones
``jtothebell/fake-08`` and runs ``make -C platform/libretro`` (the ``direct-make``
driver with a ``make_subdir`` and ``make_args: ["V=1"]`` to flip its ``Q := @``
echo guard so the compile argv is visible). Its Makefile sets ``CC = $(CXX)``, so
all 56 translation units — 36 ``.c`` and 20 ``.cpp`` — compile with the C++
driver; this contract sets ``cxx_compiler_compiles_c`` to admit the ``.c`` units
under g++ (a ``.cpp`` under gcc is still rejected, and the exact per-unit compiler
stays pinned by the invocation sha256). Objects live two directories up from the
build dir (``../../libs/…``), so a single ``("../../","")`` alias contains them.
The C++ driver links the exact object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


FAKE08_CORE_ID = "fake08"
FAKE08_BUILD_ARTIFACT_NAME = "fake08_libretro.so"

FAKE08_SOURCE_COMMIT = "814991a2571ad3970e386cef48f3b148aa1c27b9"
FAKE08_SOURCE_TREE = "5c4f211679d422eb7ac5883730b4a9d583a27fef"

FAKE08_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-fake08.yml",
    "source_url": "https://github.com/jtothebell/fake-08.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": FAKE08_SOURCE_COMMIT,
    "source_tree": FAKE08_SOURCE_TREE,
    "source_dir": "fake-08",
    "output_path": "platform/libretro/fake08_libretro.so",
    "artifact_name": FAKE08_BUILD_ARTIFACT_NAME,
    "make_subdir": "platform/libretro",
    "metadata_source_path": "/libretro-super/dist/info/fake08_libretro.info",
    "metadata_artifact_name": "fake08_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the fake08 core must preserve its exact direct-make "
    "source, recipe, metadata, and target contract"
)


def fake08_spec_is_well_formed(spec: object) -> bool:
    """Require fake-08's exact immutable direct-make catalog identity."""

    identity = FAKE08_SPEC_IDENTITY
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
                "make_args": ["V=1"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


FAKE08_LOG_CONTRACT_ID = "fake08-mixed-language-v1"
FAKE08_EXPECTED_COMPILE_COUNT = 56
FAKE08_EXPECTED_LANGUAGE_COUNTS = {"c": 36, "cxx": 20}
FAKE08_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e4c7b12a5307b65cc6a92b86e930cac1e02bb3b42194c7d67f9c1ef725b4e307"
)
FAKE08_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "a8441e1b3517fbddfdfce1083fb627d7a3635a1221b93ca61ab79fa492653f0a",
    "armhf": "5c8683caf884b7b3198eb6505fb0ef0db1b4a1bc0732ac913248d3049659c37a",
}
FAKE08_EXPECTED_LINK_OBJECT_SHA256 = (
    "1cb38c36e4f8cd745ed4d39770ebd875567488f6f8867aa736bbe8d2da524e7a"
)
FAKE08_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9cb859624d9a5622ba1866d7232b4cc88b056a474d257028f924c5a6bccfad44"
)
FAKE08_SEMANTIC_PATH_ALIASES = (("../../", ""),)
FAKE08_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-Wl,--no-undefined",
    "-lm",
)

FAKE08_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=FAKE08_CORE_ID,
    expected_compile_count=FAKE08_EXPECTED_COMPILE_COUNT,
    expected_language_counts=FAKE08_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=FAKE08_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        FAKE08_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=FAKE08_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=FAKE08_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=FAKE08_BUILD_ARTIFACT_NAME,
    expected_link_options=FAKE08_EXPECTED_LINK_OPTIONS,
    source_commit=FAKE08_SOURCE_COMMIT,
    source_tree=FAKE08_SOURCE_TREE,
    semantic_path_aliases=FAKE08_SEMANTIC_PATH_ALIASES,
    expected_link_language="cxx",
    cxx_compiler_compiles_c=True,
)


def fake08_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove fake-08's exact mixed C/C++ (all-g++) compile set and C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FAKE08_LOG_CONTRACT,
    )


__all__ = [
    "FAKE08_BUILD_ARTIFACT_NAME",
    "FAKE08_CORE_ID",
    "FAKE08_LOG_CONTRACT_ID",
    "FAKE08_SOURCE_COMMIT",
    "FAKE08_SOURCE_TREE",
    "FAKE08_SPEC_IDENTITY",
    "fake08_log_proves_contract",
    "fake08_spec_is_well_formed",
]
