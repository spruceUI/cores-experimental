#!/usr/bin/env python3
"""Execute the libretro load smoke for one core/ABI under an ARM container.

Compiles ``runtime/smoke_loader.c`` inside a target-ABI container (run under
qemu-user via binfmt, exactly as GitHub's ``docker/setup-qemu-action`` sets up,
or natively on an ARM runner) and runs it against a built core artifact from the
local store. Parses the loader's ``CHECK`` lines into a validated
``runtime_smoke`` result.

Fidelity note: with a stock ARM base image this proves the core loads under the
ARM ABI, not that it loads on a specific device — a stock image ships a modern
libstdc++. Pass ``--image`` / ``--provider-profile`` pointing at a sysroot that
carries the device's real provider libs to make the result device-faithful.

Local, read-only over the repo, and never publishes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime_smoke  # noqa: E402  (sibling standalone module)

COMPATIBILITY_DIR = ROOT / "manifests" / "compatibility"
STORE_ARTIFACTS = ROOT / ".local-e2e" / "store" / "artifacts" / "sha256"
LOADER_SOURCE = ROOT / "runtime" / "smoke_loader.c"

DOCKER_PLATFORM = {"arm64": "linux/arm64", "armhf": "linux/arm/v7"}
DEFAULT_IMAGE = {"arm64": "arm64v8/gcc:13", "armhf": "arm32v7/gcc:13"}

CONTAINER_SCRIPT = (
    "set -e; "
    "cc -O0 /smoke_loader.c -o /tmp/smoke_loader -ldl; "
    "/tmp/smoke_loader /core.so"
)


def resolve_artifact(core_id: str, architecture: str) -> Path:
    """Locate a core's ABI artifact in the content-addressed store."""

    manifest = COMPATIBILITY_DIR / f"{core_id}.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    target = document.get("targets", {}).get(architecture)
    if not isinstance(target, dict):
        raise runtime_smoke.RuntimeSmokeError(
            f"{core_id} has no {architecture} target"
        )
    digest = target.get("artifact_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise runtime_smoke.RuntimeSmokeError(f"{core_id} {architecture} artifact hash is invalid")
    path = STORE_ARTIFACTS / digest[:2] / digest
    if not path.is_file():
        raise runtime_smoke.RuntimeSmokeError(
            f"artifact not staged in the local store: {path}"
        )
    return path


def parse_loader_output(text: str) -> dict[str, bool]:
    """Parse ``CHECK <name> pass|fail`` lines into a checks map.

    Every smoke check defaults to ``False``, so a crash that stops the loader
    before a line prints is correctly recorded as a failure of that step.
    """

    checks = {name: False for name in runtime_smoke.SMOKE_CHECKS}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "CHECK" and parts[1] in checks:
            checks[parts[1]] = parts[2] == "pass"
    return checks


def run_smoke(
    *,
    core_id: str,
    architecture: str,
    artifact: Path,
    image: str,
    provider_profile: str,
    runner: str = "qemu-user",
    timeout: int = 600,
) -> dict:
    """Run the load smoke in a container and return a runtime_smoke result."""

    if architecture not in DOCKER_PLATFORM:
        raise runtime_smoke.RuntimeSmokeError(f"unknown architecture: {architecture}")
    command = [
        "docker", "run", "--rm",
        "--platform", DOCKER_PLATFORM[architecture],
        "-v", f"{LOADER_SOURCE}:/smoke_loader.c:ro",
        "-v", f"{artifact}:/core.so:ro",
        image,
        "bash", "-lc", CONTAINER_SCRIPT,
    ]
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = "timeout"
    checks = parse_loader_output(stdout)
    result = runtime_smoke.build_smoke_result(
        core_id=core_id,
        architecture=architecture,
        runner=runner,
        provider_profile=provider_profile,
        checks=checks,
    )
    result["image"] = image
    result["loader_stderr"] = stderr.strip().splitlines()[-3:]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run the load smoke for one core/ABI")
    run.add_argument("--core", required=True)
    run.add_argument("--arch", required=True, choices=sorted(DOCKER_PLATFORM))
    run.add_argument("--artifact", help="core .so path; default resolves from the store")
    run.add_argument("--image", help="ARM container image; default is a stock gcc image")
    run.add_argument(
        "--provider-profile",
        help="device contract id whose provider libs were used; default marks a "
        "generic (non-device-faithful) ARM run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            artifact = Path(args.artifact) if args.artifact else resolve_artifact(
                args.core, args.arch
            )
            image = args.image or DEFAULT_IMAGE[args.arch]
            provider = args.provider_profile or f"generic-{args.arch}"
            result = run_smoke(
                core_id=args.core,
                architecture=args.arch,
                artifact=artifact,
                image=image,
                provider_profile=provider,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["status"] == "pass" else 1
    except runtime_smoke.RuntimeSmokeError as exc:
        print(f"smoke exec error: {exc}", file=sys.stderr)
        return 2
    build_parser().error("unknown command")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
