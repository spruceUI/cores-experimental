"""Exact LowRes NX native-version C-only compile/link contract.

LowRes NX uses the shared C-only compile/link proof standard: the reviewed
compile and link commands are proven exactly via ``c_only_log_proves_contract``
(which sorts compile invocations, so parallel-interleaved build logs are
accepted). Its promoted source/build records are still bound through the golden
helpers below; the former full-log-envelope proof was dropped in favour of the
shared standard.
"""

from __future__ import annotations

import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


LOWRESNX_CORE_ID = "lowresnx"
LOWRESNX_BUILD_ARTIFACT_NAME = "lowresnx_libretro.so"
LOWRESNX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
LOWRESNX_NATIVE_GIT_VERSION = " 35adc1a"
LOWRESNX_EXPECTED_COMPILE_COUNT = 43
LOWRESNX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "6856367616793c011df7d718b09d2d3958c8fdcaae59c2a5a540544444897e42"
)
LOWRESNX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "0ad619324b9b9f918012fb410fc74414d5bdc6040d1a30655b1851efcd722182",
    "armhf": "eaf963d5059611adfc351603441a971e28c598e6c214a1a6976684dc2aae404c",
}
LOWRESNX_EXPECTED_LINK_OBJECT_SHA256 = (
    "4e00c500b7f8876248852a2e64e02644231259482e254126e29036797e32f515"
)
LOWRESNX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "7e0db66c7971f3a2075b2887d6610afe8a3822e81787e066bd25f9d6f6fa6574"
)
LOWRESNX_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=./link.T",
    "-Wl,-no-undefined",
    "-lm",
)
LOWRESNX_SEMANTIC_PATH_ALIASES = (
    ("../../core/", "core/"),
    ("../../libretro/", "libretro/"),
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-lowresnx.yml",
    "source_url": "https://github.com/timoinutilis/lowres-nx.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "35adc1a215e975be964b2ef4b652117acd7beba1",
    "source_tree": "766c70ca84d3a48769781072913a01db7f488a7b",
    "source_key": LOWRESNX_CORE_ID,
    "source_dir": "libretro-lowresnx",
    "output_path": "dist/unix/lowresnx_libretro.so",
    "artifact_name": LOWRESNX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/lowresnx_libretro.info",
    "metadata_artifact_name": "lowresnx_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "platform/LibRetro/Makefile",
    "compiler_scope": "c",
}


def lowresnx_spec_is_well_formed(spec: object) -> bool:
    """Require LowRes NX's complete immutable catalog identity."""

    identity = LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": LOWRESNX_NATIVE_GIT_VERSION_DERIVATION,
                    "value": LOWRESNX_NATIVE_GIT_VERSION,
                    "compiler_scope": "c",
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def lowresnx_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed LowRes NX tree."""

    identity = LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == LOWRESNX_CORE_ID
        and isinstance(source, dict)
        and source
        == {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
    )


def lowresnx_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted LowRes NX native-version build record."""

    identity = LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and lowresnx_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": LOWRESNX_NATIVE_GIT_VERSION_DERIVATION,
                "value": LOWRESNX_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def lowresnx_c_only_contract() -> COnlyLogContract:
    """Return LowRes NX's exact compile/link proof parameters."""

    return COnlyLogContract(
        core_id=LOWRESNX_CORE_ID,
        expected_compile_count=LOWRESNX_EXPECTED_COMPILE_COUNT,
        expected_compile_pair_sha256=LOWRESNX_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            LOWRESNX_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=LOWRESNX_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=LOWRESNX_BUILD_ARTIFACT_NAME,
        expected_link_options=LOWRESNX_EXPECTED_LINK_OPTIONS,
        source_commit=LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        expected_raw_link_object_sha256=(
            LOWRESNX_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
        semantic_path_aliases=LOWRESNX_SEMANTIC_PATH_ALIASES,
    )


def lowresnx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove LowRes NX's exact compile and link commands for one architecture."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        lowresnx_c_only_contract(),
    )
