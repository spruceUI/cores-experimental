"""Exact Gearboy native-describe mixed-language compile/link contract.

Gearboy uses the shared compile/link proof standard (like handy): the reviewed
compile and link commands are proven exactly via
``mixed_language_log_proves_contract``. The former full-log-envelope proof was
dropped in favour of that single shared standard.
"""

from __future__ import annotations

import re

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


GEARBOY_CORE_ID = "gearboy"
GEARBOY_BUILD_ARTIFACT_NAME = "gearboy_libretro.so"
GEARBOY_LOG_CONTRACT_ID = "gearboy-mixed-language-v1"
GEARBOY_LOG_PROOF_KIND = "core-arch-source"
GEARBOY_NATIVE_GIT_DESCRIBE_DERIVATION = "native-git-describe-v1"
GEARBOY_NATIVE_GIT_DESCRIBE_VALUE = "3.8.9-8-g36d723f"

GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gearboy.yml",
    "source_url": "https://github.com/drhelius/Gearboy.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "36d723ff44109e6d9eefba34e1c9a089c2d50e18",
    "source_tree": "d01d828b1e5e7330bcf908b19b1afae8c9f8897b",
    "source_key": GEARBOY_CORE_ID,
    "source_dir": "libretro-gearboy",
    "output_path": "dist/unix/gearboy_libretro.so",
    "artifact_name": GEARBOY_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/gearboy_libretro.info"
    ),
    "metadata_artifact_name": "gearboy_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "platforms/libretro/Makefile",
    "git_version_value": GEARBOY_NATIVE_GIT_DESCRIBE_VALUE,
    "compile_macro": "EMULATOR_BUILD",
}

GEARBOY_SEMANTIC_PATH_ALIASES = (
    ("../shared/dependencies/", "shared/dependencies/"),
    ("../../src/", "src/"),
)
GEARBOY_EXPECTED_COMPILE_COUNT = 40
GEARBOY_EXPECTED_LANGUAGE_COUNTS = {"c": 1, "cxx": 39}
GEARBOY_EXPECTED_COMPILE_PAIR_SHA256 = (
    "d374460a661dee9190cca22babe3e8d699875a87564745813844e883eddd814d"
)
GEARBOY_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "50ee4935508493ca8a2c346cec81a1a8b024a759c3bf407d39e07900407dabcc",
    "armhf": "812d7dbaac2de73b4ab0cadd7f9e3344f89148523cede88eed21fa447357a8b5",
}
GEARBOY_EXPECTED_LINK_OBJECT_SHA256 = (
    "e334703c3a7cb1f44ac12e2925b292faef5907dc4dc319764b536d5d6a357415"
)
GEARBOY_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "4f8735cefe210dbe2a5cef1c6f32515c63feab9ea58ec7a7ba303d5c5b23d958"
)
GEARBOY_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,-version-script=./link.T",
    "-lm",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def gearboy_spec_is_well_formed(spec: object) -> bool:
    """Require Gearboy's complete catalog and native-describe identity."""

    identity = GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
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
                    "derivation": GEARBOY_NATIVE_GIT_DESCRIBE_DERIVATION,
                    "value": GEARBOY_NATIVE_GIT_DESCRIBE_VALUE,
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def gearboy_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed Gearboy tree."""

    identity = GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
    return bool(
        core_id == GEARBOY_CORE_ID
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


def gearboy_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted Gearboy native-describe build record."""

    return bool(
        isinstance(build, dict)
        and source_commit
        == GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_commit"]
        and gearboy_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": GEARBOY_NATIVE_GIT_DESCRIBE_DERIVATION,
                "value": GEARBOY_NATIVE_GIT_DESCRIBE_VALUE,
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def gearboy_mixed_language_contract() -> MixedLanguageLogContract:
    """Return Gearboy's exact compile/link proof parameters from its constants."""

    return MixedLanguageLogContract(
        core_id=GEARBOY_CORE_ID,
        expected_compile_count=GEARBOY_EXPECTED_COMPILE_COUNT,
        expected_language_counts=GEARBOY_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=GEARBOY_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=GEARBOY_EXPECTED_COMPILE_INVOCATION_SHA256,
        expected_link_object_sha256=GEARBOY_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=GEARBOY_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=GEARBOY_BUILD_ARTIFACT_NAME,
        expected_link_options=GEARBOY_EXPECTED_LINK_OPTIONS,
        source_commit=GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_commit"],
        source_tree=GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY["source_tree"],
        semantic_path_aliases=GEARBOY_SEMANTIC_PATH_ALIASES,
    )


def gearboy_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Gearboy's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        gearboy_mixed_language_contract(),
    )
