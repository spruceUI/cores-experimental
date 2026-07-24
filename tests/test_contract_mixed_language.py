from __future__ import annotations

from dataclasses import replace
import shlex
import unittest

from scripts import core_pipeline as pipeline  # Inserts scripts/ on sys.path.
from core_pipeline_lib.contracts import mixed_language
from core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)


class MixedLanguageContractHelperTests(unittest.TestCase):
    def test_cc_suffix_is_a_cxx_compile(self) -> None:
        compiler = "aarch64-linux-gnu-g++"
        invocation = mixed_language.mixed_language_compile_invocation(
            shlex.split(f"{compiler} -c -osrc/unit.o src/unit.cc -O2"),
            {compiler},
            {compiler},
        )
        self.assertIsNotNone(invocation)
        assert invocation is not None
        self.assertEqual(("src/unit.o", "src/unit.cc", "cxx"), invocation[:3])

    def _contract_and_log(
        self,
    ) -> tuple[mixed_language.MixedLanguageLogContract, str]:
        compiler = "aarch64-linux-gnu-gcc"
        cxx_compiler = "aarch64-linux-gnu-g++"
        compile_lines = (
            f"{compiler} -c -oc/unit.o c/unit.c -O2 -fPIC",
            f"{cxx_compiler} -c -ocxx/unit.o cxx/unit.cpp -O2 -fPIC",
        )
        invocations = [
            mixed_language.mixed_language_compile_invocation(
                shlex.split(line),
                {compiler, cxx_compiler},
                {cxx_compiler},
            )
            for line in compile_lines
        ]
        self.assertNotIn(None, invocations)
        typed_invocations = [
            invocation for invocation in invocations if invocation is not None
        ]
        pairs = [
            (output, source)
            for output, source, _language, *_raw in typed_invocations
        ]
        objects = [output for output, _source in pairs]
        base = mixed_language.MixedLanguageLogContract(
            core_id="fixture",
            expected_compile_count=2,
            expected_language_counts={"c": 1, "cxx": 1},
            expected_compile_pair_sha256="0" * 64,
            expected_compile_invocation_sha256={"arm64": "0" * 64},
            expected_link_object_sha256="0" * 64,
            expected_raw_link_object_sha256="0" * 64,
            build_artifact_name="fixture_libretro.so",
            expected_link_options=("-shared", "-Wl,--no-undefined"),
            source_commit="a" * 40,
            source_tree="b" * 40,
        )
        link_line = " ".join(
            (
                cxx_compiler,
                "-o",
                base.build_artifact_name,
                *base.expected_link_options,
                *[f"./{path}" for path in reversed(objects)],
            )
        )
        link = mixed_language.mixed_language_link_command(
            shlex.split(link_line),
            {cxx_compiler},
            base,
            include_raw_sha256=True,
        )
        self.assertIsNotNone(link)
        assert link is not None
        _observed, link_sha256, raw_link_sha256 = link
        contract = replace(
            base,
            expected_compile_pair_sha256=(
                mixed_language.mixed_language_compile_pair_sha256(pairs)
            ),
            expected_compile_invocation_sha256={
                "arm64": (
                    mixed_language.mixed_language_compile_invocation_sha256(
                        typed_invocations
                    )
                )
            },
            expected_link_object_sha256=link_sha256,
            expected_raw_link_object_sha256=raw_link_sha256,
        )
        return contract, "\n".join((*compile_lines, link_line)) + "\n"

    def test_neutral_proof_accepts_only_its_exact_compile_and_link_set(self) -> None:
        contract, log = self._contract_and_log()
        arguments = (
            "fixture",
            "arm64",
            contract.source_commit,
            contract.source_tree,
            contract,
        )
        self.assertTrue(
            mixed_language.mixed_language_log_proves_contract(log, *arguments)
        )
        for label, changed in (
            ("missing-compile", "\n".join(log.splitlines()[1:]) + "\n"),
            ("extra-link-option", log.replace(" -shared ", " -shared -lm ")),
            ("response-file", log.replace(" -O2", " @compile.rsp -O2", 1)),
            ("shell-syntax", log.replace(" -O2", " $(false) -O2", 1)),
        ):
            with self.subTest(mutation=label):
                self.assertFalse(
                    mixed_language.mixed_language_log_proves_contract(
                        changed, *arguments
                    )
                )

    def test_optional_ordered_link_hash_rejects_object_reordering(self) -> None:
        contract, log = self._contract_and_log()
        lines = log.splitlines()
        link_tokens = shlex.split(lines[-1])
        ordered_digest = ordered_command_argv_sha256(link_tokens)
        self.assertIsNotNone(ordered_digest)
        ordered_contract = replace(
            contract,
            expected_ordered_link_argv_sha256={"arm64": ordered_digest},
        )
        arguments = (
            ordered_contract.core_id,
            "arm64",
            ordered_contract.source_commit,
            ordered_contract.source_tree,
            ordered_contract,
        )
        self.assertTrue(
            mixed_language.mixed_language_log_proves_contract(log, *arguments)
        )
        missing_arch_contract = replace(
            ordered_contract,
            expected_ordered_link_argv_sha256={"armhf": ordered_digest},
        )
        self.assertFalse(
            mixed_language.mixed_language_log_proves_contract(
                log,
                missing_arch_contract.core_id,
                "arm64",
                missing_arch_contract.source_commit,
                missing_arch_contract.source_tree,
                missing_arch_contract,
            )
        )
        object_indexes = [
            index
            for index, token in enumerate(link_tokens)
            if token.endswith(".o")
        ]
        self.assertGreaterEqual(len(object_indexes), 2)
        first, second = object_indexes[:2]
        link_tokens[first], link_tokens[second] = (
            link_tokens[second],
            link_tokens[first],
        )
        lines[-1] = " ".join(link_tokens)
        reordered_log = "\n".join(lines) + "\n"
        self.assertFalse(
            mixed_language.mixed_language_log_proves_contract(
                reordered_log, *arguments
            )
        )

    def test_neutral_proof_rejects_wrong_core_source_and_architecture(self) -> None:
        contract, log = self._contract_and_log()
        self.assertFalse(
            mixed_language.mixed_language_log_proves_contract(
                log,
                "other",
                "arm64",
                contract.source_commit,
                contract.source_tree,
                contract,
            )
        )
        self.assertFalse(
            mixed_language.mixed_language_log_proves_contract(
                log,
                contract.core_id,
                "arm64",
                "0" * 40,
                contract.source_tree,
                contract,
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            mixed_language.mixed_language_log_proves_contract(
                log,
                contract.core_id,
                "mips",
                contract.source_commit,
                contract.source_tree,
                contract,
            )

    def test_c_linking_is_explicit_and_cxx_remains_the_default(self) -> None:
        contract, log = self._contract_and_log()
        legacy_aliases = (("upstream/../shared/", "shared/"),)
        legacy_positional = mixed_language.MixedLanguageLogContract(
            contract.core_id,
            contract.expected_compile_count,
            contract.expected_language_counts,
            contract.expected_compile_pair_sha256,
            contract.expected_compile_invocation_sha256,
            contract.expected_link_object_sha256,
            contract.expected_raw_link_object_sha256,
            contract.build_artifact_name,
            contract.expected_link_options,
            contract.source_commit,
            contract.source_tree,
            legacy_aliases,
        )
        self.assertEqual(legacy_aliases, legacy_positional.semantic_path_aliases)
        self.assertEqual("cxx", legacy_positional.expected_link_language)
        arguments = (
            contract.core_id,
            "arm64",
            contract.source_commit,
            contract.source_tree,
        )
        self.assertEqual("cxx", contract.expected_link_language)
        self.assertTrue(
            mixed_language.mixed_language_log_proves_contract(
                log, *arguments, contract
            )
        )

        lines = log.splitlines()
        self.assertTrue(lines[-1].startswith("aarch64-linux-gnu-g++ "))
        lines[-1] = lines[-1].replace(
            "aarch64-linux-gnu-g++ ",
            "aarch64-linux-gnu-gcc ",
            1,
        )
        c_link_log = "\n".join(lines) + "\n"
        c_link_contract = replace(contract, expected_link_language="c")
        self.assertTrue(
            mixed_language.mixed_language_log_proves_contract(
                c_link_log, *arguments, c_link_contract
            )
        )
        self.assertFalse(
            mixed_language.mixed_language_log_proves_contract(
                log, *arguments, c_link_contract
            )
        )
        self.assertFalse(
            mixed_language.mixed_language_log_proves_contract(
                c_link_log,
                *arguments,
                replace(c_link_contract, expected_link_language="invalid"),
            )
        )

    def test_semantic_path_aliases_are_explicit_and_fail_closed(self) -> None:
        alias = (("upstream/../shared/", "shared/"),)
        self.assertEqual(
            "shared/unit.o",
            mixed_language.mixed_language_semantic_log_path(
                "upstream/../shared/unit.o", ".o", alias
            ),
        )
        self.assertEqual(
            "shared/unit.o",
            mixed_language.mixed_language_semantic_log_path(
                "./shared/unit.o", ".o", alias
            ),
        )
        for path in (
            "upstream/../other/unit.o",
            "upstream/../shared/../unit.o",
            "/shared/unit.o",
            "shared//unit.o",
        ):
            with self.subTest(path=path):
                self.assertIsNone(
                    mixed_language.mixed_language_semantic_log_path(
                        path, ".o", alias
                    )
                )


if __name__ == "__main__":
    unittest.main()
