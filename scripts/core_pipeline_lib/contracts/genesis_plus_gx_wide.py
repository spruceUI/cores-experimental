"""Exact Genesis Plus GX Wide C-only build-log contract."""

from __future__ import annotations

from collections import Counter
import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


GENESIS_PLUS_GX_WIDE_CORE_ID = "genesis_plus_gx_wide"
GENESIS_PLUS_GX_WIDE_C_COMPILE_COUNT = 106
GENESIS_PLUS_GX_WIDE_COMPILE_PAIR_SHA256 = (
    "d57eadc2c06b2c88ec9fd5ad2b0b3d30ef45c918044e571dce9b1861bbe0574d"
)
GENESIS_PLUS_GX_WIDE_COMPILE_INVOCATION_SHA256 = {
    "arm64": (
        "4fbe11782d08a47d8677e82d6980d9b2d3c76cb5943364dc603d809d385b0267"
    ),
    "armhf": (
        "c3ca0f9e58e1e516cc7c4d8a65f485a4f1801e182de8660abab8f0d49f2bd1c6"
    ),
}
GENESIS_PLUS_GX_WIDE_LINK_OBJECT_SHA256 = (
    "4e8b7b239868ea5a7f545c7e0fe962406356c5a3d07599c82008d9658d799b5b"
)
GENESIS_PLUS_GX_WIDE_RAW_LINK_OBJECT_SHA256 = (
    "ba4396294516013831bd08a87deb9437b1ad4949730820ce397a94e9d75fad0f"
)
# No link-invocation pin: the Makefile's object list is filesystem enumeration
# order, which differs per host (GitHub runners produced the identical
# object multiset in a different order). The link stays pinned by the
# order-tolerant object multisets and the ordered option set.
GENESIS_PLUS_GX_WIDE_BUILD_ARTIFACT_NAME = (
    "genesis_plus_gx_wide_libretro.so"
)
GENESIS_PLUS_GX_WIDE_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./libretro/link.T",
    "-Wl,--no-undefined",
    "-lm",
)
GENESIS_PLUS_GX_WIDE_SOURCE_HEAD_MARKER = (
    "HEAD is now at 29d9d10 state: save 68k bus refresh cycle counter "
    "(fixes savestate/netplay desync)"
)
GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_BUILD_ARG_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|" 29d9d10"|'
    "command-scoped-environment"
)
GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 29d9d10"|environment'
)
GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER = (
    'cp "genesis_plus_gx_wide_libretro.so" '
    '"/libretro-super/dist/unix/genesis_plus_gx_wide_libretro.so"',
    "1 core(s) successfully processed:",
    f"\t{GENESIS_PLUS_GX_WIDE_CORE_ID}",
)
GENESIS_PLUS_GX_WIDE_FORBIDDEN_LOG_FRAGMENTS = (
    "command not found",
    "collect2:",
    "core dumped",
    "dubious ownership",
    "error:",
    "fatal:",
    "internal compiler error",
    "ld returned",
    "no such file or directory",
    "permission denied",
    "segmentation fault",
    "undefined reference",
)
GENESIS_PLUS_GX_WIDE_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*"
)
GENESIS_PLUS_GX_WIDE_EXPECTED_WARNING_COUNT = {"arm64": 2, "armhf": 0}
GENESIS_PLUS_GX_WIDE_EXPECTED_NOTE_COUNT = {"arm64": 1, "armhf": 0}
GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS = {
    "arm64": {
        "cdrom": (
            "In file included from /usr/aarch64-linux-gnu/include/stdio.h:867,",
            (
                "                 from ./libretro/libretro-common/include/"
                "cdrom/cdrom.h:26,"
            ),
            "                 from libretro/libretro-common/cdrom/cdrom.c:27:",
            "In function 'printf',",
            (
                "    inlined from 'cdrom_print_sense_data.part.0' at "
                "libretro/libretro-common/cdrom/cdrom.c:178:4:"
            ),
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:107:10: "
                "warning: '%s' directive argument is null "
                "[-Wformat-overflow=]"
            ),
            (
                "  107 |   return __printf_chk (__USE_FORTIFY_LEVEL - 1, "
                "__fmt, __va_arg_pack ());"
            ),
            "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
        "libretro": (
            "libretro/libretro.c: In function 'retro_load_game':",
            (
                "libretro/libretro.c:3741:60: warning: '%s' directive output "
                "may be truncated writing up to 255 bytes into a region of "
                "size between 0 and 255 [-Wformat-truncation=]"
            ),
            (
                ' 3741 |          snprintf(content_path, sizeof(content_path), '
                '"%s%c%s.%s",'
            ),
            "      |                                                            ^~",
            (
                " 3742 |                g_rom_dir, slash, g_rom_name, "
                "content_ext);"
            ),
            "      |                                  ~~~~~~~~~~" + " " * 17,
            "In file included from /usr/aarch64-linux-gnu/include/stdio.h:867,",
            "                 from libretro/libretro.c:47:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:67:10: note: "
                "'__builtin___snprintf_chk' output between 3 and 520 bytes "
                "into a destination of size 256"
            ),
            (
                "   67 |   return __builtin___snprintf_chk (__s, __n, "
                "__USE_FORTIFY_LEVEL - 1,"
            ),
            "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
            "   68 |        __bos (__s), __fmt, __va_arg_pack ());",
            "      |        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
    },
    "armhf": {},
}
GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-genesis_plus_gx_wide.yml",
    "source_url": "https://github.com/libretro/Genesis-Plus-GX-Wide.git",
    "source_requested_ref": "refs/heads/main",
    "source_commit": "29d9d104338f46bc2e65438fb207bcf54f701e92",
    "source_tree": "27e05ed457d9c10e51b6c69067e1c05599df08fb",
    "source_key": GENESIS_PLUS_GX_WIDE_CORE_ID,
    "source_dir": "libretro-genesis_plus_gx_wide",
    "output_path": "dist/unix/genesis_plus_gx_wide_libretro.so",
    "artifact_name": GENESIS_PLUS_GX_WIDE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/genesis_plus_gx_wide_libretro.info"
    ),
    "metadata_artifact_name": "genesis_plus_gx_wide_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile.libretro",    "overlays": {
        "arm64": [
            {
                "kind": "git-apply-v1",
                "patch_path": "patches/genesis_plus_gx_wide/makefile-sort-wildcard-sources.patch",
                "patch_sha256": (
                    "c7e9bb397878b30d5012e9932005dbbe6ece146b859485737e1cf29cef00d87a"
                ),
                "source_path": "libretro/Makefile.common",
                "preimage_sha256": (
                    "6b6b82ec878235104364b2c011b95b689683630d8bc4ceefd4344900af079a50"
                ),
                "postimage_sha256": (
                    "0d1bc24fbb4085a5894977ac5a6e743658e786245320551f6be640899677af2c"
                ),
            }
        ],
        "armhf": [
            {
                "kind": "git-apply-v1",
                "patch_path": "patches/genesis_plus_gx_wide/makefile-sort-wildcard-sources.patch",
                "patch_sha256": (
                    "c7e9bb397878b30d5012e9932005dbbe6ece146b859485737e1cf29cef00d87a"
                ),
                "source_path": "libretro/Makefile.common",
                "preimage_sha256": (
                    "6b6b82ec878235104364b2c011b95b689683630d8bc4ceefd4344900af079a50"
                ),
                "postimage_sha256": (
                    "0d1bc24fbb4085a5894977ac5a6e743658e786245320551f6be640899677af2c"
                ),
            }
        ],
    },
}

GENESIS_PLUS_GX_WIDE_LOG_CONTRACT = COnlyLogContract(
    core_id=GENESIS_PLUS_GX_WIDE_CORE_ID,
    expected_compile_count=GENESIS_PLUS_GX_WIDE_C_COMPILE_COUNT,
    expected_compile_pair_sha256=GENESIS_PLUS_GX_WIDE_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        GENESIS_PLUS_GX_WIDE_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=GENESIS_PLUS_GX_WIDE_LINK_OBJECT_SHA256,
    build_artifact_name=GENESIS_PLUS_GX_WIDE_BUILD_ARTIFACT_NAME,
    expected_link_options=GENESIS_PLUS_GX_WIDE_EXPECTED_LINK_OPTIONS,
    source_commit=(
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
    ),
    source_tree=(
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"]
    ),
    expected_raw_link_object_sha256=(
        GENESIS_PLUS_GX_WIDE_RAW_LINK_OBJECT_SHA256
    ),
)


def _genesis_plus_gx_wide_log_binds_markers_and_diagnostics(
    build_log_text: str,
    arch: str,
) -> bool:
    """Bind provenance markers, success framing, and reviewed diagnostics.

    Content pins only: the exact source/native-version markers, the
    pipeline's success trailer, failure guards, the reviewed per-arch
    warning/note counts, and every reviewed diagnostic line's presence.
    Line ordering and whole-log transcripts are deliberately unpinned —
    they encode the build environment, not build identity.
    """

    lines = build_log_text.splitlines()
    if [
        line for line in lines if line.startswith("HEAD is now at ")
    ] != [GENESIS_PLUS_GX_WIDE_SOURCE_HEAD_MARKER]:
        return False
    if [
        line for line in lines if line.startswith("CORE_PIPELINE_")
    ] != [
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_BUILD_ARG_MARKER,
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_MARKER,
    ]:
        return False
    trailer = list(GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER)
    if lines[-len(trailer):] != trailer or lines.count(trailer[0]) != 1:
        return False
    lowered = [line.casefold() for line in lines]
    if any(
        fragment in line
        for line in lowered
        for fragment in GENESIS_PLUS_GX_WIDE_FORBIDDEN_LOG_FRAGMENTS
    ) or any(GENESIS_PLUS_GX_WIDE_MAKE_FAILURE_RE.match(line) for line in lowered):
        return False
    if sum(
        "warning:" in line for line in lowered
    ) != GENESIS_PLUS_GX_WIDE_EXPECTED_WARNING_COUNT.get(arch) or sum(
        "note:" in line for line in lowered
    ) != GENESIS_PLUS_GX_WIDE_EXPECTED_NOTE_COUNT.get(arch):
        return False
    line_multiset = Counter(lines)
    for stream in GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS.get(arch, {}).values():
        for line in stream:
            if line_multiset[line] < 1:
                return False
    return True


def genesis_plus_gx_wide_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the Wide core's exact source, argv, diagnostics, and envelope."""

    return bool(
        c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            GENESIS_PLUS_GX_WIDE_LOG_CONTRACT,
        )
        and _genesis_plus_gx_wide_log_binds_markers_and_diagnostics(
            build_log_text,
            arch,
        )
    )
