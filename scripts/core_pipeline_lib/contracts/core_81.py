"""Exact EightyOne native-generated-version compile/link contract.

EightyOne uses the shared compile/link proof standard (like handy): the reviewed
compile and link commands are proven exactly via
``mixed_language_log_proves_contract``. Its native ``src/version.c`` generation
is still bound through the generated-source identity and build-shell below; the
former full-log-envelope proof was dropped in favour of the shared standard.
"""

from __future__ import annotations

import re
import shlex

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


CORE_81_ID = "81"
CORE_81_BUILD_ARTIFACT_NAME = "81_libretro.so"
CORE_81_GENERATED_VERSION_PATH = "src/version.c"
CORE_81_GENERATED_VERSION_SHA256 = (
    "5a07d38a3bcd84ee5fa9abbdbe0bd706288d8ec4ee8095485447e35dc28a2862"
)

CORE_81_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-81.yml",
    "source_url": "https://github.com/libretro/81-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "fa7094910d040baa5fd8b11dbf6a1a618330ecd9",
    "source_tree": "d73d124d16714e946ba9490627a4fc38c2aea37a",
    "source_key": CORE_81_ID,
    "source_dir": "libretro-81",
    "output_path": "dist/unix/81_libretro.so",
    "artifact_name": CORE_81_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/81_libretro.info",
    "metadata_artifact_name": "81_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile.libretro",
    "generated_source": {
        "kind": "post-build-sha256-v1",
        "path": CORE_81_GENERATED_VERSION_PATH,
        "sha256": CORE_81_GENERATED_VERSION_SHA256,
    },
}

CORE_81_EXPECTED_COMPILE_COUNT = 28
CORE_81_EXPECTED_LANGUAGE_COUNTS = {"c": 16, "cxx": 12}
CORE_81_EXPECTED_COMPILE_PAIR_SHA256 = (
    "46c00506b38b944886104bac79736db6045d50ea00b06ac3f3557bb09a653067"
)
CORE_81_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "36a401a237e2f2190e061926c76d5c4d5ef049e4c983f8fca10dccd66ced758f",
    "armhf": "9338237c461f3d944d6fb34b26e38ac11b26a228d9603dbb87b234e326386c58",
}
CORE_81_EXPECTED_LINK_OBJECT_SHA256 = (
    "4e44d3d0fbe287926bf7ca12ab966041410b71d7e4724327b0d2a750f08c84dc"
)
CORE_81_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "ee340a021cd230742bceea134aca6a1343ebc9563f1722ee842993fd5c3202d7"
)
CORE_81_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=build/link.T",
    "-Wl,-no-undefined",
    "-lm",
)


def core_81_generated_source_contract_is_well_formed(value: object) -> bool:
    """Recognize only the reviewed post-build generated source identity."""

    return bool(
        isinstance(value, dict)
        and value == CORE_81_SPEC_IDENTITY["generated_source"]
    )


def core_81_spec_is_well_formed(spec: object) -> bool:
    """Require EightyOne's complete immutable catalog identity."""

    identity = CORE_81_SPEC_IDENTITY
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
                "generated_source": identity["generated_source"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def core_81_golden_source_is_well_formed(
    core_id: object, source: object
) -> bool:
    """Bind a future promoted record to the reviewed EightyOne tree."""

    identity = CORE_81_SPEC_IDENTITY
    return bool(
        core_id == CORE_81_ID
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


def core_81_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require generated-source identity in every promoted EightyOne build."""

    identity = CORE_81_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and core_81_golden_source_is_well_formed(core_id, source)
        and set(build)
        == {
            "driver",
            "environment",
            "compile_definitions",
            "generated_source",
            "log",
            "log_sha256",
        }
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and core_81_generated_source_contract_is_well_formed(
            build.get("generated_source")
        )
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", build["log_sha256"]) is not None
    )


def core_81_generated_version_shell(spec: object) -> str:
    """Verify the version source generated natively by EightyOne's Makefile."""

    if not core_81_spec_is_well_formed(spec):
        return ""
    assert isinstance(spec, dict)
    build = spec["build"]
    generated_source = build["generated_source"]
    generated_path = build["source_dir"] + "/" + generated_source["path"]
    generated_marker = (
        "CORE_PIPELINE_GENERATED_SOURCE|"
        + generated_source["path"]
        + "|sha256|"
        + generated_source["sha256"]
    )
    return "\n".join(
        (
            f"test -f {shlex.quote(generated_path)}",
            f"test ! -L {shlex.quote(generated_path)}",
            "actual_core_81_generated_sha256="
            f'"$(sha256sum {shlex.quote(generated_path)} | awk '
            "'{print $1}')\"",
            'test "$actual_core_81_generated_sha256" = '
            + shlex.quote(generated_source["sha256"]),
            f"printf '%s\\n' {shlex.quote(generated_marker)}",
        )
    )


def core_81_mixed_language_contract() -> MixedLanguageLogContract:
    """Return EightyOne's exact compile/link proof parameters."""

    return MixedLanguageLogContract(
        core_id=CORE_81_ID,
        expected_compile_count=CORE_81_EXPECTED_COMPILE_COUNT,
        expected_language_counts=CORE_81_EXPECTED_LANGUAGE_COUNTS,
        expected_compile_pair_sha256=CORE_81_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=CORE_81_EXPECTED_COMPILE_INVOCATION_SHA256,
        expected_link_object_sha256=CORE_81_EXPECTED_LINK_OBJECT_SHA256,
        expected_raw_link_object_sha256=CORE_81_EXPECTED_RAW_LINK_OBJECT_SHA256,
        build_artifact_name=CORE_81_BUILD_ARTIFACT_NAME,
        expected_link_options=CORE_81_EXPECTED_LINK_OPTIONS,
        source_commit=CORE_81_SPEC_IDENTITY["source_commit"],
        source_tree=CORE_81_SPEC_IDENTITY["source_tree"],
        expected_link_language="cxx",
    )


def core_81_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove EightyOne's exact compile and link commands for one architecture."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        core_81_mixed_language_contract(),
    )
