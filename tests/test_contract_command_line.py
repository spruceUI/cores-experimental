from __future__ import annotations

import unittest

from scripts.core_pipeline_lib.contracts.command_line import (
    command_line_is_lexically_safe,
    command_uses_response_file,
    normalized_log_path,
    ordered_command_argv_sha256,
    output_option,
    semantic_log_path,
)


class ContractCommandLineTests(unittest.TestCase):
    def test_ordered_argv_hash_binds_every_token_and_position(self) -> None:
        argv = ["aarch64-linux-gnu-g++", "-o", "core.so", "core.o"]
        self.assertEqual(
            "974ac5c89422ad60cd89583e36328d5dc98ce13dd0e8c8e2f3985c2dde35e719",
            ordered_command_argv_sha256(argv),
        )
        self.assertNotEqual(
            ordered_command_argv_sha256(argv),
            ordered_command_argv_sha256([*reversed(argv)]),
        )
        for malformed in (None, [], ["cc", 1], ["cc", "café.c"]):
            with self.subTest(malformed=malformed):
                self.assertIsNone(ordered_command_argv_sha256(malformed))

    def test_normalized_log_path_is_relative_and_exact(self) -> None:
        self.assertEqual("src/core.o", normalized_log_path("./src/core.o", ".o"))
        for value in (
            "/src/core.o",
            "src/../core.o",
            "src//core.o",
            "src/core obj.o",
            "src/core.c",
        ):
            with self.subTest(value=value):
                self.assertIsNone(normalized_log_path(value, ".o"))

    def test_reviewed_alias_maps_absolute_and_subdir_paths(self) -> None:
        # #5: a core building to an absolute OBJDIR is mapped to a contained
        # relative path by a reviewed alias applied before the ``/`` guard.
        abs_alias = (
            ("/libretro-super/libretro-chimerasnes/source/", "source/"),
        )
        self.assertEqual(
            "source/apu.o",
            semantic_log_path(
                "/libretro-super/libretro-chimerasnes/source/apu.o",
                ".o",
                abs_alias,
            ),
        )
        # #4: a link artifact emitted into a subdirectory maps to the bare name.
        subdir_alias = (("obj/player/", ""),)
        self.assertEqual(
            "lutro_libretro.so",
            semantic_log_path(
                "obj/player/lutro_libretro.so", ".so", subdir_alias
            ),
        )

    def test_alias_never_relaxes_containment(self) -> None:
        abs_alias = (
            ("/libretro-super/libretro-chimerasnes/source/", "source/"),
        )
        subdir_alias = (("obj/player/", ""),)
        for value, suffix, aliases in (
            # traversal that survives the alias substitution
            (
                "/libretro-super/libretro-chimerasnes/source/../../etc/x.o",
                ".o",
                abs_alias,
            ),
            ("obj/player/../../etc/evil.so", ".so", subdir_alias),
            # an absolute path the alias does not cover stays rejected
            ("/etc/passwd.o", ".o", abs_alias),
            # without any alias, absolute and ``..`` are still rejected
            ("/libretro-super/x.o", ".o", ()),
            ("../../x.o", ".o", ()),
        ):
            with self.subTest(value=value):
                self.assertIsNone(semantic_log_path(value, suffix, aliases))

    def test_output_option_accepts_only_one_split_or_attached_value(self) -> None:
        self.assertEqual(
            ("core.o", frozenset({2, 3})),
            output_option(["cc", "-c", "-o", "core.o", "core.c"]),
        )
        self.assertEqual(
            ("core.o", frozenset({2})),
            output_option(["cc", "-c", "-ocore.o", "core.c"]),
        )
        self.assertIsNone(output_option(["cc", "-o", "one.o", "-otwo.o"]))
        self.assertIsNone(output_option(["cc", "-o", "-shared"]))

    def test_shell_and_response_file_checks_fail_closed(self) -> None:
        self.assertTrue(command_uses_response_file(["cc", "@objects.rsp"]))
        self.assertFalse(command_uses_response_file(["cc", "object.o"]))
        self.assertTrue(command_line_is_lexically_safe("cc -c core.c -ocore.o"))
        for line in ("cc -c core.c; touch bad", "cc $(command)", "cc\nnext"):
            with self.subTest(line=line):
                self.assertFalse(command_line_is_lexically_safe(line))


if __name__ == "__main__":
    unittest.main()
