"""Exact Genesis Plus GX Wide C-only build-log contract."""

from __future__ import annotations

from collections import Counter
import re

from .c_only import COnlyLogContract, c_only_log_proves_contract
from .log_checks import lines_sha256 as _lines_sha256, multiset_lines_sha256 as _multiset_lines_sha256


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
GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_LINE_SHA256 = {
    "arm64": "f2deace00b26c083673f74eb1e618655090ea0c4114da0ec65f84eebdba58136",
    "armhf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256 = {
    "arm64": "a84a959864a7c18153cfefac064a2c8ddf6525ce9182ff92d1374b6e97ed6daa",
    "armhf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
GENESIS_PLUS_GX_WIDE_EXPECTED_LOG_LINE_MULTISET_SHA256 = {
    "arm64": (
        "f911a5764283f3a146cffaa6c03b2bc7f1b6eb071550da68370508ab8fd25636"
    ),
    "armhf": (
        "5a16f15e7696cd9fef7cf9f3d2a8ceb8256d79c4a142cc04b220677117826b83"
    ),
}
GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_LINE_COUNT = {
    "arm64": 32,
    "armhf": 32,
}
GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_SHA256 = {
    "arm64": (
        "d6c561277c7d7e8a8b3f6b5f9ca9b7c482612347486e6bb76fa7f3c48a0013be"
    ),
    "armhf": (
        "88c5d0aa8a02b0c5a2759e928fbce5297986567cafd6ba90d268c5fc53516e20"
    ),
}
GENESIS_PLUS_GX_WIDE_PARALLEL_COMMAND = {
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
GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAM_SHA256 = {
    "cdrom": "75588b082ea29eb5079fe55305012932abf8e6d70cbdb74d26dd62debdd59b6a",
    "libretro": (
        "3c04ad9cbe0da6e7c6f95f8af8635ebf416196fd26a393e1367af5d0862e275e"
    ),
}
GENESIS_PLUS_GX_WIDE_DIAGNOSTIC_HEADING_RE = re.compile(
    r"^(?:[A-Za-z0-9_./-]+\.c: )?In function '[^']+'[:,]$"
)
GENESIS_PLUS_GX_WIDE_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")
GENESIS_PLUS_GX_WIDE_DIAGNOSTIC_FROM_RE = re.compile(
    r"^\s+(?:from |inlined from )"
)
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
GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE = {
    "arm64": {
        "cdrom": "libretro/libretro-common/cdrom/cdrom.c",
        "libretro": "libretro/libretro.c",
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
    "native_makefile": "Makefile.libretro",
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


def _canonicalized_parallelism_lines(
    lines: tuple[str, ...],
    arch: str,
) -> tuple[str, ...] | None:
    """Canonicalize only the two reviewed host-capacity job tokens."""

    command = GENESIS_PLUS_GX_WIDE_PARALLEL_COMMAND.get(arch)
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
    clean_position, clean_match = clean_matches[0]
    build_position, build_match = build_matches[0]
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
        GENESIS_PLUS_GX_WIDE_DIAGNOSTIC_HEADING_RE.fullmatch(line)
        or "warning:" in lowered
        or "note:" in lowered
        or line.startswith("In file included from ")
        or GENESIS_PLUS_GX_WIDE_DIAGNOSTIC_CONTEXT_RE.match(line)
        or GENESIS_PLUS_GX_WIDE_DIAGNOSTIC_FROM_RE.match(line)
    )


def _diagnostic_context_lines_are_exact(
    build_log_text: str,
    arch: str,
) -> bool:
    """Accept only an interleaving of the reviewed diagnostic streams."""

    stream_map = GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAMS.get(arch)
    compile_source_map = (
        GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_COMPILE_SOURCE.get(arch)
    )
    expected_line_sha256 = (
        GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_LINE_SHA256.get(arch)
    )
    expected_headline_sha256 = (
        GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_HEADLINE_SHA256.get(arch)
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
        != GENESIS_PLUS_GX_WIDE_EXPECTED_DIAGNOSTIC_STREAM_SHA256.get(name)
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


def _genesis_plus_gx_wide_log_has_exact_envelope(
    build_log_text: str,
    arch: str,
) -> bool:
    """Require exact markers, diagnostics, ordering, and success framing."""

    lines = build_log_text.splitlines()
    canonicalized_lines = _canonicalized_parallelism_lines(
        tuple(lines), arch
    )
    if canonicalized_lines is not None:
        canonicalized_lines = _canonicalized_wildcard_object_lines(
            canonicalized_lines
        )
    expected_log_line_sha256 = (
        GENESIS_PLUS_GX_WIDE_EXPECTED_LOG_LINE_MULTISET_SHA256.get(arch)
    )
    expected_prelude_line_count = (
        GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_LINE_COUNT.get(arch)
    )
    expected_prelude_sha256 = (
        GENESIS_PLUS_GX_WIDE_EXPECTED_PRELUDE_SHA256.get(arch)
    )
    if (
        expected_log_line_sha256 is None
        or expected_prelude_line_count is None
        or expected_prelude_sha256 is None
        or canonicalized_lines is None
        or _multiset_lines_sha256(canonicalized_lines)
        != expected_log_line_sha256
        or lines[-len(GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER) :]
        != list(GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER)
        or lines.count(GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER[0]) != 1
    ):
        return False
    source_markers = [
        line for line in lines if line.startswith("HEAD is now at ")
    ]
    pipeline_markers = [
        line for line in lines if line.startswith("CORE_PIPELINE_")
    ]
    if source_markers != [GENESIS_PLUS_GX_WIDE_SOURCE_HEAD_MARKER] or (
        pipeline_markers
        != [
            GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_BUILD_ARG_MARKER,
            GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_MARKER,
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
        if f" -o {GENESIS_PLUS_GX_WIDE_BUILD_ARTIFACT_NAME} " in line
    ]
    if (
        len(compile_positions) != GENESIS_PLUS_GX_WIDE_C_COMPILE_COUNT
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
        != len(lines) - len(GENESIS_PLUS_GX_WIDE_SUCCESS_TRAILER) - 1
    ):
        return False
    source_position = lines.index(GENESIS_PLUS_GX_WIDE_SOURCE_HEAD_MARKER)
    build_arg_position = lines.index(
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_BUILD_ARG_MARKER
    )
    native_position = lines.index(
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_MARKER
    )
    diagnostic_positions = [
        position
        for position, line in enumerate(lines)
        if _line_is_diagnostic_context(line)
    ]
    warning_count = sum("warning:" in line.casefold() for line in lines)
    note_count = sum("note:" in line.casefold() for line in lines)
    if (
        warning_count
        != GENESIS_PLUS_GX_WIDE_EXPECTED_WARNING_COUNT.get(arch)
        or note_count != GENESIS_PLUS_GX_WIDE_EXPECTED_NOTE_COUNT.get(arch)
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
        for fragment in GENESIS_PLUS_GX_WIDE_FORBIDDEN_LOG_FRAGMENTS
    ) or any(
        GENESIS_PLUS_GX_WIDE_MAKE_FAILURE_RE.match(line)
        for line in lowered_lines
    ):
        return False
    return _diagnostic_context_lines_are_exact(build_log_text, arch)


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
        and _genesis_plus_gx_wide_log_has_exact_envelope(
            build_log_text,
            arch,
        )
    )
