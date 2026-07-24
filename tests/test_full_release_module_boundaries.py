from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "scripts" / "core_pipeline_lib"
CLI = LIBRARY / "cli"
RELEASE = LIBRARY / "release"


def module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(path: Path) -> set[str]:
    """Resolve absolute and relative imports without importing production code."""

    current_module = module_name(path)
    package = current_module.split(".")
    if path.name != "__init__.py":
        package.pop()
    imports: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            keep = len(package) - node.level + 1
            base_parts = package[:keep]
            if node.module:
                base_parts.extend(node.module.split("."))
            base = ".".join(base_parts)
        else:
            base = node.module or ""
        if base:
            imports.add(base)
        for alias in node.names:
            if alias.name != "*":
                imports.add(".".join(part for part in (base, alias.name) if part))
    return imports


def is_module_or_child(candidate: str, parent: str) -> bool:
    return candidate == parent or candidate.startswith(parent + ".")


class FullReleaseModuleBoundaryTests(unittest.TestCase):
    def test_core_dependencies_do_not_point_back_to_launcher_or_cli(self) -> None:
        library_modules = sorted(LIBRARY.rglob("*.py"))
        release_modules = sorted(RELEASE.glob("*.py"))
        self.assertTrue(release_modules)
        self.assertTrue(
            {"repository.py", "worker.py"}.issubset(
                {path.name for path in release_modules}
            )
        )

        violations = []
        for path in library_modules:
            relative = path.relative_to(ROOT).as_posix()
            inside_cli = path == CLI or CLI in path.parents
            for imported in sorted(imported_modules(path)):
                if is_module_or_child(imported, "scripts.core_pipeline"):
                    violations.append(f"{relative} imports launcher {imported}")
                if not inside_cli and is_module_or_child(
                    imported, "scripts.core_pipeline_lib.cli"
                ):
                    violations.append(f"{relative} imports CLI layer {imported}")

        self.assertEqual([], violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
