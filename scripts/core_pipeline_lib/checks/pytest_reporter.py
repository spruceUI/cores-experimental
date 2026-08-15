"""Pytest plugin emitting canonical exact-node outcome evidence for H4 checks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from .artifacts import PYTEST_REPORT_SCHEMA_VERSION
from .model import canonical_json_bytes


PLUGIN_NAME = "core-pipeline-consolidated-check-reporter"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("consolidated-check")
    group.addoption("--consolidated-check-report")
    group.addoption("--consolidated-check-id")
    group.addoption("--consolidated-check-subject-sha256")
    group.addoption("--consolidated-check-run-id")
    group.addoption("--consolidated-check-argv-sha256")


def _exclusive_write(path: Path, content: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("canonical pytest report write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class _Reporter:
    def __init__(self, config: pytest.Config) -> None:
        self.report_path = Path(config.getoption("--consolidated-check-report"))
        self.check_id = config.getoption("--consolidated-check-id")
        self.subject_sha256 = config.getoption(
            "--consolidated-check-subject-sha256"
        )
        self.run_id = config.getoption("--consolidated-check-run-id")
        self.argv_sha256 = config.getoption("--consolidated-check-argv-sha256")
        self.node_ids: list[str] = []
        self.outcomes: dict[str, str] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.node_ids = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        node_id = report.nodeid
        if report.skipped:
            self.outcomes[node_id] = "skipped"
        elif report.failed:
            self.outcomes[node_id] = "failed"
        elif report.when == "call" and node_id not in self.outcomes:
            self.outcomes[node_id] = "passed"

    def pytest_sessionfinish(
        self,
        session: pytest.Session,
        exitstatus: pytest.ExitCode | int,
    ) -> None:
        tests = [
            {
                "node_id": node_id,
                "outcome": self.outcomes.get(node_id, "failed"),
            }
            for node_id in self.node_ids
        ]
        document = {
            "schema_version": PYTEST_REPORT_SCHEMA_VERSION,
            "check_id": self.check_id,
            "subject_sha256": self.subject_sha256,
            "run_id": self.run_id,
            "argv_sha256": self.argv_sha256,
            "exitstatus": int(exitstatus),
            "tests": tests,
        }
        _exclusive_write(self.report_path, canonical_json_bytes(document))


def pytest_configure(config: pytest.Config) -> None:
    names = (
        "--consolidated-check-report",
        "--consolidated-check-id",
        "--consolidated-check-subject-sha256",
        "--consolidated-check-run-id",
        "--consolidated-check-argv-sha256",
    )
    values = tuple(config.getoption(name) for name in names)
    if any(value is None for value in values):
        raise pytest.UsageError(
            "consolidated check reporter requires every provenance option"
        )
    report_path = Path(values[0])
    if not report_path.is_absolute() or report_path.exists() or report_path.is_symlink():
        raise pytest.UsageError(
            "consolidated check report must be a new absolute path"
        )
    reporter = _Reporter(config)
    config.pluginmanager.register(reporter, PLUGIN_NAME)


__all__ = []
