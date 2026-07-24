"""Exact C-only compile/link contract for FCEUmm."""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract


FCEUMM_CORE_ID = "fceumm"
FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-fceumm.yml",
    "source_url": "https://github.com/libretro/libretro-fceumm.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "718c5a2e175735df92ba17a2945a8d1abbc48652",
    "source_tree": "9778fe04fc7b5fab1d71351784cb56be2949cf99",
    "source_key": FCEUMM_CORE_ID,
    "source_dir": "libretro-fceumm",
    "output_path": "dist/unix/fceumm_libretro.so",
    "artifact_name": "fceumm_libretro.so",
    "metadata_source_path": "/libretro-super/dist/info/fceumm_libretro.info",
    "metadata_artifact_name": "fceumm_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile.libretro",    "overlays": {
        "arm64": [
            {
                "kind": "git-apply-v1",
                "patch_path": "patches/fceumm/makefile-sort-wildcard-sources.patch",
                "patch_sha256": (
                    "2403f63b6d1cf7d2bb1d4173bd8711f5d67e7846e1b0661d58d65c78997988e0"
                ),
                "source_path": "Makefile.common",
                "preimage_sha256": (
                    "2e3046c8c68438902c060eda9d5664dcc864ec05c702ff857a964dfe64286f7a"
                ),
                "postimage_sha256": (
                    "0ab3271440bc6eece078f76b6438afbc76b73888945d904b3aecffbf5a9a71de"
                ),
            }
        ],
        "armhf": [
            {
                "kind": "git-apply-v1",
                "patch_path": "patches/fceumm/makefile-sort-wildcard-sources.patch",
                "patch_sha256": (
                    "2403f63b6d1cf7d2bb1d4173bd8711f5d67e7846e1b0661d58d65c78997988e0"
                ),
                "source_path": "Makefile.common",
                "preimage_sha256": (
                    "2e3046c8c68438902c060eda9d5664dcc864ec05c702ff857a964dfe64286f7a"
                ),
                "postimage_sha256": (
                    "0ab3271440bc6eece078f76b6438afbc76b73888945d904b3aecffbf5a9a71de"
                ),
            }
        ],
    },
}

FCEUMM_LOG_CONTRACT = COnlyLogContract(
    core_id=FCEUMM_CORE_ID,
    expected_compile_count=512,
    expected_compile_pair_sha256=(
        "544468c1b018847967651bc099dccd3c3a7f7c0d9f6f8b02a32c8bf6a7a203cd"
    ),
    expected_compile_invocation_sha256={
        "arm64": (
            "c6d92677d0da955c1b9d9e597bed411f664f6ecfc435f4c06cce3bf3e7177d48"
        ),
        "armhf": (
            "f425a063f9ba099d9d40573b8b82b06f47483d9227bf0b7e0110d8f4aa81056a"
        ),
    },
    expected_link_object_sha256=(
        "776d43d74f5c43770376d9548968f9a0130b53251b684d6c7d38adb4b3232281"
    ),
    build_artifact_name="fceumm_libretro.so",
    expected_link_options=(
        "-shared",
        "-Wl,--version-script=src/drivers/libretro/link.T",
        "-Wl,-no-undefined",
        "-lm",
    ),
    source_commit=FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
)


def fceumm_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove FCEUmm's exact C compile set and matching link-object set."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FCEUMM_LOG_CONTRACT,
    )
