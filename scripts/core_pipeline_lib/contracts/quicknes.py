"""Exact QuickNES C++ build-log contract."""

from __future__ import annotations

from .mixed_language import MixedLanguageLogContract, mixed_language_log_proves_contract


QUICKNES_CORE_ID = "quicknes"
QUICKNES_EXPECTED_COMPILE_COUNT = 30
QUICKNES_EXPECTED_LANGUAGE_COUNTS = {"cxx": 30}
QUICKNES_EXPECTED_COMPILE_PAIR_SHA256 = (
    "0701253cfc0f7e1ad7371a528f82f9c9276feb6ff43746b8f480dd4f6e126339"
)
QUICKNES_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "f37409545147530e0c6b99da92e7939327f081d9d530521a091b0cd7f0bebf7e",
    "armhf": "b4e6714d223b5df846f458ddae3c143246203d8220c4e8e999c208522d20674a",
}
QUICKNES_EXPECTED_LINK_OBJECT_SHA256 = (
    "769a65de0b8945e21ecc83ca2d12b06ed7cb4fe4573e48e1a559da4c840dc6cc"
)
QUICKNES_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "61cb7a19eaa75ae684a837381917f1871f2b72e7088f51e9ce14a4a4470b5daa"
)
QUICKNES_BUILD_ARTIFACT_NAME = "quicknes_libretro.so"
QUICKNES_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
)
QUICKNES_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-quicknes.yml",
    "source_url": "https://github.com/libretro/QuickNES_Core.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "26bb785c9deddb66a17717b21bb4e328f03ade32",
    "source_tree": "52de71e4e1acc5a4a039b07f7ed67d425df97a89",
    "source_key": QUICKNES_CORE_ID,
    "source_dir": "libretro-quicknes",
    "output_path": "dist/unix/quicknes_libretro.so",
    "artifact_name": QUICKNES_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/quicknes_libretro.info",
    "metadata_artifact_name": "quicknes_libretro.info",
    "targets": ["arm64", "armhf"],
    "git_version": {
        "derivation": "hyphen-short7-v1",
        "value": "-26bb785",
        "compiler_scope": "cxx",
    },
}


def quicknes_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable QuickNES catalog identity."""

    identity = QUICKNES_GIT_VERSION_SPEC_IDENTITY
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
                "git_version": identity["git_version"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def quicknes_cxx_contract() -> MixedLanguageLogContract:
    """Return QuickNES's exact C++ proof parameters."""

    return MixedLanguageLogContract(
        core_id=QUICKNES_CORE_ID,
        expected_compile_count=QUICKNES_EXPECTED_COMPILE_COUNT,
        expected_language_counts=QUICKNES_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=QUICKNES_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            QUICKNES_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=QUICKNES_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            QUICKNES_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=QUICKNES_BUILD_ARTIFACT_NAME,
        expected_link_options=QUICKNES_EXPECTED_LINK_OPTIONS,
        source_commit=QUICKNES_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=QUICKNES_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    )


def quicknes_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove QuickNES's exact C++ compile and link-object set."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        quicknes_cxx_contract(),
    )
