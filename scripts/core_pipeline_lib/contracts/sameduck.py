"""Exact SameDuck (libretro Game Boy) C-only build-log contract.

sameduck builds from the ``libretro`` subdirectory, so its objects and the
version-script live one directory up with a doubled separator (``..//Core/…``);
a single ``("..//","")`` alias contains them. Its Makefile names each object
``build/obj/<path>/<name>_libretro.c.o`` for source ``<path>/<name>.c`` — a
non-standard scheme the strict ``<stem>.o`` check rejects, so this contract sets
``sha_pinned_object_names`` (the exact per-compile object/source pairing stays
pinned by the compile pair and invocation sha256). 13 C translation units,
C-driver link; commit-derived ``-DGIT_VERSION`` is pinned by the per-arch
invocation sha256.
"""

from __future__ import annotations

import re

from .c_only import COnlyLogContract, c_only_log_proves_contract
from .log_checks import (
    lines_sha256 as _lines_sha256,
    multiset_lines_sha256 as _multiset_lines_sha256,
)


SAMEDUCK_CORE_ID = "sameduck"
SAMEDUCK_BUILD_ARTIFACT_NAME = "sameduck_libretro.so"

SAMEDUCK_SOURCE_COMMIT = "f0286ee9d6c44950d9a442463ffdb1ff014a5d5b"
SAMEDUCK_SOURCE_TREE = "c04c4f24a078b55386a1c62ae3619dde5b5087d9"

SAMEDUCK_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-sameduck.yml",
    "source_url": "https://github.com/libretro/sameduck.git",
    "source_requested_ref": "refs/heads/SameDuck-libretro",
    "source_commit": SAMEDUCK_SOURCE_COMMIT,
    "source_tree": SAMEDUCK_SOURCE_TREE,
    "source_key": SAMEDUCK_CORE_ID,
    "source_dir": "libretro-sameduck",
    "output_path": "dist/unix/sameduck_libretro.so",
    "artifact_name": SAMEDUCK_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/sameduck_libretro.info",
    "metadata_artifact_name": "sameduck_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the sameduck core must preserve its exact source, "
    "recipe, metadata, and target contract"
)


def sameduck_spec_is_well_formed(spec: object) -> bool:
    """Require SameDuck's exact immutable catalog identity."""

    identity = SAMEDUCK_SPEC_IDENTITY
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
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


SAMEDUCK_LOG_CONTRACT_ID = "sameduck-c-only-v1"
SAMEDUCK_EXPECTED_COMPILE_COUNT = 13
SAMEDUCK_EXPECTED_COMPILE_PAIR_SHA256 = (
    "5c75218776e6195328ea45512864d9b1d02ea511958598fe8386f14d70cf1b46"
)
SAMEDUCK_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "1120d4ce63e3daab8db31bcfdfa9dfc0012fe332f981ba95faaffb1421ec0a51",
    "armhf": "4864300eb23d012b1d116b821942e161196745adba655be16478fae7a7025309",
}
SAMEDUCK_EXPECTED_LINK_OBJECT_SHA256 = (
    "763269a024bcbcc2af66caf586852b7eba9f80207cd9034ad9f7f9fc54272198"
)
SAMEDUCK_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "3468bd325cdcd0ba901d509489d42d2a71b203cb257f1a6ebbb148802628e7c6"
)
SAMEDUCK_SEMANTIC_PATH_ALIASES = (("..//", ""),)
SAMEDUCK_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=..//libretro/link.T",
    "-Wl,--no-undefined",
    "-I../",
    "-lm",
)

# The reviewed parallel builds contain three independent compiler diagnostic
# streams (gb.c, apu.c, and sm83_cpu.c). GCC emits each warning as an atomic
# three-line event (headline, source excerpt, caret), but -j scheduling can
# interleave complete events from different streams. The hashes below bind the
# exact event contents and preserve order within each compiler stream while
# allowing only that observed cross-stream interleaving.
SAMEDUCK_EXPECTED_WARNING_COUNT = {"arm64": 11, "armhf": 8}
SAMEDUCK_EXPECTED_DIAGNOSTIC_LINE_COUNT = {"arm64": 40, "armhf": 28}
SAMEDUCK_EXPECTED_WARNING_LINES_SHA256 = {
    "arm64": "75d9292dcebbdc64bbfc5aac0c6e5fad2ef7bed0ef4b9d6e66b7bf59e10691a0",
    "armhf": "c47612c623bf1ee5405d7dc9f99778a34ad6e85e74cca0055c1f8ba6a4f38467",
}
SAMEDUCK_EXPECTED_DIAGNOSTIC_LINES_SHA256 = {
    "arm64": "48eaa326932f9459293053588d5ce44879c57654e4d12f265a6eaf0a561dfb43",
    "armhf": "25af5cbd60f6adc47507cb62f9f9ed6c59f0d75178f68fce42612e258c67e4b0",
}
SAMEDUCK_EXPECTED_DIAGNOSTIC_EVENT_STREAMS_SHA256 = {
    "arm64": (
        (
            "c37d2eac10fbf9bb8a03b1f213028bda4f374bab5d4837147b3053883b42c032",
            "5f616007362f25ded6ea4ea3b57feb207917fbea96365818cfa6c125e2f216c5",
            "376472ebac53d14b83279e2697f2279b74fe53469266bc44b15bcc26b19c407d",
            "88e3372a964bd71d908d5072eecea1e7e8d28a544d1bd4a2cbdfc8a583ced4f4",
            "dbf02d4dc2ad71efa2dc662788605b4e58375b47d813deb3d06231d103e27f4f",
            "8e479a8960a3fc34a1a91da7ca139fd9a7cb87c1303b297f92e43712b2e3bb42",
            "4e83824b29f4f1fe695be77ac3e57718e0dfc14a7182800bc7b672ff971d623d",
            "6725b42c1ddce89f637612e4acd2f78989fa20cc1f7e665a7fa3368aa3aa0fcf",
            "3cfceced5da6e918ee1bf48255f8ccff7bd80d88aefd29d35699544c7b752022",
            "88e3372a964bd71d908d5072eecea1e7e8d28a544d1bd4a2cbdfc8a583ced4f4",
            "9ceb08352afad6e61dd5d493fdfae61f5b26691e4baa7cba43fa5499b84961af",
        ),
        (
            "aa85f28c72df5b4b791045d01e37c5229c58ef9d34c969967b74a290daf1d54a",
            "43d200d40a0b3f660381431c882ace9d54cae14f52cae18d4371eafcba561a29",
            "a94c95cdd7675342d66b2898ffc6ad61fd8a06e8383c6120cf13e6671d9eeb33",
            "59b0b650afe126c60f540deeeeb980ad319614365d26197d93349e32ce3d683f",
            "752376fb3797fd3f8c85643dc11fb5e0eeaf974822065345a2b4aee6e8faf099",
        ),
        (
            "ca2750cf9ea2cf9231cc8da8314da74492ff002b06e58a03d01e5e3ddbdfd4e4",
            "b8a42fc2fb76fc5631f7b893a8a5b17b9e3dec806bc386387c7490dfb6d866e7",
        ),
    ),
    "armhf": (
        (
            "c37d2eac10fbf9bb8a03b1f213028bda4f374bab5d4837147b3053883b42c032",
            "5f616007362f25ded6ea4ea3b57feb207917fbea96365818cfa6c125e2f216c5",
            "376472ebac53d14b83279e2697f2279b74fe53469266bc44b15bcc26b19c407d",
            "88e3372a964bd71d908d5072eecea1e7e8d28a544d1bd4a2cbdfc8a583ced4f4",
            "dbf02d4dc2ad71efa2dc662788605b4e58375b47d813deb3d06231d103e27f4f",
        ),
        (
            "aa85f28c72df5b4b791045d01e37c5229c58ef9d34c969967b74a290daf1d54a",
            "43d200d40a0b3f660381431c882ace9d54cae14f52cae18d4371eafcba561a29",
            "a94c95cdd7675342d66b2898ffc6ad61fd8a06e8383c6120cf13e6671d9eeb33",
            "59b0b650afe126c60f540deeeeb980ad319614365d26197d93349e32ce3d683f",
            "752376fb3797fd3f8c85643dc11fb5e0eeaf974822065345a2b4aee6e8faf099",
        ),
        (
            "ca2750cf9ea2cf9231cc8da8314da74492ff002b06e58a03d01e5e3ddbdfd4e4",
            "5b4168961f2752dab43d348cbba350f4888f8d38afea72c9ba8a72963e7b508d",
        ),
    ),
}
SAMEDUCK_C_COMPILER = {
    "arm64": "aarch64-linux-gnu-gcc",
    "armhf": "arm-a30-linux-gnueabihf-gcc",
}
SAMEDUCK_FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "aborted",
    "broken pipe",
    "bus error",
    "cannot find",
    "collect2:",
    "command not found",
    "core dumped",
    "dubious ownership",
    "error:",
    "fatal:",
    "file format not recognized",
    "floating point exception",
    "illegal instruction",
    "internal compiler error",
    "killed",
    "no such file or directory",
    "note:",
    "permission denied",
    "segmentation fault",
    "terminated",
    "undefined reference",
)
SAMEDUCK_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
SAMEDUCK_DIAGNOSTIC_HEADING_RE = re.compile(
    r"^\.\.//Core/[^:]+: In function '[^']+':$"
)
SAMEDUCK_WARNING_RE = re.compile(
    r"^\.\.//Core/[^:]+:\d+:\d+: warning:"
)
SAMEDUCK_DIAGNOSTIC_CONTEXT_RE = re.compile(r"^\s+(?:\d+ )?\|")

SAMEDUCK_LOG_CONTRACT = COnlyLogContract(
    core_id=SAMEDUCK_CORE_ID,
    expected_compile_count=SAMEDUCK_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=SAMEDUCK_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        SAMEDUCK_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=SAMEDUCK_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=SAMEDUCK_BUILD_ARTIFACT_NAME,
    expected_link_options=SAMEDUCK_EXPECTED_LINK_OPTIONS,
    source_commit=SAMEDUCK_SOURCE_COMMIT,
    source_tree=SAMEDUCK_SOURCE_TREE,
    expected_raw_link_object_sha256=SAMEDUCK_EXPECTED_RAW_LINK_OBJECT_SHA256,
    semantic_path_aliases=SAMEDUCK_SEMANTIC_PATH_ALIASES,
    sha_pinned_object_names=True,
)


def _diagnostic_events(
    lines: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[int, ...]] | None:
    """Parse atomic GCC headings/warnings and reject unreviewed diagnostics."""

    event_hashes: list[str] = []
    diagnostic_lines: list[str] = []
    diagnostic_positions: list[int] = []
    position = 0
    while position < len(lines):
        line = lines[position]
        if SAMEDUCK_DIAGNOSTIC_HEADING_RE.fullmatch(line) is not None:
            event = (line,)
        elif SAMEDUCK_WARNING_RE.match(line) is not None:
            if (
                position + 2 >= len(lines)
                or SAMEDUCK_DIAGNOSTIC_CONTEXT_RE.match(lines[position + 1])
                is None
                or SAMEDUCK_DIAGNOSTIC_CONTEXT_RE.match(lines[position + 2])
                is None
            ):
                return None
            event = tuple(lines[position : position + 3])
        else:
            lowered = line.casefold()
            if (
                line.startswith("..//Core/")
                or SAMEDUCK_DIAGNOSTIC_CONTEXT_RE.match(line) is not None
                or any(
                    marker in lowered
                    for marker in ("warning:", "note:", "error:", "fatal:")
                )
            ):
                return None
            position += 1
            continue
        event_hashes.append(_lines_sha256(event))
        diagnostic_lines.extend(event)
        diagnostic_positions.extend(range(position, position + len(event)))
        position += len(event)
    return (
        tuple(event_hashes),
        tuple(diagnostic_lines),
        tuple(diagnostic_positions),
    )


def _diagnostic_event_streams_are_exact(
    observed: tuple[str, ...],
    expected_streams: tuple[tuple[str, ...], ...],
) -> bool:
    """Accept any interleaving that preserves each compiler stream's order."""

    states = {tuple(0 for _stream in expected_streams)}
    for event_hash in observed:
        next_states: set[tuple[int, ...]] = set()
        for state in states:
            for stream_index, stream in enumerate(expected_streams):
                stream_position = state[stream_index]
                if (
                    stream_position >= len(stream)
                    or stream[stream_position] != event_hash
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
            stream_position == len(expected_streams[stream_index])
            for stream_index, stream_position in enumerate(state)
        )
        for state in states
    )


def _diagnostic_contract_is_exact(build_log_text: str, arch: str) -> bool:
    """Bind SameDuck's reviewed warnings and their compile/link position."""

    expected_streams = SAMEDUCK_EXPECTED_DIAGNOSTIC_EVENT_STREAMS_SHA256.get(
        arch
    )
    compiler = SAMEDUCK_C_COMPILER.get(arch)
    if expected_streams is None or compiler is None:
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in SAMEDUCK_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or SAMEDUCK_MAKE_FAILURE_RE.search(build_log_text) is not None
    ):
        return False
    lines = build_log_text.splitlines()
    parsed = _diagnostic_events(lines)
    if parsed is None:
        return False
    event_hashes, diagnostic_lines, diagnostic_positions = parsed
    warning_lines = tuple(
        line for line in diagnostic_lines if "warning:" in line.casefold()
    )
    compile_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line.startswith(f"{compiler} ") and " -c " in f" {line} "
    )
    link_positions = tuple(
        position
        for position, line in enumerate(lines)
        if line.startswith(f"{compiler} ")
        and f" -o {SAMEDUCK_BUILD_ARTIFACT_NAME} " in f" {line} "
        and " -c " not in f" {line} "
    )
    return bool(
        len(diagnostic_lines)
        == SAMEDUCK_EXPECTED_DIAGNOSTIC_LINE_COUNT.get(arch)
        and len(warning_lines) == SAMEDUCK_EXPECTED_WARNING_COUNT.get(arch)
        and _multiset_lines_sha256(warning_lines)
        == SAMEDUCK_EXPECTED_WARNING_LINES_SHA256.get(arch)
        and _multiset_lines_sha256(diagnostic_lines)
        == SAMEDUCK_EXPECTED_DIAGNOSTIC_LINES_SHA256.get(arch)
        and _diagnostic_event_streams_are_exact(event_hashes, expected_streams)
        and len(compile_positions) == SAMEDUCK_EXPECTED_COMPILE_COUNT
        and len(link_positions) == 1
        and diagnostic_positions
        and tuple(sorted((*compile_positions, *diagnostic_positions)))
        == tuple(
            range(min(compile_positions), link_positions[0])
        )
    )


def sameduck_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove SameDuck's exact C build, link, and reviewed diagnostics."""

    return bool(
        c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            SAMEDUCK_LOG_CONTRACT,
        )
        and _diagnostic_contract_is_exact(build_log_text, arch)
    )


__all__ = [
    "SAMEDUCK_BUILD_ARTIFACT_NAME",
    "SAMEDUCK_CORE_ID",
    "SAMEDUCK_EXPECTED_DIAGNOSTIC_LINE_COUNT",
    "SAMEDUCK_EXPECTED_DIAGNOSTIC_LINES_SHA256",
    "SAMEDUCK_EXPECTED_WARNING_COUNT",
    "SAMEDUCK_EXPECTED_WARNING_LINES_SHA256",
    "SAMEDUCK_LOG_CONTRACT_ID",
    "SAMEDUCK_SOURCE_COMMIT",
    "SAMEDUCK_SOURCE_TREE",
    "SAMEDUCK_SPEC_IDENTITY",
    "sameduck_log_proves_contract",
    "sameduck_spec_is_well_formed",
]
