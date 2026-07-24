"""Exact A5200 C-only build-log contract."""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


A5200_CORE_ID = "a5200"
A5200_EXPECTED_COMPILE_COUNT = 36
A5200_EXPECTED_COMPILE_PAIR_SHA256 = (
    "18f957ad65d7263aa50d346204200b118bbb9f82e7f98d56c89db24fee54200f"
)
A5200_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "1781cc2749ad5b78dbd0190b7a32a9898f51a2d6ad7b7cdf414ed52412f95258",
    "armhf": "96c3037104a23941f5a4bfb29300428369ca319b88c1648c4683788f7a555cc6",
}
A5200_EXPECTED_LINK_OBJECT_SHA256 = (
    "0f8950b60a03dee260733caf191a43d363bbf9b9c782df15719799432aad53e7"
)
A5200_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "0f8950b60a03dee260733caf191a43d363bbf9b9c782df15719799432aad53e7"
)
A5200_BUILD_ARTIFACT_NAME = "a5200_libretro.so"
A5200_EXPECTED_LINK_OPTIONS = (
    "-lm",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
A5200_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-a5200.yml",
    "source_url": "https://github.com/libretro/a5200.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "23c1ea482afb08656ec507e9ce98ed242a20bdfa",
    "source_tree": "bd8a0b3f925ab9dcd5acae4f705e4f0c00f787b5",
    "source_key": A5200_CORE_ID,
    "source_dir": "libretro-a5200",
    "output_path": "dist/unix/a5200_libretro.so",
    "artifact_name": A5200_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/a5200_libretro.info",
    "metadata_artifact_name": "a5200_libretro.info",
    "targets": ["arm64", "armhf"],
    "git_version": {
        "derivation": "hyphen-short7-v1",
        "value": "-23c1ea4",
    },
}


def a5200_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable A5200 catalog identity."""

    identity = A5200_GIT_VERSION_SPEC_IDENTITY
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
                "git_version": identity["git_version"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


A5200_LOG_CONTRACT = COnlyLogContract(
    core_id=A5200_CORE_ID,
    expected_compile_count=A5200_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=A5200_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        A5200_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=A5200_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=A5200_BUILD_ARTIFACT_NAME,
    expected_link_options=A5200_EXPECTED_LINK_OPTIONS,
    source_commit=A5200_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=A5200_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=A5200_EXPECTED_RAW_LINK_OBJECT_SHA256,
)


def a5200_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove A5200's exact C compile and raw/semantic link-object sets."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        A5200_LOG_CONTRACT,
    )
