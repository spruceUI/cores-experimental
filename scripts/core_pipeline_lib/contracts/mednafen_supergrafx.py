"""Exact Mednafen SuperGrafx native-version mixed-language compile/link contract.

SuperGrafx uses the shared compile/link proof standard (like handy): the
reviewed compile and link commands are proven exactly via
``mixed_language_log_proves_contract`` (which sorts compile invocations, so
parallel-interleaved build logs are accepted). The former full-log-envelope
proof was dropped in favour of that single shared standard.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


MEDNAFEN_SUPERGRAFX_CORE_ID = "mednafen_supergrafx"
MEDNAFEN_SUPERGRAFX_BUILD_ARTIFACT_NAME = "mednafen_supergrafx_libretro.so"
MEDNAFEN_SUPERGRAFX_LOG_CONTRACT_ID = "mednafen-supergrafx-mixed-language-v1"
MEDNAFEN_SUPERGRAFX_LOG_PROOF_KIND = "core-arch-source"
MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION = " 3c6fcd3"

MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_supergrafx.yml",
    "source_url": (
        "https://github.com/libretro/beetle-supergrafx-libretro.git"
    ),
    "source_requested_ref": "refs/heads/master",
    "source_commit": "3c6fcd3deded54ebecd69408f108407ac03d11b5",
    "source_tree": "076a59d1084ebf3a6ab80f4b5a144fa865c46c9b",
    "source_key": MEDNAFEN_SUPERGRAFX_CORE_ID,
    "source_dir": "libretro-mednafen_supergrafx",
    "output_path": "dist/unix/mednafen_supergrafx_libretro.so",
    "artifact_name": MEDNAFEN_SUPERGRAFX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_supergrafx_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_supergrafx_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "cxx",
    "native_makefile": "Makefile",
}

MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_COUNT = 89
MEDNAFEN_SUPERGRAFX_EXPECTED_LANGUAGE_COUNTS = {"c": 60, "cxx": 29}
MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "923c9d324bbdbfac0997c2a25125892f7a80b56a2d422241ae1c016df50bcaae"
)
MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "0f4a557367fc2e995f57f7123f207d5e66141b331ec045ec55679fd8311fae42",
    "armhf": "d3f2b5c5a051b9805a69eb57d806061c6d1d6673dc16ded4e6a4b3208d318a97",
}
MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OBJECT_SHA256 = (
    "d19c284b8eaccc4eb3accf92193eb506e3c2f8ba0e85d238aef754c5a832ebef"
)
MEDNAFEN_SUPERGRAFX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "d19c284b8eaccc4eb3accf92193eb506e3c2f8ba0e85d238aef754c5a832ebef"
)
MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OPTIONS = (
    "-lrt",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)


MEDNAFEN_SUPERGRAFX_SORT_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/mednafen_supergrafx/makefile-sort-wildcard-sources.patch",
    "patch_sha256": (
        "8df0614ce8fe5041da1f71770d3b4561d25ab7ee1f63e595a5746696e80d04fe"
    ),
    "source_path": "Makefile.common",
    "preimage_sha256": (
        "2c5c33333abdd67f624d347c2d18b0d34f9a44d83a55750b4b4bdce72f223b8b"
    ),
    "postimage_sha256": (
        "35d85aa7e7c59b49bc62dce0ea6dbc74bca7c89ea49cd6f843073cce883f72e9"
    ),
}


def mednafen_supergrafx_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable SuperGrafx catalog identity."""

    identity = MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "overlays": {
                    "arm64": [dict(MEDNAFEN_SUPERGRAFX_SORT_OVERLAY)],
                    "armhf": [dict(MEDNAFEN_SUPERGRAFX_SORT_OVERLAY)],
                },
                "git_version": {
                    "derivation": (
                        MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_DERIVATION
                    ),
                    "value": MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION,
                    "compiler_scope": identity["compiler_scope"],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def mednafen_supergrafx_mixed_language_contract() -> MixedLanguageLogContract:
    """Return SuperGrafx's exact compile/link proof parameters."""

    return MixedLanguageLogContract(
        core_id=MEDNAFEN_SUPERGRAFX_CORE_ID,
        expected_compile_count=MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_COUNT,
        expected_language_counts=MEDNAFEN_SUPERGRAFX_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            MEDNAFEN_SUPERGRAFX_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=(
            MEDNAFEN_SUPERGRAFX_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        build_artifact_name=MEDNAFEN_SUPERGRAFX_BUILD_ARTIFACT_NAME,
        expected_link_options=MEDNAFEN_SUPERGRAFX_EXPECTED_LINK_OPTIONS,
        source_commit=MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY[
            "source_commit"
        ],
        source_tree=MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY[
            "source_tree"
        ],
    )


def mednafen_supergrafx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove SuperGrafx's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        mednafen_supergrafx_mixed_language_contract(),
    )
