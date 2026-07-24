"""Exact Potator native-version C-only compile/link contract.

Potator uses the shared C-only compile/link proof standard: the reviewed
compile and link commands are proven exactly via ``c_only_log_proves_contract``
(which sorts compile invocations, so parallel-interleaved build logs are
accepted). The former full-log-envelope proof (which also pinned the exact
compiler warning/note lines) was dropped in favour of that single shared
standard.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


POTATOR_CORE_ID = "potator"
POTATOR_BUILD_ARTIFACT_NAME = "potator_libretro.so"
POTATOR_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
POTATOR_NATIVE_GIT_VERSION = " 227c5f6"

POTATOR_EXPECTED_COMPILE_COUNT = 8
POTATOR_EXPECTED_COMPILE_PAIR_SHA256 = (
    "c7f0cb2df934eca3d9372fbc375c7c098df79b8b40aaa439f656637a981590c7"
)
POTATOR_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "c27678726df3b888908cdab59ac33e5d2233d33e0d00c768ff8ff124b654242f",
    "armhf": "b4263b98ada6e3cef50c363f0e5f64ac73fb8afdbc5aa5edcc0dee117b562bf6",
}
POTATOR_EXPECTED_LINK_OBJECT_SHA256 = (
    "870d598839dbcbdc3b58bf22fec6550ea3a57af6ccdf7438e5d3da90428f43fc"
)
POTATOR_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "372cf00433195e01a541c0a348b3d528e8a0fee5156ae002fe23f64efe9f025a"
)
POTATOR_SEMANTIC_PATH_ALIASES = (
    ("../../platform/libretro/", "platform/libretro/"),
    ("../../common/", "common/"),
)
POTATOR_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)

POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-potator.yml",
    "source_url": "https://github.com/libretro/potator.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "227c5f6f3ce74d32e9002ce24c1420288559a860",
    "source_tree": "9111933525a4508075937f251829132cf2081ba9",
    "source_key": POTATOR_CORE_ID,
    "source_dir": "libretro-potator",
    "output_path": "dist/unix/potator_libretro.so",
    "artifact_name": POTATOR_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/potator_libretro.info",
    "metadata_artifact_name": "potator_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "platform/libretro/Makefile",
    "compiler_scope": "c",
}


def potator_spec_is_well_formed(spec: object) -> bool:
    """Require Potator's complete immutable catalog identity."""

    identity = POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "git_version": {
                    "derivation": POTATOR_NATIVE_GIT_VERSION_DERIVATION,
                    "value": POTATOR_NATIVE_GIT_VERSION,
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


def potator_c_only_contract() -> COnlyLogContract:
    """Return Potator's exact compile/link proof parameters."""

    return COnlyLogContract(
        core_id=POTATOR_CORE_ID,
        expected_compile_count=POTATOR_EXPECTED_COMPILE_COUNT,
        expected_compile_pair_sha256=POTATOR_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            POTATOR_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=POTATOR_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=POTATOR_BUILD_ARTIFACT_NAME,
        expected_link_options=POTATOR_EXPECTED_LINK_OPTIONS,
        source_commit=POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        expected_raw_link_object_sha256=(
            POTATOR_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        semantic_path_aliases=POTATOR_SEMANTIC_PATH_ALIASES,
    )


def potator_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Potator's exact compile and link commands for one architecture."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        potator_c_only_contract(),
    )
