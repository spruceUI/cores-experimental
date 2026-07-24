"""Exact libgametank (GameTank, Rust) direct-cargo contract.

The first cargo core: dwbrite/gametank-sdk's ``tools/gte/libretro`` crate,
built by ``cargo zigbuild --locked`` per device target with the glibc-2.23
floor (matching the A30 sysroot; measured artifact requirement is
GLIBC <= 2.18). The dependency pin is upstream's committed ``Cargo.lock``
(checksummed crates; ``--locked`` refuses drift) and the proof pins the
compiled-crate multiset -- 69 crates, identical on both architectures,
including the git-sourced libretro-rs pinned by revision inside the
``Compiling`` line itself.
"""

from __future__ import annotations


LIBGAMETANK_CORE_ID = "libgametank"
LIBGAMETANK_BUILD_ARTIFACT_NAME = "libgametank_libretro.so"

LIBGAMETANK_SOURCE_COMMIT = "f3f5a3b3e67e96a115cc87ddfd3e5921ac59b197"
LIBGAMETANK_SOURCE_TREE = "9236ce3da5a432a626be55277ba55d32715e97f2"
LIBGAMETANK_CARGO_LOCK_SHA256 = (
    "b8c66e6924352eb35603df6a921ef43ecd91fa6b79ab8b44def74098069ce360"
)

LIBGAMETANK_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-libgametank.yml",
    "source_url": "https://github.com/dwbrite/gametank-sdk.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": LIBGAMETANK_SOURCE_COMMIT,
    "source_tree": LIBGAMETANK_SOURCE_TREE,
    "source_dir": "libgametank",
    "output_path": "libgametank_libretro.so",
    "artifact_name": LIBGAMETANK_BUILD_ARTIFACT_NAME,
    "source_date_epoch": 1784593754,
    "cargo_subdir": "tools/gte/libretro",
    "cargo_lock_sha256": LIBGAMETANK_CARGO_LOCK_SHA256,
    "cargo_targets": {
        "arm64": "aarch64-unknown-linux-gnu.2.23",
        "armhf": "armv7-unknown-linux-gnueabihf.2.23",
    },
    "metadata_repo_path": "metadata/libgametank_libretro.info",
    "metadata_sha256": (
        "f9354a9cafb77090f12a86de622db9b2a5a7bc798ae124fe111828c7cce59c82"
    ),
    "metadata_artifact_name": "libgametank_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the libgametank core must preserve its exact source, direct-cargo "
    "recipe, Cargo.lock pin, target triples, metadata, and target contract"
)


def libgametank_spec_is_well_formed(spec: object) -> bool:
    """Require libgametank's exact immutable direct-cargo catalog identity."""

    identity = LIBGAMETANK_SPEC_IDENTITY
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
                "driver": "direct-cargo",
                "source_dir": identity["source_dir"],
                "output_path": identity["output_path"],
                "artifact_name": identity["artifact_name"],
                "source_date_epoch": identity["source_date_epoch"],
                "cargo": {
                    "subdir": identity["cargo_subdir"],
                    "profile": "release",
                    "lock_sha256": identity["cargo_lock_sha256"],
                    "targets": dict(identity["cargo_targets"]),
                },
            },
            "metadata": {
                "repo_path": identity["metadata_repo_path"],
                "sha256": identity["metadata_sha256"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


from .cargo import CargoLogContract, cargo_log_proves_contract


LIBGAMETANK_LOG_CONTRACT_ID = "libgametank-cargo-v1"
LIBGAMETANK_EXPECTED_COMPILING_COUNT = {"arm64": 69, "armhf": 69}
# The 69-crate multiset is identical across both device targets (the crate
# graph carries no per-target dependencies); the sha covers the full
# ``Compiling name vX.Y.Z (source)`` lines, so the libretro-rs git revision
# is pinned by the same digest.
LIBGAMETANK_EXPECTED_COMPILING_MULTISET_SHA256 = {
    "arm64": (
        "3123563f709a5bba623a42d77b6929b8fc115a3548debd567a9758b810956530"
    ),
    "armhf": (
        "3123563f709a5bba623a42d77b6929b8fc115a3548debd567a9758b810956530"
    ),
}

LIBGAMETANK_LOG_CONTRACT = CargoLogContract(
    core_id=LIBGAMETANK_CORE_ID,
    build_artifact_name=LIBGAMETANK_BUILD_ARTIFACT_NAME,
    source_commit=LIBGAMETANK_SOURCE_COMMIT,
    source_tree=LIBGAMETANK_SOURCE_TREE,
    lock_sha256=LIBGAMETANK_CARGO_LOCK_SHA256,
    expected_target=dict(LIBGAMETANK_SPEC_IDENTITY["cargo_targets"]),
    expected_compiling_count=LIBGAMETANK_EXPECTED_COMPILING_COUNT,
    expected_compiling_multiset_sha256=(
        LIBGAMETANK_EXPECTED_COMPILING_MULTISET_SHA256
    ),
)


def libgametank_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove libgametank's exact lock digest, invocation, and crate set."""

    return cargo_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        LIBGAMETANK_LOG_CONTRACT,
    )


__all__ = [
    "LIBGAMETANK_BUILD_ARTIFACT_NAME",
    "LIBGAMETANK_CARGO_LOCK_SHA256",
    "LIBGAMETANK_CORE_ID",
    "LIBGAMETANK_LOG_CONTRACT_ID",
    "LIBGAMETANK_SOURCE_COMMIT",
    "LIBGAMETANK_SOURCE_TREE",
    "LIBGAMETANK_SPEC_IDENTITY",
    "SPEC_GUARD_MESSAGE",
    "libgametank_log_proves_contract",
    "libgametank_spec_is_well_formed",
]
