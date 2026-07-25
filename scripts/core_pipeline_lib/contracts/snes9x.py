"""Exact Snes9x mixed-language build-log contract."""

from __future__ import annotations

from collections import Counter

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


SNES9X_CORE_ID = "snes9x"
SNES9X_EXPECTED_COMPILE_COUNT = 57
SNES9X_EXPECTED_LANGUAGE_COUNTS = {"cxx": 54, "c": 3}
SNES9X_EXPECTED_COMPILE_PAIR_SHA256 = (
    "5cd28889f12c858efaac9662c4de348f84ecc20b0c2805285960bc8956f67746"
)
SNES9X_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "26eeeb300fe9ffc9455e6d4cd52102ca8dc7e62b28ebfdecb0fdb5c8459abfbc",
    "armhf": "eadb3e225a89e5a34bc45d16b97a927e8ab3c04f93b1ba95f1b1397cb1ba1e06",
}
SNES9X_EXPECTED_LINK_OBJECT_SHA256 = (
    "47a0854a63d41eb9bebff0c7eff705f47674055fcaca6c444cf4fad27ed464cf"
)
SNES9X_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "a00d9f111f06e3d66d2a3fbe09cc6ecffade72e38ead89dcd4c3d7ffee9936db"
)
SNES9X_BUILD_ARTIFACT_NAME = "snes9x_libretro.so"
SNES9X_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-Wl,-z,defs",
    "-flto",
    "-lm",
    "-lz",
)
SNES9X_SEMANTIC_PATH_ALIASES = (("../", ""),)
SNES9X_MEMMAP_WARNING_LINE = (
    "../memmap.cpp:4009:17: warning: unused variable 'close_ret' "
    "[-Wunused-variable]"
)
SNES9X_MEMMAP_WARNING_BLOCK = "\n".join(
    (
        "../memmap.cpp: In member function "
        "'void CMemory::CheckForAnyPatch(const char*, bool8, int32&)':",
        SNES9X_MEMMAP_WARNING_LINE,
        " 4009 |             int close_ret = unzClose(file);",
        "      |                 ^~~~~~~~~",
    )
)
SNES9X_SIGN_COMPARE_WARNING_LINES = {
    "arm64": (
        "../libretro/libretro.cpp:1236:34: warning: comparison of integer "
        "expressions of different signedness: 'int' and 'long unsigned int' "
        "[-Wsign-compare]"
    ),
    "armhf": (
        "../libretro/libretro.cpp:1236:34: warning: comparison of integer "
        "expressions of different signedness: 'int' and 'unsigned int' "
        "[-Wsign-compare]"
    ),
}
SNES9X_SIGN_COMPARE_WARNING_BLOCKS = {
    arch: "\n".join(
        (
            "../libretro/libretro.cpp: In function "
            "'bool retro_load_game(const retro_game_info*)':",
            warning_line,
            " 1236 |             for(int lcv = 0; lcv < sizeof(Memory.RAM); lcv++)",
            "      |                              ~~~~^~~~~~~~~~~~~~~~~~~~",
        )
    )
    for arch, warning_line in SNES9X_SIGN_COMPARE_WARNING_LINES.items()
}
SNES9X_LTO_WARNING_LINE = (
    "lto-wrapper: warning: using serial compilation of 32 LTRANS jobs"
)
SNES9X_LTO_WARNING_BLOCK = "\n".join(
    (
        SNES9X_LTO_WARNING_LINE,
        "lto-wrapper: note: see the '-flto' option documentation for more information",
    )
)
SNES9X_EXPECTED_WARNING_LINES = {
    "arm64": (
        SNES9X_MEMMAP_WARNING_LINE,
        SNES9X_SIGN_COMPARE_WARNING_LINES["arm64"],
    ),
    "armhf": (
        SNES9X_MEMMAP_WARNING_LINE,
        SNES9X_SIGN_COMPARE_WARNING_LINES["armhf"],
        SNES9X_LTO_WARNING_LINE,
    ),
}
SNES9X_EXPECTED_WARNING_BLOCKS = {
    "arm64": (
        SNES9X_MEMMAP_WARNING_BLOCK,
        SNES9X_SIGN_COMPARE_WARNING_BLOCKS["arm64"],
    ),
    "armhf": (
        SNES9X_MEMMAP_WARNING_BLOCK,
        SNES9X_SIGN_COMPARE_WARNING_BLOCKS["armhf"],
        SNES9X_LTO_WARNING_BLOCK,
    ),
}
SNES9X_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-snes9x.yml",
    "source_url": "https://github.com/libretro/snes9x.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "185488cd83aaf274752a742c94d45561cbecb7af",
    "source_tree": "da7c15404a93174aa0972d8ec053471e6cef064d",
    "source_key": SNES9X_CORE_ID,
    "source_dir": "libretro-snes9x",
    "output_path": "dist/unix/snes9x_libretro.so",
    "artifact_name": SNES9X_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/snes9x_libretro.info",
    "metadata_artifact_name": "snes9x_libretro.info",
    "targets": ["arm64", "armhf"],
    "git_version": {
        "derivation": "hyphen-short7-v1",
        "value": "-185488c",
        "compiler_scope": "cxx",
    },
}


def snes9x_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable Snes9x catalog identity."""

    identity = SNES9X_GIT_VERSION_SPEC_IDENTITY
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
                "submodules": [
                    {"path": "external/SPIRV-Cross", "commit": "bccaa94db814af33d8ef05c153e7c34d8bd4d685"},
                    {"path": "external/cubeb", "commit": "ac8474a5929e9de3bce84f16f8c589240eb9f7c4"},
                    {"path": "external/cubeb/cmake/sanitizers-cmake", "commit": "aab6948fa863bc1cbe5d0850bc46b9ef02ed4c1a"},
                    {"path": "external/cubeb/googletest", "commit": "40412d85124f7c6f3d88454583c4633e5e10fc8c"},
                    {"path": "external/glslang", "commit": "9c7fd1a33e5cecbe465e1cd70170167d5e40d398"},
                    {"path": "external/vulkan-headers", "commit": "577baa05033cf1d9236b3d078ca4b3269ed87a2b"},
                    {"path": "win32/libpng/src", "commit": "b78804f9a2568b270ebd30eca954ef7447ba92f7"},
                    {"path": "win32/zlib/src", "commit": "cacf7f1d4e3d44d871b605da3b647f07d718623f"},
                ],
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


SNES9X_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=SNES9X_CORE_ID,
    expected_compile_count=SNES9X_EXPECTED_COMPILE_COUNT,
    expected_language_counts=SNES9X_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=SNES9X_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=SNES9X_EXPECTED_COMPILE_INVOCATION_SHA256,
    expected_link_object_sha256=SNES9X_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=SNES9X_EXPECTED_RAW_LINK_OBJECT_SHA256,
    build_artifact_name=SNES9X_BUILD_ARTIFACT_NAME,
    expected_link_options=SNES9X_EXPECTED_LINK_OPTIONS,
    source_commit=SNES9X_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=SNES9X_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    semantic_path_aliases=SNES9X_SEMANTIC_PATH_ALIASES,
)


def snes9x_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Snes9x's exact compile, link, and reviewed warning sets."""

    if not isinstance(build_log_text, str):
        return False
    expected_warning_lines = SNES9X_EXPECTED_WARNING_LINES.get(arch)
    expected_warning_blocks = SNES9X_EXPECTED_WARNING_BLOCKS.get(arch)
    if expected_warning_lines is None or expected_warning_blocks is None:
        return False
    lowered_log = build_log_text.casefold()
    if any(
        marker in lowered_log
        for marker in (
            "error:",
            "fatal:",
            "undefined reference",
            "dubious ownership",
        )
    ):
        return False
    warning_lines = (
        line
        for line in build_log_text.splitlines()
        if "warning:" in line.casefold()
    )
    if Counter(warning_lines) != Counter(expected_warning_lines) or any(
        build_log_text.count(block) != 1 for block in expected_warning_blocks
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        SNES9X_LOG_CONTRACT,
    )
