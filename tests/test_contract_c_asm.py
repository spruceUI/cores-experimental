"""Unit tests for the shared C-plus-assembly proof engine (c_asm)."""

from __future__ import annotations

import dataclasses
import shlex
import unittest

from scripts.core_pipeline_lib.contracts import c_asm
from scripts.core_pipeline_lib.contracts.c_only import (
    c_only_compile_invocation_sha256,
    c_only_compile_pair_sha256,
    c_only_link_object_sha256,
    c_only_raw_link_object_sha256,
)


CC = "aarch64-linux-gnu-gcc"
COMMIT = "a" * 40
TREE = "b" * 40
CORE = "example_asm"
ARTIFACT = "example_asm_libretro.so"

COMPILE_C = f"{CC} -c -o src/a.o src/a.c -O2 -DNDEBUG"
COMPILE_ASM = f"{CC} -c -o src/dyna.o src/dyna.S -O2"
LINK = f"{CC} -shared -o {ARTIFACT} ./src/a.o ./src/dyna.o -lm"
# A make "$(info CC: <compiler> : <version>)" banner names the compiler inside
# prose and carries parentheses; it must be skipped, not fail the proof.
BANNER = f"CC:          {CC} : {CC} (Ubuntu 9.4.0-1ubuntu1~20.04.2) 9.4.0"


def _build_contract() -> c_asm.CAsmLogContract:
    c_inv = c_asm.c_asm_compile_invocation(shlex.split(COMPILE_C), {CC})
    asm_inv = c_asm.c_asm_compile_invocation(shlex.split(COMPILE_ASM), {CC})
    assert c_inv is not None and asm_inv is not None
    invocations = [c_inv, asm_inv]
    pairs = [(o, s) for o, s, _ in invocations]
    objects = ["src/a.o", "src/dyna.o"]
    raw_objects = ["./src/a.o", "./src/dyna.o"]
    return c_asm.CAsmLogContract(
        core_id=CORE,
        expected_c_compile_count={"arm64": 1},
        expected_asm_compile_count={"arm64": 1},
        expected_compile_pair_sha256={
            "arm64": c_only_compile_pair_sha256(pairs)
        },
        expected_compile_invocation_sha256={
            "arm64": c_only_compile_invocation_sha256(invocations)
        },
        expected_link_object_sha256={
            "arm64": c_only_link_object_sha256(objects)
        },
        build_artifact_name=ARTIFACT,
        expected_link_options={"arm64": ("-shared", "-lm")},
        source_commit=COMMIT,
        source_tree=TREE,
        expected_raw_link_object_sha256={
            "arm64": c_only_raw_link_object_sha256(raw_objects)
        },
    )


class CAsmProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = _build_contract()

    def _prove(self, log: str) -> bool:
        return c_asm.c_asm_log_proves_contract(
            log, CORE, "arm64", COMMIT, TREE, self.contract
        )

    def test_accepts_c_and_assembly_compiles_with_link(self) -> None:
        log = "\n".join([COMPILE_C, COMPILE_ASM, LINK]) + "\n"
        self.assertTrue(self._prove(log))

    def test_assembly_compiler_only_selects_source_by_stem(self) -> None:
        invocation = c_asm.c_asm_compile_invocation(
            shlex.split(COMPILE_ASM), {CC}
        )
        self.assertIsNotNone(invocation)
        assert invocation is not None
        output, source, _tokens = invocation
        self.assertEqual(("src/dyna.o", "src/dyna.S"), (output, source))

    def test_skips_compiler_version_banner_prose(self) -> None:
        # The banner names the compiler but is not a command: still proven.
        log = "\n".join([BANNER, COMPILE_C, COMPILE_ASM, LINK]) + "\n"
        self.assertTrue(self._prove(log))

    def test_fails_closed_on_unsafe_line_beginning_with_compiler(self) -> None:
        unsafe = f"{CC} -c -o src/a.o src/a.c && rm -rf /"
        log = "\n".join([unsafe, COMPILE_ASM, LINK]) + "\n"
        self.assertFalse(self._prove(log))

    def test_rejects_wrong_assembly_count(self) -> None:
        log = "\n".join([COMPILE_C, COMPILE_ASM, LINK]) + "\n"
        bumped = dataclasses.replace(
            self.contract, expected_asm_compile_count={"arm64": 2}
        )
        self.assertFalse(
            c_asm.c_asm_log_proves_contract(
                log, CORE, "arm64", COMMIT, TREE, bumped
            )
        )

    def test_rejects_link_object_not_compiled(self) -> None:
        # An object linked but never compiled breaks link==compile invariant.
        tampered_link = (
            f"{CC} -shared -o {ARTIFACT} ./src/a.o ./src/dyna.o "
            "./src/ghost.o -lm"
        )
        log = "\n".join([COMPILE_C, COMPILE_ASM, tampered_link]) + "\n"
        self.assertFalse(self._prove(log))

    def test_rejects_unknown_architecture_expectations(self) -> None:
        log = "\n".join([COMPILE_C, COMPILE_ASM, LINK]) + "\n"
        self.assertFalse(
            c_asm.c_asm_log_proves_contract(
                log, CORE, "armhf", COMMIT, TREE, self.contract
            )
        )


CXX = "aarch64-linux-gnu-g++"
COMPILE_CXX = f"{CXX} -c -o src/obj.o src/obj.cc -O2"


class CAsmMixedCxxProofTests(unittest.TestCase):
    """Cover the C/C++/assembly generalization (a C++ unit, C-driven link)."""

    def setUp(self) -> None:
        c_inv = c_asm.c_asm_compile_invocation(shlex.split(COMPILE_C), {CC})
        asm_inv = c_asm.c_asm_compile_invocation(shlex.split(COMPILE_ASM), {CC})
        cxx_inv = c_asm.c_asm_compile_invocation(
            shlex.split(COMPILE_CXX), {CC}, expected_cxx_compilers=frozenset({CXX})
        )
        assert c_inv is not None and asm_inv is not None and cxx_inv is not None
        self.assertEqual(("src/obj.o", "src/obj.cc"), cxx_inv[:2])
        invocations = [c_inv, asm_inv, cxx_inv]
        pairs = [(o, s) for o, s, _ in invocations]
        objects = ["src/a.o", "src/dyna.o", "src/obj.o"]
        link = f"{CC} -shared -o {ARTIFACT} ./src/a.o ./src/dyna.o ./src/obj.o -lm"
        self.link = link
        self.contract = c_asm.CAsmLogContract(
            core_id=CORE,
            expected_c_compile_count={"arm64": 1},
            expected_asm_compile_count={"arm64": 1},
            expected_cxx_compile_count={"arm64": 1},
            expected_compile_pair_sha256={
                "arm64": c_only_compile_pair_sha256(pairs)
            },
            expected_compile_invocation_sha256={
                "arm64": c_only_compile_invocation_sha256(invocations)
            },
            expected_link_object_sha256={
                "arm64": c_only_link_object_sha256(objects)
            },
            build_artifact_name=ARTIFACT,
            expected_link_options={"arm64": ("-shared", "-lm")},
            source_commit=COMMIT,
            source_tree=TREE,
            expected_link_language="c",
        )

    def test_accepts_c_cxx_and_assembly(self) -> None:
        log = (
            "\n".join([COMPILE_C, COMPILE_ASM, COMPILE_CXX, self.link]) + "\n"
        )
        self.assertTrue(
            c_asm.c_asm_log_proves_contract(
                log, CORE, "arm64", COMMIT, TREE, self.contract
            )
        )

    def test_rejects_missing_cxx_unit(self) -> None:
        # Drop the C++ compile: cxx count no longer matches, link object orphaned.
        log = "\n".join([COMPILE_C, COMPILE_ASM, self.link]) + "\n"
        self.assertFalse(
            c_asm.c_asm_log_proves_contract(
                log, CORE, "arm64", COMMIT, TREE, self.contract
            )
        )


class ForcedIncludeOperandTests(unittest.TestCase):
    """A -include/-isystem/-iquote operand must not be read as a source.

    Cores that bundle a dependency (e.g. tyrquake's libvorbis) compile with a
    forced-include header for symbol renaming; both the C-only and c_asm
    compile parsers must skip that operand.
    """

    def test_c_only_accepts_forced_include(self) -> None:
        from scripts.core_pipeline_lib.contracts.c_only import c_only_compile_invocation

        line = (
            f"{CC} -I. -include deps/vorbis/rename.h -isystem deps/inc "
            "-O2 -c -o deps/vorbis/bitrate.o deps/vorbis/bitrate.c"
        )
        invocation = c_only_compile_invocation(shlex.split(line), {CC})
        self.assertIsNotNone(invocation)
        assert invocation is not None
        self.assertEqual(
            ("deps/vorbis/bitrate.o", "deps/vorbis/bitrate.c"),
            invocation[:2],
        )

    def test_c_asm_accepts_forced_include(self) -> None:
        line = (
            f"{CC} -iquote deps/inc -include deps/vorbis/rename.h "
            "-c -o deps/vorbis/bitrate.o deps/vorbis/bitrate.c"
        )
        invocation = c_asm.c_asm_compile_invocation(shlex.split(line), {CC})
        self.assertIsNotNone(invocation)
        assert invocation is not None
        self.assertEqual(
            ("deps/vorbis/bitrate.o", "deps/vorbis/bitrate.c"),
            invocation[:2],
        )

    def test_dangling_file_operand_flag_is_rejected(self) -> None:
        from scripts.core_pipeline_lib.contracts.c_only import c_only_compile_invocation

        # -include immediately followed by another option is malformed.
        line = f"{CC} -include -O2 -c -o src/a.o src/a.c"
        self.assertIsNone(c_only_compile_invocation(shlex.split(line), {CC}))


if __name__ == "__main__":
    unittest.main()
