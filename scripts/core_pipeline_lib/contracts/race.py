"""Exact RACE native-version C-only compile/link contract.

RACE uses the shared C-only compile/link proof standard: the reviewed compile
and link commands are proven exactly via ``c_only_log_proves_contract`` (which
sorts compile invocations, so parallel-interleaved build logs are accepted).
The former full-log-envelope proof was dropped in favour of that single shared
standard.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


RACE_CORE_ID = "race"
RACE_BUILD_ARTIFACT_NAME = "race_libretro.so"
RACE_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
RACE_NATIVE_GIT_VERSION = " c7810dd"

RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-race.yml",
    "source_url": "https://github.com/libretro/RACE.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "c7810dd7f172827bfa2004813bc000b13786636b",
    "source_tree": "344c09b682f79f2135479bdd0a76d193edfdf167",
    "source_key": RACE_CORE_ID,
    "source_dir": "libretro-race",
    "output_path": "dist/unix/race_libretro.so",
    "artifact_name": RACE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/race_libretro.info",
    "metadata_artifact_name": "race_libretro.info",
    "targets": ["arm64", "armhf"],
    "native_makefile": "Makefile",
    "compiler_scope": "c",
}

RACE_EXPECTED_COMPILE_COUNT = 27
RACE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "5775a05551704150dd77245905f631b90a6dbe1b373092bc05946f31b9ea530f"
)
RACE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "56af360b51c04b14aea7f464b0a201f0c2ab5559d5a4182e2ede973ac991b3ab",
    "armhf": "20ac74d57ab44ae1af73b900faa2c67da56db3a8aeb1c494348923a90430ca8c",
}
RACE_EXPECTED_LINK_OBJECT_SHA256 = (
    "41ef1e3c61c789b23b55280d6ab03196fdb159e4286374268211f5bbf2b6ba4e"
)
RACE_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "37619ca72382cf19124f7df95bed9ce8aa53233ab2690b9c9dbabfb6570598e1"
)
RACE_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=libretro/link.T",
    "-Wl,-no-undefined",
)


def race_spec_is_well_formed(spec: object) -> bool:
    """Require RACE's complete immutable catalog identity."""

    identity = RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                    "derivation": RACE_NATIVE_GIT_VERSION_DERIVATION,
                    "value": RACE_NATIVE_GIT_VERSION,
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


def race_c_only_contract() -> COnlyLogContract:
    """Return RACE's exact compile/link proof parameters."""

    return COnlyLogContract(
        core_id=RACE_CORE_ID,
        expected_compile_count=RACE_EXPECTED_COMPILE_COUNT,
        expected_compile_pair_sha256=RACE_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=RACE_EXPECTED_COMPILE_INVOCATION_SHA256,
        expected_link_object_sha256=RACE_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=RACE_BUILD_ARTIFACT_NAME,
        expected_link_options=RACE_EXPECTED_LINK_OPTIONS,
        source_commit=RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        expected_raw_link_object_sha256=RACE_EXPECTED_RAW_LINK_OBJECT_SHA256,
    )


def race_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove RACE's exact compile and link commands for one architecture."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        race_c_only_contract(),
    )
