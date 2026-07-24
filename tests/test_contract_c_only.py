from __future__ import annotations

from dataclasses import replace
import shlex
import unittest

from scripts import core_pipeline as pipeline  # Inserts scripts/ on sys.path.
from core_pipeline_lib.contracts import c_only


def build_c_only_fixture(
    architecture: str = "arm64",
) -> tuple[c_only.COnlyLogContract, str]:
    compiler = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }[architecture]
    compile_lines = (
        (
            f"{compiler} -c -osrc/alpha.o src/alpha.c "
            "-I ../../include -O2 -fPIC"
        ),
        f"{compiler} -c -o src/beta.o src/beta.c -O2 -fPIC",
    )
    invocations = [
        c_only.c_only_compile_invocation(shlex.split(line), {compiler})
        for line in compile_lines
    ]
    if any(invocation is None for invocation in invocations):
        raise AssertionError("failed to construct C-only compile fixture")
    typed_invocations = [
        invocation for invocation in invocations if invocation is not None
    ]
    pairs = [(output, source) for output, source, _tokens in typed_invocations]
    objects = [output for output, _source in pairs]
    base = c_only.COnlyLogContract(
        core_id="fixture",
        expected_compile_count=2,
        expected_compile_pair_sha256="0" * 64,
        expected_compile_invocation_sha256={architecture: "0" * 64},
        expected_link_object_sha256="0" * 64,
        build_artifact_name="fixture_libretro.so",
        expected_link_options=("-shared", "-Wl,--no-undefined", "-lm"),
        source_commit="a" * 40,
        source_tree="b" * 40,
    )
    link_line = " ".join(
        (
            compiler,
            "-o",
            base.build_artifact_name,
            *base.expected_link_options,
            *reversed(objects),
        )
    )
    link = c_only.c_only_link_command(
        shlex.split(link_line),
        {compiler},
        base,
        include_raw_sha256=True,
    )
    if link is None:
        raise AssertionError("failed to construct C-only link fixture")
    _observed, link_sha256, _archives, raw_link_sha256 = link
    contract = replace(
        base,
        expected_compile_pair_sha256=c_only.c_only_compile_pair_sha256(pairs),
        expected_compile_invocation_sha256={
            architecture: c_only.c_only_compile_invocation_sha256(
                typed_invocations
            )
        },
        expected_link_object_sha256=link_sha256,
        expected_raw_link_object_sha256=raw_link_sha256,
        expected_link_invocation_sha256={
            architecture: c_only.ordered_command_argv_sha256(
                shlex.split(link_line)
            )
        },
        expected_raw_compile_invocation_sha256={
            architecture: c_only.c_only_raw_compile_invocation_sha256(
                tuple(shlex.split(line)) for line in compile_lines
            )
        },
    )
    return contract, "\n".join((*compile_lines, link_line)) + "\n"


class COnlyContractHelperTests(unittest.TestCase):
    def test_compile_digest_helpers_canonicalize_equivalent_order_and_paths(
        self,
    ) -> None:
        self.assertEqual(
            "9b6e997d5d933e1b2725352062054277daab06496b2c1543a72b55f5a932a78b",
            c_only.c_only_compile_pair_sha256(
                [("b.o", "b.c"), ("a.o", "a.c")]
            ),
        )
        self.assertEqual(
            "ccf08720183f78ae271107bd0701ebe9072cd2efbe3e0f16d98f81038c51bb2c",
            c_only.c_only_compile_invocation_sha256(
                [
                    ("b.o", "b.c", ("gcc", "-o", "b.o", "-c", "b.c", "-O2")),
                    ("a.o", "a.c", ("gcc", "-o", "a.o", "-c", "a.c", "-O0")),
                ]
            ),
        )
        attached = c_only.c_only_compile_invocation(
            shlex.split("gcc -oa.o -c ./a.c -O2"), {"gcc"}
        )
        split = c_only.c_only_compile_invocation(
            shlex.split("gcc -o ./a.o -c a.c -O2"), {"gcc"}
        )
        self.assertEqual(attached, split)

    def test_compile_parser_binds_split_include_operands(self) -> None:
        compiler = "aarch64-linux-gnu-gcc"
        tokens = shlex.split(
            f"{compiler} -c -o ./src/alpha.o ./src/alpha.c "
            "-I ../../core -I../../libretro -O2"
        )
        self.assertEqual(
            (
                "src/alpha.o",
                "src/alpha.c",
                (
                    compiler,
                    "-c",
                    "-o",
                    "src/alpha.o",
                    "src/alpha.c",
                    "-I",
                    "../../core",
                    "-I../../libretro",
                    "-O2",
                ),
            ),
            c_only.c_only_compile_invocation(tokens, {compiler}),
        )

        rejected = (
            f"{compiler} -c -o src/alpha.o src/alpha.c -I",
            f"{compiler} -c -o src/alpha.o src/alpha.c -I -DVALUE=1",
            (
                f"{compiler} -c -o src/alpha.o src/alpha.c "
                "src/injected.c -I ../../core"
            ),
        )
        for command in rejected:
            with self.subTest(command=command):
                self.assertIsNone(
                    c_only.c_only_compile_invocation(
                        shlex.split(command), {compiler}
                    )
                )

    def test_compile_parser_admits_attached_wl_but_not_xlinker(self) -> None:
        compiler = "aarch64-linux-gnu-gcc"
        # -Wl,... is inert under -c (no link step) and is a single attached
        # token, so it is admitted and pinned verbatim (chimerasnes ships
        # -Wl,--gc-sections in CFLAGS).
        accepted = c_only.c_only_compile_invocation(
            shlex.split(
                f"{compiler} -c -osrc/alpha.o src/alpha.c "
                "-Wl,--gc-sections -O2"
            ),
            {compiler},
        )
        self.assertEqual(("src/alpha.o", "src/alpha.c"), accepted[:2])
        self.assertIn("-Wl,--gc-sections", accepted[2])
        # -Xlinker consumes a separate operand that could be mistaken for a
        # source, so it stays rejected.
        for command in (
            f"{compiler} -c -osrc/alpha.o src/alpha.c -Xlinker --gc-sections",
            f"{compiler} -c -osrc/alpha.o src/alpha.c -Xlinker=--gc-sections",
        ):
            with self.subTest(command=command):
                self.assertIsNone(
                    c_only.c_only_compile_invocation(
                        shlex.split(command), {compiler}
                    )
                )

    def test_compile_parser_requires_explicit_parent_path_aliases(self) -> None:
        compiler = "aarch64-linux-gnu-gcc"
        tokens = shlex.split(
            f"{compiler} -c -o../../core/alpha.o ../../core/alpha.c "
            "-I ../../core"
        )
        self.assertIsNone(
            c_only.c_only_compile_invocation(tokens, {compiler})
        )
        self.assertEqual(
            (
                "core/alpha.o",
                "core/alpha.c",
                (
                    compiler,
                    "-c",
                    "-o",
                    "core/alpha.o",
                    "core/alpha.c",
                    "-I",
                    "../../core",
                ),
            ),
            c_only.c_only_compile_invocation(
                tokens,
                {compiler},
                (("../../core/", "core/"),),
            ),
        )
        self.assertIsNone(
            c_only.c_only_compile_invocation(
                shlex.split(
                    f"{compiler} -c -o../../../core/alpha.o "
                    "../../../core/alpha.c -I ../../core"
                ),
                {compiler},
                (("../../core/", "core/"),),
            )
        )

    def test_sanitized_prelude_clears_native_build_environment(self) -> None:
        prelude = pipeline.sanitized_shell_prelude()
        unset_line = next(
            line for line in prelude.splitlines() if line.startswith("unset ")
        )
        for name in ("GIT_VERSION", "MAKE", "MAKEFLAGS", "MFLAGS"):
            self.assertIn(f" {name} ", f" {unset_line} ")

    def test_neutral_proof_accepts_only_its_exact_compile_and_link_set(self) -> None:
        contract, log = build_c_only_fixture()
        arguments = (
            "fixture",
            "arm64",
            contract.source_commit,
            contract.source_tree,
            contract,
        )
        self.assertTrue(c_only.c_only_log_proves_contract(log, *arguments))
        mutations = (
            ("missing-compile", "\n".join(log.splitlines()[1:]) + "\n"),
            ("duplicate-compile", log.splitlines()[0] + "\n" + log),
            ("extra-link-option", log.replace(" -shared ", " -shared -pthread ")),
            ("response-file", log.replace(" -O2", " @compile.rsp -O2", 1)),
            ("language-switch", log.replace(" -O2", " -x c -O2", 1)),
            ("shell-syntax", log.replace(" -O2", " $(false) -O2", 1)),
            ("cxx", log.replace("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++", 1)),
            (
                "raw-link-spelling",
                log.replace(
                    " src/beta.o src/alpha.o",
                    " ./src/beta.o src/alpha.o",
                ),
            ),
            (
                "link-order",
                log.replace(
                    " src/beta.o src/alpha.o",
                    " src/alpha.o src/beta.o",
                ),
            ),
            ("fatal", log + "fatal: synthetic failure\n"),
        )
        for label, changed in mutations:
            with self.subTest(mutation=label):
                self.assertFalse(
                    c_only.c_only_log_proves_contract(changed, *arguments)
                )

    def test_raw_link_binding_is_opt_in_and_default_shape_is_stable(self) -> None:
        contract, log = build_c_only_fixture()
        legacy_contract = replace(
            contract,
            expected_raw_link_object_sha256=None,
            expected_link_invocation_sha256=None,
            expected_raw_compile_invocation_sha256=None,
        )
        changed = log.replace(
            " src/beta.o src/alpha.o",
            " ./src/beta.o src/alpha.o",
        )
        self.assertTrue(
            c_only.c_only_log_proves_contract(
                changed,
                legacy_contract.core_id,
                "arm64",
                legacy_contract.source_commit,
                legacy_contract.source_tree,
                legacy_contract,
            )
        )

        link_tokens = shlex.split(log.splitlines()[-1])
        result = c_only.c_only_link_command(
            link_tokens,
            {link_tokens[0]},
            legacy_contract,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(3, len(result))

        raw_compile_changed = log.replace(
            "-osrc/alpha.o src/alpha.c",
            "-o./src/alpha.o ./src/alpha.c",
            1,
        )
        self.assertFalse(
            c_only.c_only_log_proves_contract(
                raw_compile_changed,
                contract.core_id,
                "arm64",
                contract.source_commit,
                contract.source_tree,
                contract,
            )
        )
        self.assertTrue(
            c_only.c_only_log_proves_contract(
                raw_compile_changed,
                legacy_contract.core_id,
                "arm64",
                legacy_contract.source_commit,
                legacy_contract.source_tree,
                legacy_contract,
            )
        )

    def test_neutral_proof_rejects_wrong_identity_and_architecture(self) -> None:
        contract, log = build_c_only_fixture()
        self.assertFalse(
            c_only.c_only_log_proves_contract(
                log,
                "other",
                "arm64",
                contract.source_commit,
                contract.source_tree,
                contract,
            )
        )
        self.assertFalse(
            c_only.c_only_log_proves_contract(
                log,
                contract.core_id,
                "arm64",
                "0" * 40,
                contract.source_tree,
                contract,
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            c_only.c_only_log_proves_contract(
                log,
                contract.core_id,
                "mips",
                contract.source_commit,
                contract.source_tree,
                contract,
            )


if __name__ == "__main__":
    unittest.main()
