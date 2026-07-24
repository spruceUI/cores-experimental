"""Exact Gearsystem native-describe mixed-language compile/link contract.

Gearsystem uses the shared compile/link proof standard (like handy): the
reviewed compile and link commands are proven exactly via
``mixed_language_log_proves_contract``. The former full-log-envelope proof was
dropped in favour of that single shared standard.
"""

from __future__ import annotations

import re

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


GEARSYSTEM_CORE_ID = "gearsystem"
GEARSYSTEM_BUILD_ARTIFACT_NAME = "gearsystem_libretro.so"
GEARSYSTEM_LOG_CONTRACT_ID = "gearsystem-mixed-language-v1"
GEARSYSTEM_LOG_PROOF_KIND = "core-arch-source"
GEARSYSTEM_NATIVE_GIT_DESCRIBE_DERIVATION = "native-git-describe-v1"
GEARSYSTEM_NATIVE_GIT_DESCRIBE_VALUE = "3.9.12-5-g4f029e4"

GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gearsystem.yml",
    "source_url": "https://github.com/drhelius/Gearsystem.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "4f029e43f2d5207c5da78792503b0fff89b7b2c5",
    "source_tree": "8adfb454298c169327d705bebf94e699e5dbf480",
    "source_key": GEARSYSTEM_CORE_ID,
    "source_dir": "libretro-gearsystem",
    "output_path": "dist/unix/gearsystem_libretro.so",
    "artifact_name": GEARSYSTEM_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/gearsystem_libretro.info"
    ),
    "metadata_artifact_name": "gearsystem_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "platforms/libretro/Makefile",
    "git_version_value": GEARSYSTEM_NATIVE_GIT_DESCRIBE_VALUE,
    "compile_macro": "EMULATOR_BUILD",
}

GEARSYSTEM_SEMANTIC_PATH_ALIASES = (
    ("../shared/dependencies/", "shared/dependencies/"),
    ("../../src/", "src/"),
)
GEARSYSTEM_EXPECTED_COMPILE_COUNT = 46
GEARSYSTEM_EXPECTED_LANGUAGE_COUNTS = {"c": 2, "cxx": 44}
GEARSYSTEM_EXPECTED_COMPILE_PAIR_SHA256 = (
    "7638105b5762c5e2765af18987a32b84f1b9b0d449042338399e8aef9b80713e"
)
GEARSYSTEM_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "2b9495820799c442315bf1e1e2c25c97899f6b75efc06b0c6198aa9f08b92e60",
    "armhf": "607571e51c343d496b883db68be36326b5bfb18426acb401db2f30013bb02432",
}
GEARSYSTEM_EXPECTED_LINK_OBJECT_SHA256 = (
    "978ed38863951da6db68c4c8a6d111de08fcf5bbb233f0090b84ee3e488124bd"
)
GEARSYSTEM_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "7f38f8e747fb0ace83f3a67ec6876fdb0f7e4558552c67396c947e79d1d554e7"
)
GEARSYSTEM_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,-version-script=./link.T",
    "-lm",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def gearsystem_spec_is_well_formed(spec: object) -> bool:
    """Require Gearsystem's complete catalog and native-describe identity."""

    identity = GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
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
                    "derivation": GEARSYSTEM_NATIVE_GIT_DESCRIBE_DERIVATION,
                    "value": GEARSYSTEM_NATIVE_GIT_DESCRIBE_VALUE,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def gearsystem_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed Gearsystem tree."""

    identity = GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
    return bool(
        core_id == GEARSYSTEM_CORE_ID
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


def gearsystem_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted Gearsystem native-describe build record."""

    return bool(
        isinstance(build, dict)
        and source_commit
        == GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_commit"]
        and gearsystem_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": GEARSYSTEM_NATIVE_GIT_DESCRIBE_DERIVATION,
                "value": GEARSYSTEM_NATIVE_GIT_DESCRIBE_VALUE,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def gearsystem_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Gearsystem's exact compile/link proof parameters."""

    return MixedLanguageLogContract(
        core_id=GEARSYSTEM_CORE_ID,
        expected_compile_count=GEARSYSTEM_EXPECTED_COMPILE_COUNT,
        expected_language_counts=GEARSYSTEM_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=GEARSYSTEM_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=GEARSYSTEM_EXPECTED_COMPILE_INVOCATION_SHA256,
        expected_link_object_sha256=GEARSYSTEM_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=GEARSYSTEM_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=GEARSYSTEM_BUILD_ARTIFACT_NAME,
        expected_link_options=GEARSYSTEM_EXPECTED_LINK_OPTIONS,
        source_commit=GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_commit"],
        source_tree=GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_tree"],
        semantic_path_aliases=GEARSYSTEM_SEMANTIC_PATH_ALIASES,
    )


def gearsystem_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Gearsystem's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        gearsystem_mixed_language_contract(),
    )
