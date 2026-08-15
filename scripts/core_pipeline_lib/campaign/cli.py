"""Thin command entry point for the consolidated campaign workflow."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from ..errors import PipelineError
from ..source_bundle import REPOSITORY_ROOT
from .json_wire import decode_identity_object, rendered_json_bytes
from .model import EvidenceRef
from .store import CampaignStore
from .workflow import (
    DEFAULT_STATE_RELATIVE,
    check_transition,
    commit_transition,
    stage_transition,
    verify_transition,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core-campaign",
        description=(
            "Check, stage, commit, or verify the fixed local-only campaign "
            "transition; publication is not supported."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="read-only plan and validation")
    check.add_argument(
        "--process-receipt-ref",
        required=True,
        help="repo-relative path to a canonical check-log reference envelope",
    )

    stage = commands.add_parser("stage", help="create immutable staged evidence")
    stage.add_argument(
        "--process-receipt-ref",
        required=True,
        help="repo-relative path to a canonical check-log reference envelope",
    )

    commit = commands.add_parser("commit", help="commit one staged transition")
    commit.add_argument(
        "--staged-receipt",
        required=True,
        help="repo-relative path to a canonical staged-receipt reference envelope",
    )

    verify = commands.add_parser(
        "verify",
        help="read-only verification of an immutable root and live pointer",
    )
    verify.add_argument(
        "--state-root",
        required=True,
        help="repo-relative path to a canonical StateRoot reference envelope",
    )
    return parser


def _load_reference_document(
    store: CampaignStore,
    relative: str,
    *,
    kind: str,
    label: str,
) -> EvidenceRef:
    raw = store.read_snapshot(relative)
    document = decode_identity_object(raw, label=f"{label} reference")
    reference = EvidenceRef.from_document(document)
    if rendered_json_bytes(reference.to_document()) != raw:
        raise PipelineError(f"{label} reference is not the exact campaign rendering")
    if reference.kind != kind:
        raise PipelineError(f"{label} reference kind must be {kind}")
    envelope = store.reference_for(
        kind="artifact",
        raw=raw,
        target_content_sha256=reference.content_sha256,
    )
    if envelope.path != relative:
        raise PipelineError(f"{label} reference envelope path is not canonical")
    if store.read_exact(envelope) != raw:
        raise PipelineError(f"{label} reference envelope bytes are not exact")
    # The envelope transports a resume identity; the referenced object still
    # carries the actual authority and must independently authenticate.
    store.read_exact(reference)
    return reference


def _emit(reference: EvidenceRef, *, status: str) -> None:
    sys.stdout.buffer.write(rendered_json_bytes(reference.to_document()))
    sys.stdout.buffer.flush()
    print(status, file=sys.stderr)


def main(
    argv: Sequence[str] | None = None,
    *,
    store: CampaignStore | None = None,
) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    selected_store = store or CampaignStore(
        REPOSITORY_ROOT,
        DEFAULT_STATE_RELATIVE,
    )
    try:
        if arguments.command == "check":
            process_ref = _load_reference_document(
                selected_store,
                arguments.process_receipt_ref,
                kind="check-log",
                label="process receipt",
            )
            receipt = check_transition(
                selected_store,
                process_receipt_ref=process_ref,
            )
            _emit(
                receipt.plan,
                status="check passed; predicted plan reference (not staged)",
            )
            return 0
        if arguments.command == "stage":
            process_ref = _load_reference_document(
                selected_store,
                arguments.process_receipt_ref,
                kind="check-log",
                label="process receipt",
            )
            staged_ref = stage_transition(
                selected_store,
                process_receipt_ref=process_ref,
            )
            _emit(staged_ref, status="stage passed")
            return 0
        if arguments.command == "commit":
            staged_ref = _load_reference_document(
                selected_store,
                arguments.staged_receipt,
                kind="validation-receipt",
                label="staged receipt",
            )
            _commit, root_ref = commit_transition(
                selected_store,
                staged_receipt_ref=staged_ref,
            )
            _emit(root_ref, status="commit passed")
            return 0
        if arguments.command == "verify":
            root_ref = _load_reference_document(
                selected_store,
                arguments.state_root,
                kind="state-root",
                label="StateRoot",
            )
            verify_transition(selected_store, state_root_ref=root_ref)
            _emit(root_ref, status="verify passed")
            return 0
        raise AssertionError(f"unhandled campaign command: {arguments.command}")
    except PipelineError as exc:
        print(f"{arguments.command} failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
