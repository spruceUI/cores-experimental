"""Exact Numero (libretro TI calculator) mixed-language build-log contract.

Numero (upstream nbarkhina/numero) is a mixed C/C++ libretro-super core whose
bundled deps are reached through mid-path ``..`` traversals — the wrapper and
libretro-common live at ``libnumero/src/../...`` and ezdib at
``libnumero/src/../../ezdib`` — so two ordered semantic path aliases normalize
both compile outputs and link operands. Its 38 translation units (26 C++, 12 C)
are compiled once each with a commit-derived ``-DGIT_VERSION`` token and linked
by the C++ driver; the per-architecture compile invocation sha256 pins the exact
argv and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


NUMERO_CORE_ID = "numero"
NUMERO_BUILD_ARTIFACT_NAME = "numero_libretro.so"

NUMERO_SOURCE_COMMIT = "0ffb2f4d1382d41675746cb37820d41d79d96309"
NUMERO_SOURCE_TREE = "970f0e7be440eff0f5612d27aafa5cdf10764307"

NUMERO_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-numero.yml",
    "source_url": "https://github.com/nbarkhina/numero.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": NUMERO_SOURCE_COMMIT,
    "source_tree": NUMERO_SOURCE_TREE,
    "source_key": NUMERO_CORE_ID,
    "source_dir": "libretro-numero",
    "output_path": "dist/unix/numero_libretro.so",
    "artifact_name": NUMERO_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/numero_libretro.info",
    "metadata_artifact_name": "numero_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the numero core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def numero_spec_is_well_formed(spec: object) -> bool:
    """Require Numero's exact immutable catalog identity."""

    identity = NUMERO_SPEC_IDENTITY
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
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


NUMERO_LOG_CONTRACT_ID = "numero-mixed-language-v1"
NUMERO_EXPECTED_COMPILE_COUNT = 38
NUMERO_EXPECTED_LANGUAGE_COUNTS = {"cxx": 26, "c": 12}
NUMERO_EXPECTED_COMPILE_PAIR_SHA256 = (
    "e49aea39cc5f1154ec1979ad884c890e30af32889cf4fef075da6ce9a3da57d6"
)
NUMERO_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "f7d5eec58695e383f778a7183ca927764f051d3e9e83bf96f6e79a2ea2049d24",
    "armhf": "619f332d5a411993b96f503570e08dffd8a84ef3cc34ed2fc24f533b5f5db13f",
}
NUMERO_EXPECTED_LINK_OBJECT_SHA256 = (
    "9450a6fb72f7fe74a3356f763b76b3a509683b9313c1f5ae8595a86381dcda16"
)
NUMERO_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "8a6aebc8ac088738eb281bb5ca8719c24887b5d610495ef8a6e6424a4979b0e2"
)
NUMERO_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,-version-script=libnumero/libretro/link.T",
)
NUMERO_SEMANTIC_PATH_ALIASES = (
    ("libnumero/src/../../", ""),
    ("libnumero/src/../", "libnumero/"),
)

NUMERO_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=NUMERO_CORE_ID,
    expected_compile_count=NUMERO_EXPECTED_COMPILE_COUNT,
    expected_language_counts=NUMERO_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=NUMERO_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=NUMERO_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=NUMERO_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=NUMERO_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=NUMERO_BUILD_ARTIFACT_NAME,
    expected_link_options=NUMERO_EXPECTED_LINK_OPTIONS,
    source_commit=NUMERO_SOURCE_COMMIT,
    source_tree=NUMERO_SOURCE_TREE,
    expected_link_language="cxx",
    semantic_path_aliases=NUMERO_SEMANTIC_PATH_ALIASES,
)


def numero_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Numero's exact mixed C/C++ compile set and matching C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        NUMERO_LOG_CONTRACT,
    )


__all__ = [
    "NUMERO_BUILD_ARTIFACT_NAME",
    "NUMERO_CORE_ID",
    "NUMERO_LOG_CONTRACT_ID",
    "NUMERO_SOURCE_COMMIT",
    "NUMERO_SOURCE_TREE",
    "NUMERO_SPEC_IDENTITY",
    "numero_log_proves_contract",
    "numero_spec_is_well_formed",
]
