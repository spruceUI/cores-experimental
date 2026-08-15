"""Durable core-track transaction and command handlers.

The launcher remains the composition root. Every invocation captures a fresh,
filtered namespace so legacy monkeypatch seams and nested handler calls retain
their original behavior without a reverse import.
"""

from __future__ import annotations

import argparse
import builtins
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class TrackCommandServices:
    """Call-time launcher namespace consumed by this command domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "TrackCommandServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"missing pipeline services: {names}")
        captured = {name: namespace[name] for name in _REQUIRED_BINDINGS}
        captured.update(
            {
                name: namespace.get(name, getattr(builtins, name))
                for name in _BUILTIN_BINDINGS
            }
        )
        return cls(MappingProxyType(captured))


def required_binding_names() -> frozenset[str]:
    """Return the exact launcher bindings consumed by this leaf."""

    return _REQUIRED_BINDINGS


def builtin_binding_names() -> frozenset[str]:
    """Return builtins captured dynamically to preserve launcher overrides."""

    return _BUILTIN_BINDINGS


_REQUIRED_BINDINGS = frozenset(
    {
        'DEFAULT_CATALOG',
        'DEFAULT_CHIPSET_TUNINGS',
        'DEFAULT_CORE_TRACKS',
        'DEFAULT_SPRUCE_BRANCH_BASES',
        'DEFAULT_SPRUCE_RELEASE_ROSTER',
        'Mapping',
        'Path',
        'PipelineError',
        'ROOT',
        '_atomic_create_core_track_snapshot',
        '_atomic_restore_core_track_bytes',
        '_canonical_core_track_json_bytes',
        '_commit_core_track_registry_transaction',
        '_durably_remove_owned_core_track_snapshot',
        '_rollback_core_track_registry_transaction',
        '_validate_pin_set_document',
        'atomic_write_json',
        'construct_core_track_inventory',
        'core_track_source_ancestry_verifier',
        'decode_json_object',
        'json',
        'load_authoritative_core_pin_index',
        'load_catalog',
        'load_core_track_source_registry_index',
        'load_json',
        'load_json_with_sha256',
        'manifest_lock',
        'os',
        'plan_core_track_test',
        'promote_core_track_test',
        'safe_child',
        'set_core_track_test',
        'sha256_bytes',
        'sha256_file',
        'tempfile',
        'utc_now',
        'validate_core_tracks',
    }
)


_BUILTIN_BINDINGS = frozenset(
    {
        'BaseException',
        'FileExistsError',
        'FileNotFoundError',
        'OSError',
        'all',
        'getattr',
        'int',
        'isinstance',
        'len',
        'print',
        'tuple',
    }
)


def cmd_core_track_inventory(args: argparse.Namespace, *, services: TrackCommandServices) -> int:
    """Resolve one immutable, read-only track/marker/chipset inventory."""
    DEFAULT_CATALOG = services['DEFAULT_CATALOG']
    DEFAULT_CHIPSET_TUNINGS = services['DEFAULT_CHIPSET_TUNINGS']
    DEFAULT_CORE_TRACKS = services['DEFAULT_CORE_TRACKS']
    DEFAULT_SPRUCE_BRANCH_BASES = services['DEFAULT_SPRUCE_BRANCH_BASES']
    DEFAULT_SPRUCE_RELEASE_ROSTER = services['DEFAULT_SPRUCE_RELEASE_ROSTER']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    construct_core_track_inventory = services['construct_core_track_inventory']
    core_track_source_ancestry_verifier = services['core_track_source_ancestry_verifier']
    json = services['json']
    load_authoritative_core_pin_index = services['load_authoritative_core_pin_index']
    load_catalog = services['load_catalog']
    load_core_track_source_registry_index = services['load_core_track_source_registry_index']
    load_json = services['load_json']
    print = services['print']


    if args.catalog.resolve() != DEFAULT_CATALOG.resolve():
        raise PipelineError(
            "core-track-inventory requires the canonical core catalog"
        )
    catalog = load_catalog(args.catalog)
    pin_index = load_authoritative_core_pin_index()
    inventory = construct_core_track_inventory(
        load_json(DEFAULT_CORE_TRACKS),
        catalog=catalog,
        pin_index=pin_index,
        tunings=load_json(DEFAULT_CHIPSET_TUNINGS),
        main_release_roster=load_json(DEFAULT_SPRUCE_RELEASE_ROSTER),
        spruce_branch_bases=load_json(DEFAULT_SPRUCE_BRANCH_BASES),
        group_tag=args.group_tag,
        requested_cores=args.core,
        source_registry_index=load_core_track_source_registry_index(ROOT),
        source_ancestry_verifier=core_track_source_ancestry_verifier(),
    )
    for row in inventory["cores"]:
        if row["selected_chipset"] == "universal" and (
            row["tuning"]["properties"] != {}
            or row["tuning"]["compiler_arguments"] != []
        ):
            raise PipelineError(
                "universal core-track selections must not add chipset-specific flags"
            )
    print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0

def _canonical_core_track_json_bytes(document: object, *, services: TrackCommandServices) -> bytes:
    json = services['json']

    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

def _atomic_create_core_track_snapshot(path: Path, raw: bytes, ownership: dict[str, object], *, services: TrackCommandServices) -> None:
    """Create one snapshot while exposing only this attempt's inode identity."""
    FileExistsError = services['FileExistsError']
    Path = services['Path']
    PipelineError = services['PipelineError']
    getattr = services['getattr']
    os = services['os']
    tempfile = services['tempfile']


    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
            temporary_stat = os.fstat(handle.fileno())
            ownership["candidate_identity"] = (
                temporary_stat.st_dev,
                temporary_stat.st_ino,
            )
        ownership["link_attempted"] = True
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise PipelineError(
                f"refusing to replace existing core-track snapshot: {path}"
            ) from exc
        linked_stat = os.lstat(path)
        if ownership["candidate_identity"] != (
            linked_stat.st_dev,
            linked_stat.st_ino,
        ):
            raise PipelineError(
                "created core-track snapshot inode identity is invalid"
            )
        temporary.unlink()
        temporary = None
        directory_fd = os.open(
            path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def _atomic_restore_core_track_bytes(path: Path, raw: bytes, *, services: TrackCommandServices) -> None:
    """Replace one transaction file with its exact pre-transaction bytes."""
    Path = services['Path']
    getattr = services['getattr']
    os = services['os']
    tempfile = services['tempfile']


    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory_fd = os.open(
            path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def _durably_remove_owned_core_track_snapshot(path: Path, *, services: TrackCommandServices) -> None:
    """Remove one transaction-owned snapshot and durably record the unlink."""
    getattr = services['getattr']
    os = services['os']


    path.unlink()
    directory_fd = os.open(
        path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

def _rollback_core_track_registry_transaction(*, registry_path: Path, prior_registry_bytes: bytes, snapshot_path: Path | None, prior_snapshot_bytes: bytes | None, snapshot_existed_before: bool, snapshot_create_ownership: Mapping[str, object], registry_write_attempted: bool, services: TrackCommandServices) -> list[str]:
    """Restore the exact observed pre-state and report incomplete surfaces."""
    BaseException = services['BaseException']
    FileNotFoundError = services['FileNotFoundError']
    _atomic_restore_core_track_bytes = services['_atomic_restore_core_track_bytes']
    _durably_remove_owned_core_track_snapshot = services['_durably_remove_owned_core_track_snapshot']
    all = services['all']
    int = services['int']
    isinstance = services['isinstance']
    len = services['len']
    os = services['os']
    tuple = services['tuple']


    problems: list[str] = []
    try:
        registry_restored = registry_path.read_bytes() == prior_registry_bytes
    except BaseException:
        registry_restored = False
    registry_restore_failed = False
    if registry_write_attempted and not registry_restored:
        try:
            _atomic_restore_core_track_bytes(
                registry_path, prior_registry_bytes
            )
        except BaseException:
            registry_restore_failed = True
    try:
        registry_restored = registry_path.read_bytes() == prior_registry_bytes
    except BaseException:
        registry_restored = False
    if not registry_restored:
        problems.append("registry bytes could not be restored exactly")
        # Keep a newly created source snapshot as recovery evidence when the
        # registry itself cannot be restored. Reverse-order rollback may only
        # remove the owned snapshot after the registry pre-state is proven.
        return problems
    if registry_restore_failed:
        problems.append(
            "registry bytes may be restored but durability was not acknowledged"
        )
        # Keep the snapshot as recovery evidence whenever exact durable
        # registry restoration is not proven.
        return problems

    if snapshot_path is None:
        return problems
    if snapshot_existed_before:
        if prior_snapshot_bytes is None:
            problems.append("preexisting snapshot pre-state is unavailable")
            return problems
        try:
            snapshot_matches = snapshot_path.read_bytes() == prior_snapshot_bytes
        except BaseException:
            snapshot_matches = False
        if not snapshot_matches:
            problems.append(
                "preexisting snapshot changed during the transaction"
            )
        return problems

    if snapshot_create_ownership.get("link_attempted") is not True:
        return problems
    candidate_identity = snapshot_create_ownership.get("candidate_identity")
    if not (
        isinstance(candidate_identity, tuple)
        and len(candidate_identity) == 2
        and all(isinstance(value, int) for value in candidate_identity)
    ):
        problems.append("new transaction snapshot ownership is unavailable")
        return problems
    try:
        snapshot_stat = os.lstat(snapshot_path)
    except FileNotFoundError:
        return problems
    except BaseException:
        problems.append("new transaction snapshot ownership cannot be verified")
        return problems
    if candidate_identity != (snapshot_stat.st_dev, snapshot_stat.st_ino):
        # A different creator won the destination race. This transaction does
        # not own that path even when the foreign bytes are identical.
        return problems
    try:
        _durably_remove_owned_core_track_snapshot(snapshot_path)
    except BaseException:
        problems.append(
            "new transaction snapshot removal did not complete durably"
        )
        return problems
    try:
        snapshot_path.read_bytes()
    except FileNotFoundError:
        return problems
    except BaseException:
        problems.append("new transaction snapshot removal cannot be verified")
    else:
        problems.append("new transaction snapshot could not be removed")
    return problems

def _commit_core_track_registry_transaction(*, prior_registry: Mapping[str, object], registry: Mapping[str, object], snapshot_path: Path | None, snapshot: Mapping[str, object] | None, snapshot_file_sha256: str | None, validator: Callable[[object], dict], services: TrackCommandServices) -> None:
    """Commit one registry and optional content-addressed snapshot atomically."""
    BaseException = services['BaseException']
    DEFAULT_CORE_TRACKS = services['DEFAULT_CORE_TRACKS']
    FileNotFoundError = services['FileNotFoundError']
    OSError = services['OSError']
    PipelineError = services['PipelineError']
    _atomic_create_core_track_snapshot = services['_atomic_create_core_track_snapshot']
    _canonical_core_track_json_bytes = services['_canonical_core_track_json_bytes']
    _rollback_core_track_registry_transaction = services['_rollback_core_track_registry_transaction']
    atomic_write_json = services['atomic_write_json']
    decode_json_object = services['decode_json_object']
    sha256_bytes = services['sha256_bytes']


    registry_path = DEFAULT_CORE_TRACKS
    try:
        prior_registry_bytes = registry_path.read_bytes()
    except OSError as exc:
        raise PipelineError(
            f"cannot capture core-track registry transaction source: {exc}"
        ) from exc
    captured_registry = decode_json_object(
        prior_registry_bytes, "core-track registry transaction source"
    )
    if captured_registry != prior_registry:
        raise PipelineError(
            "core-track registry changed before transaction mutation"
        )

    if (snapshot_path is None) != (snapshot is None):
        raise PipelineError("core-track transaction snapshot contract is invalid")
    if (snapshot is None) != (snapshot_file_sha256 is None):
        raise PipelineError("core-track transaction snapshot identity is invalid")

    snapshot_existed_before = False
    prior_snapshot_bytes: bytes | None = None
    expected_snapshot_bytes: bytes | None = None
    if snapshot_path is not None:
        assert snapshot is not None
        assert snapshot_file_sha256 is not None
        expected_snapshot_bytes = _canonical_core_track_json_bytes(snapshot)
        if sha256_bytes(expected_snapshot_bytes) != snapshot_file_sha256:
            raise PipelineError(
                "core-track transaction snapshot identity is invalid"
            )
        try:
            prior_snapshot_bytes = snapshot_path.read_bytes()
        except FileNotFoundError:
            snapshot_existed_before = False
        except OSError as exc:
            raise PipelineError(
                f"cannot read existing core-track snapshot: {exc}"
            ) from exc
        else:
            snapshot_existed_before = True
            existing_snapshot = decode_json_object(
                prior_snapshot_bytes, snapshot_path
            )
            if (
                prior_snapshot_bytes != expected_snapshot_bytes
                or existing_snapshot != snapshot
                or sha256_bytes(prior_snapshot_bytes)
                != snapshot_file_sha256
            ):
                raise PipelineError(
                    "existing core-track snapshot differs from transaction"
                )

    expected_registry_bytes = _canonical_core_track_json_bytes(registry)
    snapshot_create_ownership: dict[str, object] = {
        "candidate_identity": None,
        "link_attempted": False,
    }
    registry_write_attempted = False
    try:
        if snapshot_path is not None and not snapshot_existed_before:
            assert snapshot is not None
            assert expected_snapshot_bytes is not None
            _atomic_create_core_track_snapshot(
                snapshot_path,
                expected_snapshot_bytes,
                snapshot_create_ownership,
            )
            created_snapshot_bytes = snapshot_path.read_bytes()
            if (
                created_snapshot_bytes != expected_snapshot_bytes
                or decode_json_object(created_snapshot_bytes, snapshot_path)
                != snapshot
                or sha256_bytes(created_snapshot_bytes)
                != snapshot_file_sha256
            ):
                raise PipelineError(
                    "created core-track snapshot identity is invalid"
                )
        registry_write_attempted = True
        atomic_write_json(registry_path, registry)
        on_disk_bytes = registry_path.read_bytes()
        if on_disk_bytes != expected_registry_bytes:
            raise PipelineError(
                "core-track registry bytes changed during post-write validation"
            )
        on_disk = decode_json_object(on_disk_bytes, registry_path)
        if on_disk != registry:
            raise PipelineError(
                "core-track registry changed during post-write validation"
            )
        validated_on_disk = validator(on_disk)
        if validated_on_disk != registry:
            raise PipelineError(
                "core-track registry changed during post-write validation"
            )
    except BaseException as exc:
        rollback_problems = _rollback_core_track_registry_transaction(
            registry_path=registry_path,
            prior_registry_bytes=prior_registry_bytes,
            snapshot_path=snapshot_path,
            prior_snapshot_bytes=prior_snapshot_bytes,
            snapshot_existed_before=snapshot_existed_before,
            snapshot_create_ownership=snapshot_create_ownership,
            registry_write_attempted=registry_write_attempted,
        )
        if rollback_problems:
            raise PipelineError(
                "core-track registry transaction rollback incomplete:\n- "
                + "\n- ".join(rollback_problems)
            ) from exc
        raise

def cmd_core_track_promote(args: argparse.Namespace, *, services: TrackCommandServices) -> int:
    """Approve one exact TEST cell with a tracked source-registry snapshot."""
    DEFAULT_CATALOG = services['DEFAULT_CATALOG']
    DEFAULT_CHIPSET_TUNINGS = services['DEFAULT_CHIPSET_TUNINGS']
    DEFAULT_CORE_TRACKS = services['DEFAULT_CORE_TRACKS']
    DEFAULT_SPRUCE_BRANCH_BASES = services['DEFAULT_SPRUCE_BRANCH_BASES']
    DEFAULT_SPRUCE_RELEASE_ROSTER = services['DEFAULT_SPRUCE_RELEASE_ROSTER']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    _commit_core_track_registry_transaction = services['_commit_core_track_registry_transaction']
    core_track_source_ancestry_verifier = services['core_track_source_ancestry_verifier']
    json = services['json']
    load_authoritative_core_pin_index = services['load_authoritative_core_pin_index']
    load_catalog = services['load_catalog']
    load_core_track_source_registry_index = services['load_core_track_source_registry_index']
    load_json = services['load_json']
    manifest_lock = services['manifest_lock']
    print = services['print']
    promote_core_track_test = services['promote_core_track_test']
    safe_child = services['safe_child']
    utc_now = services['utc_now']
    validate_core_tracks = services['validate_core_tracks']


    if args.catalog.resolve() != DEFAULT_CATALOG.resolve():
        raise PipelineError("core-track-promote requires the canonical core catalog")
    approved_at = args.approved_at or utc_now().replace("+00:00", "Z")
    with manifest_lock(DEFAULT_CORE_TRACKS):
        catalog = load_catalog(args.catalog)
        pin_index = load_authoritative_core_pin_index()
        tunings = load_json(DEFAULT_CHIPSET_TUNINGS)
        main_release_roster = load_json(DEFAULT_SPRUCE_RELEASE_ROSTER)
        source_index = load_core_track_source_registry_index(ROOT)
        prior_registry = load_json(DEFAULT_CORE_TRACKS)
        spruce_branch_bases = load_json(DEFAULT_SPRUCE_BRANCH_BASES)
        result = promote_core_track_test(
            prior_registry,
            repository_root=ROOT,
            catalog=catalog,
            pin_index=pin_index,
            tunings=tunings,
            main_release_roster=main_release_roster,
            spruce_branch_bases=spruce_branch_bases,
            source_registry_index=source_index,
            track=args.track,
            core_id=args.core,
            chipset=args.chipset,
            approved_at=approved_at,
            approved_by=args.approved_by,
            reason=args.reason,
            expected_test_variant=args.expected_test_variant,
            expected_current_stable=args.expected_current_stable,
            source_ancestry_verifier=core_track_source_ancestry_verifier(),
        )
        snapshot_path = safe_child(
            ROOT,
            result["snapshot_path"],
            "core-track source registry snapshot",
        )
        _commit_core_track_registry_transaction(
            prior_registry=prior_registry,
            registry=result["registry"],
            snapshot_path=snapshot_path,
            snapshot=result["snapshot"],
            snapshot_file_sha256=result["snapshot_file_sha256"],
            validator=lambda on_disk: validate_core_tracks(
                on_disk,
                catalog=catalog,
                pin_index=pin_index,
                tunings=tunings,
                main_release_roster=main_release_roster,
                spruce_branch_bases=spruce_branch_bases,
                source_registry_index=load_core_track_source_registry_index(
                    ROOT
                ),
                source_ancestry_verifier=core_track_source_ancestry_verifier(),
            ),
        )
    print(
        json.dumps(
            {
                "status": "stable",
                "track": args.track,
                "core_id": args.core,
                "chipset": args.chipset,
                "variant_id": result["stable_cell"]["approved_test_variant_id"],
                "previous_stable_variant_id": result[
                    "previous_stable_variant_id"
                ],
                "source_registry_content_sha256": result["stable_cell"][
                    "source_registry_content_sha256"
                ],
                "source_registry_snapshot_path": result["snapshot_path"],
                "track_registry_content_sha256": result["registry"][
                    "content_sha256"
                ],
                "validation_scope": "static-build-selection-only",
                "publication": "disabled",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def _core_track_test_context(
    args: argparse.Namespace,
    *,
    command: str,
    services: TrackCommandServices,
) -> dict[str, Any]:
    """Load and deeply validate the immutable inputs shared by plan and set."""

    DEFAULT_CATALOG = services['DEFAULT_CATALOG']
    DEFAULT_CHIPSET_TUNINGS = services['DEFAULT_CHIPSET_TUNINGS']
    DEFAULT_CORE_TRACKS = services['DEFAULT_CORE_TRACKS']
    DEFAULT_SPRUCE_BRANCH_BASES = services['DEFAULT_SPRUCE_BRANCH_BASES']
    DEFAULT_SPRUCE_RELEASE_ROSTER = services['DEFAULT_SPRUCE_RELEASE_ROSTER']
    Mapping = services['Mapping']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    _validate_pin_set_document = services['_validate_pin_set_document']
    core_track_source_ancestry_verifier = services['core_track_source_ancestry_verifier']
    isinstance = services['isinstance']
    load_authoritative_core_pin_index = services['load_authoritative_core_pin_index']
    load_catalog = services['load_catalog']
    load_core_track_source_registry_index = services['load_core_track_source_registry_index']
    load_json = services['load_json']
    load_json_with_sha256 = services['load_json_with_sha256']
    safe_child = services['safe_child']

    if args.catalog.resolve() != DEFAULT_CATALOG.resolve():
        raise PipelineError(f"{command} requires the canonical core catalog")
    catalog = load_catalog(args.catalog)
    pin_index = load_authoritative_core_pin_index()
    tunings = load_json(DEFAULT_CHIPSET_TUNINGS)
    target_pin_entry = pin_index.get(args.pin_id)
    if not isinstance(target_pin_entry, Mapping):
        raise PipelineError("core-track TEST pin is not authoritative")
    target_pin_path = safe_child(
        ROOT,
        target_pin_entry.get("path", ""),
        "core-track TEST pin",
    )
    target_pin, target_pin_file_sha256 = load_json_with_sha256(
        target_pin_path
    )
    if target_pin_file_sha256 != target_pin_entry.get("file_sha256"):
        raise PipelineError(
            "core-track TEST pin file identity changed after authoritative indexing"
        )
    if target_pin.get("content_sha256") != target_pin_entry.get(
        "content_sha256"
    ):
        raise PipelineError(
            "core-track TEST pin content identity changed after authoritative indexing"
        )
    target_pin_report = _validate_pin_set_document(
        target_pin,
        verify_store=True,
        verify_sources=True,
        document_path=target_pin_path,
        historical_recipe_proofs=True,
    )
    if target_pin_report.get("status") != "valid":
        raise PipelineError(
            "core-track TEST pin lacks complete authoritative evidence:\n- "
            + "\n- ".join(target_pin_report.get("errors", []))
        )
    return {
        "catalog": catalog,
        "pin_index": pin_index,
        "tunings": tunings,
        "target_pin_path": target_pin_path,
        "target_pin_file_sha256": target_pin_file_sha256,
        "prior_registry": load_json(DEFAULT_CORE_TRACKS),
        "main_release_roster": load_json(DEFAULT_SPRUCE_RELEASE_ROSTER),
        "spruce_branch_bases": load_json(DEFAULT_SPRUCE_BRANCH_BASES),
        "source_registry_index": load_core_track_source_registry_index(ROOT),
        "source_ancestry_verifier": core_track_source_ancestry_verifier(),
    }


def _core_track_test_transition_kwargs(
    args: argparse.Namespace,
    context: Mapping[str, Any],
    *,
    services: TrackCommandServices,
) -> dict[str, Any]:
    """Project common CLI proposal fields onto the pure transition engine."""

    ROOT = services['ROOT']
    getattr = services['getattr']

    return {
        "repository_root": ROOT,
        "catalog": context["catalog"],
        "pin_index": context["pin_index"],
        "tunings": context["tunings"],
        "main_release_roster": context["main_release_roster"],
        "spruce_branch_bases": context["spruce_branch_bases"],
        "source_registry_index": context["source_registry_index"],
        "source_ancestry_verifier": context["source_ancestry_verifier"],
        "track": args.track,
        "core_id": args.core,
        "chipset": args.chipset,
        "pin_id": args.pin_id,
        "tuning_profile": args.tuning_profile,
        "slice_time": args.slice_time,
        "outlier_authorized_at": getattr(
            args, "outlier_authorized_at", None
        ),
        "outlier_authorized_by": getattr(
            args, "outlier_authorized_by", None
        ),
        "outlier_reason": getattr(args, "outlier_reason", None),
        "applicable_chipsets": args.applicable_chipset,
    }


def cmd_core_track_plan_test(
    args: argparse.Namespace, *, services: TrackCommandServices
) -> int:
    """Validate and predict one exact TEST transition without writing state."""

    OSError = services['OSError']
    PipelineError = services['PipelineError']
    json = services['json']
    plan_core_track_test = services['plan_core_track_test']
    print = services['print']
    sha256_file = services['sha256_file']

    context = _core_track_test_context(
        args,
        command="core-track-plan-test",
        services=services,
    )
    result = plan_core_track_test(
        context["prior_registry"],
        **_core_track_test_transition_kwargs(args, context, services=services),
    )
    try:
        current_target_pin_sha256 = sha256_file(context["target_pin_path"])
    except OSError as exc:
        raise PipelineError("core-track TEST pin changed during planning") from exc
    if current_target_pin_sha256 != context["target_pin_file_sha256"]:
        raise PipelineError("core-track TEST pin changed during planning")
    outlier = result["source_order_outlier"]
    set_test_arguments = {
        "track": args.track,
        "core": args.core,
        "chipset": args.chipset,
        "pin_id": args.pin_id,
        "tuning_profile": args.tuning_profile,
        "slice_time": result["version_slice"]["slice_time"],
        "applicable_chipset": result["cell"]["applicable_chipsets"],
        **result["expectations"],
        "outlier_authorized_at": (
            outlier["authorized_at"] if outlier is not None else None
        ),
        "outlier_authorized_by": (
            outlier["authorized_by"] if outlier is not None else None
        ),
        "outlier_reason": (
            outlier["reason"] if outlier is not None else None
        ),
    }
    print(
        json.dumps(
            {
                "status": "planned",
                "mutation": "disabled",
                "publication": "disabled",
                "track": args.track,
                "core_id": args.core,
                "chipset": args.chipset,
                "source_registry_content_sha256": result[
                    "source_registry_content_sha256"
                ],
                "variant_id": result["variant_id"],
                "assignment_content_sha256": result[
                    "assignment_content_sha256"
                ],
                "edge_deferred_by_admission": result[
                    "edge_deferred_by_admission"
                ],
                "predicted_track_registry_content_sha256": result[
                    "registry"
                ]["content_sha256"],
                "set_test_arguments": set_test_arguments,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_core_track_set_test(args: argparse.Namespace, *, services: TrackCommandServices) -> int:
    """CAS one authoritative tuned pin into one exact track-local TEST cell."""
    DEFAULT_CORE_TRACKS = services['DEFAULT_CORE_TRACKS']
    OSError = services['OSError']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    _commit_core_track_registry_transaction = services['_commit_core_track_registry_transaction']
    core_track_source_ancestry_verifier = services['core_track_source_ancestry_verifier']
    getattr = services['getattr']
    json = services['json']
    load_core_track_source_registry_index = services['load_core_track_source_registry_index']
    manifest_lock = services['manifest_lock']
    print = services['print']
    safe_child = services['safe_child']
    set_core_track_test = services['set_core_track_test']
    sha256_file = services['sha256_file']
    validate_core_tracks = services['validate_core_tracks']

    with manifest_lock(DEFAULT_CORE_TRACKS):
        context = _core_track_test_context(
            args,
            command="core-track-set-test",
            services=services,
        )
        result = set_core_track_test(
            context["prior_registry"],
            **_core_track_test_transition_kwargs(
                args, context, services=services
            ),
            expected_source_registry=args.expected_source_registry,
            expected_current_test=args.expected_current_test,
            expected_current_assignment=args.expected_current_assignment,
            expected_new_variant=args.expected_new_variant,
            expected_parent_variant=getattr(args, "expected_parent_variant", None),
            expected_parent_registry=getattr(
                args, "expected_parent_registry", None
            ),
        )
        try:
            current_target_pin_sha256 = sha256_file(
                context["target_pin_path"]
            )
        except OSError as exc:
            raise PipelineError(
                "core-track TEST pin changed before track registry mutation"
            ) from exc
        if current_target_pin_sha256 != context["target_pin_file_sha256"]:
            raise PipelineError(
                "core-track TEST pin changed before track registry mutation"
            )
        snapshot_path: Path | None = None
        if result["snapshot"] is not None:
            snapshot_path = safe_child(
                ROOT,
                result["snapshot_path"],
                "core-track parent registry snapshot",
            )
        _commit_core_track_registry_transaction(
            prior_registry=context["prior_registry"],
            registry=result["registry"],
            snapshot_path=snapshot_path,
            snapshot=result["snapshot"],
            snapshot_file_sha256=result["snapshot_file_sha256"],
            validator=lambda on_disk: validate_core_tracks(
                on_disk,
                catalog=context["catalog"],
                pin_index=context["pin_index"],
                tunings=context["tunings"],
                main_release_roster=context["main_release_roster"],
                spruce_branch_bases=context["spruce_branch_bases"],
                source_registry_index=load_core_track_source_registry_index(
                    ROOT
                ),
                source_ancestry_verifier=core_track_source_ancestry_verifier(),
            ),
        )
    print(
        json.dumps(
            {
                "status": "test",
                "track": args.track,
                "core_id": args.core,
                "chipset": args.chipset,
                "source_registry_content_sha256": result[
                    "source_registry_content_sha256"
                ],
                "previous_variant_id": result["previous_variant_id"],
                "variant_id": result["variant_id"],
                "previous_assignment_content_sha256": result[
                    "previous_assignment_content_sha256"
                ],
                "parent_variant_id": result["parent_variant_id"],
                "parent_selection_content_sha256": result[
                    "parent_selection_content_sha256"
                ],
                "parent_registry_content_sha256": result[
                    "parent_registry_content_sha256"
                ],
                "version_slice": result["version_slice"],
                "slice_comparison_basis": result[
                    "slice_comparison_basis"
                ],
                "slice_branch_basis_registry_content_sha256": result[
                    "slice_branch_basis_registry_content_sha256"
                ],
                "slice_branch_basis_snapshot": result[
                    "slice_branch_basis_snapshot"
                ],
                "assignment_content_sha256": result[
                    "assignment_content_sha256"
                ],
                "source_order_parent_binding": result[
                    "source_order_parent_binding"
                ],
                "source_registry_snapshot_path": result["snapshot_path"],
                "source_registry_snapshot_file_sha256": result[
                    "snapshot_file_sha256"
                ],
                "source_order_outlier": result["source_order_outlier"],
                "edge_deferred_by_admission": result[
                    "edge_deferred_by_admission"
                ],
                "track_registry_content_sha256": result["registry"][
                    "content_sha256"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
