"""Exact Parallel N64 C/C++/assembly contract and reviewed make-variable set.

parallel_n64 is the first catalog core whose artifact *directly links* a
graphics library: the shipped SpruceOS ``parallel_n64_libretro.so`` carries
``libGLESv2.so.2`` in ``DT_NEEDED``. Every other core reaches GL through the
frontend (``SET_HW_RENDER`` plus ``get_proc_address``), so this one is the
exception that the reviewed make-variable set below exists to reproduce. It is
also shipped **arm64 only**, so the catalog targets one ABI.

Its Makefile defaults ``ARCH`` to ``uname -m``, which is ``x86_64`` on the
cross-build host: the default build selects the x86 dynarec and ``-msse
-msse2``, and the aarch64 compiler rejects those flags outright. ``ARCH`` is a
reserved make-variable name (the pipeline owns toolchain identity), but the
Makefile keys everything that actually matters off non-reserved switches:

* ``WITH_DYNAREC=aarch64`` selects the arm64 dynarec and its
  ``linkage_arm64.S`` assembly. It defaults to ``$(ARCH)``, so naming it
  directly makes ``ARCH`` irrelevant.
* ``NOSSE=1`` suppresses the ``-msse -msse2`` block, which is gated on
  ``WITH_DYNAREC`` being x86-shaped rather than on ``ARCH``.
* ``GLES=1`` selects the GLES2 renderer, which is what makes the artifact link
  ``libGLESv2`` the way the shipped one does.

That set was verified equivalent to the reserved-name spelling: a full build
with ``ARCH=aarch64 GLES=1`` and one with ``WITH_DYNAREC=aarch64 GLES=1
NOSSE=1`` produced a byte-identical ``parallel_n64_libretro.so``.
``WITH_DYNAREC`` is also why ``make_variables`` had to admit a string value;
the reviewed-profile equality is what actually admits it.
"""

from __future__ import annotations

from .c_asm import CAsmLogContract, c_asm_log_proves_contract


PARALLEL_N64_CORE_ID = "parallel_n64"
PARALLEL_N64_BUILD_ARTIFACT_NAME = "parallel_n64_libretro.so"

PARALLEL_N64_SOURCE_COMMIT = "00c6c9df91d2c2daaae615cefad7911be556fbfa"
PARALLEL_N64_SOURCE_TREE = "d762ea5fe18afe5f245080082148005f1c7ce811"

PARALLEL_N64_MAKE_VARIABLES = {
    "GLES": 1,
    "NOSSE": 1,
    "WITH_DYNAREC": "aarch64",
}
PARALLEL_N64_MAKE_PROFILE = "parallel-n64-aarch64-gles-v1"

PARALLEL_N64_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-parallel_n64.yml",
    "source_url": "https://github.com/libretro/parallel-n64.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": PARALLEL_N64_SOURCE_COMMIT,
    "source_tree": PARALLEL_N64_SOURCE_TREE,
    "source_key": PARALLEL_N64_CORE_ID,
    "source_dir": "libretro-parallel_n64",
    "output_path": "dist/unix/parallel_n64_libretro.so",
    "artifact_name": PARALLEL_N64_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/parallel_n64_libretro.info"
    ),
    "metadata_artifact_name": "parallel_n64_libretro.info",
    "targets": ["arm64"],
}


def parallel_n64_spec_is_well_formed(spec: object) -> bool:
    """Require Parallel N64's exact immutable catalog identity."""

    identity = PARALLEL_N64_SPEC_IDENTITY
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
                "source_date_epoch": 1784512327,
                "make_variables": dict(PARALLEL_N64_MAKE_VARIABLES),
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


PARALLEL_N64_LOG_CONTRACT_ID = "parallel-n64-c-asm-v1"
PARALLEL_N64_EXPECTED_C_COMPILE_COUNT = {"arm64": 215}
PARALLEL_N64_EXPECTED_CXX_COMPILE_COUNT = {"arm64": 34}
PARALLEL_N64_EXPECTED_ASM_COMPILE_COUNT = {"arm64": 1}
PARALLEL_N64_EXPECTED_COMPILE_PAIR_SHA256 = {
    "arm64": (
        "43a7796e62598002665e66481081722a72521ba6349f6ec90f6f4d36f7f65bdf"
    ),
}
PARALLEL_N64_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": (
        "7d311131bf59b76b6e2457047eca4e3b4af4988449c599c16c2e71b48fbffa89"
    ),
}
PARALLEL_N64_EXPECTED_LINK_OBJECT_SHA256 = {
    "arm64": (
        "34ecc566293c0c6cd096d068e7d51fc8d60e0c2d7dee6e7a64189e8b10f7e535"
    ),
}
PARALLEL_N64_EXPECTED_RAW_LINK_OBJECT_SHA256 = {
    "arm64": (
        "437332099acbe00101283d490c9a9fc05b1c319299d14938ff9bd946c4c04a91"
    ),
}
# The `-lGLESv2` operand is the whole point of the GLES=1 make variable, and it
# is pinned here: a build that silently lost the GLES renderer would no longer
# prove this contract.
PARALLEL_N64_EXPECTED_LINK_OPTIONS = {
    "arm64": (
        "-shared",
        "-Wl,--no-undefined",
        "-Wl,--version-script=./libretro/link.T",
        "-lpthread",
        "-lrt",
        "-lm",
        "-fPIC",
        "-lGLESv2",
    ),
}

PARALLEL_N64_LOG_CONTRACT = CAsmLogContract(
    core_id=PARALLEL_N64_CORE_ID,
    expected_c_compile_count=PARALLEL_N64_EXPECTED_C_COMPILE_COUNT,
    expected_asm_compile_count=PARALLEL_N64_EXPECTED_ASM_COMPILE_COUNT,
    expected_compile_pair_sha256=PARALLEL_N64_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        PARALLEL_N64_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=PARALLEL_N64_EXPECTED_LINK_OBJECT_SHA256,
    build_artifact_name=PARALLEL_N64_BUILD_ARTIFACT_NAME,
    expected_link_options=PARALLEL_N64_EXPECTED_LINK_OPTIONS,
    source_commit=PARALLEL_N64_SOURCE_COMMIT,
    source_tree=PARALLEL_N64_SOURCE_TREE,
    expected_cxx_compile_count=PARALLEL_N64_EXPECTED_CXX_COMPILE_COUNT,
    expected_link_language="cxx",
    expected_raw_link_object_sha256=(
        PARALLEL_N64_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
)


def parallel_n64_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Parallel N64's exact compile set and ordered C++ link."""

    return c_asm_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        PARALLEL_N64_LOG_CONTRACT,
    )


__all__ = [
    "PARALLEL_N64_BUILD_ARTIFACT_NAME",
    "PARALLEL_N64_CORE_ID",
    "PARALLEL_N64_LOG_CONTRACT_ID",
    "PARALLEL_N64_MAKE_PROFILE",
    "PARALLEL_N64_MAKE_VARIABLES",
    "PARALLEL_N64_SOURCE_COMMIT",
    "PARALLEL_N64_SOURCE_TREE",
    "PARALLEL_N64_SPEC_IDENTITY",
    "parallel_n64_log_proves_contract",
    "parallel_n64_spec_is_well_formed",
]
