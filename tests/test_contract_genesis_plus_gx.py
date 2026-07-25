"""Genesis Plus GX contract: engine binding, provenance markers, reviewed diagnostics."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import genesis_plus_gx as contract_module

from .cores.support import ROOT, evidence_handles


CORE_ID = "genesis_plus_gx"
OTHER_CORE_ID = "genesis_plus_gx_wide"
_H = evidence_handles(CORE_ID)
P = "GENESIS_PLUS_GX"


def _stored_log(arch: str) -> str:
    return (
        ROOT
        / ".local-e2e/runs"
        / _H["SELECTED_RUN"]
        / CORE_ID
        / arch
        / "build.log"
    ).read_text(encoding="utf-8")


def _proves(log_text: str, arch: str) -> bool:
    return contract_module.genesis_plus_gx_log_proves_contract(
        log_text,
        CORE_ID,
        arch,
        _H["SOURCE_COMMIT"],
        _H["SOURCE_TREE"],
    )


class GenesisPlusGxContractTests(unittest.TestCase):
    def test_registered_contract_binds_the_engine_parameters(self) -> None:
        registered = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered)
        contract = getattr(contract_module, f"{P}_LOG_CONTRACT")
        self.assertEqual(CORE_ID, contract.core_id)
        self.assertEqual(_H["SOURCE_COMMIT"], contract.source_commit)
        self.assertEqual(_H["SOURCE_TREE"], contract.source_tree)
        self.assertEqual(
            getattr(contract_module, f"{P}_C_COMPILE_COUNT"),
            contract.expected_compile_count,
        )
        self.assertEqual(
            set(_H["TARGETS"]),
            set(contract.expected_compile_invocation_sha256),
        )

    def test_stored_logs_prove_and_are_arch_scoped(self) -> None:
        for arch in _H["TARGETS"]:
            with self.subTest(architecture=arch):
                self.assertTrue(_proves(_stored_log(arch), arch))
        arches = sorted(_H["TARGETS"])
        if len(arches) == 2:
            self.assertFalse(_proves(_stored_log(arches[0]), arches[1]))

    def test_stored_logs_do_not_prove_the_sibling_core(self) -> None:
        sibling = pipeline.registered_core_log_contract_proves
        arch = sorted(_H["TARGETS"])[0]
        self.assertFalse(
            sibling(
                _stored_log(arch),
                OTHER_CORE_ID,
                arch,
                _H["SOURCE_COMMIT"],
                _H["SOURCE_TREE"],
            )
        )

    def test_provenance_markers_fail_closed(self) -> None:
        arch = sorted(_H["TARGETS"])[0]
        log = _stored_log(arch)
        head = getattr(contract_module, f"{P}_SOURCE_HEAD_MARKER")
        native = getattr(
            contract_module, f"{P}_NATIVE_GIT_VERSION_MARKER"
        )
        for marker in (head, native):
            with self.subTest(marker=marker[:30]):
                mutated = log.replace(marker + "\n", "", 1)
                self.assertNotEqual(mutated, log)
                self.assertFalse(_proves(mutated, arch))
        doubled = log.replace(head + "\n", head + "\n" + head + "\n", 1)
        self.assertFalse(_proves(doubled, arch))

    def test_success_framing_and_failure_guards_fail_closed(self) -> None:
        arch = sorted(_H["TARGETS"])[0]
        log = _stored_log(arch)
        trailer = getattr(contract_module, f"{P}_SUCCESS_TRAILER")
        truncated = log[: log.rindex(trailer[0])]
        self.assertFalse(_proves(truncated, arch))
        poisoned = log.replace(
            trailer[0], "collect2: error: ld returned 1\n" + trailer[0], 1
        )
        self.assertFalse(_proves(poisoned, arch))

    def test_reviewed_diagnostics_fail_closed(self) -> None:
        streams = getattr(
            contract_module, f"{P}_EXPECTED_DIAGNOSTIC_STREAMS"
        )
        for arch, arch_streams in streams.items():
            if arch not in _H["TARGETS"] or not arch_streams:
                continue
            log = _stored_log(arch)
            first_stream = next(iter(arch_streams.values()))
            warning_line = next(
                line for line in first_stream if "warning:" in line
            )
            with self.subTest(architecture=arch):
                removed = log.replace(warning_line + "\n", "", 1)
                self.assertNotEqual(removed, log)
                self.assertFalse(_proves(removed, arch))


if __name__ == "__main__":
    unittest.main()
