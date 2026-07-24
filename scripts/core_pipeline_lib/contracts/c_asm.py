"""Neutral exact C/C++/assembly compile and link-log proof machinery.

Generalizes the C-only proof to cores that compile hand-written assembly
(``.s``/``.S``) - and optionally C++ (``.cc``/``.cpp``/...) - alongside C. Such
cores routinely select a different dynarec or GPU backend per ABI, so the object
set, the compile invocations, the link objects, and even the C compile count
differ per architecture. Every expectation is therefore captured per
architecture. The sha256 helpers are shared verbatim with the C-only engine, so
an assembly, C, or C++ object hashes identically once normalized; the only new
behavior is accepting assembly and C++ sources and proving the per-architecture
C, C++, and assembly counts against the declared link language.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import shlex

from ..errors import PipelineError
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
from .c_only import (
    c_only_compile_invocation_sha256,
    c_only_compile_pair_sha256,
    c_only_link_object_sha256,
    c_only_raw_compile_invocation_sha256,
    c_only_raw_link_object_sha256,
)


# Assembly and C sources compile through the C driver; C++ sources compile
# through the C++ driver. Suffixes are matched case-sensitively, as emitted.
C_ASM_SOURCE_SUFFIXES = (".c", ".s", ".S")
CXX_SOURCE_SUFFIXES = (".cpp", ".cc", ".cxx", ".c++", ".C")


@dataclass(frozen=True, slots=True)
class CAsmLogContract:
    """Exact per-architecture C/C++/assembly compile and link parameters."""

    core_id: str
    expected_c_compile_count: Mapping[str, int]
    expected_asm_compile_count: Mapping[str, int]
    expected_compile_pair_sha256: Mapping[str, str]
    expected_compile_invocation_sha256: Mapping[str, str]
    expected_link_object_sha256: Mapping[str, str]
    build_artifact_name: str
    expected_link_options: Mapping[str, tuple[str, ...]]
    source_commit: str
    source_tree: str
    expected_cxx_compile_count: Mapping[str, int] | None = None
    expected_link_language: str = "c"
    expected_raw_link_object_sha256: Mapping[str, str] | None = None
    expected_raw_compile_invocation_sha256: Mapping[str, str] | None = None
    expected_link_invocation_sha256: Mapping[str, str] | None = None
    semantic_path_aliases: tuple[tuple[str, str], ...] = ()
    # Opt-in: accept objects named `<source>.o` (osdcore.c -> osdcore.c.o),
    # the yabause/yabasanshiro convention. The exact per-compile pairing
    # stays pinned by the pair and invocation sha256s, so nothing is lost
    # by admitting the alternate name (the sameduck lesson, c_asm edition).
    source_suffixed_object_names: bool = False


def c_asm_compile_invocation(
    tokens: list[str],
    expected_c_compilers: set[str],
    semantic_path_aliases: tuple[tuple[str, str], ...] = (),
    expected_cxx_compilers: frozenset[str] = frozenset(),
    source_suffixed_object_names: bool = False,
) -> tuple[str, str, tuple[str, ...]] | None:
    """Parse and normalize one C, C++, or assembly compile invocation."""

    if not tokens:
        return None
    if tokens[0] in expected_cxx_compilers:
        allowed_suffixes: tuple[str, ...] = CXX_SOURCE_SUFFIXES
    elif tokens[0] in expected_c_compilers:
        allowed_suffixes = C_ASM_SOURCE_SUFFIXES
    else:
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
    output = semantic_log_path(raw_output, ".o", semantic_path_aliases)
    if output is None:
        return None
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
    stem = output[: -len(".o")]
    source: str | None = None
    for suffix in allowed_suffixes:
        candidate = semantic_log_path(
            tokens[source_index], suffix, semantic_path_aliases
        )
        if candidate is not None and (
            candidate[: -len(suffix)] == stem
            or (source_suffixed_object_names and candidate == stem)
        ):
            source = candidate
            break
    if source is None:
        return None
    first_output_index = min(output_indexes)
    canonical_tokens: list[str] = []
    for index, token in enumerate(tokens):
        if index == first_output_index:
            canonical_tokens.extend(("-o", output))
        elif index in output_indexes:
            continue
        elif index == source_index:
            canonical_tokens.append(source)
        else:
            canonical_tokens.append(token)
    return output, source, tuple(canonical_tokens)


def c_asm_link_command(
    tokens: list[str],
    expected_link_compilers: set[str],
    contract: CAsmLogContract,
    expected_options: tuple[str, ...],
    *,
    include_raw_sha256: bool = False,
) -> tuple[Counter[str], str] | tuple[Counter[str], str, str] | None:
    """Parse one exact link command (C or C++ driver) against per-arch options."""

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
    output = semantic_log_path(
        raw_output, ".so", contract.semantic_path_aliases
    )
    if output != contract.build_artifact_name:
        return None
    observed_options = Counter(
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes and token.startswith("-")
    )
    if observed_options != Counter(expected_options):
        return None
    raw_operands = [
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes and not token.startswith("-")
    ]
    objects: list[str] = []
    for operand in raw_operands:
        normalized = semantic_log_path(
            operand, ".o", contract.semantic_path_aliases
        )
        if normalized is None:
            return None
        objects.append(normalized)
    if not objects:
        return None
    result = (Counter(objects), c_only_link_object_sha256(objects))
    if include_raw_sha256:
        return (*result, c_only_raw_link_object_sha256(raw_operands))
    return result


def c_asm_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
    contract: CAsmLogContract,
) -> bool:
    """Prove an exact, duplicate-free C/C++/assembly compile set and link."""

    if core_id != contract.core_id or not isinstance(build_log_text, str):
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
    expected_c_count = contract.expected_c_compile_count.get(arch)
    expected_asm_count = contract.expected_asm_compile_count.get(arch)
    expected_options = contract.expected_link_options.get(arch)
    cxx_count_map = contract.expected_cxx_compile_count or {}
    expected_cxx_count = cxx_count_map.get(arch, 0)
    if (
        expected_c_count is None
        or expected_asm_count is None
        or expected_options is None
    ):
        return False
    expected_c_compilers = expected_compilers - expected_cxx_compilers
    uses_cxx = contract.expected_cxx_compile_count is not None
    compile_cxx_compilers = expected_cxx_compilers if uses_cxx else frozenset()
    link_compilers = (
        expected_cxx_compilers
        if contract.expected_link_language == "cxx"
        else expected_c_compilers
    )
    compile_pairs: Counter[tuple[str, str]] = Counter()
    compile_invocations: list[tuple[str, str, tuple[str, ...]]] = []
    raw_compile_invocations: list[tuple[str, ...]] = []
    c_compile_count = 0
    cxx_compile_count = 0
    asm_compile_count = 0
    link_objects: Counter[str] | None = None
    link_object_sha256: str | None = None
    raw_link_object_sha256: str | None = None
    link_invocation_sha256: str | None = None
    for line in build_log_text.splitlines():
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        if not command_line_is_lexically_safe(line):
            # A line that mentions a compiler only inside prose (for example a
            # make "CC: <compiler> : <version banner>" info line, whose version
            # string legitimately carries parentheses) is not a build command.
            # Fail closed only when the line actually begins with a target
            # compiler token; otherwise skip it. Any real compile that slips
            # past here still produces a linked object, which the
            # link_objects == compile_objects invariant below would catch.
            leading = line.split(maxsplit=1)
            if leading and leading[0] in expected_compilers:
                return False
            continue
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
            invocation = c_asm_compile_invocation(
                tokens,
                expected_c_compilers,
                contract.semantic_path_aliases,
                expected_cxx_compilers=compile_cxx_compilers,
                source_suffixed_object_names=(
                    contract.source_suffixed_object_names
                ),
            )
            if invocation is None:
                return False
            output, source, _tokens = invocation
            compile_pairs[(output, source)] += 1
            compile_invocations.append(invocation)
            raw_compile_invocations.append(tuple(tokens))
            if tokens[0] in compile_cxx_compilers:
                cxx_compile_count += 1
            elif source.endswith(".c"):
                c_compile_count += 1
            else:
                asm_compile_count += 1
            continue
        if not has_output or link_objects is not None:
            return False
        link = c_asm_link_command(
            tokens,
            link_compilers,
            contract,
            expected_options,
            include_raw_sha256=True,
        )
        if link is None:
            return False
        link_objects, link_object_sha256, raw_link_object_sha256 = link
        link_invocation_sha256 = ordered_command_argv_sha256(tokens)

    total_expected = expected_c_count + expected_cxx_count + expected_asm_count
    compile_objects: Counter[str] = Counter()
    compile_sources: Counter[str] = Counter()
    for (output, source), count in compile_pairs.items():
        compile_objects[output] += count
        compile_sources[source] += count
    return bool(
        c_compile_count == expected_c_count
        and cxx_compile_count == expected_cxx_count
        and asm_compile_count == expected_asm_count
        and len(compile_pairs) == total_expected
        and sum(compile_pairs.values()) == total_expected
        and all(count == 1 for count in compile_pairs.values())
        and len(compile_objects) == total_expected
        and len(compile_sources) == total_expected
        and all(count == 1 for count in compile_objects.values())
        and all(count == 1 for count in compile_sources.values())
        and c_only_compile_pair_sha256(compile_pairs)
        == contract.expected_compile_pair_sha256.get(arch)
        and c_only_compile_invocation_sha256(compile_invocations)
        == contract.expected_compile_invocation_sha256.get(arch)
        and (
            contract.expected_raw_compile_invocation_sha256 is None
            or c_only_raw_compile_invocation_sha256(raw_compile_invocations)
            == contract.expected_raw_compile_invocation_sha256.get(arch)
        )
        and link_objects == compile_objects
        and link_object_sha256 == contract.expected_link_object_sha256.get(arch)
        and (
            contract.expected_raw_link_object_sha256 is None
            or raw_link_object_sha256
            == contract.expected_raw_link_object_sha256.get(arch)
        )
        and (
            contract.expected_link_invocation_sha256 is None
            or link_invocation_sha256
            == contract.expected_link_invocation_sha256.get(arch)
        )
    )


__all__ = [
    "C_ASM_SOURCE_SUFFIXES",
    "CXX_SOURCE_SUFFIXES",
    "CAsmLogContract",
    "c_asm_compile_invocation",
    "c_asm_link_command",
    "c_asm_log_proves_contract",
]
