# Cores-spruce pipeline review

Reviewed 2026-07-20 in `/home/arkun/ai/CFW/Spruce/git/Cores-spruce` on `main`
(local checkpoint `450163c`, working tree carrying the uncommitted
Gearboy/Gearsystem lifecycle set). Read-only review; no repository changes made.

## Verdict

Healthy and safe to sit at the human deployment gate. Everything the docs claim
is backed by passing checks, and the "nothing publishes to GitHub without a
human" invariant holds under scrutiny — enforced in three independent layers
(workflow triggers, workflow permissions, and record-level validation). The
items for the human reviewer to weigh are all on the *legacy* (unmigrated)
surface, not the migrated pipeline.

## Validated (all green)

- **Test suite:** `python3 -B -m unittest discover -s tests` → 1074 passed,
  11 skips, exit 0 (~163s). The 11 skips are the documented environmental
  detached-worktree evidence-store cases.
- **`catalog-check`:** `status: valid`, `publication: disabled`. Coverage 50 =
  40 canonical + 10 legacy-bridge; 4 pending (atari800, fbneo, mame2003_plus,
  picodrive). Matches the docs.
- **`audit-workflows`:** `status: valid`; 54/54 catalog cores & workflows, 98
  total per-core workflows, 54 shared-pipeline, 44 unmigrated legacy, 88 masked
  failure paths, 40 info-only risks. Every number matches README/architecture
  docs. The audit self-validates the coordinator/worker with pinned action SHAs.
- **Gearboy/Gearsystem focused tests:** `test_contract_gearboy` +
  `tests.cores.test_gearboy` (21+21) and the Gearsystem equivalents (22+22)
  pass. All six new JSON files parse; doc edits mirror the existing Potator
  pattern precisely.
- **Hygiene:** `.gitignore` covers `.local-e2e/`, `__pycache__/`, `CLAUDE.md`;
  `.pytest_cache/` is untracked and self-ignored. No secrets in tracked/untracked
  sources (apparent hits are `GIT_VERSION` compile-token constants). No
  TODO/FIXME/HACK/debug markers in `scripts/`.

## GitHub-deployment safety (core concern) — solid

The "publication-disabled" claim is real and defended in depth:

1. **Triggers.** No workflow fires on `push`, `pull_request`, `schedule`, or
   `release`. All 101 workflows are `workflow_dispatch`/`workflow_call` only, so
   merging to GitHub cannot auto-run or auto-publish anything — a human must
   click Run.
2. **Migrated path.** The 54 migrated per-core workflows plus the
   `release-candidate.yml` coordinator and `_build-one-core.yml` worker all
   declare `permissions: contents: read`, use `persist-credentials: false`, pin
   every action to a full SHA, and only produce ephemeral
   `actions/upload-artifact` outputs (retention-limited CI artifacts, never a
   GitHub Release or `git push`). The worker gates on
   `test -z "$(git status --short)"` before building.
3. **Record layer.** `publication == "disabled"` is required fail-closed at
   every boundary independently — plans, results, seals, goldens, compatibility,
   blacklist, catalog policy, build records, and evidence. The `github-actions`
   runtime profile (`scripts/core_pipeline_lib/runtime/github_actions.py`) has
   zero network/publish code, and its native variant refuses to run on a dirty
   checkout or a `GITHUB_SHA` that does not match HEAD.

## Findings for the human before the gate

1. **Legacy workflows are the live-publish surface (documented, but the real
   risk).** 44 unmigrated per-core workflows + `build-docker.yml` (45 total)
   still declare `contents: write` and run `gh release upload --clobber` /
   `gh release create`. They are human-gated (dispatch-only), so nothing fires
   on merge — but anyone who manually dispatches, e.g. `build-hatari.yml`, will
   publish a `beta-*` release. This is what the README warns about ("must not be
   treated as reliable artifact gates until migrated"). The deployment decision
   should account for who can trigger these post-push.
2. **Legacy workflows use unpinned actions.** Those same 45 files use
   `actions/checkout@v4` and `mlugg/setup-zig@v2` (mutable tags) rather than
   pinned SHAs. Every migrated workflow is properly SHA-pinned. Same population
   as finding 1 — best folded into each core's migration rather than a separate
   pass.
3. **Process gate, not code.** SESSION.md notes the dev-workflow audit-log
   append is pending because the local approval-service quota is exhausted until
   2026-07-24 ("do not retry or bypass"). If committing the Gearboy/Gearsystem
   work is meant to route through that audit trail, it is currently blocked by
   that gate — a scheduling constraint, not a defect.

## Uncommitted Gearboy/Gearsystem work

The working tree matches SESSION.md exactly: two new canonical lifecycles
(compatibility manifests, one-core pins, source sets, focused + contract tests)
plus README/architecture/operations doc updates and the full-release count bump
(38→40 canonical, 12→10 bridge). It is self-consistent, passes the full suite,
and is cleanly separable from the committed FBNeo checkpoint (`a37ba2b`). Ready
to be reviewed and committed as its own change per the existing plan — subject
to the audit-log gate in finding 3.

---

# Workflow-layer review: individual builder & dispatched group build

Second pass (2026-07-20), scoped to the GitHub Actions surface — the individual
core builders (`build-<core>.yml`) and the dispatched group build
(`release-candidate.yml` coordinator + `_build-one-core.yml` worker) — for
readability, consistency, and optimization, with Actions as the final target but
kept local/human-gated until deployment.

## How the two paths relate (verified)

- The dispatched group build does **not** reuse the individual `build-<core>.yml`
  files. The coordinator derives a matrix from an immutable plan and fans it out
  to one reusable worker, `_build-one-core.yml`. So there are two separate
  Actions implementations of "build one core."
- Both paths do share the underlying build contract: the individual builder runs
  `core_pipeline.py e2e`, the worker runs `build-core`, and `cmd_build_core` is a
  thin wrapper that calls `cmd_e2e` (`scripts/core_pipeline.py:10757`). Both
  funnel through `cmd_e2e` → `perform_build` → `package_e2e_core`. The only
  behavioral difference is fail-fast: the individual `e2e` runs with
  `fail_fast=False` (build both ABIs for full diagnostics); the worker's
  `build-core` forces `fail_fast=True` (stop the core after the first failed ABI
  to save matrix time). The architecture doc's "shared worker contract" claim is
  accurate.

## Consistency — strong where it counts

- The 54 migrated individual builders are **byte-identical modulo the core name**
  (0/54 differ from a normalized reference). Excellent uniformity.
- All 54 migrated builders + coordinator + worker: `permissions: contents: read`,
  `workflow_dispatch`/`workflow_call`-only triggers, every action pinned to a
  full SHA. Nothing auto-fires on push; nothing publishes.

## Consistency gaps (the individual builder vs the group worker diverge)

1. **`persist-credentials: false` is missing from all 54 individual builders.**
   The coordinator and worker set it; 0/54 individual builders do, so each leaves
   the checkout token in `.git/config` for the job. Low blast radius (contents:
   read, no push), but an inconsistent hardening posture — set it in all 54.
2. **Toolchain download location differs.** The individual builder downloads the
   ~900 MB of tarballs into the repo root (`--dir .`); the worker downloads into
   `$RUNNER_TEMP/core-toolchains` (outside the repo). Both are individually
   correct, but for different reasons, which makes them fragile: the individual
   path only stays clean because `cmd_e2e` computes cleanliness with
   `git status --untracked-files=no`, whereas the worker's YAML guard
   `test -z "$(git status --short)"` *includes* untracked files and would fail if
   it downloaded into the repo. Tightening either side silently breaks the other.
3. **"Clean" is defined two different ways** (`--untracked-files=no` in `cmd_e2e`
   vs full `git status --short` in the worker YAML). Align on one definition.
4. **Subcommand naming hides the relationship.** The individual builder says
   `e2e` and the worker says `build-core`; they are the same contract differing
   only in fail-fast, but nothing in the YAML tells a maintainer that. A reader
   comparing the two files cannot see why they differ.
5. **`timeout-minutes` mismatch for the identical build.** Individual builder 45,
   worker 90. A slow core could time out on individual dispatch yet pass in the
   group. Align the two (or document the asymmetry).

## Optimization

1. **Collapse the 54 identical builders into thin callers of one reusable
   workflow.** Since they are already byte-identical modulo name, extract a
   `_build-core.yml` reusable workflow (checkout + toolchain download/verify/load
   + run e2e) and reduce each `build-<core>.yml` to a ~10-line caller passing
   `core_id` (and `fail_fast: false`). Benefits: one place to maintain the
   toolchain/build steps instead of 54, and the individual and group paths stay
   in lockstep by construction.
   - This is **safe against the 50-unique-reusable-workflow call-tree limit**: the
     individual wrappers are not in the coordinator's call tree (each is its own
     top-level dispatch, whose tree is `wrapper → _build-core` = 2 unique). It
     still satisfies `release/eligibility.py`, which only requires the file to
     exist at `.github/workflows/build-<core>.yml`.
   - The release worker `_build-one-core.yml` can also delegate its build steps to
     `_build-core.yml`, keeping only its plan-membership check, result recording,
     and artifact uploads — collapsing the two implementations into one and making
     the group build literally reuse the individual build definition.
2. **Cache the 900 MB toolchain download.** There is no `actions/cache` anywhere.
   The group build re-downloads 259 MB + 652 MB per matrix job (up to 54 cores,
   `max-parallel: 4`). Cache keyed on the toolchain-lock SHA
   (`pins/toolchains/local-cache-v1.json`); the `verify-downloads` gate still runs
   on the cached bytes, so integrity is preserved. This is the single largest
   CI-time / egress win.
3. **If "group build using the individual builds" is the intended model**, it is
   not the current one — optimization 1 is what makes it real (both paths become
   callers of `_build-core.yml`).

## Readability

- Individual builders are short, uniform, and readable; the inline checksum-gate
  comment is helpful. Coordinator/worker use clear `env:` blocks, descriptive
  step names, and a good "keep the immutable portable result last" note.
- The one readability gap is #4 above: add a one-line comment (in each builder or
  the shared reusable) noting that `e2e` and the worker's `build-core` share
  `cmd_e2e` and differ only in fail-fast. That removes the biggest "why are these
  two files different?" question for a future maintainer.

All of the above are local-only refactors; none change the publication-disabled
posture, and all remain gated behind the human deployment decision.

---

# Correction: the workflow layer is hash-locked by design

Third pass (2026-07-20). On attempting to implement the workflow-layer changes
above, I found the workflow surface is a deliberate content-addressed hash lock,
which changes what "implement" means and corrects two of my earlier
optimization suggestions. Recording this so the earlier section is read with
this caveat.

## What is frozen, and where

- **Coordinator and worker are frozen by exact SHA256.**
  `scripts/core_pipeline_lib/release/workflow_audit.py` pins
  `EXPECTED_WORKFLOW_SHA256` for `release-candidate.yml` and
  `_build-one-core.yml` ("the reviewed canonical contract"). Any byte change
  fails the audit until that hash is deliberately updated.
- **The audit allowlist forbids exactly my two headline optimizations.**
  `ALLOWED_ACTIONS` is only `actions/checkout`, `actions/download-artifact`,
  `actions/upload-artifact`; `EXPECTED_ACTION_COUNTS` pins the exact per-role
  inventory; and `_audit_uses` rejects any `./`-prefixed reference in the worker
  (only the coordinator may reference `_build-one-core.yml`). Therefore:
  - **Composite-action unification of the worker is disallowed** — the worker
    may not `uses: ./.github/actions/...`.
  - **`actions/cache` in the worker is disallowed** — it is an unapproved action
    and would break the pinned action inventory.
- **Every individual `build-<core>.yml` is byte-pinned too.** Each core-set pin
  records `workflow_sha256` (e.g. gearboy → `de4b7d74…`) and
  `manifests/core-builds.json` mirrors it; the pins additionally record the
  sha256 of every pipeline `.py` file. So editing an individual builder (even
  just adding `persist-credentials: false` or changing `timeout-minutes`) breaks
  that core's `validate-pin-set` / catalog identity and would require
  regenerating the recorded hash — i.e. re-blessing the exact evidence the human
  review gate signs.

## Consequence

The consistency fixes and optimizations in the previous section are still valid
*engineering*, but none can be "just edited in": each is a deliberate,
human-gated action that regenerates pinned security hashes (and, for the
worker/coordinator, updates the audit's `EXPECTED_WORKFLOW_SHA256` and possibly
`ALLOWED_ACTIONS`). That is additionally blocked right now by the dev-workflow
audit-log approval quota (exhausted until 2026-07-24 per SESSION.md). **I
therefore did not modify any workflow or pin**, to avoid forging that evidence.
The path to apply them, when approved, is: change the YAML → regenerate each
touched core's pin `workflow_sha256` (and `core-builds.json`) → for the
coordinator/worker, update `workflow_audit.py`'s expected hashes/allowlist and
its tests → re-run `catalog-check`, `audit-workflows`, and the full suite.

---

# Individual-core build review: devices and their differing requirements

Fourth pass (2026-07-20). Scope expansion into the per-core build as it relates
to the target devices. Data is drawn from `manifests/device-runtime-contracts.json`,
`manifests/execution-profiles.json`, and all 40 canonical
`manifests/compatibility/*.json` records. No files were changed.

## Build topology (only two profiles actually build)

- **`ra64-universal-v1`** (arm64, `locked-build-identity`): aarch64 GCC 9.4.0
  (Ubuntu 20.04), sysroot `/`, packages to `cores64/`. The universal 64-bit path.
- **`ra32-a30-v1`** (armhf, `locked-build-identity`): arm-a30 GCC 13.2.0
  (Buildroot 2024.02.1), A30 sysroot, packages to `cores/`. The **only** 32-bit
  build identity — every armhf artifact is compiled with the A30 toolchain.
- Provisional profiles with `build_identity: null` — `ra32-mini-v0`,
  `ra32-universal-v0`, `ra64-pixel2-v0` — do not build. `ra64-pixel2-v0` is
  additionally `provisional-missing-frontend` (no RetroArch binary captured).

The individual core builder is **device-agnostic**: it always builds both ABIs
through those two locked profiles and packages `cores/` + `cores64/` +
`<core>_libretro.info`. Device eligibility is a *downstream* read of each
target's captured `version_requirements`, never a build-time branch. This keeps
the 54 builders uniform (confirmed byte-identical modulo core name) and is the
right separation of concerns.

## Device families and ABI ceilings

- **32-bit (armhf) consumers:**
  - Miyoo Mini family (MINI, V4, PLUS, FLIP) — packaged **fallback** libstdc++
    with GLIBCXX ceiling **3.4.24** (`enforcing: false`). The binding constraint.
  - Miyoo A30 — bundled libstdc++ with GLIBCXX ceiling **3.4.32**
    (`enforcing: false`), matching the GCC 13.2 toolchain's maximum.
- **64-bit (arm64) consumers:** Trimui a133p (Smart Pro, Brick; Brick Pro
  staged), Trimui Smart Pro S, Miyoo Flip (64-bit default), plus provisional
  Anbernic H700 family, MagicX Zero28, and GKD Pixel2. No captured provider
  ceiling (`effective_abi_ceiling: unknown`).
- Every device contract is `provisional` / `needs-target-runtime`, and every
  provider is non-enforcing, so the GLIBCXX screen below is **necessary but not
  sufficient**: no device view is eligible until target runtime is captured.

## Per-core requirement segmentation (the differing requirements)

Derived by taking each target's maximum GLIBCXX symbol and comparing to the
device ceilings. arm64 is uniformly modest (all cores ≤ GLIBCXX 3.4.21, GLIBC
≤ 2.29) because of the older GCC 9.4 toolchain, so the 64-bit side clears the
ABI screen across the board. The 32-bit side splits three ways:

- **C-only (19 cores) — portable to every armhf device including Mini.** No
  libstdc++ dependency (`needed` is just libc/libm), GLIBC ≤ 2.7: 2048, a5200,
  cap32, crocods, fceumm, fmsx, freechaf, genesis_plus_gx, genesis_plus_gx_wide,
  lowresnx, mednafen_pce_fast, o2em, pokemini, potator, prosystem, race,
  snes9x2005, snes9x2005_plus, vecx.
- **C++ under the Mini ceiling (12 cores) — Mini- and A30-eligible on the ABI
  screen** (armhf GLIBCXX ≤ 3.4.21): 81, bluemsx, handy, mednafen_lynx,
  mednafen_ngp, mednafen_supergrafx, mednafen_vb, mednafen_wswan, quicknes,
  tgbdual, vice_x64, vice_xvic.
- **C++ over the Mini ceiling (9 cores) — A30-only on 32-bit**, Mini family
  ineligible pending an older-ABI/sparse-family override build or device-provider
  evidence: gambatte (3.4.29), mednafen_pcfx (3.4.29), mednafen_supafaust
  (3.4.29), gearboy / gearcoleco / gearsystem / nestopia / snes9x / stella2014
  (3.4.32).
- **Zero cores exceed the A30 3.4.32 ceiling.** The single A30-toolchain armhf
  artifact never overshoots A30, so A30 is the universal 32-bit consumer while
  Mini is the selective one.

Only one formal cross-core device constraint is currently encoded:
`mini-cxx-provider-unverified-v0` (gearboy, gearsystem; GLIBCXX_3.4.32 vs the
Mini fallback; `unverified-for-profile`). By the table above, gearcoleco,
nestopia, snes9x, stella2014, gambatte, mednafen_pcfx, and mednafen_supafaust
have the same Mini exposure — worth encoding the same constraint row for those
seven so the Mini-ineligibility is uniformly machine-checkable rather than only
narrated in per-core caveats.

## Cross-core device policies (already encoded)

- **ffmpeg:** `software-diagnostic-only`, default `excluded`; a PVR-accelerated
  flavor is only provisional for the a133p / MagicX families and explicitly
  denied on Miyoo Flip and Trimui Smart Pro S; needs target playback.
- **swanstation:** armhf device views `not-consumed`; catalog menu eligibility
  `unsupported` (32-bit devices do not receive it).

## Implications and considerations

1. **Device targeting is a packaging/annotation problem, not a build problem.**
   The builder correctly stays device-agnostic. The value-add is to surface each
   package's already-captured ABI screen (Mini-ok / A30-only / arm64-only) as a
   first-class per-core release annotation, so the human release decision and any
   on-device catalog gating are driven by `version_requirements` data that
   already exists rather than rediscovered per core.
2. **The 9 over-Mini cores are the natural sparse-family-override candidates.**
   The device policy is `portable-shared-default-sparse-family-override-on-evidence`;
   these nine are exactly where the shared A30 armhf artifact fails the Mini
   screen. Giving them a real Mini 32-bit build identity would require an
   older/lower-ABI armhf toolchain profile (a genuine `ra32-mini-v0`
   build_identity) or captured Mini provider evidence. None exists today;
   deferring is correct, but they are the concrete backlog.
3. **Blocked/assumed device paths to flag for the human gate:**
   - `ra64-pixel2-v0` is missing its frontend binary — GKD Pixel2 cannot be
     validated even once cores build.
   - Provisional Anbernic H700, MagicX Zero28, and Trimui Brick Pro (staged)
     reuse `ra64-universal-v1` with no captured provider, so their eligibility is
     assumed-by-family, not proven.
4. **Consistency check (passed):** every per-core caveat's ABI claim matches the
   captured `version_requirements` (e.g. gearboy armhf max GLIBCXX 3.4.32, arm64
   max 3.4.21), and the README/architecture per-core notes agree with the device
   registry. No drift found between the narrated device requirements and the
   machine-readable manifests.

---

# End-goal assessment: does the machinery serve "a working core set per device"?

Fifth pass (2026-07-20). Stepping back from the inner CI/integrity machinery to
judge the pipeline against its actual end goal — a RetroArch core set that runs
on each device target (Miyoo Mini family + A30 on armhf; Trimui, Miyoo Flip,
Smart Pro S, and provisional Anbernic/MagicX/GKD on arm64), packaged for
spruceOS and published only on a human decision. Where the machinery is in the
way or over-built, it is called out for consolidation.

## The core finding: the investment is inverted

The end goal is a core that **loads and runs on the device**. The pipeline
spends almost all of its complexity proving the *build transcript* is
bit-reproducible, and spends **nothing** proving the *output runs*:

- 48 per-core contract modules + 55 contract test files assert exact
  compile-command counts, exact diagnostic NFAs, exact link-object orderings,
  and byte-identical logs per ABI.
- Every core-set pin embeds a 170-file hash bundle of the entire `scripts/`
  tree, per ABI, as "the code that built this."
- An 847-line byte-freeze audit + SHA256-pinned coordinator/worker guard the CI
  config; `core_pipeline.py` is 11,375 lines; recipe snapshots span schema v1–v8.
- There is **no target RetroArch/QEMU runner and no runtime fixture** (confirmed:
  no runtime runner exists in `scripts/`). Every device view is
  `static-build-only` / `needs-target-runtime` / ineligible.

So the pipeline can prove a core was compiled with exactly 92 C commands and a
byte-identical log, but cannot answer "does it launch on a Miyoo Mini?" — which
is the only integrity the end goal requires. The reproducibility fortress is
built around a build that has never been shown to run on a single target.

## What genuinely serves the goal (keep)

- **The shared build/package primitive** (`e2e` → both ABIs → `cores/` +
  `cores64/` + `.info`). One contract, device-agnostic, byte-identical across the
  54 migrated builders. This is the right spine.
- **The device model as a screen.** `device-runtime-contracts.json` +
  `execution-profiles.json` correctly name the real constraint: the per-device
  libstdc++ provider ceiling (Mini 3.4.24, A30 3.4.32) and the ABI split. The
  captured `version_requirements` per artifact is exactly the right, cheap,
  device-relevant signal.
- **Pinned toolchain images + pinned action SHAs + publication-disabled default.**
  Hermetic containerized builds and supply-chain pinning are low-cost, real
  integrity that supports the goal.

## Over-engineered relative to the goal (consolidate / re-implement)

1. **Per-core byte-exact compile-command contracts — the biggest offender.**
   The 48 contract modules / 55 tests that pin "44 C++ compiles", "92 C
   compiles", exact diagnostic NFAs and link orderings prove reproducibility of
   the *compile transcript*. That is not a device-fitness signal, and it is an
   enormous maintenance surface: every upstream source bump that adds a file or a
   warning breaks the NFA. The hermetic pinned container + sanitized env already
   deliver the anti-tamper property these are reaching for. **Consolidate to** a
   promotion gate of: artifact SHA256 + source commit/tree + toolchain image ID +
   required libretro exports + captured `version_requirements`. Demote the
   compile-transcript proofs to an optional diagnostic, not a per-core gate.

2. **170-file pipeline-bundle hash per pin, per ABI.** Snapshotting the whole
   `scripts/` tree into every pin means any tooling edit invalidates the recorded
   provenance of unrelated cores and forces mass regeneration. Source commit +
   toolchain image ID + artifact hash already make a build reproducible.
   **Consolidate to** a single pipeline version/commit reference, not a 170-hash
   bundle duplicated across every pin and ABI.

3. **98 per-core workflows + 847-line byte-freeze audit.** The workflow layer is
   organized per-core, each file byte-provenance-pinned, with a hash-frozen
   coordinator/worker. For "build a set per device" the natural shape is a
   parameterized matrix (core × arch) plus a per-device assembly job — not 54+44
   near-identical YAMLs (the 54 migrated ones are byte-identical modulo name) each
   individually hash-pinned. **Consolidate to** one reusable build workflow driven
   by a matrix; keep the individual entrypoints only as thin debug conveniences;
   keep pinned action SHAs (cheap, real) but drop the per-file byte-freeze, which
   guards config for builds that never prove device runtime.

4. **Golden tiers / channels / schema v1–v8 / legacy-tranche machinery** exist to
   version and preserve provenance records for a product that has not yet shipped
   one validated device set. This is lifecycle scaffolding ahead of a lifecycle.
   It is not wrong, but it is weight to carry; freeze it and stop extending it
   until a device set actually ships.

## What makes the most sense (re-implementation shape)

Organize around the **device target**, with the core build as an input, not the
unit of the product:

1. **Device profile = {ABI, RetroArch frontend binary, provider-lib ceiling,
   toolchain matched to the device's real runtime}.** Today armhf is
   A30-toolchain-only, so the Mini family silently inherits A30 binaries; the 9
   over-ceiling cores can't run on Mini. Either stand up a real lower-ABI Mini
   profile or declare those cores "A30-only" explicitly and stop implying a Mini
   set exists.
2. **Build each core once per ABI; a device set = filter(cores that build ∧ clear
   the device provider ceiling ∧ pass a runtime smoke test) → one package per
   device.** The `version_requirements` screen already yields the first two
   filters (see the C-only / under-ceiling / over-ceiling segmentation above);
   make it emit the actual per-device set instead of an "everything ineligible"
   annotation.
3. **Add the one integrity gate the goal needs: a target runtime smoke test.**
   RetroArch load + libretro core-info + a few frames under QEMU-user (or
   on-device) as the promotion gate. This replaces most of the value the
   compile-transcript NFAs were straining to provide, and it is the difference
   between "we compiled it exactly so" and "it runs on the Mini."
4. **Provenance = source commit + toolchain image ID + artifact hash + libretro
   symbols + version_requirements + runtime-smoke result.** Sufficient to
   reproduce and to decide device fitness; retire the per-compile NFAs and the
   170-hash bundles as gates.

Net: keep the shared build primitive, the device screen, and the hermetic
pinned toolchain/publish-disabled posture. Consolidate the per-core transcript
contracts, the per-pin whole-tree hash bundles, and the per-core workflow/audit
sprawl. Redirect that complexity budget into device-set assembly and a runtime
smoke test — the parts the end goal actually requires and the pipeline currently
lacks.

---

# Core-build migration review: fail-open + tranche consolidation

Sixth pass (2026-07-20). Reviews the consolidation of the two legacy build
models into the individual-core e2e pipeline, the remaining upgrade surface, and
correctness/optimization of the individual builds. Assessment only; no changes.

## The two legacy models being consolidated

1. **Fail-open individual workflows (44 remain).** Pattern (e.g. `build-hatari.yml`):
   `./libretro-build.sh <core> ... || echo "::warning::<arch> build failed"` —
   a failed architecture is masked to a warning and the step *succeeds*; the
   package step then ships whatever built. A core missing an entire ABI — or with
   only its `.info` and no `.so` at all — uploads as a "successful" beta. The
   audit counts this exactly: **88 masked build-failure paths** (44 × 2 ABIs) and
   **40 info-only-package risks**. The e2e migration replaces this with a
   fail-closed contract: build both targets, validate ELF/ABI + libretro exports,
   ZIP only when *all* catalog targets pass. This is the core safety win.
2. **Tranche/aggregate builds (retired).** Grouped multi-core pins
   (`compose-pin-set --core mgba --core gpsp ...`) with parent/child carry-forward
   — one lock spanning several cores. Now replaced by one-core records and frozen
   read-only: 50 path-bound aggregate documents, 4 archived aggregate workflows,
   and `active_aggregate_workflows: 0`. Nothing active builds in tranches anymore.

## Upgrade ladder — what remains (54 cataloged + 44 uncataloged)

Provenance completeness across the 54 catalog cores: **52 carry an exact
`source.tree` pin; only `ecwolf` and `gpsp` do not**, and only `gpsp` still uses
the resolver `platforms` default. Green registry/boundary tests confirm no
orphan or mismatched contract wiring; `targets` is a list on all 54; duplicate
source commits (vice_x64/xvic, snes9x2005/plus) are legitimate shared-upstream
pairs.

- **40 canonical** — fully migrated: hardened contract + tree pin + compatibility
  manifest + promoted schema-v2 golden. Done.
- **10 legacy-bridge** — cataloged and shared-pipeline, but golden evidence still
  bridges to the schema-v1 aggregate `golden-start.json`; no compatibility
  manifest. Three tiers:
  - **Ready to promote (4): `mgba`, `uzem`, `freeintv`, `vemulator`.** Already have
    hardened contracts (800–933 lines each) + tree + source_key. They need only a
    compatibility manifest + schema-v2 golden promotion. Highest ROI: promoting
    them moves canonical 40→44 and retires four `golden-start.json` dependencies
    with almost no new build work.
  - **Pin-only, no contract (4): `ffmpeg`, `neocd`, `pcsx_rearmed`, `swanstation`.**
    Tree-pinned but no exact-build contract/proof (swanstation is `direct-cmake`
    with a CMake patch but no contract). Need a contract + oracle before promotion.
  - **Weakest (2): `ecwolf`, `gpsp`.** `ecwolf` has no tree pin and no contract.
    `gpsp` is the single least-migrated core — `direct-make`, resolver `platforms`,
    commit-only (no tree), no source_key, no git_version, no contract. Its build is
    the closest surviving relative of the fail-open resolver the migration exists
    to eliminate.
- **4 pending** — `atari800`, `fbneo`, `mame2003_plus`, `picodrive`: cataloged in
  `pending/`, hardened contracts exist, non-admitting; need selected-plus-
  independent reproduction gates before canonical pins.
- **44 uncataloged legacy** — the fail-open workflows above; not migrated at all.
  Each needs a catalog entry + contract + compatibility record + shared-pipeline
  workflow (the standard per-core migration).

## Correctness / optimization findings for the individual builds

1. **Correct `gpsp` and `ecwolf` provenance (real reproducibility gap).** They are
   the only two cores without a `source.tree` pin, so they are pinned to a commit
   that can be re-tagged rather than to exact content. `gpsp` additionally rides
   the generic `direct-make` + `platforms` resolver with no contract — the same
   non-determinism class the migration was built to close. Tree-pin both; give
   `gpsp` a hardened contract (or at minimum an exact tree + build proof).
2. **Promote the 4 ready contract-bridges next (finish the cheap 40%).** `mgba`,
   `uzem`, `freeintv`, `vemulator` are a manifest + promotion away from canonical.
   Doing these first is the highest value-per-effort and directly advances (3).
3. **Retire `golden-start.json` as a live dependency.** It is the last active tie
   to the tranche model: the 10 bridge cores still validate through it. Once the 4
   ready bridges are promoted and the 6 weaker ones upgraded, no active core
   depends on it and it becomes purely historical alongside the rest of the
   frozen aggregate fixtures — the true completion of the consolidation.
4. **Not defects (do not "fix"):** absent `git_version` on `81`, `freechaf`,
   `mednafen_lynx`/`ngp`/`pce_fast`/`vb`, `o2em` is intentional (native-version or
   no-version cores, documented). Absent `source_key` on `gpsp`/`swanstation` is
   consistent with their non-`libretro-super` drivers.

Net: the fail-open safety consolidation is architecturally done for the migrated
54 (fail-closed e2e, no masking, no partial packages), and the tranche model is
fully retired to history. What remains is finishing the per-core migration —
promote the 4 ready bridges, harden the 6 weak bridges (`gpsp`/`ecwolf` first as
correctness fixes), clear the 4 pending reproduction gates, and migrate the 44
fail-open legacy workflows — after which `golden-start.json` retires and the
catalog is uniformly fail-closed and tree-pinned.

---

# Consolidation & simplification design: the implemented cores

Seventh pass (2026-07-20). Goal: make the already-implemented core contracts and
tests maintainable by a human without AI — reusability, readability, simplicity.
Assessment + design; nothing changed.

## The core problem: one contract pattern expressed two ways

The 54 cores carry ~90,000 lines of contract + test code: ~24k in
`contracts/*.py`, ~35k in `test_contract_*.py`, ~31k in `tests/cores/*.py`. The
same proof is written two completely different ways:

- **Declarative (good):** 27+ cores prove a mixed-language build in ~80–130 lines
  by declaring constants (compile counts, language split, git-version identity,
  link options) and calling the shared `MixedLanguageLogContract` /
  `c_only` helper. `handy.py` is 82 lines.
- **Hand-rolled (the problem):** 18 cores — `uzem`, `vemulator`, `freeintv`,
  `mgba`, `atari800`, `picodrive`, `gearboy`, `gearsystem`, the snes9x2005 pair,
  the vice pair, `fmsx`, `81`, `2048`, `lowresnx`, `potator`, `race`,
  `mednafen_supergrafx` — reimplement the *identical* six-function proof skeleton
  (`_markers_are_exact`, `_compile_and_link_scope_is_exact`,
  `_log_envelope_is_exact`, `_diagnostics_and_version_are_exact`,
  `_allowed_compiler_metadata`, `_build_invocation_metadata_is_allowed`) at
  ~500–930 lines each. That is **8,832 lines** doing what the helper already does
  in ~100; `uzem` and `vemulator` are ~half literally-identical after
  normalization and 100% identical in structure.

A maintainer without AI therefore has to understand the same NFA proof eighteen
separate times, each an 800-line bespoke module. That is the single biggest
readability and simplicity debt in the repo.

## Design: one way to write a contract

Principle — a contract is **data, not code**. A per-core module should be a short
block of named, comment-annotated constants plus one call to a shared factory.
The maintainer learns the shared factory once; every core is a table they can
check against a build log.

1. **Absorb the six hand-rolled functions into the shared helpers as
   parameters.** The reason those 18 cores hand-roll is that the current
   `MixedLanguageLogContract` does not parametrize per-ABI diagnostics, compiler-
   metadata allowances, or the version-marker/psABI-note cases they need. Grow
   the helper to accept those as inputs (allowed-diagnostics table, per-ABI note
   sets, version-marker derivation), then delete the per-core reimplementations.
   Net: ~8,800 lines → ~2,000, and one proof engine instead of eighteen.
2. **Migrate incrementally, one core at a time, suite green each step.** Each
   hand-rolled core already has an adversarial test that pins its exact
   fail-closed behavior; the migration is correct iff the declarative form passes
   the same tests. Low risk, mechanical, independently landable — ideal for the
   no-AI-maintenance goal because the end state is far simpler than today.
3. **Data-drive the adversarial tests.** `test_contract_<core>.py` is huge
   (`uzem` = 1,135 lines for 8 tests) because each hand-builds mutation fixtures.
   Replace with one shared adversarial harness: a table of mutation classes
   (reordered framing, wrapper compiler, extra compile, altered link, response-
   file/shell indirection, setup mutation) applied generically to any contract +
   its canonical passing log. Each core supplies contract + passing log; the
   harness asserts every mutation fails closed. Collapses most of the 35k
   contract-test lines to a harness + per-core data.
4. **Keep the two-file test split but shrink it.** `test_contract_<core>` =
   proof/adversarial (→ shared harness); `tests/cores/test_<core>` = lifecycle
   (catalog/pin/manifest wiring, already ~200 lines). The proof side shrinks
   dramatically once (3) lands.
5. **Generate the lifecycle data files.** compatibility manifest, pin, and
   source-set are uniform data; `scripts/promote_core.py` already composes them
   deterministically. Make generation the norm so no one hand-computes a hash.
6. **Fold one-off split-out modules back in.** e.g. `core_81_diagnostics.py`
   exists only for one core; such one-offs should live in the core's module or
   the shared helper, not as bespoke files a maintainer must discover.

## What the maintainer sees afterward

Adding or fixing a core becomes: edit a ~50–100-line declarative module (counts,
tokens, allowed diagnostics — each a line you can verify against the build log)
and reuse the shared harness. No one reads or writes an 800-line NFA again. The
shared factory + adversarial harness are the *only* things to understand; every
core is data on top of them.

## Sequencing and risk

This is mechanical, incremental, and fully test-guarded (the existing adversarial
tests are the oracle for each migration). It pairs naturally with the tiered
decision: the existing heavy set gets consolidated to one clean pattern, and the
44-core bucket adds mostly light cores, so the maintainer-facing codebase ends up
small and uniform. Recommended order: (1)+(2) helper absorption + per-core
migration first (biggest win), then (3) the adversarial harness, then (5)/(6)
cleanups. Estimated reduction: ~8,800 → ~2,000 contract lines and a large cut in
the 35k contract-test lines, with strictly-preserved fail-closed behavior.

---

# Consolidation rollout: course-correction after uzem + vemulator

Eighth pass (2026-07-20). Implemented the uzem migration (template) and then
inspected vemulator as core #2. A material finding changes how the rest must be
done.

## What shipped

`uzem` migrated to a shared `native_version_envelope.py` engine: 801 -> 442
lines, its exact fail-closed proof preserved (all 8 adversarial mutation tests +
lifecycle + module-boundary tests green; full suite 1143). The engine is the
extracted, parametrized form of uzem's six-function proof.

## The finding: shared function names hid divergent proof logic

The 18 hand-rolled cores share the same six function *names*
(`_markers_are_exact`, `_compile_and_link_scope_is_exact`, `_log_envelope_is_exact`,
...), which is what made them look like one engine. They are not. Their
*positioning logic* genuinely differs:

- **uzem**: compiles must be strictly contiguous, then a single trailing
  diagnostic block, then the link (`[compiles][block][link]`).
- **vemulator**: compiles and multiple diagnostic blocks may be **interspersed**,
  each block placed after its owner compile, together filling one contiguous
  range before the link.
- **gearboy/gearsystem**: a different skeleton again
  (`_command_scope_is_exact` + `_preamble_is_exact`, no diagnostics).
- **mednafen_supergrafx**: ~23 diagnostic constructs; **atari800**: 1,148 lines.

Each core's adversarial tests pin its own strictness, so a single engine cannot
satisfy all of them: uzem's tests require rejecting interspersed diagnostics that
vemulator's tests require accepting. A one-size engine would either fail a
member's tests or degenerate into a per-core mode switch that is *less* readable
than the current modules — defeating the goal.

## Revised approach (test-guarded, per true group)

1. **Group by identical logic, not by function name.** Audit the 18 modules and
   partition them into sets whose positioning/diagnostic logic is actually the
   same. uzem's engine serves uzem's group; each other group gets its own small
   engine (or a deliberately parametrized one) only where members are provably
   identical.
2. **A generalization is valid iff every member's adversarial tests stay green.**
   That is the safety rule: extend an engine to a group only when all members
   pass unchanged. Never relax one core's strictness to fit another.
3. **Expect several small engines, not one.** Likely groups: uzem-style
   contiguous+trailing; vemulator-style interspersed multi-block; gearboy-style
   preamble/no-diagnostics; and the C-only families. Each still removes real
   duplication within its group and gives a maintainer one shape per group.
4. **Keep uzem's engine.** It is correct and cleaner for uzem's model and is the
   foundation for uzem's group once the audit identifies its members; if the
   audit finds uzem is a group of one, fold the engine back inline.

Net: the consolidation is real but finer-grained than "one engine for 18." The
honest unit of work is a per-group logic audit plus a test-guarded engine per
group — careful, multi-session, and safe because each core's adversarial tests
are the oracle. uzem is done and verified; I stopped rather than force vemulator
onto an engine whose strictness it does not share.

---

# Leveling-down rollout: verified template + per-core recipe & map

Ninth pass (2026-07-20). Implemented uzem's leveling-down end to end (verified),
then mapped the remaining 12 cores. The rollout is well-defined but per-core
bespoke; this records the exact recipe and each core's complexity so it can be
finished cleanly (one green core at a time) without re-deriving anything.

## Verified template (uzem)

uzem.py 801->190, test_contract_uzem.py 1135->134, envelope engine deleted; full
suite green; existing golden still validates (compile/link is a subset of the old
envelope). Net ~1,600 lines removed for one core.

## The exact recipe (per core)

1. Rewrite `<core>.py` to the handy shape: keep the spec-identity dict, the
   compile/link constants (compile count, language counts, the four sha256s,
   link options, and `semantic_path_aliases`/`expected_link_language` if the core
   uses them), `SHA256_RE`, and the `*_spec_is_well_formed` / `*_golden_source_*`
   / `*_golden_build_*` functions verbatim. Add `*_mixed_language_contract()`
   that BUILDS the `MixedLanguageLogContract` fresh from the constants (so test
   mocks take effect), and `*_log_proves_contract` that calls
   `mixed_language_log_proves_contract(..., *_mixed_language_contract())`.
   Delete every envelope constant/function and drop `expected_ordered_link_argv_sha256`
   (extra strictness the handy standard omits).
2. Add the core to `_individual_mixed_language_contract` in
   `tests/core_contract_helpers.py`.
3. Replace `test_contract_<core>.py` with the ~130-line handy form (registry
   identity, catalog identity, golden source/build, and the shared-fixture
   dispatch test).
4. Fix `tests/cores/test_<core>.py` where it names a removed envelope constant
   (inline the literal, as done for uzem's `UZEM_NATIVE_VERSION_MARKER`).
5. Keep any identity field the pipeline reads at build time (e.g. `native_makefile`).

## Per-core complexity map (12 remaining)

- **Clean mixed cores — direct recipe:** `gearboy`, `gearsystem`, `core_81`,
  `mednafen_supergrafx`. No `core_pipeline.py` coupling. Each is bespoke only in
  its version model (git-describe, native-space, etc.) and constants.
- **Coupled bridge cores — recipe + wiring care:** `vemulator`, `mgba`,
  `freeintv`. These are legacy-bridge cores whose *historical* golden is
  validated in `core_pipeline.py` (e.g. vemulator at lines ~5455-5462) via
  `*_historical_oracle_log_proves_contract` + `*_historical_recipe_is_well_formed`.
  Level down by making the historical-oracle proof also compile/link (identical
  to the active proof once markers are irrelevant) and KEEP
  `*_historical_recipe_is_well_formed` (it validates a frozen recipe dict, not the
  log). Do not remove the core_pipeline imports/usage.
- **C-only cores — need a shared fixture first:** `race`, `core_2048`,
  `lowresnx`, `potator`, plus the C-only bridge cores `mgba`, `freeintv`,
  `atari800`. There is no `build_c_only_log_fixture`/`_individual_c_only_contract`
  yet, and the c_only declarative test standard (see `test_contract_vecx.py`,
  ~451 lines) is richer than the mixed handy form. Build the shared c_only
  synthetic fixture + dispatch once, then apply the recipe.

## Guardrail

Every core's adversarial + lifecycle tests are the oracle: a leveled-down core is
correct iff its focused tests and the full suite stay green. Do them one green
core at a time. This is careful, security-relevant work best done focused, not
batched fast — which is why uzem was taken all the way through as the proven
reference rather than rushing all 12.
