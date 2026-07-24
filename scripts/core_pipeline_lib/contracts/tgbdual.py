"""Exact TGB Dual C++ build-log contract."""

from __future__ import annotations

from .mixed_language import MixedLanguageLogContract, mixed_language_log_proves_contract


TGBDUAL_CORE_ID = "tgbdual"
TGBDUAL_EXPECTED_COMPILE_COUNT = 9
TGBDUAL_EXPECTED_LANGUAGE_COUNTS = {"cxx": 9}
TGBDUAL_EXPECTED_COMPILE_PAIR_SHA256 = (
    "542e059152f969e44d6dd7f1b7c21c3d7bb6d5871d2e70391932c1d7e9524593"
)
TGBDUAL_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "62ec4bf64de3f51d36ae7cfcab4661d5d3d732f4b084072aaa44c53cddae4f54",
    "armhf": "b59f7ce2134d0eb9edcb2f7cbae58b9dbc6991141a993028d2cb438fe04bb640",
}
TGBDUAL_EXPECTED_LINK_OBJECT_SHA256 = (
    "aa052ddc7fd40dd2f4a6fd7ff1da866116140f6b85e23b2335ce55f275cbd8a0"
)
TGBDUAL_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "4d77f59831b406cf142f11f33451667352c8bb5bc8b4f620436fd866fd688814"
)
TGBDUAL_BUILD_ARTIFACT_NAME = "tgbdual_libretro.so"
TGBDUAL_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=libretro/link.T",
    "-fPIC",
)
TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-tgbdual.yml",
    "source_url": "https://github.com/libretro/tgbdual-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "bf816b096f1dca55ea805337d7c9e78d6b98d839",
    "source_tree": "96122db14e9117e875c7ecaec7e77519e8be5636",
    "source_key": TGBDUAL_CORE_ID,
    "source_dir": "libretro-tgbdual",
    "output_path": "dist/unix/tgbdual_libretro.so",
    "artifact_name": TGBDUAL_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/tgbdual_libretro.info",
    "metadata_artifact_name": "tgbdual_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "cxx",
    "native_makefile": "Makefile",
}


def tgbdual_cxx_contract() -> MixedLanguageLogContract:
    """Return TGB Dual's exact C++ proof parameters."""

    return MixedLanguageLogContract(
        core_id=TGBDUAL_CORE_ID,
        expected_compile_count=TGBDUAL_EXPECTED_COMPILE_COUNT,
        expected_language_counts=TGBDUAL_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=TGBDUAL_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            TGBDUAL_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=TGBDUAL_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            TGBDUAL_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=TGBDUAL_BUILD_ARTIFACT_NAME,
        expected_link_options=TGBDUAL_EXPECTED_LINK_OPTIONS,
        source_commit=TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    )


def tgbdual_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove TGB Dual's exact C++ compile and link-object set."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        tgbdual_cxx_contract(),
    )
