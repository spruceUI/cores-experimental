"""Tests for the promotion lifecycle composer (promote_core.py)."""

from __future__ import annotations

import copy
from contextlib import contextmanager
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "promote_core", ROOT / "scripts" / "promote_core.py"
)
assert _spec is not None and _spec.loader is not None
promote_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_core)
import core_pipeline as pipeline  # noqa: E402

UZEM_ID = "uzem-d4fe82c38bf3-34eca38274ae"
EASYRPG_CANDIDATE_ID = "easyrpg-212f3466c9f2-6b88f668ee6e"


def _stripped_easyrpg_pin(root: Path) -> str:
    """Write a self-hashed candidate pin with its provenance labels removed."""

    original = json.loads(
        (ROOT / "pins" / "core-sets" / f"{EASYRPG_CANDIDATE_ID}.json")
        .read_text(encoding="utf-8")
    )
    pin = copy.deepcopy(original)
    selection = pin["cores"]["easyrpg"]["selection"]
    selection.pop("source_candidate")
    selection.pop("output_reproduction")
    for target in selection["targets"].values():
        record = target["golden_record"]
        record.pop("source_candidate")
        record.pop("output_reproduction")
        target["provenance_identity_sha256"] = (
            pipeline.provenance_identity_sha256(record)
        )
    selection["selection_sha256"] = (
        promote_core.records_source._selection_content_sha256(selection)
    )
    source_commit = next(iter(selection["targets"].values()))[
        "golden_record"
    ]["source"]["commit"]
    semantic_id = (
        f"easyrpg-{source_commit[:12]}-{selection['selection_sha256'][:12]}"
    )
    pin["pin_id"] = semantic_id
    pin["sources"][0]["path"] = (
        f".local-e2e/nightlies/{semantic_id}/golden.json"
    )
    pin["sources"][0]["pin_id"] = semantic_id
    pin["content_sha256"] = promote_core.records_source._pin_set_content_sha256(
        pin
    )
    (root / "pins" / "core-sets").mkdir(parents=True)
    (root / "pins" / "core-sets" / f"{semantic_id}.json").write_text(
        json.dumps(pin, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "manifests").mkdir(parents=True)
    (root / "manifests" / "core-builds.json").write_bytes(
        (ROOT / "manifests" / "core-builds.json").read_bytes()
    )
    return semantic_id


@contextmanager
def _canonicalized_easyrpg_candidate_laundering():
    """Retain candidate raw evidence behind canonicalized summary records."""

    pin_path = (
        ROOT / "pins" / "core-sets" / f"{EASYRPG_CANDIDATE_ID}.json"
    )
    if not pin_path.is_file():
        raise unittest.SkipTest("EasyRPG candidate pin is not present")
    original_pin = json.loads(pin_path.read_text(encoding="utf-8"))
    original_golden_path = ROOT / original_pin["sources"][0]["path"]
    if not original_golden_path.is_file():
        raise unittest.SkipTest("EasyRPG candidate golden is not present")
    pin = copy.deepcopy(original_pin)
    golden = json.loads(original_golden_path.read_text(encoding="utf-8"))
    selection = pin["cores"]["easyrpg"]["selection"]
    selected_run = selection["e2e"]["run_id"]
    reproduction_run = selection["output_reproduction"]["reproduction"][
        "run_id"
    ]
    selection.pop("source_candidate")
    selection.pop("output_reproduction")
    canonical_source = json.loads(
        (ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8")
    )["cores"]["easyrpg"]["source"]
    for target in selection["targets"].values():
        record = target["golden_record"]
        record.pop("source_candidate")
        record.pop("output_reproduction")
        record["source"] = {
            "url": canonical_source["url"],
            "resolved_url": canonical_source["url"],
            "requested_ref": canonical_source["requested_ref"],
            "commit": canonical_source["commit"],
            "resolved_commit": canonical_source["commit"],
            "tree": canonical_source["tree"],
            "submodules": [],
        }
        target["provenance_identity_sha256"] = (
            pipeline.provenance_identity_sha256(record)
        )
    selection["selection_sha256"] = pipeline.selection_content_sha256(
        selection
    )
    semantic_id = (
        f"easyrpg-{canonical_source['commit'][:12]}-"
        f"{selection['selection_sha256'][:12]}"
    )
    golden["pin_id"] = semantic_id
    golden["build_goldens"]["easyrpg"] = {
        architecture: copy.deepcopy(target["golden_record"])
        for architecture, target in selection["targets"].items()
    }
    golden["content_sha256"] = pipeline.golden_content_sha256(golden)
    golden_relative = f".local-e2e/nightlies/{semantic_id}/golden.json"
    golden_path = ROOT / golden_relative
    generated_pin_path = ROOT / "pins" / "core-sets" / f"{semantic_id}.json"
    if generated_pin_path.exists() or golden_path.exists():
        raise RuntimeError("canonicalized laundering fixture path already exists")
    golden_path.parent.mkdir(parents=True)
    golden_bytes = (json.dumps(golden, indent=2) + "\n").encode()
    golden_path.write_bytes(golden_bytes)
    pin["pin_id"] = semantic_id
    pin["sources"][0].update(
        {
            "path": golden_relative,
            "pin_id": semantic_id,
            "file_sha256": hashlib.sha256(golden_bytes).hexdigest(),
            "content_sha256": golden["content_sha256"],
        }
    )
    pin["content_sha256"] = pipeline.pin_set_content_sha256(pin)
    generated_pin_path.write_text(
        json.dumps(pin, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        yield semantic_id, selected_run, reproduction_run
    finally:
        generated_pin_path.unlink(missing_ok=True)
        golden_path.unlink(missing_ok=True)
        try:
            golden_path.parent.rmdir()
        except OSError:
            pass


class HelperTests(unittest.TestCase):
    def test_content_sha256_ignores_schema_and_self(self):
        a = {"$schema": "x", "a": 1, "content_sha256": "old"}
        b = {"$schema": "y", "a": 1}
        self.assertEqual(
            promote_core.content_sha256(a), promote_core.content_sha256(b)
        )

    def test_source_selection_digest_includes_host_reproduction(self):
        selection = {
            "tier": "build_golden",
            "validation_scope": "static-build-only",
            "e2e": {
                "run_id": "selected",
                "content_sha256": "1" * 64,
            },
            "package": {
                "name": "alpha_libretro.zip",
                "sha256": "2" * 64,
                "size": 10,
            },
            "metadata": {
                "sha256": "3" * 64,
                "size": 11,
            },
            "targets": {
                "arm64": {
                    "artifact": {
                        "sha256": "4" * 64,
                        "size": 12,
                    },
                    "build_record_sha256": "5" * 64,
                    "provenance_identity_sha256": "6" * 64,
                }
            },
            "host_reproduction": {
                "schema_version": 1,
                "validation_scope": "dual-hardened-host-e2e-equivalence-v1",
                "selected": {"content_sha256": "7" * 64},
                "reproduction": {"content_sha256": "8" * 64},
                "equivalent_builds": {"arm64": "9" * 64},
                "equivalent_outputs": {"package": {"sha256": "a" * 64}},
                "content_sha256": "b" * 64,
            },
        }
        self.assertEqual(
            pipeline.selection_content_sha256(selection),
            promote_core.records_source._selection_content_sha256(selection),
        )

        without_proof = copy.deepcopy(selection)
        without_proof.pop("host_reproduction")
        self.assertNotEqual(
            promote_core.records_source._selection_content_sha256(selection),
            promote_core.records_source._selection_content_sha256(without_proof),
        )

        changed_proof = copy.deepcopy(selection)
        changed_proof["host_reproduction"]["equivalent_builds"]["arm64"] = (
            "c" * 64
        )
        self.assertEqual(
            pipeline.selection_content_sha256(changed_proof),
            promote_core.records_source._selection_content_sha256(changed_proof),
        )
        self.assertNotEqual(
            pipeline.selection_content_sha256(selection),
            pipeline.selection_content_sha256(changed_proof),
        )

    def test_max_glibcxx_picks_highest(self):
        value, key = promote_core.max_glibcxx(
            ["GLIBCXX_3.4", "GLIBCXX_3.4.29", "GLIBC_2.4"]
        )
        self.assertEqual(value, "3.4.29")
        self.assertEqual(key, (3, 4, 29))


class SourceLockTests(unittest.TestCase):
    def test_compose_source_lock_matches_catalog_and_validates(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from profile_registry import canonical_content_sha256, validate_source_lock

        catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8")
        )
        source = catalog["cores"]["atari800"]["source"]
        lock = promote_core.compose_source_lock("atari800")
        self.assertEqual("atari800", lock["core_id"])
        self.assertEqual(f"atari800-{source['commit'][:12]}", lock["source_lock_id"])
        self.assertEqual(source["commit"], lock["source"]["commit"])
        self.assertEqual(source["tree"], lock["source"]["tree"])
        self.assertEqual([], lock["source"]["submodules"])
        self.assertEqual(
            canonical_content_sha256(lock), lock["content_sha256"]
        )
        validate_source_lock(lock, path=None)


class DeviceCaveatTests(unittest.TestCase):
    def test_over_mini_ceiling_is_a30_only(self):
        caveat = promote_core._device_caveat(
            {"armhf": {"version_requirements": ["GLIBCXX_3.4.29"]}}
        )
        self.assertIn("above the observed", caveat)
        self.assertIn("Mini profile is ineligible", caveat)

    def test_within_mini_ceiling_clears_both(self):
        caveat = promote_core._device_caveat(
            {"armhf": {"version_requirements": ["GLIBCXX_3.4.21"]}}
        )
        self.assertIn("within the observed Miyoo Mini", caveat)

    def test_c_only_clears_every_ceiling(self):
        caveat = promote_core._device_caveat(
            {"armhf": {"version_requirements": ["GLIBC_2.7"]}}
        )
        self.assertIn("no libstdc++ dependency", caveat)


class ComposeSourceSetTests(unittest.TestCase):
    def test_reproduces_committed_uzem_source_set(self):
        # The composed document must self-validate and bind its pin exactly.
        try:
            composed = promote_core.compose_source_set(UZEM_ID)
        except promote_core.PromoteCoreError:
            self.skipTest("uzem promotion evidence not present")
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from profile_registry import validate_source_set

        validate_source_set(composed)
        self.assertEqual(UZEM_ID, composed["source_set_id"])
        self.assertEqual(
            f"pins/core-sets/{UZEM_ID}.json", composed["evidence_pin"]["path"]
        )

    def test_canonical_composer_rejects_genuine_easyrpg_candidate(self):
        with self.assertRaisesRegex(
            promote_core.PromoteCoreError,
            "refuses source-candidate/output-reproduction evidence",
        ):
            promote_core.compose_source_set(EASYRPG_CANDIDATE_ID)

    def test_stripped_rehashed_candidate_still_differs_from_canonical_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            semantic_id = _stripped_easyrpg_pin(root)
            with mock.patch.object(promote_core, "ROOT", root), \
                    self.assertRaisesRegex(
                        promote_core.PromoteCoreError,
                        "source differs from the catalog source",
                    ):
                promote_core.compose_source_set(semantic_id)

    def test_canonicalized_candidate_summary_cannot_launder_raw_evidence(self):
        with _canonicalized_easyrpg_candidate_laundering() as fixture:
            semantic_id, _selected_run, _reproduction_run = fixture
            with self.assertRaisesRegex(
                promote_core.PromoteCoreError,
                "stored selected record source differs from golden",
            ):
                promote_core.compose_source_set(semantic_id)
            pin_path = ROOT / "pins" / "core-sets" / f"{semantic_id}.json"
            report = pipeline.authoritative_core_track_pin_report(
                pipeline.load_json(pin_path),
                pin_path,
            )
            self.assertEqual("invalid", report["status"])
            self.assertIn(
                "stored selected record source differs from golden",
                "\n".join(report["errors"]),
            )

    def test_low_level_projected_catalog_preserves_candidate_group_composition(self):
        pin = json.loads(
            (
                ROOT
                / "pins"
                / "core-sets"
                / f"{EASYRPG_CANDIDATE_ID}.json"
            ).read_text(encoding="utf-8")
        )
        selected_source = pin["cores"]["easyrpg"]["selection"]["targets"][
            "arm64"
        ]["golden_record"]["source"]
        catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(
                encoding="utf-8"
            )
        )
        catalog["cores"]["easyrpg"]["source"] = {
            "url": selected_source["url"],
            "requested_ref": selected_source["requested_ref"],
            "commit": selected_source["commit"],
            "tree": selected_source["tree"],
            "submodules": [
                {"path": item["path"], "commit": item["commit"]}
                for item in selected_source["submodules"]
            ],
        }
        composed = promote_core.records_source.compose_source_set(
            EASYRPG_CANDIDATE_ID,
            repository_root=ROOT,
            catalog=catalog,
        )
        self.assertEqual(
            selected_source["commit"],
            composed["sources"]["easyrpg"]["commit"],
        )


class ComposeCompatibilityTests(unittest.TestCase):
    def test_equal_outputs_do_not_claim_equal_build_logs(self):
        source = {
            "url": "https://example.invalid/demo.git",
            "resolved_url": "https://example.invalid/demo.git",
            "requested_ref": "refs/heads/main",
            "commit": "1" * 40,
            "resolved_commit": "1" * 40,
            "tree": "2" * 40,
            "submodules": [],
        }
        artifact = {
            "sha256": "a" * 64,
            "needed": [],
            "version_requirements": [],
        }
        golden_record = {"source": source, "artifact": artifact}
        golden = {
            "core_id": "demo",
            "pin_id": "demo-111111111111-333333333333",
            "content_sha256": "4" * 64,
            "build_goldens": {"demo": {"arm64": golden_record}},
        }
        selected = {
            "content_sha256": "b" * 64,
            "package_sha256": "c" * 64,
        }
        reproduction = {
            "content_sha256": "e" * 64,
            "package_sha256": "c" * 64,
        }
        selection = {
            "e2e": {
                "run_id": "selected",
                "content_sha256": selected["content_sha256"],
                "package_sha256": selected["package_sha256"],
            },
            "package": {"sha256": selected["package_sha256"]},
            "targets": {"arm64": {"golden_record": golden_record}},
        }
        pin = {
            "sources": [
                {
                    "path": ".local-e2e/nightlies/demo/golden.json",
                    "file_sha256": "5" * 64,
                    "content_sha256": golden["content_sha256"],
                }
            ]
        }
        semantic_pin = ("demo", pin, "6" * 64, selection)
        source_set = {
            "sources": {"demo": {"commit": source["commit"]}}
        }
        catalog = {
            "cores": {
                "demo": {
                    "source": {
                        key: source[key]
                        for key in (
                            "url",
                            "requested_ref",
                            "commit",
                            "tree",
                            "submodules",
                        )
                    }
                }
            }
        }
        validate_e2e = mock.Mock(side_effect=(selected, reproduction))
        lifecycle_snapshot = promote_core._OrdinaryLifecycleSnapshot(
            source_set,
            semantic_pin,
            catalog,
            (),
        )
        with mock.patch.object(
            promote_core,
            "_ordinary_source_set_snapshot",
            return_value=lifecycle_snapshot,
        ), mock.patch.object(
            promote_core,
            "_load_with_sha256",
            return_value=(golden, "5" * 64),
        ), mock.patch.object(
            promote_core,
            "_exact_file_digest",
            return_value="7" * 64,
        ), mock.patch.object(
            promote_core,
            "_validation_pipeline",
            return_value=mock.Mock(
                _validate_compatibility_e2e_run=validate_e2e,
                validate_core_compatibility_document=mock.Mock(
                    return_value={"status": "valid", "errors": []}
                ),
            ),
        ):
            manifest = promote_core.compose_compatibility(
                "demo",
                "demo-111111111111-333333333333",
                "selected",
                "reproduction",
            )

        self.assertEqual(2, validate_e2e.call_count)
        self.assertEqual(
            ["selected", "reproduction"],
            [
                call.args[0].parent.name
                for call in validate_e2e.call_args_list
            ],
        )

        self.assertEqual("reproducible", manifest["package_state"])
        evidence_caveat = manifest["caveats"][0]
        self.assertIn("reproduced the exact demo_libretro.zip package bytes", evidence_caveat)
        self.assertIn("separate content-addressed execution evidence", evidence_caveat)
        self.assertIn("transcript byte equality is not required", evidence_caveat)
        self.assertNotIn("build logs byte for byte", evidence_caveat)

    def test_compatibility_rejects_genuine_easyrpg_candidate_before_runs(self):
        with mock.patch.object(
            promote_core,
            "_load",
            side_effect=AssertionError("run evidence must not be read"),
        ), self.assertRaisesRegex(
            promote_core.PromoteCoreError,
            "refuses source-candidate/output-reproduction evidence",
        ):
            promote_core.compose_compatibility(
                "easyrpg",
                EASYRPG_CANDIDATE_ID,
                "not-read-selected",
                "not-read-reproduction",
            )

    def test_compatibility_rejects_stripped_rehashed_candidate_before_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            semantic_id = _stripped_easyrpg_pin(root)
            compatibility_path = (
                root / "manifests" / "compatibility" / "easyrpg.json"
            )
            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(
                        promote_core,
                        "_load",
                        side_effect=AssertionError("run evidence must not be read"),
                    ), self.assertRaisesRegex(
                        promote_core.PromoteCoreError,
                        "source differs from the catalog source",
                    ):
                promote_core.compose_compatibility(
                    "easyrpg",
                    semantic_id,
                    "not-read-selected",
                    "not-read-reproduction",
                )
            self.assertFalse(compatibility_path.exists())

    def test_compose_lifecycle_candidate_failure_never_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            semantic_id = _stripped_easyrpg_pin(root)
            compatibility_path = (
                root / "manifests" / "compatibility" / "easyrpg.json"
            )
            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(
                        promote_core,
                        "_write_create_only",
                        side_effect=AssertionError("output write was attempted"),
                    ) as write:
                status = promote_core.main(
                    [
                        "compose-lifecycle",
                        "--core",
                        "easyrpg",
                        "--semantic-id",
                        semantic_id,
                        "--selected-run",
                        "not-read-selected",
                        "--reproduction-run",
                        "not-read-reproduction",
                    ]
                )
            self.assertEqual(1, status)
            write.assert_not_called()
            self.assertFalse(compatibility_path.exists())

    def test_canonicalized_candidate_raw_evidence_rejects_without_output(self):
        with _canonicalized_easyrpg_candidate_laundering() as fixture:
            semantic_id, selected_run, reproduction_run = fixture
            compatibility_path = (
                ROOT / "manifests" / "compatibility" / "easyrpg.json"
            )
            original_output = (
                compatibility_path.read_bytes()
                if compatibility_path.exists()
                else None
            )
            with self.assertRaisesRegex(
                promote_core.PromoteCoreError,
                "stored selected record source differs from golden",
            ):
                promote_core.compose_compatibility(
                    "easyrpg",
                    semantic_id,
                    selected_run,
                    reproduction_run,
                )
            with mock.patch.object(
                promote_core,
                "_write_create_only",
                side_effect=AssertionError("output write was attempted"),
            ) as write:
                status = promote_core.main(
                    [
                        "compose-lifecycle",
                        "--core",
                        "easyrpg",
                        "--semantic-id",
                        semantic_id,
                        "--selected-run",
                        selected_run,
                        "--reproduction-run",
                        reproduction_run,
                    ]
                )
            self.assertEqual(1, status)
            write.assert_not_called()
            if original_output is None:
                self.assertFalse(compatibility_path.exists())
            else:
                self.assertEqual(original_output, compatibility_path.read_bytes())

    def test_compose_lifecycle_rejects_e2e_swap_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "e2e-record.json"
            evidence_path.write_bytes(b"initial evidence\n")
            snapshot = promote_core._OrdinaryLifecycleSnapshot(
                source_set={"source_set_id": "demo"},
                semantic_pin=("demo", {}, "a" * 64, {}),
                catalog={},
                evidence_files=(
                    (
                        evidence_path,
                        hashlib.sha256(b"initial evidence\n").hexdigest(),
                        "selected compatibility E2E",
                    ),
                ),
            )

            def swap_evidence(*_args, **_kwargs):
                evidence_path.write_bytes(b"replacement evidence\n")
                return {"content_sha256": "b" * 64}, snapshot

            with mock.patch.object(
                promote_core,
                "_ordinary_source_set_snapshot",
                return_value=snapshot,
            ), mock.patch.object(
                promote_core,
                "_compose_compatibility_from_snapshot",
                side_effect=swap_evidence,
            ), mock.patch.object(
                promote_core,
                "_write_create_only",
                side_effect=AssertionError("output write was attempted"),
            ) as write:
                status = promote_core.main(
                    [
                        "compose-lifecycle",
                        "--core",
                        "demo",
                        "--semantic-id",
                        "demo-111111111111-222222222222",
                        "--selected-run",
                        "selected",
                        "--reproduction-run",
                        "reproduction",
                    ]
                )

            self.assertEqual(1, status)
            write.assert_not_called()

    def test_composes_valid_uzem_manifest_with_derived_device_caveat(self):
        try:
            manifest = promote_core.compose_compatibility(
                "uzem", UZEM_ID,
                "actions-sim-build-core-uzem-w3", "build-core-uzem-local-w3",
            )
        except promote_core.PromoteCoreError:
            self.skipTest("uzem promotion evidence not present")
        self.assertEqual(manifest["core_id"], "uzem")
        self.assertEqual(manifest["publication"], "disabled")
        self.assertEqual(manifest["package_state"], "reproducible")
        self.assertEqual(set(manifest["targets"]), {"arm64", "armhf"})
        self.assertEqual(
            manifest["golden_source"], f"pins/core-sets/{UZEM_ID}.json"
        )
        # The device caveat is derived, not retyped: uzem is over the Mini ceiling.
        self.assertTrue(
            any("Mini profile is ineligible" in c for c in manifest["caveats"])
        )
        # content_sha256 is self-consistent.
        self.assertEqual(
            manifest["content_sha256"], promote_core.content_sha256(manifest)
        )

    def test_extra_caveats_are_appended(self):
        try:
            manifest = promote_core.compose_compatibility(
                "uzem", UZEM_ID,
                "actions-sim-build-core-uzem-w3", "build-core-uzem-local-w3",
                extra_caveats=["GPLv3 review pending."],
            )
        except promote_core.PromoteCoreError:
            self.skipTest("uzem promotion evidence not present")
        self.assertEqual(manifest["caveats"][-1], "GPLv3 review pending.")


class FinishPromotionTests(unittest.TestCase):
    @staticmethod
    def _channel_from_args(args):
        return args[args.index("--channel") + 1]

    @staticmethod
    def _successful_channel_pipeline(root, calls, *, reject_current=False):
        semantic_id = "demo-aaaa-bbbb"

        def fake_pipeline(*args):
            calls.append(args)
            command = args[0]
            if command not in {"update-channel", "validate-channel"}:
                return ""
            channel = FinishPromotionTests._channel_from_args(args)
            pointer = (
                root / ".local-e2e" / "channels" / f"{channel}.demo.json"
            )
            if command == "validate-channel":
                raw = pointer.read_bytes()
                document = json.loads(raw.decode("utf-8"))
                status = (
                    "invalid"
                    if document.get("target", {}).get("id") != semantic_id
                    else "valid"
                )
                report = json.dumps(
                    {
                        "status": status,
                        "channel": channel,
                        "core_id": "demo",
                        "pointer_file_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
                if status == "invalid":
                    raise promote_core.PipelineCommandError(
                        "current pointer invalid", stdout=report, stderr=""
                    )
                return report
            if "--expect-current" in args and reject_current:
                raise promote_core.PromoteCoreError("current pointer invalid")
            target = {
                "id": semantic_id,
                "path": args[args.index("--target") + 1],
            }
            document = {
                "channel": channel,
                "core_id": "demo",
                "target": target,
            }
            raw = (json.dumps(document, sort_keys=True) + "\n").encode()
            pointer.write_bytes(raw)
            return json.dumps(
                {
                    "status": (
                        "created" if "--expect-absent" in args else "updated"
                    ),
                    "channel": channel,
                    "pointer_file_sha256": hashlib.sha256(raw).hexdigest(),
                    "target": target,
                }
            )

        return fake_pipeline

    def test_dangling_pointer_falls_back_to_expect_absent(self):
        calls = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            for channel in ("nightly", "pinned", "release"):
                (channels / f"{channel}.demo.json").write_text(
                    '{"target": {"id": "demo-aaaa-old1"}}', encoding="utf-8"
                )
            fake_pipeline = self._successful_channel_pipeline(
                root, calls, reject_current=True
            )
            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(promote_core, "_pipeline", fake_pipeline):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")
            for channel in ("nightly", "pinned", "release"):
                pointer = json.loads(
                    (channels / f"{channel}.demo.json").read_text(encoding="utf-8")
                )
                self.assertEqual("demo-aaaa-bbbb", pointer["target"]["id"])
        swaps = [c for c in calls if c[0] == "update-channel"]
        self.assertEqual(6, len(swaps))  # one failed CAS + one create per channel
        self.assertEqual(3, sum("--expect-absent" in c for c in swaps))
        validates = [c for c in calls if c[0] == "validate-channel"]
        self.assertEqual(6, len(validates))  # invalid preflight + valid final proof

    def test_pointer_already_current_still_uses_digest_compare_and_swap(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            for channel in ("nightly", "pinned", "release"):
                (channels / f"{channel}.demo.json").write_text(
                    '{"target": {"id": "demo-aaaa-bbbb"}}', encoding="utf-8"
                )
            fake_pipeline = self._successful_channel_pipeline(root, calls)
            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(promote_core, "_pipeline", fake_pipeline):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")
        swaps = [c for c in calls if c[0] == "update-channel"]
        self.assertEqual(3, len(swaps))
        self.assertTrue(all("--expect-current" in call for call in swaps))
        self.assertTrue(all("--expect-absent" not in call for call in swaps))
        self.assertEqual(6, sum(c[0] == "validate-channel" for c in calls))

    def test_pointer_snapshot_hashes_the_same_strict_utf8_bytes_it_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            pointer = Path(tmp) / "pointer.json"
            pointer.write_text('{"target":{"id":"original"}}\n', encoding="utf-8")
            original = pointer.read_bytes()
            replacement = b'{"target":{"id":"replacement"}}\n'
            with mock.patch.object(
                Path, "read_bytes", side_effect=(original, replacement)
            ) as read_bytes:
                snapshot = promote_core._pointer_snapshot(pointer)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(original, snapshot[0])
        self.assertEqual("original", snapshot[1]["target"]["id"])
        self.assertEqual(hashlib.sha256(original).hexdigest(), snapshot[2])
        read_bytes.assert_called_once_with()

    def test_finish_rejects_non_utf8_channel_pointer_without_mutation(self):
        for encoding in ("utf-16", "utf-32"):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                channels = root / ".local-e2e" / "channels"
                channels.mkdir(parents=True)
                (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                    parents=True
                )
                pointer = channels / "nightly.demo.json"
                raw = json.dumps(
                    {"target": {"id": "demo-aaaa-bbbb"}}
                ).encode(encoding)
                pointer.write_bytes(raw)
                calls = []

                with mock.patch.object(promote_core, "ROOT", root), \
                        mock.patch.object(
                            promote_core,
                            "_pipeline",
                            lambda *args: calls.append(args) or "",
                        ), self.assertRaisesRegex(
                            promote_core.PromoteCoreError,
                            "invalid channel pointer",
                        ):
                    promote_core.finish_promotion("demo", "demo-aaaa-bbbb")

                self.assertEqual(raw, pointer.read_bytes())
                self.assertFalse(any(call[0] == "update-channel" for call in calls))

    def test_failed_cas_never_removes_a_replacement_pointer(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            pointer = channels / "nightly.demo.json"
            pointer.write_text(
                '{"channel":"nightly","core_id":"demo",'
                '"target":{"id":"demo-old"}}\n',
                encoding="utf-8",
            )
            replacement = (
                '{"channel":"nightly","core_id":"demo",'
                '"target":{"id":"replacement"}}\n'
            ).encode()

            def fake_pipeline(*args):
                calls.append(args)
                if args[0] == "validate-channel":
                    raw = pointer.read_bytes()
                    return json.dumps(
                        {
                            "status": "invalid",
                            "channel": "nightly",
                            "core_id": "demo",
                            "pointer_file_sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
                if args[0] == "update-channel":
                    pointer.write_bytes(replacement)
                    raise promote_core.PromoteCoreError("compare-and-swap failed")
                return ""

            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(promote_core, "_pipeline", fake_pipeline), \
                    self.assertRaisesRegex(
                        promote_core.PromoteCoreError,
                        "changed after compare-and-swap failure",
                    ):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")

            self.assertEqual(replacement, pointer.read_bytes())
            self.assertFalse(
                any("--expect-absent" in call for call in calls)
            )

    def test_valid_pointer_is_preserved_when_new_target_update_fails(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            pointer = channels / "nightly.demo.json"
            original = (
                '{"channel":"nightly","core_id":"demo",'
                '"target":{"id":"demo-old"}}\n'
            ).encode()
            pointer.write_bytes(original)

            def fake_pipeline(*args):
                calls.append(args)
                if args[0] == "validate-channel":
                    return json.dumps(
                        {
                            "status": "valid",
                            "channel": "nightly",
                            "core_id": "demo",
                            "pointer_file_sha256": hashlib.sha256(original).hexdigest(),
                        }
                    )
                if args[0] == "update-channel":
                    raise promote_core.PromoteCoreError("new target is invalid")
                return ""

            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(promote_core, "_pipeline", fake_pipeline), \
                    self.assertRaisesRegex(
                        promote_core.PromoteCoreError, "new target is invalid"
                    ):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")

            self.assertEqual(original, pointer.read_bytes())
            self.assertFalse(
                any("--expect-absent" in call for call in calls)
            )

    def test_replacement_after_validation_is_never_reported_as_accepted(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            pointer = channels / "nightly.demo.json"
            target = {
                "id": "demo-aaaa-bbbb",
                "path": ".local-e2e/nightlies/demo-aaaa-bbbb/golden.json",
            }
            accepted = (
                json.dumps(
                    {"channel": "nightly", "core_id": "demo", "target": target},
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            accepted_digest = hashlib.sha256(accepted).hexdigest()
            replacement = (
                json.dumps(
                    {
                        "channel": "nightly",
                        "core_id": "demo",
                        "target": {"id": "replacement"},
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode()

            def fake_pipeline(*args):
                calls.append(args)
                if args[0] == "update-channel":
                    pointer.write_bytes(accepted)
                    return json.dumps(
                        {
                            "status": "created",
                            "channel": "nightly",
                            "pointer_file_sha256": accepted_digest,
                            "target": target,
                        }
                    )
                if args[0] == "validate-channel":
                    pointer.write_bytes(replacement)
                    return json.dumps(
                        {
                            "status": "valid",
                            "channel": "nightly",
                            "core_id": "demo",
                            "pointer_file_sha256": accepted_digest,
                        }
                    )
                return ""

            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(promote_core, "_pipeline", fake_pipeline), \
                    self.assertRaisesRegex(
                        promote_core.PromoteCoreError,
                        "changed after validation",
                    ):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")

            self.assertEqual(replacement, pointer.read_bytes())


class RunWaveTests(unittest.TestCase):
    def test_wave_refuses_a_dirty_tree(self):
        with mock.patch.object(
            promote_core, "_worktree_is_clean", lambda: False
        ):
            with self.assertRaises(promote_core.PromoteCoreError):
                promote_core.run_wave(
                    ["demo"], "wX", refresh=True,
                    carry_caveats=True, finish=True,
                )

    def test_wave_builds_every_core_before_any_promote(self):
        order = []

        def fake_pipeline(*args):
            order.append((args[0], args[args.index("--core") + 1]))
            return ""

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(promote_core, "ROOT", Path(tmp)), \
                mock.patch.object(promote_core, "_worktree_is_clean",
                                  lambda: True), \
                mock.patch.object(promote_core, "_pipeline", fake_pipeline), \
                mock.patch.object(promote_core, "run_promotion",
                                  lambda core, *a, **k: order.append(
                                      ("promote", core)) or f"{core}-x-y"), \
                mock.patch.object(promote_core, "finish_promotion",
                                  lambda *a: None), \
                mock.patch.object(promote_core, "_write_evidence_index",
                                  lambda core: None):
            promote_core.run_wave(
                ["one", "two"], "wX", refresh=True,
                carry_caveats=False, finish=True,
            )
        first_promote = order.index(("promote", "one"))
        builds_after = [
            entry for entry in order[first_promote:]
            if entry[0] == "build-core"
        ]
        self.assertEqual([], builds_after)
        self.assertEqual(4, sum(e[0] == "build-core" for e in order))


if __name__ == "__main__":
    unittest.main()
