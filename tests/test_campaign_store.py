from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from scripts.core_pipeline_lib.campaign.model import (
    CheckResult,
    EvidenceRef,
    Receipt,
)
from scripts.core_pipeline_lib.campaign.store import (
    FAULT_SEAMS,
    CampaignStore,
    PointerState,
    PointerTransaction,
    StoreResult,
    TransactionView,
    VerificationView,
    canonical_object_reference,
)
from scripts.core_pipeline_lib.errors import PipelineError
import scripts.core_pipeline_lib.campaign.store as store_module


CAMPAIGN_ID = "core-build-campaign-v1"
POINTER_PATH = "campaign-matrix.json"


class InjectedFault(RuntimeError):
    pass


class FailAt:
    def __init__(self, seam: str) -> None:
        if seam not in FAULT_SEAMS:
            raise AssertionError(f"unknown seam in test: {seam}")
        self.seam = seam
        self.events: list[str] = []
        self.triggered = False

    def __call__(self, seam: str) -> None:
        self.events.append(seam)
        if seam == self.seam and not self.triggered:
            self.triggered = True
            raise InjectedFault(seam)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pointer_reference(
    raw: bytes,
    *,
    path: str = POINTER_PATH,
    kind: str = "matrix-pointer",
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=_digest(raw),
        target_content_sha256=_digest(b"semantic\x00" + raw),
        size=len(raw),
    )


def _plan_reference() -> EvidenceRef:
    return EvidenceRef(
        kind="transition-plan",
        path="fixtures/campaign/plan.json",
        file_sha256=_digest(b"plan raw"),
        target_content_sha256=_digest(b"plan semantic"),
        size=len(b"plan raw"),
    )


def _receipt(stage: str, *, passed: bool = True) -> Receipt:
    check = CheckResult(
        check_id="campaign.plan.identity",
        subject_sha256=_digest(b"plan semantic"),
        status="passed" if passed else "failed",
        message=None if passed else "injected validation failure",
    )
    return Receipt(
        transition_id="transition-1",
        plan=_plan_reference(),
        stage=stage,
        status="passed" if passed else "failed",
        started_at="2026-08-14T12:00:00Z",
        completed_at="2026-08-14T12:00:01Z",
        checks=(check,),
    )


PRE_COMMIT_RECEIPT = _receipt("pre-commit")
POST_COMMIT_RECEIPT = _receipt("post-commit")


def _stage_required(
    store: CampaignStore,
    *,
    raw: bytes = b"immutable transaction evidence\n",
) -> tuple[EvidenceRef, ...]:
    reference = store.reference_for(
        kind="artifact",
        raw=raw,
        target_content_sha256=None,
    )
    store.create_or_verify(reference=reference, raw=raw)
    return (reference,)


def _transaction(
    store: CampaignStore,
    *,
    expected: EvidenceRef | None,
    successor: EvidenceRef,
    successor_raw: bytes,
    required_objects: tuple[EvidenceRef, ...],
):
    return store.pointer_transaction(
        campaign_id=CAMPAIGN_ID,
        expected=expected,
        successor=successor,
        successor_raw=successor_raw,
        required_objects=required_objects,
    )


def _commit(
    store: CampaignStore,
    *,
    expected: EvidenceRef | None,
    successor: EvidenceRef,
    successor_raw: bytes,
    required_objects: tuple[EvidenceRef, ...],
):
    pre_receipt = _receipt("pre-commit")
    post_receipt = _receipt("post-commit")
    result = _transaction(
        store,
        expected=expected,
        successor=successor,
        successor_raw=successor_raw,
        required_objects=required_objects,
    ).commit(
        pre_commit=lambda _view: pre_receipt,
        post_commit=lambda _view: post_receipt,
    )
    return result, pre_receipt, post_receipt


def _install_verification_pointer_and_lock(
    repository_root: Path,
    *,
    reference: EvidenceRef,
    raw: bytes,
) -> Path:
    pointer_path = repository_root / reference.path
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_bytes(raw)
    pointer_path.chmod(0o644)
    lock_path = (
        repository_root
        / "campaign-state"
        / "locks"
        / f"{CAMPAIGN_ID}.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    return lock_path


def _tree_fingerprint(repository_root: Path) -> tuple[tuple[object, ...], ...]:
    entries: list[tuple[object, ...]] = []
    for path in sorted(repository_root.rglob("*")):
        metadata = path.lstat()
        entries.append(
            (
                path.relative_to(repository_root).as_posix(),
                stat.S_IFMT(metadata.st_mode),
                stat.S_IMODE(metadata.st_mode),
                metadata.st_nlink,
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None,
            )
        )
    return tuple(entries)


class CampaignStoreTests(unittest.TestCase):
    def test_canonical_object_reference_is_pure_and_matches_store(self) -> None:
        raw = b"strict phase freeze bytes\n"
        expected = canonical_object_reference(
            state_relative=".local-e2e/campaign-state",
            kind="phase-freeze-cas",
            raw=raw,
            target_content_sha256=_digest(b"semantic phase freeze"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CampaignStore(root, ".local-e2e/campaign-state")
            self.assertEqual(
                store.reference_for(
                    kind="phase-freeze-cas",
                    raw=raw,
                    target_content_sha256=_digest(b"semantic phase freeze"),
                ),
                expected,
            )
            self.assertFalse((root / ".local-e2e").exists())

        self.assertEqual(
            expected.path,
            ".local-e2e/campaign-state/objects/phase-freeze-cas/sha256/"
            f"{_digest(raw)[:2]}/{_digest(raw)}",
        )
        for state_relative in ("", "/absolute", "state/../escape", "state//x"):
            with self.subTest(state_relative=state_relative):
                with self.assertRaises(PipelineError):
                    canonical_object_reference(
                        state_relative=state_relative,
                        kind="phase-freeze-cas",
                        raw=raw,
                        target_content_sha256=_digest(b"semantic phase freeze"),
                    )
        with self.assertRaises(PipelineError):
            canonical_object_reference(
                state_relative="state",
                kind="not-an-evidence-kind",
                raw=raw,
                target_content_sha256=None,
            )
        with self.assertRaises(PipelineError):
            canonical_object_reference(
                state_relative="state",
                kind="artifact",
                raw=bytearray(raw),  # type: ignore[arg-type]
                target_content_sha256=None,
            )

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.repository_root = Path(self._temporary.name)

    def store(self, *, fault_hook=None) -> CampaignStore:
        return CampaignStore(
            self.repository_root,
            "campaign-state",
            fault_hook=fault_hook,
        )

    def test_read_pointer_is_no_create_exact_and_byte_opaque(self) -> None:
        store = self.store()
        raw = b"\xff\x00legacy pointer bytes are not JSON\n"
        reference = _pointer_reference(raw)

        self.assertIsNone(store.read_pointer(reference))
        self.assertEqual([], list(self.repository_root.iterdir()))

        pointer_path = self.repository_root / reference.path
        pointer_path.write_bytes(raw)
        pointer_path.chmod(0o644)
        state = store.read_pointer(reference)
        self.assertEqual(PointerState(reference=reference, raw=raw), state)
        self.assertFalse((self.repository_root / "campaign-state").exists())

        wrong = _pointer_reference(b"different pointer bytes")
        with self.assertRaisesRegex(PipelineError, "do not match"):
            store.read_pointer(wrong)

    def test_read_snapshot_is_no_create_and_returns_exact_tracked_bytes(self) -> None:
        store = self.store()
        with self.assertRaisesRegex(PipelineError, "snapshot is missing"):
            store.read_snapshot("tracked/transition-spec.json")
        self.assertEqual([], list(self.repository_root.iterdir()))

        tracked = self.repository_root / "tracked"
        tracked.mkdir()
        snapshot_path = tracked / "transition-spec.json"
        raw = b"{\"tracked\":true}\n"
        snapshot_path.write_bytes(raw)
        snapshot_path.chmod(0o644)

        self.assertEqual(raw, store.read_snapshot("tracked/transition-spec.json"))
        self.assertFalse((self.repository_root / "campaign-state").exists())

        for relative in ("", "../escape", "/absolute", "tracked//invalid"):
            with self.subTest(relative=relative), self.assertRaises(PipelineError):
                store.read_snapshot(relative)

    def test_read_snapshot_rejects_symlinks_hardlinks_and_fifo(self) -> None:
        store = self.store()
        outside = self.repository_root / "outside"
        outside.mkdir()
        outside_file = outside / "source"
        outside_file.write_bytes(b"outside")
        outside_file.chmod(0o644)

        (self.repository_root / "linked-parent").symlink_to(
            outside,
            target_is_directory=True,
        )
        with self.assertRaises(PipelineError):
            store.read_snapshot("linked-parent/source")

        tracked = self.repository_root / "tracked"
        tracked.mkdir()
        (tracked / "symlink").symlink_to(outside_file)
        with self.assertRaises(PipelineError):
            store.read_snapshot("tracked/symlink")

        hardlink = tracked / "hardlink"
        hardlink.write_bytes(b"linked bytes")
        hardlink.chmod(0o644)
        os.link(hardlink, tracked / "second-link")
        with self.assertRaisesRegex(PipelineError, "link count"):
            store.read_snapshot("tracked/hardlink")

        fifo = tracked / "fifo"
        os.mkfifo(fifo, 0o644)
        with self.assertRaisesRegex(PipelineError, "regular file"):
            store.read_snapshot("tracked/fifo")
        self.assertFalse((self.repository_root / "campaign-state").exists())

    def test_read_snapshot_rejects_replacement_during_single_fd_read(self) -> None:
        store = self.store()
        tracked = self.repository_root / "tracked"
        tracked.mkdir()
        snapshot_path = tracked / "engine-bundle.json"
        original = b"original tracked snapshot"
        replacement = b"foreign replacement snapshot"
        snapshot_path.write_bytes(original)
        snapshot_path.chmod(0o644)
        real_read = os.read
        replaced = False

        def racing_read(file_descriptor: int, size: int) -> bytes:
            nonlocal replaced
            block = real_read(file_descriptor, size)
            if block and not replaced:
                replaced = True
                candidate = tracked / "replacement.tmp"
                candidate.write_bytes(replacement)
                candidate.chmod(0o644)
                os.replace(candidate, snapshot_path)
            return block

        with mock.patch.object(store_module.os, "read", side_effect=racing_read):
            with self.assertRaisesRegex(
                PipelineError,
                r"changed (?:while|after) it was read",
            ):
                store.read_snapshot("tracked/engine-bundle.json")
        self.assertEqual(replacement, snapshot_path.read_bytes())

    def test_reopened_repository_root_must_match_pinned_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            repository = parent / "repository"
            repository.mkdir()
            store = CampaignStore(repository, "campaign-state")
            raw = b"pointer must not move to a replacement repository"
            reference = _pointer_reference(raw)

            original = parent / "original-repository"
            repository.rename(original)
            repository.mkdir()

            with self.assertRaisesRegex(PipelineError, "root identity changed"):
                store.read_snapshot("tracked/transition-spec.json")
            with self.assertRaisesRegex(PipelineError, "root identity changed"):
                store.read_pointer(reference)
            self.assertEqual([], list(repository.iterdir()))

    def test_semantic_target_does_not_make_store_parse_domain_bytes(self) -> None:
        store = self.store()
        raw = b"\xffnot-json-and-not-a-state-root"
        reference = store.reference_for(
            kind="state-root",
            raw=raw,
            target_content_sha256=_digest(b"caller-validated semantic identity"),
        )

        self.assertEqual(
            "created",
            store.create_or_verify(reference=reference, raw=raw).disposition,
        )
        self.assertEqual(raw, store.read_exact(reference))

    def test_content_addressed_create_verify_and_collision_are_exact(self) -> None:
        events: list[str] = []
        store = self.store(fault_hook=events.append)
        raw = b"raw campaign artifact\n"
        reference = store.reference_for(
            kind="artifact",
            raw=raw,
            target_content_sha256=None,
        )

        created = store.create_or_verify(reference=reference, raw=raw)
        self.assertEqual(StoreResult(reference, "created"), created)
        destination = self.repository_root / reference.path
        destination_stat = destination.stat()
        self.assertEqual(raw, destination.read_bytes())
        self.assertEqual(0o644, stat.S_IMODE(destination_stat.st_mode))
        self.assertEqual(1, destination_stat.st_nlink)
        self.assertEqual(
            [
                "cas.after_temp_create",
                "cas.after_file_fsync",
                "cas.after_publish",
                "cas.after_directory_fsync",
            ],
            events,
        )

        events.clear()
        self.assertEqual(
            StoreResult(reference, "verified"),
            store.create_or_verify(reference=reference, raw=raw),
        )
        self.assertEqual([], events)

        destination.write_bytes(b"foreign collision bytes\n")
        with self.assertRaisesRegex(PipelineError, "collision"):
            store.create_or_verify(reference=reference, raw=raw)
        self.assertEqual(b"foreign collision bytes\n", destination.read_bytes())

    def test_exact_cas_verification_fsyncs_without_create_fault_seams(self) -> None:
        events: list[str] = []
        store = self.store(fault_hook=events.append)
        raw = b"already-published exact object"
        reference = store.reference_for(
            kind="artifact",
            raw=raw,
            target_content_sha256=None,
        )
        store.create_or_verify(reference=reference, raw=raw)
        events.clear()
        fsync_targets: list[str] = []
        real_fsync = os.fsync

        def record_fsync(file_descriptor: int) -> None:
            mode = os.fstat(file_descriptor).st_mode
            fsync_targets.append("directory" if stat.S_ISDIR(mode) else "file")
            real_fsync(file_descriptor)

        with mock.patch.object(store_module.os, "fsync", side_effect=record_fsync):
            result = store.create_or_verify(reference=reference, raw=raw)

        self.assertEqual("verified", result.disposition)
        self.assertEqual(["directory"], fsync_targets)
        self.assertEqual([], events)

    def test_content_addressed_path_is_code_owned(self) -> None:
        store = self.store()
        raw = b"canonical object"
        reference = store.reference_for(
            kind="artifact",
            raw=raw,
            target_content_sha256=None,
        )
        wrong_path = EvidenceRef(
            kind=reference.kind,
            path="campaign-state/objects/artifact/attacker",
            file_sha256=reference.file_sha256,
            target_content_sha256=None,
            size=reference.size,
        )

        with self.assertRaisesRegex(PipelineError, "not canonical"):
            store.create_or_verify(reference=wrong_path, raw=raw)
        self.assertFalse((self.repository_root / wrong_path.path).exists())

    def test_caller_authorized_immutable_reference_create_and_verify(self) -> None:
        events: list[str] = []
        store = self.store(fault_hook=events.append)
        raw = b"historical semantic snapshot\n"
        reference = EvidenceRef(
            kind="matrix-snapshot",
            path="historical/campaign/matrix-snapshot.json",
            file_sha256=_digest(raw),
            target_content_sha256=_digest(b"historical semantic matrix"),
            size=len(raw),
        )

        self.assertEqual(
            StoreResult(reference, "created"),
            store.create_or_verify_reference(reference=reference, raw=raw),
        )
        self.assertEqual(raw, (self.repository_root / reference.path).read_bytes())
        self.assertEqual(
            [
                "cas.after_temp_create",
                "cas.after_file_fsync",
                "cas.after_publish",
                "cas.after_directory_fsync",
            ],
            events,
        )

        events.clear()
        self.assertEqual(
            StoreResult(reference, "verified"),
            store.create_or_verify_reference(reference=reference, raw=raw),
        )
        self.assertEqual([], events)

    def test_caller_authorized_reference_rejects_pointer_kind(self) -> None:
        store = self.store()
        raw = b"must not create mutable authority"
        reference = _pointer_reference(raw)

        with self.assertRaisesRegex(PipelineError, "rejects matrix-pointer"):
            store.create_or_verify_reference(reference=reference, raw=raw)
        self.assertFalse((self.repository_root / reference.path).exists())

    def test_caller_authorized_reference_is_nofollow_and_collision_safe(
        self,
    ) -> None:
        store = self.store()
        raw = b"historical raw CAS alias"
        reference = EvidenceRef(
            kind="matrix-cas",
            path="historical/raw/matrix.json",
            file_sha256=_digest(raw),
            target_content_sha256=None,
            size=len(raw),
        )
        outside = self.repository_root / "outside"
        outside.mkdir()
        (self.repository_root / "historical").symlink_to(
            outside,
            target_is_directory=True,
        )
        with self.assertRaises(PipelineError):
            store.create_or_verify_reference(reference=reference, raw=raw)
        self.assertEqual([], list(outside.iterdir()))

        (self.repository_root / "historical").unlink()
        destination = self.repository_root / reference.path
        destination.parent.mkdir(parents=True)
        outside_file = outside / "foreign"
        outside_file.write_bytes(b"foreign symlink target")
        destination.symlink_to(outside_file)
        with self.assertRaises(PipelineError):
            store.create_or_verify_reference(reference=reference, raw=raw)
        self.assertEqual(b"foreign symlink target", outside_file.read_bytes())

        destination.unlink()
        destination.write_bytes(b"foreign collision")
        destination.chmod(0o644)
        with self.assertRaisesRegex(PipelineError, "collision"):
            store.create_or_verify_reference(reference=reference, raw=raw)
        self.assertEqual(b"foreign collision", destination.read_bytes())

    def test_content_addressed_faults_retain_only_valid_published_orphans(
        self,
    ) -> None:
        for seam, should_exist in (
            ("cas.after_temp_create", False),
            ("cas.after_file_fsync", False),
            ("cas.after_publish", True),
            ("cas.after_directory_fsync", True),
        ):
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fail = FailAt(seam)
                store = CampaignStore(root, "campaign-state", fault_hook=fail)
                raw = f"artifact for {seam}\n".encode()
                reference = store.reference_for(
                    kind="artifact",
                    raw=raw,
                    target_content_sha256=None,
                )
                with self.assertRaisesRegex(InjectedFault, seam):
                    store.create_or_verify(reference=reference, raw=raw)

                destination = root / reference.path
                self.assertEqual(should_exist, destination.exists())
                self.assertEqual([], list(root.rglob(".tmp-*")))
                if should_exist:
                    events_before_retry = tuple(fail.events)
                    fsync_targets: list[str] = []
                    real_fsync = os.fsync

                    def record_fsync(file_descriptor: int) -> None:
                        mode = os.fstat(file_descriptor).st_mode
                        fsync_targets.append(
                            "directory" if stat.S_ISDIR(mode) else "file"
                        )
                        real_fsync(file_descriptor)

                    with mock.patch.object(
                        store_module.os,
                        "fsync",
                        side_effect=record_fsync,
                    ):
                        result = store.create_or_verify(
                            reference=reference,
                            raw=raw,
                        )
                    self.assertEqual("verified", result.disposition)
                    self.assertEqual(["directory"], fsync_targets)
                    self.assertEqual(events_before_retry, tuple(fail.events))

    def test_content_addressed_create_race_accepts_only_exact_winner(self) -> None:
        for exact in (True, False):
            with self.subTest(exact=exact), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                raw = b"race candidate"
                holder: dict[str, EvidenceRef] = {}
                events: list[str] = []

                def race(seam: str) -> None:
                    events.append(seam)
                    if seam != "cas.after_file_fsync":
                        return
                    reference = holder["reference"]
                    destination = root / reference.path
                    destination.write_bytes(raw if exact else b"foreign")
                    destination.chmod(0o644)

                store = CampaignStore(root, "campaign-state", fault_hook=race)
                reference = store.reference_for(
                    kind="artifact",
                    raw=raw,
                    target_content_sha256=None,
                )
                holder["reference"] = reference
                if exact:
                    result = store.create_or_verify(reference=reference, raw=raw)
                    self.assertEqual("verified", result.disposition)
                    self.assertEqual(raw, (root / reference.path).read_bytes())
                    self.assertEqual(
                        [
                            "cas.after_temp_create",
                            "cas.after_file_fsync",
                            "cas.after_directory_fsync",
                        ],
                        events,
                    )
                else:
                    with self.assertRaisesRegex(PipelineError, "collision"):
                        store.create_or_verify(reference=reference, raw=raw)
                    self.assertEqual(b"foreign", (root / reference.path).read_bytes())
                    self.assertEqual(
                        ["cas.after_temp_create", "cas.after_file_fsync"],
                        events,
                    )

    def test_store_rejects_symlinked_cas_paths_and_hardlinks(self) -> None:
        raw = b"no-follow candidate"
        for component in ("campaign-state", "objects", "artifact"):
            with (
                self.subTest(component=component),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                outside = root / "outside"
                outside.mkdir()
                store = CampaignStore(root, "campaign-state")
                reference = store.reference_for(
                    kind="artifact",
                    raw=raw,
                    target_content_sha256=None,
                )
                if component == "campaign-state":
                    (root / "campaign-state").symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                elif component == "objects":
                    (root / "campaign-state").mkdir()
                    (root / "campaign-state" / "objects").symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                else:
                    (root / "campaign-state" / "objects").mkdir(parents=True)
                    (root / "campaign-state" / "objects" / "artifact").symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                with self.assertRaises(PipelineError):
                    store.create_or_verify(reference=reference, raw=raw)
                self.assertEqual([], list(outside.iterdir()))

        store = self.store()
        reference = store.reference_for(
            kind="artifact",
            raw=raw,
            target_content_sha256=None,
        )
        destination = self.repository_root / reference.path
        destination.parent.mkdir(parents=True)
        outside_file = self.repository_root / "outside-file"
        outside_file.write_bytes(raw)
        destination.symlink_to(outside_file)
        with self.assertRaises(PipelineError):
            store.create_or_verify(reference=reference, raw=raw)
        self.assertEqual(raw, outside_file.read_bytes())

        destination.unlink()
        destination.write_bytes(raw)
        destination.chmod(0o644)
        second_link = self.repository_root / "second-link"
        os.link(destination, second_link)
        with self.assertRaisesRegex(PipelineError, "link count"):
            store.create_or_verify(reference=reference, raw=raw)

    def test_pointer_and_lock_paths_reject_symlinks_and_hardlinks(self) -> None:
        store = self.store()
        raw = b"opaque successor"
        nested = _pointer_reference(raw, path="pointers/campaign-matrix.json")
        outside = self.repository_root / "outside"
        outside.mkdir()
        (self.repository_root / "pointers").symlink_to(
            outside,
            target_is_directory=True,
        )
        with self.assertRaises(PipelineError):
            store.read_pointer(nested)
        self.assertEqual([], list(outside.iterdir()))

        (self.repository_root / "pointers").unlink()
        outside_file = outside / "foreign-pointer"
        outside_file.write_bytes(raw)
        (self.repository_root / POINTER_PATH).symlink_to(outside_file)
        reference = _pointer_reference(raw)
        with self.assertRaises(PipelineError):
            store.read_pointer(reference)
        self.assertEqual(raw, outside_file.read_bytes())

        (self.repository_root / POINTER_PATH).unlink()
        pointer_path = self.repository_root / POINTER_PATH
        pointer_path.write_bytes(raw)
        pointer_path.chmod(0o644)
        os.link(pointer_path, self.repository_root / "pointer-hardlink")
        with self.assertRaisesRegex(PipelineError, "link count"):
            store.read_pointer(reference)

        pointer_path.unlink()
        (self.repository_root / "pointer-hardlink").unlink()
        required = _stage_required(store)
        locks = self.repository_root / "campaign-state" / "locks"
        locks.mkdir()
        foreign_lock = outside / "foreign.lock"
        foreign_lock.write_bytes(b"foreign")
        (locks / f"{CAMPAIGN_ID}.lock").symlink_to(foreign_lock)
        with self.assertRaises(PipelineError):
            _transaction(
                store,
                expected=None,
                successor=reference,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertEqual(b"foreign", foreign_lock.read_bytes())
        self.assertFalse(pointer_path.exists())

    def test_successful_commit_uses_one_lock_pointer_last_and_exact_receipts(
        self,
    ) -> None:
        events: list[str] = []
        store = self.store(fault_hook=events.append)
        required = _stage_required(store)
        events.clear()
        raw = b"\xffopaque campaign matrix successor\x00"
        successor = _pointer_reference(raw)
        pre_receipt = _receipt("pre-commit")
        post_receipt = _receipt("post-commit")
        observations: list[PointerState | None] = []

        def pre(view: TransactionView) -> Receipt:
            self.assertEqual(CAMPAIGN_ID, view.campaign_id)
            self.assertIsNone(view.expected)
            self.assertEqual(successor, view.successor)
            self.assertEqual(
                store.read_exact(required[0]),
                view.read_exact(required[0]),
            )
            observations.append(view.read_pointer(successor))
            return pre_receipt

        def post(view: TransactionView) -> Receipt:
            observations.append(view.read_pointer(successor))
            return post_receipt

        transaction = _transaction(
            store,
            expected=None,
            successor=successor,
            successor_raw=raw,
            required_objects=required,
        )
        self.assertEqual(successor, transaction.successor_reference)
        self.assertIsNone(transaction.expected_reference)

        real_flock = fcntl.flock
        with mock.patch.object(store_module.fcntl, "flock", wraps=real_flock) as flock:
            result = transaction.commit(pre_commit=pre, post_commit=post)

        self.assertIsNone(result.before)
        self.assertEqual(PointerState(successor, raw), result.after)
        self.assertIs(pre_receipt, result.pre_commit)
        self.assertIs(post_receipt, result.post_commit)
        self.assertEqual([None, result.after], observations)
        lock_operations = [call.args[1] for call in flock.call_args_list]
        self.assertEqual(1, lock_operations.count(fcntl.LOCK_EX))
        self.assertEqual(1, lock_operations.count(fcntl.LOCK_UN))
        self.assertEqual(
            (
                "pointer.after_lock",
                "pointer.after_cas",
                "pointer.after_required_verify",
                "pointer.after_pre_commit",
                "pointer.after_temp_create",
                "pointer.after_file_fsync",
                "pointer.before_replace",
                "pointer.after_replace",
                "pointer.after_directory_fsync",
                "pointer.after_post_commit",
            ),
            tuple(events),
        )
        self.assertEqual(raw, (self.repository_root / POINTER_PATH).read_bytes())

    def test_verify_pointer_requires_existing_lock_without_creating_state(
        self,
    ) -> None:
        for existing_parents in (False, True):
            with (
                self.subTest(existing_parents=existing_parents),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                store = CampaignStore(root, "campaign-state")
                raw = b"read-only pointer verification"
                reference = _pointer_reference(raw)
                pointer_path = root / reference.path
                pointer_path.write_bytes(raw)
                pointer_path.chmod(0o644)
                if existing_parents:
                    (root / "campaign-state" / "locks").mkdir(parents=True)
                before = _tree_fingerprint(root)

                with self.assertRaisesRegex(PipelineError, "lock is missing"):
                    store.verify_pointer(
                        campaign_id=CAMPAIGN_ID,
                        expected=reference,
                        validator=lambda _view: None,
                    )

                self.assertEqual(before, _tree_fingerprint(root))

    def test_verify_pointer_shared_callback_is_exact_and_read_only(self) -> None:
        events: list[str] = []
        store = self.store(fault_hook=events.append)
        immutable = _stage_required(store)
        events.clear()
        raw = b"exact pointer selected for read-only verification"
        reference = _pointer_reference(raw)
        _install_verification_pointer_and_lock(
            self.repository_root,
            reference=reference,
            raw=raw,
        )
        before = _tree_fingerprint(self.repository_root)
        seen: list[PointerState | None] = []
        returned = object()

        def validate(view: VerificationView) -> object:
            self.assertIs(type(view), VerificationView)
            self.assertEqual(CAMPAIGN_ID, view.campaign_id)
            self.assertEqual(reference, view.expected)
            self.assertEqual(
                store.read_exact(immutable[0]),
                view.read_exact(immutable[0]),
            )
            seen.append(view.read_pointer(reference))
            return returned

        real_flock = fcntl.flock
        with mock.patch.object(store_module.fcntl, "flock", wraps=real_flock) as flock:
            result = store.verify_pointer(
                campaign_id=CAMPAIGN_ID,
                expected=reference,
                validator=validate,
            )

        self.assertIs(returned, result)
        self.assertEqual([PointerState(reference, raw)], seen)
        self.assertEqual(
            [fcntl.LOCK_SH, fcntl.LOCK_UN],
            [call.args[1] for call in flock.call_args_list],
        )
        self.assertEqual([], events)
        self.assertEqual(before, _tree_fingerprint(self.repository_root))
        self.assertEqual([], list(self.repository_root.rglob(".tmp-*")))

    def test_verify_pointer_rejects_callback_pointer_drift_or_replacement(
        self,
    ) -> None:
        for change in ("raw-drift", "same-raw-replacement"):
            with (
                self.subTest(change=change),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                store = CampaignStore(root, "campaign-state")
                raw = b"pointer verification inode"
                reference = _pointer_reference(raw)
                _install_verification_pointer_and_lock(
                    root,
                    reference=reference,
                    raw=raw,
                )
                pointer_path = root / reference.path

                def mutate(_view: VerificationView) -> None:
                    if change == "raw-drift":
                        pointer_path.write_bytes(b"foreign pointer bytes")
                        return
                    replacement = root / "replacement-pointer.tmp"
                    replacement.write_bytes(raw)
                    replacement.chmod(0o644)
                    os.replace(replacement, pointer_path)

                with self.assertRaises(PipelineError):
                    store.verify_pointer(
                        campaign_id=CAMPAIGN_ID,
                        expected=reference,
                        validator=mutate,
                    )

    def test_verify_pointer_rejects_callback_lock_replacement(self) -> None:
        store = self.store()
        raw = b"pointer protected by stable verification lock"
        reference = _pointer_reference(raw)
        lock_path = _install_verification_pointer_and_lock(
            self.repository_root,
            reference=reference,
            raw=raw,
        )

        def replace_lock(_view: VerificationView) -> None:
            replacement = lock_path.with_name("replacement.lock")
            replacement.write_bytes(b"")
            replacement.chmod(0o600)
            os.replace(replacement, lock_path)

        with self.assertRaisesRegex(PipelineError, "lock changed while held"):
            store.verify_pointer(
                campaign_id=CAMPAIGN_ID,
                expected=reference,
                validator=replace_lock,
            )

    def test_verify_pointer_rejects_lock_replacement_after_each_snapshot(
        self,
    ) -> None:
        for replacement_after_read in (1, 2):
            with (
                self.subTest(replacement_after_read=replacement_after_read),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                store = CampaignStore(root, "campaign-state")
                raw = b"pointer with snapshot-adjacent lock identity"
                reference = _pointer_reference(raw)
                lock_path = _install_verification_pointer_and_lock(
                    root,
                    reference=reference,
                    raw=raw,
                )
                original_read = store._read_pointer_with_snapshot
                read_count = 0
                validator_called = False

                def read_then_replace_lock(expected: EvidenceRef):
                    nonlocal read_count
                    result = original_read(expected)
                    read_count += 1
                    if read_count == replacement_after_read:
                        replacement = lock_path.with_name(
                            f"replacement-{replacement_after_read}.lock"
                        )
                        replacement.write_bytes(b"")
                        replacement.chmod(0o600)
                        os.replace(replacement, lock_path)
                    return result

                def validate(_view: VerificationView) -> None:
                    nonlocal validator_called
                    validator_called = True

                with (
                    mock.patch.object(
                        store,
                        "_read_pointer_with_snapshot",
                        side_effect=read_then_replace_lock,
                    ),
                    self.assertRaisesRegex(
                        PipelineError,
                        "lock changed while held",
                    ),
                ):
                    store.verify_pointer(
                        campaign_id=CAMPAIGN_ID,
                        expected=reference,
                        validator=validate,
                    )

                self.assertEqual(replacement_after_read, read_count)
                self.assertEqual(
                    replacement_after_read == 2,
                    validator_called,
                )

    def test_verify_pointer_rejects_wrong_reference_without_mutation(self) -> None:
        store = self.store()
        raw = b"exact matrix pointer reference required"
        reference = _pointer_reference(raw)
        _install_verification_pointer_and_lock(
            self.repository_root,
            reference=reference,
            raw=raw,
        )
        before = _tree_fingerprint(self.repository_root)
        called = False

        def validate(_view: VerificationView) -> None:
            nonlocal called
            called = True

        with self.assertRaisesRegex(PipelineError, "exact matrix-pointer"):
            store.verify_pointer(
                campaign_id=CAMPAIGN_ID,
                expected=_pointer_reference(raw, kind="matrix-snapshot"),
                validator=validate,
            )
        with self.assertRaisesRegex(PipelineError, "do not match"):
            store.verify_pointer(
                campaign_id=CAMPAIGN_ID,
                expected=_pointer_reference(b"wrong pointer identity"),
                validator=validate,
            )

        self.assertFalse(called)
        self.assertEqual(before, _tree_fingerprint(self.repository_root))

    def test_verify_pointer_propagates_callback_exception(self) -> None:
        store = self.store()
        raw = b"pointer whose validator raises"
        reference = _pointer_reference(raw)
        _install_verification_pointer_and_lock(
            self.repository_root,
            reference=reference,
            raw=raw,
        )
        failure = RuntimeError("validator failed")

        def fail(_view: VerificationView) -> None:
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            store.verify_pointer(
                campaign_id=CAMPAIGN_ID,
                expected=reference,
                validator=fail,
            )
        self.assertIs(failure, caught.exception)
        self.assertEqual(raw, (self.repository_root / POINTER_PATH).read_bytes())

    def test_lock_replacement_at_acquisition_fails_before_pointer_mutation(
        self,
    ) -> None:
        store = self.store()
        required = _stage_required(store)
        raw = b"successor blocked by lock replacement"
        successor = _pointer_reference(raw)
        lock_path = (
            self.repository_root
            / "campaign-state"
            / "locks"
            / f"{CAMPAIGN_ID}.lock"
        )

        def replace_lock(seam: str) -> None:
            if seam != "pointer.after_lock":
                return
            foreign = lock_path.parent / "foreign-lock.tmp"
            foreign.write_bytes(b"foreign lock")
            foreign.chmod(0o600)
            os.replace(foreign, lock_path)

        failing_store = self.store(fault_hook=replace_lock)
        with self.assertRaisesRegex(PipelineError, "lock changed while held"):
            _transaction(
                failing_store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertEqual(b"foreign lock", lock_path.read_bytes())
        self.assertFalse((self.repository_root / POINTER_PATH).exists())

    def test_lock_replacement_at_before_replace_blocks_publication(self) -> None:
        store = self.store()
        required = _stage_required(store)
        raw = b"successor blocked at replacement boundary"
        successor = _pointer_reference(raw)
        lock_path = (
            self.repository_root
            / "campaign-state"
            / "locks"
            / f"{CAMPAIGN_ID}.lock"
        )

        def replace_lock(seam: str) -> None:
            if seam != "pointer.before_replace":
                return
            foreign = lock_path.parent / "foreign-lock.tmp"
            foreign.write_bytes(b"foreign late-pre lock")
            foreign.chmod(0o600)
            os.replace(foreign, lock_path)

        failing_store = self.store(fault_hook=replace_lock)
        with self.assertRaisesRegex(PipelineError, "lock changed while held"):
            _transaction(
                failing_store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertEqual(b"foreign late-pre lock", lock_path.read_bytes())
        self.assertFalse((self.repository_root / POINTER_PATH).exists())
        self.assertEqual([], list(self.repository_root.rglob(".tmp-*")))

    def test_lock_replacement_after_post_callback_rolls_back_owned_pointer(
        self,
    ) -> None:
        store = self.store()
        required = _stage_required(store)
        raw = b"successor rolled back after post callback"
        successor = _pointer_reference(raw)
        lock_path = (
            self.repository_root
            / "campaign-state"
            / "locks"
            / f"{CAMPAIGN_ID}.lock"
        )

        def post(_view: TransactionView) -> Receipt:
            foreign = lock_path.parent / "foreign-lock.tmp"
            foreign.write_bytes(b"foreign post lock")
            foreign.chmod(0o600)
            os.replace(foreign, lock_path)
            return POST_COMMIT_RECEIPT

        with self.assertRaisesRegex(PipelineError, "lock changed while held"):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=post,
            )
        self.assertEqual(b"foreign post lock", lock_path.read_bytes())
        self.assertFalse((self.repository_root / POINTER_PATH).exists())

    def test_update_callbacks_see_exact_old_then_new_raw_pointer(self) -> None:
        store = self.store()
        required = _stage_required(store)
        old_raw = b"legacy matrix generation one"
        old_reference = _pointer_reference(old_raw)
        first, _pre, _post = _commit(
            store,
            expected=None,
            successor=old_reference,
            successor_raw=old_raw,
            required_objects=required,
        )
        new_raw = b"legacy matrix generation two"
        new_reference = _pointer_reference(new_raw)
        pre_receipt = _receipt("pre-commit")
        post_receipt = _receipt("post-commit")
        observations: list[PointerState | None] = []

        result = _transaction(
            store,
            expected=old_reference,
            successor=new_reference,
            successor_raw=new_raw,
            required_objects=required,
        ).commit(
            pre_commit=lambda view: (
                observations.append(view.read_pointer(old_reference)) or pre_receipt
            ),
            post_commit=lambda view: (
                observations.append(view.read_pointer(new_reference)) or post_receipt
            ),
        )

        self.assertEqual(first.after, result.before)
        self.assertEqual(
            [first.after, PointerState(new_reference, new_raw)],
            observations,
        )
        self.assertEqual(PointerState(new_reference, new_raw), result.after)

    def test_transactions_are_single_use_and_stale_replays_fail_closed(self) -> None:
        store = self.store()
        required = _stage_required(store)
        first_raw = b"first pointer"
        first = _pointer_reference(first_raw)
        transaction = _transaction(
            store,
            expected=None,
            successor=first,
            successor_raw=first_raw,
            required_objects=required,
        )
        transaction.commit(
            pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
            post_commit=lambda _view: POST_COMMIT_RECEIPT,
        )

        with self.assertRaisesRegex(PipelineError, "single-use"):
            transaction.commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        with self.assertRaisesRegex(PipelineError, "expected absence"):
            _transaction(
                store,
                expected=None,
                successor=first,
                successor_raw=first_raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )

        second_raw = b"second pointer"
        second = _pointer_reference(second_raw)
        _commit(
            store,
            expected=first,
            successor=second,
            successor_raw=second_raw,
            required_objects=required,
        )
        with self.assertRaisesRegex(PipelineError, "compare-and-swap failed"):
            _transaction(
                store,
                expected=first,
                successor=second,
                successor_raw=second_raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertEqual(PointerState(second, second_raw), store.read_pointer(second))

    def test_transaction_factory_rejects_inexact_or_ambiguous_inputs(self) -> None:
        store = self.store()
        raw = b"successor"
        successor = _pointer_reference(raw)
        with self.assertRaisesRegex(PipelineError, "do not match"):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=b"wrong",
                required_objects=(),
            )
        with self.assertRaisesRegex(PipelineError, "do not match"):
            PointerTransaction(
                store=store,
                campaign_id=CAMPAIGN_ID,
                expected=None,
                successor=successor,
                successor_raw=b"wrong",
                required_objects=(),
            )
        with self.assertRaisesRegex(PipelineError, "must differ"):
            _transaction(
                store,
                expected=successor,
                successor=successor,
                successor_raw=raw,
                required_objects=(),
            )
        other_path = _pointer_reference(b"old", path="other-pointer.json")
        with self.assertRaisesRegex(PipelineError, "expected pointer"):
            _transaction(
                store,
                expected=other_path,
                successor=successor,
                successor_raw=raw,
                required_objects=(),
            )

        first = store.reference_for(
            kind="artifact",
            raw=b"z",
            target_content_sha256=None,
        )
        second = store.reference_for(
            kind="artifact",
            raw=b"a",
            target_content_sha256=None,
        )
        unsorted = tuple(
            sorted((first, second), key=lambda item: item.path, reverse=True)
        )
        with self.assertRaisesRegex(PipelineError, "sorted and unique"):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=unsorted,
            )
        with self.assertRaisesRegex(PipelineError, "sorted and unique"):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=(first, first),
            )

    def test_wrong_or_failed_stage_receipts_fail_closed(self) -> None:
        cases = (
            ("pre-wrong-stage", _receipt("check"), _receipt("post-commit")),
            (
                "pre-failed",
                _receipt("pre-commit", passed=False),
                _receipt("post-commit"),
            ),
            ("post-wrong-stage", _receipt("pre-commit"), _receipt("check")),
            (
                "post-failed",
                _receipt("pre-commit"),
                _receipt("post-commit", passed=False),
            ),
        )
        for label, pre_receipt, post_receipt in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                store = CampaignStore(root, "campaign-state")
                required = _stage_required(store)
                raw = f"pointer for {label}".encode()
                successor = _pointer_reference(raw)
                with self.assertRaises(PipelineError):
                    _transaction(
                        store,
                        expected=None,
                        successor=successor,
                        successor_raw=raw,
                        required_objects=required,
                    ).commit(
                        pre_commit=lambda _view, value=pre_receipt: value,
                        post_commit=lambda _view, value=post_receipt: value,
                    )
                self.assertFalse((root / POINTER_PATH).exists())
                self.assertEqual(
                    b"immutable transaction evidence\n",
                    store.read_exact(required[0]),
                )

    def test_every_pre_replace_fault_preserves_pointer_and_valid_cas_orphans(
        self,
    ) -> None:
        seams = (
            "pointer.after_lock",
            "pointer.after_cas",
            "pointer.after_required_verify",
            "pointer.after_pre_commit",
            "pointer.after_temp_create",
            "pointer.after_file_fsync",
            "pointer.before_replace",
        )
        for seam in seams:
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                staging_store = CampaignStore(root, "campaign-state")
                required = _stage_required(staging_store)
                raw = f"opaque successor for {seam}".encode()
                successor = _pointer_reference(raw)
                fail = FailAt(seam)
                store = CampaignStore(root, "campaign-state", fault_hook=fail)
                pre_receipt = _receipt("pre-commit")
                post_receipt = _receipt("post-commit")
                with self.assertRaisesRegex(InjectedFault, seam):
                    _transaction(
                        store,
                        expected=None,
                        successor=successor,
                        successor_raw=raw,
                        required_objects=required,
                    ).commit(
                        pre_commit=lambda _view: pre_receipt,
                        post_commit=lambda _view: post_receipt,
                    )
                self.assertFalse((root / POINTER_PATH).exists())
                self.assertEqual(
                    b"immutable transaction evidence\n",
                    staging_store.read_exact(required[0]),
                )
                self.assertEqual([], list(root.rglob(".tmp-*")))

    def test_every_post_replace_fault_rolls_back_created_pointer(self) -> None:
        for seam in (
            "pointer.after_replace",
            "pointer.after_directory_fsync",
            "pointer.after_post_commit",
        ):
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                staging_store = CampaignStore(root, "campaign-state")
                required = _stage_required(staging_store)
                raw = f"opaque successor for {seam}".encode()
                successor = _pointer_reference(raw)
                fail = FailAt(seam)
                store = CampaignStore(root, "campaign-state", fault_hook=fail)
                with self.assertRaisesRegex(InjectedFault, seam):
                    _transaction(
                        store,
                        expected=None,
                        successor=successor,
                        successor_raw=raw,
                        required_objects=required,
                    ).commit(
                        pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                        post_commit=lambda _view: POST_COMMIT_RECEIPT,
                    )
                self.assertFalse((root / POINTER_PATH).exists())
                self.assertIn("rollback.after_owned_unlink", fail.events)
                self.assertEqual(
                    b"immutable transaction evidence\n",
                    staging_store.read_exact(required[0]),
                )

    def test_update_failure_restores_exact_predecessor_pointer(self) -> None:
        store = self.store()
        required = _stage_required(store)
        old_raw = b"exact predecessor bytes"
        old = _pointer_reference(old_raw)
        _commit(
            store,
            expected=None,
            successor=old,
            successor_raw=old_raw,
            required_objects=required,
        )
        new_raw = b"candidate successor bytes"
        new = _pointer_reference(new_raw)
        fail = FailAt("pointer.after_directory_fsync")
        failing_store = self.store(fault_hook=fail)
        with self.assertRaisesRegex(InjectedFault, "after_directory_fsync"):
            _transaction(
                failing_store,
                expected=old,
                successor=new,
                successor_raw=new_raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )

        self.assertEqual(PointerState(old, old_raw), store.read_pointer(old))
        self.assertIn("rollback.after_restore", fail.events)
        self.assertIn("rollback.after_directory_fsync", fail.events)
        self.assertEqual(
            b"immutable transaction evidence\n",
            store.read_exact(required[0]),
        )

    def test_all_rollback_fault_seams_are_fail_closed(self) -> None:
        unlink_seams = (
            "rollback.before_owned_unlink",
            "rollback.after_owned_unlink",
            "rollback.after_unlink_directory_fsync",
        )
        for seam in unlink_seams:
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                staging_store = CampaignStore(root, "campaign-state")
                required = _stage_required(staging_store)
                raw = f"successor for {seam}".encode()
                successor = _pointer_reference(raw)
                fail = FailAt(seam)
                store = CampaignStore(root, "campaign-state", fault_hook=fail)
                with self.assertRaisesRegex(PipelineError, "rollback incomplete"):
                    _transaction(
                        store,
                        expected=None,
                        successor=successor,
                        successor_raw=raw,
                        required_objects=required,
                    ).commit(
                        pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                        post_commit=lambda _view: (_ for _ in ()).throw(
                            InjectedFault("post validation")
                        ),
                    )
                self.assertEqual(
                    seam == "rollback.before_owned_unlink",
                    (root / POINTER_PATH).exists(),
                )

        restore_seams = (
            "rollback.before_restore",
            "rollback.after_restore",
            "rollback.after_directory_fsync",
        )
        for seam in restore_seams:
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                base_store = CampaignStore(root, "campaign-state")
                required = _stage_required(base_store)
                old_raw = b"old pointer"
                old = _pointer_reference(old_raw)
                _commit(
                    base_store,
                    expected=None,
                    successor=old,
                    successor_raw=old_raw,
                    required_objects=required,
                )
                new_raw = f"new pointer for {seam}".encode()
                new = _pointer_reference(new_raw)
                fail = FailAt(seam)
                store = CampaignStore(root, "campaign-state", fault_hook=fail)
                with self.assertRaisesRegex(PipelineError, "rollback incomplete"):
                    _transaction(
                        store,
                        expected=old,
                        successor=new,
                        successor_raw=new_raw,
                        required_objects=required,
                    ).commit(
                        pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                        post_commit=lambda _view: (_ for _ in ()).throw(
                            InjectedFault("post validation")
                        ),
                    )
                expected_raw = new_raw if seam == "rollback.before_restore" else old_raw
                self.assertEqual(expected_raw, (root / POINTER_PATH).read_bytes())

    def test_foreign_pointer_replacement_is_preserved_during_rollback(self) -> None:
        store = self.store()
        required = _stage_required(store)
        successor_raw = b"transaction successor"
        successor = _pointer_reference(successor_raw)
        pointer_path = self.repository_root / POINTER_PATH
        foreign_bytes = b"foreign pointer replacement\n"

        def replace_then_fail(seam: str) -> None:
            if seam != "pointer.after_replace":
                return
            foreign = self.repository_root / "foreign.tmp"
            foreign.write_bytes(foreign_bytes)
            foreign.chmod(0o644)
            os.replace(foreign, pointer_path)
            raise InjectedFault("foreign replacement installed")

        failing_store = self.store(fault_hook=replace_then_fail)
        with self.assertRaisesRegex(PipelineError, "rollback incomplete") as caught:
            _transaction(
                failing_store,
                expected=None,
                successor=successor,
                successor_raw=successor_raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertIsInstance(caught.exception.__cause__, InjectedFault)
        self.assertEqual(foreign_bytes, pointer_path.read_bytes())

    def test_required_object_drift_blocks_pointer_before_mutation(self) -> None:
        store = self.store()
        required = _stage_required(store)
        victim_path = self.repository_root / required[0].path
        victim_path.write_bytes(b"tampered immutable evidence\n")
        raw = b"successor must not publish"
        successor = _pointer_reference(raw)

        with self.assertRaises(PipelineError):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertFalse((self.repository_root / POINTER_PATH).exists())

    def test_required_object_drift_during_precheck_blocks_pointer(self) -> None:
        store = self.store()
        required = _stage_required(store)
        victim_path = self.repository_root / required[0].path
        raw = b"successor must remain unpublished"
        successor = _pointer_reference(raw)

        def pre(_view: TransactionView) -> Receipt:
            victim_path.write_bytes(b"callback-side evidence drift\n")
            return PRE_COMMIT_RECEIPT

        with self.assertRaises(PipelineError):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=pre,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertFalse((self.repository_root / POINTER_PATH).exists())

    def test_required_object_mutation_at_before_replace_blocks_pointer(self) -> None:
        store = self.store()
        required = _stage_required(store)
        victim_path = self.repository_root / required[0].path
        raw = b"successor blocked at final evidence boundary"
        successor = _pointer_reference(raw)

        def mutate_required(seam: str) -> None:
            if seam == "pointer.before_replace":
                victim_path.write_bytes(b"before-replace evidence mutation\n")

        failing_store = self.store(fault_hook=mutate_required)
        with self.assertRaises(PipelineError):
            _transaction(
                failing_store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertFalse((self.repository_root / POINTER_PATH).exists())
        self.assertEqual([], list(self.repository_root.rglob(".tmp-*")))

    def test_required_object_drift_during_postcheck_rolls_back_pointer(self) -> None:
        store = self.store()
        required = _stage_required(store)
        victim_path = self.repository_root / required[0].path
        raw = b"successor requiring post-check rollback"
        successor = _pointer_reference(raw)

        def post(_view: TransactionView) -> Receipt:
            victim_path.write_bytes(b"post-check evidence drift\n")
            return POST_COMMIT_RECEIPT

        with self.assertRaises(PipelineError):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=raw,
                required_objects=required,
            ).commit(
                pre_commit=lambda _view: PRE_COMMIT_RECEIPT,
                post_commit=post,
            )
        self.assertFalse((self.repository_root / POINTER_PATH).exists())

    def test_foreign_change_during_precheck_is_preserved(self) -> None:
        store = self.store()
        required = _stage_required(store)
        successor_raw = b"transaction successor"
        successor = _pointer_reference(successor_raw)
        foreign_raw = b"foreign precheck pointer"

        def pre(_view: TransactionView) -> Receipt:
            pointer_path = self.repository_root / POINTER_PATH
            pointer_path.write_bytes(foreign_raw)
            pointer_path.chmod(0o644)
            return PRE_COMMIT_RECEIPT

        with self.assertRaisesRegex(PipelineError, "changed during pre-commit"):
            _transaction(
                store,
                expected=None,
                successor=successor,
                successor_raw=successor_raw,
                required_objects=required,
            ).commit(
                pre_commit=pre,
                post_commit=lambda _view: POST_COMMIT_RECEIPT,
            )
        self.assertEqual(
            foreign_raw,
            (self.repository_root / POINTER_PATH).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
