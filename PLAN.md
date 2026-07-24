# Phased plan: device-target-organized pipeline with runtime fitness

Written 2026-07-20. Target model (from REVIEW.md's end-goal assessment): the
**device target** is the organizing unit; a core is an input; a device set is
`filter(cores that build ∧ clear the device provider ceiling ∧ pass a target
runtime smoke test)` packaged per device; provenance collapses to
`source commit + toolchain image ID + artifact hash + libretro exports +
version_requirements + runtime-smoke result`.

## Guardrails (every phase)

- Local-only, publication-disabled; no push/dispatch/publish. Human gate before
  GitHub is untouched.
- The full test suite (`python3 -B -m unittest discover -s tests`),
  `catalog-check`, and `audit-workflows` stay green at the end of every phase.
- Integrity is *preserved*, not removed: hermetic pinned toolchain images,
  artifact hashes, and libretro-symbol validation remain throughout. Only the
  *excess* transcript/whole-tree-hash machinery is retired, and only after its
  replacement gate exists.
- Each phase is independently landable and reversible; risky consolidation is
  sequenced last, after its safer replacement is proven.

## Phases

### Phase 1 — Device-set assembly (additive, zero removals) ← implementing now

Turn the latent per-core `version_requirements` + device provider ceilings into
a first-class per-device candidate set. New **standalone** tool
`scripts/device_sets.py` (mirrors `profile_registry.py` / `toolchain_archive.py`,
so it is outside the pipeline provenance bundle and touches no frozen state) +
`tests/test_device_sets.py`. Output per device family: cores that build for the
device ABI and clear its provider ceiling, with reasons for every exclusion
(over-ceiling, no-arch-target, policy-excluded). No existing behavior changes.
This makes "device target" a real, tested output and creates the seam where the
runtime result later plugs in.

### Phase 2 — Consolidated fitness record (parallel to existing gates) ← done

Add a compact per-core-per-ABI fitness record — `{source commit + authoritative
pin ref, per ABI: artifact hash, ELF, execution profile, toolchain image id,
runtime deps, max GLIBCXX/GLIBC, libretro_abi, runtime_smoke: pending}`. Landed
as a standalone composer `scripts/fitness_record.py` (+ `tests/test_fitness_record.py`),
built from already-captured tracked data (compatibility manifests + execution
profiles), so it needs no rebuild and touches no frozen state. It **references**
the pin for full identity rather than duplicating the 170-file bundle — the
consolidation seam. Transcript contracts are untouched (still gates for now);
this record just makes a compact, device-relevant evidence view exist.

Design refinement vs. the original sketch: the fitness record is an independent
projection, not something `e2e` must emit or that device-set assembly must
import. Both `device_sets.py` (device -> cores) and `fitness_record.py` (core ->
provenance) read the same tracked data and compose at packaging time (Phase 6),
which avoids coupling and keeps each tool self-contained. Wiring the record into
`e2e` as a live output is deferred to when it becomes the promotion gate (with
Phase 3's runtime result).

### Phase 3 — Target runtime smoke test (the gate the goal needs) ← harness landed

The portable, verifiable core is landed as `scripts/runtime_smoke.py`
(+ `tests/test_runtime_smoke.py`): the smoke-result contract (the exact libretro
entry points a run must exercise — `SMOKE_CHECKS`), result validation, merge into
a fitness record's `runtime_smoke` field, and the payoff — `annotate_device_set`
promotes a core to `runtime_verified` when a captured pass on a device's provider
overrides the static ABI screen (an over-ceiling core that actually runs becomes
eligible for that device). All unit-tested with synthetic results.

**Executor (landed and running locally).** The ARM artifacts run under
qemu-user, registered via `tonistiigi/binfmt` — exactly what GitHub's
`docker/setup-qemu-action` does, so local and CI are identical. The executor is
`runtime/smoke_loader.c` (a minimal libretro loader: dlopen with `RTLD_NOW` so an
unmet provider symbol fails at load, then the content-free `SMOKE_CHECKS`
sequence) driven by `scripts/smoke_exec.py`, which compiles the loader inside a
target-ABI container, runs it against a store artifact, and emits a validated
`runtime_smoke` result. `tests/test_smoke_exec.py` covers the deterministic
parse/resolve logic.

Verified end to end: `gearboy` arm64 loads and passes all six checks under an
emulated arm64 container (the loader captures the core's own
`Gearboy 3.8.9-8-g36d723f` identity). The device-ceiling signal is real too:
running `gearboy` armhf (needs GLIBCXX 3.4.32) against an old libstdc++
(GCC 8, ~3.4.25) fails at `dlopen` exactly as it would on a Mini — the smoke
detects device-ABI incompatibility, not just generic-ARM load.

**On Actions** the same executor runs on an x86 `ubuntu-latest` runner with
`docker/setup-qemu-action`, or a native arm64 runner. Remaining Phase 3 work:
source each device's real provider libs into a per-device sysroot image (turns
"runs under ARM" into "runs on the Mini/A30"), the dispatched smoke workflow,
and widening from one core to the roster.

### Phase 4 — Demote transcript contracts to optional diagnostics

With fitness + runtime smoke as the promotion gate, flip the 48 compile-transcript
contract modules from required gates to opt-in diagnostics (`--strict-transcript`).
Keep them runnable; take them off the critical path. Shrink the 55 contract test
files to a representative diagnostic few. Large maintenance-surface reduction.

### Phase 5 — Provenance & workflow consolidation

Replace the 170-file pipeline-bundle in pins with a single pipeline
commit/version reference. Reorganize workflows into one reusable `core × arch`
build workflow + a per-device assembly/packaging workflow; keep individual
`build-<core>.yml` as thin debug callers; replace the byte-freeze audit with
pinned-SHA + structural lint. Freeze golden/channel/schema-v1–v8 machinery.

### Phase 6 — Device packaging & human-gated publish path

Per-device package (`cores/`+`cores64/`+`.info`+manifest) with fitness + smoke
evidence attached, staged at `.local-e2e/device-sets/<device>/`, ready for the
human publish decision. No auto-publish.

## Pre-bucket architecture improvements (approved 2026-07-20)

Before the 44-core legacy migration bucket, five improvements were approved to
avoid multiplying friction/over-engineering 44×:

1. **Promotion automation** — `scripts/promote_core.py compose-lifecycle` composes
   the source-set + compatibility manifest deterministically (auto-derives the
   device-eligibility caveat from `version_requirements`). Reproduces uzem's
   hand-authored source-set byte-for-byte. Done, green.
2. **Decouple brittle counts** — `test_gearboy`/`test_gearsystem`/
   `test_full_release_repository` now derive canonical/bridge counts dynamically,
   so a promotion no longer edits them. Done, green.
3. **Contract tiering (decision: tiered, light default / heavy on registered
   contract)** — `scripts/contract_tier.py` defines the policy and the light
   gate (valid static build golden + passing runtime smoke). All 41 current
   canonical cores are heavy (they carry registered contracts); the light tier
   applies to future legacy migrations that are not given a transcript contract.
4. **Runtime smoke as the universal gate** — the light gate requires a passing
   runtime_smoke for full (non-static-only) promotion, both tiers, so device
   fitness is captured per core rather than deferred. Done (gate defined).
5. **Tool unification** — `contract_tier.py report` folds tier + light-gate +
   runtime_smoke + device (Mini) eligibility into one view. Done (unified view).

Remaining deep integrations (per-core, during the bucket): rewire
`core_pipeline` promotion to defer light-tier cores to the light gate; surface
the tier/device view inside `catalog-check`/`audit-workflows`; generate the
per-core doc lists from the catalog.

## Status

- [x] Phase 1 — device-set assembly (`scripts/device_sets.py`), green
- [x] Phase 2 — consolidated fitness record (`scripts/fitness_record.py`), green
- [~] Phase 3 — runtime smoke contract (`scripts/runtime_smoke.py`) + executor
  (`runtime/smoke_loader.c`, `scripts/smoke_exec.py`) landed green and verified
  executing under qemu (load pass + ceiling-fail both demonstrated). Pending:
  per-device provider-lib sysroots, dispatched workflow, roster widening.
- [~] Phase 4 — contract tiering + light gate (`scripts/contract_tier.py`)
  landed green; per-core promotion rewiring deferred to the bucket.
- [ ] Phase 5–6 — catalog-check integration, doc generation, device packaging.
