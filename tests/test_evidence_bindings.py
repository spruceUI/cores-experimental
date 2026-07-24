"""Parametric evidence bindings: every core's promoted surfaces, one gate.

For each catalog core this verifies — from the tracked evidence index and
the promoted documents themselves — everything the per-core test files
used to assert through hand-transcribed literals:

  * the compatibility document names the pin, runs, and package the index
    records, and the pin's selection binds the same package and run;
  * both E2E records exist on disk with the indexed file/content digests,
    passed, and carry the correct runner evidence for their role;
  * the package exists in both runs with the pinned digest and size and
    the exact expected member set;
  * every per-arch build record and log matches the indexed digests, the
    artifact digests match record, pin, and compatibility targets, and
    the two runs' artifacts and packages are byte-identical;
  * where the core registers a build-log contract, both stored logs prove
    it.

Reviewed material — contract constants, caveat tokens, negative controls,
spec/schema/workflow shapes — stays in the per-core test files. This gate
covers only what is derivable from promoted disk state, so re-promotions
never require editing a test file: the regenerated index is the new
expectation, reviewed on the same diff as the promotion.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
import zipfile
from pathlib import Path

from scripts import core_pipeline as pipeline

from .cores.support import ROOT, file_sha256, load_document

_spec = importlib.util.spec_from_file_location(
    "evidence_index", ROOT / "scripts" / "evidence_index.py"
)
assert _spec is not None and _spec.loader is not None
evidence_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evidence_index)

ROLE_RUNNERS = {
    "selected": {
        "backend": "local-docker",
        "local_only": True,
        "mode": "simulated",
        "profile": "github-actions",
        "publication": "disabled",
    },
    "reproduction": {
        "backend": "local-docker",
        "local_only": True,
        "mode": "native",
        "profile": "local",
        "publication": "disabled",
    },
}

ARCH_PACKAGE_DIR = {"arm64": "cores64", "armhf": "cores"}


def _catalog() -> dict:
    return load_document(ROOT / "manifests" / "core-builds.json")


class EvidenceBindingTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = _catalog()

    def _assert_core_bindings(self, core: str) -> None:
        spec = self.catalog["cores"][core]
        index = load_document(evidence_index.index_path(core))
        compatibility = load_document(
            ROOT / "manifests" / "compatibility" / f"{core}.json"
        )
        pin = load_document(ROOT / index["pin_path"])
        artifact_name = spec["build"]["artifact_name"]
        targets = spec["targets"]

        # Compatibility <-> index <-> pin identity.
        self.assertEqual(index["semantic_id"], pin["pin_id"])
        self.assertEqual(
            index["pin_path"], compatibility["golden_source"]
        )
        self.assertEqual(
            index["compatibility"]["content_sha256"],
            compatibility["content_sha256"],
        )
        self.assertEqual(
            index["compatibility"]["file_sha256"],
            file_sha256(ROOT / "manifests" / "compatibility" / f"{core}.json"),
        )
        selection = pin["cores"][core]["selection"]
        self.assertEqual(
            index["selection_sha256"], selection["selection_sha256"]
        )
        self.assertEqual(
            index["package"]["sha256"], selection["package"]["sha256"]
        )
        self.assertEqual(
            index["runs"]["selected"]["run_id"], selection["e2e"]["run_id"]
        )
        self.assertEqual(
            index["runs"]["selected"]["e2e_content_sha256"],
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            index["runs"]["reproduction"]["e2e_content_sha256"],
            compatibility["reproduction_e2e_content_sha256"],
        )

        packages: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {arch: [] for arch in targets}
        proves = pipeline.registered_core_log_contract_proves
        has_contract = pipeline.core_log_contract_for(core) is not None

        for role, run in index["runs"].items():
            run_root = ROOT / ".local-e2e" / "runs" / run["run_id"]
            e2e_path = run_root / "e2e-record.json"
            evidence = load_document(e2e_path)
            self.assertEqual(run["e2e_file_sha256"], file_sha256(e2e_path))
            self.assertEqual(
                run["e2e_content_sha256"], evidence["content_sha256"]
            )
            self.assertEqual("passed", evidence["result"])
            self.assertEqual(ROLE_RUNNERS[role], evidence["runner"])

            package = evidence["packages"][0]
            self.assertEqual([core], [p["core_id"] for p in evidence["packages"]])
            self.assertEqual("packaged", package["result"])
            self.assertEqual(index["package"]["sha256"], package["sha256"])
            package_path = run_root / package["path"]
            self.assertEqual(
                index["package"]["sha256"], file_sha256(package_path)
            )
            expected_members = {f"{artifact_name.removesuffix('.so')}.info",
                                "manifest.json"}
            for arch in targets:
                expected_members.add(f"{ARCH_PACKAGE_DIR[arch]}/{artifact_name}")
            with zipfile.ZipFile(package_path) as archive:
                self.assertEqual(expected_members, set(archive.namelist()))
            packages.append(package_path.read_bytes())

            builds = {b["architecture"]: b for b in evidence["builds"]}
            self.assertEqual(set(targets), set(builds))
            for arch in targets:
                bound = run["builds"][arch]
                record_path = ROOT / builds[arch]["record"]
                self.assertEqual(
                    bound["record_sha256"], file_sha256(record_path)
                )
                self.assertEqual(
                    builds[arch]["record_sha256"], bound["record_sha256"]
                )
                record = load_document(record_path)
                self.assertEqual("passed", record["result"])
                self.assertEqual(
                    spec["source"]["commit"], record["source"]["commit"]
                )
                log_path = record_path.parent / record["build"]["log"]
                self.assertEqual(bound["log_sha256"], file_sha256(log_path))
                self.assertEqual(bound["log_size"], log_path.stat().st_size)
                artifact_path = record_path.parent / Path(
                    record["artifact"]["path"]
                ).name
                self.assertEqual(
                    index["targets"][arch]["artifact_sha256"],
                    record["artifact"]["sha256"],
                )
                self.assertEqual(
                    index["targets"][arch]["artifact_sha256"],
                    file_sha256(artifact_path),
                )
                self.assertEqual(
                    index["targets"][arch]["image_id"],
                    record["toolchain"]["image_id"],
                )
                archive_facts = record["toolchain"]["archive_provenance"][
                    "archive"
                ]
                self.assertEqual(
                    index["targets"][arch]["toolchain_archive_sha256"],
                    archive_facts["sha256"],
                )
                artifacts[arch].append(artifact_path.read_bytes())
                if has_contract:
                    self.assertTrue(
                        proves(
                            log_path.read_text(encoding="utf-8"),
                            core,
                            arch,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        ),
                        f"{core}/{arch}/{role}: stored log fails its "
                        "registered contract",
                    )

        # Byte reproduction across the two independent runs.
        self.assertEqual(packages[0], packages[1])
        for arch, payloads in artifacts.items():
            self.assertEqual(
                payloads[0], payloads[1],
                f"{core}/{arch}: artifacts differ between runs",
            )

        # Compatibility targets carry the same artifact identity.
        for arch in targets:
            self.assertEqual(
                index["targets"][arch]["artifact_sha256"],
                compatibility["targets"][arch]["artifact_sha256"],
            )

    def test_every_core_binds_its_promoted_evidence(self) -> None:
        for core in sorted(self.catalog["cores"]):
            with self.subTest(core=core):
                self._assert_core_bindings(core)


if __name__ == "__main__":
    unittest.main()
