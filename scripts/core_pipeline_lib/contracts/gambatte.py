"""Exact Gambatte mixed-language build-log contract."""

from __future__ import annotations

from .mixed_language import MixedLanguageLogContract, mixed_language_log_proves_contract


GAMBATTE_CORE_ID = "gambatte"
GAMBATTE_EXPECTED_COMPILE_COUNT = 47
GAMBATTE_EXPECTED_LANGUAGE_COUNTS = {"c": 16, "cxx": 31}
GAMBATTE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "41da9360e228fcf28b2f063e5e72f48b22d6bfce3dd4844d7439ababc0db2e87"
)
GAMBATTE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "aa39c9d63b45dc2c0e71b207864c3ec37ccf9249fa48492302763dd0c74650ed",
    "armhf": "afa4a906c570592ceed13db5ed41f0380be0e13fc5a206df19336b6fbfbbc3d8",
}
GAMBATTE_EXPECTED_LINK_OBJECT_SHA256 = (
    "3ff42dabb0b5e12d27e31d852fb27e43e2a308d00a2fc030a27b1f4645e8c7d8"
)
GAMBATTE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "9cd855ee762f60b71d8f5468292ec91e255cb2dbe83f10613ea6c2e64abdc600"
)
GAMBATTE_BUILD_ARTIFACT_NAME = "gambatte_libretro.so"
GAMBATTE_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,-version-script=libgambatte/libretro/link.T",
)
GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gambatte.yml",
    "source_url": "https://github.com/libretro/gambatte-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "dfc165599f3f1068c40a0b7ad6fe5f161283d483",
    "source_tree": "5ca06b386819d5a99f83531d38d88d1d04db426c",
    "source_key": GAMBATTE_CORE_ID,
    "source_dir": "libretro-gambatte",
    "output_path": "dist/unix/gambatte_libretro.so",
    "artifact_name": GAMBATTE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/gambatte_libretro.info",
    "metadata_artifact_name": "gambatte_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "cxx",
    "native_makefile": "Makefile.libretro",
}
GAMBATTE_SEMANTIC_PATH_ALIASES = (
    ("libgambatte/src/../libretro/", "libgambatte/libretro/"),
    (
        "libgambatte/src/../libretro-common/",
        "libgambatte/libretro-common/",
    ),
)


def gambatte_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Gambatte's exact proof parameters from its owned constants."""

    return MixedLanguageLogContract(
        core_id=GAMBATTE_CORE_ID,
        expected_compile_count=GAMBATTE_EXPECTED_COMPILE_COUNT,
        expected_language_counts=GAMBATTE_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=GAMBATTE_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            GAMBATTE_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=GAMBATTE_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            GAMBATTE_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=GAMBATTE_BUILD_ARTIFACT_NAME,
        expected_link_options=GAMBATTE_EXPECTED_LINK_OPTIONS,
        source_commit=(
            GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
        ),
        source_tree=GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        semantic_path_aliases=GAMBATTE_SEMANTIC_PATH_ALIASES,
    )


def gambatte_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Gambatte's exact mixed C/C++ compile and link-object set."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        gambatte_mixed_language_contract(),
    )
