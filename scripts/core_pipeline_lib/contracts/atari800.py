"""Exact Atari800 native-version C-only compile/link and evidence contract.

Atari800 uses the shared C-only compile/link proof standard: the reviewed
compile and link commands are proven exactly via ``c_only_log_proves_contract``
(which sorts compile invocations, so parallel-interleaved build logs are
accepted). Its promoted source/build records and whole-file metadata
replacement are still bound through the golden/metadata helpers below; the
former full-log-envelope proof was dropped in favour of the shared standard.
"""

from __future__ import annotations

import re

from .c_only import COnlyLogContract, c_only_log_proves_contract


ATARI800_CORE_ID = "atari800"
ATARI800_BUILD_ARTIFACT_NAME = "atari800_libretro.so"

ATARI800_NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
ATARI800_NATIVE_GIT_VERSION = " 9d3bcf2"

ATARI800_METADATA_REPLACEMENT_KIND = "whole-file-v1"
ATARI800_METADATA_REPLACEMENT_PATH = "metadata/atari800/source-v1.info"
ATARI800_METADATA_PREIMAGE_SHA256 = (
    "1682c00740626f0bc709dbbcdae1777222773b93a1007bc02e4024df7b181653"
)
ATARI800_METADATA_REPLACEMENT_SHA256 = (
    "4b56fa399760a8c48e6ac8b08ecc2ae2f7163bbfb34f3f08351bc7e092602e5e"
)
ATARI800_METADATA_REPLACEMENT = {
    "kind": ATARI800_METADATA_REPLACEMENT_KIND,
    "path": ATARI800_METADATA_REPLACEMENT_PATH,
    "preimage_sha256": ATARI800_METADATA_PREIMAGE_SHA256,
    "replacement_sha256": ATARI800_METADATA_REPLACEMENT_SHA256,
}

ATARI800_FORBIDDEN_NEEDED_PREFIXES = [
    "libEGL",
    "libGL",
    "libGLES",
    "libOpenGL",
    "libSDL",
    "libstdc++",
    "libz",
]
ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-atari800.yml",
    "source_url": "https://github.com/libretro/libretro-atari800.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "9d3bcf283502512052e21c6f1453fbdf7aa3122b",
    "source_tree": "b42ab0f0a498f3aa076c62825a9082fb7e5889e8",
    "source_key": ATARI800_CORE_ID,
    "source_dir": "libretro-atari800",
    "output_path": "dist/unix/atari800_libretro.so",
    "artifact_name": ATARI800_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/atari800_libretro.info"
    ),
    "metadata_artifact_name": "atari800_libretro.info",
    "targets": ["arm64", "armhf"],
    "compiler_scope": "c",
    "native_makefile": "Makefile",
    "forbidden_needed_prefixes": ATARI800_FORBIDDEN_NEEDED_PREFIXES,
}

# The exact reviewed object set. The compile/link sha256 constants below pin
# the commands; this list documents which translation units they cover and
# derives the expected compile count.
ATARI800_EXPECTED_RAW_LINK_OBJECTS = tuple(
    """
./libretro/libretro-common/streams/memory_stream.o
./libretro/libretro-common/compat/compat_strl.o
./libretro/libretro-common/compat/compat_strcasestr.o
./libretro/libretro-common/compat/fopen_utf8.o
./libretro/libretro-common/encodings/encoding_utf.o
./libretro/libretro-common/file/file_path.o
./libretro/libretro-common/file/file_path_io.o
./libretro/libretro-common/string/stdstring.o
./libretro/libretro-common/time/rtime.o
./libretro/libretro-common/vfs/vfs_implementation.o
./libretro/carts_hash.o
./libretro/libretro-core.o
./libretro/core-mapper.o
./libretro/graph.o
./libretro/vkbd.o
./libretro/retro_strings.o
./libretro/retro_utils.o
./libretro/retro_disk_control.o
./atari800/src/afile.o
./atari800/src/antic.o
./atari800/src/atari.o
./atari800/src/binload.o
./atari800/src/cartridge.o
./atari800/src/cassette.o
./atari800/src/compfile.o
./atari800/src/cfg.o
./atari800/src/cpu.o
./atari800/src/crc32.o
./atari800/src/devices.o
./atari800/src/cartridge_info.o
./atari800/src/esc.o
./atari800/src/gtia.o
./atari800/src/img_tape.o
./atari800/src/log.o
./atari800/src/memory.o
./atari800/src/monitor.o
./atari800/src/pbi.o
./atari800/src/pia.o
./atari800/src/pokey.o
./atari800/src/pokeysnd.o
./atari800/src/mzpokeysnd.o
./atari800/src/remez.o
./atari800/src/rtime.o
./atari800/src/sio.o
./atari800/src/sysrom.o
./atari800/src/util.o
./atari800/src/sound.o
./atari800/src/pbi_proto80.o
./atari800/src/af80.o
./atari800/src/input.o
./atari800/src/statesav.o
./atari800/src/ui_basic.o
./atari800/src/ui.o
./atari800/src/artifact.o
./atari800/src/colours.o
./atari800/src/colours_ntsc.o
./atari800/src/colours_pal.o
./atari800/src/colours_external.o
./atari800/src/screen.o
./atari800/src/cycle_map.o
./atari800/src/pbi_mio.o
./atari800/src/pbi_bb.o
./atari800/src/pbi_scsi.o
./atari800/src/ide.o
./atari800/src/xep80.o
./atari800/src/xep80_fonts.o
./atari800/src/file_export.o
./atari800/src/filter_ntsc.o
./atari800/src/atari_ntsc/atari_ntsc.o
./libretro/platform.o
./atari800/src/roms/altirraos_xl.o
./atari800/src/roms/altirraos_800.o
./atari800/src/roms/altirra_basic.o
./atari800/src/roms/altirra_5200_os.o
./atari800/src/roms/altirra_5200_charset.o
./deps/zlib/adler32.o
./deps/zlib/crc32.o
./deps/zlib/deflate.o
./deps/zlib/gzclose.o
./deps/zlib/gzlib.o
./deps/zlib/gzread.o
./deps/zlib/gzwrite.o
./deps/zlib/inffast.o
./deps/zlib/inflate.o
./deps/zlib/inftrees.o
./deps/zlib/trees.o
./deps/zlib/zutil.o
""".split()
)
ATARI800_EXPECTED_COMPILE_PAIRS = tuple(
    (
        raw_output.removeprefix("./"),
        raw_output.removeprefix("./").removesuffix(".o") + ".c",
    )
    for raw_output in ATARI800_EXPECTED_RAW_LINK_OBJECTS
)
ATARI800_EXPECTED_COMPILE_COUNT = len(ATARI800_EXPECTED_COMPILE_PAIRS)
ATARI800_EXPECTED_COMPILE_PAIR_SHA256 = (
    "81d0a9ae4f3ab548318ce69e92ab4a379d7af2cbb5cc66e8555dcbf8e542c22d"
)
ATARI800_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "a000fe531d1515ccab47f5310dc5f55ed8a4c157ea0ac9f6458d94fbde4bb68e",
    "armhf": "a3fcbb8f4ed55d358d0c9c76d130de776845918190946916f2d45b1461cbbf33",
}
ATARI800_EXPECTED_LINK_OBJECT_SHA256 = (
    "70cd4c4c05e9f872d9429aa1cf897e8d4c3e0d895b1cdec37aa327f7b187a9d2"
)
ATARI800_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "51a91349057bc68204f307126932e7f71105febe8cbda55f88a4838091792e89"
)
ATARI800_EXPECTED_LINK_OPTIONS = (
    "-shared",
    "-Wl,-version-script=link.T",
    "-Wl,-no-undefined",
    "-lm",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def atari800_spec_is_well_formed(spec: object) -> bool:
    """Require Atari800's complete immutable catalog contract."""

    identity = ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "git_version": {
                    "derivation": ATARI800_NATIVE_GIT_VERSION_DERIVATION,
                    "value": ATARI800_NATIVE_GIT_VERSION,
                    "compiler_scope": identity["compiler_scope"],
                },
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
                "replacement": ATARI800_METADATA_REPLACEMENT,
            },
            "targets": identity["targets"],
            "validation": {
                "forbidden_needed_prefixes": identity[
                    "forbidden_needed_prefixes"
                ]
            },
        }
    )


def atari800_identity_is_well_formed(spec: object) -> bool:
    """Bind Atari800 while a detailed validator reports replacement errors."""

    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
        "validation",
    }:
        return False
    identity = ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    validation = spec.get("validation")
    if not all(
        isinstance(value, dict)
        for value in (source, build, metadata, validation)
    ):
        return False
    assert isinstance(metadata, dict)
    if (
        not set(metadata).issubset(
            {"source_path", "artifact_name", "replacement"}
        )
        or set(metadata) - {"replacement"}
        != {"source_path", "artifact_name"}
    ):
        return False
    return bool(
        spec.get("workflow") == identity["workflow"]
        and source
        == {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
        }
        and build
        == {
            "driver": "libretro-super",
            "source_key": identity["source_key"],
            "source_dir": identity["source_dir"],
            "output_path": identity["output_path"],
            "artifact_name": identity["artifact_name"],
            "git_version": {
                "derivation": ATARI800_NATIVE_GIT_VERSION_DERIVATION,
                "value": ATARI800_NATIVE_GIT_VERSION,
                "compiler_scope": identity["compiler_scope"],
            },
        }
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name")
        == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
        and validation
        == {
            "forbidden_needed_prefixes": identity[
                "forbidden_needed_prefixes"
            ]
        }
    )


def atari800_metadata_replacement_contract_is_well_formed(
    value: object,
) -> bool:
    """Recognize only the reviewed Atari800 whole-file metadata replacement."""

    return bool(
        isinstance(value, dict) and value == ATARI800_METADATA_REPLACEMENT
    )


def atari800_golden_source_is_well_formed(
    core_id: object,
    source: object,
) -> bool:
    """Bind a promoted source record to the exact reviewed Atari800 tree."""

    identity = ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        core_id == ATARI800_CORE_ID
        and isinstance(source, dict)
        and source
        == {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
    )


def atari800_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
) -> bool:
    """Require Atari800's native version and metadata replacement contract."""

    identity = ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(build, dict)
        and source_commit == identity["source_commit"]
        and atari800_golden_source_is_well_formed(core_id, source)
        and build
        == {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": ATARI800_NATIVE_GIT_VERSION_DERIVATION,
                "value": ATARI800_NATIVE_GIT_VERSION,
                "compiler_scope": identity["compiler_scope"],
            },
            "metadata_replacement": ATARI800_METADATA_REPLACEMENT,
            "log": "build.log",
            "log_sha256": build.get("log_sha256"),
        }
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
    )


def atari800_c_only_contract() -> COnlyLogContract:
    """Return Atari800's exact compile/link proof parameters."""

    return COnlyLogContract(
        core_id=ATARI800_CORE_ID,
        expected_compile_count=ATARI800_EXPECTED_COMPILE_COUNT,
        expected_compile_pair_sha256=ATARI800_EXPECTED_COMPILE_PAIR_SHA256,
        expected_compile_invocation_sha256=(
            ATARI800_EXPECTED_COMPILE_INVOCATION_SHA256
        ),
        expected_link_object_sha256=ATARI800_EXPECTED_LINK_OBJECT_SHA256,
        build_artifact_name=ATARI800_BUILD_ARTIFACT_NAME,
        expected_link_options=ATARI800_EXPECTED_LINK_OPTIONS,
        source_commit=ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        source_tree=ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"],
        expected_raw_link_object_sha256=(
            ATARI800_EXPECTED_RAW_LINK_OBJECT_SHA256
        ),
    )


def atari800_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Atari800's exact compile and link commands for one architecture."""

    return c_only_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        atari800_c_only_contract(),
    )
