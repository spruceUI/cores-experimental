# Campaign historical-Python execution quarantine

Status: active. This policy is local-only and does not authorize publication,
deployment, device mutation, or external-service mutation.

## Quarantined evidence

The 2026-08-14 campaign baseline contains 77 ignored historical Python
artifacts below `.local-e2e/`. They are preserved evidence of earlier campaign
decisions. Preserve them in place and preserve their authenticated raw bytes,
paths, and identities. The count is a frozen inventory fact, not a directory to
rediscover at runtime and not an allowlist for executing 77 files.

Every quarantined Python artifact is evidence-only. Consolidated campaign and
check code must never:

- import it, add its directory to an import path, or load it as a module;
- pass it to Python, a shell, a subprocess, `runpy`, an import loader, or an
  equivalent execution service;
- evaluate or compile its contents with `eval`, `exec`, or `compile`;
- inherit behavior by monkeypatching, calling, or adapting its private
  functions, classes, module globals, or command entry point; or
- copy or modify it to create a new campaign generator.

No new executable Python belongs below `.local-e2e/`. A new campaign operation
is represented by reviewed tracked code plus strict declarative records and
immutable evidence references.

## Permitted evidence operations

An explicitly scoped investigation may inspect a quarantined artifact
inertly—as raw text or an AST—and may authenticate its path, byte length, line
count, and digest. Campaign validation may authenticate an exact byte snapshot
through a reviewed `EvidenceRef`. Neither operation grants execution authority.

If historical behavior is still required, characterize the behavior and
negative cases, then implement it independently in tracked production code.
The historical artifact remains unchanged and is never the implementation
dependency, template, plugin, adapter, or executable oracle.

## Consolidated public boundary

The campaign command boundary exposes exactly `check`, `stage`, `commit`, and
`verify`. Its path-valued options name strict evidence-reference documents:

| verb | accepted option |
|---|---|
| `check` | `--process-receipt-ref` |
| `stage` | `--process-receipt-ref` |
| `commit` | `--staged-receipt` |
| `verify` | `--state-root` |

There is no generator, script, module, adapter, loader, Python, shell, or
arbitrary executable option. The four workflow functions accept only the
campaign store, the corresponding typed evidence reference, and their reviewed
clock seam where applicable.

The check runner is a separate process boundary. Its executable argv prefixes
are code-owned entries in the tracked check registry. Validated parameters may
fill reviewed operand flags, but they may not select an executable, generator,
script, module, loader, or adapter.

## Enforcement

`tests/test_campaign_execution_quarantine.py` enforces three independent
boundaries without reading `.local-e2e/`:

1. an AST scan of tracked campaign and check packages rejects dynamic loading,
   evaluation, direct process execution, and held-Python path literals;
2. the exact four-verb CLI and workflow signatures reject executable-path
   expansion; and
3. registered check parameters cannot select executable code.

The test detector includes adversarial self-tests so aliasing an import loader
or constructing a held Python path from path fragments does not silently weaken
the quarantine.
