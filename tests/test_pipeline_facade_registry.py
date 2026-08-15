"""Structural checks for the declarative launcher facade registry."""

from __future__ import annotations

import ast
import inspect
from collections import Counter
from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline


ROOT = Path(__file__).resolve().parents[1]


def _assigned_expressions(tree: ast.AST) -> dict[str, ast.expr]:
    """Return named expressions used to resolve dynamic loader paths."""

    assignments: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = value
    return assignments


def _string_literals(
    node: ast.AST,
    assignments: dict[str, ast.expr],
    *,
    seen: frozenset[str] = frozenset(),
) -> set[str]:
    """Resolve string literals through simple named path expressions."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if (
        isinstance(node, ast.Name)
        and node.id in assignments
        and node.id not in seen
    ):
        return _string_literals(
            assignments[node.id],
            assignments,
            seen=seen | {node.id},
        )
    literals: set[str] = set()
    for child in ast.iter_child_nodes(node):
        literals.update(_string_literals(child, assignments, seen=seen))
    return literals


def _launcher_loaders() -> dict[str, frozenset[str]]:
    """Find direct and statically resolved dynamic launcher loads."""

    loaders: dict[str, frozenset[str]] = {}
    source_paths = sorted((*ROOT.glob("tests/**/*.py"), *ROOT.glob("scripts/**/*.py")))
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assignments = _assigned_expressions(tree)
        kinds: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name in {"core_pipeline", "scripts.core_pipeline"}
                for alias in node.names
            ):
                kinds.add("direct")
            elif isinstance(node, ast.ImportFrom):
                if node.module in {"core_pipeline", "scripts.core_pipeline"}:
                    kinds.add("direct")
                elif node.module == "scripts" and any(
                    alias.name == "core_pipeline" for alias in node.names
                ):
                    kinds.add("direct")
            elif isinstance(node, ast.Call):
                function = node.func
                is_dynamic_loader = (
                    isinstance(function, ast.Attribute)
                    and function.attr == "spec_from_file_location"
                ) or (
                    isinstance(function, ast.Name)
                    and function.id == "spec_from_file_location"
                )
                if (
                    is_dynamic_loader
                    and len(node.args) >= 2
                    and "core_pipeline.py"
                    in _string_literals(node.args[1], assignments)
                ):
                    kinds.add("dynamic")
        if kinds:
            loaders[path.relative_to(ROOT).as_posix()] = frozenset(kinds)
    return loaders


class PipelineFacadeRegistryTests(unittest.TestCase):
    def test_launcher_loads_stay_below_compatibility_budget(self) -> None:
        allowed = {
            "scripts/promote_core.py",
            "tests/core_contract_helpers.py",
            "tests/cores/support.py",
            "tests/test_core_pipeline.py",
            "tests/test_full_release_matrix.py",
            "tests/test_full_release_repository.py",
            "tests/test_host_build_telemetry.py",
            "tests/test_host_reproduction.py",
            "tests/test_per_core_lifecycle.py",
            "tests/test_pipeline_blacklist_integration.py",
            "tests/test_pipeline_cli_parser.py",
            "tests/test_pipeline_facade_registry.py",
            "tests/test_prebuild_pipeline_freeze.py",
            "tests/test_promote_core.py",
            "tests/test_release_source_graph.py",
            "tests/test_track_build_integration.py",
            "tests/test_tuned_bootstrap.py",
        }
        loaders = _launcher_loaders()
        self.assertLess(len(loaders), 20)
        self.assertLessEqual(set(loaders), allowed)

    def test_registry_exactly_covers_injected_leaf_functions(self) -> None:
        expected: set[str] = set()
        grouped: Counter[str] = Counter()
        for public_name, (
            leaf_module_name,
            injections,
            public_signature,
        ) in pipeline._FACADE_REGISTRY.items():
            with self.subTest(public_name=public_name):
                leaf_module = getattr(pipeline, leaf_module_name)
                leaf = getattr(leaf_module, public_name)
                injection_names = {name for name, _factory in injections}
                leaf_signature = inspect.signature(leaf)
                self.assertTrue(injection_names)
                self.assertLessEqual(
                    injection_names,
                    set(leaf_signature.parameters),
                )
                expected_signature = leaf_signature.replace(
                    parameters=[
                        parameter
                        for name, parameter in leaf_signature.parameters.items()
                        if name not in injection_names
                    ]
                )
                self.assertEqual(expected_signature, public_signature)
                self.assertEqual(
                    public_signature,
                    inspect.signature(getattr(pipeline, public_name)),
                )
                for _name, factory_name in injections:
                    self.assertTrue(callable(getattr(pipeline, factory_name)))
                grouped[leaf_module_name] += 1
                expected.add(public_name)

        self.assertEqual(expected, set(pipeline._FACADE_REGISTRY))
        self.assertEqual(278, len(expected))
        self.assertEqual(
            Counter(
                {
                    "_pipeline_inputs": 33,
                    "_build_contracts": 2,
                    "_catalog_contracts": 32,
                    "_catalog_validation": 20,
                    "_candidate_models": 16,
                    "_build_recipes": 27,
                    "_build_execution": 22,
                    "_evidence_validation": 20,
                    "_stored_evidence": 18,
                    "_pin_lifecycle": 26,
                    "_release_lifecycle": 24,
                    "_cli_catalog_build": 9,
                    "_cli_track_commands": 10,
                    "_cli_promotion_commands": 12,
                    "_cli_full_release_commands": 7,
                }
            ),
            grouped,
        )

    def test_facade_resolves_target_and_factory_at_call_time(self) -> None:
        service = object()
        seen: dict[str, object] = {}

        def replacement(document: dict, *, services: object) -> str:
            seen.update(document=document, services=services)
            return "replacement-result"

        with (
            mock.patch.object(
                pipeline._pipeline_inputs,
                "e2e_content_sha256",
                replacement,
            ),
            mock.patch.object(
                pipeline,
                "_pipeline_input_services",
                return_value=service,
            ),
        ):
            result = pipeline.e2e_content_sha256({"field": "value"})

        self.assertEqual("replacement-result", result)
        self.assertEqual(
            {"document": {"field": "value"}, "services": service},
            seen,
        )

    def test_facade_rejects_private_injection_bypass(self) -> None:
        self.assertNotIn(
            "services",
            inspect.signature(pipeline.e2e_content_sha256).parameters,
        )
        with self.assertRaises(TypeError):
            pipeline.e2e_content_sha256({}, services=object())

    def test_facade_rejects_hidden_routing_control_bypass(self) -> None:
        hidden_controls = {
            "__public_name": "golden_content_sha256",
            "__leaf_module_name": "_catalog_contracts",
            "__injections": (),
            "__signature": inspect.Signature(),
        }
        for name, value in hidden_controls.items():
            with self.subTest(name=name), self.assertRaises(TypeError):
                pipeline.e2e_content_sha256({}, **{name: value})

    def test_facade_metadata_is_public_and_leaf_documented(self) -> None:
        facade = pipeline.validate_catalog
        leaf = pipeline._catalog_validation.validate_catalog
        self.assertEqual("validate_catalog", facade.__name__)
        self.assertEqual("validate_catalog", facade.__qualname__)
        self.assertEqual("scripts.core_pipeline", facade.__module__)
        self.assertEqual(leaf.__doc__, facade.__doc__)
        self.assertNotIn("services", facade.__annotations__)


if __name__ == "__main__":
    unittest.main()
