"""Exact individual C-only compile/link contract for Caprice32."""

from __future__ import annotations

from .c_only import COnlyLogContract, c_only_log_proves_contract
from .cpc_common import (
    CpcLogContract,
    CpcMakeTraceContract,
    cpc_allowed_linker_forwarding,
    cpc_log_proves_contract,
)


CAP32_CORE_ID = "cap32"
CAP32_NATIVE_GIT_VERSION = " 4abfb8b"
CAP32_NATIVE_GIT_VERSION_MARKER = (
    f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{CAP32_NATIVE_GIT_VERSION}"|file'
)
CAP32_MAKE_TRACE_MARKER = "CORE_PIPELINE_MAKE_TRACE|MAKEFLAGS=--trace|scoped"
CAP32_EXPECTED_C_COMPILE_COUNT = 44
CAP32_BUILD_ARTIFACT_NAME = "cap32_libretro.so"
CAP32_EXPECTED_COMPILE_PAIR_SHA256 = (
    "744d3d92d8a84a7cbe1fb618e0248cbd3b0dd4b351f0a575a90e840b6268c666"
)
CAP32_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "2043e765cb6584fb3bdf3ad458803f807ef2a1f6e121f0f9b915cd384c467a64",
    "armhf": "f841a2006c73d827c025dad9bfe7bb28cebfaa8f1b6f45ce718dba7bf38b5ba9",
}
CAP32_EXPECTED_LINK_OBJECT_SHA256 = (
    "68456106c45c3d6905174b2c6d982168653b4223124fe741617e7dcf1ad2dbd0"
)
CAP32_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "dc3596bf09dc4095a11e580354a3f52aad2e46ab6c7fb78adacb97df9364d4d7"
)
CAP32_EXPECTED_LINK_INVOCATION_SHA256 = {
    "arm64": "40e4b01f1f70ce96be1e0e51c77ddaf10cfb139251c3e78db5ee53620f5ad3a9",
    "armhf": "0b054c5f1fd71fd7560102e33e0584fac34f90d7d50680291eb780614052dc76",
}
CAP32_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
    "-lm",
)
CAP32_ALLOWED_LINKER_FORWARDING = cpc_allowed_linker_forwarding(
    CAP32_EXPECTED_LINK_OPTIONS
)
CAP32_SUCCESS_TRAILER = (
    "1 core(s) successfully processed:",
    f"\t{CAP32_CORE_ID}",
)
CAP32_FORBIDDEN_LOG_FRAGMENTS = (
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
CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-cap32.yml",
    "source_url": "https://github.com/libretro/libretro-cap32.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "4abfb8be233bec630f369379fb6c1d92d31f1c7d",
    "source_tree": "c9704612f7acd0459125bc28427212def1cce681",
    "source_key": CAP32_CORE_ID,
    "source_dir": "libretro-cap32",
    "output_path": "dist/unix/cap32_libretro.so",
    "artifact_name": CAP32_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/cap32_libretro.info",
    "metadata_artifact_name": "cap32_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile",
}
CAP32_LOG_CONTRACT = CpcLogContract(
    core_id=CAP32_CORE_ID,
    expected_c_compile_count=CAP32_EXPECTED_C_COMPILE_COUNT,
    build_artifact_name=CAP32_BUILD_ARTIFACT_NAME,
    expected_link_options=CAP32_EXPECTED_LINK_OPTIONS,
    source_commit=CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    make_trace=CpcMakeTraceContract(
        marker=CAP32_MAKE_TRACE_MARKER,
        compile_makefile_line="485",
        link_makefile_line="511",
    ),
)
CAP32_EXACT_LOG_CONTRACT = COnlyLogContract(
    core_id=CAP32_CORE_ID,
    expected_compile_count=CAP32_EXPECTED_C_COMPILE_COUNT,
    expected_compile_pair_sha256=CAP32_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        CAP32_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=CAP32_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=CAP32_BUILD_ARTIFACT_NAME,
    expected_link_options=CAP32_EXPECTED_LINK_OPTIONS,
    source_commit=CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=CAP32_EXPECTED_RAW_LINK_OBJECT_SHA256,
    expected_link_invocation_sha256=CAP32_EXPECTED_LINK_INVOCATION_SHA256,
)


def _cap32_log_has_exact_envelope(build_log_text: str) -> bool:
    """Reject unreviewed diagnostics and require the exact build envelope."""

    lines = build_log_text.splitlines()
    if lines[-len(CAP32_SUCCESS_TRAILER) :] != list(CAP32_SUCCESS_TRAILER):
        return False
    native_markers = [
        line
        for line in lines
        if line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION|")
    ]
    if native_markers != [CAP32_NATIVE_GIT_VERSION_MARKER]:
        return False
    if lines.index(CAP32_NATIVE_GIT_VERSION_MARKER) >= lines.index(
        CAP32_MAKE_TRACE_MARKER
    ):
        return False
    lowered_lines = [line.casefold() for line in lines]
    if any(
        fragment in line
        for line in lowered_lines
        for fragment in CAP32_FORBIDDEN_LOG_FRAGMENTS
    ):
        return False
    return not any(
        "warning:" in line or "note:" in line for line in lowered_lines
    )


def cap32_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Caprice32's exact source, argv, trace, and build envelope."""

    return bool(
        c_only_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            CAP32_EXACT_LOG_CONTRACT,
        )
        and cpc_log_proves_contract(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
            CAP32_LOG_CONTRACT,
        )
        and _cap32_log_has_exact_envelope(build_log_text)
    )
