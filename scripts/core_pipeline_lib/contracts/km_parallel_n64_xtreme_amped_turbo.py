"""Exact KM parallel-n64 fork contract (direct-make, armhf GLES2).

The KMFDManic fork was broken at its pinned HEAD under the v2 toolchain for
reasons the fork itself introduced or that postdate its era: a commented-out
``GLdouble`` typedef in the bundled glsm header, a missing ``<stdexcept>``
include, a tentative-definition ``_gSPVertex`` in a shared header, and the
pre-GCC10 commons model its C sources rely on. Five reviewed overlays under
``patches/km_parallel_n64_xtreme_amped_turbo/`` restore buildability without
changing behavior; ``-fcommon`` restores the commons semantics the fork was
written for rather than editing dozens of translation units.

The Makefile's product keeps upstream's ``parallel_n64_libretro.so`` name;
the direct-make driver stages it under the core's own canonical artifact
name, the same rebrand rule the km_duckswanstation fork uses. Glide64mk2
embeds ``__DATE__`` in that product, so the recipe binds ``SOURCE_DATE_EPOCH``
to the pinned source commit's committer timestamp.
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


KM_PARALLEL_N64_CORE_ID = "km_parallel_n64_xtreme_amped_turbo"
KM_PARALLEL_N64_BUILD_ARTIFACT_NAME = (
    "km_parallel_n64_xtreme_amped_turbo_libretro.so"
)

KM_PARALLEL_N64_SOURCE_COMMIT = "be8d13e6fddec4eaf705cb04e755e0cf3687d842"
KM_PARALLEL_N64_SOURCE_TREE = "2cec86f7b29182ab8c22481ccaf143f37b97cf0f"
KM_PARALLEL_N64_SOURCE_DATE_EPOCH = 1671482574

KM_PARALLEL_N64_BUILD_OVERLAYS = {
    "armhf": [
        {
            "kind": "git-apply-v1",
            "patch_path": (
                "patches/km_parallel_n64_xtreme_amped_turbo/"
                "makefile-fcommon.patch"
            ),
            "patch_sha256": (
                "ea0338b8f6f6116178d8ebdaee56307afeebd9d2d6a8b974ec8a53f934db3082"
            ),
            "postimage_sha256": (
                "d4f4bdf492b2442eddceaad5b7e4af94b626540981cad8eb2cd97a15c976ae6f"
            ),
            "preimage_sha256": (
                "a3c03dc51f2d886da4b7011c386a916ce6a71585b5cb56fe35dffed8235aee7a"
            ),
            "source_path": "Makefile",
        },
        {
            "kind": "git-apply-v1",
            "patch_path": (
                "patches/km_parallel_n64_xtreme_amped_turbo/"
                "glide64-rdp-gspvertex-def.patch"
            ),
            "patch_sha256": (
                "cf2fbfa956a40cb839981e67bdb2d9dc53758519222481481426b4bd30b20a70"
            ),
            "postimage_sha256": (
                "3ce90f40aed7296e0280853323bc5d8ab372cbe53a51638c28116ccd6b6f1923"
            ),
            "preimage_sha256": (
                "fdcc5df7cb95f3a918f47e1c1c1d3517fbcd4bb530832b20443d77d79c5d094c"
            ),
            "source_path": "glide2gl/src/Glide64/glide64_rdp.c",
        },
        {
            "kind": "git-apply-v1",
            "patch_path": (
                "patches/km_parallel_n64_xtreme_amped_turbo/"
                "rdp-gspvertex-extern.patch"
            ),
            "patch_sha256": (
                "227dfb416a27ece7f8fe2328f126a58b0c83b2fd1fcd7916d873de616e3d2856"
            ),
            "postimage_sha256": (
                "0717c1b921ffddc27dcb2914ff7834bdb09c30ea249d8540deeadc5992ec88ed"
            ),
            "preimage_sha256": (
                "49f6f95e8313457dc888c043f6e2a671fbc35ad8d55844db6c21274917e7ef6a"
            ),
            "source_path": "glide2gl/src/Glide64/rdp.h",
        },
        {
            "kind": "git-apply-v1",
            "patch_path": (
                "patches/km_parallel_n64_xtreme_amped_turbo/"
                "glsm-gldouble-typedef.patch"
            ),
            "patch_sha256": (
                "b8de55727daf4f9c953e0bbdb5157ab5073eebb28108d88ea8580bbd9ed46266"
            ),
            "postimage_sha256": (
                "1ceefefa05f37af1fc1ab98a459f2256b10f1efbfa43dcbd7e5dfd23c034268b"
            ),
            "preimage_sha256": (
                "05655a321adc93f01cedb81dbcd66f3127743200a577a655a35efdaad23ea495"
            ),
            "source_path": "libretro-common/include/glsm/glsm.h",
        },
        {
            "kind": "git-apply-v1",
            "patch_path": (
                "patches/km_parallel_n64_xtreme_amped_turbo/"
                "parallel-al-stdexcept.patch"
            ),
            "patch_sha256": (
                "08ebd16dc47d7160d9760a9fb9f9edf27a383f295940c3ffff4955b866044f56"
            ),
            "postimage_sha256": (
                "06d25734bae596a9b1baf0e062b3399e283f2bf7ec65769b536a06337dfe5a2c"
            ),
            "preimage_sha256": (
                "bf3362000a9a1a12e7c798e129216bad89b8981bb838c8b9e6ea7bc2aab19145"
            ),
            "source_path": "mupen64plus-video-angrylion-thr/parallel_al.cpp",
        },
    ]
}

KM_PARALLEL_N64_SPEC_IDENTITY = {
    "workflow": (
        ".github/workflows/"
        "build-km_parallel_n64_xtreme_amped_turbo.yml"
    ),
    "source_url": "https://github.com/KMFDManic/parallel-n64.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": KM_PARALLEL_N64_SOURCE_COMMIT,
    "source_tree": KM_PARALLEL_N64_SOURCE_TREE,
    "source_dir": KM_PARALLEL_N64_CORE_ID,
    "output_path": "parallel_n64_libretro.so",
    "artifact_name": KM_PARALLEL_N64_BUILD_ARTIFACT_NAME,
    "metadata_repo_path": (
        "metadata/km_parallel_n64_xtreme_amped_turbo_libretro.info"
    ),
    "metadata_artifact_name": (
        "km_parallel_n64_xtreme_amped_turbo_libretro.info"
    ),
    "metadata_sha256": (
        "de131279f27a150ede90f514b1a4fdc1d2b3b9b07272f871d633e81c182d36c2"
    ),
    "targets": ["armhf"],
}


SPEC_GUARD_MESSAGE = (
    "the km_parallel_n64_xtreme_amped_turbo core must preserve its exact "
    "timestamped direct-make source, recipe, metadata, and target contract"
)


def km_parallel_n64_spec_is_well_formed(
    spec: object,
) -> bool:
    """Require the KM fork's exact immutable timestamped catalog identity."""

    identity = KM_PARALLEL_N64_SPEC_IDENTITY
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
                "driver": "direct-make",
                "source_dir": identity["source_dir"],
                "output_path": identity["output_path"],
                "artifact_name": identity["artifact_name"],
                "platforms": {"armhf": "unix"},
                "make_args": [
                    "WITH_DYNAREC=arm",
                    "FORCE_GLES=1",
                    "NOSSE=1",
                ],
                "overlays": KM_PARALLEL_N64_BUILD_OVERLAYS,
                "source_date_epoch": KM_PARALLEL_N64_SOURCE_DATE_EPOCH,
            },
            "metadata": {
                "repo_path": identity["metadata_repo_path"],
                "artifact_name": identity["metadata_artifact_name"],
                "sha256": identity["metadata_sha256"],
            },
            "targets": identity["targets"],
        }
    )

KM_PARALLEL_N64_LOG_CONTRACT_ID = "km-parallel-n64-c-asm-v1"
KM_PARALLEL_N64_EXPECTED_C_COMPILE_COUNT = {"armhf": 167}
KM_PARALLEL_N64_EXPECTED_CXX_COMPILE_COUNT = {"armhf": 44}
KM_PARALLEL_N64_EXPECTED_ASM_COMPILE_COUNT = {"armhf": 1}
KM_PARALLEL_N64_EXPECTED_COMPILE_PAIR_SHA256 = {
    "armhf": (
        "59e09c4063d1ab5f25a8e9054c8255b5ad686a98cbf9e5277416922acb521321"
    ),
}
KM_PARALLEL_N64_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "armhf": (
        "b9f165909f9afa83e334f00be24037db90595342d4ade123eb039fcec85a3955"
    ),
}
KM_PARALLEL_N64_EXPECTED_LINK_OBJECT_SHA256 = {
    "armhf": (
        "7f3954052aefede11080faec91b8771439eb8d69e23d01e2171ce74127802e35"
    ),
}
KM_PARALLEL_N64_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "armhf": (
        "ac9c78fbc82274bb70c77113c2b2d6298967c205cd3fee6dee4833896beb88e7"
    ),
}
# `-lGLESv2` is what FORCE_GLES=1 exists to produce, pinned like the other
# GLES cores: a build that silently lost the GLES renderer no longer proves
# this contract.
KM_PARALLEL_N64_EXPECTED_LINK_OPTIONS = {
    "armhf": (
        "-shared",
        "-Wl,--no-undefined",
        "-Wl,--version-script=./libretro/link.T",
        "-pthread",
        "-lm",
        "-fPIC",
        "-lGLESv2",
    ),
}

KM_PARALLEL_N64_LOG_CONTRACT = CAsmLogContract(
    core_id=KM_PARALLEL_N64_CORE_ID,
    expected_c_compile_count=KM_PARALLEL_N64_EXPECTED_C_COMPILE_COUNT,
    expected_asm_compile_count=KM_PARALLEL_N64_EXPECTED_ASM_COMPILE_COUNT,
    expected_compile_pair_sha256=KM_PARALLEL_N64_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        KM_PARALLEL_N64_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=KM_PARALLEL_N64_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name="parallel_n64_libretro.so",
    expected_link_options=KM_PARALLEL_N64_EXPECTED_LINK_OPTIONS,
    source_commit=KM_PARALLEL_N64_SOURCE_COMMIT,
    source_tree=KM_PARALLEL_N64_SOURCE_TREE,
    expected_cxx_compile_count=KM_PARALLEL_N64_EXPECTED_CXX_COMPILE_COUNT,
    expected_link_language="cxx",
    expected_raw_link_object_sha256=(
        KM_PARALLEL_N64_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def km_parallel_n64_xtreme_amped_turbo_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the KM fork's exact compile set and ordered GLES C++ link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        KM_PARALLEL_N64_LOG_CONTRACT,
    )


__all__ = [
    "KM_PARALLEL_N64_BUILD_ARTIFACT_NAME",
    "KM_PARALLEL_N64_CORE_ID",
    "KM_PARALLEL_N64_LOG_CONTRACT_ID",
    "KM_PARALLEL_N64_SOURCE_COMMIT",
    "KM_PARALLEL_N64_SOURCE_DATE_EPOCH",
    "KM_PARALLEL_N64_SOURCE_TREE",
    "KM_PARALLEL_N64_SPEC_IDENTITY",
    "km_parallel_n64_xtreme_amped_turbo_log_proves_contract",
    "km_parallel_n64_spec_is_well_formed",
]
