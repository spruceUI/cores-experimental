"""Run builds in the pinned toolchain images and record what came out."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import recipe
from .catalog import Repo, known_good
from .variants import Variant

# retro_deinit is recorded but not required: some cores crash there when no game was loaded.
SMOKE_STEPS = ("dlopen", "retro_api_version", "retro_set_environment", "retro_init",
               "retro_get_system_info")
CHECK = re.compile(r"CHECK (\S+) (pass|fail)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_present(image_id: str) -> bool:
    if shutil.which("docker") is None:
        raise RuntimeError("docker is not on PATH")
    result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image_id],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == image_id


def run_container(repo: Repo, image_id: str, script: recipe.Script, out: Path,
                  cpus: str | None = None) -> int:
    out.mkdir(parents=True)
    (out / "script.sh").write_text(script.text)
    command = ["docker", "run", "--rm", "-e", f"OUTPUT_UID={os.getuid()}",
               "-e", f"OUTPUT_GID={os.getgid()}", "-v", f"{out.resolve()}:/output"]
    if cpus:
        command += ["--cpuset-cpus", cpus]
    for host, container in script.mounts:
        command += ["-v", f"{(repo.root / host).resolve()}:{container}:ro"]
    command += [image_id, "bash", "-lc", script.text]
    with (out / "build.log").open("w") as log:
        return subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode


def usability(out: Path) -> dict:
    """Parse the smoke loader's CHECK lines into a verdict."""
    smoke = out / "smoke.txt"
    if not smoke.exists():
        return {"probed": False}
    # A core may print to stdout without a newline, so a CHECK can start mid-line.
    checks = dict(CHECK.findall(smoke.read_text(errors="replace")))
    loaded = all(checks.get(step) == "pass" for step in SMOKE_STEPS)
    return {"probed": True, "loaded": loaded, "checks": checks}


def variant_calls(out: Path) -> dict | None:
    log = out / "variant-calls.log"
    if not log.exists():
        return None
    calls = log.read_text(errors="replace").splitlines()
    compiles = sum(1 for call in calls if " -c " in f" {call} ")
    return {"calls": len(calls), "compiles": compiles}


def build_one(repo: Repo, core: str, variant: Variant, out: Path, repeat: int = 1,
              spec: dict | None = None) -> dict:
    spec = spec or repo.cores[core]
    toolchain = repo.toolchains[recipe.toolchain_for(spec, variant.arch)]
    script = recipe.render(core, spec, variant.arch, variant)
    started = time.time()
    exit_code = run_container(repo, toolchain["image_id"], script, out)
    artifact = out / spec["build"]["artifact_name"]
    metadata = out / spec["metadata"]["artifact_name"]
    record = {
        "core": core,
        "variant": variant.describe(),
        "source": spec["source"],
        "toolchain": {"image": toolchain["image"], "image_id": toolchain["image_id"]},
        "exit_code": exit_code,
        "seconds": round(time.time() - started, 1),
        "host": platform.node(),
        "artifact": None,
        "metadata": None,
    }
    if artifact.is_file() and artifact.stat().st_size > 0:
        record["artifact"] = {"name": artifact.name, "sha256": sha256(artifact),
                              "size": artifact.stat().st_size}
    if metadata.is_file():
        record["metadata"] = {"name": metadata.name, "sha256": sha256(metadata)}
    record["usability"] = usability(out)
    record["variant_calls"] = variant_calls(out)
    record["status"] = status(record)
    if repeat > 1 and record["artifact"]:
        # A freeze must not depend on timing or parallelism: rebuild on half the CPUs.
        again = out / "repeat"
        cpus = os.cpu_count() or 1
        run_container(repo, toolchain["image_id"], script, again,
                      cpus=f"0-{max(0, cpus // 2 - 1)}" if cpus > 1 else None)
        second = again / artifact.name
        record["repeat_sha256"] = sha256(second) if second.is_file() else None
        record["reproducible"] = record["repeat_sha256"] == record["artifact"]["sha256"]
    (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def status(record: dict) -> str:
    # The smoke step never fails the script, so a non-zero exit is a build step failing.
    if not record["artifact"] or record["exit_code"] != 0:
        return "failed"
    use = record["usability"]
    if not use["probed"]:
        return "built"
    return "usable" if use["loaded"] else "unusable"


def build_core(repo: Repo, core: str, variants: list[Variant], out: Path, repeat: int = 1,
               fallback: bool = False) -> list[dict]:
    """Build each variant; with `fallback`, retry a failed one at the known-good recipe."""
    records = []
    previous = known_good(repo.cores[core]) if fallback else None
    for variant in variants:
        target = out / core / variant.name
        failed = target.with_name(target.name + ".current")
        for stale in (target, failed):
            if stale.exists():
                shutil.rmtree(stale)
        print(f"== {core} {variant.name} ({' '.join(variant.flags) or 'catalog flags'})", flush=True)
        record = build_one(repo, core, variant, target, repeat)
        if previous and record["status"] in ("failed", "unusable"):
            print(f"   {record['status']} at {record['source']['commit'][:12]}; trying known-good "
                  f"{previous['source']['commit'][:12]}", flush=True)
            target.rename(failed)
            record = build_one(repo, core, variant, target, repeat, spec=previous)
            failed.rename(target / "current-attempt")
            record["fallback"] = {"from_commit": repo.cores[core]["source"]["commit"]}
            (target / "record.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"   {record['status']} in {record['seconds']}s", flush=True)
        records.append(record)
    return records
