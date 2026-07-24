#!/usr/bin/env python3
"""Extract per-core contract constants from an exploratory build log.

Onboarding step 6 of docs/adding-a-new-core.md: after the exploratory build,
the per-arch compile/link sha256 constants must be transcribed into the core's
contract module. Until now that parsing was re-improvised in scratchpad scripts
for every core -- the one step of the recipe with no tooling, and the largest
remaining source of transcription error.

This tool runs the REAL engine parsers (the same code the proof will run) over
the logs and prints the constants ready to paste:

    python3 scripts/extract_contract.py --core <core> --run-id <run-id> \\
        [--engine c_only|mixed_language|c_asm]

Read-only. Lives outside the hashed pipeline bundle on purpose: it is
authoring tooling, not build policy, so adding or changing it never perturbs
any core's recipe identity.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core_pipeline_lib.contracts import c_asm as CA  # noqa: E402
from core_pipeline_lib.contracts import mixed_language as ML  # noqa: E402
from core_pipeline_lib.contracts.c_only import (  # noqa: E402
    c_only_compile_invocation,
    c_only_compile_invocation_sha256,
    c_only_compile_pair_sha256,
    c_only_link_object_sha256,
    c_only_raw_link_object_sha256,
)
from core_pipeline_lib.contracts.command_line import (  # noqa: E402
    ordered_command_argv_sha256,
    output_option,
    semantic_log_path,
)
from core_pipeline_lib.contracts.compiler import (  # noqa: E402
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)


def _classify(source: str, compiler: str, cxx: frozenset[str]) -> str:
    if compiler in cxx and not source.endswith(".c"):
        return "cxx"
    if source.endswith(".c"):
        return "c"
    return "asm"


def extract_arch(log_path: Path, arch: str, engine: str) -> dict:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    compilers = TARGET_COMPILERS[arch]
    cxx = TARGET_CXX_COMPILERS[arch]
    pairs: Counter = Counter()
    invocations: list = []
    languages: Counter = Counter()
    rejected: list[str] = []
    link_tokens: list[str] | None = None
    for line in text.splitlines():
        if not line_may_name_target_compiler(line, compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens or tokens[0] not in compilers:
            continue
        if "-c" in tokens:
            if engine == "c_asm":
                parsed = CA.c_asm_compile_invocation(
                    tokens, compilers, (), expected_cxx_compilers=cxx
                )
            elif engine == "mixed_language":
                parsed = ML.mixed_language_compile_invocation(
                    tokens, compilers, cxx
                )
                if parsed is not None:
                    parsed = parsed[:2] + (tuple(tokens),)
            else:
                parsed = c_only_compile_invocation(tokens, compilers)
            if parsed is None:
                rejected.append(line[-160:])
                continue
            output, source = parsed[0], parsed[1]
            pairs[(output, source)] += 1
            invocations.append(parsed)
            languages[_classify(source, tokens[0], cxx)] += 1
        elif any(t == "-o" or t.startswith("-o") for t in tokens[1:]):
            link_tokens = tokens
    result: dict = {
        "arch": arch,
        "compiles": sum(pairs.values()),
        "languages": dict(languages),
        "compile_pair_sha256": c_only_compile_pair_sha256(pairs),
        "compile_invocation_sha256": c_only_compile_invocation_sha256(
            invocations
        ),
        "rejected_compiles": len(rejected),
        "rejected_samples": rejected[:3],
    }
    if link_tokens is not None:
        raw_output, output_indexes = output_option(link_tokens)
        operands = [
            token
            for index, token in enumerate(link_tokens[1:], start=1)
            if index not in output_indexes and not token.startswith("-")
        ]
        objects = [semantic_log_path(op, ".o") for op in operands]
        result["link"] = {
            "artifact": raw_output,
            "options": [
                token
                for index, token in enumerate(link_tokens[1:], start=1)
                if index not in output_indexes and token.startswith("-")
            ],
            "link_object_sha256": c_only_link_object_sha256(
                [obj for obj in objects if obj]
            ),
            "raw_link_object_sha256": c_only_raw_link_object_sha256(operands),
            "ordered_link_argv_sha256": ordered_command_argv_sha256(
                link_tokens
            ),
            "objects_all_contained": all(objects),
            "objects_match_compiles": Counter(
                obj for obj in objects if obj
            )
            == Counter({out: n for (out, _src), n in pairs.items()}),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--engine",
        choices=["c_only", "mixed_language", "c_asm"],
        default="c_asm",
        help="engine parser to run (c_asm accepts C, C++, and assembly, so it "
        "is the safe default for classification)",
    )
    args = parser.parse_args(argv)
    run_dir = ROOT / ".local-e2e" / "runs" / args.run_id / args.core
    if not run_dir.is_dir():
        print(f"error: no run directory: {run_dir}", file=sys.stderr)
        return 1
    results = []
    for arch_dir in sorted(run_dir.iterdir()):
        log = arch_dir / "build.log"
        if arch_dir.name in TARGET_COMPILERS and log.is_file():
            results.append(extract_arch(log, arch_dir.name, args.engine))
    if not results:
        print("error: no build logs found", file=sys.stderr)
        return 1
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
