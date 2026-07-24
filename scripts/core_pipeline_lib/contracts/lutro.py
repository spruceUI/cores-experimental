"""Exact Lutro (libretro Lua game framework) C-only + archive build-log contract.

lutro is a C-only libretro-super core whose build first archives its bundled Lua
interpreter objects into an in-tree static library (``ar rcu liblua.a <29 lua
objects>``) and then links the 84 lutro/libretro-common/deps objects **plus**
``liblua.a`` into ``obj/player/lutro_libretro.so``. Because the archived Lua
objects are not named on the link line, the plain ``link == compile`` identity
does not hold; this contract runs the c_only engine in archive-membership mode,
which proves ``link_direct_objects ∪ archive_members == compile_objects`` and
additionally pins the exact 29-member Lua set and the archive name. The objects
and the artifact live under ``obj/player/``; a single ``semantic_path_aliases``
prefix strips it (the engine also drops the residual ``./``) so the compile,
link, and artifact paths are contained and stem-equal. 113 C TUs total, C-driver
link. Per-architecture compile invocation sha256 pins the exact argv.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


LUTRO_CORE_ID = "lutro"
LUTRO_BUILD_ARTIFACT_NAME = "lutro_libretro.so"

LUTRO_SOURCE_COMMIT = "1df938b3bf37b8d1eb6cdd07ec915c4f569a7551"
LUTRO_SOURCE_TREE = "d20aac44229476877084e26c2558c63737a86c98"

LUTRO_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-lutro.yml",
    "source_url": "https://github.com/libretro/libretro-lutro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": LUTRO_SOURCE_COMMIT,
    "source_tree": LUTRO_SOURCE_TREE,
    "source_key": LUTRO_CORE_ID,
    "source_dir": "libretro-lutro",
    "output_path": "dist/unix/lutro_libretro.so",
    "artifact_name": LUTRO_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/lutro_libretro.info",
    "metadata_artifact_name": "lutro_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the lutro core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def lutro_spec_is_well_formed(spec: object) -> bool:
    """Require Lutro's exact immutable catalog identity."""

    identity = LUTRO_SPEC_IDENTITY
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


LUTRO_LOG_CONTRACT_ID = "lutro-c-only-archive-v1"
LUTRO_EXPECTED_COMPILE_COUNT = 113
LUTRO_EXPECTED_COMPILE_PAIR_SHA256 = (
    "f6a600392b1a1476ad41c281ea770d2023987c08561be68410d371259ea4ad40"
)
LUTRO_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "e103aa9fcbb61c7a0c559445f531e53b73734ada2e0780b73c019c781dd47966",
    "armhf": "f946fb66b736e178b869497a99bc2b16b932eabf5c03b2bcc8f4af662ee4e49a",
}
# link references the 84 direct objects (Lua objects are inside liblua.a)
LUTRO_EXPECTED_LINK_OBJECT_SHA256 = (
    "1bc6a80d9cd258d2065086deb65130ff375bddb7d5bb952b2638117f12a98b40"
)
LUTRO_EXPECTED_ARCHIVE_MEMBER_SHA256 = (
    "88da09e9cdd61010dfdc2b48edc3ec842a186e944ebf9a26746ab2766a79e1b8"
)
LUTRO_EXPECTED_ARCHIVE_NAMES = ("liblua.a",)
LUTRO_SEMANTIC_PATH_ALIASES = (("obj/player/", ""),)
LUTRO_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-as-needed,--no-undefined",
    "-Wl,-E",
    "-lm",
)

LUTRO_LOG_CONTRACT = COnlyLogContract(
    core_id=LUTRO_CORE_ID,
    expected_compile_count=LUTRO_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=LUTRO_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        LUTRO_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=LUTRO_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=LUTRO_BUILD_ARTIFACT_NAME,
    expected_link_options=LUTRO_EXPECTED_LINK_OPTIONS,
    source_commit=LUTRO_SOURCE_COMMIT,
    source_tree=LUTRO_SOURCE_TREE,
    semantic_path_aliases=LUTRO_SEMANTIC_PATH_ALIASES,
    expected_archive_member_sha256=LUTRO_EXPECTED_ARCHIVE_MEMBER_SHA256,
    expected_archive_names=LUTRO_EXPECTED_ARCHIVE_NAMES,
)


def lutro_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Lutro's exact C compile set, Lua archive, and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        LUTRO_LOG_CONTRACT,
    )


__all__ = [
    "LUTRO_BUILD_ARTIFACT_NAME",
    "LUTRO_CORE_ID",
    "LUTRO_LOG_CONTRACT_ID",
    "LUTRO_SOURCE_COMMIT",
    "LUTRO_SOURCE_TREE",
    "LUTRO_SPEC_IDENTITY",
    "lutro_log_proves_contract",
    "lutro_spec_is_well_formed",
]
