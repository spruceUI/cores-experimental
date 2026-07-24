# Core builder audit — consolidation, over-engineering, improvement

*2026-07-22. Measured against the tree at `0b6f6dd` (92 canonical cores) and
against the lived cost of onboarding six cores in one session. Every number
below was measured, not estimated.*

## Shape of the builder today

| unit | size |
|---|---|
| `scripts/core_pipeline.py` | 12,378 lines, 196 functions |
| `scripts/core_pipeline_lib/contracts/` | 97 modules, 25,209 lines |
| supporting scripts (promote, toolchain, profiles) | ~3,000 lines |
| CLI | 16 subcommands |

The proof engines themselves (`c_only` / `mixed_language` / `c_asm` /
`direct_cmake`) are in good shape: the per-core relaxations added this session
were all opt-in fields with zero default-behaviour change, which is exactly how
a shared engine should grow. The findings below are about everything *around*
them.

## Findings, ordered by payoff

### 1. The promote chain is eight manual commands (highest payoff, lowest risk)

Every onboarding runs the same ritual: `import-golden → promote (×arch) →
derive-core-id → compose-core-golden → validate-golden → compose-pin-set →
validate-pin-set → compose-lifecycle`, with the semantic ID plumbed through by
hand (`docs/adding-a-new-core.md` scripts it in bash; 14 command invocations).
Every step already exists as code; only the orchestration is manual, and a
mis-plumbed SID fails halfway with the candidate dir in an odd state.

**Fix:** one `promote_core.py run --core X --selected-run A --reproduction-run
B` that sequences the existing steps. Pure orchestration, no validation change.

### 2. ~3,700 lines of copy-pasted spec validators

78 `*_spec_is_well_formed` functions (2,297 lines) plus their
`*_SPEC_IDENTITY` dicts (1,395 lines) are the same function: *rebuild the
expected catalog dict and compare for equality*. The variation is only which
optional `build` keys appear (overlays / make_variables / submodules / epoch).
Onboarding chailove this session meant copy-pasting mupen64plus_next's module
and changing constants — the definition of mechanical duplication.

On top of that, `core_pipeline.py` carries three parallel per-core registration
points: 89 contract-module import blocks, a 51-entry `if core_id == X and not
x_spec_is_well_formed(spec)` dispatch chain, and an 86-entry proof-name → callable
map — plus the fourth registration in `contracts/registry.py`.

**Fix:** one shared `spec_matches_identity(spec, identity)` helper; each core
module keeps only its identity dict and proof constants. Replace the dispatch
chain and proof map with a registry keyed by core id (the `registry.py`
dataclass is already the natural home). Estimated net deletion: ~3,000 lines,
no behaviour change, per-core tests unchanged.

### 3. The count-bump ritual makes every onboarding touch 3 test files

Eight audit-count literals in `test_core_pipeline.py`, the
`len(CORE_LOG_CONTRACTS)` literal, and the roster-message string in
`test_full_release_repository.py` all churn on every single onboarding. The
compatibility counts were already converted to derived values (the comment in
the test says why); the rest were not. These literals are tripwires by design —
but a tripwire only needs *one* authoritative literal, not five scattered
copies of the same fact.

**Fix:** a single `tests/expected_counts.py` (or fixture JSON) holding the
reviewed numbers once; the three test files import it. Onboarding then edits
one reviewed line instead of hunting literals. Keep `masked_build_failure_paths`
and friends literal — their downward march *is* the migration's scoreboard.

### 4. Adding a make-variable profile touches six places

`make_variable_profile`, the contract-name map, the `validated_make_variables`
branch, `make_variable_shell`'s makefile selection, the golden-build validator,
and the recipe-snapshot validator (52 `MAKE_PROFILE` references in
`core_pipeline.py`). parallel_n64 and mupen64plus_next each paid this in full.

**Fix:** a `MakeProfile` dataclass registry — id, exact variables, build keys,
whether `source_date_epoch`/`git_version` are required or forbidden, makefile
path, forbidden-macro set. The six if/elif chains collapse to lookups. The
reviewed-exact-profile security property is unchanged: the registry entries
*are* the review.

### 5. The toolchain digest chain has five hand-synchronized layers

Editing one Dockerfile comment required coordinated updates to: the toolchain
lock (per-arch sha256 + its content hash), the `core-builds.json` mirror (+
lock file/content hashes + validator self-pin), the digests **hardcoded in
`toolchain_archive.py`'s `TOOLCHAIN_CONTRACTS`**, `execution-profiles.json`
(per-profile digests + content hash), and the pinned literals in
`test_core_pipeline.py`. Five layers, three different content-hash algorithms.
The mirrors exist deliberately (drift detection), but updating them is pure
mechanism.

**Fix:** a `sync-toolchain-digests` subcommand that recomputes the whole chain
from the Dockerfiles outward and reports what moved. The cross-check property
is preserved — validation still compares independently stored copies — only
the update becomes mechanical.

### 6. Generic validators have grown per-core elif bodies (the over-engineering)

`validate_catalog` (654 lines), the pin-set/golden validators (~590 each), and
`verify_recipe_snapshot` (562 lines, dispatching on snapshot_version 1–10)
each embed per-core special cases — vecx, 81, picodrive, snes9x2005_plus,
ffmpeg — inside nominally generic functions. That is the worst of both worlds:
the generic path is no longer readable, and the per-core logic is far from the
per-core module that owns everything else about that core. The
`validated_make_variables` function alone is 247 lines, most of it per-profile
error prose.

**Fix (opportunistic, not a rewrite):** when a special case is next touched,
move it into the owning contract module behind a small interface (e.g.
`golden_build_contract_overrides(core_id)`). Don't do a big-bang refactor —
these validators are load-bearing and the tests pin them; migrate case by case.

### 7. The pipeline-bundle hash makes every engine edit a full rebuild (decision, not defect)

`pipeline_sha256` covers 131 files, so editing *any* contract module
invalidates *every* core's recipe identity — the "edit pipeline → rebuild both
profiles" tax was paid four times this session. Scoping the hash per-core
(own module + shared engines) would eliminate most rebuilds but weakens the
"the whole pipeline is pinned" property to "the relevant pipeline is pinned".
That is a real trade-off about what the recipe identity *means*, so it needs a
deliberate decision, not a cleanup commit. Recorded here; recommend leaving
as-is until the onboarding rate drops.

### 8. Contract-constant extraction is re-improvised every onboarding

The per-arch sha256 constants (compile pair, invocation, link objects, link
options) are extracted with ad-hoc scratchpad scripts rewritten each time
(`extract_casm.py` and friends this session). That's the one step of the
recipe with no tooling.

**Fix:** an `extract-contract --core X --run-id Y` subcommand that parses the
exploratory log with the real engine parsers and prints the constants block
ready to paste into the contract module. Small, and it removes the largest
remaining source of onboarding transcription error.

## What is *not* over-engineered

Worth saying explicitly: the things that look heavy are earning their keep.
The five-layer digest mirroring caught a real drift (armhf base tag) this
session. The strict catalog validators rejected four genuinely wrong states
during KM onboarding before any build ran. The anti-overclaim guard in
`profile_registry` correctly rejected an evidence transcription that claimed
too much. The cost problems above are about *update mechanics*, not about the
checks existing.

## Suggested order

1 (promote command) → 2 (spec dedup) → 3 (count fixture) → 8 (extractor) →
4 (profile registry) → 5 (digest sync) → 6 (opportunistic) → 7 (decision only).

Items 1–3 remove most of the per-core onboarding tax and are independently
committable with the full suite green after each.
