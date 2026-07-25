#!/usr/bin/env python3
"""Compose the hand-authored tail of a canonical core promotion.

The pipeline provides commands for the build/promote chain (import-golden,
promote, derive-core-id, compose-core-golden, compose-pin-set); this tool owns
the lifecycle tail. The source lock and source-set are composed in memory
(records.source is the single composer; they are never written as files), and
the one remaining written lifecycle artifact is the compatibility manifest
(manifests/compatibility/<core>.json), fully determined by evidence that
already exists after the pin is composed. The device-eligibility caveat (the
ABI-ceiling reasoning) is derived from the captured version_requirements
rather than retyped per core.

Full promotion sequence (this tool is the last step):

  build-core --runner-profile github-actions-sim --core C --run-id SEL
  build-core --runner-profile local            --core C --run-id REP
  import-golden --core C --spruceos ../spruceOS --output NIGHTLY_CANDIDATE
  promote (arm64) ; promote (armhf) into the candidate
  derive-core-id --core C --source-golden CANDIDATE
  compose-core-golden ; compose-pin-set
  promote_core.py compose-lifecycle --core C --semantic-id SID \\
      --selected-run SEL --reproduction-run REP [--caveat "..."]

Local, read-only over inputs, create-only over outputs; never publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from core_pipeline_lib.errors import PipelineError  # noqa: E402
from core_pipeline_lib.records import source as records_source  # noqa: E402

# Captured device provider ceilings (device-runtime-contracts.json). Used only
# to phrase the device-eligibility caveat; the machine-readable screen lives in
# device_sets.py.
MINI_GLIBCXX_CEILING = (3, 4, 24)
A30_GLIBCXX_CEILING = (3, 4, 32)
ELF_LABEL = {"arm64": "ELF64/AArch64", "armhf": "ELF32/ARM hard-float"}


class PromoteCoreError(Exception):
    """Raised for missing or inconsistent promotion inputs."""


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromoteCoreError(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PromoteCoreError(f"invalid JSON in {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_sha256(document: dict[str, Any]) -> str:
    material = {k: v for k, v in document.items() if k not in {"$schema", "content_sha256"}}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    return tuple(int(p) for p in parts) if all(p.isdecimal() for p in parts) else ()


def max_glibcxx(version_requirements: list[str]) -> tuple[str | None, tuple[int, ...]]:
    best_value, best_key = None, ()
    for symbol in version_requirements:
        if symbol.startswith("GLIBCXX_"):
            key = _version_tuple(symbol[len("GLIBCXX_") :])
            if key and key >= best_key:
                best_key, best_value = key, symbol[len("GLIBCXX_") :]
    return best_value, best_key


def compose_source_set(semantic_id: str) -> dict[str, Any]:
    """Compose the source-set (records.source is the single composer)."""

    try:
        return records_source.compose_source_set(
            semantic_id, repository_root=ROOT
        )
    except PipelineError as exc:
        raise PromoteCoreError(str(exc)) from exc


def compose_source_lock(core_id: str) -> dict[str, Any]:
    """Compose a core's source lock (records.source is the single composer)."""

    try:
        return records_source.compose_source_lock(core_id, repository_root=ROOT)
    except PipelineError as exc:
        raise PromoteCoreError(str(exc)) from exc


def _device_caveat(targets: dict[str, Any]) -> str:
    armhf = targets.get("armhf", {})
    value, key = max_glibcxx(armhf.get("version_requirements", []))
    if value is None:
        return (
            "The armhf artifact has no libstdc++ dependency, so it clears every "
            "captured provider ceiling; ARM64 is bound to ra64-universal-v1 and "
            "ARMHF to ra32-a30-v1. Provider inspection and target-runtime capture "
            "are absent, so every device view remains provisional and ineligible "
            "pending a runtime smoke result."
        )
    if key > MINI_GLIBCXX_CEILING:
        eligibility = (
            f"ARMHF requires GLIBCXX_{value}, above the observed non-enforcing "
            "Miyoo Mini fallback provider value GLIBCXX_3.4.24, so the Mini "
            "profile is ineligible; A30 is the eligible 32-bit consumer at the "
            "ABI screen."
        )
    else:
        eligibility = (
            f"ARMHF's maximum GLIBCXX_{value} is within the observed Miyoo Mini "
            "fallback provider ceiling GLIBCXX_3.4.24, so both the Mini and A30 "
            "profiles clear the ABI screen."
        )
    return (
        "This is static build/package evidence only. ARM64 is build-identity-"
        f"bound to ra64-universal-v1 and ARMHF to ra32-a30-v1. {eligibility} "
        "Provider inspection and target-runtime capture are absent, so every "
        "execution profile and device view remains provisional and ineligible "
        "pending a runtime smoke result."
    )


def compose_compatibility(
    core_id: str,
    semantic_id: str,
    selected_run: str,
    reproduction_run: str,
    extra_caveats: list[str] | None = None,
) -> dict[str, Any]:
    """Compose the compatibility manifest from the golden and e2e records."""

    golden = _load(ROOT / ".local-e2e" / "nightlies" / semantic_id / "golden.json")
    build_goldens = golden.get("build_goldens", {}).get(core_id)
    if not isinstance(build_goldens, dict):
        raise PromoteCoreError(f"golden has no build_goldens for {core_id}")
    source_commit = golden.get("cores", {}).get(core_id, {}).get("source", {}).get("commit")
    if not source_commit:
        # Fall back to the semantic-id/source-lock commit when the golden omits it.
        source_commit = compose_source_set(semantic_id)["sources"][core_id]["commit"]

    selected = _load(ROOT / ".local-e2e" / "runs" / selected_run / "e2e-record.json")
    reproduction = _load(ROOT / ".local-e2e" / "runs" / reproduction_run / "e2e-record.json")
    package_sha = selected["packages"][0]["sha256"]
    reproducible = reproduction["packages"][0]["sha256"] == package_sha

    targets: dict[str, Any] = {}
    for arch in ("arm64", "armhf"):
        target = build_goldens.get(arch)
        if not isinstance(target, dict):
            continue
        artifact = target["artifact"]
        targets[arch] = {
            "state": "local_static_build_golden",
            "validation_scope": "static-build-only",
            "runtime_validation": "needs-target-runtime",
            "artifact_sha256": artifact["sha256"],
            "elf": ELF_LABEL[arch],
            "needed": artifact["needed"],
            "version_requirements": artifact["version_requirements"],
        }

    caveats = [
        (
            "The publication-disabled simulated-Actions build-core run and the "
            "independent native-local build-core run "
            + ("reproduced" if reproducible else "did not reproduce")
            + f" the {core_id}_libretro.zip package, resolver metadata, both ABI "
            "artifacts, and both active-marker build logs byte for byte. Execution "
            "was local; both builds cloned the pinned source over the network, so "
            "no offline source cache is proven."
        ),
        _device_caveat(targets),
        (
            "Content, BIOS/firmware handling, controls, audio/video pacing, saves "
            "and state round trips, reset and unload behavior, frontend "
            "integration, compatibility, licensing review, and sustained "
            "performance remain target-runtime and human gates. Publication "
            "remains disabled regardless of local byte reproducibility."
        ),
    ]
    caveats.extend(extra_caveats or [])

    document = {
        "$schema": "../core-compatibility.schema.json",
        "schema_version": 1,
        "core_id": core_id,
        "publication": "disabled",
        "evidence_availability": "workspace-local-ignored",
        "golden_source": f"pins/core-sets/{semantic_id}.json",
        "source_commit": source_commit,
        "e2e_run": f".local-e2e/runs/{selected_run}/e2e-record.json",
        "selected_e2e_content_sha256": selected["content_sha256"],
        "reproduction_run": f".local-e2e/runs/{reproduction_run}/e2e-record.json",
        "reproduction_e2e_content_sha256": reproduction["content_sha256"],
        "package_state": "reproducible" if reproducible else "not-reproducible",
        "package_sha256": package_sha,
        "caveats": caveats,
        "targets": targets,
    }
    document["content_sha256"] = content_sha256(document)
    return document


def _write_create_only(path: Path, document: dict[str, Any]) -> None:
    if path.exists():
        raise PromoteCoreError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _pipeline(*args: str) -> str:
    """Run one core_pipeline.py subcommand, failing loudly with its output."""

    command = [sys.executable, str(ROOT / "scripts" / "core_pipeline.py"), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise PromoteCoreError(
            f"`{' '.join(args)}` failed:\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def _write_evidence_index(core: str) -> None:
    """Regenerate the tracked evidence index from the promoted disk state."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "evidence_index", ROOT / "scripts" / "evidence_index.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = module.write(core)
    print(f"evidence index: {path.relative_to(ROOT)}")


def finish_promotion(core: str, semantic_id: str) -> None:
    """Materialize the release and repoint the three channels for a promotion.

    Goldens and pin-sets embed created_at, so every re-promotion invalidates
    the previous release bytes and all three channel pointers; the repair is
    mandatory follow-up work, so the promote chain finishes it. The
    compare-and-swap path is tried first; a pointer whose current target no
    longer deep-validates (stale or dangling after a refresh) is removed and
    re-created with --expect-absent.
    """

    pin = f"pins/core-sets/{semantic_id}.json"
    release = f".local-e2e/releases/{semantic_id}"
    if not (ROOT / release).exists():
        _pipeline("promote-release", "--pin-set", pin, "--output", release)
    _pipeline("validate-release", "--pin-set", pin, "--release", release)
    print(f"release materialized: {release}")
    channel_targets = {
        "nightly": f".local-e2e/nightlies/{semantic_id}/golden.json",
        "pinned": pin,
        "release": f"{release}/release-manifest.json",
    }
    for channel, target in channel_targets.items():
        pointer = ROOT / ".local-e2e" / "channels" / f"{channel}.{core}.json"
        swapped = False
        if pointer.exists():
            current = json.loads(pointer.read_text(encoding="utf-8"))
            if current.get("target", {}).get("id") == semantic_id:
                swapped = True
            else:
                digest = hashlib.sha256(pointer.read_bytes()).hexdigest()
                try:
                    _pipeline("update-channel", "--channel", channel,
                              "--core", core, "--target", target,
                              "--expect-current", digest)
                    swapped = True
                except PromoteCoreError:
                    pointer.unlink()
        if not swapped:
            _pipeline("update-channel", "--channel", channel, "--core", core,
                      "--target", target, "--expect-absent")
        _pipeline("validate-channel", "--channel", channel, "--core", core)
        print(f"channel {channel} -> {semantic_id}")


def _worktree_is_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0 and not result.stdout.strip()


def current_extra_caveats(core: str) -> list[str]:
    """The promoted document's caveats past the standard trio, for carry-over."""

    path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    if not path.exists():
        return []
    return list(_load(path).get("caveats", [])[3:])


def run_wave(
    cores: list[str],
    label: str,
    refresh: bool,
    carry_caveats: bool,
    finish: bool,
) -> None:
    """Two-phase multi-core rebuild + re-promote.

    Build records snapshot repository_head/repository_dirty, and promotion
    dirties tracked pins — so a wave must build EVERY core first (builds
    write only ignored .local-e2e paths) and only then promote. Interleaving
    the phases stamps repository_dirty=true into every post-first-promote
    record; this command exists so that sequencing mistake cannot recur.
    """

    if not _worktree_is_clean():
        raise PromoteCoreError(
            "wave requires a clean committed tree: build records snapshot "
            "repository_dirty, and every build must complete before any "
            "promote dirties tracked pins"
        )
    runs = {
        core: (
            f"actions-sim-build-core-{core}-{label}",
            f"build-core-{core}-local-{label}",
        )
        for core in cores
    }
    for index, core in enumerate(cores, 1):
        for profile, run_id in zip(("github-actions-sim", "local"), runs[core]):
            if (ROOT / ".local-e2e" / "runs" / run_id).exists():
                continue
            _pipeline("build-core", "--runner-profile", profile,
                      "--core", core, "--run-id", run_id)
        print(f"[{index}/{len(cores)}] {core}: built")
    for index, core in enumerate(cores, 1):
        caveats = current_extra_caveats(core) if carry_caveats else []
        selected, reproduction = runs[core]
        semantic_id = run_promotion(
            core, selected, reproduction, caveats, refresh
        )
        if finish:
            finish_promotion(core, semantic_id)
        _write_evidence_index(core)
        print(f"[{index}/{len(cores)}] {core}: promoted {semantic_id}")


def run_promotion(
    core: str,
    selected_run: str,
    reproduction_run: str,
    caveats: list[str],
    refresh: bool,
) -> str:
    """Sequence the whole promote chain; returns the semantic id.

    Each step is the existing reviewed CLI subcommand, invoked exactly as the
    documented manual ritual did -- this adds orchestration, not new policy.
    """

    catalog = _load(ROOT / "manifests" / "core-builds.json")
    spec = catalog.get("cores", {}).get(core)
    if spec is None:
        raise PromoteCoreError(f"core is not in the catalog: {core}")
    targets = spec.get("targets", [])
    if not targets:
        raise PromoteCoreError(f"core has no targets: {core}")
    for run_id in (selected_run, reproduction_run):
        for arch in targets:
            record = ROOT / ".local-e2e" / "runs" / run_id / core / arch / "build-record.json"
            if not record.is_file():
                raise PromoteCoreError(f"missing build record: {record}")

    compatibility_path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    retired: list[tuple[Path, Path]] = []
    if compatibility_path.exists():
        if not refresh:
            raise PromoteCoreError(
                f"{core} is already promoted; pass --refresh to re-promote "
                "(retires the previous source-set/pin-set/compatibility first)"
            )
        # Move the previous promotion's derived artifacts ASIDE rather than
        # deleting them: a failed refresh must never destroy outputs (learned
        # the hard way -- a retire-then-fail sequence deleted 27 cores' files
        # during the v2 re-promote wave). They are restored on any failure and
        # removed only after the whole chain, catalog-check included, passes.
        previous = _load(compatibility_path)
        previous_pin = previous.get("golden_source", "")
        previous_sid = Path(previous_pin).stem if previous_pin else ""
        candidates = [compatibility_path]
        if previous_sid:
            candidates.append(ROOT / "pins" / "core-sets" / f"{previous_sid}.json")
        for stale in candidates:
            if stale.exists():
                aside = stale.with_name(stale.name + ".retiring")
                stale.rename(aside)
                retired.append((stale, aside))
                print(f"retiring {stale.relative_to(ROOT)}")

    try:
        return _run_promotion_chain(
            core, targets, selected_run, reproduction_run, caveats, retired
        )
    except BaseException:
        for original, aside in retired:
            if aside.exists() and not original.exists():
                aside.rename(original)
                print(f"restored {original.relative_to(ROOT)}")
        raise


def _run_promotion_chain(
    core: str,
    targets: list[str],
    selected_run: str,
    reproduction_run: str,
    caveats: list[str],
    retired: list[tuple[Path, Path]],
) -> str:
    compatibility_path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    candidate_dir = ROOT / ".local-e2e" / "nightlies" / f"{core}-candidate-01"
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True)
    candidate = candidate_dir / "golden.json"

    _pipeline("import-golden", "--core", core, "--spruceos", "../spruceOS",
              "--output", str(candidate))
    for arch in targets:
        record = ROOT / ".local-e2e" / "runs" / selected_run / core / arch / "build-record.json"
        e2e = ROOT / ".local-e2e" / "runs" / selected_run / "e2e-record.json"
        _pipeline("promote", "--golden", str(candidate),
                  "--record", str(record), "--e2e-record", str(e2e))
        print(f"promoted {core}/{arch}")
    derived = json.loads(_pipeline(
        "derive-core-id", "--core", core, "--source-golden", str(candidate)
    ))
    semantic_id = derived["semantic_id"]
    print(f"semantic id: {semantic_id}")

    semantic_dir = ROOT / ".local-e2e" / "nightlies" / semantic_id
    semantic_dir.mkdir(parents=True, exist_ok=True)
    golden = semantic_dir / "golden.json"
    if golden.exists():
        golden.unlink()
    _pipeline("compose-core-golden", "--core", core,
              "--source-golden", str(candidate), "--output", str(golden))
    _pipeline("validate-golden", "--golden", str(golden), "--verify-store")
    print("golden valid")
    pin_path = ROOT / "pins" / "core-sets" / f"{semantic_id}.json"
    _pipeline("compose-pin-set", "--pin-id", semantic_id, "--core", core,
              "--source-golden", str(golden), "--output", str(pin_path))
    _pipeline("validate-pin-set", "--pin-set", str(pin_path),
              "--verify-store", "--verify-sources")
    print("pin-set valid")

    compatibility = compose_compatibility(
        core, semantic_id, selected_run, reproduction_run, caveats
    )
    _write_create_only(compatibility_path, compatibility)
    print(f"wrote manifests/compatibility/{core}.json")
    _pipeline("catalog-check")
    print("catalog valid")
    for original, aside in retired:
        aside.unlink(missing_ok=True)
    return semantic_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock = subparsers.add_parser(
        "compose-source-lock",
        help="create the catalog-derived source lock for a core",
    )
    lock.add_argument("--core", required=True)
    lock.add_argument(
        "--print", action="store_true", help="print the lock instead of writing it"
    )
    compose = subparsers.add_parser(
        "compose-lifecycle",
        help="create the source-set and compatibility manifest for a promoted core",
    )
    compose.add_argument("--core", required=True)
    compose.add_argument("--semantic-id", required=True)
    compose.add_argument("--selected-run", required=True)
    compose.add_argument("--reproduction-run", required=True)
    compose.add_argument(
        "--caveat", action="append", default=[], help="extra core-specific caveat (repeatable)"
    )
    compose.add_argument(
        "--print", action="store_true", help="print the documents instead of writing them"
    )
    runner = subparsers.add_parser(
        "run",
        help="sequence the whole promote chain for a built core "
             "(import-golden through compose-lifecycle plus catalog-check)",
    )
    runner.add_argument("--core", required=True)
    runner.add_argument("--selected-run", required=True)
    runner.add_argument("--reproduction-run", required=True)
    runner.add_argument(
        "--caveat", action="append", default=[], help="extra core-specific caveat (repeatable)"
    )
    runner.add_argument(
        "--refresh", action="store_true",
        help="re-promote an already-promoted core, retiring its previous "
             "source-set, pin-set, and compatibility manifest first",
    )
    runner.add_argument(
        "--carry-caveats", action="store_true",
        help="carry the promoted document's extra caveats (past the standard "
             "trio) into the refresh instead of passing each --caveat",
    )
    runner.add_argument(
        "--no-finish", action="store_true",
        help="skip the release materialization and channel repoint that "
             "normally complete the promotion",
    )
    wave = subparsers.add_parser(
        "wave",
        help="two-phase multi-core rebuild + re-promote: build every core "
             "on the clean tree first, then promote every core",
    )
    wave.add_argument("--core", action="append", required=True)
    wave.add_argument(
        "--label", required=True,
        help="run-id suffix; runs are actions-sim-build-core-<core>-<label> "
             "and build-core-<core>-local-<label>",
    )
    wave.add_argument("--refresh", action="store_true")
    wave.add_argument("--carry-caveats", action="store_true")
    wave.add_argument("--no-finish", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compose-source-lock":
            print(json.dumps(compose_source_lock(args.core), indent=2))
            return 0
        if args.command == "run":
            caveats = args.caveat
            if args.carry_caveats:
                if caveats:
                    raise PromoteCoreError(
                        "pass either --carry-caveats or explicit --caveat "
                        "values, not both"
                    )
                caveats = current_extra_caveats(args.core)
            semantic_id = run_promotion(
                args.core, args.selected_run, args.reproduction_run,
                caveats, args.refresh,
            )
            if not args.no_finish:
                finish_promotion(args.core, semantic_id)
            _write_evidence_index(args.core)
            print(f"promotion complete: {semantic_id}")
            return 0
        if args.command == "wave":
            run_wave(
                args.core, args.label, args.refresh,
                args.carry_caveats, not args.no_finish,
            )
            print(f"wave complete: {len(args.core)} cores")
            return 0
        if args.command == "compose-lifecycle":
            source_set = compose_source_set(args.semantic_id)
            compatibility = compose_compatibility(
                args.core, args.semantic_id, args.selected_run,
                args.reproduction_run, args.caveat,
            )
            if args.print:
                print(json.dumps({"source_set": source_set, "compatibility": compatibility}, indent=2))
                return 0
            _write_create_only(
                ROOT / "manifests" / "compatibility" / f"{args.core}.json", compatibility
            )
            print(f"wrote manifests/compatibility/{args.core}.json")
            return 0
    except PromoteCoreError as exc:
        print(f"promote-core error: {exc}", file=sys.stderr)
        return 1
    build_parser().error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
