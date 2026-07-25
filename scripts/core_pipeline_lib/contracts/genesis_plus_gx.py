"""Exact Genesis Plus GX C-only build-log contract."""

from __future__ import annotations

from collections import Counter
import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


GENESIS_PLUS_GX_CORE_ID = "genesis_plus_gx"
GENESIS_PLUS_GX_C_COMPILE_COUNT = 117
GENESIS_PLUS_GX_COMPILE_PAIR_SHA256 = (
    "c67efaa2ee59bcc7843af62f3988b0d21aa4efc33b76c123b4456159b8dba226"
)
GENESIS_PLUS_GX_COMPILE_INVOCATION_SHA256 = {
    "arm64": (
        "3c5230277f45f7229e68eaa84a9789a40518b53bce0e3e7005ccb96658ca117d"
    ),
    "armhf": (
        "492b944204da4419de18a186ba4ea4303d6b63dfa722a808f8daf203aa7167a2"
    ),
}
GENESIS_PLUS_GX_LINK_OBJECT_SHA256 = (
    "c6cbde832da2a1840d03261aecb79012fd3fc716c61c4e3f69b8eb161d31d8ff"
)
GENESIS_PLUS_GX_RAW_LINK_OBJECT_SHA256 = (
    "fb819ef64ee50aff786ce185fcb8205e7345ceada1d3f41b7ae596e9992a1bdf"
)
# No link-invocation pin: the Makefile's object list is filesystem enumeration
# order, which differs per host (GitHub runners produced the identical
# object multiset in a different order). The link stays pinned by the
# order-tolerant object multisets and the ordered option set.
GENESIS_PLUS_GX_BUILD_ARTIFACT_NAME = "genesis_plus_gx_libretro.so"
GENESIS_PLUS_GX_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./libretro/link.T",
    "-Wl,--no-undefined",
    "-lm",
)
GENESIS_PLUS_GX_SOURCE_HEAD_MARKER = (
    "HEAD is now at fa4dca56 Fetch translations & Recreate "
    "libretro_core_options_intl.h"
)
GENESIS_PLUS_GX_NATIVE_GIT_VERSION_BUILD_ARG_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|" fa4dca5"|'
    "command-scoped-environment"
)
GENESIS_PLUS_GX_NATIVE_GIT_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" fa4dca5"|environment'
)
GENESIS_PLUS_GX_SUCCESS_TRAILER = (
    'cp "genesis_plus_gx_libretro.so" '
    '"/libretro-super/dist/unix/genesis_plus_gx_libretro.so"',
    "1 core(s) successfully processed:",
    f"\t{GENESIS_PLUS_GX_CORE_ID}",
)
GENESIS_PLUS_GX_FORBIDDEN_LOG_FRAGMENTS = (
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
GENESIS_PLUS_GX_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*"
)
GENESIS_PLUS_GX_EXPECTED_WARNING_COUNT = {"arm64": 2, "armhf": 0}
GENESIS_PLUS_GX_EXPECTED_NOTE_COUNT = {"arm64": 1, "armhf": 0}
GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS = {
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
                "libretro/libretro.c:3458:60: warning: '%s' directive output "
                "may be truncated writing up to 255 bytes into a region of "
                "size between 0 and 255 [-Wformat-truncation=]"
            ),
            (
                ' 3458 |          snprintf(content_path, sizeof(content_path), '
                '"%s%c%s.%s",'
            ),
            "      |                                                            ^~",
            (
                " 3459 |                g_rom_dir, slash, g_rom_name, "
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
GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-genesis_plus_gx.yml",
    "source_url": "https://github.com/libretro/Genesis-Plus-GX.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "fa4dca561e08d5be9077419f7b255e1da213ed21",
    "source_tree": "7f4b0916e938e15e046e1c35acd0173aab1aaac3",
    "source_key": GENESIS_PLUS_GX_CORE_ID,
    "source_dir": "libretro-genesis_plus_gx",
    "output_path": "dist/unix/genesis_plus_gx_libretro.so",
    "artifact_name": GENESIS_PLUS_GX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/genesis_plus_gx_libretro.info"
    ),
    "metadata_artifact_name": "genesis_plus_gx_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile.libretro",    "overlays": {
        "arm64": [
            {
                "kind": "git-apply-v1",
                "patch_path": "patches/genesis_plus_gx/makefile-sort-wildcard-sources.patch",
                "patch_sha256": (
                    "f1a35fd09937bbae35e34e814d534f4c4d7f4e926a23dfcd430a35ec430fdd23"
                ),
                "source_path": "libretro/Makefile.common",
                "preimage_sha256": (
                    "3f1f5dc4ecf8d98471c25ef51dfba1f2f9ab6f5f30a4d9c17d15d7d4a2d5ece4"
                ),
                "postimage_sha256": (
                    "b9deb7b93719f8bfbda24d929d1166a228c2a5647c08e1c8cfb32b313f468753"
                ),
            }
        ],
        "armhf": [
            {
                "kind": "git-apply-v1",
                "patch_path": "patches/genesis_plus_gx/makefile-sort-wildcard-sources.patch",
                "patch_sha256": (
                    "f1a35fd09937bbae35e34e814d534f4c4d7f4e926a23dfcd430a35ec430fdd23"
                ),
                "source_path": "libretro/Makefile.common",
                "preimage_sha256": (
                    "3f1f5dc4ecf8d98471c25ef51dfba1f2f9ab6f5f30a4d9c17d15d7d4a2d5ece4"
                ),
                "postimage_sha256": (
                    "b9deb7b93719f8bfbda24d929d1166a228c2a5647c08e1c8cfb32b313f468753"
                ),
            }
        ],
    },
}

GENESIS_PLUS_GX_LOG_CONTRACT = COnlyLogContract(
    core_id=GENESIS_PLUS_GX_CORE_ID,
    expected_compile_count=GENESIS_PLUS_GX_C_COMPILE_COUNT,
    expected_compile_pair_sha256=GENESIS_PLUS_GX_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        GENESIS_PLUS_GX_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=GENESIS_PLUS_GX_LINK_OBJECT_SHA256,
    build_artifact_name=GENESIS_PLUS_GX_BUILD_ARTIFACT_NAME,
    expected_link_options=GENESIS_PLUS_GX_EXPECTED_LINK_OPTIONS,
    source_commit=GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY[
        "source_commit"
    ],
    source_tree=GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=GENESIS_PLUS_GX_RAW_LINK_OBJECT_SHA256,
)


def _genesis_plus_gx_log_binds_markers_and_diagnostics(
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
    ] != [GENESIS_PLUS_GX_SOURCE_HEAD_MARKER]:
        return False
    if [
        line for line in lines if line.startswith("CORE_PIPELINE_")
    ] != [
        GENESIS_PLUS_GX_NATIVE_GIT_VERSION_BUILD_ARG_MARKER,
        GENESIS_PLUS_GX_NATIVE_GIT_VERSION_MARKER,
    ]:
        return False
    trailer = list(GENESIS_PLUS_GX_SUCCESS_TRAILER)
    if lines[-len(trailer):] != trailer or lines.count(trailer[0]) != 1:
        return False
    lowered = [line.casefold() for line in lines]
    if any(
        fragment in line
        for line in lowered
        for fragment in GENESIS_PLUS_GX_FORBIDDEN_LOG_FRAGMENTS
    ) or any(GENESIS_PLUS_GX_MAKE_FAILURE_RE.match(line) for line in lowered):
        return False
    if sum(
        "warning:" in line for line in lowered
    ) != GENESIS_PLUS_GX_EXPECTED_WARNING_COUNT.get(arch) or sum(
        "note:" in line for line in lowered
    ) != GENESIS_PLUS_GX_EXPECTED_NOTE_COUNT.get(arch):
        return False
    line_multiset = Counter(lines)
    for stream in GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS.get(arch, {}).values():
        for line in stream:
            if line_multiset[line] < 1:
                return False
    return True


def genesis_plus_gx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove the base core's exact source, argv, diagnostics, and envelope."""

    return bool(
        c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            GENESIS_PLUS_GX_LOG_CONTRACT,
        )
        and _genesis_plus_gx_log_binds_markers_and_diagnostics(build_log_text, arch)
    )
