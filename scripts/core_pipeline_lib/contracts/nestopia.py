"""Exact Nestopia C++ build-log contract."""

from __future__ import annotations

from .mixed_language import MixedLanguageLogContract, mixed_language_log_proves_contract


NESTOPIA_CORE_ID = "nestopia"
NESTOPIA_EXPECTED_COMPILE_COUNT = 296
NESTOPIA_EXPECTED_LANGUAGE_COUNTS = {"cxx": 296}
NESTOPIA_EXPECTED_COMPILE_PAIR_SHA256 = (
    "93d40fc1faab944a39c390424416570ff7cd7e296dde6c363e6a9c26f529995f"
)
NESTOPIA_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "37a64ac88dc0271487810a2371b95f5c312dfa76f160f8a5622f615819db9b4d",
    "armhf": "ee9d9d6620d28a0142a5ed6264c5a3374e7771e8addc5dd67d73f6042688be32",
}
NESTOPIA_EXPECTED_LINK_OBJECT_SHA256 = (
    "eb024c90f6cf386ef3103e3f8176aff70c27f78a45f4f08786006969e7756f40"
)
NESTOPIA_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "019ff56cd1d9ab79fc4ac6b852d7fd421ac6e53ca4f4313a85b43f31de7976cc"
)
NESTOPIA_BUILD_ARTIFACT_NAME = "nestopia_libretro.so"
NESTOPIA_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
)
NESTOPIA_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-nestopia.yml",
    "source_url": "https://github.com/libretro/nestopia.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "b0fd87dd07e3c52903435d302b04e5e97796f127",
    "source_tree": "43152d8aa00233ac56e27bdbce5cd3e77918bc60",
    "source_key": NESTOPIA_CORE_ID,
    "source_dir": "libretro-nestopia",
    "output_path": "dist/unix/nestopia_libretro.so",
    "artifact_name": NESTOPIA_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/nestopia_libretro.info",
    "metadata_artifact_name": "nestopia_libretro.info",
    "targets": ["arm64", "armhf"],
    "git_version": {
        "derivation": "hyphen-short7-v1",
        "value": "-b0fd87d",
        "compiler_scope": "cxx",
    },
}
NESTOPIA_SEMANTIC_PATH_ALIASES = (
    ("../source/", "source/"),
    ("../libretro/", "libretro/"),
)


def nestopia_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable Nestopia catalog identity."""

    identity = NESTOPIA_GIT_VERSION_SPEC_IDENTITY
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


def nestopia_cxx_contract() -> MixedLanguageLogContract:
    """Return Nestopia's exact C++ proof parameters."""

    return MixedLanguageLogContract(
        core_id=NESTOPIA_CORE_ID,
        expected_compile_count=NESTOPIA_EXPECTED_COMPILE_COUNT,
        expected_language_counts=NESTOPIA_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=NESTOPIA_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            NESTOPIA_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=NESTOPIA_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            NESTOPIA_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=NESTOPIA_BUILD_ARTIFACT_NAME,
        expected_link_options=NESTOPIA_EXPECTED_LINK_OPTIONS,
        source_commit=NESTOPIA_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=NESTOPIA_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        semantic_path_aliases=NESTOPIA_SEMANTIC_PATH_ALIASES,
    )


def nestopia_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Nestopia's exact C++ compile and link-object set."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        nestopia_cxx_contract(),
    )
