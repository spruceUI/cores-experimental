"""Focused malformed-input checks for the individual-core lifecycle."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from .cores.support import pipeline


CORE_ID = "handy"


def minimal_pin() -> dict:
    """Return the smallest structurally valid empty pin document."""

    document = {
        "schema_version": 1,
        "pin_id": "fixture-pin",
        "local_only": True,
        "publication": "disabled",
        "scope": [],
        "parent": None,
        "sources": [],
        "selection_policy": copy.deepcopy(pipeline.PIN_SELECTION_POLICY),
        "cores": {},
        "summary": {
            "core_count": 0,
            "retained_parent_count": 0,
            "selected_source_count": 0,
        },
    }
    document["content_sha256"] = pipeline.pin_set_content_sha256(document)
    return document


def refresh_pin_digest(document: dict) -> dict:
    document["content_sha256"] = pipeline.pin_set_content_sha256(document)
    return document


class LifecycleFailClosedTests(unittest.TestCase):
    def test_semantic_id_rejects_non_string_source_commit(self) -> None:
        selection = {
            "selection_sha256": "b" * 64,
            "targets": {
                "arm64": {
                    "golden_record": {"source": {"commit": []}},
                }
            },
        }
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "individual core semantic identity.*invalid",
        ):
            pipeline.individual_core_semantic_id(CORE_ID, selection)

    def test_pin_validator_rejects_malformed_top_level_shapes(self) -> None:
        cases: dict[str, dict] = {}

        pin_id = minimal_pin()
        pin_id["pin_id"] = []
        cases["pin_id list"] = refresh_pin_digest(pin_id)

        null_sources = minimal_pin()
        null_sources["sources"] = None
        cases["sources null"] = refresh_pin_digest(null_sources)

        malformed_source = minimal_pin()
        malformed_source["sources"] = [None]
        cases["source entry null"] = refresh_pin_digest(malformed_source)

        cores_list = minimal_pin()
        cores_list["cores"] = []
        cases["cores list"] = refresh_pin_digest(cores_list)

        malformed_core = minimal_pin()
        malformed_core["scope"] = [CORE_ID]
        malformed_core["cores"] = {CORE_ID: None}
        malformed_core["summary"]["core_count"] = 1
        malformed_core["summary"]["selected_source_count"] = 1
        cases["core entry null"] = refresh_pin_digest(malformed_core)

        malformed_selection = minimal_pin()
        malformed_selection["scope"] = [CORE_ID]
        malformed_selection["cores"] = {
            CORE_ID: {
                "decision": "select_source",
                "source_index": 0,
                "selection": [],
            }
        }
        malformed_selection["summary"]["core_count"] = 1
        malformed_selection["summary"]["selected_source_count"] = 1
        cases["selection list"] = refresh_pin_digest(malformed_selection)

        malformed_summary = minimal_pin()
        malformed_summary["summary"] = []
        cases["summary list"] = refresh_pin_digest(malformed_summary)

        for label, document in cases.items():
            with self.subTest(shape=label):
                report = pipeline.validate_pin_set_document(document)
                self.assertEqual("invalid", report["status"])
                self.assertTrue(report["errors"])

    def test_release_rejects_symlinked_asset_resolving_inside_release(self) -> None:
        payload = b"local package bytes"
        package_sha256 = pipeline.sha256_bytes(payload)
        selection_sha256 = "c" * 64
        pin = {
            "pin_id": "fixture-pin",
            "content_sha256": "d" * 64,
            "scope": [CORE_ID],
            "cores": {
                CORE_ID: {
                    "selection": {
                        "tier": "build_golden",
                        "selection_sha256": selection_sha256,
                        "package": {
                            "sha256": package_sha256,
                            "size": len(payload),
                        },
                    }
                }
            },
        }
        pin_file_sha256 = "e" * 64

        local_root = pipeline.ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            releases_root = Path(temporary) / "releases"
            release_root = releases_root / "fixture-release"
            real_directory = release_root / "real"
            real_directory.mkdir(parents=True)
            asset_name = f"{CORE_ID}_libretro.zip"
            real_asset = real_directory / asset_name
            real_asset.write_bytes(payload)
            (release_root / asset_name).symlink_to(
                real_asset.relative_to(release_root)
            )
            manifest = {
                "schema_version": 1,
                "release_id": release_root.name,
                "local_only": True,
                "publication": "disabled",
                "pin": {
                    "pin_id": pin["pin_id"],
                    "content_sha256": pin["content_sha256"],
                    "file_sha256": pin_file_sha256,
                },
                "assets": [
                    {
                        "core_id": CORE_ID,
                        "path": asset_name,
                        "sha256": package_sha256,
                        "size": len(payload),
                        "selection_sha256": selection_sha256,
                        "source_tier": "build_golden",
                    }
                ],
            }
            manifest["content_sha256"] = pipeline.release_content_sha256(
                manifest
            )
            (release_root / "release-manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            with mock.patch.object(
                pipeline,
                "DEFAULT_RELEASES",
                releases_root,
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "release asset path must not traverse a symlink",
            ):
                pipeline._validate_local_release(
                    release_root,
                    pin,
                    pin_file_sha256,
                )

    def test_nightly_target_rejects_non_object_build_goldens(self) -> None:
        local_root = pipeline.ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            nightlies = Path(temporary) / "nightlies"
            for label, malformed in (("null", None), ("list", [])):
                with self.subTest(shape=label):
                    target = nightlies / f"handy-{label}" / "golden.json"
                    target.parent.mkdir(parents=True)
                    target.write_text(
                        json.dumps(
                            {
                                "pin_id": "ignored-for-individual-nightly",
                                "content_sha256": "f" * 64,
                                "build_goldens": malformed,
                            }
                        ),
                        encoding="utf-8",
                    )
                    with mock.patch.object(
                        pipeline,
                        "DEFAULT_NIGHTLIES",
                        nightlies,
                    ), mock.patch.object(
                        pipeline,
                        "validate_golden_document",
                        return_value={"status": "invalid", "errors": []},
                    ), mock.patch.object(
                        pipeline,
                        "verify_local_store",
                        return_value=[],
                    ), self.assertRaisesRegex(
                        pipeline.PipelineError,
                        "individual nightly channel target must contain "
                        "exactly its core",
                    ):
                        pipeline.derive_channel_target(
                            "nightly",
                            target,
                            core_id=CORE_ID,
                        )

    def test_store_verifier_rejects_non_string_entry_paths(self) -> None:
        for malformed_path in ([], {}):
            with self.subTest(path=malformed_path):
                document = {
                    "build_goldens": {
                        CORE_ID: {
                            "arm64": {
                                "local_store": {
                                    "artifact": {
                                        "path": malformed_path,
                                        "sha256": "a" * 64,
                                    },
                                    "build_records": {},
                                    "build_logs": {},
                                    "recipe_snapshots": {},
                                }
                            }
                        }
                    }
                }
                errors = pipeline.verify_local_store(document)
                self.assertTrue(errors)
                self.assertTrue(
                    any("identity is invalid" in error for error in errors),
                    errors,
                )


if __name__ == "__main__":
    unittest.main()
