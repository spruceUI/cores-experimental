"""Exact individual C-only compile/link contract for CrocoDS."""

from __future__ import annotations

from collections import Counter
import re

from .c_only import COnlyLogContract, c_only_log_proves_contract
from .cpc_common import (
    CpcLogContract,
    cpc_allowed_linker_forwarding,
    cpc_log_proves_contract,
)
from .log_checks import lines_sha256 as _lines_sha256, multiset_lines_sha256 as _multiset_lines_sha256


CROCODS_CORE_ID = "crocods"
CROCODS_NATIVE_GIT_VERSION = " 87bbb3d"
CROCODS_NATIVE_GIT_VERSION_MARKER = (
    f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{CROCODS_NATIVE_GIT_VERSION}"|file'
)
CROCODS_SOURCE_HEAD_MARKER = (
    "HEAD is now at 87bbb3d libretro: add webOS to CI (#23)"
)
CROCODS_EXPECTED_C_COMPILE_COUNT = 50
CROCODS_BUILD_ARTIFACT_NAME = "crocods_libretro.so"
CROCODS_EXPECTED_COMPILE_PAIR_SHA256 = (
    "3fe69417a41c248471e49abad65df02ba125fbaaf88d4e8e414e165d1c955ce3"
)
CROCODS_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "238b3239602a67d1cbcb854dea500010357829accb5604ae18e429727130e16c",
    "armhf": "10b85ed54b31e4eacc8382b6c445e205eae9efc20866e5dfac55afc68ea699dd",
}
CROCODS_EXPECTED_LINK_OBJECT_SHA256 = (
    "9484537e9ebfc0216cb634c9c1f4914485f62a96f85861d74abd47518358fb48"
)
CROCODS_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "45a5d42f201875a4a970ff9ad12610e0fce3c0f9c7df7bd635eee7aa40d1bbc1"
)
CROCODS_EXPECTED_LINK_INVOCATION_SHA256 = {
    "arm64": "2d6a66efb6c684a17ad46c06f8289ffa20da3cc1576415837e3204fff0ea4d94",
    "armhf": "876a2f547960e06b07e4b0f937420eb876e104bbe14fc6e310439b0e8f6ee0ad",
}
CROCODS_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-lm",
)
CROCODS_ALLOWED_LINKER_FORWARDING = cpc_allowed_linker_forwarding(
    CROCODS_EXPECTED_LINK_OPTIONS
)
CROCODS_SUCCESS_TRAILER = (
    "1 core(s) successfully processed:",
    f"\t{CROCODS_CORE_ID}",
)
CROCODS_FORBIDDEN_LOG_FRAGMENTS = (
    "command not found",
    "collect2:",
    "core dumped",
    "dubious ownership",
    "error:",
    "fatal:",
    "internal compiler error",
    "ld returned",
    "make: ***",
    "no such file or directory",
    "permission denied",
    "segmentation fault",
    "undefined reference",
)
CROCODS_EXPECTED_WARNING_COUNT = {"arm64": 9, "armhf": 0}
CROCODS_EXPECTED_NOTE_COUNT = {"arm64": 7, "armhf": 0}
CROCODS_EXPECTED_DIAGNOSTIC_LINE_SHA256 = {
    "arm64": "3cd29831cfb566c5a8db9bbf4ad1734b777be53b32ab16fa3f2c69e6cd2a1e01",
    "armhf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
CROCODS_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256 = {
    "arm64": "0f30158b6786ce8263ec171f364318c225f7fa251ab0df4d8836dd6bd942471b",
    "armhf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
CROCODS_EXPECTED_DIAGNOSTIC_STREAM_SHA256 = {
    "apps_autorun": (
        "bd5de63e95819ab15643b2505d49c9d761894af0f2e04869fc479b03ecc065cd"
    ),
    "platform": (
        "e4654cd95f2ba960f3edce47c91080485fac5ede2f3a9fecb440d4e11aab4ba9"
    ),
    "apps_disk": (
        "159e7913757d093fba7c396f53ed30d527ac760436c9cb84d9543762a74cd28d"
    ),
    "gif": "79c512000ecb54a36a771b82fbcd1a9e3851f6cd397cb63527bd3a54efb7c049",
    "iniparser": (
        "d79938fa15792934548744e90dfcc19a188e3c91d950c4bb396fa45d59d3d074"
    ),
}
CROCODS_DIAGNOSTIC_HEADING_RE = re.compile(
    r"^crocods-core/[A-Za-z0-9_./-]+\.c: In function '[^']+':$"
)
CROCODS_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")
CROCODS_DIAGNOSTIC_FROM_RE = re.compile(r"^\s+from ")
CROCODS_EXPECTED_DIAGNOSTIC_STREAMS = {
    "arm64": {
        "apps_autorun": (
            "crocods-core/apps_autorun.c: In function 'apps_autorun_init':",
            (
                "crocods-core/apps_autorun.c:94:9: warning: ignoring return val"
                "ue of 'fread', declared with attribute warn_unused_result [-Wu"
                "nused-result]"
            ),
            "   94 |         fread(dsk, 1, dsk_size, fic);",
            "      |         ^~~~~~~~~~~~~~~~~~~~~~~~~~~~",
            "crocods-core/apps_autorun.c: In function 'DispAutorun':",
            (
                "crocods-core/apps_autorun.c:355:56: warning: '     ' directive"
                " output truncated writing 5 bytes into a region of size 3 [-Wf"
                "ormat-truncation=]"
            ),
            (
                "  355 |             snprintf(text, 27, \"   %8s %3s %05d %02x  "
                "   \", apps_autorun_files[n].name, apps_autorun_files[n].ext, a"
                "pps_autorun_files[n].nbpages, apps_autorun_files[n].user);"
            ),
            (
                "      |                                                     ~~"
                "~^~"
            ),
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/crocods.h:30,",
            "                 from crocods-core/platform.h:25,",
            "                 from crocods-core/apps_autorun.c:1:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:67:10: note: '__b"
                "uiltin___snprintf_chk' output 30 or more bytes into a destinat"
                "ion of size 27"
            ),
            (
                "   67 |   return __builtin___snprintf_chk (__s, __n, __USE_FOR"
                "TIFY_LEVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~~~~~~~"
            ),
            "   68 |        __bos (__s), __fmt, __va_arg_pack ());",
            "      |        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
            (
                "crocods-core/apps_autorun.c:388:35: warning: '%s' directive wr"
                "iting up to 255 bytes into a region of size 252 [-Wformat-over"
                "flow=]"
            ),
            "  388 |         sprintf(autoString, \"run\\\"%s\\n\", usefile);",
            "      |                                   ^~     ~~~~~~~",
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/crocods.h:30,",
            "                 from crocods-core/platform.h:25,",
            "                 from crocods-core/apps_autorun.c:1:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:36:10: note: '__b"
                "uiltin___sprintf_chk' output between 6 and 261 bytes into a de"
                "stination of size 256"
            ),
            (
                "   36 |   return __builtin___sprintf_chk (__s, __USE_FORTIFY_L"
                "EVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~"
            ),
            "   37 |       __bos (__s), __fmt, __va_arg_pack ());",
            "      |       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
        "platform": (
            "crocods-core/platform.c: In function 'saveIni.part.0':",
            (
                "crocods-core/platform.c:515:27: warning: '.ini' directive writ"
                "ing 4 bytes into a region of size between 2 and 2049 [-Wformat"
                "-overflow=]"
            ),
            "  515 |      sprintf(iniFile0, \"%s.ini\", core->filename);",
            "      |                           ^~~~",
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/crocods.h:30,",
            "                 from crocods-core/platform.h:25,",
            "                 from crocods-core/platform.c:1:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:36:10: note: '__b"
                "uiltin___sprintf_chk' output between 5 and 2052 bytes into a d"
                "estination of size 2049"
            ),
            (
                "   36 |   return __builtin___sprintf_chk (__s, __USE_FORTIFY_L"
                "EVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~"
            ),
            "   37 |       __bos (__s), __fmt, __va_arg_pack ());",
            "      |       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
            "crocods-core/platform.c: In function 'loadIni':",
            (
                "crocods-core/platform.c:1717:30: warning: '.ini' directive wri"
                "ting 4 bytes into a region of size between 2 and 2049 [-Wforma"
                "t-overflow=]"
            ),
            " 1717 |         sprintf(iniFile0, \"%s.ini\", core->filename);",
            "      |                              ^~~~",
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/crocods.h:30,",
            "                 from crocods-core/platform.h:25,",
            "                 from crocods-core/platform.c:1:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:36:10: note: '__b"
                "uiltin___sprintf_chk' output between 5 and 2052 bytes into a d"
                "estination of size 2049"
            ),
            (
                "   36 |   return __builtin___sprintf_chk (__s, __USE_FORTIFY_L"
                "EVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~"
            ),
            "   37 |       __bos (__s), __fmt, __va_arg_pack ());",
            "      |       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
            (
                "crocods-core/platform.c:1684:30: warning: '.ini' directive wri"
                "ting 4 bytes into a region of size between 2 and 2049 [-Wforma"
                "t-overflow=]"
            ),
            " 1684 |         sprintf(iniFile0, \"%s.ini\", core->filename);",
            "      |                              ^~~~",
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/crocods.h:30,",
            "                 from crocods-core/platform.h:25,",
            "                 from crocods-core/platform.c:1:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:36:10: note: '__b"
                "uiltin___sprintf_chk' output between 5 and 2052 bytes into a d"
                "estination of size 2049"
            ),
            (
                "   36 |   return __builtin___sprintf_chk (__s, __USE_FORTIFY_L"
                "EVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~"
            ),
            "   37 |       __bos (__s), __fmt, __va_arg_pack ());",
            "      |       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
        "apps_disk": (
            "crocods-core/apps_disk.c: In function 'DispAppsDisk':",
            (
                "crocods-core/apps_disk.c:218:33: warning: '%s' directive outpu"
                "t may be truncated writing up to 2047 bytes into a region of s"
                "ize 27 [-Wformat-truncation=]"
            ),
            "  218 |             snprintf(text, 27, \"%s\", filename);",
            "      |                                 ^~   ~~~~~~~~",
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/crocods.h:30,",
            "                 from crocods-core/platform.h:25,",
            "                 from crocods-core/apps_disk.c:1:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:67:10: note: '__b"
                "uiltin_snprintf' output between 1 and 2048 bytes into a destin"
                "ation of size 27"
            ),
            (
                "   67 |   return __builtin___snprintf_chk (__s, __n, __USE_FOR"
                "TIFY_LEVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~~~~~~~"
            ),
            "   68 |        __bos (__s), __fmt, __va_arg_pack ());",
            "      |        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
        "gif": (
            "crocods-core/gif.c: In function 'ReadBackgroundGif':",
            (
                "crocods-core/gif.c:142:2: warning: ignoring return value of 'f"
                "read', declared with attribute warn_unused_result [-Wunused-re"
                "sult]"
            ),
            "  142 |  fread(pImageFileMem, 1, dwImageFileSize, fic);",
            "      |  ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
        "iniparser": (
            (
                "crocods-core/iniparser/iniparser.c: In function 'iniparser_loa"
                "d':"
            ),
            (
                "crocods-core/iniparser/iniparser.c:791:32: warning: '__builtin"
                "___sprintf_chk' may write a terminating nul past the end of th"
                "e destination [-Wformat-overflow=]"
            ),
            "  791 |             sprintf(tmp, \"%s:%s\", section, key);",
            "      |                                ^",
            (
                "In file included from /usr/aarch64-linux-gnu/include/stdio.h:8"
                "67,"
            ),
            "                 from crocods-core/iniparser/iniparser.h:17,",
            "                 from crocods-core/iniparser/iniparser.c:12:",
            (
                "/usr/aarch64-linux-gnu/include/bits/stdio2.h:36:10: note: '__b"
                "uiltin___sprintf_chk' output between 2 and 2050 bytes into a d"
                "estination of size 2049"
            ),
            (
                "   36 |   return __builtin___sprintf_chk (__s, __USE_FORTIFY_L"
                "EVEL - 1,"
            ),
            (
                "      |          ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
                "~~~~~~~~~"
            ),
            "   37 |       __bos (__s), __fmt, __va_arg_pack ());",
            "      |       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        ),
    },
    "armhf": {},
}

CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-crocods.yml",
    "source_url": "https://github.com/libretro/libretro-crocods.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "87bbb3d9007ac537864278c6c3149ae3291873f8",
    "source_tree": "5a76585f521954c8e8ebef9b489a4d6c7a8b73db",
    "source_key": CROCODS_CORE_ID,
    "source_dir": "libretro-crocods",
    "output_path": "dist/unix/crocods_libretro.so",
    "artifact_name": CROCODS_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/crocods_libretro.info",
    "metadata_artifact_name": "crocods_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile",
}
CROCODS_LOG_CONTRACT = CpcLogContract(
    core_id=CROCODS_CORE_ID,
    expected_c_compile_count=CROCODS_EXPECTED_C_COMPILE_COUNT,
    build_artifact_name=CROCODS_BUILD_ARTIFACT_NAME,
    expected_link_options=CROCODS_EXPECTED_LINK_OPTIONS,
    source_commit=CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
)
CROCODS_EXACT_LOG_CONTRACT = COnlyLogContract(
    core_id=CROCODS_CORE_ID,
    expected_compile_count=CROCODS_EXPECTED_C_COMPILE_COUNT,
    expected_compile_pair_sha256=CROCODS_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        CROCODS_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=CROCODS_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=CROCODS_BUILD_ARTIFACT_NAME,
    expected_link_options=CROCODS_EXPECTED_LINK_OPTIONS,
    source_commit=CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=(
        CROCODS_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    expected_link_invocation_sha256=(
        CROCODS_EXPECTED_LINK_INVOCATION_SHA256
    ),
)


def _line_is_diagnostic_context(line: str) -> bool:
    """Recognize every reviewed or potentially injected diagnostic line."""

    lowered = line.casefold()
    return bool(
        CROCODS_DIAGNOSTIC_HEADING_RE.fullmatch(line)
        or "warning:" in lowered
        or "note:" in lowered
        or line.startswith("In file included from ")
        or CROCODS_DIAGNOSTIC_CONTEXT_RE.match(line)
        or CROCODS_DIAGNOSTIC_FROM_RE.match(line)
    )


def _diagnostic_context_lines_are_exact(
    build_log_text: str,
    arch: str,
) -> bool:
    """Accept only an interleaving of the reviewed per-source streams."""

    stream_map = CROCODS_EXPECTED_DIAGNOSTIC_STREAMS.get(arch)
    expected_line_sha256 = CROCODS_EXPECTED_DIAGNOSTIC_LINE_SHA256.get(arch)
    expected_headline_sha256 = (
        CROCODS_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256.get(arch)
    )
    if (
        stream_map is None
        or expected_line_sha256 is None
        or expected_headline_sha256 is None
    ):
        return False
    expected_streams = tuple(stream_map.values())
    expected_lines = Counter(
        line for stream in expected_streams for line in stream
    )
    actual_lines = tuple(
        line
        for line in build_log_text.splitlines()
        if _line_is_diagnostic_context(line)
    )
    if (
        Counter(actual_lines) != expected_lines
        or _multiset_lines_sha256(actual_lines) != expected_line_sha256
    ):
        return False
    headlines = tuple(
        line
        for line in actual_lines
        if "warning:" in line.casefold() or "note:" in line.casefold()
    )
    if _multiset_lines_sha256(headlines) != expected_headline_sha256:
        return False

    states = {tuple(0 for _stream in expected_streams)}
    for line in actual_lines:
        next_states: set[tuple[int, ...]] = set()
        for state in states:
            for stream_index, stream in enumerate(expected_streams):
                position = state[stream_index]
                if position >= len(stream) or stream[position] != line:
                    continue
                advanced = list(state)
                advanced[stream_index] += 1
                next_states.add(tuple(advanced))
        if not next_states:
            return False
        states = next_states
    return any(
        all(
            position == len(expected_streams[index])
            for index, position in enumerate(state)
        )
        for state in states
    )


def _crocods_log_has_exact_envelope(
    build_log_text: str,
    arch: str,
) -> bool:
    """Require exact markers, diagnostics, success, and failure absence."""

    lines = build_log_text.splitlines()
    if lines[-len(CROCODS_SUCCESS_TRAILER) :] != list(
        CROCODS_SUCCESS_TRAILER
    ):
        return False
    source_markers = [
        line for line in lines if line.startswith("HEAD is now at ")
    ]
    native_markers = [
        line
        for line in lines
        if line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION|")
    ]
    if (
        source_markers != [CROCODS_SOURCE_HEAD_MARKER]
        or native_markers != [CROCODS_NATIVE_GIT_VERSION_MARKER]
    ):
        return False
    compile_positions = [
        position
        for position, line in enumerate(lines)
        if "-DGIT_VERSION=" in line and " -c " in line
    ]
    link_positions = [
        position
        for position, line in enumerate(lines)
        if f" -o {CROCODS_BUILD_ARTIFACT_NAME} " in line
    ]
    if (
        len(compile_positions) != CROCODS_EXPECTED_C_COMPILE_COUNT
        or len(link_positions) != 1
    ):
        return False
    source_position = lines.index(CROCODS_SOURCE_HEAD_MARKER)
    native_position = lines.index(CROCODS_NATIVE_GIT_VERSION_MARKER)
    link_position = link_positions[0]
    diagnostic_positions = [
        position
        for position, line in enumerate(lines)
        if _line_is_diagnostic_context(line)
    ]
    warning_count = sum(
        "warning:" in line.casefold() for line in lines
    )
    note_count = sum("note:" in line.casefold() for line in lines)
    if (
        warning_count != CROCODS_EXPECTED_WARNING_COUNT.get(arch)
        or note_count != CROCODS_EXPECTED_NOTE_COUNT.get(arch)
        or not (
            source_position < native_position < min(compile_positions)
            and max(compile_positions) < link_position
        )
        or (
            diagnostic_positions
            and not (
                native_position < min(diagnostic_positions)
                and max(diagnostic_positions) < link_position
            )
        )
    ):
        return False
    lowered_lines = [line.casefold() for line in lines]
    if any(
        fragment in line
        for line in lowered_lines
        for fragment in CROCODS_FORBIDDEN_LOG_FRAGMENTS
    ):
        return False
    return _diagnostic_context_lines_are_exact(build_log_text, arch)


def crocods_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove CrocoDS's exact source, argv, diagnostics, and envelope."""

    return bool(
        c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            CROCODS_EXACT_LOG_CONTRACT,
        )
        and cpc_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            CROCODS_LOG_CONTRACT,
        )
        and _crocods_log_has_exact_envelope(build_log_text, arch)
    )
