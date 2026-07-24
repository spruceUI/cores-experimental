"""Exact Stella 2014 mixed-language build-log contract."""

from __future__ import annotations

from .mixed_language import MixedLanguageLogContract, mixed_language_log_proves_contract


STELLA2014_CORE_ID = "stella2014"
STELLA2014_EXPECTED_COMPILE_COUNT = 98
STELLA2014_EXPECTED_LANGUAGE_COUNTS = {"c": 14, "cxx": 84}
STELLA2014_EXPECTED_COMPILE_PAIR_SHA256 = (
    "51ab0cd42b84d0573a25b5c7b73991a0bdb698a8bdd2a81d2738077c27aff934"
)
STELLA2014_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "bca67cc8501e904beb2d23df73c54c6c14201ce16ae4a78bcc6eea1b7b3034fb",
    "armhf": "a196253abf5bd25ba802930c269131f7c9befaddb2b14d24067f1b471be9cefd",
}
STELLA2014_EXPECTED_LINK_OBJECT_SHA256 = (
    "e96c30ea8cfb9b90a29f5a397ea319f8d62c462730c04d3cca832885c8e9f3d7"
)
STELLA2014_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "81e8d2aa540061e0f01093e03433d9f8124b037bb97922525a9ba88a4511e756"
)
STELLA2014_BUILD_ARTIFACT_NAME = "stella2014_libretro.so"
STELLA2014_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-stella2014.yml",
    "source_url": "https://github.com/libretro/stella2014-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "4a7da82595d27b8df7af1ecb467a64b642a41bc9",
    "source_tree": "25eb55b1241824f7003eb3006847870672bbe4b2",
    "source_key": STELLA2014_CORE_ID,
    "source_dir": "libretro-stella2014",
    "output_path": "dist/unix/stella2014_libretro.so",
    "artifact_name": STELLA2014_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/stella2014_libretro.info",
    "metadata_artifact_name": "stella2014_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
}
STELLA2014_SEMANTIC_PATH_ALIASES = (
    ("stella/../libretro-common/", "libretro-common/"),
)


def stella2014_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Stella 2014's exact proof parameters from its owned constants."""

    return MixedLanguageLogContract(
        core_id=STELLA2014_CORE_ID,
        expected_compile_count=STELLA2014_EXPECTED_COMPILE_COUNT,
        expected_language_counts=STELLA2014_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=STELLA2014_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            STELLA2014_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=STELLA2014_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            STELLA2014_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=STELLA2014_BUILD_ARTIFACT_NAME,
        expected_link_options=STELLA2014_EXPECTED_LINK_OPTIONS,
        source_commit=(
            STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
        ),
        source_tree=STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        semantic_path_aliases=STELLA2014_SEMANTIC_PATH_ALIASES,
    )


def stella2014_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        stella2014_mixed_language_contract(),
    )
