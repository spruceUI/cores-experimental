"""Release, channel, promotion, and package lifecycle.

The launcher remains the composition root. Global dependencies are captured in
a filtered call-time service record so legacy wrappers and monkeypatch seams
remain dynamic without introducing a reverse import.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol
import zipfile


class _PinValidationContext(Protocol):
    """Read-once evidence caches supplied by the launcher composition root."""

    log_proofs: dict[tuple[str, str, str, str], tuple[bool, ...]]
    pinned_packages: set[tuple[str, str, str, str, int]]
    verified_bytes: dict[tuple[str, str], bytes]


_MODULE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = _MODULE_ROOT / "manifests" / "core-builds.json"
DEFAULT_STORE = _MODULE_ROOT / ".local-e2e" / "store"


@dataclass(frozen=True, slots=True)
class ReleaseLifecycleServices:
    """Call-time namespace required by this lifecycle domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "ReleaseLifecycleServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(
                f"missing lifecycle services: {names}"
            )
        return cls(
            MappingProxyType(
                {name: namespace[name] for name in _REQUIRED_BINDINGS}
            )
        )


def required_binding_names() -> frozenset[str]:
    """Return the exact launcher bindings consumed by this leaf."""

    return _REQUIRED_BINDINGS


_REQUIRED_BINDINGS = frozenset(
    {
        'ARCH_LAYOUT',
        'CHANNEL_KINDS',
        'CORE_ID_RE',
        'DEFAULT_CATALOG',
        'DEFAULT_CHANNELS',
        'DEFAULT_NIGHTLIES',
        'DEFAULT_PIN_SET_DIR',
        'DEFAULT_RELEASES',
        'DEFAULT_RUNS',
        'HOST_REPRODUCTION_SCOPE',
        'LOCAL_ID_RE',
        'Mapping',
        'Path',
        'PipelineError',
        'ROOT',
        'SHA256_RE',
        'SOURCE_CANDIDATE_REPRODUCTION_SCOPE',
        'STORE_TARGET_EVIDENCE_NAMES',
        'TUNED_REPRODUCTION_SCOPE',
        '_PinValidationContext',
        '_derive_channel_target',
        '_promote_build_record_locked',
        '_require_channel_target_sources_eligible',
        '_require_current_selection_source_authority',
        '_require_pin_current_selection_authority',
        '_require_public_ordinary_catalog',
        '_resolve_release_pin',
        '_store_reference',
        '_validate_channel_pointer_document',
        '_validate_local_release',
        '_validate_pin_set_document',
        '_verify_local_store',
        'add_zip_entry',
        'atomic_create_json',
        'atomic_write_json',
        'candidate_golden_id_is_well_formed',
        'channel_pointer_path',
        'channel_target_root',
        'complete_core_bundle',
        'compose_pin_set',
        'copy',
        'create_host_reproduction_proof',
        'decode_json_object',
        'dt',
        'durable_atomic_channel_write',
        'golden_content_sha256',
        'host_reproduction_content_sha256',
        'immutable_promotion_output_paths',
        'individual_core_semantic_id',
        'json',
        'load_catalog',
        'load_catalog_with_sha256',
        'load_json',
        'load_json_with_sha256',
        'manifest_lock',
        'metadata_matches_replacement',
        'one_core_golden_document',
        'os',
        'recipe_snapshot',
        'release_content_sha256',
        'require_active_candidate_golden_path',
        'require_active_core_golden',
        'require_canonical_store_entry',
        'require_contained',
        'require_empty_golden_slot',
        'require_golden_sources_eligible',
        'require_host_reproduction_equivalence',
        'require_individual_pin_identity',
        'require_lexical_repository_path',
        'require_manifest_reference_path',
        'require_ordinary_promotion_catalog',
        'require_pin_sources_eligible',
        'require_source_candidate_equivalence',
        'require_source_commits_eligible',
        'require_tuned_candidate_equivalence',
        'resolve_tuning_candidate_selection',
        'runner_evidence_is_hardened',
        'safe_child',
        'sha256_bytes',
        'sha256_file',
        'shutil',
        'snapshot_json_file',
        'store_bytes',
        'store_file',
        'tempfile',
        'utc_now',
        'validate_build_record_identity',
        'validate_e2e_evidence',
        'validate_golden_document',
        'validate_host_reproduction_e2e_evidence',
        'validate_pin_set_document',
        'validate_source_candidate_e2e_evidence',
        'validate_tuned_e2e_evidence',
        'validated_embedded_source_candidate_shape',
        'validated_host_reproduction_shape',
        'validated_metadata_replacement',
        'validated_output_reproduction_shape',
        'validated_tuning_candidate_selection',
        'verified_json_object',
        'verify_local_store',
        'zipfile',
    }
)


def _validate_local_release(
    release_root: Path,
    pin: dict,
    pin_file_sha256: str,
    expected_release_id: str | None = None,
    *,
    manifest_document: dict | None = None,
    services: ReleaseLifecycleServices,
) -> dict:
    errors: list[str] = []
    release_root = services['require_lexical_repository_path'](
        release_root, services['DEFAULT_RELEASES'], "local release"
    )
    manifest_path = release_root / "release-manifest.json"
    if manifest_document is None:
        try:
            manifest, _manifest_file_sha256 = services['load_json_with_sha256'](manifest_path)
        except services['PipelineError'] as exc:
            return {"status": "invalid", "errors": [str(exc)]}
    else:
        manifest = manifest_document
    if (
        manifest.get("schema_version") != 1
        or not manifest.get("local_only")
        or manifest.get("publication") != "disabled"
    ):
        errors.append("release manifest contract is invalid")
    expected_release_id = expected_release_id or release_root.name
    if (
        manifest.get("release_id") != expected_release_id
        or not isinstance(manifest.get("release_id"), str)
        or not services['LOCAL_ID_RE'].fullmatch(manifest["release_id"])
    ):
        errors.append("release ID is invalid")
    if manifest.get("content_sha256") != services['release_content_sha256'](manifest):
        errors.append("release content digest is invalid")
    expected_pin = {
        "pin_id": pin.get("pin_id"),
        "content_sha256": pin.get("content_sha256"),
        "file_sha256": pin_file_sha256,
    }
    if manifest.get("pin") != expected_pin:
        errors.append("release is not bound to the supplied pin")
    assets = manifest.get("assets", [])
    if not isinstance(assets, list):
        errors.append("release assets must be an array")
        assets = []
    expected_names = {"release-manifest.json"}
    seen_cores: set[str] = set()
    pin_cores = pin.get("cores")
    if not isinstance(pin_cores, dict):
        errors.append("release pin cores must be an object")
        pin_cores = {}
    pin_scope = pin.get("scope")
    if not isinstance(pin_scope, list) or any(
        not isinstance(core_id, str) for core_id in pin_scope
    ):
        errors.append("release pin scope must be an array of core IDs")
        pin_scope_set: set[str] | None = None
    else:
        pin_scope_set = set(pin_scope)
    for asset in assets:
        if not isinstance(asset, dict):
            errors.append("release asset must be an object")
            continue
        core_id = asset.get("core_id")
        name = asset.get("path")
        if (
            not isinstance(core_id, str)
            or services['CORE_ID_RE'].fullmatch(core_id) is None
            or not isinstance(name, str)
            or core_id in seen_cores
            or name != f"{core_id}_libretro.zip"
        ):
            errors.append("release asset identity is invalid")
            continue
        seen_cores.add(core_id)
        expected_names.add(name)
        core_record = pin_cores.get(core_id)
        selection = (
            core_record.get("selection") if isinstance(core_record, dict) else None
        )
        if not isinstance(selection, dict):
            errors.append(f"{core_id}: release pin selection is invalid")
            continue
        package = selection.get("package")
        if not isinstance(package, dict):
            errors.append(f"{core_id}: release pin package is invalid")
            continue
        path = services['require_lexical_repository_path'](
            release_root / name,
            release_root,
            f"{core_id} release asset",
        )
        if (
            asset.get("sha256") != package.get("sha256")
            or asset.get("size") != package.get("size")
            or asset.get("selection_sha256") != selection.get("selection_sha256")
            or asset.get("source_tier") != selection.get("tier")
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != asset.get("size")
            or services['sha256_file'](path) != asset.get("sha256")
        ):
            errors.append(f"{core_id}: released package differs from its pin")
    if pin_scope_set is not None and seen_cores != pin_scope_set:
        errors.append("release core scope does not match the pin")
    actual_names = {
        str(path.relative_to(release_root))
        for path in release_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_names != expected_names:
        errors.append("release contains missing or unexpected files")
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def validate_local_release(
    release_root: Path,
    pin: dict,
    pin_file_sha256: str,
    expected_release_id: str | None = None,
    *,
    services: ReleaseLifecycleServices,
) -> dict:
    """Validate disk bytes against their uniquely resolved, deeply proven pin."""

    try:
        release_root = services['require_lexical_repository_path'](
            release_root, services['DEFAULT_RELEASES'], "local release"
        )
        manifest, _manifest_sha256 = services['load_json_with_sha256'](
            release_root / "release-manifest.json"
        )
        validation_context = services['_PinValidationContext']()
        resolved_pin, resolved_pin_path = services['_resolve_release_pin'](
            manifest,
            validation_context,
        )
        resolved_pin_sha256 = services['sha256_file'](resolved_pin_path)
        if pin != resolved_pin or pin_file_sha256 != resolved_pin_sha256:
            raise services['PipelineError'](
                "release supplied pin differs from its immutable manifest pin"
            )
        pin_report = services['_validate_pin_set_document'](
            resolved_pin,
            verify_store=True,
            verify_sources=True,
            document_path=resolved_pin_path,
            _validation_context=validation_context,
        )
        if pin_report["status"] == "valid":
            services['_require_pin_current_selection_authority'](
                resolved_pin,
                operation="local release validation",
            )
        report = services['_validate_local_release'](
            release_root,
            resolved_pin,
            resolved_pin_sha256,
            expected_release_id,
            manifest_document=manifest,
        )
        report["errors"] = [*pin_report["errors"], *report["errors"]]
        report["status"] = "valid" if not report["errors"] else "invalid"
        return report
    except services['PipelineError'] as exc:
        return {"status": "invalid", "errors": [str(exc)]}


def promote_local_release(
    pin_path: Path,
    output_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    *,
    services: ReleaseLifecycleServices,
) -> dict:
    pin_path = services['require_lexical_repository_path'](
        pin_path, services['DEFAULT_PIN_SET_DIR'], "individual release pin"
    )
    output_path = services['require_lexical_repository_path'](
        output_path, services['DEFAULT_RELEASES'], "individual release output"
    )
    if not services['LOCAL_ID_RE'].fullmatch(output_path.name):
        raise services['PipelineError']("release directory name is invalid")
    pin, pin_file_sha256 = services['load_json_with_sha256'](pin_path)
    report = services['validate_pin_set_document'](
        pin,
        verify_store=True,
        verify_sources=True,
        document_path=pin_path,
    )
    if report["status"] != "valid":
        raise services['PipelineError']("release pin is invalid:\n- " + "\n- ".join(report["errors"]))
    _core_id, semantic_id = services['require_individual_pin_identity'](
        pin,
        pin_path=pin_path,
    )
    expected_output = (services['DEFAULT_RELEASES'] / semantic_id).resolve()
    if output_path != expected_output:
        raise services['PipelineError'](
            f"individual release output must be .local-e2e/releases/{semantic_id}"
        )
    catalog = services['load_json'](catalog_path)
    catalog_file_sha256 = services['_require_public_ordinary_catalog'](
        catalog_path,
        catalog,
    )
    services['_require_pin_current_selection_authority'](
        pin,
        operation="local release promotion",
        catalog=catalog,
    )
    services['require_pin_sources_eligible'](catalog, pin)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with services['manifest_lock'](output_path):
        if output_path.exists():
            raise services['PipelineError'](f"refusing to replace existing local release: {output_path}")
        temporary = services['Path'](services['tempfile'].mkdtemp(prefix=f".{output_path.name}.", dir=output_path.parent))
        try:
            assets = []
            for core_id in pin["scope"]:
                selection = pin["cores"][core_id]["selection"]
                package = selection["package"]
                source = services['require_canonical_store_entry'](
                    package, "packages", f"{core_id} release source"
                )
                destination = services['safe_child'](
                    temporary, package["name"], f"{core_id} release destination"
                )
                services['shutil'].copyfile(source, destination)
                services['os'].chmod(destination, 0o644)
                if (
                    destination.stat().st_size != package["size"]
                    or services['sha256_file'](destination) != package["sha256"]
                ):
                    raise services['PipelineError'](f"{core_id}: copied release package changed")
                assets.append(
                    {
                        "core_id": core_id,
                        "path": package["name"],
                        "sha256": package["sha256"],
                        "size": package["size"],
                        "source_tier": selection["tier"],
                        "selection_sha256": selection["selection_sha256"],
                    }
                )
            manifest = {
                "$schema": "../../../manifests/local-release.schema.json",
                "schema_version": 1,
                "release_id": output_path.name,
                # Releases are immutable views of the pin and inherit its
                # timestamp for deterministic byte-for-byte reconstruction.
                "created_at": pin.get("created_at"),
                "local_only": True,
                "publication": "disabled",
                "pin": {
                    "pin_id": pin["pin_id"],
                    "content_sha256": pin["content_sha256"],
                    "file_sha256": pin_file_sha256,
                },
                "assets": assets,
            }
            manifest["content_sha256"] = services['release_content_sha256'](manifest)
            services['atomic_write_json'](temporary / "release-manifest.json", manifest)
            validation = services['_validate_local_release'](
                temporary,
                pin,
                pin_file_sha256,
                expected_release_id=output_path.name,
                manifest_document=manifest,
            )
            if validation["status"] != "valid":
                raise services['PipelineError'](
                    "staged local release is invalid:\n- "
                    + "\n- ".join(validation["errors"])
                )
            if services['sha256_file'](catalog_path) != catalog_file_sha256:
                raise services['PipelineError'](
                    "canonical catalog changed before release promotion"
                )
            temporary.rename(output_path)
        except Exception:
            if temporary.exists():
                services['shutil'].rmtree(temporary)
            raise
    return manifest


def channel_pointer_path(channel: str, core_id: str | None = None, *, services: ReleaseLifecycleServices) -> Path:
    if channel not in services['CHANNEL_KINDS']:
        raise services['PipelineError'](f"unknown local channel: {channel}")
    if core_id is not None and not services['CORE_ID_RE'].fullmatch(core_id):
        raise services['PipelineError']("individual channel core ID is invalid")
    filename = f"{channel}.{core_id}.json" if core_id else f"{channel}.json"
    try:
        relative = (services['DEFAULT_CHANNELS'] / filename).relative_to(services['ROOT'])
    except ValueError as exc:
        raise services['PipelineError']("channel pointer directory must be inside the repository") from exc
    return services['require_manifest_reference_path'](
        {"path": str(relative)}, services['DEFAULT_CHANNELS'], "channel pointer"
    )


def channel_target_root(channel: str, *, services: ReleaseLifecycleServices) -> Path:
    if channel == "nightly":
        return services['DEFAULT_NIGHTLIES']
    if channel == "pinned":
        return services['DEFAULT_PIN_SET_DIR']
    if channel == "release":
        return services['DEFAULT_RELEASES']
    raise services['PipelineError'](f"unknown local channel: {channel}")


def _resolve_release_pin(
    manifest: dict,
    validation_context: _PinValidationContext | None = None,
    *,
    services: ReleaseLifecycleServices,
) -> tuple[dict, Path]:
    release_pin = manifest.get("pin")
    if not isinstance(release_pin, dict):
        raise services['PipelineError']("release manifest pin identity is invalid")
    matches: list[tuple[dict, Path]] = []
    if services['DEFAULT_PIN_SET_DIR'].is_dir():
        for candidate in sorted(services['DEFAULT_PIN_SET_DIR'].glob("*.json")):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                pin, pin_file_sha256 = services['snapshot_json_file'](
                    candidate,
                    "release manifest pin",
                    validation_context,
                )
            except services['PipelineError']:
                continue
            if pin_file_sha256 != release_pin.get("file_sha256"):
                continue
            try:
                services['require_individual_pin_identity'](pin, pin_path=candidate)
            except services['PipelineError']:
                continue
            if (
                pin.get("pin_id") == release_pin.get("pin_id")
                and pin.get("content_sha256") == release_pin.get("content_sha256")
            ):
                matches.append((pin, candidate))
    if len(matches) != 1:
        raise services['PipelineError'](
            "release manifest must resolve exactly one immutable pin-set document"
        )
    return matches[0]


def resolve_release_pin(manifest: dict, *, services: ReleaseLifecycleServices) -> tuple[dict, Path]:
    """Resolve one release pin with a fresh proof context."""

    return services['_resolve_release_pin'](manifest, services['_PinValidationContext']())


def _derive_channel_target(
    channel: str,
    target_path: Path,
    _validation_context: _PinValidationContext | None = None,
    *,
    core_id: str | None = None,
    services: ReleaseLifecycleServices,
) -> dict:
    if _validation_context is None:
        _validation_context = services['_PinValidationContext']()
    kind = services['CHANNEL_KINDS'].get(channel)
    if kind is None:
        raise services['PipelineError'](f"unknown local channel: {channel}")
    target_path = services['require_lexical_repository_path'](
        target_path,
        services['channel_target_root'](channel),
        f"{channel} channel target",
    )
    relative = str(target_path.relative_to(services['ROOT']))
    if not target_path.is_file() or target_path.is_symlink():
        raise services['PipelineError'](f"{channel} channel target must be a regular file")
    if channel == "release" and target_path.name != "release-manifest.json":
        raise services['PipelineError']("release channel target must be a release-manifest.json")

    document, target_file_sha256 = services['snapshot_json_file'](
        target_path,
        f"{channel} channel target",
        _validation_context,
    )
    identity = (
        target_path.parent.name
        if channel == "nightly" and core_id is not None
        else document.get("release_id" if channel == "release" else "pin_id", "")
    )
    content_sha256 = document.get("content_sha256", "")
    preflight_errors = []
    if not isinstance(identity, str) or not services['LOCAL_ID_RE'].fullmatch(identity):
        preflight_errors.append(f"{channel} channel target ID is invalid")
    if not isinstance(content_sha256, str) or not services['SHA256_RE'].fullmatch(content_sha256):
        preflight_errors.append(f"{channel} channel target content digest is invalid")
    if preflight_errors:
        raise services['PipelineError'](
            f"{channel} channel target is invalid:\n- " + "\n- ".join(preflight_errors)
        )
    if channel == "nightly":
        report = services['validate_golden_document'](document)
        if report["status"] == "valid":
            report["errors"].extend(
                services['_verify_local_store'](document, _validation_context)
            )
        complete_bundle = None
        complete_bundles: list[tuple[str, Mapping[str, object]]] = []
        build_goldens = document.get("build_goldens")
        if core_id is not None and (
            not isinstance(build_goldens, dict)
            or set(build_goldens) != {core_id}
        ):
            report["errors"].append(
                "individual nightly channel target must contain exactly its core"
            )
        candidates = (
            (core_id,)
            if core_id is not None and isinstance(build_goldens, dict)
            else (build_goldens if isinstance(build_goldens, dict) else ())
        )
        for candidate_core_id in candidates:
            try:
                candidate_bundle = services['complete_core_bundle'](document, candidate_core_id)
                if candidate_bundle is not None:
                    complete_bundles.append((candidate_core_id, candidate_bundle))
                    if complete_bundle is None:
                        complete_bundle = candidate_bundle
            except services['PipelineError'] as exc:
                report["errors"].append(str(exc))
        if complete_bundles:
            current_catalog = services['load_catalog'](services['DEFAULT_CATALOG'])
            for candidate_core_id, candidate_bundle in complete_bundles:
                try:
                    services['_require_current_selection_source_authority'](
                        current_catalog,
                        candidate_bundle,
                        core_id=candidate_core_id,
                        operation="nightly channel target",
                    )
                except services['PipelineError'] as exc:
                    report["errors"].append(str(exc))
        if complete_bundle is None:
            report["errors"].append(
                (
                    f"nightly channel target has no complete {core_id} bundle"
                    if core_id is not None
                    else "nightly channel target has no complete build-golden bundle"
                )
            )
        elif core_id is not None:
            try:
                semantic_id = services['individual_core_semantic_id'](
                    core_id, complete_bundle
                )
                if identity != semantic_id:
                    report["errors"].append(
                        "individual nightly channel target ID is not semantic"
                    )
            except services['PipelineError'] as exc:
                report["errors"].append(str(exc))
    elif channel == "pinned":
        report = services['_validate_pin_set_document'](
            document,
            verify_store=True,
            verify_sources=True,
            document_path=target_path,
            _validation_context=_validation_context,
        )
        if report["status"] == "valid":
            try:
                services['_require_pin_current_selection_authority'](
                    document,
                    operation="pinned channel target",
                )
            except services['PipelineError'] as exc:
                report["errors"].append(str(exc))
        if core_id is not None:
            try:
                pinned_core_id, semantic_id = services['require_individual_pin_identity'](
                    document,
                    pin_path=target_path,
                )
                if pinned_core_id != core_id or identity != semantic_id:
                    report["errors"].append(
                        "individual pinned channel target identity differs"
                    )
            except services['PipelineError'] as exc:
                report["errors"].append(str(exc))
    else:
        pin, pin_path = services['_resolve_release_pin'](document, _validation_context)
        release_pin = document.get("pin")
        release_pin_file_sha256 = (
            release_pin.get("file_sha256") if isinstance(release_pin, dict) else ""
        )
        pin_report = services['_validate_pin_set_document'](
            pin,
            verify_store=True,
            verify_sources=True,
            document_path=pin_path,
            _validation_context=_validation_context,
        )
        if pin_report["status"] == "valid":
            try:
                services['_require_pin_current_selection_authority'](
                    pin,
                    operation="release channel target",
                )
            except services['PipelineError'] as exc:
                pin_report["errors"].append(str(exc))
        report = services['_validate_local_release'](
            target_path.parent,
            pin,
            release_pin_file_sha256,
            expected_release_id=identity,
            manifest_document=document,
        )
        report["errors"] = [*pin_report["errors"], *report["errors"]]
        if core_id is not None:
            try:
                released_core_id, semantic_id = services['require_individual_pin_identity'](
                    pin,
                    pin_path=pin_path,
                )
                if released_core_id != core_id or identity != semantic_id:
                    report["errors"].append(
                        "individual release channel target identity differs"
                    )
            except services['PipelineError'] as exc:
                report["errors"].append(str(exc))

    canonical_relative = target_path.relative_to(services['channel_target_root'](channel).resolve())
    if channel == "nightly" and (
        len(canonical_relative.parts) != 2
        or not services['LOCAL_ID_RE'].fullmatch(canonical_relative.parts[0])
        or canonical_relative.parts[1] != "golden.json"
    ):
        report["errors"].append(
            "nightly channel target must be <nightly-id>/golden.json"
        )
    elif channel == "pinned" and canonical_relative.parts != (f"{identity}.json",):
        report["errors"].append("pinned channel target filename must match its pin ID")
    elif channel == "release" and canonical_relative.parts != (
        identity,
        "release-manifest.json",
    ):
        report["errors"].append(
            "release channel target directory must match its release ID"
        )
    after_sha256 = services['sha256_file'](target_path)
    if after_sha256 != target_file_sha256:
        report["errors"].append(f"{channel} channel target changed during validation")
    if report["errors"]:
        raise services['PipelineError'](
            f"{channel} channel target is invalid:\n- " + "\n- ".join(report["errors"])
        )
    return {
        "kind": kind,
        "path": relative,
        "id": identity,
        "file_sha256": target_file_sha256,
        "content_sha256": content_sha256,
    }


def derive_channel_target(
    channel: str,
    target_path: Path,
    *,
    core_id: str | None = None,
    services: ReleaseLifecycleServices,
) -> dict:
    """Derive a channel target with a fresh proof context."""

    return services['_derive_channel_target'](
        channel,
        target_path,
        services['_PinValidationContext'](),
        core_id=core_id,
    )


def _validate_channel_pointer_document(
    document: dict,
    *,
    expected_channel: str | None = None,
    expected_core: str | None = None,
    verify_target: bool = True,
    _validation_context: _PinValidationContext | None = None,
    services: ReleaseLifecycleServices,
) -> dict:
    if _validation_context is None:
        _validation_context = services['_PinValidationContext']()
    errors: list[str] = []
    required_fields = {
        "$schema",
        "schema_version",
        "channel",
        "updated_at",
        "local_only",
        "publication",
        "target",
    }
    schema_version = document.get("schema_version")
    if schema_version == 2:
        required_fields.add("core_id")
    if set(document) != required_fields:
        errors.append("channel pointer fields are not exact")
    if document.get("$schema") != "../../manifests/channel-pointer.schema.json":
        errors.append("channel pointer schema reference is invalid")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        errors.append("schema_version must be 1 or 2")
    if expected_core is None:
        if type(schema_version) is not int or schema_version != 1:
            errors.append("aggregate channel alias must use schema_version 1")
    elif type(schema_version) is not int or schema_version != 2:
        errors.append("individual channel alias must use schema_version 2")
    if document.get("local_only") is not True or document.get("publication") != "disabled":
        errors.append("channel pointer must be local-only and publication-disabled")
    channel = document.get("channel")
    if not isinstance(channel, str) or channel not in services['CHANNEL_KINDS']:
        errors.append("channel is invalid")
    if expected_channel is not None and channel != expected_channel:
        errors.append("channel pointer document does not match its alias filename")
    core_id = document.get("core_id") if schema_version == 2 else None
    if schema_version == 2 and (
        not isinstance(core_id, str) or services['CORE_ID_RE'].fullmatch(core_id) is None
    ):
        errors.append("individual channel core ID is invalid")
    if expected_core is not None and core_id != expected_core:
        errors.append("channel pointer document does not match its core alias filename")
    if expected_core is None and "core_id" in document:
        errors.append("aggregate channel pointer must not name a core")
    updated_at = document.get("updated_at")
    try:
        parsed_updated_at = services['dt'].datetime.fromisoformat(updated_at)
        if parsed_updated_at.utcoffset() != services['dt'].timedelta(0):
            raise ValueError
    except (TypeError, ValueError):
        errors.append("updated_at must be an aware UTC timestamp")

    target = document.get("target")
    target_fields = {"kind", "path", "id", "file_sha256", "content_sha256"}
    if not isinstance(target, dict) or set(target) != target_fields:
        errors.append("channel target fields are not exact")
        target = None
    elif isinstance(channel, str) and channel in services['CHANNEL_KINDS']:
        if target.get("kind") != services['CHANNEL_KINDS'][channel]:
            errors.append("channel target kind is invalid")
        if not isinstance(target.get("id"), str) or not services['LOCAL_ID_RE'].fullmatch(
            target["id"]
        ):
            errors.append("channel target ID is invalid")
        if not isinstance(target.get("file_sha256"), str) or not services['SHA256_RE'].fullmatch(
            target["file_sha256"]
        ):
            errors.append("channel target file digest is invalid")
        if not isinstance(
            target.get("content_sha256"), str
        ) or not services['SHA256_RE'].fullmatch(target["content_sha256"]):
            errors.append("channel target content digest is invalid")
        if not isinstance(target.get("path"), str):
            errors.append("channel target path is invalid")
        else:
            try:
                target_path = services['require_manifest_reference_path'](
                    target, services['channel_target_root'](channel), f"{channel} channel target"
                )
                if verify_target:
                    if core_id is None:
                        derived = services['_derive_channel_target'](
                            channel, target_path, _validation_context
                        )
                    else:
                        derived = services['_derive_channel_target'](
                            channel,
                            target_path,
                            _validation_context,
                            core_id=core_id,
                        )
                    if target != derived:
                        errors.append("channel target identity no longer matches the pointer")
            except services['PipelineError'] as exc:
                errors.append(str(exc))
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def validate_channel_pointer_document(
    document: dict,
    *,
    expected_channel: str | None = None,
    expected_core: str | None = None,
    verify_target: bool = True,
    services: ReleaseLifecycleServices,
) -> dict:
    """Validate a channel pointer with a fresh proof context."""

    return services['_validate_channel_pointer_document'](
        document,
        expected_channel=expected_channel,
        expected_core=expected_core,
        verify_target=verify_target,
        _validation_context=services['_PinValidationContext'](),
    )


def _require_channel_target_sources_eligible(
    catalog: dict,
    channel: str,
    target_path: Path,
    *,
    core_id: str | None = None,
    target_document: dict | None = None,
    validation_context: _PinValidationContext | None = None,
    services: ReleaseLifecycleServices,
) -> None:
    target_path = services['require_lexical_repository_path'](
        target_path,
        services['channel_target_root'](channel),
        f"{channel} channel target",
    )
    document = target_document
    if document is None:
        document, _file_sha256 = services['snapshot_json_file'](
            target_path,
            f"{channel} channel target",
            validation_context,
        )
    if channel == "nightly":
        if core_id is None:
            services['require_golden_sources_eligible'](catalog, document)
        else:
            selection = services['complete_core_bundle'](document, core_id)
            if selection is None:
                raise services['PipelineError'](
                    f"nightly channel target has no complete {core_id} bundle"
                )
            services['require_source_commits_eligible'](
                catalog,
                (
                    (core_id, target["golden_record"].get("source"))
                    for target in selection["targets"].values()
                ),
            )
    elif channel == "pinned":
        services['require_pin_sources_eligible'](catalog, document)
    elif channel == "release":
        pin, _ = services['_resolve_release_pin'](document, validation_context)
        services['require_pin_sources_eligible'](catalog, pin)
    else:
        raise services['PipelineError'](f"unknown local channel: {channel}")


def require_channel_target_sources_eligible(
    catalog: dict,
    channel: str,
    target_path: Path,
    *,
    core_id: str | None = None,
    services: ReleaseLifecycleServices,
) -> None:
    """Check channel source eligibility with a fresh proof context."""

    canonical_catalog = services['load_catalog'](services['DEFAULT_CATALOG'])
    if catalog != canonical_catalog:
        raise services['PipelineError'](
            "channel source eligibility requires the canonical catalog bytes"
        )
    services['_require_channel_target_sources_eligible'](
        canonical_catalog,
        channel,
        target_path,
        core_id=core_id,
        validation_context=services['_PinValidationContext'](),
    )


def update_channel(
    channel: str,
    target_path: Path,
    *,
    core_id: str,
    expect_absent: bool = False,
    expect_current: str | None = None,
    catalog_path: Path = DEFAULT_CATALOG,
    services: ReleaseLifecycleServices,
) -> dict:
    validation_context = services['_PinValidationContext']()
    if expect_absent == (expect_current is not None):
        raise services['PipelineError'](
            "exactly one of --expect-absent or --expect-current is required"
        )
    if expect_current is not None and not services['SHA256_RE'].fullmatch(expect_current):
        raise services['PipelineError']("--expect-current must be an exact SHA256")
    catalog = services['load_json'](catalog_path)
    catalog_file_sha256 = services['_require_public_ordinary_catalog'](
        catalog_path,
        catalog,
    )
    catalog_cores = catalog.get("cores")
    if not isinstance(catalog_cores, dict):
        raise services['PipelineError']("catalog cores must be an object")
    if not isinstance(core_id, str) or services['CORE_ID_RE'].fullmatch(core_id) is None:
        raise services['PipelineError']("individual channel core ID is invalid")
    if core_id not in catalog_cores:
        raise services['PipelineError'](f"individual channel core is not cataloged: {core_id}")
    pointer_path = services['channel_pointer_path'](channel, core_id)
    with services['manifest_lock'](pointer_path):
        current_document = None
        pointer_exists = pointer_path.exists() or pointer_path.is_symlink()
        if expect_absent:
            if pointer_exists:
                raise services['PipelineError'](f"channel pointer already exists: {pointer_path}")
            current_sha256 = None
        else:
            if not pointer_exists or not pointer_path.is_file() or pointer_path.is_symlink():
                raise services['PipelineError'](f"current channel pointer is unavailable: {pointer_path}")
            current_bytes = pointer_path.read_bytes()
            current_sha256 = services['sha256_bytes'](current_bytes)
            if current_sha256 != expect_current:
                raise services['PipelineError'](
                    f"channel compare-and-swap failed: expected {expect_current}, "
                    f"found {current_sha256}"
                )
            try:
                current_document = services['decode_json_object'](
                    current_bytes, "current channel pointer"
                )
            except services['PipelineError'] as exc:
                raise services['PipelineError']("current channel pointer is not valid JSON") from exc
            current_report = services['_validate_channel_pointer_document'](
                current_document,
                expected_channel=channel,
                expected_core=core_id,
                _validation_context=validation_context,
            )
            if current_report["status"] != "valid":
                raise services['PipelineError'](
                    "current channel pointer is invalid:\n- "
                    + "\n- ".join(current_report["errors"])
                )

        target = services['_derive_channel_target'](
            channel,
            target_path,
            validation_context,
            core_id=core_id,
        )
        canonical_target = services['safe_child'](
            services['ROOT'], target["path"], f"{channel} channel target"
        )
        target_document = services['verified_json_object'](
            canonical_target,
            target["file_sha256"],
            f"{channel} channel target",
            validation_context,
        )
        if channel == "nightly":
            services['require_active_core_golden'](target_document, core_id)
        services['_require_channel_target_sources_eligible'](
            catalog,
            channel,
            target_path,
            core_id=core_id,
            target_document=target_document,
            validation_context=validation_context,
        )
        if current_document is not None and current_document.get("target") == target:
            return {
                "status": "unchanged",
                "channel": channel,
                "pointer": str(pointer_path.relative_to(services['ROOT'])),
                "pointer_file_sha256": current_sha256,
                "target": target,
            }
        document = {
            "$schema": "../../manifests/channel-pointer.schema.json",
            "schema_version": 2,
            "channel": channel,
            "core_id": core_id,
            "updated_at": services['utc_now'](),
            "local_only": True,
            "publication": "disabled",
            "target": target,
        }
        report = services['_validate_channel_pointer_document'](
            document,
            expected_channel=channel,
            expected_core=core_id,
            _validation_context=validation_context,
        )
        if report["status"] != "valid":
            raise services['PipelineError'](
                "new channel pointer is invalid:\n- " + "\n- ".join(report["errors"])
            )
        if current_sha256 is not None and services['sha256_file'](pointer_path) != current_sha256:
            raise services['PipelineError']("channel pointer changed during compare-and-swap")
        if services['sha256_file'](canonical_target) != target["file_sha256"]:
            raise services['PipelineError']("channel target changed before pointer update")
        if services['sha256_file'](catalog_path) != catalog_file_sha256:
            raise services['PipelineError'](
                "canonical catalog changed before channel pointer update"
            )
        pointer_file_sha256 = services['sha256_bytes'](
            (services['json'].dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        services['durable_atomic_channel_write'](pointer_path, document, create=expect_absent)
        return {
            "status": "created" if expect_absent else "updated",
            "channel": channel,
            "pointer": str(pointer_path.relative_to(services['ROOT'])),
            "pointer_file_sha256": pointer_file_sha256,
            "target": target,
        }


def require_empty_golden_slot(golden: dict, core_id: str, arch: str, *, services: ReleaseLifecycleServices) -> None:
    if golden.get("build_goldens", {}).get(core_id, {}).get(arch) is not None:
        raise services['PipelineError'](
            f"immutable build golden already exists for {core_id}/{arch}; create a new pin set"
        )


def require_active_candidate_golden_path(
    golden_path: Path,
    golden: dict,
    *,
    services: ReleaseLifecycleServices,
) -> Path:
    """Bind a mutable working golden to its exact candidate identity."""

    golden_path = services['require_lexical_repository_path'](
        golden_path,
        services['DEFAULT_NIGHTLIES'],
        "active core candidate golden",
    )
    relative = golden_path.relative_to(services['DEFAULT_NIGHTLIES'].resolve())
    core_id = golden.get("core_id")
    candidate_id = golden.get("pin_id")
    if (
        len(relative.parts) != 2
        or relative.parts[1] != "golden.json"
        or relative.parts[0] != candidate_id
        or not services['candidate_golden_id_is_well_formed'](core_id, candidate_id)
    ):
        raise services['PipelineError'](
            "active core candidate must be its exact "
            "<core>-candidate-<label>/golden.json path"
        )
    return golden_path


def promote_build_record(
    golden_path: Path,
    record_path: Path,
    e2e_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    store_root: Path = DEFAULT_STORE,
    *,
    services: ReleaseLifecycleServices,
) -> dict:
    golden_path = services['require_lexical_repository_path'](
        golden_path, services['DEFAULT_NIGHTLIES'], "individual promotion golden"
    )
    record_path = services['require_lexical_repository_path'](
        record_path, services['DEFAULT_RUNS'], "build record"
    )
    e2e_path = services['require_lexical_repository_path'](
        e2e_path, services['DEFAULT_RUNS'], "E2E record"
    )
    # Keep the cheap pre-lock gate so an obviously ineligible candidate cannot
    # create lock state. The E2E-bound snapshot is checked authoritatively
    # inside the lock before any promotion policy is applied.
    catalog = services['load_catalog'](catalog_path)
    services['require_ordinary_promotion_catalog'](catalog, "legacy promotion", catalog_path)
    candidate_record = services['load_json'](record_path)
    services['require_source_commits_eligible'](
        catalog,
        [(candidate_record.get("core_id"), candidate_record.get("source"))],
    )
    with services['manifest_lock'](golden_path):
        return services['_promote_build_record_locked'](
            golden_path, record_path, e2e_path, catalog_path, store_root
        )


def _promote_build_record_locked(
    golden_path: Path,
    record_path: Path,
    e2e_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    store_root: Path = DEFAULT_STORE,
    *,
    services: ReleaseLifecycleServices,
) -> dict:
    golden_path = services['require_lexical_repository_path'](
        golden_path, services['DEFAULT_NIGHTLIES'], "individual promotion golden"
    )
    record_path = services['require_lexical_repository_path'](
        record_path, services['DEFAULT_RUNS'], "build record"
    )
    e2e_path = services['require_lexical_repository_path'](
        e2e_path, services['DEFAULT_RUNS'], "E2E record"
    )
    store_root = services['require_contained'](store_root, services['ROOT'] / ".local-e2e", "local store")
    catalog = services['load_catalog'](catalog_path)
    services['require_ordinary_promotion_catalog'](catalog, "legacy promotion", catalog_path)
    golden = services['load_json'](golden_path)
    before = services['validate_golden_document'](golden)
    if before["status"] != "valid":
        raise services['PipelineError']("cannot promote into an invalid golden manifest")
    (
        evidence,
        validated_e2e_sha,
        bound_records,
        package_path,
        package_record,
    ) = services['validate_e2e_evidence'](
        e2e_path, record_path, catalog_path, catalog
    )
    selected_binding = next(
        (
            binding
            for binding in bound_records.values()
            if binding[1].resolve() == record_path.resolve()
        ),
        None,
    )
    if selected_binding is None:
        raise services['PipelineError']("selected build record is not E2E-bound")
    record, record_path, _ = selected_binding
    core_id = record["core_id"]
    arch = record["architecture"]
    # The mutable record path is only a selector into the immutable E2E
    # evidence. Promotion policy must consume the exact record snapshot bound
    # by that E2E, never a separately loaded candidate at the same path.
    services['require_source_commits_eligible'](
        catalog,
        [(core_id, record.get("source"))],
    )
    services['require_active_core_golden'](golden, core_id)
    services['require_active_candidate_golden_path'](golden_path, golden)
    build_goldens = golden.get("build_goldens")
    if (
        not isinstance(build_goldens, dict)
        or set(build_goldens) - {core_id}
    ):
        raise services['PipelineError'](
            "active promotion golden may contain build evidence for only one core"
        )
    services['require_empty_golden_slot'](golden, core_id, arch)
    target_store: dict[str, dict[str, dict[str, str]]] = {
        name: {} for name in services['STORE_TARGET_EVIDENCE_NAMES']
    }
    artifact_path: Path | None = None
    metadata_path: Path | None = None
    for target, (target_record, target_record_path, expected_record_sha) in bound_records.items():
        target_artifact, target_metadata, target_log = services['validate_build_record_identity'](
            target_record, target_record_path, catalog_path, catalog
        )
        stored_record, stored_record_sha = services['store_file'](
            store_root, "build-records", target_record_path
        )
        stored_log, stored_log_sha = services['store_file'](store_root, "logs", target_log)
        stored_recipe, stored_recipe_sha = services['store_bytes'](
            store_root, "recipes", services['recipe_snapshot'](target_record)
        )
        if stored_record_sha != expected_record_sha:
            raise services['PipelineError'](f"stored {target} build record changed after E2E validation")
        if stored_log_sha != target_record["build"]["log_sha256"]:
            raise services['PipelineError'](f"stored {target} build log changed after E2E validation")
        target_store["build_records"][target] = {
            "path": str(stored_record.relative_to(services['ROOT'])),
            "sha256": stored_record_sha,
        }
        target_store["build_logs"][target] = {
            "path": str(stored_log.relative_to(services['ROOT'])),
            "sha256": stored_log_sha,
        }
        target_store["recipe_snapshots"][target] = {
            "path": str(stored_recipe.relative_to(services['ROOT'])),
            "sha256": stored_recipe_sha,
        }
        if target == arch:
            artifact_path = target_artifact
            metadata_path = target_metadata
    if artifact_path is None or metadata_path is None:
        raise services['PipelineError']("selected target evidence disappeared during promotion")
    artifact = record["artifact"]
    metadata = record["metadata"]
    recipe = record["recipe"]
    source = record["source"]
    toolchain = record["toolchain"]
    build = record["build"]
    stored_artifact, artifact_store_sha = services['store_file'](store_root, "artifacts", artifact_path)
    stored_metadata, metadata_store_sha = services['store_file'](store_root, "metadata", metadata_path)
    stored_e2e, e2e_store_sha = services['store_file'](store_root, "e2e", e2e_path)
    stored_package, package_store_sha = services['store_file'](store_root, "packages", package_path)
    if artifact_store_sha != artifact["sha256"]:
        raise services['PipelineError']("stored artifact digest differs from validated artifact digest")
    if metadata_store_sha != metadata["sha256"]:
        raise services['PipelineError']("stored metadata digest differs from its build record")
    if e2e_store_sha != validated_e2e_sha:
        raise services['PipelineError']("stored E2E record changed after validation")
    if package_store_sha != package_record["sha256"]:
        raise services['PipelineError']("stored E2E package changed after validation")
    promoted = {
        "core_id": core_id,
        "architecture": arch,
        "promotion_state": "build_golden",
        "promotion_reason": "initial-local-golden",
        "validation_scope": "static-build-only",
        "promoted_at": services['utc_now'](),
        "local_record": str(record_path.relative_to(services['ROOT'])),
        "source": source,
        "recipe": recipe,
        "toolchain": toolchain,
        "build": build,
        "artifact": artifact,
        "metadata": metadata,
        "e2e": {
            "run_id": evidence["run_id"],
            "record": str(e2e_path.relative_to(services['ROOT'])),
            "record_sha256": e2e_store_sha,
            "content_sha256": evidence["content_sha256"],
            "package": str(package_path.relative_to(services['ROOT'])),
            "package_sha256": package_store_sha,
            "build_records": {
                target: details["sha256"]
                for target, details in target_store["build_records"].items()
            },
        },
        "local_store": {
            "availability": "local-only",
            "artifact": {
                "path": str(stored_artifact.relative_to(services['ROOT'])),
                "sha256": artifact_store_sha,
            },
            "metadata": {
                "path": str(stored_metadata.relative_to(services['ROOT'])),
                "sha256": metadata_store_sha,
            },
            "e2e_record": {
                "path": str(stored_e2e.relative_to(services['ROOT'])),
                "sha256": e2e_store_sha,
            },
            "package": {
                "path": str(stored_package.relative_to(services['ROOT'])),
                "sha256": package_store_sha,
            },
            **target_store,
        },
    }
    if toolchain.get("archive_provenance") is not None:
        promoted["provenance_version"] = 2
    golden.setdefault("build_goldens", {}).setdefault(core_id, {})[arch] = promoted
    golden["content_sha256"] = services['golden_content_sha256'](golden)
    golden["updated_at"] = services['utc_now']()
    validation = services['validate_golden_document'](golden)
    if validation["status"] != "valid":
        raise services['PipelineError']("promotion would invalidate golden manifest:\n" + "\n".join(validation["errors"]))
    services['atomic_write_json'](golden_path, golden)
    return promoted


def _store_reference(path: Path, digest: str, *, services: ReleaseLifecycleServices) -> dict:
    return {"path": str(path.relative_to(services['ROOT'])), "sha256": digest}


def promote_tuned_variant(
    *,
    core_id: str,
    profile_id: str,
    source_golden_path: Path,
    selected_e2e_path: Path,
    reproduction_e2e_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    store_root: Path = DEFAULT_STORE,
    services: ReleaseLifecycleServices,
) -> dict:
    """Promote two independent tuned E2Es into one immutable golden and pin."""

    source_golden_path = services['require_lexical_repository_path'](
        source_golden_path, services['DEFAULT_NIGHTLIES'], "tuned source candidate golden"
    )
    selected_e2e_path = services['require_lexical_repository_path'](
        selected_e2e_path, services['DEFAULT_RUNS'], "selected tuning candidate E2E"
    )
    reproduction_e2e_path = services['require_lexical_repository_path'](
        reproduction_e2e_path, services['DEFAULT_RUNS'], "reproduction tuning candidate E2E"
    )
    store_root = services['require_contained'](store_root, services['ROOT'] / ".local-e2e", "local store")
    catalog = services['load_catalog'](catalog_path)
    services['require_ordinary_promotion_catalog'](catalog, "tuned promotion", catalog_path)
    selection = services['resolve_tuning_candidate_selection'](profile_id)
    if core_id not in catalog["cores"]:
        raise services['PipelineError'](f"tuned promotion core is not cataloged: {core_id}")
    source_golden = services['load_json'](source_golden_path)
    source_report = services['validate_golden_document'](source_golden)
    if source_report["status"] != "valid":
        raise services['PipelineError']("tuned source candidate golden is invalid")
    services['require_active_core_golden'](source_golden, core_id)
    services['require_active_candidate_golden_path'](source_golden_path, source_golden)
    if source_golden.get("build_goldens", {}).get(core_id) != {}:
        raise services['PipelineError']("tuned promotion requires an empty core candidate golden")

    selected = services['validate_tuned_e2e_evidence'](
        selected_e2e_path,
        catalog_path,
        catalog,
        expected_core=core_id,
        expected_selection=selection,
    )
    reproduction = services['validate_tuned_e2e_evidence'](
        reproduction_e2e_path,
        catalog_path,
        catalog,
        expected_core=core_id,
        expected_selection=selection,
    )
    outputs = services['require_tuned_candidate_equivalence'](selected, reproduction)
    services['require_source_commits_eligible'](
        catalog,
        [
            (core_id, selected["record"]["source"]),
            (core_id, reproduction["record"]["source"]),
        ],
    )

    def store_bundle(bundle: Mapping[str, object]) -> dict:
        record = bundle["record"]
        assert isinstance(record, services['Mapping'])
        stored_e2e, e2e_sha = services['store_file'](store_root, "e2e", bundle["e2e_path"])
        stored_record, record_sha = services['store_file'](
            store_root, "build-records", bundle["record_path"]
        )
        stored_log, log_sha = services['store_file'](store_root, "logs", bundle["log_path"])
        stored_recipe, recipe_sha = services['store_bytes'](
            store_root, "recipes", services['recipe_snapshot'](dict(record))
        )
        if (
            e2e_sha != bundle["e2e_file_sha256"]
            or record_sha != bundle["record_sha256"]
            or log_sha != record["build"]["log_sha256"]
        ):
            raise services['PipelineError']("tuning candidate changed during store admission")
        return {
            "run_id": bundle["e2e"]["run_id"],
            "content_sha256": bundle["e2e"]["content_sha256"],
            "e2e_record": services['_store_reference'](stored_e2e, e2e_sha),
            "build_record": services['_store_reference'](stored_record, record_sha),
            "build_log": services['_store_reference'](stored_log, log_sha),
            "recipe_snapshot": services['_store_reference'](stored_recipe, recipe_sha),
        }

    selected_store = store_bundle(selected)
    reproduction_store = store_bundle(reproduction)
    record = services['copy'].deepcopy(selected["record"])
    arch = selected["architecture"]
    stored_artifact, artifact_sha = services['store_file'](
        store_root, "artifacts", selected["artifact_path"]
    )
    stored_metadata, metadata_sha = services['store_file'](
        store_root, "metadata", selected["metadata_path"]
    )
    stored_package, package_sha = services['store_file'](
        store_root, "packages", selected["package_path"]
    )
    if (
        artifact_sha != record["artifact"]["sha256"]
        or metadata_sha != record["metadata"]["sha256"]
        or package_sha != selected["package_record"]["sha256"]
    ):
        raise services['PipelineError']("tuning candidate outputs changed during store admission")
    reproduction_proof = {
        "schema_version": 1,
        "validation_scope": services['TUNED_REPRODUCTION_SCOPE'],
        "selected": selected_store,
        "reproduction": reproduction_store,
        "equivalent_outputs": outputs,
    }
    selected_hardened = services['runner_evidence_is_hardened'](
        selected["e2e"].get("runner")
    )
    reproduction_hardened = services['runner_evidence_is_hardened'](
        reproduction["e2e"].get("runner")
    )
    if selected_hardened != reproduction_hardened:
        raise services['PipelineError'](
            "tuned promotion cannot mix hardened and legacy host evidence"
        )
    host_reproduction = None
    if selected_hardened:
        selected_host_bundle = {
            "e2e": selected["e2e"],
            "e2e_path": selected["e2e_path"],
            "targets": {
                arch: {
                    "record": selected["record"],
                    "record_path": selected["record_path"],
                    "log_path": selected["log_path"],
                }
            },
            "package_record": selected["package_record"],
        }
        reproduction_host_bundle = {
            "e2e": reproduction["e2e"],
            "e2e_path": reproduction["e2e_path"],
            "targets": {
                arch: {
                    "record": reproduction["record"],
                    "record_path": reproduction["record_path"],
                    "log_path": reproduction["log_path"],
                }
            },
            "package_record": reproduction["package_record"],
        }
        host_reproduction = services['create_host_reproduction_proof'](
            selected_host_bundle,
            reproduction_host_bundle,
            selected_e2e_record=selected_store["e2e_record"],
            reproduction_e2e_record=reproduction_store["e2e_record"],
        )
    target_store = {
        "build_records": {arch: selected_store["build_record"]},
        "build_logs": {arch: selected_store["build_log"]},
        "recipe_snapshots": {arch: selected_store["recipe_snapshot"]},
    }
    promoted_at = services['utc_now']()
    promoted = {
        "core_id": core_id,
        "architecture": arch,
        "promotion_state": "build_golden",
        "promotion_reason": "dual-independent-tuned-reproduction",
        "validation_scope": "static-build-only",
        "promoted_at": promoted_at,
        "local_record": str(selected["record_path"].relative_to(services['ROOT'])),
        "source": services['copy'].deepcopy(record["source"]),
        "recipe": services['copy'].deepcopy(record["recipe"]),
        "toolchain": services['copy'].deepcopy(record["toolchain"]),
        "build": services['copy'].deepcopy(record["build"]),
        "artifact": services['copy'].deepcopy(record["artifact"]),
        "metadata": services['copy'].deepcopy(record["metadata"]),
        "tuning_candidate": services['copy'].deepcopy(selection),
        "reproduction": reproduction_proof,
        "e2e": {
            "run_id": selected["e2e"]["run_id"],
            "record": str(selected_e2e_path.relative_to(services['ROOT'])),
            "record_sha256": selected_store["e2e_record"]["sha256"],
            "content_sha256": selected["e2e"]["content_sha256"],
            "package": str(selected["package_path"].relative_to(services['ROOT'])),
            "package_sha256": package_sha,
            "build_records": {arch: selected_store["build_record"]["sha256"]},
        },
        "local_store": {
            "availability": "local-only",
            "artifact": services['_store_reference'](stored_artifact, artifact_sha),
            "metadata": services['_store_reference'](stored_metadata, metadata_sha),
            "e2e_record": selected_store["e2e_record"],
            "package": services['_store_reference'](stored_package, package_sha),
            **target_store,
        },
    }
    if record["toolchain"].get("archive_provenance") is not None:
        promoted["provenance_version"] = 2
    if host_reproduction is not None:
        promoted["host_reproduction"] = services['copy'].deepcopy(host_reproduction)
        services['validated_host_reproduction_shape'](
            host_reproduction,
            core_id=core_id,
            golden_records={arch: promoted},
        )
    working = services['one_core_golden_document'](
        core_id=core_id,
        pin_id=source_golden["pin_id"],
        created_at=source_golden["created_at"],
        updated_at=promoted_at,
        baseline=source_golden["baseline"],
        core_record=source_golden["cores"][core_id],
        build_goldens={arch: promoted},
    )
    working["content_sha256"] = services['golden_content_sha256'](working)
    working_report = services['validate_golden_document'](working)
    if working_report["status"] != "valid":
        raise services['PipelineError'](
            "tuned promotion would create an invalid golden:\n- "
            + "\n- ".join(working_report["errors"])
        )
    working_store_errors = services['verify_local_store'](working)
    if working_store_errors:
        raise services['PipelineError'](
            "tuned promotion store proof is invalid:\n- "
            + "\n- ".join(working_store_errors)
        )
    bundle = services['complete_core_bundle'](working, core_id)
    if bundle is None:
        raise services['PipelineError']("tuned promotion did not produce a complete one-ABI bundle")
    semantic_id = services['individual_core_semantic_id'](core_id, bundle)
    golden_path, pin_path = services['immutable_promotion_output_paths'](
        semantic_id,
        label="tuned",
    )
    if golden_path.exists() or golden_path.is_symlink() or pin_path.exists() or pin_path.is_symlink():
        raise services['PipelineError']("refusing to replace an existing tuned golden or pin")
    working["pin_id"] = semantic_id
    working["content_sha256"] = services['golden_content_sha256'](working)
    with services['manifest_lock'](golden_path):
        services['atomic_create_json'](golden_path, working)
    try:
        pin = services['compose_pin_set'](
            pin_id=semantic_id,
            core_ids=[core_id],
            source_paths=[golden_path],
            output_path=pin_path,
            catalog_path=catalog_path,
        )
    except Exception:
        # The golden is immutable, valid evidence and deliberately retained;
        # a subsequent retry can diagnose the pin-side collision explicitly.
        raise
    services['require_individual_pin_identity'](pin, pin_path=pin_path)
    result = {
        "status": "created",
        "core_id": core_id,
        "architecture": arch,
        "profile_id": profile_id,
        "semantic_id": semantic_id,
        "golden": str(golden_path.relative_to(services['ROOT'])),
        "pin": str(pin_path.relative_to(services['ROOT'])),
        "selection_sha256": bundle["selection_sha256"],
        "pin_content_sha256": pin["content_sha256"],
    }
    if host_reproduction is not None:
        result["host_reproduction_content_sha256"] = host_reproduction[
            "content_sha256"
        ]
    return result


def promote_source_candidate(
    *,
    core_id: str,
    source_golden_path: Path,
    selected_e2e_path: Path,
    reproduction_e2e_path: Path,
    catalog_path: Path,
    store_root: Path = DEFAULT_STORE,
    services: ReleaseLifecycleServices,
) -> dict:
    """Create an immutable golden/pin from two untuned candidate E2Es."""

    source_golden_path = services['require_lexical_repository_path'](
        source_golden_path,
        services['DEFAULT_NIGHTLIES'],
        "source-candidate starting golden",
    )
    selected_e2e_path = services['require_lexical_repository_path'](
        selected_e2e_path,
        services['DEFAULT_RUNS'],
        "selected source-candidate E2E",
    )
    reproduction_e2e_path = services['require_lexical_repository_path'](
        reproduction_e2e_path,
        services['DEFAULT_RUNS'],
        "reproduction source-candidate E2E",
    )
    store_root = services['require_contained'](store_root, services['ROOT'] / ".local-e2e", "local store")
    catalog, catalog_file_sha256 = services['load_catalog_with_sha256'](catalog_path)
    if "source_candidate" not in catalog:
        raise services['PipelineError'](
            "source-candidate promotion requires an authenticated generated catalog"
        )
    source_candidate = services['validated_embedded_source_candidate_shape'](
        catalog["source_candidate"],
        core_id=core_id,
    )
    if set(catalog.get("cores", {})) != {core_id}:
        raise services['PipelineError']("source-candidate promotion catalog scope is invalid")

    source_golden = services['load_json'](source_golden_path)
    source_report = services['validate_golden_document'](source_golden)
    if source_report["status"] != "valid":
        raise services['PipelineError'](
            "source-candidate starting golden is invalid:\n- "
            + "\n- ".join(source_report["errors"])
        )
    services['require_active_core_golden'](source_golden, core_id)
    services['require_active_candidate_golden_path'](source_golden_path, source_golden)
    if source_golden.get("build_goldens", {}).get(core_id) != {}:
        raise services['PipelineError'](
            "source-candidate promotion requires an empty core candidate golden"
        )

    selected = services['validate_source_candidate_e2e_evidence'](
        selected_e2e_path,
        catalog_path,
        catalog,
        expected_core=core_id,
        catalog_file_sha256=catalog_file_sha256,
    )
    reproduction = services['validate_source_candidate_e2e_evidence'](
        reproduction_e2e_path,
        catalog_path,
        catalog,
        expected_core=core_id,
        catalog_file_sha256=catalog_file_sha256,
    )
    equivalent_outputs = services['require_source_candidate_equivalence'](
        selected,
        reproduction,
    )
    services['require_source_commits_eligible'](
        catalog,
        [
            (core_id, target["record"]["source"])
            for bundle in (selected, reproduction)
            for target in bundle["targets"].values()
        ],
    )

    def store_e2e_bundle(bundle: Mapping[str, object]) -> dict:
        stored_e2e, e2e_sha = services['store_file'](
            store_root,
            "e2e",
            bundle["e2e_path"],
        )
        if e2e_sha != bundle["e2e_file_sha256"]:
            raise services['PipelineError']("source-candidate E2E changed during store admission")
        side = {
            "run_id": bundle["e2e"]["run_id"],
            "content_sha256": bundle["e2e"]["content_sha256"],
            "e2e_record": services['_store_reference'](stored_e2e, e2e_sha),
            "build_records": {},
            "build_logs": {},
            "recipe_snapshots": {},
        }
        for arch, target in sorted(bundle["targets"].items()):
            record = target["record"]
            stored_record, record_sha = services['store_file'](
                store_root,
                "build-records",
                target["record_path"],
            )
            stored_log, log_sha = services['store_file'](
                store_root,
                "logs",
                target["log_path"],
            )
            stored_recipe, recipe_sha = services['store_bytes'](
                store_root,
                "recipes",
                services['recipe_snapshot'](record),
            )
            if (
                record_sha != target["record_sha256"]
                or log_sha != record["build"]["log_sha256"]
            ):
                raise services['PipelineError'](
                    "source-candidate target changed during store admission"
                )
            side["build_records"][arch] = services['_store_reference'](
                stored_record,
                record_sha,
            )
            side["build_logs"][arch] = services['_store_reference'](stored_log, log_sha)
            side["recipe_snapshots"][arch] = services['_store_reference'](
                stored_recipe,
                recipe_sha,
            )
        return side

    selected_store = store_e2e_bundle(selected)
    reproduction_store = store_e2e_bundle(reproduction)
    selected_hardened = services['runner_evidence_is_hardened'](
        selected["e2e"].get("runner")
    )
    reproduction_hardened = services['runner_evidence_is_hardened'](
        reproduction["e2e"].get("runner")
    )
    if selected_hardened != reproduction_hardened:
        raise services['PipelineError'](
            "source-candidate promotion cannot mix hardened and legacy host evidence"
        )
    host_reproduction = None
    if selected_hardened:
        host_reproduction = services['create_host_reproduction_proof'](
            selected,
            reproduction,
            selected_e2e_record=selected_store["e2e_record"],
            reproduction_e2e_record=reproduction_store["e2e_record"],
        )
    first_arch = sorted(selected["targets"])[0]
    first_target = selected["targets"][first_arch]
    stored_metadata, metadata_sha = services['store_file'](
        store_root,
        "metadata",
        first_target["metadata_path"],
    )
    stored_package, package_sha = services['store_file'](
        store_root,
        "packages",
        selected["package_path"],
    )
    if (
        metadata_sha != equivalent_outputs["metadata"]["sha256"]
        or package_sha != equivalent_outputs["package"]["sha256"]
    ):
        raise services['PipelineError']("source-candidate outputs changed during store admission")
    artifact_store: dict[str, dict] = {}
    for arch, target in sorted(selected["targets"].items()):
        stored_artifact, artifact_sha = services['store_file'](
            store_root,
            "artifacts",
            target["artifact_path"],
        )
        if artifact_sha != equivalent_outputs["artifacts"][arch]["sha256"]:
            raise services['PipelineError'](
                "source-candidate artifact changed during store admission"
            )
        artifact_store[arch] = services['_store_reference'](stored_artifact, artifact_sha)

    output_reproduction = {
        "schema_version": 1,
        "validation_scope": services['SOURCE_CANDIDATE_REPRODUCTION_SCOPE'],
        "selected": selected_store,
        "reproduction": reproduction_store,
        "equivalent_outputs": equivalent_outputs,
    }
    promoted_at = services['utc_now']()
    build_records_sha = {
        arch: reference["sha256"]
        for arch, reference in selected_store["build_records"].items()
    }
    promoted_records: dict[str, dict] = {}
    for arch, target in sorted(selected["targets"].items()):
        record = target["record"]
        promoted = {
            "core_id": core_id,
            "architecture": arch,
            "promotion_state": "build_golden",
            "promotion_reason": "dual-independent-source-candidate-reproduction",
            "validation_scope": "static-build-only",
            "promoted_at": promoted_at,
            "local_record": str(target["record_path"].relative_to(services['ROOT'])),
            "source": services['copy'].deepcopy(record["source"]),
            "recipe": services['copy'].deepcopy(record["recipe"]),
            "toolchain": services['copy'].deepcopy(record["toolchain"]),
            "build": services['copy'].deepcopy(record["build"]),
            "artifact": services['copy'].deepcopy(record["artifact"]),
            "metadata": services['copy'].deepcopy(record["metadata"]),
            "source_candidate": services['copy'].deepcopy(source_candidate),
            "output_reproduction": services['copy'].deepcopy(output_reproduction),
            "e2e": {
                "run_id": selected["e2e"]["run_id"],
                "record": str(selected_e2e_path.relative_to(services['ROOT'])),
                "record_sha256": selected_store["e2e_record"]["sha256"],
                "content_sha256": selected["e2e"]["content_sha256"],
                "package": str(selected["package_path"].relative_to(services['ROOT'])),
                "package_sha256": package_sha,
                "build_records": services['copy'].deepcopy(build_records_sha),
            },
            "local_store": {
                "availability": "local-only",
                "artifact": services['copy'].deepcopy(artifact_store[arch]),
                "metadata": services['_store_reference'](stored_metadata, metadata_sha),
                "e2e_record": services['copy'].deepcopy(selected_store["e2e_record"]),
                "package": services['_store_reference'](stored_package, package_sha),
                "build_records": services['copy'].deepcopy(selected_store["build_records"]),
                "build_logs": services['copy'].deepcopy(selected_store["build_logs"]),
                "recipe_snapshots": services['copy'].deepcopy(
                    selected_store["recipe_snapshots"]
                ),
            },
        }
        if record["toolchain"].get("archive_provenance") is not None:
            promoted["provenance_version"] = 2
        if host_reproduction is not None:
            promoted["host_reproduction"] = services['copy'].deepcopy(host_reproduction)
        promoted_records[arch] = promoted

    services['validated_output_reproduction_shape'](
        output_reproduction,
        core_id=core_id,
        golden_records=promoted_records,
    )
    if host_reproduction is not None:
        services['validated_host_reproduction_shape'](
            host_reproduction,
            core_id=core_id,
            golden_records=promoted_records,
        )
    working = services['one_core_golden_document'](
        core_id=core_id,
        pin_id=source_golden["pin_id"],
        created_at=source_golden["created_at"],
        updated_at=promoted_at,
        baseline=source_golden["baseline"],
        core_record=source_golden["cores"][core_id],
        build_goldens=promoted_records,
    )
    working["content_sha256"] = services['golden_content_sha256'](working)
    working_report = services['validate_golden_document'](working)
    if working_report["status"] != "valid":
        raise services['PipelineError'](
            "source-candidate promotion would create an invalid golden:\n- "
            + "\n- ".join(working_report["errors"])
        )
    store_errors = services['verify_local_store'](working)
    if store_errors:
        raise services['PipelineError'](
            "source-candidate promotion store proof is invalid:\n- "
            + "\n- ".join(store_errors)
        )
    bundle = services['complete_core_bundle'](working, core_id)
    if bundle is None:
        raise services['PipelineError']("source-candidate promotion bundle is incomplete")
    semantic_id = services['individual_core_semantic_id'](core_id, bundle)
    golden_path, pin_path = services['immutable_promotion_output_paths'](
        semantic_id,
        label="source-candidate",
    )
    if (
        golden_path.exists()
        or golden_path.is_symlink()
        or pin_path.exists()
        or pin_path.is_symlink()
    ):
        raise services['PipelineError'](
            "refusing to replace an existing source-candidate golden or pin"
        )
    working["pin_id"] = semantic_id
    working["content_sha256"] = services['golden_content_sha256'](working)
    with services['manifest_lock'](golden_path):
        services['atomic_create_json'](golden_path, working)
    pin = services['compose_pin_set'](
        pin_id=semantic_id,
        core_ids=[core_id],
        source_paths=[golden_path],
        output_path=pin_path,
        catalog_path=catalog_path,
    )
    services['require_individual_pin_identity'](pin, pin_path=pin_path)
    result = {
        "status": "created",
        "core_id": core_id,
        "architectures": sorted(promoted_records),
        "candidate_id": source_candidate["candidate_id"],
        "semantic_id": semantic_id,
        "golden": str(golden_path.relative_to(services['ROOT'])),
        "pin": str(pin_path.relative_to(services['ROOT'])),
        "selection_sha256": bundle["selection_sha256"],
        "pin_content_sha256": pin["content_sha256"],
    }
    if host_reproduction is not None:
        result["host_reproduction_content_sha256"] = host_reproduction[
            "content_sha256"
        ]
    return result


def promote_host_reproduction(
    *,
    core_id: str,
    source_golden_path: Path,
    selected_e2e_path: Path,
    reproduction_e2e_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    store_root: Path = DEFAULT_STORE,
    services: ReleaseLifecycleServices,
) -> dict:
    """Create one immutable proof-bearing golden/pin from two hardened runs."""

    source_golden_path = services['require_lexical_repository_path'](
        source_golden_path,
        services['DEFAULT_NIGHTLIES'],
        "host-reproduction starting golden",
    )
    selected_e2e_path = services['require_lexical_repository_path'](
        selected_e2e_path,
        services['DEFAULT_RUNS'],
        "host-reproduction selected E2E",
    )
    reproduction_e2e_path = services['require_lexical_repository_path'](
        reproduction_e2e_path,
        services['DEFAULT_RUNS'],
        "host-reproduction reproduction E2E",
    )
    store_root = services['require_contained'](store_root, services['ROOT'] / ".local-e2e", "local store")
    catalog, catalog_file_sha256 = services['load_catalog_with_sha256'](catalog_path)
    services['require_ordinary_promotion_catalog'](
        catalog, "host-reproduction promotion", catalog_path
    )
    if core_id not in catalog.get("cores", {}):
        raise services['PipelineError'](f"host-reproduction core is not cataloged: {core_id}")
    source_golden = services['load_json'](source_golden_path)
    source_report = services['validate_golden_document'](source_golden)
    if source_report["status"] != "valid":
        raise services['PipelineError']("host-reproduction starting golden is invalid")
    services['require_active_core_golden'](source_golden, core_id)
    services['require_active_candidate_golden_path'](source_golden_path, source_golden)
    if source_golden.get("build_goldens", {}).get(core_id) != {}:
        raise services['PipelineError'](
            "host-reproduction promotion requires an empty core candidate golden"
        )

    selected = services['validate_host_reproduction_e2e_evidence'](
        selected_e2e_path,
        catalog_path,
        catalog,
        expected_core=core_id,
        catalog_file_sha256=catalog_file_sha256,
    )
    reproduction = services['validate_host_reproduction_e2e_evidence'](
        reproduction_e2e_path,
        catalog_path,
        catalog,
        expected_core=core_id,
        catalog_file_sha256=catalog_file_sha256,
    )
    equivalent_builds, equivalent_outputs = (
        services['require_host_reproduction_equivalence'](selected, reproduction)
    )
    services['require_source_commits_eligible'](
        catalog,
        [
            (core_id, target["record"]["source"])
            for bundle in (selected, reproduction)
            for target in bundle["targets"].values()
        ],
    )

    stored_selected_e2e, selected_e2e_sha256 = services['store_file'](
        store_root, "e2e", selected["e2e_path"]
    )
    stored_reproduction_e2e, reproduction_e2e_sha256 = services['store_file'](
        store_root, "e2e", reproduction["e2e_path"]
    )
    if (
        selected_e2e_sha256 != selected["e2e_file_sha256"]
        or reproduction_e2e_sha256 != reproduction["e2e_file_sha256"]
    ):
        raise services['PipelineError']("host-reproduction E2E changed during store admission")
    selected_side = {
        "run_id": selected["e2e"]["run_id"],
        "content_sha256": selected["e2e"]["content_sha256"],
        "e2e_record": services['_store_reference'](
            stored_selected_e2e, selected_e2e_sha256
        ),
    }
    reproduction_side = {
        "run_id": reproduction["e2e"]["run_id"],
        "content_sha256": reproduction["e2e"]["content_sha256"],
        "e2e_record": services['_store_reference'](
            stored_reproduction_e2e, reproduction_e2e_sha256
        ),
    }
    host_reproduction = {
        "schema_version": 1,
        "validation_scope": services['HOST_REPRODUCTION_SCOPE'],
        "selected": selected_side,
        "reproduction": reproduction_side,
        "equivalent_builds": equivalent_builds,
        "equivalent_outputs": equivalent_outputs,
    }
    host_reproduction["content_sha256"] = (
        services['host_reproduction_content_sha256'](host_reproduction)
    )

    target_store: dict[str, dict[str, dict[str, str]]] = {
        name: {} for name in services['STORE_TARGET_EVIDENCE_NAMES']
    }
    artifact_store: dict[str, dict] = {}
    for arch, target in sorted(selected["targets"].items()):
        record = target["record"]
        stored_record, record_sha256 = services['store_file'](
            store_root, "build-records", target["record_path"]
        )
        stored_log, log_sha256 = services['store_file'](
            store_root, "logs", target["log_path"]
        )
        stored_recipe, recipe_sha256 = services['store_bytes'](
            store_root, "recipes", services['recipe_snapshot'](record)
        )
        stored_artifact, artifact_sha256 = services['store_file'](
            store_root, "artifacts", target["artifact_path"]
        )
        if (
            record_sha256 != target["record_sha256"]
            or log_sha256 != record["build"]["log_sha256"]
            or artifact_sha256 != record["artifact"]["sha256"]
        ):
            raise services['PipelineError'](
                f"host-reproduction {arch} evidence changed during store admission"
            )
        target_store["build_records"][arch] = services['_store_reference'](
            stored_record, record_sha256
        )
        target_store["build_logs"][arch] = services['_store_reference'](
            stored_log, log_sha256
        )
        target_store["recipe_snapshots"][arch] = services['_store_reference'](
            stored_recipe, recipe_sha256
        )
        artifact_store[arch] = services['_store_reference'](
            stored_artifact, artifact_sha256
        )
    first_arch = sorted(selected["targets"])[0]
    first_target = selected["targets"][first_arch]
    stored_metadata, metadata_sha256 = services['store_file'](
        store_root, "metadata", first_target["metadata_path"]
    )
    stored_package, package_sha256 = services['store_file'](
        store_root, "packages", selected["package_path"]
    )
    if (
        metadata_sha256 != equivalent_outputs["metadata"]["sha256"]
        or package_sha256 != equivalent_outputs["package"]["sha256"]
    ):
        raise services['PipelineError'](
            "host-reproduction outputs changed during store admission"
        )

    promoted_at = services['utc_now']()
    build_records_sha256 = {
        arch: reference["sha256"]
        for arch, reference in target_store["build_records"].items()
    }
    promoted_records: dict[str, dict] = {}
    for arch, target in sorted(selected["targets"].items()):
        record = target["record"]
        promoted = {
            "core_id": core_id,
            "architecture": arch,
            "promotion_state": "build_golden",
            "promotion_reason": "dual-hardened-host-reproduction",
            "validation_scope": "static-build-only",
            "promoted_at": promoted_at,
            "local_record": str(target["record_path"].relative_to(services['ROOT'])),
            "source": services['copy'].deepcopy(record["source"]),
            "recipe": services['copy'].deepcopy(record["recipe"]),
            "toolchain": services['copy'].deepcopy(record["toolchain"]),
            "build": services['copy'].deepcopy(record["build"]),
            "artifact": services['copy'].deepcopy(record["artifact"]),
            "metadata": services['copy'].deepcopy(record["metadata"]),
            "host_reproduction": services['copy'].deepcopy(host_reproduction),
            "e2e": {
                "run_id": selected["e2e"]["run_id"],
                "record": str(selected_e2e_path.relative_to(services['ROOT'])),
                "record_sha256": selected_e2e_sha256,
                "content_sha256": selected["e2e"]["content_sha256"],
                "package": str(selected["package_path"].relative_to(services['ROOT'])),
                "package_sha256": package_sha256,
                "build_records": services['copy'].deepcopy(build_records_sha256),
            },
            "local_store": {
                "availability": "local-only",
                "artifact": services['copy'].deepcopy(artifact_store[arch]),
                "metadata": services['_store_reference'](
                    stored_metadata, metadata_sha256
                ),
                "e2e_record": services['copy'].deepcopy(selected_side["e2e_record"]),
                "package": services['_store_reference'](stored_package, package_sha256),
                "build_records": services['copy'].deepcopy(target_store["build_records"]),
                "build_logs": services['copy'].deepcopy(target_store["build_logs"]),
                "recipe_snapshots": services['copy'].deepcopy(
                    target_store["recipe_snapshots"]
                ),
            },
        }
        if record["toolchain"].get("archive_provenance") is not None:
            promoted["provenance_version"] = 2
        promoted_records[arch] = promoted
    services['validated_host_reproduction_shape'](
        host_reproduction,
        core_id=core_id,
        golden_records=promoted_records,
    )
    working = services['one_core_golden_document'](
        core_id=core_id,
        pin_id=source_golden["pin_id"],
        created_at=source_golden["created_at"],
        updated_at=promoted_at,
        baseline=source_golden["baseline"],
        core_record=source_golden["cores"][core_id],
        build_goldens=promoted_records,
    )
    working["content_sha256"] = services['golden_content_sha256'](working)
    working_report = services['validate_golden_document'](working)
    if working_report["status"] != "valid":
        raise services['PipelineError'](
            "host-reproduction promotion would create an invalid golden:\n- "
            + "\n- ".join(working_report["errors"])
        )
    store_errors = services['verify_local_store'](working)
    if store_errors:
        raise services['PipelineError'](
            "host-reproduction store proof is invalid:\n- "
            + "\n- ".join(store_errors)
        )
    bundle = services['complete_core_bundle'](working, core_id)
    if bundle is None:
        raise services['PipelineError']("host-reproduction bundle is incomplete")
    semantic_id = services['individual_core_semantic_id'](core_id, bundle)
    golden_path, pin_path = services['immutable_promotion_output_paths'](
        semantic_id, label="host-reproduction"
    )
    if (
        golden_path.exists()
        or golden_path.is_symlink()
        or pin_path.exists()
        or pin_path.is_symlink()
    ):
        raise services['PipelineError'](
            "refusing to replace an existing host-reproduction golden or pin"
        )
    working["pin_id"] = semantic_id
    working["content_sha256"] = services['golden_content_sha256'](working)
    with services['manifest_lock'](golden_path):
        services['atomic_create_json'](golden_path, working)
    pin = services['compose_pin_set'](
        pin_id=semantic_id,
        core_ids=[core_id],
        source_paths=[golden_path],
        output_path=pin_path,
        catalog_path=catalog_path,
    )
    services['require_individual_pin_identity'](pin, pin_path=pin_path)
    return {
        "status": "created",
        "core_id": core_id,
        "architectures": sorted(promoted_records),
        "semantic_id": semantic_id,
        "golden": str(golden_path.relative_to(services['ROOT'])),
        "pin": str(pin_path.relative_to(services['ROOT'])),
        "host_reproduction_content_sha256": host_reproduction[
            "content_sha256"
        ],
        "selection_sha256": bundle["selection_sha256"],
        "pin_content_sha256": pin["content_sha256"],
    }


def add_zip_entry(archive: zipfile.ZipFile, name: str, data: bytes, *, services: ReleaseLifecycleServices) -> None:
    entry = services['zipfile'].ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = services['zipfile'].ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, data)


def package_e2e_core(
    run_root: Path,
    core_id: str,
    records: list[dict],
    spec: dict,
    group_selection: dict | None = None,
    tuning_selection: dict | None = None,
    *,
    services: ReleaseLifecycleServices,
) -> dict:
    if group_selection is not None and tuning_selection is not None:
        raise services['PipelineError']("group and tuning-candidate packages are mutually exclusive")
    candidate_selection = (
        services['validated_tuning_candidate_selection'](tuning_selection)
        if tuning_selection is not None
        else None
    )
    expected_targets = set(
        group_selection["selected_architectures"]
        if group_selection is not None
        else [candidate_selection["profile"]["architecture"]]
        if candidate_selection is not None
        else spec["targets"]
    )
    actual_targets = {record["architecture"] for record in records}
    if actual_targets != expected_targets:
        return {
            "core_id": core_id,
            "result": "not_packaged",
            "reason": "E2E target set is incomplete",
        }
    if not records or any(record["result"] != "passed" for record in records):
        return {"core_id": core_id, "result": "not_packaged", "reason": "target build failed"}
    metadata_records = [record.get("metadata", {}) for record in records]
    metadata_hashes = {item.get("sha256") for item in metadata_records}
    if (
        any(item.get("status") != "valid" for item in metadata_records)
        or len(metadata_hashes) != 1
    ):
        return {
            "core_id": core_id,
            "result": "not_packaged",
            "reason": "target metadata is missing or inconsistent",
        }
    metadata_replacement = services['validated_metadata_replacement'](spec)
    if metadata_replacement is not None and any(
        not services['metadata_matches_replacement'](metadata, metadata_replacement)
        for metadata in metadata_records
    ):
        return {
            "core_id": core_id,
            "result": "not_packaged",
            "reason": "target metadata does not match the catalog replacement",
        }
    package_path = run_root / f"{core_id}_libretro.zip"
    manifest = {
        "schema_version": 1,
        "local_only": True,
        "publication": "disabled",
        "core_id": core_id,
        "artifacts": {},
    }
    if candidate_selection is not None:
        manifest["tuning_candidate"] = services['copy'].deepcopy(candidate_selection)
    with services['zipfile'].ZipFile(package_path, "w") as archive:
        for record in sorted(records, key=lambda item: item["architecture"]):
            arch = record["architecture"]
            source_path = run_root / core_id / arch / record["artifact"]["path"]
            member = f"{services['ARCH_LAYOUT'][arch]['package_directory']}/{source_path.name}"
            services['add_zip_entry'](archive, member, source_path.read_bytes())
            manifest["artifacts"][arch] = {
                "path": member,
                "sha256": record["artifact"]["sha256"],
                "source_commit": record["source"]["resolved_commit"],
                "toolchain_image_id": record["toolchain"]["resolved_image_id"],
            }
        metadata = metadata_records[0]
        metadata_path = run_root / core_id / records[0]["architecture"] / metadata["path"]
        metadata_name = spec["metadata"]["artifact_name"]
        services['add_zip_entry'](archive, metadata_name, metadata_path.read_bytes())
        manifest["metadata"] = {
            "path": metadata_name,
            "sha256": metadata["sha256"],
        }
        services['add_zip_entry'](
            archive,
            "manifest.json",
            (services['json'].dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
    package_record = {
        "core_id": core_id,
        "result": "packaged",
        "path": package_path.name,
        "sha256": services['sha256_file'](package_path),
        "size": package_path.stat().st_size,
    }
    if group_selection is not None:
        expected_package = group_selection["expected_outputs"]["package"]
        package_record["core_group"] = {
            "variant_id": group_selection["variant_id"],
            "comparison": expected_package["comparison"],
        }
        if expected_package["comparison"] == "exact" and (
            package_record["path"] != expected_package["name"]
            or package_record["sha256"] != expected_package["sha256"]
            or package_record["size"] != expected_package["size"]
        ):
            return {
                **package_record,
                "result": "not_packaged",
                "reason": "package does not match the selected core group pin",
            }
    if candidate_selection is not None:
        package_record["tuning_candidate"] = services['copy'].deepcopy(candidate_selection)
    return package_record

