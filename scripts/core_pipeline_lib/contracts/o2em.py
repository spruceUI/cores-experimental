"""Exact O2EM native-version C-only build-log contract."""

from __future__ import annotations

import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


O2EM_CORE_ID = "o2em"
O2EM_EXPECTED_COMPILE_COUNT = 42
O2EM_EXPECTED_COMPILE_PAIR_SHA256 = (
    "114f728cdc7478e5051cdf758c1c2e6c8a3ec79429df70fc9b5c4a9137b6823c"
)
O2EM_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "db363efa7a87669274fd8287d048b4afc2abfc37494216c612b88e081cfbdf43",
    "armhf": "2d97f851bc6881e85566d83b77c0a4460c0e605463508779cb8948c8dd02f680",
}
O2EM_EXPECTED_LINK_OBJECT_SHA256 = (
    "ac914313d526274da887a23b6be0f30aa4177e427040b56a94180bd7f5b9c7e2"
)
O2EM_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "ac914313d526274da887a23b6be0f30aa4177e427040b56a94180bd7f5b9c7e2"
)
O2EM_BUILD_ARTIFACT_NAME = "o2em_libretro.so"
O2EM_EXPECTED_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
    "-lm",
)
O2EM_NATIVE_GIT_VERSION = " e03d3be"
O2EM_NATIVE_GIT_VERSION_LOG_TOKEN = (
    r'-DGIT_VERSION=\"" e03d3be"\"'
)
O2EM_FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "warning:",
    "error:",
    "fatal:",
    "note:",
    "undefined reference",
    "dubious ownership",
    ": cannot find -l",
    "collect2: ld returned",
    "file format not recognized",
    "segmentation fault",
    "core dumped",
    "killed",
    "aborted",
)
O2EM_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)
O2EM_NATIVE_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-o2em.yml",
    "source_url": "https://github.com/libretro/libretro-o2em.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "e03d3be88f79fe940b933e53f1515d97313f6c59",
    "source_tree": "fef887dc747594a47e9bed9ac7367d2912b579d1",
    "source_key": O2EM_CORE_ID,
    "source_dir": "libretro-o2em",
    "output_path": "dist/unix/o2em_libretro.so",
    "artifact_name": O2EM_BUILD_ARTIFACT_NAME,
    "metadata_source_path": "/libretro-super/dist/info/o2em_libretro.info",
    "metadata_artifact_name": "o2em_libretro.info",
    "targets": ["arm64", "armhf"],
}


def o2em_spec_is_well_formed(spec: object) -> bool:
    """Require O2EM's exact catalog identity and native version derivation."""

    identity = O2EM_NATIVE_VERSION_SPEC_IDENTITY
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


O2EM_LOG_CONTRACT = COnlyLogContract(
    core_id=O2EM_CORE_ID,
    expected_compile_count=O2EM_EXPECTED_COMPILE_COUNT,
    expected_compile_pair_sha256=O2EM_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        O2EM_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=O2EM_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=O2EM_BUILD_ARTIFACT_NAME,
    expected_link_options=O2EM_EXPECTED_LINK_OPTIONS,
    source_commit=O2EM_NATIVE_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=O2EM_NATIVE_VERSION_SPEC_IDENTITY["source_tree"],
    expected_raw_link_object_sha256=(
        O2EM_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def o2em_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove O2EM's native version, diagnostics, compile, and link sets."""

    if not isinstance(build_log_text, str):
        return False
    lowered_log = build_log_text.casefold()
    if (
        any(
            marker in lowered_log
            for marker in O2EM_FORBIDDEN_DIAGNOSTIC_MARKERS
        )
        or O2EM_MAKE_FAILURE_RE.search(build_log_text) is not None
        or "CORE_PIPELINE_GIT_VERSION" in build_log_text
        or build_log_text.count("-DGIT_VERSION=")
        != O2EM_EXPECTED_COMPILE_COUNT
        or build_log_text.count(O2EM_NATIVE_GIT_VERSION_LOG_TOKEN)
        != O2EM_EXPECTED_COMPILE_COUNT
    ):
        return False
    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        O2EM_LOG_CONTRACT,
    )
