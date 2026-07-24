"""Exact Handy mixed-language build-log contract."""

from __future__ import annotations

from .mixed_language import MixedLanguageLogContract, mixed_language_log_proves_contract


HANDY_CORE_ID = "handy"
HANDY_EXPECTED_COMPILE_COUNT = 25
HANDY_EXPECTED_LANGUAGE_COUNTS = {"c": 13, "cxx": 12}
HANDY_EXPECTED_COMPILE_PAIR_SHA256 = (
    "109cc9cda6b72017d06d9b8609d8d83c932e39b2d3e090b7189a325589597bf8"
)
HANDY_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "caa6a5c4aa106b2d6bc99354482eb046eeed44ab86078788e10950148e70c2e6",
    "armhf": "5167d8ee4d138e97512140c3ed268de1335d5555f5c3fcd6fa5ad719baec9ff8",
}
HANDY_EXPECTED_LINK_OBJECT_SHA256 = (
    "8e5e41451fbc58db71926e7fd76dfeef0a3af7a76f18063d4b0395b8d35c06e8"
)
HANDY_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "43bf4225ac480d9c31658ec7cb3c8695830a2b0029fcfe3e8ab0b47fbe6157ea"
)
HANDY_BUILD_ARTIFACT_NAME = "handy_libretro.so"
HANDY_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=libretro/link.T",
    "-Wl,-no-undefined",
)
HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-handy.yml",
    "source_url": "https://github.com/libretro/libretro-handy.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "bc55d462f0b2d6b073ea93dc552ebd73cec60fd1",
    "source_tree": "e8cbeec52b120a52c208037a281072656a899ea9",
    "source_key": HANDY_CORE_ID,
    "source_dir": "libretro-handy",
    "output_path": "dist/unix/handy_libretro.so",
    "artifact_name": HANDY_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/handy_libretro.info",
    "metadata_artifact_name": "handy_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "cxx",
    "native_makefile": "Makefile",
}


def handy_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Handy's exact proof parameters from its owned constants."""

    return MixedLanguageLogContract(
        core_id=HANDY_CORE_ID,
        expected_compile_count=HANDY_EXPECTED_COMPILE_COUNT,
        expected_language_counts=HANDY_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=HANDY_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            HANDY_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=HANDY_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=HANDY_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=HANDY_BUILD_ARTIFACT_NAME,
        expected_link_options=HANDY_EXPECTED_LINK_OPTIONS,
        source_commit=HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    )


def handy_log_proves_contract(
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
        handy_mixed_language_contract(),
    )
