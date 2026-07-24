"""Exact blueMSX mixed-language native-version build contract."""

from __future__ import annotations

from collections import Counter
import re
import shlex

from .command_line import output_option
from .compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


BLUEMSX_CORE_ID = "bluemsx"
BLUEMSX_BUILD_ARTIFACT_NAME = "bluemsx_libretro.so"
BLUEMSX_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
BLUEMSX_NATIVE_GIT_VERSION = " 5f595c7"
BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN = r'-DGIT_VERSION=\"" 5f595c7"\"'
BLUEMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN = '-DGIT_VERSION=" 5f595c7"'
BLUEMSX_SOURCE_HEAD_MARKER = (
    "HEAD is now at 5f595c7 Android: keep legacy callback-pointer "
    "mismatches as warnings"
)
BLUEMSX_NATIVE_VERSION_MARKER = (
    'CORE_PIPELINE_NATIVE_GIT_VERSION|" 5f595c7"|file'
)
BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-bluemsx.yml",
    "source_url": "https://github.com/libretro/blueMSX-libretro.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "5f595c79906ff3379641b5ee8f3796106214a0a4",
    "source_tree": "1d6e218616f313f9147aa7ecf3f74584a9aaa23c",
    "source_key": BLUEMSX_CORE_ID,
    "source_dir": "libretro-bluemsx",
    "output_path": "dist/unix/bluemsx_libretro.so",
    "artifact_name": BLUEMSX_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/bluemsx_libretro.info",
    "metadata_artifact_name": "bluemsx_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile.libretro",
}

BLUEMSX_EXPECTED_COMPILE_COUNT = 269
BLUEMSX_EXPECTED_LANGUAGE_COUNTS = {"c": 255, "cxx": 14}
BLUEMSX_EXPECTED_COMPILE_PAIR_SHA256 = (
    "cd7ff9673f83630e220fda7186b2887fe5cfb208019388223a503d4da0f385ec"
)
BLUEMSX_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "b164112377465c8b7d41d82f5a2385c19ce1f0021b3f8d1b48dc64ed025f96a1",
    "armhf": "82e9389a71aba5a01ef6229a80771ac70891b16dd8e1ec1fa59390049f840dca",
}
BLUEMSX_EXPECTED_LINK_OBJECT_SHA256 = (
    "4f7e5b8f24429107aa86d06e304bce477137c2cbe1468bae5b613c4067f550b4"
)
BLUEMSX_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "7f65220d6c91961e84d4801548bd0da14349843fe176d69d7149752cc64a3d86"
)
BLUEMSX_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
)
BLUEMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256 = {
    "arm64": "8b495607ac268e960f0dc4822d07388636f8137e379dd15371ccada08776b17d",
    "armhf": "9b638c84c69d48f61577f6cdcccb22acf618e1ab353ec203f4330c19d3df6483",
}
BLUEMSX_WARNING_SUPPRESSION_OPTION = "-w"
BLUEMSX_FORBIDDEN_EMITTED_DIAGNOSTIC_MARKERS = (
    "warning:",
    "error:",
    "fatal:",
    "note:",
    "undefined reference",
    "dubious ownership",
    "cannot find",
    "no such file or directory",
    "internal compiler error",
    "permission denied",
    "command not found",
    "collect2: ld returned",
    "file format not recognized",
    "segmentation fault",
    "core dumped",
    "killed",
    "aborted",
    "terminated",
    "bus error",
    "illegal instruction",
    "broken pipe",
    "floating point exception",
)
BLUEMSX_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def bluemsx_spec_is_well_formed(spec: object) -> bool:
    """Require blueMSX's complete immutable catalog identity."""

    identity = BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "git_version": {
                    "derivation": BLUEMSX_NATIVE_GIT_VERSION_DERIVATION,
                    "value": BLUEMSX_NATIVE_GIT_VERSION,
                    "compiler_scope": identity["compiler_scope"],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


def bluemsx_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the reviewed blueMSX tree."""

    identity = BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == BLUEMSX_CORE_ID
        and isinstance(source, dict)
        and source
        == {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
    )


def bluemsx_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require the exact promoted blueMSX C-scoped native build record."""

    identity = BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and bluemsx_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": BLUEMSX_NATIVE_GIT_VERSION_DERIVATION,
                "value": BLUEMSX_NATIVE_GIT_VERSION,
                "compiler_scope": identity["compiler_scope"],
            },
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


BLUEMSX_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=BLUEMSX_CORE_ID,
    expected_compile_count=BLUEMSX_EXPECTED_COMPILE_COUNT,
    expected_language_counts=BLUEMSX_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=BLUEMSX_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        BLUEMSX_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=BLUEMSX_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        BLUEMSX_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=BLUEMSX_BUILD_ARTIFACT_NAME,
    expected_link_options=BLUEMSX_EXPECTED_LINK_OPTIONS,
    source_commit=BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_link_language="cxx",
    expected_ordered_link_argv_sha256=(
        BLUEMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256
    ),
)


def _bluemsx_markers_are_exact(lines: list[str]) -> bool:
    observed = tuple(
        line
        for line in lines
        if line.startswith("HEAD is now at ")
        or line.startswith("CORE_PIPELINE_")
    )
    return observed == (
        BLUEMSX_SOURCE_HEAD_MARKER,
        BLUEMSX_NATIVE_VERSION_MARKER,
    )


def _bluemsx_compile_scope_and_suppression_are_exact(
    lines: list[str],
    arch: str,
) -> tuple[list[int], list[tuple[int, list[str]]]] | None:
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        return None
    compile_positions: list[int] = []
    link_commands: list[tuple[int, list[str]]] = []
    language_counts: Counter[str] = Counter()
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return None
        if not tokens or tokens[0] not in expected_compilers:
            continue
        if "-c" in tokens:
            compile_positions.append(line_number)
            is_cxx = tokens[0] in expected_cxx_compilers
            language = "cxx" if is_cxx else "c"
            language_counts[language] += 1
            version_tokens = [
                token for token in tokens[1:] if "GIT_VERSION" in token
            ]
            if (
                tokens.count(BLUEMSX_WARNING_SUPPRESSION_OPTION) != 1
                or (
                    is_cxx
                    and version_tokens
                )
                or (
                    not is_cxx
                    and version_tokens
                    != [BLUEMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN]
                )
            ):
                return None
            continue
        parsed_output = output_option(tokens)
        if (
            parsed_output is not None
            and parsed_output[0] == BLUEMSX_BUILD_ARTIFACT_NAME
        ):
            link_commands.append((line_number, tokens))
    if (
        len(compile_positions) != BLUEMSX_EXPECTED_COMPILE_COUNT
        or dict(language_counts) != BLUEMSX_EXPECTED_LANGUAGE_COUNTS
        or len(link_commands) != 1
    ):
        return None
    return compile_positions, link_commands


def bluemsx_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove exact C-scoped version, suppression, compile, and link argv."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in BLUEMSX_FORBIDDEN_EMITTED_DIAGNOSTIC_MARKERS
        )
        or BLUEMSX_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != BLUEMSX_EXPECTED_LANGUAGE_COUNTS["c"]
        or build_log_text.count(BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN)
        != BLUEMSX_EXPECTED_LANGUAGE_COUNTS["c"]
    ):
        return False
    lines = build_log_text.splitlines()
    if not _bluemsx_markers_are_exact(lines):
        return False
    commands = _bluemsx_compile_scope_and_suppression_are_exact(lines, arch)
    if commands is None:
        return False
    compile_positions, link_commands = commands
    link_position, _link_tokens = link_commands[0]
    source_position = lines.index(BLUEMSX_SOURCE_HEAD_MARKER)
    marker_position = lines.index(BLUEMSX_NATIVE_VERSION_MARKER)
    if not (
        source_position < marker_position < min(compile_positions)
        and max(compile_positions) < link_position
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        BLUEMSX_LOG_CONTRACT,
    )
