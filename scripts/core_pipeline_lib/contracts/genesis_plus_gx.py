"""Exact Genesis Plus GX C-only build-log contract."""

from __future__ import annotations

from collections import Counter
import re

from .c_only import COnlyLogContract, c_only_log_proves_contract
from .log_checks import lines_sha256 as _lines_sha256, multiset_lines_sha256 as _multiset_lines_sha256


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
GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_LINE_SHA256 = {
    "arm64": "58b5a069dd62fa3797cc56d38616ae05bdf36ce2a63b5ecd826b820337c6057e",
    "armhf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256 = {
    "arm64": "b7a8795361e2cb1c4b0684e4ff7a14d3979c6e18249b4946b6db35eded857ed0",
    "armhf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
GENESIS_PLUS_GX_EXPECTED_LOG_LINE_MULTISET_SHA256 = {
    "arm64": (
        "f05411146d5dbf14a57c8a25543d8abb116880d56f14424302848059ff32ebd9"
    ),
    "armhf": (
        "e80466c1a92b0c83086211dccde87453ea69a49625ba780ac09f7cd2c54219eb"
    ),
}
GENESIS_PLUS_GX_EXPECTED_PRELUDE_LINE_COUNT = {
    "arm64": 32,
    "armhf": 32,
}
GENESIS_PLUS_GX_EXPECTED_PRELUDE_SHA256 = {
    "arm64": (
        "0e6b7febe535330adb4938533d9739169fd7e9da058f82086038b0c3f83c70ea"
    ),
    "armhf": (
        "8f2a700d59e88f699381819f46fa63c5835ca636ebb7db78397539b01ada2217"
    ),
}
GENESIS_PLUS_GX_PARALLEL_COMMAND = {
    "arm64": {
        "make": "make",
        "cc": "aarch64-linux-gnu-gcc",
        "cxx": "aarch64-linux-gnu-g++",
    },
    "armhf": {
        "make": "gmake",
        "cc": "arm-a30-linux-gnueabihf-gcc",
        "cxx": "arm-a30-linux-gnueabihf-g++",
    },
}
GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAM_SHA256 = {
    "cdrom": "75588b082ea29eb5079fe55305012932abf8e6d70cbdb74d26dd62debdd59b6a",
    "libretro": (
        "3ec5d9deb228a4c085e4732d2f4428f2ac71f18566db39a514176abb3169cf2e"
    ),
}
GENESIS_PLUS_GX_DIAGNOSTIC_HEADING_RE = re.compile(
    r"^(?:[A-Za-z0-9_./-]+\.c: )?In function '[^']+'[:,]$"
)
GENESIS_PLUS_GX_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")
GENESIS_PLUS_GX_DIAGNOSTIC_FROM_RE = re.compile(
    r"^\s+(?:from |inlined from )"
)
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
GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE = {
    "arm64": {
        "cdrom": "libretro/libretro-common/cdrom/cdrom.c",
        "libretro": "libretro/libretro.c",
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
    "native_makefile": "Makefile.libretro",
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


def _canonicalized_parallelism_lines(
    lines: tuple[str, ...],
    arch: str,
) -> tuple[str, ...] | None:
    """Canonicalize only the two reviewed host-capacity job tokens."""

    command = GENESIS_PLUS_GX_PARALLEL_COMMAND.get(arch)
    if command is None:
        return None
    make_program = re.escape(command["make"])
    cc = re.escape(command["cc"])
    cxx = re.escape(command["cxx"])
    clean_re = re.compile(
        rf'^{make_program} -f Makefile\.libretro platform="unix" '
        r"-j([1-9][0-9]*)  clean$"
    )
    build_re = re.compile(
        rf'^{make_program} -f Makefile\.libretro platform="unix" '
        rf'-j([1-9][0-9]*) CC="{cc}" CXX="{cxx}" $'
    )
    clean_matches = [
        (position, match)
        for position, line in enumerate(lines)
        if (match := clean_re.fullmatch(line)) is not None
    ]
    build_matches = [
        (position, match)
        for position, line in enumerate(lines)
        if (match := build_re.fullmatch(line)) is not None
    ]
    if len(clean_matches) != 1 or len(build_matches) != 1:
        return None
    _clean_position, clean_match = clean_matches[0]
    _build_position, build_match = build_matches[0]
    if clean_match.group(1) != build_match.group(1):
        return None
    canonicalized = list(lines)
    for position, match in (clean_matches[0], build_matches[0]):
        start, end = match.span(1)
        line = canonicalized[position]
        canonicalized[position] = line[:start] + "<JOBS>" + line[end:]
    return tuple(canonicalized)


def _canonicalized_wildcard_object_lines(
    lines: tuple[str, ...],
) -> tuple[str, ...]:
    """Sort object tokens inside the two wildcard-ordered Makefile lines.

    The clean `rm -f ...` and the link command enumerate objects in
    $(wildcard) order -- filesystem enumeration, which differs per host
    (GitHub runners emit the identical multiset in a different order).
    Canonicalizing to sorted order keeps every object byte pinned while
    dropping only the environment-dependent ordering.
    """

    canonicalized = []
    for line in lines:
        tokens = line.split(" ")
        if (
            line.startswith("rm -f ./")
            or (" -o " in line and "_libretro.so" in line)
        ) and sum(token.endswith(".o") for token in tokens) > 1:
            objects = sorted(t for t in tokens if t.endswith(".o"))
            rest_iter = iter(objects)
            tokens = [
                next(rest_iter) if t.endswith(".o") else t for t in tokens
            ]
            canonicalized.append(" ".join(tokens))
        else:
            canonicalized.append(line)
    return tuple(canonicalized)


def _line_is_diagnostic_context(line: str) -> bool:
    """Recognize every reviewed or potentially injected diagnostic line."""

    lowered = line.casefold()
    return bool(
        GENESIS_PLUS_GX_DIAGNOSTIC_HEADING_RE.fullmatch(line)
        or "warning:" in lowered
        or "note:" in lowered
        or line.startswith("In file included from ")
        or GENESIS_PLUS_GX_DIAGNOSTIC_CONTEXT_RE.match(line)
        or GENESIS_PLUS_GX_DIAGNOSTIC_FROM_RE.match(line)
    )


def _diagnostic_context_lines_are_exact(
    build_log_text: str,
    arch: str,
) -> bool:
    """Accept only an interleaving of the reviewed diagnostic streams."""

    stream_map = GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAMS.get(arch)
    compile_source_map = (
        GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE.get(arch)
    )
    expected_line_sha256 = (
        GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_LINE_SHA256.get(arch)
    )
    expected_headline_sha256 = (
        GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256.get(arch)
    )
    if (
        stream_map is None
        or compile_source_map is None
        or set(stream_map) != set(compile_source_map)
        or expected_line_sha256 is None
        or expected_headline_sha256 is None
    ):
        return False
    if any(
        _lines_sha256(stream)
        != GENESIS_PLUS_GX_EXPECTED_DIAGNOSTIC_STREAM_SHA256.get(name)
        for name, stream in stream_map.items()
    ):
        return False
    lines = build_log_text.splitlines()
    expected_stream_names = tuple(stream_map)
    expected_streams = tuple(
        stream_map[name] for name in expected_stream_names
    )
    compile_positions: dict[str, int] = {}
    for name, source in compile_source_map.items():
        positions = [
            position
            for position, line in enumerate(lines)
            if f" -c {source} " in line and "-DGIT_VERSION=" in line
        ]
        if len(positions) != 1:
            return False
        compile_positions[name] = positions[0]
    expected_lines = Counter(
        line for stream in expected_streams for line in stream
    )
    actual_context = tuple(
        (position, line)
        for position, line in enumerate(lines)
        if _line_is_diagnostic_context(line)
    )
    actual_lines = tuple(line for _position, line in actual_context)
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
    for line_position, line in actual_context:
        next_states: set[tuple[int, ...]] = set()
        for state in states:
            for stream_index, stream in enumerate(expected_streams):
                position = state[stream_index]
                if position >= len(stream) or stream[position] != line:
                    continue
                stream_name = expected_stream_names[stream_index]
                if (
                    position == 0
                    and line_position <= compile_positions[stream_name]
                ):
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


def _genesis_plus_gx_log_has_exact_envelope(
    build_log_text: str,
    arch: str,
) -> bool:
    """Require exact markers, diagnostics, ordering, and success framing."""

    lines = build_log_text.splitlines()
    expected_log_line_sha256 = (
        GENESIS_PLUS_GX_EXPECTED_LOG_LINE_MULTISET_SHA256.get(arch)
    )
    expected_prelude_line_count = (
        GENESIS_PLUS_GX_EXPECTED_PRELUDE_LINE_COUNT.get(arch)
    )
    expected_prelude_sha256 = (
        GENESIS_PLUS_GX_EXPECTED_PRELUDE_SHA256.get(arch)
    )
    canonicalized_lines = _canonicalized_parallelism_lines(
        tuple(lines), arch
    )
    if canonicalized_lines is not None:
        canonicalized_lines = _canonicalized_wildcard_object_lines(
            canonicalized_lines
        )
    if (
        expected_log_line_sha256 is None
        or expected_prelude_line_count is None
        or expected_prelude_sha256 is None
        or canonicalized_lines is None
        or _multiset_lines_sha256(canonicalized_lines)
        != expected_log_line_sha256
        or lines[-len(GENESIS_PLUS_GX_SUCCESS_TRAILER) :]
        != list(GENESIS_PLUS_GX_SUCCESS_TRAILER)
        or lines.count(GENESIS_PLUS_GX_SUCCESS_TRAILER[0]) != 1
    ):
        return False
    source_markers = [
        line for line in lines if line.startswith("HEAD is now at ")
    ]
    pipeline_markers = [
        line for line in lines if line.startswith("CORE_PIPELINE_")
    ]
    if source_markers != [GENESIS_PLUS_GX_SOURCE_HEAD_MARKER] or (
        pipeline_markers
        != [
            GENESIS_PLUS_GX_NATIVE_GIT_VERSION_BUILD_ARG_MARKER,
            GENESIS_PLUS_GX_NATIVE_GIT_VERSION_MARKER,
        ]
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
        if f" -o {GENESIS_PLUS_GX_BUILD_ARTIFACT_NAME} " in line
    ]
    if (
        len(compile_positions) != GENESIS_PLUS_GX_C_COMPILE_COUNT
        or len(link_positions) != 1
    ):
        return False
    first_compile_position = min(compile_positions)
    link_position = link_positions[0]
    prelude = canonicalized_lines[:first_compile_position]
    if (
        len(prelude) != expected_prelude_line_count
        or _lines_sha256(prelude) != expected_prelude_sha256
        or link_position
        != len(lines) - len(GENESIS_PLUS_GX_SUCCESS_TRAILER) - 1
    ):
        return False
    source_position = lines.index(GENESIS_PLUS_GX_SOURCE_HEAD_MARKER)
    build_arg_position = lines.index(
        GENESIS_PLUS_GX_NATIVE_GIT_VERSION_BUILD_ARG_MARKER
    )
    native_position = lines.index(GENESIS_PLUS_GX_NATIVE_GIT_VERSION_MARKER)
    diagnostic_positions = [
        position
        for position, line in enumerate(lines)
        if _line_is_diagnostic_context(line)
    ]
    warning_count = sum("warning:" in line.casefold() for line in lines)
    note_count = sum("note:" in line.casefold() for line in lines)
    if (
        warning_count != GENESIS_PLUS_GX_EXPECTED_WARNING_COUNT.get(arch)
        or note_count != GENESIS_PLUS_GX_EXPECTED_NOTE_COUNT.get(arch)
        or not (
            source_position
            < build_arg_position
            < native_position
            < first_compile_position
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
        for fragment in GENESIS_PLUS_GX_FORBIDDEN_LOG_FRAGMENTS
    ) or any(
        GENESIS_PLUS_GX_MAKE_FAILURE_RE.match(line)
        for line in lowered_lines
    ):
        return False
    return _diagnostic_context_lines_are_exact(build_log_text, arch)


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
        and _genesis_plus_gx_log_has_exact_envelope(build_log_text, arch)
    )
