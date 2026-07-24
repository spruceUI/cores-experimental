from __future__ import annotations

import unittest

from scripts.core_pipeline_lib.contracts.compiler import (
    COMPILER_COMMAND_RE,
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)


class ContractCompilerTests(unittest.TestCase):
    def test_target_compiler_sets_are_exact(self) -> None:
        self.assertEqual({"arm64", "armhf"}, set(TARGET_COMPILERS))
        for arch, cxx_compilers in TARGET_CXX_COMPILERS.items():
            self.assertTrue(cxx_compilers < TARGET_COMPILERS[arch])
            self.assertTrue(
                all(COMPILER_COMMAND_RE.fullmatch(item) for item in TARGET_COMPILERS[arch])
            )

    def test_log_discovery_handles_literal_and_shell_escaped_names(self) -> None:
        compilers = TARGET_COMPILERS["arm64"]
        self.assertTrue(
            line_may_name_target_compiler(
                "aarch64-linux-gnu-gcc -c source.c", compilers
            )
        )
        self.assertTrue(
            line_may_name_target_compiler(
                "aarch64-linux-gnu-'g'cc -c source.c", compilers
            )
        )
        self.assertFalse(line_may_name_target_compiler("cc -c source.c", compilers))


if __name__ == "__main__":
    unittest.main()
