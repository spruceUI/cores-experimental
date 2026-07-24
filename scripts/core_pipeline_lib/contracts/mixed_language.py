"""Neutral mixed C/C++ compile and link-log proof machinery."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import shlex

from ..errors import PipelineError
from ..foundation import sha256_bytes
from .command_line import (
    FILE_OPERAND_FLAGS,
    command_line_is_lexically_safe,
    command_uses_response_file,
    ordered_command_argv_sha256,
    output_option,
    semantic_log_path,
)
from .compiler import (
    COMPILER_COMMAND_RE,
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)


@dataclass(frozen=True, slots=True)
class MixedLanguageLogContract:
    """Exact per-core parameters consumed by the neutral proof engine."""

    core_id: str
    expected_compile_count: int
    expected_language_counts: Mapping[str, int]
    expected_compile_pair_sha256: str
    expected_compile_invocation_sha256: Mapping[str, str]
    expected_link_object_sha256: str
    expected_raw_link_object_sha256: str
    build_artifact_name: str
    expected_link_options: tuple[str, ...]
    source_commit: str
    source_tree: str
    semantic_path_aliases: tuple[tuple[str, str], ...] = ()
    expected_link_language: str = "cxx"
    expected_ordered_link_argv_sha256: Mapping[str, str] | None = None
    # Some Makefiles set `CC = $(CXX)` and compile every translation unit with
    # the C++ driver regardless of suffix (fake08). Opting in allows a `.c`
    # source to be compiled by the C++ compiler; a `.cpp` source still requires
    # the C++ compiler, and the language is still counted by suffix. The exact
    # compiler for each unit stays pinned by the compile invocation sha256.
    cxx_compiler_compiles_c: bool = False
    # Some Makefiles name objects after the whole source path rather than its
    # stem -- dosbox_pure emits `build/release/src~hardware~vga.cpp.o`, keeping
    # the suffix and mangling `/` to `~`. Setting this True drops only the
    # object==<stem>.o naming check; the exact per-compile object/source pairing
    # stays pinned by the compile pair and invocation sha256 (the source operand
    # must still be a lone contained C/C++ file). Mirrors the same-named c_only
    # relaxation.
    sha_pinned_object_names: bool = False
    # Paired with the above for dosbox_pure: `~` is a shell metacharacter, so
    # the shared line guard rejects any log line containing one. Opting in
    # admits it only in non-word-initial position (see
    # command_line_is_lexically_safe); every other core keeps the strict guard.
    allow_embedded_tilde: bool = False


def mixed_language_semantic_log_path(
    value: object,
    suffix: str,
    semantic_path_aliases: tuple[tuple[str, str], ...] = (),
) -> str | None:
    """Return a contained lexical path while retaining raw argv separately."""

    return semantic_log_path(value, suffix, semantic_path_aliases)


def mixed_language_compile_invocation(
    tokens: list[str],
    expected_compilers: set[str],
    expected_cxx_compilers: set[str],
    semantic_path_aliases: tuple[tuple[str, str], ...] = (),
    cxx_compiler_compiles_c: bool = False,
    sha_pinned_object_names: bool = False,
) -> tuple[str, str, str, str, str, tuple[str, ...]] | None:
    """Parse one mixed-language compile into semantic and raw identities."""

    if not tokens or tokens[0] not in expected_compilers:
        return None
    parsed_output = output_option(tokens)
    if (
        tokens.count("-c") != 1
        or parsed_output is None
        or command_uses_response_file(tokens)
        or "--" in tokens[1:]
        or any(token == "-x" or token.startswith("-x") for token in tokens[1:])
        # -Xlinker consumes a separate operand (keep rejected); an attached
        # -Wl,... token is inert under -c and pinned verbatim, so admit it.
        or any(
            token == "-Xlinker" or token.startswith("-Xlinker=")
            for token in tokens[1:]
        )
    ):
        return None
    raw_output, output_indexes = parsed_output
    output = mixed_language_semantic_log_path(
        raw_output, ".o", semantic_path_aliases
    )
    if output is None:
        return None
    # A flag that consumes a separate file operand (-I/-include/-isystem/
    # -iquote/-imacros/-idirafter) must not have that operand mistaken for a
    # second source. c_only and c_asm already do this; mixed_language did not,
    # which rejected any core using a forced include (e.g. chailove's
    # `-include retro_endianness.h`).
    option_operand_indexes: set[int] = set()
    for index, token in enumerate(tokens[1:], start=1):
        if token not in FILE_OPERAND_FLAGS:
            continue
        operand_index = index + 1
        if (
            operand_index >= len(tokens)
            or tokens[operand_index].startswith("-")
        ):
            return None
        option_operand_indexes.add(operand_index)
    source_indexes = [
        index
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes
        and index not in option_operand_indexes
        and token != "-c"
        and not token.startswith("-")
    ]
    if len(source_indexes) != 1:
        return None
    source_index = source_indexes[0]
    raw_source = tokens[source_index]
    suffix = next(
        (
            candidate
            for candidate in (".cxx", ".cpp", ".cc", ".c")
            if raw_source.endswith(candidate)
        ),
        None,
    )
    if suffix is None:
        return None
    source = mixed_language_semantic_log_path(
        raw_source, suffix, semantic_path_aliases
    )
    if source is None:
        return None
    if not sha_pinned_object_names and output != source.removesuffix(suffix) + ".o":
        return None
    language = "c" if suffix == ".c" else "cxx"
    compiler_is_cxx = tokens[0] in expected_cxx_compilers
    if language == "cxx" and not compiler_is_cxx:
        return None
    if language == "c" and compiler_is_cxx and not cxx_compiler_compiles_c:
        return None
    first_output_index = min(output_indexes)
    raw_tokens: list[str] = []
    for index, token in enumerate(tokens):
        if index == first_output_index:
            raw_tokens.extend(("-o", raw_output))
        elif index not in output_indexes:
            raw_tokens.append(token)
    return output, source, language, raw_output, raw_source, tuple(raw_tokens)


def mixed_language_link_command(
    tokens: list[str],
    expected_link_compilers: set[str],
    contract: MixedLanguageLogContract,
    *,
    include_raw_sha256: bool = False,
) -> tuple[Counter[str], str] | tuple[Counter[str], str, str] | None:
    if not tokens or tokens[0] not in expected_link_compilers or "-c" in tokens:
        return None
    parsed_output = output_option(tokens)
    if (
        parsed_output is None
        or command_uses_response_file(tokens)
        or "--" in tokens[1:]
        or any(token == "-x" or token.startswith("-x") for token in tokens[1:])
        or any(
            token == "-Xlinker" or token.startswith("-Xlinker=")
            for token in tokens[1:]
        )
    ):
        return None
    raw_output, output_indexes = parsed_output
    # semantic_log_path already guarantees a contained relative output; the
    # artifact-name equality is the only remaining check (admits a reviewed
    # link subdirectory only when the contract aliases it).
    output = mixed_language_semantic_log_path(
        raw_output, ".so", contract.semantic_path_aliases
    )
    if output != contract.build_artifact_name:
        return None
    observed_options = Counter(
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes and token.startswith("-")
    )
    if observed_options != Counter(contract.expected_link_options):
        return None
    raw_operands = [
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes and not token.startswith("-")
    ]
    objects: list[str] = []
    for operand in raw_operands:
        normalized = mixed_language_semantic_log_path(
            operand, ".o", contract.semantic_path_aliases
        )
        if normalized is None:
            return None
        objects.append(normalized)
    if not objects:
        return None
    result = (Counter(objects), mixed_language_link_object_sha256(objects))
    if include_raw_sha256:
        return (*result, mixed_language_raw_link_object_sha256(raw_operands))
    return result


def mixed_language_compile_pair_sha256(
    pairs: Iterable[tuple[str, str]],
) -> str:
    material = "".join(
        f"{output}|{source}\n" for output, source in sorted(pairs)
    )
    return sha256_bytes(material.encode("utf-8"))


def mixed_language_compile_invocation_sha256(
    invocations: Iterable[
        tuple[str, str, str, str, str, tuple[str, ...]]
    ],
) -> str:
    canonical = [
        [raw_output, raw_source, list(raw_tokens)]
        for (
            _output,
            _source,
            _language,
            raw_output,
            raw_source,
            raw_tokens,
        ) in invocations
    ]
    canonical.sort()
    return sha256_bytes(
        json.dumps(
            canonical,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def mixed_language_link_object_sha256(objects: Iterable[str]) -> str:
    material = "".join(f"{path}\n" for path in sorted(objects))
    return sha256_bytes(material.encode("utf-8"))


def mixed_language_raw_link_object_sha256(objects: Iterable[str]) -> str:
    material = "".join(f"{path}\n" for path in sorted(objects))
    return sha256_bytes(material.encode("utf-8"))


def mixed_language_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
    contract: MixedLanguageLogContract,
) -> bool:
    if core_id != contract.core_id:
        return False
    lowered_log = build_log_text.lower()
    if "fatal:" in lowered_log or "dubious ownership" in lowered_log:
        return False
    if (
        source_commit != contract.source_commit
        or source_tree != contract.source_tree
    ):
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    if contract.expected_link_language == "cxx":
        expected_link_compilers = expected_cxx_compilers
    elif contract.expected_link_language == "c":
        expected_link_compilers = expected_compilers - expected_cxx_compilers
    else:
        return False
    compile_pairs: Counter[tuple[str, str]] = Counter()
    compile_invocations: list[
        tuple[str, str, str, str, str, tuple[str, ...]]
    ] = []
    language_counts: Counter[str] = Counter()
    link_objects: Counter[str] | None = None
    link_object_sha256: str | None = None
    raw_link_object_sha256: str | None = None
    ordered_link_argv_sha256: str | None = None
    for line in build_log_text.splitlines():
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        if not command_line_is_lexically_safe(
            line, contract.allow_embedded_tilde
        ):
            return False
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        if not tokens:
            continue
        has_output = any(
            token == "-o" or token.startswith("-o") for token in tokens[1:]
        )
        if "-c" not in tokens and not has_output:
            if tokens[0] in expected_compilers:
                return False
            continue
        if (
            not COMPILER_COMMAND_RE.fullmatch(tokens[0])
            or tokens[0] not in expected_compilers
        ):
            return False
        if "-c" in tokens:
            invocation = mixed_language_compile_invocation(
                tokens,
                expected_compilers,
                expected_cxx_compilers,
                contract.semantic_path_aliases,
                contract.cxx_compiler_compiles_c,
                contract.sha_pinned_object_names,
            )
            if invocation is None:
                return False
            output, source, language, *_raw = invocation
            compile_pairs[(output, source)] += 1
            compile_invocations.append(invocation)
            language_counts[language] += 1
            continue
        if not has_output or link_objects is not None:
            return False
        link = mixed_language_link_command(
            tokens,
            expected_link_compilers,
            contract,
            include_raw_sha256=True,
        )
        if link is None:
            return False
        link_objects, link_object_sha256, raw_link_object_sha256 = link
        ordered_link_argv_sha256 = ordered_command_argv_sha256(tokens)
    compile_objects = Counter(
        {output: count for (output, _source), count in compile_pairs.items()}
    )
    compile_sources = Counter(
        {source: count for (_output, source), count in compile_pairs.items()}
    )
    return bool(
        len(compile_pairs) == contract.expected_compile_count
        and sum(compile_pairs.values()) == contract.expected_compile_count
        and all(count == 1 for count in compile_pairs.values())
        and len(compile_objects) == contract.expected_compile_count
        and len(compile_sources) == contract.expected_compile_count
        and all(count == 1 for count in compile_objects.values())
        and all(count == 1 for count in compile_sources.values())
        and dict(language_counts) == dict(contract.expected_language_counts)
        and mixed_language_compile_pair_sha256(compile_pairs)
        == contract.expected_compile_pair_sha256
        and mixed_language_compile_invocation_sha256(compile_invocations)
        == contract.expected_compile_invocation_sha256.get(arch)
        and link_objects == compile_objects
        and link_object_sha256 == contract.expected_link_object_sha256
        and raw_link_object_sha256 == contract.expected_raw_link_object_sha256
        and (
            contract.expected_ordered_link_argv_sha256 is None
            or ordered_link_argv_sha256
            == contract.expected_ordered_link_argv_sha256.get(arch)
        )
    )
