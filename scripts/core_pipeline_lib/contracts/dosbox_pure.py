"""Exact DOSBox Pure mixed-language (all-C++) contract.

dosbox_pure is 112 C++ translation units and no C, so it is the ``mixed_language``
standard with an empty C bucket, linked by the C++ driver.

Two build-shape notes:

* Its ``COMPILE`` define silences the compiler with ``@``, so the compile argv
  never reaches the log. A reviewed ``build.overlays`` patch drops that one
  token -- echo only, the artifact is byte-identical. The link recipe was
  already visible.
* It flattens the whole source tree into one object directory by mangling ``/``
  to ``~``: ``src/hardware/vga.cpp`` becomes
  ``build/release/src~hardware~vga.cpp.o``. ``~`` is a shell metacharacter, so
  that shape had to clear three guards: the object==``<stem>.o`` naming check
  (hence ``sha_pinned_object_names``), the shared containment guard's
  per-segment charset (now admits a ``~`` that does not lead a segment), and
  the line-level lexical guard (hence ``allow_embedded_tilde``, which admits a
  ``~`` only where no shell would expand it).

The exact per-compile object/source pairing stays pinned by the compile pair and
per-architecture invocation sha256, so nothing is lost by relaxing the name.
"""

from __future__ import annotations

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


DOSBOX_PURE_CORE_ID = "dosbox_pure"
DOSBOX_PURE_BUILD_ARTIFACT_NAME = "dosbox_pure_libretro.so"

DOSBOX_PURE_SOURCE_COMMIT = "a4a0bab7f8931433588f2fcad9045c85b277373d"
DOSBOX_PURE_SOURCE_TREE = "0b64e0b00ba92300de9f73f213f3feaddf54a134"

DOSBOX_PURE_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-dosbox_pure.yml",
    "source_url": "https://github.com/libretro/dosbox-pure.git",
    "source_requested_ref": "refs/heads/main",
    "source_commit": DOSBOX_PURE_SOURCE_COMMIT,
    "source_tree": DOSBOX_PURE_SOURCE_TREE,
    "source_key": DOSBOX_PURE_CORE_ID,
    "source_dir": "libretro-dosbox_pure",
    "output_path": "dist/unix/dosbox_pure_libretro.so",
    "artifact_name": DOSBOX_PURE_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/dosbox_pure_libretro.info"
    ),
    "metadata_artifact_name": "dosbox_pure_libretro.info",
    "targets": ["arm64", "armhf"],
}

DOSBOX_PURE_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/dosbox_pure/makefile-echo-compile.patch",
    "patch_sha256": (
        "558e13fd0eda732aba8deb3c810f6938bd2928730102a7c69034680ea9ac5427"
    ),
    "source_path": "Makefile",
    "preimage_sha256": (
        "5173c065012911a306f9554212b0fb40fb5f51eda462b33b410ce9d15e31122b"
    ),
    "postimage_sha256": (
        "4df0254507737f44f3c2668f5c80387a57516108d1bd9d29327561f427b2d4fc"
    ),
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the dosbox_pure core must preserve its exact source, "
    "recipe, overlay, metadata, and target contract"
)


DOSBOX_PURE_SORT_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/dosbox_pure/makefile-echo-and-sort.patch",
    "patch_sha256": (
        "e153114cd471eaab74c25387632caf67c17c1a1a7f3182f8d9989961bdc3e0ca"
    ),
    "source_path": "Makefile",
    "preimage_sha256": (
        "5173c065012911a306f9554212b0fb40fb5f51eda462b33b410ce9d15e31122b"
    ),
    "postimage_sha256": (
        "66f8b298fd0920b109ac1f669207ece2cbb91d7399a7013f1df8d61d5e959472"
    ),
}


def dosbox_pure_spec_is_well_formed(spec: object) -> bool:
    """Require DOSBox Pure's exact immutable catalog identity."""

    identity = DOSBOX_PURE_SPEC_IDENTITY
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
                "overlays": {
                    "arm64": [dict(DOSBOX_PURE_SORT_OVERLAY)],
                    "armhf": [dict(DOSBOX_PURE_SORT_OVERLAY)],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


DOSBOX_PURE_LOG_CONTRACT_ID = "dosbox-pure-mixed-language-v1"
DOSBOX_PURE_EXPECTED_COMPILE_COUNT = 112
DOSBOX_PURE_EXPECTED_LANGUAGE_COUNTS = {"cxx": 112}
DOSBOX_PURE_EXPECTED_COMPILE_PAIR_SHA256 = (
    "13b3539c6e6830e137358c60b270117fef2d94da5b1fe1bacdec12d85e51dec5"
)
DOSBOX_PURE_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "54ccf8f01186a4ea843cd990fafae93e581d34918802258b931329d4b9dbd41c",
    "armhf": "de354ddfc66240b4cec0f52b8932b18704be0b99eeacad0c56edbe80cd8cb225",
}
_LINK_OBJECTS = (
    "ebaaa51bbf6fbf1ac0fb918317c4aef40f7607f8ea56bf7b6b8359df2b0a7dc6"
)
DOSBOX_PURE_EXPECTED_LINK_OBJECT_SHA256 = _LINK_OBJECTS
DOSBOX_PURE_EXPECTED_RAW_LINK_OBJECT_SHA256 = _LINK_OBJECTS
DOSBOX_PURE_EXPECTED_LINK_OPTIONS = (
    "-Wl,--gc-sections",
    "-fno-ident",
    "-O2",
    "-shared",
    "-lpthread",
)
# No ordered-link-argv pin: the Makefile's object list is filesystem
# enumeration order, which differs per host (GitHub runners produced the
# same 120-object multiset in a different order). The link stays exactly
# pinned by the order-tolerant object multiset and the ordered option set.

DOSBOX_PURE_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=DOSBOX_PURE_CORE_ID,
    expected_compile_count=DOSBOX_PURE_EXPECTED_COMPILE_COUNT,
    expected_language_counts=DOSBOX_PURE_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=DOSBOX_PURE_EXPECTED_COMPILE_PAIR_SHA256,
    expected_compile_invocation_sha256=(
        DOSBOX_PURE_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=DOSBOX_PURE_EXPECTED_LINK_OBJECT_SHA256,
    expected_raw_link_object_sha256=(
        DOSBOX_PURE_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=DOSBOX_PURE_BUILD_ARTIFACT_NAME,
    expected_link_options=DOSBOX_PURE_EXPECTED_LINK_OPTIONS,
    source_commit=DOSBOX_PURE_SOURCE_COMMIT,
    source_tree=DOSBOX_PURE_SOURCE_TREE,
    expected_link_language="cxx",
    sha_pinned_object_names=True,
    allow_embedded_tilde=True,
)


def dosbox_pure_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove DOSBox Pure's exact 112-C++ compile set and ordered C++ link."""

    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        DOSBOX_PURE_LOG_CONTRACT,
    )


__all__ = [
    "DOSBOX_PURE_BUILD_ARTIFACT_NAME",
    "DOSBOX_PURE_CORE_ID",
    "DOSBOX_PURE_LOG_CONTRACT_ID",
    "DOSBOX_PURE_SOURCE_COMMIT",
    "DOSBOX_PURE_SOURCE_TREE",
    "DOSBOX_PURE_SPEC_IDENTITY",
    "dosbox_pure_log_proves_contract",
    "dosbox_pure_spec_is_well_formed",
]
