"""Neutral exact C-only compile and link-log proof machinery."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import re
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
class COnlyLogContract:
    """Exact per-core parameters consumed by the neutral proof engine."""

    core_id: str
    expected_compile_count: int
    expected_compile_pair_sha256: str
    expected_compile_invocation_sha256: Mapping[str, str]
    expected_link_object_sha256: str
    build_artifact_name: str
    expected_link_options: tuple[str, ...]
    source_commit: str
    source_tree: str
    expected_raw_link_object_sha256: str | None = None
    expected_link_invocation_sha256: Mapping[str, str] | None = None
    semantic_path_aliases: tuple[tuple[str, str], ...] = ()
    expected_raw_compile_invocation_sha256: Mapping[str, str] | None = None
    # Archive-membership mode (opt-in): when a core links a static archive built
    # in-tree with `ar` (e.g. lutro bundles its Lua objects into liblua.a), the
    # link no longer names every compiled object. Setting the member sha256
    # switches the object-identity check to
    #   link_direct_objects ∪ archive_members == compile_objects
    # and additionally pins the exact archived member set and archive names.
    expected_archive_member_sha256: str | None = None
    expected_archive_names: tuple[str, ...] = ()
    # Non-standard object naming (opt-in): the strict engine requires each
    # object to be named `<source-stem>.o`. Modern libretro Makefiles instead
    # name objects after the full source (`foo.c.o`), insert an infix
    # (`foo_libretro.c.o`, sameduck), or mangle separators (`dir~foo.cpp.o`).
    # Setting this True drops only the object==<stem>.o naming check; the exact
    # per-compile object/source pairing stays pinned by the compile pair and
    # invocation sha256 (the source operand must still be a lone contained `.c`).
    sha_pinned_object_names: bool = False


def c_only_compile_invocation(
    tokens: list[str],
    expected_c_compilers: set[str],
    semantic_path_aliases: tuple[tuple[str, str], ...] = (),
    sha_pinned_object_names: bool = False,
) -> tuple[str, str, tuple[str, ...]] | None:
    """Parse and normalize one strict C compile invocation."""

    if not tokens or tokens[0] not in expected_c_compilers:
        return None
    parsed_output = output_option(tokens)
    if (
        tokens.count("-c") != 1
        or parsed_output is None
        or command_uses_response_file(tokens)
        or "--" in tokens[1:]
        or any(token == "-x" or token.startswith("-x") for token in tokens[1:])
        # -Xlinker consumes a separate operand (could be mistaken for a source),
        # so it stays rejected; an attached -Wl,... token is a single argument
        # that gcc ignores under -c (no link step), so it is admitted and pinned
        # verbatim by the invocation sha256 (e.g. -Wl,--gc-sections in CFLAGS).
        or any(
            token == "-Xlinker" or token.startswith("-Xlinker=")
            for token in tokens[1:]
        )
    ):
        return None
    raw_output, output_indexes = parsed_output
    output = semantic_log_path(
        raw_output, ".o", semantic_path_aliases
    )
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
    source = semantic_log_path(
        tokens[source_index], ".c", semantic_path_aliases
    )
    if source is None:
        return None
    if not sha_pinned_object_names and source != output.removesuffix(".o") + ".c":
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


def c_only_link_command(
    tokens: list[str],
    expected_c_compilers: set[str],
    contract: COnlyLogContract,
    *,
    include_raw_sha256: bool = False,
) -> (
    tuple[Counter[str], str, tuple[str, ...]]
    | tuple[Counter[str], str, tuple[str, ...], str]
    | None
):
    """Parse one exact C-compiler link command and its object identity.

    Returns ``(objects, link_object_sha256, archive_names)`` and, when
    ``include_raw_sha256`` is set, a trailing raw object-operand sha256.
    ``archive_names`` is empty unless the contract enables archive-membership
    mode, in which case linked ``.a`` operands are collected by basename.
    """

    if not tokens or tokens[0] not in expected_c_compilers or "-c" in tokens:
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
    # semantic_log_path already guarantees the (alias-mapped) output is a
    # contained relative path; requiring it to equal the artifact name is the
    # only remaining check. This admits a reviewed link subdirectory
    # (obj/<platform>/<artifact>.so) exactly when the contract aliases it, while
    # any un-aliased subdir/absolute output still maps to a non-artifact name.
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
    if observed_options != Counter(contract.expected_link_options):
        return None
    raw_operands = [
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index not in output_indexes and not token.startswith("-")
    ]
    archive_mode = contract.expected_archive_member_sha256 is not None
    objects: list[str] = []
    object_operands: list[str] = []
    archives: list[str] = []
    for operand in raw_operands:
        if archive_mode and operand.endswith(".a"):
            archives.append(operand.rsplit("/", 1)[-1])
            continue
        normalized = semantic_log_path(
            operand, ".o", contract.semantic_path_aliases
        )
        if normalized is None:
            return None
        objects.append(normalized)
        object_operands.append(operand)
    if not objects:
        return None
    result = (
        Counter(objects),
        c_only_link_object_sha256(objects),
        tuple(sorted(archives)),
    )
    if include_raw_sha256:
        return (*result, c_only_raw_link_object_sha256(object_operands))
    return result


def c_only_compile_pair_sha256(
    pairs: Iterable[tuple[str, str]],
) -> str:
    material = "".join(
        f"{output}|{source}\n" for output, source in sorted(pairs)
    )
    return sha256_bytes(material.encode("utf-8"))


def c_only_compile_invocation_sha256(
    invocations: Iterable[tuple[str, str, tuple[str, ...]]],
) -> str:
    canonical = [
        [output, source, list(tokens)]
        for output, source, tokens in sorted(invocations)
    ]
    return sha256_bytes(
        json.dumps(
            canonical,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def c_only_raw_compile_invocation_sha256(
    invocations: Iterable[tuple[str, ...]],
) -> str:
    """Hash exact compile argv while allowing parallel command reordering."""

    canonical = sorted([list(tokens) for tokens in invocations])
    return sha256_bytes(
        json.dumps(
            canonical,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def c_only_link_object_sha256(objects: Iterable[str]) -> str:
    material = "".join(f"{path}\n" for path in sorted(objects))
    return sha256_bytes(material.encode("utf-8"))


def c_only_raw_link_object_sha256(objects: Iterable[str]) -> str:
    """Hash raw link operands before semantic path normalization."""

    material = "".join(f"{path}\n" for path in sorted(objects))
    return sha256_bytes(material.encode("utf-8"))


_AR_FLAG_RE = re.compile(r"[a-zA-Z]+")


def c_only_archive_command(
    line: str,
    semantic_path_aliases: tuple[tuple[str, str], ...] = (),
) -> list[str] | None:
    """Parse one strict ``ar`` archive command into its member object set.

    Recognizes ``ar <flags> <archive>.a <member>.o ...`` (the create/replace
    form; a trailing ``# comment`` is dropped). Every operand after the archive
    must be a ``.o`` member that maps to a contained relative path; anything else
    fails closed. Returns ``None`` for a line that is not a well-formed archive
    creation so the caller can ignore it.
    """

    stripped = line.strip()
    if not stripped.startswith("ar "):
        return None
    # Drop a trailing `# comment` (Makefiles annotate the Lua archive rule) and
    # any whitespace it leaves behind before the control-character safety gate.
    command = stripped.split("#", 1)[0].strip()
    if not command_line_is_lexically_safe(command):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if (
        len(tokens) < 4
        or tokens[0] != "ar"
        or _AR_FLAG_RE.fullmatch(tokens[1]) is None
        or "r" not in tokens[1]
        or not tokens[2].endswith(".a")
    ):
        return None
    members: list[str] = []
    for operand in tokens[3:]:
        if not operand.endswith(".o"):
            return None
        normalized = semantic_log_path(operand, ".o", semantic_path_aliases)
        if normalized is None:
            return None
        members.append(normalized)
    if not members:
        return None
    return members


def c_only_archive_member_sha256(members: Iterable[str]) -> str:
    """Hash the archived member object set (order-independent)."""

    material = "".join(f"{path}\n" for path in sorted(members))
    return sha256_bytes(material.encode("utf-8"))


def c_only_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
    contract: COnlyLogContract,
) -> bool:
    """Prove an exact, duplicate-free C compile set and matching link."""

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
    expected_c_compilers = expected_compilers - expected_cxx_compilers
    archive_mode = contract.expected_archive_member_sha256 is not None
    compile_pairs: Counter[tuple[str, str]] = Counter()
    compile_invocations: list[tuple[str, str, tuple[str, ...]]] = []
    raw_compile_invocations: list[tuple[str, ...]] = []
    link_objects: Counter[str] | None = None
    link_object_sha256: str | None = None
    raw_link_object_sha256: str | None = None
    link_invocation_sha256: str | None = None
    link_archives: tuple[str, ...] = ()
    archive_members: Counter[str] = Counter()
    for line in build_log_text.splitlines():
        if archive_mode and line.strip().startswith("ar "):
            members = c_only_archive_command(
                line, contract.semantic_path_aliases
            )
            if members is not None:
                archive_members.update(members)
                continue
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        if not command_line_is_lexically_safe(line):
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
            or tokens[0] not in expected_c_compilers
        ):
            return False
        if "-c" in tokens:
            invocation = c_only_compile_invocation(
                tokens,
                expected_c_compilers,
                contract.semantic_path_aliases,
                contract.sha_pinned_object_names,
            )
            if invocation is None:
                return False
            output, source, _tokens = invocation
            compile_pairs[(output, source)] += 1
            compile_invocations.append(invocation)
            raw_compile_invocations.append(tuple(tokens))
            continue
        if not has_output or link_objects is not None:
            return False
        link = c_only_link_command(
            tokens,
            expected_c_compilers,
            contract,
            include_raw_sha256=True,
        )
        if link is None:
            return False
        (
            link_objects,
            link_object_sha256,
            link_archives,
            raw_link_object_sha256,
        ) = link
        link_invocation_sha256 = ordered_command_argv_sha256(tokens)

    compile_objects: Counter[str] = Counter()
    compile_sources: Counter[str] = Counter()
    for (output, source), count in compile_pairs.items():
        compile_objects[output] += count
        compile_sources[source] += count
    return bool(
        len(compile_pairs) == contract.expected_compile_count
        and sum(compile_pairs.values()) == contract.expected_compile_count
        and all(count == 1 for count in compile_pairs.values())
        and len(compile_objects) == contract.expected_compile_count
        and len(compile_sources) == contract.expected_compile_count
        and all(count == 1 for count in compile_objects.values())
        and all(count == 1 for count in compile_sources.values())
        and c_only_compile_pair_sha256(compile_pairs)
        == contract.expected_compile_pair_sha256
        and c_only_compile_invocation_sha256(compile_invocations)
        == contract.expected_compile_invocation_sha256.get(arch)
        and (
            contract.expected_raw_compile_invocation_sha256 is None
            or c_only_raw_compile_invocation_sha256(raw_compile_invocations)
            == contract.expected_raw_compile_invocation_sha256.get(arch)
        )
        and (
            (link_objects + archive_members) == compile_objects
            if archive_mode
            else link_objects == compile_objects
        )
        and (
            not archive_mode
            or (
                c_only_archive_member_sha256(archive_members.elements())
                == contract.expected_archive_member_sha256
                and link_archives == contract.expected_archive_names
            )
        )
        and link_object_sha256 == contract.expected_link_object_sha256
        and (
            contract.expected_raw_link_object_sha256 is None
            or raw_link_object_sha256
            == contract.expected_raw_link_object_sha256
        )
        and (
            contract.expected_link_invocation_sha256 is None
            or link_invocation_sha256
            == contract.expected_link_invocation_sha256.get(arch)
        )
    )
