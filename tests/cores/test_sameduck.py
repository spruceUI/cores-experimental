"""Focused sameduck catalog, workflow, contract, and object-naming tests."""

from __future__ import annotations

import dataclasses
import unittest

from .support import pipeline
from core_pipeline_lib.contracts import core_log_contract_for, sameduck
from core_pipeline_lib.contracts.c_only import c_only_log_proves_contract

from .support import evidence_handles, ROOT, load_document


CORE_ID = "sameduck"
_H = evidence_handles(CORE_ID)
SOURCE_URL = "https://github.com/libretro/sameduck.git"
SOURCE_COMMIT = "f0286ee9d6c44950d9a442463ffdb1ff014a5d5b"
SOURCE_TREE = "c04c4f24a078b55386a1c62ae3619dde5b5087d9"
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
ORACLE_ROOT = ROOT / "tests/fixtures/per-core-oracles/sameduck"
REVIEWED_RUN_IDS = (
    "actions-sim-build-core-sameduck-v1",
    "actions-sim-build-core-sameduck-w3",
    "actions-sim-explore-sameduck",
    "build-core-sameduck-local-v1",
    "build-core-sameduck-local-w3",
    "campaign-20260810-main-universal-sameduck-resume-01",
    "sameduck-explore-v1",
)


class SameduckManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/SameDuck-libretro",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual("libretro-sameduck", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(sameduck.sameduck_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(sameduck.sameduck_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core sameduck", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class SameduckCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/sameduck.json"
        compatibility = load_document(compatibility_path)
        report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual("valid", report["status"], report["errors"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/sameduck.json").exists()
        )


class SameduckContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def _representative_log(self, arch: str) -> str:
        return (ORACLE_ROOT / f"{arch}-build.txt").read_text(
            encoding="utf-8"
        )

    def _diagnostic_events(
        self, log: str
    ) -> tuple[list[str], int, int, list[tuple[str, tuple[str, ...]]]]:
        lines = log.splitlines()
        start = next(
            position
            for position, line in enumerate(lines)
            if sameduck.SAMEDUCK_DIAGNOSTIC_HEADING_RE.fullmatch(line)
            is not None
        )
        link = next(
            position
            for position, line in enumerate(lines)
            if f" -o {sameduck.SAMEDUCK_BUILD_ARTIFACT_NAME} "
            in f" {line} "
            and " -c " not in f" {line} "
        )
        events: list[tuple[str, tuple[str, ...]]] = []
        position = start
        while position < link:
            line = lines[position]
            if sameduck.SAMEDUCK_DIAGNOSTIC_HEADING_RE.fullmatch(line):
                event = (line,)
            else:
                self.assertIsNotNone(sameduck.SAMEDUCK_WARNING_RE.match(line))
                event = tuple(lines[position : position + 3])
                self.assertEqual(3, len(event))
            source = line.split(":", 1)[0]
            events.append((source, event))
            position += len(event)
        self.assertEqual(link, position)
        return lines, start, link, events

    def _rewrite_diagnostic_events(
        self,
        log: str,
        events: list[tuple[str, tuple[str, ...]]],
    ) -> str:
        lines, start, link, _original = self._diagnostic_events(log)
        replacement = [
            line for _source, event in events for line in event
        ]
        return "\n".join((*lines[:start], *replacement, *lines[link:])) + "\n"

    def test_contract_uses_sha_pinned_object_names(self) -> None:
        # the load-bearing relaxation: sameduck names objects
        # build/obj/<path>/<name>_libretro.c.o, not <stem>.o
        self.assertTrue(
            sameduck.SAMEDUCK_LOG_CONTRACT.sha_pinned_object_names
        )
        self.assertEqual(
            (("..//", ""),),
            sameduck.SAMEDUCK_LOG_CONTRACT.semantic_path_aliases,
        )

    def test_registry_failure_names_reviewed_diagnostics(self) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertIn("reviewed diagnostic contract", contract.failure_message)

    def test_tracked_oracle_logs_prove_the_exact_contract(self) -> None:
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                self.assertTrue(
                    sameduck.sameduck_log_proves_contract(
                        self._representative_log(arch),
                        CORE_ID,
                        arch,
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
                )

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    sameduck.sameduck_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the sameduck contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local sameduck build logs present")

    def test_all_retained_logs_accept_only_reviewed_parallel_interleaving(
        self,
    ) -> None:
        proven = 0
        for run_id in REVIEWED_RUN_IDS:
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                with self.subTest(run_id=run_id, arch=arch):
                    self.assertTrue(
                        sameduck.sameduck_log_proves_contract(
                            log,
                            CORE_ID,
                            arch,
                            SOURCE_COMMIT,
                            SOURCE_TREE,
                        )
                    )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local sameduck build logs present")

    def test_cross_source_event_reordering_is_accepted(self) -> None:
        log = self._representative_log("arm64")
        _lines, _start, _link, events = self._diagnostic_events(log)
        sources = tuple(dict.fromkeys(source for source, _event in events))
        reordered = [
            (source, event)
            for source in reversed(sources)
            for observed_source, event in events
            if observed_source == source
        ]
        mutated = self._rewrite_diagnostic_events(log, reordered)
        self.assertNotEqual(log, mutated)
        self.assertTrue(
            sameduck.sameduck_log_proves_contract(
                mutated,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_compile_echoes_may_follow_reviewed_diagnostics(self) -> None:
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                lines = self._representative_log(arch).splitlines()
                compiler = sameduck.SAMEDUCK_C_COMPILER[arch]
                compile_positions = [
                    position
                    for position, line in enumerate(lines)
                    if line.startswith(f"{compiler} ")
                    and " -c " in f" {line} "
                ]
                self.assertEqual(13, len(compile_positions))
                moved_positions = set(compile_positions[-5:])
                moved_lines = [lines[position] for position in compile_positions[-5:]]
                remaining = [
                    line
                    for position, line in enumerate(lines)
                    if position not in moved_positions
                ]
                link_position = next(
                    position
                    for position, line in enumerate(remaining)
                    if f" -o {sameduck.SAMEDUCK_BUILD_ARTIFACT_NAME} "
                    in f" {line} "
                    and " -c " not in f" {line} "
                )
                mutated = "\n".join(
                    (
                        *remaining[:link_position],
                        *moved_lines,
                        *remaining[link_position:],
                    )
                ) + "\n"
                self.assertTrue(
                    sameduck.sameduck_log_proves_contract(
                        mutated,
                        CORE_ID,
                        arch,
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
                )

    def test_within_source_event_reordering_is_rejected(self) -> None:
        log = self._representative_log("arm64")
        _lines, _start, _link, events = self._diagnostic_events(log)
        source = events[0][0]
        positions = [
            position
            for position, (observed_source, _event) in enumerate(events)
            if observed_source == source
        ]
        self.assertGreaterEqual(len(positions), 2)
        reordered = list(events)
        first, second = positions[:2]
        reordered[first], reordered[second] = (
            reordered[second],
            reordered[first],
        )
        mutated = self._rewrite_diagnostic_events(log, reordered)
        self.assertFalse(
            sameduck.sameduck_log_proves_contract(
                mutated,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_plain_output_inside_diagnostic_span_is_rejected(self) -> None:
        log = self._representative_log("arm64")
        lines, start, _link, _events = self._diagnostic_events(log)
        lines.insert(start, "UNREVIEWED BUILD OUTPUT")
        mutated = "\n".join(lines) + "\n"
        self.assertFalse(
            sameduck.sameduck_log_proves_contract(
                mutated,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_unreviewed_or_failed_diagnostics_are_rejected(self) -> None:
        log = self._representative_log("arm64")
        mutations = {
            "extra warning": (
                log
                + "synthetic.c:1:1: warning: unreviewed diagnostic\n"
                + "    1 | injected\n"
                + "      | ^~~~~~~~\n"
            ),
            "compiler error": log + "synthetic.c:1:1: error: injected\n",
            "make failure": log + "make: *** [sameduck] Error 1\n",
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    sameduck.sameduck_log_proves_contract(
                        mutated,
                        CORE_ID,
                        "arm64",
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
                )

    def test_missing_or_changed_reviewed_diagnostic_is_rejected(self) -> None:
        for arch in ("arm64", "armhf"):
            log = self._representative_log(arch)
            lines = log.splitlines(keepends=True)
            warning_position = next(
                position
                for position, line in enumerate(lines)
                if "warning:" in line.casefold()
            )
            self.assertLess(warning_position + 2, len(lines))
            missing_context = "".join(
                (
                    *lines[: warning_position + 1],
                    *lines[warning_position + 2 :],
                )
            )
            changed_warning = log.replace(
                "multi-character character constant",
                "changed reviewed diagnostic",
                1,
            )
            self.assertNotEqual(changed_warning, log)
            for label, mutated in {
                "missing context": missing_context,
                "changed warning": changed_warning,
            }.items():
                with self.subTest(arch=arch, label=label):
                    self.assertFalse(
                        sameduck.sameduck_log_proves_contract(
                            mutated,
                            CORE_ID,
                            arch,
                            SOURCE_COMMIT,
                            SOURCE_TREE,
                        )
                    )

    def test_strict_object_naming_would_reject(self) -> None:
        log = self._representative_log("arm64")
        strict = dataclasses.replace(
            sameduck.SAMEDUCK_LOG_CONTRACT, sha_pinned_object_names=False
        )
        self.assertFalse(
            c_only_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, strict
            )
        )


if __name__ == "__main__":
    unittest.main()
