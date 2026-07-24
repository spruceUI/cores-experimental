#!/usr/bin/env python3

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError
import importlib.util
import io
from pathlib import Path
import unittest
from unittest import mock

from scripts.core_pipeline_lib.cli import (
    ParserConfig,
    ParserHandlers,
    build_parser as build_extracted_parser,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "core_pipeline.py"
SPEC = importlib.util.spec_from_file_location(
    "core_pipeline_cli_reference", MODULE_PATH
)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


COMMANDS = {
    "catalog-check",
    "audit-workflows",
    "import-golden",
    "validate-golden",
    "build",
    "build-core",
    "e2e",
    "promote",
    "derive-core-id",
    "compose-core-golden",
    "compose-pin-set",
    "validate-pin-set",
    "promote-release",
    "validate-release",
    "update-channel",
    "validate-channel",
    "plan-release",
    "release-matrix",
    "record-release-result",
    "seal-release",
}

EXPECTED_DESTINATIONS = {
    "catalog-check": set(),
    "audit-workflows": {"output"},
    "import-golden": {"core", "spruceos", "output", "allow_missing"},
    "validate-golden": {
        "golden",
        "spruceos",
        "verify_files",
        "verify_store",
    },
    "build": {"core", "arch", "output"},
    "build-core": {"runner_profile", "core", "run_id", "output_root"},
    "e2e": {
        "runner_profile",
        "core",
        "arch",
        "run_id",
        "output_root",
        "fail_fast",
    },
    "promote": {"golden", "record", "e2e_record"},
    "derive-core-id": {"core", "source_golden"},
    "compose-core-golden": {"core", "source_golden", "output"},
    "compose-pin-set": {
        "pin_id",
        "core",
        "source_golden",
        "output",
    },
    "validate-pin-set": {"pin_set", "verify_store", "verify_sources"},
    "promote-release": {"pin_set", "output"},
    "validate-release": {"pin_set", "release", "verify_store"},
    "update-channel": {
        "channel",
        "core",
        "target",
        "expect_absent",
        "expect_current",
    },
    "validate-channel": {"channel", "core"},
    "plan-release": {"candidate_id", "core", "scope", "output"},
    "release-matrix": {"plan"},
    "record-release-result": {"plan", "core", "e2e_record", "output_dir"},
    "seal-release": {
        "plan",
        "results_root",
        "runner_profile",
        "output_dir",
    },
}

EXPECTED_REQUIRED = {
    "catalog-check": set(),
    "audit-workflows": set(),
    "import-golden": {"core", "output"},
    "validate-golden": {"golden"},
    "build": {"core", "arch", "output"},
    "build-core": {"core"},
    "e2e": {"core"},
    "promote": {"golden", "record", "e2e_record"},
    "derive-core-id": {"core", "source_golden"},
    "compose-core-golden": {"core", "source_golden", "output"},
    "compose-pin-set": {"pin_id", "core", "source_golden", "output"},
    "validate-pin-set": {"pin_set"},
    "promote-release": {"pin_set", "output"},
    "validate-release": {"pin_set", "release"},
    "update-channel": {"channel", "core", "target"},
    "validate-channel": {"channel", "core"},
    "plan-release": {"candidate_id", "output"},
    "release-matrix": {"plan"},
    "record-release-result": {"plan", "core", "e2e_record", "output_dir"},
    "seal-release": {
        "plan",
        "results_root",
        "runner_profile",
        "output_dir",
    },
}


def parser_handlers() -> ParserHandlers:
    return ParserHandlers(
        catalog_check=pipeline.cmd_catalog_check,
        audit_workflows=pipeline.cmd_audit,
        import_golden=pipeline.cmd_import_golden,
        validate_golden=pipeline.cmd_validate_golden,
        build=pipeline.cmd_build,
        build_core=pipeline.cmd_build_core,
        e2e=pipeline.cmd_e2e,
        promote=pipeline.cmd_promote,
        derive_core_id=pipeline.cmd_derive_core_id,
        compose_core_golden=pipeline.cmd_compose_core_golden,
        compose_pin_set=pipeline.cmd_compose_pin_set,
        validate_pin_set=pipeline.cmd_validate_pin_set,
        promote_release=pipeline.cmd_promote_release,
        validate_release=pipeline.cmd_validate_release,
        update_channel=pipeline.cmd_update_channel,
        validate_channel=pipeline.cmd_validate_channel,
        plan_release=pipeline.cmd_plan_release,
        release_matrix=pipeline.cmd_release_matrix,
        record_release_result=pipeline.cmd_record_release_result,
        seal_release=pipeline.cmd_seal_release,
    )


def parser_config() -> ParserConfig:
    return ParserConfig(
        description=pipeline.__doc__,
        path_value=pipeline.path_value,
        default_catalog=pipeline.DEFAULT_CATALOG,
        default_runs=pipeline.DEFAULT_RUNS,
        default_spruceos=pipeline.ROOT.parent / "spruceOS",
        arch_choices=tuple(sorted(pipeline.ARCH_LAYOUT)),
        runner_profile_choices=("local", "github-actions", "github-actions-sim"),
        default_runner_profile="local",
        channel_choices=tuple(sorted(pipeline.CHANNEL_KINDS)),
        release_scope_choices=("canonical", "full-workflow-roster"),
    )


def subcommand_parsers(
    parser: argparse.ArgumentParser,
) -> dict[str, argparse.ArgumentParser]:
    subparser_actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(subparser_actions) != 1:
        raise AssertionError("parser must have exactly one subparser action")
    return dict(subparser_actions[0].choices)


def action_signature(action: argparse.Action) -> tuple[object, ...]:
    action_type = type(action)
    normalized_action_type = (
        action_type.__module__.removeprefix("scripts."),
        action_type.__qualname__,
    )
    choices = action.choices
    if isinstance(action, argparse._SubParsersAction):
        normalized_choices: object = tuple(choices) if choices is not None else None
    elif choices is None:
        normalized_choices = None
    else:
        normalized_choices = tuple(choices)
    return (
        normalized_action_type,
        tuple(action.option_strings),
        action.dest,
        action.nargs,
        action.const,
        action.default,
        action.required,
        normalized_choices,
        action.type,
        action.metavar,
        action.help,
    )


def parser_signature(parser: argparse.ArgumentParser) -> tuple[object, ...]:
    mutual_exclusion = tuple(
        (
            group.required,
            tuple(
                (tuple(action.option_strings), action.dest)
                for action in group._group_actions
            ),
        )
        for group in parser._mutually_exclusive_groups
    )
    children = subcommand_parsers(parser) if any(
        isinstance(action, argparse._SubParsersAction) for action in parser._actions
    ) else {}
    return (
        parser.prog,
        parser.description,
        parser.epilog,
        tuple(action_signature(action) for action in parser._actions),
        mutual_exclusion,
        dict(parser._defaults),
        tuple(
            (name, parser_signature(child))
            for name, child in sorted(children.items())
        ),
    )


class PipelineCliParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handlers = parser_handlers()
        self.config = parser_config()
        self.reference = pipeline.build_parser()
        self.extracted = build_extracted_parser(
            handlers=self.handlers,
            config=self.config,
        )

    def test_extracted_parser_has_complete_structural_and_help_parity(self) -> None:
        self.assertEqual(
            parser_signature(self.reference), parser_signature(self.extracted)
        )
        reference_commands = subcommand_parsers(self.reference)
        extracted_commands = subcommand_parsers(self.extracted)
        self.assertEqual(COMMANDS, set(reference_commands))
        self.assertEqual(set(reference_commands), set(extracted_commands))
        self.assertEqual(self.reference.format_help(), self.extracted.format_help())
        for command in sorted(COMMANDS):
            with self.subTest(command=command):
                self.assertEqual(
                    reference_commands[command].format_help(),
                    extracted_commands[command].format_help(),
                )

    def test_parser_matches_independent_public_command_contract(self) -> None:
        root_actions = {
            action.dest: action
            for action in self.extracted._actions
            if action.dest != "help"
        }
        self.assertEqual({"catalog", "command"}, set(root_actions))
        self.assertIs(root_actions["catalog"].type, pipeline.path_value)
        self.assertEqual(pipeline.DEFAULT_CATALOG, root_actions["catalog"].default)
        self.assertTrue(root_actions["command"].required)
        self.assertEqual(COMMANDS, set(root_actions["command"].choices))

        commands = subcommand_parsers(self.extracted)
        expected_handlers = {
            "catalog-check": pipeline.cmd_catalog_check,
            "audit-workflows": pipeline.cmd_audit,
            "import-golden": pipeline.cmd_import_golden,
            "validate-golden": pipeline.cmd_validate_golden,
            "build": pipeline.cmd_build,
            "build-core": pipeline.cmd_build_core,
            "e2e": pipeline.cmd_e2e,
            "promote": pipeline.cmd_promote,
            "derive-core-id": pipeline.cmd_derive_core_id,
            "compose-core-golden": pipeline.cmd_compose_core_golden,
            "compose-pin-set": pipeline.cmd_compose_pin_set,
            "validate-pin-set": pipeline.cmd_validate_pin_set,
            "promote-release": pipeline.cmd_promote_release,
            "validate-release": pipeline.cmd_validate_release,
            "update-channel": pipeline.cmd_update_channel,
            "validate-channel": pipeline.cmd_validate_channel,
            "plan-release": pipeline.cmd_plan_release,
            "release-matrix": pipeline.cmd_release_matrix,
            "record-release-result": pipeline.cmd_record_release_result,
            "seal-release": pipeline.cmd_seal_release,
        }
        for command in sorted(COMMANDS):
            with self.subTest(command=command):
                actions = {
                    action.dest: action
                    for action in commands[command]._actions
                    if action.dest != "help"
                }
                self.assertEqual(EXPECTED_DESTINATIONS[command], set(actions))
                self.assertEqual(
                    EXPECTED_REQUIRED[command],
                    {dest for dest, action in actions.items() if action.required},
                )
                self.assertIs(
                    expected_handlers[command], commands[command]._defaults["handler"]
                )

        build_actions = {
            action.dest: action for action in commands["build"]._actions
        }
        self.assertEqual(("arm64", "armhf"), tuple(build_actions["arch"].choices))
        build_core_actions = {
            action.dest: action for action in commands["build-core"]._actions
        }
        self.assertEqual(
            ("local", "github-actions", "github-actions-sim"),
            tuple(build_core_actions["runner_profile"].choices),
        )
        self.assertEqual("local", build_core_actions["runner_profile"].default)
        self.assertEqual(
            pipeline.DEFAULT_RUNS, build_core_actions["output_root"].default
        )
        e2e_actions = {
            action.dest: action for action in commands["e2e"]._actions
        }
        self.assertEqual(
            ("local", "github-actions", "github-actions-sim"),
            tuple(e2e_actions["runner_profile"].choices),
        )
        self.assertEqual("local", e2e_actions["runner_profile"].default)
        self.assertEqual(pipeline.DEFAULT_RUNS, e2e_actions["output_root"].default)
        for command in ("update-channel", "validate-channel"):
            channel_actions = {
                action.dest: action for action in commands[command]._actions
            }
            self.assertEqual(
                ("nightly", "pinned", "release"),
                tuple(channel_actions["channel"].choices),
            )
            self.assertTrue(channel_actions["core"].required)
        update_groups = commands["update-channel"]._mutually_exclusive_groups
        self.assertEqual(1, len(update_groups))
        self.assertTrue(update_groups[0].required)
        self.assertEqual(
            {"expect_absent", "expect_current"},
            {action.dest for action in update_groups[0]._group_actions},
        )
        plan_groups = commands["plan-release"]._mutually_exclusive_groups
        self.assertEqual(1, len(plan_groups))
        self.assertTrue(plan_groups[0].required)
        self.assertEqual(
            {"core", "scope"},
            {action.dest for action in plan_groups[0]._group_actions},
        )
        plan_actions = {
            action.dest: action for action in commands["plan-release"]._actions
        }
        self.assertEqual(
            ("canonical", "full-workflow-roster"),
            tuple(plan_actions["scope"].choices),
        )
        seal_actions = {
            action.dest: action for action in commands["seal-release"]._actions
        }
        self.assertEqual(
            ("local", "github-actions", "github-actions-sim"),
            tuple(seal_actions["runner_profile"].choices),
        )
        self.assertTrue(seal_actions["runner_profile"].required)

    def test_every_command_parses_to_the_same_namespace_and_handler(self) -> None:
        samples = {
            "catalog-check": [],
            "audit-workflows": ["--output", "./audit.json"],
            "import-golden": [
                "--core",
                "handy",
                "--spruceos",
                "./spruceos",
                "--output",
                "./golden.json",
                "--allow-missing",
            ],
            "validate-golden": [
                "--golden",
                "./golden.json",
                "--spruceos",
                "./spruceos",
                "--verify-files",
                "--verify-store",
            ],
            "build": ["--core", "handy", "--arch", "arm64", "--output", "./out"],
            "build-core": [
                "--runner-profile",
                "github-actions-sim",
                "--core",
                "handy",
                "--run-id",
                "actions-sim-build-core-parity",
                "--output-root",
                "./runs",
            ],
            "e2e": [
                "--runner-profile",
                "github-actions-sim",
                "--core",
                "handy",
                "--arch",
                "arm64",
                "--arch",
                "armhf",
                "--run-id",
                "actions-sim-cli-parity",
                "--output-root",
                "./runs",
                "--fail-fast",
            ],
            "promote": [
                "--golden",
                "./golden.json",
                "--record",
                "./build-record.json",
                "--e2e-record",
                "./e2e-record.json",
            ],
            "derive-core-id": [
                "--core",
                "handy",
                "--source-golden",
                "./golden.json",
            ],
            "compose-core-golden": [
                "--core",
                "handy",
                "--source-golden",
                "./golden.json",
                "--output",
                "./nightlies/handy/golden.json",
            ],
            "compose-pin-set": [
                "--pin-id",
                "candidate-1",
                "--core",
                "handy",
                "--source-golden",
                "./golden.json",
                "--output",
                "./pin.json",
            ],
            "validate-pin-set": [
                "--pin-set",
                "./pin.json",
                "--verify-store",
                "--verify-sources",
            ],
            "promote-release": [
                "--pin-set",
                "./pin.json",
                "--output",
                "./release",
            ],
            "validate-release": [
                "--pin-set",
                "./pin.json",
                "--release",
                "./release",
                "--verify-store",
            ],
            "update-channel": [
                "--channel",
                "nightly",
                "--core",
                "handy",
                "--target",
                "./pin.json",
                "--expect-absent",
            ],
            "validate-channel": ["--channel", "release", "--core", "handy"],
            "plan-release": [
                "--candidate-id",
                "release-canary-v1",
                "--core",
                "2048",
                "--core",
                "gambatte",
                "--output",
                "./release-plan.json",
            ],
            "release-matrix": ["--plan", "./release-plan.json"],
            "record-release-result": [
                "--plan",
                "./release-plan.json",
                "--core",
                "gambatte",
                "--e2e-record",
                "./runs/gambatte/e2e-record.json",
                "--output-dir",
                "./results/gambatte",
            ],
            "seal-release": [
                "--plan",
                "./release-plan.json",
                "--results-root",
                "./results",
                "--runner-profile",
                "github-actions-sim",
                "--output-dir",
                "./candidate",
            ],
        }

        for command, arguments in samples.items():
            argv = ["--catalog", "./catalog.json", command, *arguments]
            with self.subTest(command=command):
                reference_args = self.reference.parse_args(argv)
                extracted_args = self.extracted.parse_args(argv)
                self.assertEqual(vars(reference_args), vars(extracted_args))
                self.assertIs(reference_args.handler, extracted_args.handler)

    def test_import_golden_requires_core_and_output(self) -> None:
        incomplete = (
            ["import-golden", "--output", "./golden.json"],
            ["import-golden", "--core", "handy"],
        )
        for parser in (self.reference, self.extracted):
            for argv in incomplete:
                with self.subTest(parser=parser.prog, argv=argv), mock.patch(
                    "sys.stderr", new=io.StringIO()
                ), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_validate_golden_requires_explicit_input(self) -> None:
        for parser in (self.reference, self.extracted):
            with self.subTest(parser=parser.prog), mock.patch(
                "sys.stderr", new=io.StringIO()
            ), self.assertRaises(SystemExit):
                parser.parse_args(["validate-golden"])

    def test_channel_expectation_and_runner_profile_contracts_are_exact(self) -> None:
        reference_current = self.reference.parse_args(
            [
                "update-channel",
                "--channel",
                "pinned",
                "--core",
                "handy",
                "--target",
                "./pin.json",
                "--expect-current",
                "old-pin",
            ]
        )
        extracted_current = self.extracted.parse_args(
            [
                "update-channel",
                "--channel",
                "pinned",
                "--core",
                "handy",
                "--target",
                "./pin.json",
                "--expect-current",
                "old-pin",
            ]
        )
        self.assertEqual(vars(reference_current), vars(extracted_current))

        e2e_actions = {
            action.dest: action
            for action in subcommand_parsers(self.extracted)["e2e"]._actions
        }
        self.assertEqual(
            ("local", "github-actions", "github-actions-sim"),
            e2e_actions["runner_profile"].choices,
        )
        self.assertEqual("local", e2e_actions["runner_profile"].default)

    def test_mutating_cli_has_no_aggregate_or_parent_lineage_form(self) -> None:
        rejected = (
            [
                "update-channel",
                "--channel",
                "nightly",
                "--target",
                "./golden.json",
                "--expect-absent",
            ],
            [
                "compose-pin-set",
                "--pin-id",
                "fixture",
                "--core",
                "handy",
                "--source-golden",
                "./golden.json",
                "--parent-pin",
                "./parent.json",
                "--output",
                "./pin.json",
            ],
        )
        for parser in (self.reference, self.extracted):
            for argv in rejected:
                with self.subTest(parser=parser.prog, argv=argv), mock.patch(
                    "sys.stderr", new=io.StringIO()
                ), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_active_channel_validation_has_no_aggregate_form(self) -> None:
        argv = ["validate-channel", "--channel", "nightly"]
        for parser in (self.reference, self.extracted):
            with self.subTest(parser=parser.prog), mock.patch(
                "sys.stderr", new=io.StringIO()
            ), self.assertRaises(SystemExit):
                parser.parse_args(argv)

    def test_build_commands_require_exactly_one_nonrepeatable_core(self) -> None:
        rejected = (
            ["e2e"],
            ["e2e", "--core", "handy", "--core", "stella2014"],
            [
                "build-core",
                "--core",
                "handy",
                "--core",
                "stella2014",
            ],
        )
        for parser in (self.reference, self.extracted):
            for argv in rejected:
                with self.subTest(parser=parser.prog, argv=argv), mock.patch(
                    "sys.stderr", new=io.StringIO()
                ), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

            parsed = parser.parse_args(
                ["e2e", "--core", "handy", "--arch", "arm64", "--arch", "armhf"]
            )
            self.assertEqual("handy", parsed.core)
            self.assertEqual(["arm64", "armhf"], parsed.arch)

    def test_release_plan_requires_one_selector_and_unique_explicit_cores(self) -> None:
        rejected = (
            [
                "plan-release",
                "--candidate-id",
                "candidate-v1",
                "--output",
                "./plan.json",
            ],
            [
                "plan-release",
                "--candidate-id",
                "candidate-v1",
                "--core",
                "gambatte",
                "--core",
                "gambatte",
                "--output",
                "./plan.json",
            ],
            [
                "plan-release",
                "--candidate-id",
                "candidate-v1",
                "--core",
                "gambatte",
                "--scope",
                "canonical",
                "--output",
                "./plan.json",
            ],
            [
                "plan-release",
                "--candidate-id",
                "candidate-v1",
                "--all",
                "--output",
                "./plan.json",
            ],
        )
        for parser in (self.reference, self.extracted):
            for argv in rejected:
                with self.subTest(parser=parser.prog, argv=argv), mock.patch(
                    "sys.stderr", new=io.StringIO()
                ), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

            explicit = parser.parse_args(
                [
                    "plan-release",
                    "--candidate-id",
                    "candidate-v1",
                    "--core",
                    "2048",
                    "--core",
                    "gambatte",
                    "--output",
                    "./plan.json",
                ]
            )
            self.assertEqual(["2048", "gambatte"], explicit.core)
            self.assertIsNone(explicit.scope)

            scoped = parser.parse_args(
                [
                    "plan-release",
                    "--candidate-id",
                    "candidate-v1",
                    "--scope",
                    "full-workflow-roster",
                    "--output",
                    "./plan.json",
                ]
            )
            self.assertIsNone(scoped.core)
            self.assertEqual("full-workflow-roster", scoped.scope)

    def test_release_worker_and_seal_commands_require_all_inputs(self) -> None:
        rejected = (
            [
                "record-release-result",
                "--plan",
                "./plan.json",
                "--core",
                "gambatte",
                "--e2e-record",
                "./e2e-record.json",
            ],
            [
                "seal-release",
                "--plan",
                "./plan.json",
                "--results-root",
                "./results",
                "--output-dir",
                "./candidate",
            ],
            [
                "seal-release",
                "--plan",
                "./plan.json",
                "--results-root",
                "./results",
                "--runner-profile",
                "remote",
                "--output-dir",
                "./candidate",
            ],
        )
        for parser in (self.reference, self.extracted):
            for argv in rejected:
                with self.subTest(parser=parser.prog, argv=argv), mock.patch(
                    "sys.stderr", new=io.StringIO()
                ), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_entry_script_and_every_command_expose_help(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            pipeline.main(["--help"])
        self.assertEqual(0, raised.exception.code)
        self.assertIn("build-core", output.getvalue())

        for command in sorted(COMMANDS):
            with self.subTest(command=command):
                output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                    pipeline.main([command, "--help"])
                self.assertEqual(0, raised.exception.code)
                self.assertIn("usage:", output.getvalue())
                self.assertIn(command, output.getvalue())

    def test_run_creating_command_help_describes_individual_core_scope(self) -> None:
        for command in ("build-core", "e2e"):
            with self.subTest(command=command):
                output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                    pipeline.main([command, "--help"])
                self.assertEqual(0, raised.exception.code)
                self.assertIn("new individual-core run identity", output.getvalue())
                self.assertIn("one catalog core", output.getvalue())
        e2e_help = subcommand_parsers(self.extracted)["e2e"].format_help()
        self.assertIn("exactly one catalog core", e2e_help)
        self.assertIn("may not be", e2e_help)
        self.assertIn("repeated", e2e_help)

    def test_build_core_delegates_one_complete_catalog_core_to_e2e(self) -> None:
        args = argparse.Namespace(
            catalog=Path("catalog.json"),
            runner_profile="github-actions-sim",
            core="handy",
            run_id="actions-sim-handy-single",
            output_root=Path("runs"),
        )
        with mock.patch.object(pipeline, "cmd_e2e", return_value=7) as e2e:
            self.assertEqual(7, pipeline.cmd_build_core(args))
        delegated = e2e.call_args.args[0]
        self.assertEqual(
            {
                "catalog": Path("catalog.json"),
                "runner_profile": "github-actions-sim",
                "core": "handy",
                "arch": None,
                "run_id": "actions-sim-handy-single",
                "output_root": Path("runs"),
                "fail_fast": True,
            },
            vars(delegated),
        )

    def test_e2e_rejects_ambiguous_core_and_duplicate_architecture_selectors(self) -> None:
        catalog = {
            "cores": {
                "handy": {"targets": ["arm64", "armhf"]},
            }
        }
        with mock.patch.object(pipeline, "load_catalog", return_value=catalog):
            for core in (None, ["handy"], ["handy", "handy"]):
                with self.subTest(core=core), self.assertRaisesRegex(
                    pipeline.PipelineError, "E2E requires exactly one --core"
                ):
                    pipeline.cmd_e2e(
                        argparse.Namespace(
                            catalog=Path("catalog.json"),
                            core=core,
                            arch=None,
                        )
                    )
            with self.assertRaisesRegex(
                pipeline.PipelineError, "duplicate E2E architectures: arm64"
            ):
                pipeline.cmd_e2e(
                    argparse.Namespace(
                        catalog=Path("catalog.json"),
                        core="handy",
                        arch=["arm64", "arm64"],
                    )
                )

    def test_dependencies_are_immutable_and_reject_ambiguous_inputs(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.handlers.build = pipeline.cmd_e2e  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            self.config.default_catalog = Path("changed")  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "must be unique"):
            ParserConfig(
                description=None,
                path_value=pipeline.path_value,
                default_catalog=Path("catalog"),
                default_runs=Path("runs"),
                default_spruceos=Path("spruceos"),
                arch_choices=("arm64", "arm64"),
                runner_profile_choices=("local",),
                default_runner_profile="local",
                channel_choices=("nightly",),
                release_scope_choices=("canonical",),
            )
        with self.assertRaisesRegex(TypeError, "handler must be callable"):
            ParserHandlers(
                catalog_check=None,  # type: ignore[arg-type]
                audit_workflows=pipeline.cmd_audit,
                import_golden=pipeline.cmd_import_golden,
                validate_golden=pipeline.cmd_validate_golden,
                build=pipeline.cmd_build,
                build_core=pipeline.cmd_build_core,
                e2e=pipeline.cmd_e2e,
                promote=pipeline.cmd_promote,
                derive_core_id=pipeline.cmd_derive_core_id,
                compose_core_golden=pipeline.cmd_compose_core_golden,
                compose_pin_set=pipeline.cmd_compose_pin_set,
                validate_pin_set=pipeline.cmd_validate_pin_set,
                promote_release=pipeline.cmd_promote_release,
                validate_release=pipeline.cmd_validate_release,
                update_channel=pipeline.cmd_update_channel,
                validate_channel=pipeline.cmd_validate_channel,
                plan_release=pipeline.cmd_plan_release,
                release_matrix=pipeline.cmd_release_matrix,
                record_release_result=pipeline.cmd_record_release_result,
                seal_release=pipeline.cmd_seal_release,
            )


if __name__ == "__main__":
    unittest.main()
