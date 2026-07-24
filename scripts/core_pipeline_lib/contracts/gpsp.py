"""Exact gpSP C/C++/assembly build-log contract.

gpSP is a direct-make GBA core with a small C++ component and a per-ABI ARM
dynarec written in assembly (24 C, 2 C++, 2 assembly sources per architecture);
the assembly sources and per-arch flags differ per ABI, so every sha256 identity
is captured per architecture on the shared c_asm standard. The final link is
driven by the C compiler.
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


GPSP_CORE_ID = "gpsp"
GPSP_BUILD_ARTIFACT_NAME = "gpsp_libretro.so"

GPSP_SOURCE_COMMIT = "69e86ebe89f14c3f5f75b809c12c0a953b3d6ce4"
GPSP_SOURCE_TREE = "de26635ae1419714d0efe3c85b75faf494be950c"

GPSP_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-gpsp.yml",
    "source_url": "https://github.com/libretro/gpsp.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": GPSP_SOURCE_COMMIT,
    "source_tree": GPSP_SOURCE_TREE,
    "source_dir": "gpsp",
    "output_path": "gpsp_libretro.so",
    "artifact_name": GPSP_BUILD_ARTIFACT_NAME,
    "platforms": {"arm64": "arm64", "armhf": "armv7hardfloat"},
    "metadata_source_path": "/libretro-super/dist/info/gpsp_libretro.info",
    "metadata_artifact_name": "gpsp_libretro.info",
    "targets": ["arm64", "armhf"],
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the gpsp core must preserve its exact source, "
    "direct-make recipe, platforms, metadata, and target "
    "contract"
)


def gpsp_spec_is_well_formed(spec: object) -> bool:
    """Require gpSP's exact immutable direct-make catalog identity."""

    identity = GPSP_SPEC_IDENTITY
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
                "driver": "direct-make",
                "source_dir": identity["source_dir"],
                "output_path": identity["output_path"],
                "artifact_name": identity["artifact_name"],
                "platforms": identity["platforms"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


GPSP_LOG_CONTRACT_ID = "gpsp-c-asm-v1"
GPSP_EXPECTED_C_COMPILE_COUNT = {"arm64": 24, "armhf": 24}
GPSP_EXPECTED_CXX_COMPILE_COUNT = {"arm64": 2, "armhf": 2}
GPSP_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 2, "armhf": 2}
GPSP_EXPECTED_COMPILE_PAIR_SHA256 = {
    "arm64": "aab7ee27969dc21136fef52fdeb0dead0cab66954d6bfab1a2779935233e9ccf",
    "armhf": "edc94d83fa8bbb3b82f9c9848eea62f6eff7c34f77b9ebb8e4939fab1891420b",
}
GPSP_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "5e0fa1a6555f549feeaff649a6dc0e14d9599a951ee464c845a365a41ec5750e",
    "armhf": "11434ab3860b6fc00a7723c56e8633fc19fb518ac3f50c5883aecc8e3af9d134",
}
GPSP_EXPECTED_LINK_OBJECT_SHA256 = {
    "arm64": "c3b417f3d3787d0157d840b3e1189b756dc978516fa257448771bfc1c9182610",
    "armhf": "2f53cea0a90eb5902f3c6d3208580da537ba26e1721b2a1d9fd264754b2d17d2",
}
GPSP_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "arm64": "fa7755857be25c771c5f545f2b39d7fdb48c1b29e265449a0439c8c3215e9221",
    "armhf": "26ff38452dc2c78fe58dd8f6177a4358d3cf94b5423d2b389a96480f2a9e8e1a",
}
# The link options are identical on both ABIs; captured per arch for symmetry.
GPSP_LINK_OPTIONS = (
    "-fPIC",
    "-shared",
    "-Wl,--version-script=link.T",
    "-I./libretro",
    "-I./libretro/libretro-common/include",
    "-I./",
    "-O3",
    "-DNDEBUG",
    "-lm",
    "-Wl,--no-undefined",
)
GPSP_EXPECTED_LINK_OPTIONS = {"arm64": GPSP_LINK_OPTIONS, "armhf": GPSP_LINK_OPTIONS}


def gpsp_c_asm_contract() -> CAsmLogContract:
    """Return gpSP's exact per-arch C/C++/assembly proof parameters."""

    return CAsmLogContract(
        core_id=GPSP_CORE_ID,
        expected_c_compile_count=GPSP_EXPECTED_C_COMPILE_COUNT,
        expected_asm_compile_count=GPSP_EXPECTED_ASM_COMPILE_COUNT,
        expected_compile_pair_sha256=GPSP_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            GPSP_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=GPSP_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=GPSP_BUILD_ARTIFACT_NAME,
        expected_link_options=GPSP_EXPECTED_LINK_OPTIONS,
        source_commit=GPSP_SOURCE_COMMIT,
        source_tree=GPSP_SOURCE_TREE,
        expected_cxx_compile_count=GPSP_EXPECTED_CXX_COMPILE_COUNT,
        expected_link_language="c",
        expected_raw_link_object_sha256=GPSP_EXPECTED_RAW_LINK_OBJECT_SHA256,
        semantic_path_aliases=(),
    )


def gpsp_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove gpSP's exact per-arch C/C++/assembly compiles and link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        gpsp_c_asm_contract(),
    )


__all__ = [
    "GPSP_BUILD_ARTIFACT_NAME",
    "GPSP_CORE_ID",
    "GPSP_LOG_CONTRACT_ID",
    "GPSP_SOURCE_COMMIT",
    "GPSP_SOURCE_TREE",
    "GPSP_SPEC_IDENTITY",
    "gpsp_c_asm_contract",
    "gpsp_log_proves_contract",
    "gpsp_spec_is_well_formed",
]
