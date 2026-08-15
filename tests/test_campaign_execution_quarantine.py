from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stderr
import inspect
import io
from pathlib import Path
import unittest

from scripts.core_pipeline_lib.campaign import cli, workflow
from scripts.core_pipeline_lib.checks import CHECK_DEFINITIONS


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "docs" / "campaign-execution-quarantine.md"
PRODUCTION_PACKAGES = (
    ROOT / "scripts" / "core_pipeline_lib" / "campaign",
    ROOT / "scripts" / "core_pipeline_lib" / "checks",
)
ALLOWED_EXECUTION_CALLS = {
    "scripts/core_pipeline_lib/checks/service.py": frozenset(
        {"execution call: subprocess.run"}
    ),
}

EXPECTED_CLI_OPTIONS = {
    "check": frozenset({"--process-receipt-ref"}),
    "stage": frozenset({"--process-receipt-ref"}),
    "commit": frozenset({"--staged-receipt"}),
    "verify": frozenset({"--state-root"}),
}
EXPECTED_WORKFLOW_PARAMETERS = {
    "predict_transition": ("store",),
    "check_transition": ("store", "process_receipt_ref", "clock"),
    "stage_transition": ("store", "process_receipt_ref", "clock"),
    "commit_transition": ("store", "staged_receipt_ref", "clock"),
    "verify_transition": ("store", "state_root_ref"),
}

FORBIDDEN_IMPORT_ROOTS = frozenset({"importlib", "runpy", "zipimport"})
FORBIDDEN_EXACT_CALLS = frozenset(
    {
        "__import__",
        "compile",
        "eval",
        "exec",
        "importlib.import_module",
        "importlib.machinery.SourceFileLoader",
        "importlib.machinery.SourcelessFileLoader",
        "importlib.util.module_from_spec",
        "importlib.util.spec_from_file_location",
        "os.popen",
        "os.system",
        "runpy.run_module",
        "runpy.run_path",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.run",
    }
)
FORBIDDEN_CALL_SUFFIXES = (".exec_module", ".load_module")
FORBIDDEN_CALL_PREFIXES = ("os.exec", "os.spawn")
EXECUTABLE_COMPONENTS = frozenset(
    {
        "adapter",
        "executable",
        "generator",
        "loader",
        "module",
        "python",
        "script",
        "shell",
    }
)


def _qualified_name(node: ast.expr, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value, aliases)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _import_aliases(tree: ast.AST) -> tuple[dict[str, str], tuple[str, ...]]:
    aliases: dict[str, str] = {}
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                imports.append(item.name)
                binding = item.asname or item.name.split(".", 1)[0]
                aliases[binding] = item.name if item.asname else binding
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
            for item in node.names:
                binding = item.asname or item.name
                aliases[binding] = f"{module}.{item.name}" if module else item.name
    return aliases, tuple(imports)


def _string_fragments(node: ast.AST) -> tuple[str, ...]:
    return tuple(
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and type(item.value) is str
    )


def _names_executable_code(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(component in normalized for component in EXECUTABLE_COMPONENTS)


def _scan_tree(tree: ast.AST) -> tuple[str, ...]:
    aliases, imports = _import_aliases(tree)
    violations: set[str] = set()

    for imported in imports:
        root = imported.split(".", 1)[0]
        if root in FORBIDDEN_IMPORT_ROOTS:
            violations.add(f"dynamic import module: {imported}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = _qualified_name(node.func, aliases)
            if (
                called in FORBIDDEN_EXACT_CALLS
                or called.endswith(FORBIDDEN_CALL_SUFFIXES)
                or called.startswith(FORBIDDEN_CALL_PREFIXES)
            ):
                violations.add(f"execution call: {called}")

        if isinstance(node, ast.Constant) and type(node.value) is str:
            normalized = node.value.replace("\\", "/")
            if ".local-e2e" in normalized and ".py" in normalized:
                violations.add("held Python path literal")
        elif isinstance(node, (ast.BinOp, ast.JoinedStr)):
            combined = "/".join(_string_fragments(node)).replace("\\", "/")
            if ".local-e2e" in combined and ".py" in combined:
                violations.add("constructed held Python path")

    return tuple(sorted(violations))


def _scan_source(source: str) -> tuple[str, ...]:
    return _scan_tree(ast.parse(source))


def _production_sources() -> tuple[Path, ...]:
    return tuple(
        path
        for package in PRODUCTION_PACKAGES
        for path in sorted(package.rglob("*.py"))
    )


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    actions = tuple(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    if len(actions) != 1:
        raise AssertionError("campaign CLI must have one exact subparser action")
    return actions[0].choices


class QuarantineDetectorTests(unittest.TestCase):
    def test_detector_rejects_dynamic_loading_and_execution_aliases(self) -> None:
        sources = {
            "builtin-exec": "exec(payload)",
            "builtin-compile": "compile(payload, name, 'exec')",
            "builtin-import": "__import__(module_name)",
            "importlib-alias": (
                "import importlib as loader\n"
                "loader.import_module(module_name)\n"
            ),
            "from-import-alias": (
                "from importlib.util import spec_from_file_location as load\n"
                "load(module_name, path)\n"
            ),
            "runpy": "import runpy\nrunpy.run_path(path)\n",
            "source-loader": (
                "from importlib.machinery import SourceFileLoader as Loader\n"
                "Loader(module_name, path).load_module()\n"
            ),
            "exec-module": "loader.exec_module(module)",
            "subprocess": "import subprocess\nsubprocess.run(argv)\n",
            "os-system": "import os\nos.system(command)\n",
        }
        for label, source in sources.items():
            with self.subTest(label=label):
                self.assertTrue(_scan_source(source))

    def test_detector_rejects_literal_and_constructed_held_python_paths(self) -> None:
        sources = {
            "literal": 'path = ".local-e2e/campaigns/held.py"',
            "path-parts": 'path = root / ".local-e2e" / "held.py"',
            "formatted": 'path = f".local-e2e/campaigns/{name}.py"',
        }
        for label, source in sources.items():
            with self.subTest(label=label):
                self.assertTrue(_scan_source(source))

    def test_detector_allows_inert_non_python_evidence_reads(self) -> None:
        source = (
            "from pathlib import Path\n"
            "def read_evidence(root: Path) -> bytes:\n"
            "    return (root / '.local-e2e' / 'evidence.json').read_bytes()\n"
        )
        self.assertEqual((), _scan_source(source))


class CampaignExecutionQuarantineTests(unittest.TestCase):
    def test_policy_pins_inventory_and_evidence_only_rule(self) -> None:
        policy = " ".join(POLICY_PATH.read_text(encoding="utf-8").split())
        required = (
            "77 ignored historical Python artifacts",
            "Preserve them in place",
            "evidence-only",
            "must never",
            "exactly `check`, `stage`, `commit`, and `verify`",
            "without reading `.local-e2e/`",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, policy)

    def test_tracked_campaign_and_check_sources_are_execution_quarantined(self) -> None:
        violations: list[str] = []
        for path in _production_sources():
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            actual = frozenset(_scan_tree(tree))
            allowed = ALLOWED_EXECUTION_CALLS.get(relative, frozenset())
            violations.extend(
                f"{relative}: {item}" for item in sorted(actual - allowed)
            )
            violations.extend(
                f"{relative}: stale execution allowlist: {item}"
                for item in sorted(allowed - actual)
            )
        self.assertEqual([], violations)

    def test_reviewed_check_process_service_is_exactly_no_shell(self) -> None:
        path = ROOT / "scripts" / "core_pipeline_lib" / "checks" / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases, _imports = _import_aliases(tree)
        calls = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _qualified_name(node.func, aliases) == "subprocess.run"
        )
        self.assertEqual(1, len(calls))
        shell_keywords = tuple(
            keyword.value
            for keyword in calls[0].keywords
            if keyword.arg == "shell"
        )
        self.assertEqual(1, len(shell_keywords))
        self.assertIsInstance(shell_keywords[0], ast.Constant)
        self.assertIs(shell_keywords[0].value, False)

    def test_cli_exposes_only_the_four_evidence_reference_boundaries(self) -> None:
        parsers = _subparsers(cli.build_parser())
        self.assertEqual(tuple(EXPECTED_CLI_OPTIONS), tuple(parsers))
        for verb, expected in EXPECTED_CLI_OPTIONS.items():
            options = frozenset(
                option
                for action in parsers[verb]._actions
                for option in action.option_strings
                if option not in {"-h", "--help"}
            )
            with self.subTest(verb=verb):
                self.assertEqual(expected, options)
                self.assertTrue(
                    all(not _names_executable_code(option) for option in options)
                )

    def test_cli_rejects_executable_path_options(self) -> None:
        parser = cli.build_parser()
        for option in (
            "--adapter-path",
            "--executable",
            "--generator",
            "--generator-path",
            "--loader",
            "--module",
            "--module-path",
            "--python",
            "--script",
            "--script-path",
            "--shell",
        ):
            with self.subTest(option=option), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args(("check", option, ".local-e2e/held.py"))

    def test_public_workflow_signatures_accept_no_executable_path_seam(self) -> None:
        self.assertEqual(
            frozenset(EXPECTED_WORKFLOW_PARAMETERS),
            frozenset(
                name
                for name in workflow.__all__
                if name.endswith("_transition")
            ),
        )
        for name, expected in EXPECTED_WORKFLOW_PARAMETERS.items():
            parameters = tuple(inspect.signature(getattr(workflow, name)).parameters)
            with self.subTest(name=name):
                self.assertEqual(expected, parameters)
                self.assertTrue(
                    all(not _names_executable_code(item) for item in parameters)
                )

    def test_check_parameters_cannot_select_executable_code(self) -> None:
        violations: list[str] = []
        for definition in CHECK_DEFINITIONS:
            for token in definition.argv_prefix:
                normalized = token.replace("\\", "/")
                if ".local-e2e" in normalized and ".py" in normalized:
                    violations.append(
                        f"{definition.check_id}: held Python argv token {token!r}"
                    )
            for parameter in definition.parameters:
                if _names_executable_code(parameter.name) or _names_executable_code(
                    parameter.flag
                ):
                    violations.append(
                        f"{definition.check_id}: executable parameter "
                        f"{parameter.name}/{parameter.flag}"
                    )
                if not definition.argv_prefix:
                    violations.append(
                        f"{definition.check_id}: parameter without fixed argv prefix"
                    )
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
