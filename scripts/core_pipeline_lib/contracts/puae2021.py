"""Exact PUAE 2021 (libretro Amiga, 2.6.1 branch) C-only build-log contract.

puae2021 is the ``2.6.1``-branch build of the portable ``libretro/libretro-uae``
source (libretro-super applies ``libretro_puae2021_post_fetch_cmd="git checkout
2.6.1"``, so the branch pin is carried entirely by the source identity — same
repository as mainline puae, different ref). It is a C-only libretro-super core:
176 translation units compiled by the C driver with a commit-derived
``-DGIT_VERSION`` token, then linked by the C driver. The Makefile writes every
object under ``build/./<path>.o`` while the source is ``<path>.c``, so the
contract strips the ``build/./`` object prefix via ``semantic_path_aliases`` to
recover the compile/source stem equality and the link/compile object identity;
the raw (pre-normalization) link operands keep the prefix, hence the distinct
raw link-object sha256. The per-architecture compile invocation sha256 pins the
exact argv and the link references precisely the compiled object set.
"""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


PUAE2021_CORE_ID = "puae2021"
PUAE2021_BUILD_ARTIFACT_NAME = "puae2021_libretro.so"

PUAE2021_SOURCE_COMMIT = "0fece7d9514e2224530cd252489c8928d49eebca"
PUAE2021_SOURCE_TREE = "90e86c39361baebcbc7c2a9a302aa88e30034d6a"
# main.c embeds __DATE__/__TIME__; pinning SOURCE_DATE_EPOCH to the commit's
# committer date (2026-07-20) makes the artifact bytes and build-id reproducible.
PUAE2021_SOURCE_DATE_EPOCH = 1784565128

PUAE2021_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-puae2021.yml",
    "source_url": "https://github.com/libretro/libretro-uae.git",
    "source_requested_ref": "refs/heads/2.6.1",
    "source_commit": PUAE2021_SOURCE_COMMIT,
    "source_tree": PUAE2021_SOURCE_TREE,
    "source_key": PUAE2021_CORE_ID,
    "source_dir": "libretro-puae2021",
    "output_path": "dist/unix/puae2021_libretro.so",
    "artifact_name": PUAE2021_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/puae2021_libretro.info",
    "metadata_artifact_name": "puae2021_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the puae2021 core must preserve its exact 2.6.1-branch "
    "source, recipe, metadata, and target contract"
)


def puae2021_spec_is_well_formed(spec: object) -> bool:
    """Require PUAE 2021's exact immutable 2.6.1-branch catalog identity."""

    identity = PUAE2021_SPEC_IDENTITY
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
                "source_date_epoch": PUAE2021_SOURCE_DATE_EPOCH,
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


PUAE2021_LOG_CONTRACT_ID = "puae2021-c-only-v1"
PUAE2021_EXPECTED_COMPILE_COUNT = 176
PUAE2021_EXPECTED_COMPILE_PAIR_SHA256 = (
    "f13e3facb84f17950575843de24f40aabaa4d0bcf9c200524a950e331f491dcd"
)
PUAE2021_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "655e84d7412761536144b7c33473c17d2ece3653ffb141453bdab805e251f61a",
    "armhf": "ea07007bd9447bf997273090c1bc10e19000adb588b4852ad857e9a8de4bf4f0",
}
PUAE2021_EXPECTED_LINK_OBJECT_SHA256 = (
    "ca51193063fbb233cb2663c9c792faea1c9a5e1c7bcf9b6ce10dce533e6aeebd"
)
PUAE2021_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "05061a2b0c59e9d893912aa6f3c91132e39618a56a2ff6fa278ebddea832397b"
)
PUAE2021_SEMANTIC_PATH_ALIASES = (("build/./", ""),)
PUAE2021_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./libretro/link.T",
    "-Wl,--gc-sections",
    "-I./sources/src",
    "-I./sources/src/include",
    "-I.",
    "-I./retrodep",
    "-I./deps/7zip",
    "-I./libretro",
    "-I./libretro-common/include",
    "-I./libretro-common/include/compat/zlib",
    "-I./deps/libchdr/include",
    "-I./deps/zstd/lib",
    "-lpthread",
    "-s",
)

PUAE2021_LOG_CONTRACT = COnlyLogContract(
    core_id=PUAE2021_CORE_ID,
    expected_compile_count=PUAE2021_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=PUAE2021_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        PUAE2021_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=PUAE2021_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=PUAE2021_BUILD_ARTIFACT_NAME,
    expected_link_options=PUAE2021_EXPECTED_LINK_OPTIONS,
    source_commit=PUAE2021_SOURCE_COMMIT,
    source_tree=PUAE2021_SOURCE_TREE,
    expected_raw_link_object_sha256=PUAE2021_EXPECTED_RAW_LINK_OBJECT_SHA256,
    semantic_path_aliases=PUAE2021_SEMANTIC_PATH_ALIASES,
)


def puae2021_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove PUAE 2021's exact C compile set and matching link."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        PUAE2021_LOG_CONTRACT,
    )


__all__ = [
    "PUAE2021_BUILD_ARTIFACT_NAME",
    "PUAE2021_CORE_ID",
    "PUAE2021_LOG_CONTRACT_ID",
    "PUAE2021_SOURCE_COMMIT",
    "PUAE2021_SOURCE_TREE",
    "PUAE2021_SPEC_IDENTITY",
    "puae2021_log_proves_contract",
    "puae2021_spec_is_well_formed",
]
