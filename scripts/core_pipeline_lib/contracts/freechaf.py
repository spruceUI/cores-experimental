"""Exact FreeChaF native-version C-only build-log contract."""

from __future__ import annotations

import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


FREECHAF_CORE_ID = "freechaf"
FREECHAF_EXPECTED_COMPILE_COUNT = 25
FREECHAF_EXPECTED_COMPILE_PAIR_SHA256 = (
    "4c0d7b11a3f58cd09aab51ac9614b370e1a22c1f4dc0584f333dd036e04c39d7"
)
FREECHAF_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "54d1259958fb40c52fcaccec94f03404a1fbde06fcc535bb595ea30dbfce98ef",
    "armhf": "a6f12936542629961c3033e9bbb5132c6a5e4020982c2babe35236348e8d3d81",
}
FREECHAF_EXPECTED_LINK_OBJECT_SHA256 = (
    "c21e6399d24b3bdd11f7c477cd91663958ff1e6711fea312799b788f90c7101f"
)
FREECHAF_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "c21e6399d24b3bdd11f7c477cd91663958ff1e6711fea312799b788f90c7101f"
)
FREECHAF_BUILD_ARTIFACT_NAME = "freechaf_libretro.so"
FREECHAF_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=./link.T",
    "-Wl,--no-undefined",
)
FREECHAF_NATIVE_GIT_VERSION = " 76c7a84"
FREECHAF_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" 76c7a84"\"'
)
FREECHAF_SUBMODULE_PATH = "src/deps/libretro-common"
FREECHAF_SUBMODULE_COMMIT = "01c6122931a10a7012973054e7067859d2116420"
FREECHAF_SUBMODULE_CHECKOUT_MARKER = (
    f"Submodule path '{FREECHAF_SUBMODULE_PATH}': checked out "
    f"'{FREECHAF_SUBMODULE_COMMIT}'"
)
FREECHAF_EXPECTED_WARNING_LINE = (
    "src/deps/libretro-common/file/file_path.c:77:10: warning: unused variable "
    "'local' [-Wunused-variable]"
)
FREECHAF_EXPECTED_WARNING_BLOCK = "\n".join(
    (
        "src/deps/libretro-common/file/file_path.c: In function 'strftime_am_pm':",
        FREECHAF_EXPECTED_WARNING_LINE,
        "   77 |    char *local = NULL;",
        "      |          ^~~~~",
    )
)
FREECHAF_FORBIDDEN_DIAGNOSTIC_MARKERS = (
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
FREECHAF_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
FREECHAF_NATIVE_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-freechaf.yml",
    "source_url": "https://github.com/libretro/FreeChaF.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "76c7a84f1f7e80f3e6f2bba96fe100cb24e99124",
    "source_tree": "da8f96e1b0866e49ecf6a3bcd2b9974670669429",
    "source_key": FREECHAF_CORE_ID,
    "source_dir": "libretro-freechaf",
    "output_path": "dist/unix/freechaf_libretro.so",
    "artifact_name": FREECHAF_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/freechaf_libretro.info",
    "metadata_artifact_name": "freechaf_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the freechaf core must preserve its exact native "
    "version, source, recipe, metadata, and target contract"
)


def freechaf_spec_is_well_formed(spec: object) -> bool:
    """Require FreeChaF's complete catalog identity and native version input."""

    identity = FREECHAF_NATIVE_VERSION_SPEC_IDENTITY
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
                "submodules": [
                    {"path": "src/deps/libretro-common", "commit": "01c6122931a10a7012973054e7067859d2116420"},
                ],
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


FREECHAF_LOG_CONTRACT = COnlyLogContract(
    core_id=FREECHAF_CORE_ID,
    expected_compile_count=FREECHAF_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=FREECHAF_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        FREECHAF_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=FREECHAF_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=FREECHAF_BUILD_ARTIFACT_NAME,
    expected_link_options=FREECHAF_EXPECTED_LINK_OPTIONS,
    source_commit=FREECHAF_NATIVE_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=FREECHAF_NATIVE_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=(
        FREECHAF_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def freechaf_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove FreeChaF's source, native version, warning, compile, and link sets."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    warning_lines = [
        line
        for line in build_log_text.splitlines()
        if "warning:" in line.casefold()
    ]
    submodule_checkout_lines = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("Submodule path '") and ": checked out '" in line
    ]
    if (
        any(
            marker in lowered_log
            for marker in FREECHAF_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or FREECHAF_MAKE_FAILURE_RE.search(build_log_text) is not None
        or warning_lines != [FREECHAF_EXPECTED_WARNING_LINE]
        or build_log_text.count(FREECHAF_EXPECTED_WARNING_BLOCK) != 1
        or submodule_checkout_lines != [FREECHAF_SUBMODULE_CHECKOUT_MARKER]
        or build_log_text.count(FREECHAF_SUBMODULE_CHECKOUT_MARKER) != 1
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != FREECHAF_EXPECTED_COMPILE_COUNT
        or build_log_text.count(FREECHAF_NATIVE_GIT_VERSION_LOG_TOKEN)
        != FREECHAF_EXPECTED_COMPILE_COUNT
    ):
        return False
    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        FREECHAF_LOG_CONTRACT,
    )
