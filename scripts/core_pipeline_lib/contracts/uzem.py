"""Exact Uzem native-version mixed-language compile/link contract.

Uzem uses the shared compile/link proof standard (like handy): the reviewed
compile and link commands are proven exactly via
``mixed_language_log_proves_contract``. The former full-log-envelope proof (fetch
prefix, marker ordering, diagnostic placement, success trailer) was dropped in
favour of that single shared standard.
"""

from __future__ import annotations

import re

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


UZEM_CORE_ID = "uzem"
UZEM_BUILD_ARTIFACT_NAME = "uzem_libretro.so"
UZEM_LOG_CONTRACT_ID = "uzem-mixed-language-v1"
UZEM_LOG_PROOF_KIND = "core-arch-source"
UZEM_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
UZEM_NATIVE_GIT_VERSION = " d4fe82c"

UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-uzem.yml",
    "source_url": "https://github.com/libretro/libretro-uzem.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "d4fe82c38bf3fc789b955bcfcc81dc2e3a2ea89f",
    "source_tree": "949f7cb3c2f61295335ea59e35e7d9f031693ac1",
    "source_key": UZEM_CORE_ID,
    "source_dir": "libretro-uzem",
    "output_path": "dist/unix/uzem_libretro.so",
    "artifact_name": UZEM_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/uzem_libretro.info",
    "metadata_artifact_name": "uzem_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile.libretro",
}

UZEM_EXPECTED_COMPILE_COUNT = 18
UZEM_EXPECTED_LANGUAGE_COUNTS = {"c": 12, "cxx": 6}
UZEM_EXPECTED_COMPILE_PAIR_SHA256 = (
    "b6222fd2ae45ba2878d66cfd4a5ff41f66f8ee7f3d934cfe4c376c3c9a448cf7"
)
UZEM_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "81fcc0000aea85becbe260df153ea032d45142a018bba7ac013c7239255c229c",
    "armhf": "27fabfeb196ae9e95da2dc654ec409a19467fbc08d2c36de6ae5582eb4c4a3b3",
}
UZEM_EXPECTED_LINK_OBJECT_SHA256 = (
    "cb7a04020f2d690567868ba1d52942ec80c557aa898c596ab864d6554a6e2e1a"
)
UZEM_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "daa378032888353d257ce0b5de215ac4996452749fb35c073a45238c927f68a1"
)
UZEM_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,--version-script=link.T",
    "-lm",
    "-fPIC",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def uzem_spec_is_well_formed(spec: object) -> bool:
    """Require Uzem's complete immutable catalog and native identity."""

    identity = UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": UZEM_NATIVE_GIT_VERSION_DERIVATION,
                    "value": UZEM_NATIVE_GIT_VERSION,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def uzem_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed Uzem tree."""

    identity = UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == UZEM_CORE_ID
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


def uzem_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted Uzem native-version build record."""

    identity = UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and uzem_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": UZEM_NATIVE_GIT_VERSION_DERIVATION,
                "value": UZEM_NATIVE_GIT_VERSION,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def uzem_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Uzem's exact compile/link proof parameters from its constants."""

    return MixedLanguageLogContract(
        core_id=UZEM_CORE_ID,
        expected_compile_count=UZEM_EXPECTED_COMPILE_COUNT,
        expected_language_counts=UZEM_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=UZEM_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=UZEM_EXPECTED_COMPILE_INVOCATION_SHA256,
        expected_link_object_sha256=UZEM_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=UZEM_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=UZEM_BUILD_ARTIFACT_NAME,
        expected_link_options=UZEM_EXPECTED_LINK_OPTIONS,
        source_commit=UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    )


def uzem_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Uzem's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        uzem_mixed_language_contract(),
    )
