"""Promotion, pin, release, and channel command handlers.

The launcher remains the composition root. Every invocation captures a fresh,
filtered namespace so legacy monkeypatch seams and nested handler calls retain
their original behavior without a reverse import.
"""

from __future__ import annotations

import argparse
import builtins
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class PromotionCommandServices:
    """Call-time launcher namespace consumed by this command domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "PromotionCommandServices":
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
        'DEFAULT_NIGHTLIES',
        'DEFAULT_PIN_SET_DIR',
        'DEFAULT_RELEASES',
        'PipelineError',
        'ROOT',
        'channel_pointer_path',
        'complete_core_bundle',
        'compose_core_golden',
        'compose_pin_set',
        'derive_core_id',
        'individual_core_semantic_id',
        'json',
        'load_json',
        'load_json_with_sha256',
        'promote_build_record',
        'promote_host_reproduction',
        'promote_local_release',
        'promote_source_candidate',
        'promote_tuned_variant',
        'require_active_core_golden',
        'require_individual_pin_identity',
        'require_lexical_repository_path',
        'update_channel',
        'validate_channel_pointer_document',
        'validate_local_release',
        'validate_pin_set_document',
    }
)


_BUILTIN_BINDINGS = frozenset(
    {
        'dict',
        'getattr',
        'isinstance',
        'len',
        'print',
        'set',
        'str',
    }
)


def cmd_promote(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    json = services['json']
    print = services['print']
    promote_build_record = services['promote_build_record']

    promoted = promote_build_record(args.golden, args.record, args.e2e_record, args.catalog)
    print(json.dumps(promoted, indent=2, sort_keys=True))
    return 0

def cmd_promote_host_reproduction(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    json = services['json']
    print = services['print']
    promote_host_reproduction = services['promote_host_reproduction']

    result = promote_host_reproduction(
        core_id=args.core,
        source_golden_path=args.source_golden,
        selected_e2e_path=args.selected_e2e,
        reproduction_e2e_path=args.reproduction_e2e,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_promote_source_candidate(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    json = services['json']
    print = services['print']
    promote_source_candidate = services['promote_source_candidate']

    result = promote_source_candidate(
        core_id=args.core,
        source_golden_path=args.source_golden,
        selected_e2e_path=args.selected_e2e,
        reproduction_e2e_path=args.reproduction_e2e,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_promote_tuned_variant(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    json = services['json']
    print = services['print']
    promote_tuned_variant = services['promote_tuned_variant']

    result = promote_tuned_variant(
        core_id=args.core,
        profile_id=args.tuning_profile,
        source_golden_path=args.source_golden,
        selected_e2e_path=args.selected_e2e,
        reproduction_e2e_path=args.reproduction_e2e,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_derive_core_id(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    derive_core_id = services['derive_core_id']
    json = services['json']
    print = services['print']

    result = derive_core_id(
        core_id=args.core,
        source_path=args.source_golden,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_compose_core_golden(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    compose_core_golden = services['compose_core_golden']
    json = services['json']
    print = services['print']

    result = compose_core_golden(
        core_id=args.core,
        source_path=args.source_golden,
        output_path=args.output,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_compose_pin_set(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    DEFAULT_NIGHTLIES = services['DEFAULT_NIGHTLIES']
    DEFAULT_PIN_SET_DIR = services['DEFAULT_PIN_SET_DIR']
    PipelineError = services['PipelineError']
    complete_core_bundle = services['complete_core_bundle']
    compose_pin_set = services['compose_pin_set']
    dict = services['dict']
    individual_core_semantic_id = services['individual_core_semantic_id']
    isinstance = services['isinstance']
    json = services['json']
    load_json = services['load_json']
    print = services['print']
    require_active_core_golden = services['require_active_core_golden']
    require_individual_pin_identity = services['require_individual_pin_identity']
    require_lexical_repository_path = services['require_lexical_repository_path']
    set = services['set']

    source_path = require_lexical_repository_path(
        args.source_golden,
        DEFAULT_NIGHTLIES,
        "individual pin source golden",
    )
    source = load_json(source_path)
    require_active_core_golden(source, args.core)
    build_goldens = source.get("build_goldens")
    if not isinstance(build_goldens, dict) or set(build_goldens) != {args.core}:
        raise PipelineError(
            "active pin composition requires an exact one-core nightly golden"
        )
    selection = complete_core_bundle(source, args.core)
    if selection is None:
        raise PipelineError(
            f"individual pin source has no complete {args.core} bundle"
        )
    semantic_id = individual_core_semantic_id(args.core, selection)
    if args.pin_id != semantic_id:
        raise PipelineError(f"--pin-id must be semantic ID {semantic_id}")
    expected_source = (DEFAULT_NIGHTLIES / semantic_id / "golden.json").resolve()
    if source_path != expected_source:
        raise PipelineError(
            "individual pin source path must use its exact semantic nightly ID"
        )
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_PIN_SET_DIR,
        "individual pin output",
    )
    expected_output = (DEFAULT_PIN_SET_DIR / f"{semantic_id}.json").resolve()
    if output_path != expected_output:
        raise PipelineError(
            f"individual pin output must be pins/core-sets/{semantic_id}.json"
        )
    document = compose_pin_set(
        pin_id=args.pin_id,
        core_ids=[args.core],
        source_paths=[source_path],
        output_path=output_path,
        catalog_path=args.catalog,
    )
    require_individual_pin_identity(document, pin_path=output_path)
    print(
        json.dumps(
            {
                "status": "created",
                "pin_id": document["pin_id"],
                "content_sha256": document["content_sha256"],
                **document["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def cmd_validate_pin_set(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    json = services['json']
    load_json = services['load_json']
    print = services['print']
    validate_pin_set_document = services['validate_pin_set_document']

    document = load_json(args.pin_set)
    report = validate_pin_set_document(
        document,
        verify_store=args.verify_store,
        verify_sources=args.verify_sources,
        document_path=args.pin_set,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1

def cmd_promote_release(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    DEFAULT_PIN_SET_DIR = services['DEFAULT_PIN_SET_DIR']
    DEFAULT_RELEASES = services['DEFAULT_RELEASES']
    PipelineError = services['PipelineError']
    json = services['json']
    len = services['len']
    load_json = services['load_json']
    print = services['print']
    promote_local_release = services['promote_local_release']
    require_individual_pin_identity = services['require_individual_pin_identity']
    require_lexical_repository_path = services['require_lexical_repository_path']

    pin_path = require_lexical_repository_path(
        args.pin_set,
        DEFAULT_PIN_SET_DIR,
        "individual release pin",
    )
    pin = load_json(pin_path)
    _core_id, semantic_id = require_individual_pin_identity(
        pin,
        pin_path=pin_path,
    )
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_RELEASES,
        "individual release output",
    )
    expected_output = (DEFAULT_RELEASES / semantic_id).resolve()
    if output_path != expected_output:
        raise PipelineError(
            f"individual release output must be .local-e2e/releases/{semantic_id}"
        )
    manifest = promote_local_release(pin_path, output_path, args.catalog)
    print(
        json.dumps(
            {
                "status": "created",
                "release_id": manifest["release_id"],
                "content_sha256": manifest["content_sha256"],
                "asset_count": len(manifest["assets"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def cmd_validate_release(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    json = services['json']
    load_json_with_sha256 = services['load_json_with_sha256']
    print = services['print']
    validate_local_release = services['validate_local_release']
    validate_pin_set_document = services['validate_pin_set_document']

    pin, pin_file_sha256 = load_json_with_sha256(args.pin_set)
    pin_report = validate_pin_set_document(
        pin,
        verify_store=args.verify_store,
        verify_sources=True,
        document_path=args.pin_set,
    )
    if pin_report["status"] != "valid":
        report = {
            "status": "invalid",
            "errors": ["supplied pin set is invalid", *pin_report["errors"]],
        }
    else:
        report = validate_local_release(args.release, pin, pin_file_sha256)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1

def cmd_update_channel(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    PipelineError = services['PipelineError']
    getattr = services['getattr']
    json = services['json']
    print = services['print']
    update_channel = services['update_channel']

    core_id = getattr(args, "core", None)
    if core_id is None:
        raise PipelineError("active channel mutation requires --core")
    result = update_channel(
        args.channel,
        args.target,
        core_id=core_id,
        expect_absent=args.expect_absent,
        expect_current=args.expect_current,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_validate_channel(args: argparse.Namespace, *, services: PromotionCommandServices) -> int:
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    channel_pointer_path = services['channel_pointer_path']
    getattr = services['getattr']
    json = services['json']
    load_json_with_sha256 = services['load_json_with_sha256']
    print = services['print']
    str = services['str']
    validate_channel_pointer_document = services['validate_channel_pointer_document']

    core_id = getattr(args, "core", None)
    if core_id is None:
        raise PipelineError("active channel validation requires --core")
    pointer_path = channel_pointer_path(args.channel, core_id)
    if not pointer_path.is_file() or pointer_path.is_symlink():
        raise PipelineError(f"channel pointer is unavailable: {pointer_path}")
    document, pointer_file_sha256 = load_json_with_sha256(pointer_path)
    report = validate_channel_pointer_document(
        document,
        expected_channel=args.channel,
        expected_core=core_id,
    )
    details = {
        "channel": args.channel,
        "pointer": str(pointer_path.relative_to(ROOT)),
        "pointer_file_sha256": pointer_file_sha256,
    }
    if core_id is not None:
        details["core_id"] = core_id
    report.update(details)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1
