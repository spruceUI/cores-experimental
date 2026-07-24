# Core pipeline operator guide

This guide covers the local-only core build pipeline in this repository. Run
all commands from the `Cores-spruce` repository root.

For exhaustive entry-script syntax—including every flag combination, runner
environment requirement, input dependency, and per-command `--help` surface—see
the [core pipeline command-line reference](core-pipeline-cli-reference.md).

The pipeline deliberately has no publication command. It may write tracked pin
manifests when you explicitly choose a tracked output path, but builds, evidence,
the content-addressed store, channel pointers, and local releases stay below
`.local-e2e/` unless a command says otherwise.

**Quick map** — this guide is long; jump straight to what you need:
[Prerequisites](#prerequisites) · [Build locally](#build-locally) ·
[Simulate the Actions profile](#simulate-the-github-actions-runner-profile-locally) ·
[Tests and validation](#run-tests-and-validation) ·
[Promote a candidate](#promote-a-passing-candidate-locally) ·
[Channels](#update-local-artifact-channels) ·
[Source lifecycle](#source-commit-lifecycle) ·
[Commit blacklist](#blacklist-a-source-commit) ·
[Final checklist](#final-operator-checklist).
The single most common flow (onboard + promote one core) is condensed in
[`adding-a-new-core.md`](adding-a-new-core.md).

## Terminology

The repository currently has two related lifecycles. Do not confuse them:

- A **source commit** is the full 40-character commit in
  `manifests/core-builds.json` at `cores.<core_id>.source.commit`.
- An **E2E candidate** is a local run of that source for every target listed by
  the core. A passing run contains build records and a package.
- A **build golden** is one architecture from a passing, complete E2E promoted
  into a golden manifest and the local content-addressed store.
- A **pin set** is an immutable package selection. It is the artifact lifecycle's
  `pinned` target.
- A **local release** is an exact-byte materialization of a pin set. It does not
  rebuild or publish anything.
- `nightly`, `pinned`, and `release` are mutable local channel pointers to
  immutable artifacts. They are not independent source-commit fields.

There is currently only one active source-commit field per core. Separate
`pinned_commit`, `release_candidate_commit`, and `release_commit` fields and
commands do **not** exist yet; see [Source commit lifecycle](#source-commit-lifecycle).
Every active lifecycle uses an individual core file and semantic ID. Grouped
names and aggregate chronology were retired on 2026-07-23 and are preserved
only in git history.

## Prerequisites

- Python 3, Git, and Docker must be available.
- Docker must be able to inspect and run `cores-arm64:latest`,
  `cores-armhf:latest`, and `cores-rust:latest` (the direct-cargo
  driver's image) with the exact image IDs declared in
  `manifests/core-builds.json`.
- The portable toolchain archives must match `pins/toolchains/local-cache-v1.json`
  when archive-store validation is requested.
- Use a new run ID for every E2E. The pipeline refuses to reuse an existing run
  directory. New user-supplied local and simulated-Actions IDs must pass the
  reserved historical-name guard (any ID containing `tranche` is rejected).
- Local and simulated-Actions profiles reject `GITHUB_ACTIONS=true`. Run the
  native `github-actions` profile only inside the corresponding workflow job.

Useful preflight checks:

```bash
python3 scripts/core_pipeline.py catalog-check
python3 scripts/core_pipeline.py audit-workflows
python3 scripts/toolchain_archive.py validate-lock
python3 scripts/toolchain_archive.py validate-lock --verify-store
```

The workflow audit checks independent per-core coverage: every catalog core
must own exactly one `.github/workflows/build-<core>.yml`; missing and
uncataloged owners are reported, and each catalog owner must invoke exactly its
own core with the native `github-actions` runner profile. Missing or mis-bound
catalog owners and any active `build-all*.yml` or `build-all*.yaml` aggregate
workflow are errors. The retired aggregate build-all records live only in git history and are
never an active execution surface.
The audit also validates the publication-disabled release coordinator and
reusable worker, including their exact triggers, read-only permissions, pinned
actions, one-worker matrix shape, bounded parallelism, shared CLI calls,
toolchain location, and fan-in-preserving artifact paths.

`--verify-store` is stricter and requires the ignored local archive store. The
build itself also verifies the selected Docker image ID before compiling.

## Build locally

### Build one architecture

Use `build` when diagnosing one core/ABI and no package is needed:

```bash
python3 scripts/core_pipeline.py build \
  --core handy \
  --arch arm64 \
  --output .local-e2e/manual/handy-arm64
```

The command writes a build record, build log, artifact, and metadata beneath the
chosen output directory. Use an output below `.local-e2e/` so local evidence
remains ignored by Git.

### Build and package one complete core

Use `build-core` to build all catalog-declared targets for exactly one core and
create only that core's package:

```bash
python3 scripts/core_pipeline.py build-core \
  --runner-profile local \
  --core handy \
  --run-id local-handy-01
```

Outputs are written below `.local-e2e/runs/local-handy-01/`. The most important
files are:

- `e2e-record.json`
- `handy/arm64/build-record.json`
- `handy/armhf/build-record.json`
- `handy_libretro.zip`, only when the complete target set passes

There is deliberately no `--arch` flag on `build-core`: target selection,
toolchains, source pins, recipes, metadata, overlays, and compatibility
parameters all come from the selected core's catalog entry.

### Run a per-core E2E or architecture diagnostic

`e2e` requires exactly one `--core`. Omit `--arch` for the core's complete,
package-capable target set:

```bash
python3 scripts/core_pipeline.py e2e \
  --runner-profile local \
  --core handy \
  --run-id local-handy-e2e-01 \
  --fail-fast
```

Repeat `--arch` only to select unique architectures enabled by that core. An
explicit set equal to the catalog target set remains package-capable; a proper
subset is a per-core diagnostic run that is intentionally not packaged or
promotable and exits nonzero. Omitted, repeated, or multiple distinct `--core`
arguments are rejected. To exercise another core, start a separate run with a
new run ID.

## Simulate the GitHub Actions runner profile locally

The local Actions profile exercises the same shared Python build/package path
while recording GitHub-Actions-shaped runner evidence:

```bash
python3 scripts/core_pipeline.py e2e \
  --runner-profile github-actions-sim \
  --core handy \
  --run-id actions-sim-handy-01
```

The run ID is mandatory and must start with `actions-sim-`. Persisted runner
evidence identifies the run as profile `github-actions`, mode `simulated`, and
backend `local-docker`.

This is not a general GitHub Actions emulator. It does not execute Actions'
checkout implementation, artifact download, `docker load`, permissions, or YAML
job orchestration. Audit those workflow surfaces separately:

```bash
python3 scripts/core_pipeline.py audit-workflows
```

That audit checks the one-file-per-core workflow inventory, exact core/profile
bindings, absence of active `build-all*.yml` or `build-all*.yaml` aggregate
workflows, and the static safety/shape contract of the release coordinator and
worker. It does not execute either Actions workflow.

Migrated workflows invoke the same E2E implementation with
`--runner-profile github-actions`. That native profile requires exact Actions
environment markers, an exact `GITHUB_WORKSPACE`, a clean tracked checkout,
`GITHUB_SHA` equal to `HEAD`, positive run/attempt IDs, and a run ID of
`actions-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`. Do not fake those variables for
a local simulation; use `github-actions-sim`.

## Run tests and validation

Run the focused tests while changing runner profiles, provenance bundling, or
commit policy:

```bash
python3 -m unittest \
  tests.test_runner_profiles \
  tests.test_runner_evidence \
  tests.test_pipeline_source_bundle \
  tests.test_commit_blacklist
```

Run the core pipeline regression module:

```bash
python3 -m unittest tests.test_core_pipeline
```

Run all unit tests before a checkpoint or lifecycle promotion:

```bash
python3 -m unittest discover -s tests -v
```

Run the focused individual-core evidence and channel tests while changing a
canonical core's records or lifecycle behavior:

```bash
python3 -m unittest \
  tests.test_contract_mednafen_supafaust \
  tests.test_contract_mednafen_vb \
  tests.test_contract_mednafen_ngp \
  tests.test_contract_mednafen_lynx \
  tests.test_contract_mednafen_pce_fast \
  tests.test_contract_mednafen_supergrafx \
  tests.test_contract_mednafen_wswan \
  tests.test_contract_mednafen_pcfx \
  tests.test_contract_pokemini \
  tests.test_contract_gearcoleco \
  tests.test_contract_vice_x64 \
  tests.test_contract_vice_xvic \
  tests.test_contract_fmsx \
  tests.test_contract_bluemsx \
  tests.test_contract_snes9x2005 \
  tests.test_contract_snes9x2005_plus \
  tests.test_contract_cap32 \
  tests.test_contract_crocods \
  tests.test_contract_genesis_plus_gx \
  tests.test_contract_genesis_plus_gx_wide \
  tests.test_contract_o2em \
  tests.test_contract_freechaf \
  tests.test_contract_vecx \
  tests.test_contract_race \
  tests.test_contract_potator \
  tests.test_contract_gearboy \
  tests.test_contract_gearsystem \
  tests.cores.test_handy \
  tests.cores.test_stella2014 \
  tests.cores.test_fceumm \
  tests.cores.test_gambatte \
  tests.cores.test_tgbdual \
  tests.cores.test_quicknes \
  tests.cores.test_nestopia \
  tests.cores.test_a5200 \
  tests.cores.test_prosystem \
  tests.cores.test_snes9x \
  tests.cores.test_mednafen_supafaust \
  tests.cores.test_mednafen_vb \
  tests.cores.test_mednafen_ngp \
  tests.cores.test_mednafen_lynx \
  tests.cores.test_mednafen_pce_fast \
  tests.cores.test_mednafen_supergrafx \
  tests.cores.test_mednafen_wswan \
  tests.cores.test_mednafen_pcfx \
  tests.cores.test_pokemini \
  tests.cores.test_gearcoleco \
  tests.cores.test_vice_x64 \
  tests.cores.test_vice_xvic \
  tests.cores.test_fmsx \
  tests.cores.test_bluemsx \
  tests.cores.test_snes9x2005 \
  tests.cores.test_snes9x2005_plus \
  tests.cores.test_cap32 \
  tests.cores.test_crocods \
  tests.cores.test_genesis_plus_gx \
  tests.cores.test_genesis_plus_gx_wide \
  tests.cores.test_o2em \
  tests.cores.test_freechaf \
  tests.cores.test_vecx \
  tests.cores.test_race \
  tests.cores.test_potator \
  tests.cores.test_gearboy \
  tests.cores.test_gearsystem
```

Also validate the tracked contracts affected by a source or artifact update:

```bash
python3 scripts/core_pipeline.py catalog-check
python3 scripts/core_pipeline.py audit-workflows
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/handy-bc55d462f0b2-c82a2178b4f0.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/stella2014-4a7da82595d2-a7cd8bf6403d.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fceumm-718c5a2e1757-b9cb59f371db.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gambatte-dfc165599f3f-782fa4634494.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/tgbdual-bf816b096f1d-e1aa014fb7ae.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/quicknes-26bb785c9ded-0dfc478cbffd.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/nestopia-b0fd87dd07e3-9570ea287053.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/a5200-23c1ea482afb-26663d9e7f87.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/prosystem-363b6dfbd3e2-245dc2e3516d.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x-185488cd83aa-b7aaac2ae7c1.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearcoleco-112345747c04-02350ee96cf1.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_x64-7946cfa0d377-1085a07760d4.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fmsx-f013e213458e-b015409bc42c.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/bluemsx-5f595c79906f-e600380ac6d7.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/cap32-4abfb8be233b-4f89ee89dec9.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/crocods-87bbb3d9007a-5a44afda913e.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/o2em-e03d3be88f79-a966ff1d0775.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vecx-8f671cc9d737-599c2197e36a.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/lowresnx-35adc1a215e9-bcaea00ea240.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/race-c7810dd7f172-c0ea16475d19.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/potator-227c5f6f3ce7-66e2c96acf38.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/2048-c90437d3c391-e1ff15dd7d6a.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/81-fa7094910d04-22dd2ebacdc6.json
git diff --check
```

`--source-set` is required because the registry has no aggregate default, and
normal `report` accepts exactly one source lock. Pass the new individual
source-set path rather than an example when validating another core revision.
The retired legacy aggregate source sets live only in git history and are
not valid inputs to normal reporting.

## Promote a passing candidate locally

The whole chain below is sequenced by one command,
`scripts/promote_core.py run` (import-golden through compose-lifecycle plus
the final catalog-check); the per-step commands remain the reference for what
it does and for recovering a partial chain:

```bash
python3 scripts/promote_core.py run \
  --core handy \
  --selected-run actions-sim-build-core-handy-w3 \
  --reproduction-run build-core-handy-local-w3 \
  [--refresh] [--caveat "..." ...]
```

`--refresh` re-promotes an already-promoted core. The previous promotion's
pin-set, source-set, and compatibility manifest are renamed aside (never
deleted) and restored on any failure; they are removed only after the whole
chain, catalog-check included, succeeds. A failed refresh therefore cannot
destroy a core's promoted outputs. Caveats are NOT carried over implicitly:
pass the core's caveat set explicitly on every refresh (read it from the
current compatibility document first), or the refreshed document falls back
to the generic caveats.

Three re-promotion invariants learned the hard way:

- **Channel pointers invalidate on every re-promotion.** Goldens and pin-sets
  embed `created_at`, so re-composed documents change bytes even when the
  evidence is identical. After a refresh, re-point all three channels (the old
  pointer is now invalid, so compare-and-swap is impossible: remove the
  pointer file and re-create with `--expect-absent`) and recreate the local
  release when the pin bytes changed.
- **Clean-tree evidence.** Build records snapshot `repository_head` and
  `repository_dirty`; several per-core test files enforce
  `repository_dirty=false` on the bound records. Rebuilds meant for promotion
  must run with a committed, clean tree — and since promotion itself dirties
  tracked pins, a multi-core rebuild must be TWO-PHASE: build every core
  first (builds write only gitignored `.local-e2e` paths, so the tree stays
  clean), then promote every core after.
- **Never edit the catalog or the hashed pipeline bundle mid-batch.** A
  build record binds `catalog_sha256` and the pipeline bundle hash at build
  time; an edit between a core's builds — or between its build and its
  promote — makes the record unpromotable.

Promotion requires a passed, exact-one-core schema-v2 E2E record. Promote each
architecture into an empty slot in the selected golden manifest. Initialize a new, create-only
nightly golden from the sibling SpruceOS checkout first:

```bash
python3 scripts/core_pipeline.py import-golden \
  --core handy \
  --spruceos ../spruceOS \
  --output .local-e2e/nightlies/handy-candidate-02/golden.json
```

The required `--core` and `--output` identify one create-only schema-v2
candidate. Its `core_id` is `handy`, and its `cores` and `build_goldens` maps
each have exactly that one key. The output must have the exact shape
`.local-e2e/nightlies/<core>-candidate-<label>/golden.json`; its candidate ID
must pass the reserved historical-name guard (any ID containing `tranche`
is rejected).

If the imported baseline reports that the selected core has no valid shipped
artifact, review that report before rerunning with `--allow-missing`. The flag
can write incomplete imported evidence, but does not make that evidence valid
promotion evidence or relax the complete E2E promotion contract. Every other
validation failure remains fatal.

Then promote both architecture records:

```bash
python3 scripts/core_pipeline.py promote \
  --golden .local-e2e/nightlies/handy-candidate-02/golden.json \
  --record .local-e2e/runs/actions-sim-build-core-handy-w3/handy/arm64/build-record.json \
  --e2e-record .local-e2e/runs/actions-sim-build-core-handy-w3/e2e-record.json

python3 scripts/core_pipeline.py promote \
  --golden .local-e2e/nightlies/handy-candidate-02/golden.json \
  --record .local-e2e/runs/actions-sim-build-core-handy-w3/handy/armhf/build-record.json \
  --e2e-record .local-e2e/runs/actions-sim-build-core-handy-w3/e2e-record.json
```

`promote` refuses to overwrite an existing core/architecture golden or add a
second core to a working candidate. Start a new candidate golden for every core
and new source/recipe lineage. The singleton imported baseline remains
available for validation. Its `build_goldens.<core>` object starts empty and
acquires only that core's promoted architectures.

After both targets are promoted, derive the semantic ID and canonical paths
without writing anything:

```bash
python3 scripts/core_pipeline.py derive-core-id \
  --core handy \
  --source-golden .local-e2e/nightlies/handy-candidate-02/golden.json
```

The JSON output reports `semantic_id`, `nightly_golden`, `pin_set`, and
`release`. Copy the reported `nightly_golden` path into the create-only
projection command. For the current Handy evidence that is:

```bash
python3 scripts/core_pipeline.py compose-core-golden \
  --core handy \
  --source-golden .local-e2e/nightlies/handy-candidate-02/golden.json \
  --output .local-e2e/nightlies/handy-bc55d462f0b2-c82a2178b4f0/golden.json

python3 scripts/core_pipeline.py validate-golden \
  --golden .local-e2e/nightlies/handy-bc55d462f0b2-c82a2178b4f0/golden.json \
  --verify-store
```

`compose-core-golden` is create-only and rejects a guessed or run-label output
directory. Its source and output each have exactly one `build_goldens` key. Use
the same derive/project sequence for Stella 2014, producing
`.local-e2e/nightlies/stella2014-4a7da82595d2-a7cd8bf6403d/golden.json` from its
promoted working candidate.

Compose one parentless immutable pin for the promoted core. The canonical ID
combines the core ID, the first twelve source-commit characters, and the first
twelve selection-digest characters. This keeps a changed recipe or toolchain
distinct even when it rebuilds the same source commit.

```bash
python3 scripts/core_pipeline.py compose-pin-set \
  --pin-id handy-bc55d462f0b2-c82a2178b4f0 \
  --core handy \
  --source-golden .local-e2e/nightlies/handy-bc55d462f0b2-c82a2178b4f0/golden.json \
  --output pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json

python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json \
  --verify-store \
  --verify-sources
```

Use the same form for Stella 2014:

```bash
python3 scripts/core_pipeline.py compose-pin-set \
  --pin-id stella2014-4a7da82595d2-a7cd8bf6403d \
  --core stella2014 \
  --source-golden .local-e2e/nightlies/stella2014-4a7da82595d2-a7cd8bf6403d/golden.json \
  --output pins/core-sets/stella2014-4a7da82595d2-a7cd8bf6403d.json
```

The current Mednafen Supafaust individual pin is validated independently:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json \
  --verify-store \
  --verify-sources
```

Mednafen Virtual Boy uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json \
  --verify-store \
  --verify-sources
```

Mednafen Lynx uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json \
  --verify-store \
  --verify-sources
```

Mednafen PCE Fast uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json \
  --verify-store \
  --verify-sources
```

Mednafen SuperGrafx uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json \
  --verify-store \
  --verify-sources
```

Mednafen WonderSwan uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json \
  --verify-store \
  --verify-sources
```

Mednafen PC-FX uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json \
  --verify-store \
  --verify-sources
```

PokéMini uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json \
  --verify-store \
  --verify-sources
```

Potator uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/potator-227c5f6f3ce7-66e2c96acf38.json \
  --verify-store \
  --verify-sources
```

Gearboy and Gearsystem use the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/gearboy-36d723ff4410-34b7df6bcf6b.json \
  --verify-store \
  --verify-sources

python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/gearsystem-4f029e43f2d5-0f8b301c259a.json \
  --verify-store \
  --verify-sources
```

GearColeco uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/gearcoleco-112345747c04-02350ee96cf1.json \
  --verify-store \
  --verify-sources
```

VICE x64 uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/vice_x64-7946cfa0d377-1085a07760d4.json \
  --verify-store \
  --verify-sources
```

VICE xvic uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json \
  --verify-store \
  --verify-sources
```

fMSX uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/fmsx-f013e213458e-b015409bc42c.json \
  --verify-store \
  --verify-sources
```

blueMSX uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/bluemsx-5f595c79906f-e600380ac6d7.json \
  --verify-store \
  --verify-sources
```

Snes9x 2005 uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json \
  --verify-store \
  --verify-sources
```

Snes9x 2005 Plus uses its own one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json \
  --verify-store \
  --verify-sources
```

Cap32 uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/cap32-4abfb8be233b-4f89ee89dec9.json \
  --verify-store \
  --verify-sources
```

CrocoDS uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/crocods-87bbb3d9007a-5a44afda913e.json \
  --verify-store \
  --verify-sources
```

Genesis Plus GX uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json \
  --verify-store \
  --verify-sources
```

Genesis Plus GX Wide uses its own one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json \
  --verify-store \
  --verify-sources
```

O2EM uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/o2em-e03d3be88f79-a966ff1d0775.json \
  --verify-store \
  --verify-sources
```

FreeChaF uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json \
  --verify-store \
  --verify-sources
```

VecX uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/vecx-8f671cc9d737-599c2197e36a.json \
  --verify-store \
  --verify-sources
```

LowRes NX uses the same one-core validation form:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/lowresnx-35adc1a215e9-bcaea00ea240.json \
  --verify-store \
  --verify-sources

python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/race-c7810dd7f172-c0ea16475d19.json \
  --verify-store \
  --verify-sources

python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/2048-c90437d3c391-e1ff15dd7d6a.json \
  --verify-store \
  --verify-sources

python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/81-fa7094910d04-22dd2ebacdc6.json \
  --verify-store \
  --verify-sources
```

For another core or revision, use the exact values printed by
`derive-core-id`; never guess or shorten a different digest. New individual
pins have exactly one core in `scope`, no parent, and no retained selection.
Legacy aggregate pins remain readable validation fixtures, but the active
pipeline has no aggregate composition writer.

After each pin exists, create its immutable source lock and one-core source set
as described in
[Immutable source locks and source sets](#immutable-source-locks-and-source-sets-manual-contract).
The current Handy, Stella 2014, FCEUmm, Gambatte, TGB Dual, QuickNES, Nestopia,
A5200, ProSystem, Snes9x, Mednafen Supafaust, Mednafen Virtual Boy, Mednafen
Lynx, Mednafen PCE Fast, Mednafen SuperGrafx, Mednafen WonderSwan, Mednafen
PC-FX, PokéMini, Potator, Gearboy, Gearsystem, GearColeco, VICE x64, VICE xvic,
fMSX,
blueMSX, Snes9x 2005, Snes9x 2005 Plus, Cap32, CrocoDS, Genesis Plus GX,
Genesis Plus GX Wide, O2EM, FreeChaF, VecX, LowRes NX, RACE, 2048, and EightyOne
records demonstrate the resulting paths:

```bash
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/handy-bc55d462f0b2-c82a2178b4f0.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/stella2014-4a7da82595d2-a7cd8bf6403d.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fceumm-718c5a2e1757-b9cb59f371db.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gambatte-dfc165599f3f-782fa4634494.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/tgbdual-bf816b096f1d-e1aa014fb7ae.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/quicknes-26bb785c9ded-0dfc478cbffd.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/nestopia-b0fd87dd07e3-9570ea287053.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/a5200-23c1ea482afb-26663d9e7f87.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/prosystem-363b6dfbd3e2-245dc2e3516d.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x-185488cd83aa-b7aaac2ae7c1.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearcoleco-112345747c04-02350ee96cf1.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_x64-7946cfa0d377-1085a07760d4.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fmsx-f013e213458e-b015409bc42c.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/bluemsx-5f595c79906f-e600380ac6d7.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/cap32-4abfb8be233b-4f89ee89dec9.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/crocods-87bbb3d9007a-5a44afda913e.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/o2em-e03d3be88f79-a966ff1d0775.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vecx-8f671cc9d737-599c2197e36a.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/lowresnx-35adc1a215e9-bcaea00ea240.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/race-c7810dd7f172-c0ea16475d19.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/potator-227c5f6f3ce7-66e2c96acf38.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearboy-36d723ff4410-34b7df6bcf6b.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearsystem-4f029e43f2d5-0f8b301c259a.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/2048-c90437d3c391-e1ff15dd7d6a.json

python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/81-fa7094910d04-22dd2ebacdc6.json
```

That separate registry check—not `core_pipeline.py --verify-sources`—fails
closed when the selected source lacks its exact per-core lock.

Materialize and validate the exact pinned package bytes:

```bash
python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json \
  --output .local-e2e/releases/handy-bc55d462f0b2-c82a2178b4f0

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json \
  --release .local-e2e/releases/handy-bc55d462f0b2-c82a2178b4f0 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/stella2014-4a7da82595d2-a7cd8bf6403d.json \
  --output .local-e2e/releases/stella2014-4a7da82595d2-a7cd8bf6403d

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/stella2014-4a7da82595d2-a7cd8bf6403d.json \
  --release .local-e2e/releases/stella2014-4a7da82595d2-a7cd8bf6403d \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json \
  --output .local-e2e/releases/mednafen_supafaust-2b93c0d7dff5-debb21b70273

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json \
  --release .local-e2e/releases/mednafen_supafaust-2b93c0d7dff5-debb21b70273 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json \
  --output .local-e2e/releases/mednafen_vb-38e7a0ec9ac7-ed193088da99

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json \
  --release .local-e2e/releases/mednafen_vb-38e7a0ec9ac7-ed193088da99 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json \
  --output .local-e2e/releases/mednafen_lynx-fcdefcfb3c11-29e56373f32a

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json \
  --release .local-e2e/releases/mednafen_lynx-fcdefcfb3c11-29e56373f32a \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json \
  --output .local-e2e/releases/mednafen_pce_fast-0bc6c8692834-cdd0e0603032

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json \
  --release .local-e2e/releases/mednafen_pce_fast-0bc6c8692834-cdd0e0603032 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json \
  --output .local-e2e/releases/mednafen_supergrafx-3c6fcd3deded-c84693b9711a

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json \
  --release .local-e2e/releases/mednafen_supergrafx-3c6fcd3deded-c84693b9711a \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json \
  --output .local-e2e/releases/mednafen_wswan-da6d0d9acb8d-da715bbcb6da

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json \
  --release .local-e2e/releases/mednafen_wswan-da6d0d9acb8d-da715bbcb6da \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json \
  --output .local-e2e/releases/mednafen_pcfx-650c30ea2203-1c9309580e68

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json \
  --release .local-e2e/releases/mednafen_pcfx-650c30ea2203-1c9309580e68 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json \
  --output .local-e2e/releases/pokemini-bb009b1379ad-2ecf9f68eb0c

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json \
  --release .local-e2e/releases/pokemini-bb009b1379ad-2ecf9f68eb0c \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/gearcoleco-112345747c04-02350ee96cf1.json \
  --output .local-e2e/releases/gearcoleco-112345747c04-02350ee96cf1

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/gearcoleco-112345747c04-02350ee96cf1.json \
  --release .local-e2e/releases/gearcoleco-112345747c04-02350ee96cf1 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/vice_x64-7946cfa0d377-1085a07760d4.json \
  --output .local-e2e/releases/vice_x64-7946cfa0d377-1085a07760d4

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/vice_x64-7946cfa0d377-1085a07760d4.json \
  --release .local-e2e/releases/vice_x64-7946cfa0d377-1085a07760d4 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json \
  --output .local-e2e/releases/vice_xvic-7946cfa0d377-f1e6abfe933c

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json \
  --release .local-e2e/releases/vice_xvic-7946cfa0d377-f1e6abfe933c \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/fmsx-f013e213458e-b015409bc42c.json \
  --output .local-e2e/releases/fmsx-f013e213458e-b015409bc42c

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/fmsx-f013e213458e-b015409bc42c.json \
  --release .local-e2e/releases/fmsx-f013e213458e-b015409bc42c \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/bluemsx-5f595c79906f-e600380ac6d7.json \
  --output .local-e2e/releases/bluemsx-5f595c79906f-e600380ac6d7

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/bluemsx-5f595c79906f-e600380ac6d7.json \
  --release .local-e2e/releases/bluemsx-5f595c79906f-e600380ac6d7 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json \
  --output .local-e2e/releases/snes9x2005-b60356971fc9-23fbb6c59d54

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json \
  --release .local-e2e/releases/snes9x2005-b60356971fc9-23fbb6c59d54 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json \
  --output .local-e2e/releases/snes9x2005_plus-b60356971fc9-77ca2d085240

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json \
  --release .local-e2e/releases/snes9x2005_plus-b60356971fc9-77ca2d085240 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/cap32-4abfb8be233b-4f89ee89dec9.json \
  --output .local-e2e/releases/cap32-4abfb8be233b-4f89ee89dec9

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/cap32-4abfb8be233b-4f89ee89dec9.json \
  --release .local-e2e/releases/cap32-4abfb8be233b-4f89ee89dec9 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/crocods-87bbb3d9007a-5a44afda913e.json \
  --output .local-e2e/releases/crocods-87bbb3d9007a-5a44afda913e

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/crocods-87bbb3d9007a-5a44afda913e.json \
  --release .local-e2e/releases/crocods-87bbb3d9007a-5a44afda913e \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json \
  --output .local-e2e/releases/genesis_plus_gx-fa4dca561e08-b94a8729a601

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json \
  --release .local-e2e/releases/genesis_plus_gx-fa4dca561e08-b94a8729a601 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json \
  --output .local-e2e/releases/genesis_plus_gx_wide-29d9d104338f-5035640f9981

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json \
  --release .local-e2e/releases/genesis_plus_gx_wide-29d9d104338f-5035640f9981 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/o2em-e03d3be88f79-a966ff1d0775.json \
  --output .local-e2e/releases/o2em-e03d3be88f79-a966ff1d0775

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/o2em-e03d3be88f79-a966ff1d0775.json \
  --release .local-e2e/releases/o2em-e03d3be88f79-a966ff1d0775 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json \
  --output .local-e2e/releases/freechaf-76c7a84f1f7e-3fc6b43191ef

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json \
  --release .local-e2e/releases/freechaf-76c7a84f1f7e-3fc6b43191ef \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/vecx-8f671cc9d737-599c2197e36a.json \
  --output .local-e2e/releases/vecx-8f671cc9d737-599c2197e36a

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/vecx-8f671cc9d737-599c2197e36a.json \
  --release .local-e2e/releases/vecx-8f671cc9d737-599c2197e36a \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/lowresnx-35adc1a215e9-bcaea00ea240.json \
  --output .local-e2e/releases/lowresnx-35adc1a215e9-bcaea00ea240

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/lowresnx-35adc1a215e9-bcaea00ea240.json \
  --release .local-e2e/releases/lowresnx-35adc1a215e9-bcaea00ea240 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/race-c7810dd7f172-c0ea16475d19.json \
  --output .local-e2e/releases/race-c7810dd7f172-c0ea16475d19

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/race-c7810dd7f172-c0ea16475d19.json \
  --release .local-e2e/releases/race-c7810dd7f172-c0ea16475d19 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/potator-227c5f6f3ce7-66e2c96acf38.json \
  --output .local-e2e/releases/potator-227c5f6f3ce7-66e2c96acf38

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/potator-227c5f6f3ce7-66e2c96acf38.json \
  --release .local-e2e/releases/potator-227c5f6f3ce7-66e2c96acf38 \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/gearboy-36d723ff4410-34b7df6bcf6b.json \
  --output .local-e2e/releases/gearboy-36d723ff4410-34b7df6bcf6b

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/gearboy-36d723ff4410-34b7df6bcf6b.json \
  --release .local-e2e/releases/gearboy-36d723ff4410-34b7df6bcf6b \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/gearsystem-4f029e43f2d5-0f8b301c259a.json \
  --output .local-e2e/releases/gearsystem-4f029e43f2d5-0f8b301c259a

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/gearsystem-4f029e43f2d5-0f8b301c259a.json \
  --release .local-e2e/releases/gearsystem-4f029e43f2d5-0f8b301c259a \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/2048-c90437d3c391-e1ff15dd7d6a.json \
  --output .local-e2e/releases/2048-c90437d3c391-e1ff15dd7d6a

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/2048-c90437d3c391-e1ff15dd7d6a.json \
  --release .local-e2e/releases/2048-c90437d3c391-e1ff15dd7d6a \
  --verify-store

python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/81-fa7094910d04-22dd2ebacdc6.json \
  --output .local-e2e/releases/81-fa7094910d04-22dd2ebacdc6

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/81-fa7094910d04-22dd2ebacdc6.json \
  --release .local-e2e/releases/81-fa7094910d04-22dd2ebacdc6 \
  --verify-store
```

`promote-release` refuses an existing destination and never builds, repacks, or
publishes. The source commit is carried transitively through the build record,
golden, pin selection, and release manifest.

## Update local artifact channels

New work uses individual schema-v2 pointers. Create Handy, Stella 2014,
Mednafen Supafaust, Mednafen Virtual Boy, Mednafen Lynx, Mednafen PCE Fast,
Mednafen SuperGrafx, Mednafen WonderSwan, Mednafen PC-FX, PokéMini, Potator,
Gearboy, Gearsystem, GearColeco, VICE x64, VICE xvic,
fMSX, blueMSX, Snes9x 2005,
Snes9x 2005 Plus, Cap32, CrocoDS, Genesis Plus GX, Genesis Plus GX Wide, O2EM,
FreeChaF, VecX, LowRes NX, RACE, 2048, and EightyOne pointers only when their
respective aliases are absent.
Mednafen Virtual Boy, Mednafen Lynx, Mednafen PCE Fast, Mednafen SuperGrafx,
PokéMini, Potator, Gearboy, Gearsystem, GearColeco,
VICE x64, VICE xvic, fMSX, blueMSX, Snes9x 2005, Snes9x 2005 Plus, CrocoDS,
Genesis Plus GX, Genesis Plus GX Wide, LowRes NX, RACE, 2048, and EightyOne show the
complete nightly, pinned, and release sequence; the other examples below show
the pinned state:

```bash
python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core handy \
  --target pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core stella2014 \
  --target pins/core-sets/stella2014-4a7da82595d2-a7cd8bf6403d.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_supafaust \
  --target pins/core-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core mednafen_vb \
  --target .local-e2e/nightlies/mednafen_vb-38e7a0ec9ac7-ed193088da99/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_vb \
  --target pins/core-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core mednafen_vb \
  --target .local-e2e/releases/mednafen_vb-38e7a0ec9ac7-ed193088da99/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core mednafen_lynx \
  --target .local-e2e/nightlies/mednafen_lynx-fcdefcfb3c11-29e56373f32a/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_lynx \
  --target pins/core-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core mednafen_lynx \
  --target .local-e2e/releases/mednafen_lynx-fcdefcfb3c11-29e56373f32a/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core mednafen_pce_fast \
  --target .local-e2e/nightlies/mednafen_pce_fast-0bc6c8692834-cdd0e0603032/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_pce_fast \
  --target pins/core-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core mednafen_pce_fast \
  --target .local-e2e/releases/mednafen_pce_fast-0bc6c8692834-cdd0e0603032/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core mednafen_supergrafx \
  --target .local-e2e/nightlies/mednafen_supergrafx-3c6fcd3deded-c84693b9711a/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_supergrafx \
  --target pins/core-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core mednafen_supergrafx \
  --target .local-e2e/releases/mednafen_supergrafx-3c6fcd3deded-c84693b9711a/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_wswan \
  --target pins/core-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core mednafen_pcfx \
  --target pins/core-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core pokemini \
  --target .local-e2e/nightlies/pokemini-bb009b1379ad-2ecf9f68eb0c/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core pokemini \
  --target pins/core-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core pokemini \
  --target .local-e2e/releases/pokemini-bb009b1379ad-2ecf9f68eb0c/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core gearcoleco \
  --target .local-e2e/nightlies/gearcoleco-112345747c04-02350ee96cf1/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core gearcoleco \
  --target pins/core-sets/gearcoleco-112345747c04-02350ee96cf1.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core gearcoleco \
  --target .local-e2e/releases/gearcoleco-112345747c04-02350ee96cf1/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core vice_x64 \
  --target .local-e2e/nightlies/vice_x64-7946cfa0d377-1085a07760d4/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core vice_x64 \
  --target pins/core-sets/vice_x64-7946cfa0d377-1085a07760d4.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core vice_x64 \
  --target .local-e2e/releases/vice_x64-7946cfa0d377-1085a07760d4/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core vice_xvic \
  --target .local-e2e/nightlies/vice_xvic-7946cfa0d377-f1e6abfe933c/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core vice_xvic \
  --target pins/core-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core vice_xvic \
  --target .local-e2e/releases/vice_xvic-7946cfa0d377-f1e6abfe933c/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core fmsx \
  --target .local-e2e/nightlies/fmsx-f013e213458e-b015409bc42c/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core fmsx \
  --target pins/core-sets/fmsx-f013e213458e-b015409bc42c.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core fmsx \
  --target .local-e2e/releases/fmsx-f013e213458e-b015409bc42c/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core bluemsx \
  --target .local-e2e/nightlies/bluemsx-5f595c79906f-e600380ac6d7/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core bluemsx \
  --target pins/core-sets/bluemsx-5f595c79906f-e600380ac6d7.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core bluemsx \
  --target .local-e2e/releases/bluemsx-5f595c79906f-e600380ac6d7/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core snes9x2005 \
  --target .local-e2e/nightlies/snes9x2005-b60356971fc9-23fbb6c59d54/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core snes9x2005 \
  --target pins/core-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core snes9x2005 \
  --target .local-e2e/releases/snes9x2005-b60356971fc9-23fbb6c59d54/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core snes9x2005_plus \
  --target .local-e2e/nightlies/snes9x2005_plus-b60356971fc9-77ca2d085240/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core snes9x2005_plus \
  --target pins/core-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core snes9x2005_plus \
  --target .local-e2e/releases/snes9x2005_plus-b60356971fc9-77ca2d085240/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core crocods \
  --target .local-e2e/nightlies/crocods-87bbb3d9007a-5a44afda913e/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core crocods \
  --target pins/core-sets/crocods-87bbb3d9007a-5a44afda913e.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core crocods \
  --target .local-e2e/releases/crocods-87bbb3d9007a-5a44afda913e/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core genesis_plus_gx \
  --target .local-e2e/nightlies/genesis_plus_gx-fa4dca561e08-b94a8729a601/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core genesis_plus_gx \
  --target pins/core-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core genesis_plus_gx \
  --target .local-e2e/releases/genesis_plus_gx-fa4dca561e08-b94a8729a601/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core genesis_plus_gx_wide \
  --target .local-e2e/nightlies/genesis_plus_gx_wide-29d9d104338f-5035640f9981/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core genesis_plus_gx_wide \
  --target pins/core-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core genesis_plus_gx_wide \
  --target .local-e2e/releases/genesis_plus_gx_wide-29d9d104338f-5035640f9981/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core o2em \
  --target pins/core-sets/o2em-e03d3be88f79-a966ff1d0775.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core freechaf \
  --target pins/core-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core vecx \
  --target pins/core-sets/vecx-8f671cc9d737-599c2197e36a.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core lowresnx \
  --target .local-e2e/nightlies/lowresnx-35adc1a215e9-bcaea00ea240/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core lowresnx \
  --target pins/core-sets/lowresnx-35adc1a215e9-bcaea00ea240.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core lowresnx \
  --target .local-e2e/releases/lowresnx-35adc1a215e9-bcaea00ea240/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core race \
  --target .local-e2e/nightlies/race-c7810dd7f172-c0ea16475d19/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core race \
  --target pins/core-sets/race-c7810dd7f172-c0ea16475d19.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core race \
  --target .local-e2e/releases/race-c7810dd7f172-c0ea16475d19/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core potator \
  --target .local-e2e/nightlies/potator-227c5f6f3ce7-66e2c96acf38/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core potator \
  --target pins/core-sets/potator-227c5f6f3ce7-66e2c96acf38.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core potator \
  --target .local-e2e/releases/potator-227c5f6f3ce7-66e2c96acf38/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core gearboy \
  --target .local-e2e/nightlies/gearboy-36d723ff4410-34b7df6bcf6b/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core gearboy \
  --target pins/core-sets/gearboy-36d723ff4410-34b7df6bcf6b.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core gearboy \
  --target .local-e2e/releases/gearboy-36d723ff4410-34b7df6bcf6b/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core gearsystem \
  --target .local-e2e/nightlies/gearsystem-4f029e43f2d5-0f8b301c259a/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core gearsystem \
  --target pins/core-sets/gearsystem-4f029e43f2d5-0f8b301c259a.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core gearsystem \
  --target .local-e2e/releases/gearsystem-4f029e43f2d5-0f8b301c259a/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core 2048 \
  --target .local-e2e/nightlies/2048-c90437d3c391-e1ff15dd7d6a/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core 2048 \
  --target pins/core-sets/2048-c90437d3c391-e1ff15dd7d6a.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core 2048 \
  --target .local-e2e/releases/2048-c90437d3c391-e1ff15dd7d6a/release-manifest.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel nightly \
  --core 81 \
  --target .local-e2e/nightlies/81-fa7094910d04-22dd2ebacdc6/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core 81 \
  --target pins/core-sets/81-fa7094910d04-22dd2ebacdc6.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release \
  --core 81 \
  --target .local-e2e/releases/81-fa7094910d04-22dd2ebacdc6/release-manifest.json \
  --expect-absent
```

For an existing channel, first obtain the current pointer hash:

```bash
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned \
  --core handy
```

Then compare-and-swap with the exact reported `pointer_file_sha256`:

```bash
python3 scripts/core_pipeline.py update-channel \
  --channel pinned \
  --core handy \
  --target pins/core-sets/handy-<next-source12>-<next-selection12>.json \
  --expect-current <current-pointer-file-sha256>
```

Use the same namespace and compare-and-swap pattern for the other states:

| Core | Channel | Canonical target example | Pointer |
| --- | --- | --- | --- |
| Handy | `nightly` | `.local-e2e/nightlies/handy-bc55d462f0b2-c82a2178b4f0/golden.json` | `.local-e2e/channels/nightly.handy.json` |
| Handy | `release` | `.local-e2e/releases/handy-bc55d462f0b2-c82a2178b4f0/release-manifest.json` | `.local-e2e/channels/release.handy.json` |
| Stella 2014 | `nightly` | `.local-e2e/nightlies/stella2014-4a7da82595d2-a7cd8bf6403d/golden.json` | `.local-e2e/channels/nightly.stella2014.json` |
| Stella 2014 | `release` | `.local-e2e/releases/stella2014-4a7da82595d2-a7cd8bf6403d/release-manifest.json` | `.local-e2e/channels/release.stella2014.json` |
| QuickNES | `nightly` | `.local-e2e/nightlies/quicknes-26bb785c9ded-0dfc478cbffd/golden.json` | `.local-e2e/channels/nightly.quicknes.json` |
| QuickNES | `release` | `.local-e2e/releases/quicknes-26bb785c9ded-0dfc478cbffd/release-manifest.json` | `.local-e2e/channels/release.quicknes.json` |
| Nestopia | `nightly` | `.local-e2e/nightlies/nestopia-b0fd87dd07e3-9570ea287053/golden.json` | `.local-e2e/channels/nightly.nestopia.json` |
| Nestopia | `pinned` | `pins/core-sets/nestopia-b0fd87dd07e3-9570ea287053.json` | `.local-e2e/channels/pinned.nestopia.json` |
| Nestopia | `release` | `.local-e2e/releases/nestopia-b0fd87dd07e3-9570ea287053/release-manifest.json` | `.local-e2e/channels/release.nestopia.json` |
| A5200 | `nightly` | `.local-e2e/nightlies/a5200-23c1ea482afb-26663d9e7f87/golden.json` | `.local-e2e/channels/nightly.a5200.json` |
| A5200 | `pinned` | `pins/core-sets/a5200-23c1ea482afb-26663d9e7f87.json` | `.local-e2e/channels/pinned.a5200.json` |
| A5200 | `release` | `.local-e2e/releases/a5200-23c1ea482afb-26663d9e7f87/release-manifest.json` | `.local-e2e/channels/release.a5200.json` |
| ProSystem | `nightly` | `.local-e2e/nightlies/prosystem-363b6dfbd3e2-245dc2e3516d/golden.json` | `.local-e2e/channels/nightly.prosystem.json` |
| ProSystem | `pinned` | `pins/core-sets/prosystem-363b6dfbd3e2-245dc2e3516d.json` | `.local-e2e/channels/pinned.prosystem.json` |
| ProSystem | `release` | `.local-e2e/releases/prosystem-363b6dfbd3e2-245dc2e3516d/release-manifest.json` | `.local-e2e/channels/release.prosystem.json` |
| Snes9x | `nightly` | `.local-e2e/nightlies/snes9x-185488cd83aa-b7aaac2ae7c1/golden.json` | `.local-e2e/channels/nightly.snes9x.json` |
| Snes9x | `pinned` | `pins/core-sets/snes9x-185488cd83aa-b7aaac2ae7c1.json` | `.local-e2e/channels/pinned.snes9x.json` |
| Snes9x | `release` | `.local-e2e/releases/snes9x-185488cd83aa-b7aaac2ae7c1/release-manifest.json` | `.local-e2e/channels/release.snes9x.json` |
| Mednafen Supafaust | `nightly` | `.local-e2e/nightlies/mednafen_supafaust-2b93c0d7dff5-debb21b70273/golden.json` | `.local-e2e/channels/nightly.mednafen_supafaust.json` |
| Mednafen Supafaust | `pinned` | `pins/core-sets/mednafen_supafaust-2b93c0d7dff5-debb21b70273.json` | `.local-e2e/channels/pinned.mednafen_supafaust.json` |
| Mednafen Supafaust | `release` | `.local-e2e/releases/mednafen_supafaust-2b93c0d7dff5-debb21b70273/release-manifest.json` | `.local-e2e/channels/release.mednafen_supafaust.json` |
| Mednafen Virtual Boy | `nightly` | `.local-e2e/nightlies/mednafen_vb-38e7a0ec9ac7-ed193088da99/golden.json` | `.local-e2e/channels/nightly.mednafen_vb.json` |
| Mednafen Virtual Boy | `pinned` | `pins/core-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json` | `.local-e2e/channels/pinned.mednafen_vb.json` |
| Mednafen Virtual Boy | `release` | `.local-e2e/releases/mednafen_vb-38e7a0ec9ac7-ed193088da99/release-manifest.json` | `.local-e2e/channels/release.mednafen_vb.json` |
| Mednafen Neo Geo Pocket | `nightly` | `.local-e2e/nightlies/mednafen_ngp-a50d5ac288a8-26b82754fc25/golden.json` | `.local-e2e/channels/nightly.mednafen_ngp.json` |
| Mednafen Neo Geo Pocket | `pinned` | `pins/core-sets/mednafen_ngp-a50d5ac288a8-26b82754fc25.json` | `.local-e2e/channels/pinned.mednafen_ngp.json` |
| Mednafen Neo Geo Pocket | `release` | `.local-e2e/releases/mednafen_ngp-a50d5ac288a8-26b82754fc25/release-manifest.json` | `.local-e2e/channels/release.mednafen_ngp.json` |
| Mednafen Lynx | `nightly` | `.local-e2e/nightlies/mednafen_lynx-fcdefcfb3c11-29e56373f32a/golden.json` | `.local-e2e/channels/nightly.mednafen_lynx.json` |
| Mednafen Lynx | `pinned` | `pins/core-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json` | `.local-e2e/channels/pinned.mednafen_lynx.json` |
| Mednafen Lynx | `release` | `.local-e2e/releases/mednafen_lynx-fcdefcfb3c11-29e56373f32a/release-manifest.json` | `.local-e2e/channels/release.mednafen_lynx.json` |
| Mednafen PCE Fast | `nightly` | `.local-e2e/nightlies/mednafen_pce_fast-0bc6c8692834-cdd0e0603032/golden.json` | `.local-e2e/channels/nightly.mednafen_pce_fast.json` |
| Mednafen PCE Fast | `pinned` | `pins/core-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json` | `.local-e2e/channels/pinned.mednafen_pce_fast.json` |
| Mednafen PCE Fast | `release` | `.local-e2e/releases/mednafen_pce_fast-0bc6c8692834-cdd0e0603032/release-manifest.json` | `.local-e2e/channels/release.mednafen_pce_fast.json` |
| Mednafen SuperGrafx | `nightly` | `.local-e2e/nightlies/mednafen_supergrafx-3c6fcd3deded-c84693b9711a/golden.json` | `.local-e2e/channels/nightly.mednafen_supergrafx.json` |
| Mednafen SuperGrafx | `pinned` | `pins/core-sets/mednafen_supergrafx-3c6fcd3deded-c84693b9711a.json` | `.local-e2e/channels/pinned.mednafen_supergrafx.json` |
| Mednafen SuperGrafx | `release` | `.local-e2e/releases/mednafen_supergrafx-3c6fcd3deded-c84693b9711a/release-manifest.json` | `.local-e2e/channels/release.mednafen_supergrafx.json` |
| Mednafen WonderSwan | `nightly` | `.local-e2e/nightlies/mednafen_wswan-da6d0d9acb8d-da715bbcb6da/golden.json` | `.local-e2e/channels/nightly.mednafen_wswan.json` |
| Mednafen WonderSwan | `pinned` | `pins/core-sets/mednafen_wswan-da6d0d9acb8d-da715bbcb6da.json` | `.local-e2e/channels/pinned.mednafen_wswan.json` |
| Mednafen WonderSwan | `release` | `.local-e2e/releases/mednafen_wswan-da6d0d9acb8d-da715bbcb6da/release-manifest.json` | `.local-e2e/channels/release.mednafen_wswan.json` |
| Mednafen PC-FX | `nightly` | `.local-e2e/nightlies/mednafen_pcfx-650c30ea2203-1c9309580e68/golden.json` | `.local-e2e/channels/nightly.mednafen_pcfx.json` |
| Mednafen PC-FX | `pinned` | `pins/core-sets/mednafen_pcfx-650c30ea2203-1c9309580e68.json` | `.local-e2e/channels/pinned.mednafen_pcfx.json` |
| Mednafen PC-FX | `release` | `.local-e2e/releases/mednafen_pcfx-650c30ea2203-1c9309580e68/release-manifest.json` | `.local-e2e/channels/release.mednafen_pcfx.json` |
| PokéMini | `nightly` | `.local-e2e/nightlies/pokemini-bb009b1379ad-2ecf9f68eb0c/golden.json` | `.local-e2e/channels/nightly.pokemini.json` |
| PokéMini | `pinned` | `pins/core-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json` | `.local-e2e/channels/pinned.pokemini.json` |
| PokéMini | `release` | `.local-e2e/releases/pokemini-bb009b1379ad-2ecf9f68eb0c/release-manifest.json` | `.local-e2e/channels/release.pokemini.json` |
| GearColeco | `nightly` | `.local-e2e/nightlies/gearcoleco-112345747c04-02350ee96cf1/golden.json` | `.local-e2e/channels/nightly.gearcoleco.json` |
| GearColeco | `pinned` | `pins/core-sets/gearcoleco-112345747c04-02350ee96cf1.json` | `.local-e2e/channels/pinned.gearcoleco.json` |
| GearColeco | `release` | `.local-e2e/releases/gearcoleco-112345747c04-02350ee96cf1/release-manifest.json` | `.local-e2e/channels/release.gearcoleco.json` |
| VICE x64 | `nightly` | `.local-e2e/nightlies/vice_x64-7946cfa0d377-1085a07760d4/golden.json` | `.local-e2e/channels/nightly.vice_x64.json` |
| VICE x64 | `pinned` | `pins/core-sets/vice_x64-7946cfa0d377-1085a07760d4.json` | `.local-e2e/channels/pinned.vice_x64.json` |
| VICE x64 | `release` | `.local-e2e/releases/vice_x64-7946cfa0d377-1085a07760d4/release-manifest.json` | `.local-e2e/channels/release.vice_x64.json` |
| VICE xvic | `nightly` | `.local-e2e/nightlies/vice_xvic-7946cfa0d377-f1e6abfe933c/golden.json` | `.local-e2e/channels/nightly.vice_xvic.json` |
| VICE xvic | `pinned` | `pins/core-sets/vice_xvic-7946cfa0d377-f1e6abfe933c.json` | `.local-e2e/channels/pinned.vice_xvic.json` |
| VICE xvic | `release` | `.local-e2e/releases/vice_xvic-7946cfa0d377-f1e6abfe933c/release-manifest.json` | `.local-e2e/channels/release.vice_xvic.json` |
| fMSX | `nightly` | `.local-e2e/nightlies/fmsx-f013e213458e-b015409bc42c/golden.json` | `.local-e2e/channels/nightly.fmsx.json` |
| fMSX | `pinned` | `pins/core-sets/fmsx-f013e213458e-b015409bc42c.json` | `.local-e2e/channels/pinned.fmsx.json` |
| fMSX | `release` | `.local-e2e/releases/fmsx-f013e213458e-b015409bc42c/release-manifest.json` | `.local-e2e/channels/release.fmsx.json` |
| blueMSX | `nightly` | `.local-e2e/nightlies/bluemsx-5f595c79906f-e600380ac6d7/golden.json` | `.local-e2e/channels/nightly.bluemsx.json` |
| blueMSX | `pinned` | `pins/core-sets/bluemsx-5f595c79906f-e600380ac6d7.json` | `.local-e2e/channels/pinned.bluemsx.json` |
| blueMSX | `release` | `.local-e2e/releases/bluemsx-5f595c79906f-e600380ac6d7/release-manifest.json` | `.local-e2e/channels/release.bluemsx.json` |
| Snes9x 2005 | `nightly` | `.local-e2e/nightlies/snes9x2005-b60356971fc9-23fbb6c59d54/golden.json` | `.local-e2e/channels/nightly.snes9x2005.json` |
| Snes9x 2005 | `pinned` | `pins/core-sets/snes9x2005-b60356971fc9-23fbb6c59d54.json` | `.local-e2e/channels/pinned.snes9x2005.json` |
| Snes9x 2005 | `release` | `.local-e2e/releases/snes9x2005-b60356971fc9-23fbb6c59d54/release-manifest.json` | `.local-e2e/channels/release.snes9x2005.json` |
| Snes9x 2005 Plus | `nightly` | `.local-e2e/nightlies/snes9x2005_plus-b60356971fc9-77ca2d085240/golden.json` | `.local-e2e/channels/nightly.snes9x2005_plus.json` |
| Snes9x 2005 Plus | `pinned` | `pins/core-sets/snes9x2005_plus-b60356971fc9-77ca2d085240.json` | `.local-e2e/channels/pinned.snes9x2005_plus.json` |
| Snes9x 2005 Plus | `release` | `.local-e2e/releases/snes9x2005_plus-b60356971fc9-77ca2d085240/release-manifest.json` | `.local-e2e/channels/release.snes9x2005_plus.json` |
| Cap32 | `nightly` | `.local-e2e/nightlies/cap32-4abfb8be233b-4f89ee89dec9/golden.json` | `.local-e2e/channels/nightly.cap32.json` |
| Cap32 | `pinned` | `pins/core-sets/cap32-4abfb8be233b-4f89ee89dec9.json` | `.local-e2e/channels/pinned.cap32.json` |
| Cap32 | `release` | `.local-e2e/releases/cap32-4abfb8be233b-4f89ee89dec9/release-manifest.json` | `.local-e2e/channels/release.cap32.json` |
| CrocoDS | `nightly` | `.local-e2e/nightlies/crocods-87bbb3d9007a-5a44afda913e/golden.json` | `.local-e2e/channels/nightly.crocods.json` |
| CrocoDS | `pinned` | `pins/core-sets/crocods-87bbb3d9007a-5a44afda913e.json` | `.local-e2e/channels/pinned.crocods.json` |
| CrocoDS | `release` | `.local-e2e/releases/crocods-87bbb3d9007a-5a44afda913e/release-manifest.json` | `.local-e2e/channels/release.crocods.json` |
| Genesis Plus GX | `nightly` | `.local-e2e/nightlies/genesis_plus_gx-fa4dca561e08-b94a8729a601/golden.json` | `.local-e2e/channels/nightly.genesis_plus_gx.json` |
| Genesis Plus GX | `pinned` | `pins/core-sets/genesis_plus_gx-fa4dca561e08-b94a8729a601.json` | `.local-e2e/channels/pinned.genesis_plus_gx.json` |
| Genesis Plus GX | `release` | `.local-e2e/releases/genesis_plus_gx-fa4dca561e08-b94a8729a601/release-manifest.json` | `.local-e2e/channels/release.genesis_plus_gx.json` |
| Genesis Plus GX Wide | `nightly` | `.local-e2e/nightlies/genesis_plus_gx_wide-29d9d104338f-5035640f9981/golden.json` | `.local-e2e/channels/nightly.genesis_plus_gx_wide.json` |
| Genesis Plus GX Wide | `pinned` | `pins/core-sets/genesis_plus_gx_wide-29d9d104338f-5035640f9981.json` | `.local-e2e/channels/pinned.genesis_plus_gx_wide.json` |
| Genesis Plus GX Wide | `release` | `.local-e2e/releases/genesis_plus_gx_wide-29d9d104338f-5035640f9981/release-manifest.json` | `.local-e2e/channels/release.genesis_plus_gx_wide.json` |
| O2EM | `nightly` | `.local-e2e/nightlies/o2em-e03d3be88f79-a966ff1d0775/golden.json` | `.local-e2e/channels/nightly.o2em.json` |
| O2EM | `pinned` | `pins/core-sets/o2em-e03d3be88f79-a966ff1d0775.json` | `.local-e2e/channels/pinned.o2em.json` |
| O2EM | `release` | `.local-e2e/releases/o2em-e03d3be88f79-a966ff1d0775/release-manifest.json` | `.local-e2e/channels/release.o2em.json` |
| FreeChaF | `nightly` | `.local-e2e/nightlies/freechaf-76c7a84f1f7e-3fc6b43191ef/golden.json` | `.local-e2e/channels/nightly.freechaf.json` |
| FreeChaF | `pinned` | `pins/core-sets/freechaf-76c7a84f1f7e-3fc6b43191ef.json` | `.local-e2e/channels/pinned.freechaf.json` |
| FreeChaF | `release` | `.local-e2e/releases/freechaf-76c7a84f1f7e-3fc6b43191ef/release-manifest.json` | `.local-e2e/channels/release.freechaf.json` |
| VecX | `nightly` | `.local-e2e/nightlies/vecx-8f671cc9d737-599c2197e36a/golden.json` | `.local-e2e/channels/nightly.vecx.json` |
| VecX | `pinned` | `pins/core-sets/vecx-8f671cc9d737-599c2197e36a.json` | `.local-e2e/channels/pinned.vecx.json` |
| VecX | `release` | `.local-e2e/releases/vecx-8f671cc9d737-599c2197e36a/release-manifest.json` | `.local-e2e/channels/release.vecx.json` |
| LowRes NX | `nightly` | `.local-e2e/nightlies/lowresnx-35adc1a215e9-bcaea00ea240/golden.json` | `.local-e2e/channels/nightly.lowresnx.json` |
| LowRes NX | `pinned` | `pins/core-sets/lowresnx-35adc1a215e9-bcaea00ea240.json` | `.local-e2e/channels/pinned.lowresnx.json` |
| LowRes NX | `release` | `.local-e2e/releases/lowresnx-35adc1a215e9-bcaea00ea240/release-manifest.json` | `.local-e2e/channels/release.lowresnx.json` |
| RACE | `nightly` | `.local-e2e/nightlies/race-c7810dd7f172-c0ea16475d19/golden.json` | `.local-e2e/channels/nightly.race.json` |
| RACE | `pinned` | `pins/core-sets/race-c7810dd7f172-c0ea16475d19.json` | `.local-e2e/channels/pinned.race.json` |
| RACE | `release` | `.local-e2e/releases/race-c7810dd7f172-c0ea16475d19/release-manifest.json` | `.local-e2e/channels/release.race.json` |
| Potator | `nightly` | `.local-e2e/nightlies/potator-227c5f6f3ce7-66e2c96acf38/golden.json` | `.local-e2e/channels/nightly.potator.json` |
| Potator | `pinned` | `pins/core-sets/potator-227c5f6f3ce7-66e2c96acf38.json` | `.local-e2e/channels/pinned.potator.json` |
| Potator | `release` | `.local-e2e/releases/potator-227c5f6f3ce7-66e2c96acf38/release-manifest.json` | `.local-e2e/channels/release.potator.json` |
| Gearboy | `nightly` | `.local-e2e/nightlies/gearboy-36d723ff4410-34b7df6bcf6b/golden.json` | `.local-e2e/channels/nightly.gearboy.json` |
| Gearboy | `pinned` | `pins/core-sets/gearboy-36d723ff4410-34b7df6bcf6b.json` | `.local-e2e/channels/pinned.gearboy.json` |
| Gearboy | `release` | `.local-e2e/releases/gearboy-36d723ff4410-34b7df6bcf6b/release-manifest.json` | `.local-e2e/channels/release.gearboy.json` |
| Gearsystem | `nightly` | `.local-e2e/nightlies/gearsystem-4f029e43f2d5-0f8b301c259a/golden.json` | `.local-e2e/channels/nightly.gearsystem.json` |
| Gearsystem | `pinned` | `pins/core-sets/gearsystem-4f029e43f2d5-0f8b301c259a.json` | `.local-e2e/channels/pinned.gearsystem.json` |
| Gearsystem | `release` | `.local-e2e/releases/gearsystem-4f029e43f2d5-0f8b301c259a/release-manifest.json` | `.local-e2e/channels/release.gearsystem.json` |
| 2048 | `nightly` | `.local-e2e/nightlies/2048-c90437d3c391-e1ff15dd7d6a/golden.json` | `.local-e2e/channels/nightly.2048.json` |
| 2048 | `pinned` | `pins/core-sets/2048-c90437d3c391-e1ff15dd7d6a.json` | `.local-e2e/channels/pinned.2048.json` |
| 2048 | `release` | `.local-e2e/releases/2048-c90437d3c391-e1ff15dd7d6a/release-manifest.json` | `.local-e2e/channels/release.2048.json` |
| EightyOne | `nightly` | `.local-e2e/nightlies/81-fa7094910d04-22dd2ebacdc6/golden.json` | `.local-e2e/channels/nightly.81.json` |
| EightyOne | `pinned` | `pins/core-sets/81-fa7094910d04-22dd2ebacdc6.json` | `.local-e2e/channels/pinned.81.json` |
| EightyOne | `release` | `.local-e2e/releases/81-fa7094910d04-22dd2ebacdc6/release-manifest.json` | `.local-e2e/channels/release.81.json` |

Always pass the same `--core` to `validate-channel` and `update-channel`.
The active CLI has no aggregate channel form; the retired schema-v1 pointer
bytes live only in git history.
A schema-v2 nightly target must contain exactly its named core in both `cores`
and `build_goldens`; an aggregate schema-v1 golden is immutable historical input
and cannot be reused as an active candidate or target. There is no force
update.

## Clean contract-to-E2E transition

When a core has no inherited compatibility row, its exact catalog and build
contract must still be committed before promotable clean-checkout evidence can
exist. Use one temporary individual record at
`manifests/compatibility/pending/<core_id>.json`; never add a new row to the
frozen legacy matrix and never create a placeholder canonical compatibility
record.

The pending record binds the complete catalog core-spec digest, exact source
commit, sorted target set, publication-disabled state, and the required
selected-plus-independent-reproduction E2E gate. Compute its semantic digest
after filling every other field. First derive `core_spec_sha256` from the exact
validated catalog entry:

```bash
python3 - CORE_ID <<'PY'
import json
import sys
from pathlib import Path
from scripts.core_pipeline_lib.records.compatibility_pending import (
    catalog_core_spec_sha256,
)

catalog = json.loads(
    Path("manifests/core-builds.json").read_text(encoding="utf-8")
)
print(catalog_core_spec_sha256(catalog["cores"][sys.argv[1]]))
PY
```

Copy that value into the pending record, then derive `content_sha256`:

```bash
python3 - manifests/compatibility/pending/CORE_ID.json <<'PY'
import json
import sys
from pathlib import Path
from scripts.core_pipeline_lib.records.compatibility_pending import (
    pending_compatibility_content_sha256,
)

path = Path(sys.argv[1])
document = json.loads(path.read_text(encoding="utf-8"))
print(pending_compatibility_content_sha256(document))
PY
```

Run `catalog-check` and the unit suite, then create the clean local contract
checkpoint. After the simulated-Actions and local reproduction runs pass,
remove the pending JSON in the same change that adds the evidence-backed
`manifests/compatibility/<core_id>.json`. `catalog-check` requires exact,
disjoint coverage throughout and reports pending core IDs explicitly. Pending
records are not inputs to promotion, pins, releases, or channels.

The current pending files are `atari800.json`, `fbneo.json`,
`mame2003_plus.json`, and `picodrive.json`. In particular, FBNeo's retained
ARM64 and ARMHF controls are characterization evidence only: they omit the
final wrapper's native version/date marker lines and do not include a selected
or independent shared-pipeline E2E record. Do not promote them by copying their
artifact hashes into a canonical record. Re-run the finalized wrapper, add the
core-owned oracle, and resolve the ARMHF `GLIBCXX_3.4.29` device-provider gate
first.

## Source commit lifecycle

### Implemented now: update the build pin

The build pin is the catalog entry at
`manifests/core-builds.json: cores.<core_id>.source`. Updating it is currently a
manual, reviewed manifest edit; there is no `set-source-pin` command.

For a proposed commit:

1. Resolve and record the exact lowercase 40-character commit, commit tree,
   requested full ref (`refs/heads/...` or `refs/tags/...`), and sorted exact
   submodule gitlinks where applicable.
2. Check the exact `(core_id, source_url, commit)` identity against
   `policies/core-commit-blacklist.json` before editing the catalog.
3. Update `source.commit` and `source.tree`. Update any matching core-specific
   constants in `manifests/core-builds.schema.json`, and review every
   commit-derived recipe input such as `source_date_epoch`, `git_version`,
   patches, overlays, or native version proof; these may also need a new exact
   value.
4. Run `catalog-check`, both-ABI E2E, and an independent reproducibility E2E with
   a new run ID. Compare package and target artifact SHA-256 values.
5. Promote into a new golden/pin/release lineage. Once accepted, add the new
   immutable source lock/source set and create or replace that core's canonical
   `manifests/compatibility/<core_id>.json` record with the actual run and
   artifact evidence. The merged registry lets this canonical file supersede
   the immutable legacy matrix row for the same core. Never edit an older
   immutable source lock, pin set, release, or legacy matrix row to point at the
   new commit; duplicate ownership among canonical compatibility files is
   invalid.

The canonical compatibility record must name distinct run IDs and bind both
E2E semantic digests: `selected_e2e_content_sha256` belongs to an exact
`github-actions/simulated/local-docker` run, while
`reproduction_e2e_content_sha256` belongs to an exact
`local/native/local-docker` run. Do not copy a selected run into a second path
as reproduction evidence. Deep validation reads each recorded log, proves its
digest and compile contract, and checks both runs against the selected pin's
historical content-addressed recipe snapshot; it deliberately does not require
the immutable record to match today's catalog or pipeline bytes. When parallel
compilation changes only log-line ordering, the reproduction build may carry a
different `log_sha256` only if every other build field matches and the complete
line multiset is identical to the selected content-addressed log. Missing,
changed, or extra lines still fail closed.

Mednafen Supafaust is the current core-owned exact-contract example. Its
`mednafen-supafaust-cxx-link-v1` proof requires the exact 44-command C++ compile
set per ABI, `GIT_VERSION="-2b93c0d"` on every compile, exact link
objects/options, and complete ordered diagnostic streams while accepting valid
parallel-stream interleaving. Its canonical selected and reproduction evidence
are the individual-core run IDs
`actions-sim-build-core-mednafen_supafaust-w3` and
`build-core-mednafen_supafaust-local-w3`. The semantic pin/source-set ID
`mednafen_supafaust-2b93c0d7dff5-debb21b70273`, compatibility manifest
`manifests/compatibility/mednafen_supafaust.json`, lifecycle test
`tests/cores/test_mednafen_supafaust.py`, and exact-contract test
`tests/test_contract_mednafen_supafaust.py` are likewise individual-core.
New canonical build, pin, manifest, test, channel, and run IDs must remain
owned by exactly one core.

Mednafen Virtual Boy demonstrates the smaller native-version mixed-language
variant. Its `mednafen-vb-mixed-language-v1` proof binds exact native
leading-space version ` 38e7a0e` to all 10 C and three C++ compile commands and
proves the complete ordered 13-object C++ link. ARM64 must contain no compiler,
linker, or process-failure diagnostics. ARMHF admits only its two exact reviewed
GCC psABI notes and rejects every warning, error, fatal diagnostic, or
unexpected note. Its individual selected and reproduction runs are
`actions-sim-build-core-mednafen_vb-w3` and
`build-core-mednafen_vb-local-w3`; its semantic lifecycle ID is
`mednafen_vb-38e7a0ec9ac7-ed193088da99`. Its independent owners are
`pins/core-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json`,
`pins/source-sets/mednafen_vb-38e7a0ec9ac7-ed193088da99.json`,
`manifests/compatibility/mednafen_vb.json`,
`scripts/core_pipeline_lib/contracts/mednafen_vb.py`,
`tests/cores/test_mednafen_vb.py`, and
`tests/test_contract_mednafen_vb.py`. Its local release is
`.local-e2e/releases/mednafen_vb-38e7a0ec9ac7-ed193088da99`; its nightly,
pinned, and release pointers are
`.local-e2e/channels/nightly.mednafen_vb.json`,
`.local-e2e/channels/pinned.mednafen_vb.json`, and
`.local-e2e/channels/release.mednafen_vb.json`. The pipeline remains
publication-disabled, and no device view is eligible until target-runtime
validation covers content, controls, A/V, saves, states, and performance.

Mednafen Neo Geo Pocket demonstrates the larger parallel native-version
mixed-language variant. Its `mednafen-ngp-mixed-language-v1` proof binds exact
native leading-space version ` a50d5ac` across 32 C and five C++ compile
commands, including all 69 raw native-version occurrences, and proves the
complete ordered 37-object C++ link. Both ABIs require the exact three reviewed
missing-braces warnings; ARMHF additionally requires two reviewed GCC 7.1
psABI notes. Parallel compilation may complete the warning and note blocks in
either order, but neither block may be split, changed, or emitted after the
link. Its individual selected and reproduction runs are
`actions-sim-build-core-mednafen_ngp-w3` and
`build-core-mednafen_ngp-local-w3`; its semantic lifecycle ID is
`mednafen_ngp-a50d5ac288a8-26b82754fc25`. Its independent owners are
`pins/core-sets/mednafen_ngp-a50d5ac288a8-26b82754fc25.json`,
`pins/source-sets/mednafen_ngp-a50d5ac288a8-26b82754fc25.json`,
`manifests/compatibility/mednafen_ngp.json`,
`scripts/core_pipeline_lib/contracts/mednafen_ngp.py`,
`tests/cores/test_mednafen_ngp.py`, and
`tests/test_contract_mednafen_ngp.py`. Its local release is
`.local-e2e/releases/mednafen_ngp-a50d5ac288a8-26b82754fc25`; its nightly,
pinned, and release pointers are
`.local-e2e/channels/nightly.mednafen_ngp.json`,
`.local-e2e/channels/pinned.mednafen_ngp.json`, and
`.local-e2e/channels/release.mednafen_ngp.json`. The pipeline remains
publication-disabled, and no device view is eligible until target-runtime
validation covers content, controls, A/V, saves, states, and performance.

Mednafen Lynx demonstrates the C++-scoped native-version mixed-language
variant. Its `mednafen-lynx-mixed-language-v1` proof binds exact native
leading-space version ` fcdefcf` only to the 16 C++ compiles, requires all 13 C
compiles, and proves the complete ordered 29-object C++ link. Each ABI requires
its exact format-truncation warning and associated note. ARMHF additionally
requires two reviewed GCC 7.1 psABI notes; its two complete diagnostic blocks
may appear in either order but may not split, mutate, or cross the link
boundary. Its individual selected and reproduction runs are
`actions-sim-build-core-mednafen_lynx-w3` and
`build-core-mednafen_lynx-local-w3`; its semantic lifecycle ID is
`mednafen_lynx-fcdefcfb3c11-29e56373f32a`. Its independent owners are
`pins/core-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json`,
`pins/source-sets/mednafen_lynx-fcdefcfb3c11-29e56373f32a.json`,
`manifests/compatibility/mednafen_lynx.json`,
`scripts/core_pipeline_lib/contracts/mednafen_lynx.py`,
`tests/cores/test_mednafen_lynx.py`, and
`tests/test_contract_mednafen_lynx.py`. Its local release is
`.local-e2e/releases/mednafen_lynx-fcdefcfb3c11-29e56373f32a`; its nightly,
pinned, and release pointers are
`.local-e2e/channels/nightly.mednafen_lynx.json`,
`.local-e2e/channels/pinned.mednafen_lynx.json`, and
`.local-e2e/channels/release.mednafen_lynx.json`. The pipeline remains
publication-disabled. Required external `lynxboot.img` firmware is not
packaged, and legal/policy review plus content, controls, rotation, A/V, saves,
states, compatibility, frontend integration, and performance remain runtime
gates; no device view is eligible.

Mednafen PCE Fast demonstrates the no-version C-only compile variant. Its
`mednafen-pce-fast-c-only-v1` proof requires exactly 92 C compiles, rejects C++
compiles and every injected or native version token, and proves exact source
and success framing plus the complete ordered 92-object C++ link. Every
warning, note, error, or fatal diagnostic is rejected. Its individual selected
and reproduction runs are `actions-sim-build-core-mednafen_pce_fast-w3` and
`build-core-mednafen_pce_fast-local-w3`; its semantic lifecycle ID is
`mednafen_pce_fast-0bc6c8692834-cdd0e0603032`. Its independent owners are
`pins/core-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json`,
`pins/source-sets/mednafen_pce_fast-0bc6c8692834-cdd0e0603032.json`,
`manifests/compatibility/mednafen_pce_fast.json`,
`scripts/core_pipeline_lib/contracts/mednafen_pce_fast.py`,
`tests/cores/test_mednafen_pce_fast.py`, and
`tests/test_contract_mednafen_pce_fast.py`. Its local release is
`.local-e2e/releases/mednafen_pce_fast-0bc6c8692834-cdd0e0603032`; its nightly,
pinned, and release pointers are
`.local-e2e/channels/nightly.mednafen_pce_fast.json`,
`.local-e2e/channels/pinned.mednafen_pce_fast.json`, and
`.local-e2e/channels/release.mednafen_pce_fast.json`. The pipeline remains
publication-disabled, and no firmware is packaged. PCE-CD requires a legally
supplied system-card BIOS; HuCard and CD loading, controls, A/V, saves, states,
PCE Fast compatibility boundaries, frontend integration, and performance
remain target-runtime gates, so no device view is eligible.

Mednafen WonderSwan demonstrates the native-version mixed-language variant.
Its `mednafen-wswan-mixed-language-v1` proof binds the native leading-space
short hash to all 14 C and one C++ compile commands, proves the complete ordered
15-object C++ link, and requires the exact two reviewed source warnings on both
ABIs plus the reviewed GCC psABI notes only on ARMHF. Its individual selected
and reproduction runs are `actions-sim-build-core-mednafen_wswan-w3` and
`build-core-mednafen_wswan-local-w3`; its semantic lifecycle ID is
`mednafen_wswan-da6d0d9acb8d-da715bbcb6da`. The compatibility owner is
`manifests/compatibility/mednafen_wswan.json`, the lifecycle owner is
`tests/cores/test_mednafen_wswan.py`, and exact build-log proof remains in
`tests/test_contract_mednafen_wswan.py`.

Mednafen PC-FX demonstrates the typed host-specialization portability variant.
Its `mednafen-pcfx-mixed-language-v1` recipe requires `IS_X86=0`; omitting it
allows host-x86 inference to introduce ARM-incompatible x86/SSE paths. The
proof requires all 60 C and 34 C++ compiles, binds native leading-space version
` 650c30e` to the C++ commands only, and proves the complete ordered 94-object
C++ link. Selected and reproduction logs may differ in whole-file order under
parallel compilation, but each per-stream ordering and the complete diagnostic
multiset remain fail-closed. Its individual selected and reproduction runs are
`actions-sim-build-core-mednafen_pcfx-w3` and
`build-core-mednafen_pcfx-local-w3`; its semantic lifecycle ID is
`mednafen_pcfx-650c30ea2203-1c9309580e68`. The compatibility owner is
`manifests/compatibility/mednafen_pcfx.json`, the lifecycle owner is
`tests/cores/test_mednafen_pcfx.py`, and exact build-log proof remains in
`tests/test_contract_mednafen_pcfx.py`.

This PC-FX record is static-build evidence only. Runtime requires a separately
supplied, unbundled `pcfx.rom` BIOS version 1.00 with MD5
`08e36edbea28a017f79f8d4f7ff9b6d7`; the pipeline establishes no redistribution
rights. Resolver metadata reports display version `v0.9.33.3`, while the built
core reports `v0.9.36.5 650c30e`. Provider inspection and target runtime are
still absent, including the ARMHF `GLIBCXX_3.4.29` requirement, so no device
view is eligible and publication remains a human review gate.

PokéMini demonstrates the native-version C-only variant with reviewed
diagnostics. Its `pokemini-c-only-v1` proof binds native leading-space version
` bb009b1` to all 43 C compiles, proves the complete ordered 43-object C link,
and admits exactly five warnings and five associated notes per ABI. Its
individual selected and reproduction runs are
`actions-sim-build-core-pokemini-w3` and `build-core-pokemini-local-w3`; its
semantic lifecycle ID is `pokemini-bb009b1379ad-2ecf9f68eb0c`. The canonical
owners are `pins/core-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json`,
`pins/source-sets/pokemini-bb009b1379ad-2ecf9f68eb0c.json`,
`manifests/compatibility/pokemini.json`, `tests/cores/test_pokemini.py`, and
`tests/test_contract_pokemini.py`.

This PokéMini record is local static-build evidence, and both builds cloned the
pinned source over the network; it is not offline or target-runtime proof.
ARMHF logs reproduce byte for byte. ARM64 whole-log ordering differs through
parallel compilation, but both logs independently pass the exact proof. The
optional unbundled `bios.min`, provider inspection, and target runtime remain
external gates. The reviewed `.eep` path `sprintf` can emit up to 517 bytes
into a 512-byte destination, so its potential overflow remains an unresolved
runtime safety risk and every device view remains ineligible.

GearColeco demonstrates an exact mixed C/C++ build whose reviewed diagnostics
can precede unrelated compile-command echoes under parallel `make`. Its
`gearcoleco-mixed-language-v1` proof binds native version
`1.6.6-11-g1123457` to the one C and all 19 C++ compiles, requires the Processor
compile before its exact seven-warning block, and requires every compile and
that block before the exact C++ link and build-complete marker. The selected
`actions-sim-build-core-gearcoleco-w3` run is
`github-actions/simulated/local-docker` evidence with E2E content SHA-256
`43c20dfc81e417c9c74cb935710c4a50d3e8766ae39b137738e3c7467ddc178b`;
the independent `build-core-gearcoleco-local-w3` run is
`local/native/local-docker` evidence with E2E content SHA-256
`29653ff1ed53ec3a72e604f520d7c9ca0672c2e75370f77c490a0b56752c4a30`.
They reproduce the package, metadata, both ABI artifacts, and both build logs
byte for byte. Its semantic lifecycle ID is
`gearcoleco-112345747c04-02350ee96cf1`, and its pin, source set, compatibility
manifest, lifecycle test, and contract test are each owned by GearColeco alone.

VICE x64 demonstrates the large mixed-language, zero-diagnostic variant. Its
`vice-x64-mixed-language-v1` proof independently parses all 536 C and 28 C++
compiles per ABI, binds native leading-space version ` 7946cfa0d3` to all 564
commands, and proves the exact ordered C++ link and absence of diagnostics. The
selected `actions-sim-build-core-vice_x64-w3` run is
`github-actions/simulated/local-docker` evidence with E2E content SHA-256
`34005d085b8b1df201cc4dec35dd9373a7b3ffc2e60ad96f748952c32c892378`;
the independent `build-core-vice_x64-local-w3` run is
`local/native/local-docker` evidence with E2E content SHA-256
`5c729210b41a25651e8202449616989db00c2591b17394d1b4f27927bd4b6e75`.
They reproduce package
`8c5b764edc945f9cec4b94ca19203eb6919ce1b48d50cbb94ca4d82afc57d437`,
ARM64 artifact
`2ec9bd7e0d9cdf35b43ff5e672c998fee10a79119a151b3f5d5c42f0c2d45121`,
ARMHF artifact
`69061cfb98940f0a66200a214a477fb7545dc1a112018acf5aa02a9d07c0780a`,
and metadata
`4051f9d21e2e22e8268b2c98cde07bfd942d71e135bf0ad455c3c12a7e1fdd23`
byte for byte. Selected ARM64/ARMHF log hashes are respectively
`cdcc3f0aae1dc318fe8494d9c5e351c637b47c31d468bc63a6e59607c5ae31e6`
and `cc98bf37483a1bde358106e4a4a1daa507c61998d7e0a4c760057cf8dbf3f5ee`;
local hashes are
`5308a0af0e00b349295f26e1c6de1c4edc974cda56c0be8d128f335d2649653c`
and `c21870bc3359c293fbc143294ee98a994ed5e4f8b4b02a25f5a96657c690a7a8`.
The different hashes reflect parallel line ordering only: each ABI pair has an
identical complete line multiset and each log independently passes the exact
564-command proof.

Its semantic lifecycle ID is
`vice_x64-7946cfa0d377-1085a07760d4`; the pin, source set, compatibility
manifest, lifecycle test, contract test, release, and channel aliases are owned
by VICE x64 alone. Both fresh runs cloned the pinned source over the network and
used no offline cache, so these records do not prove offline rebuilds. Metadata
advertises display version `3.9`, while the binary identifies
`3.10 7946cfa0d3`. Provider and target-runtime checks remain open, and no device
view is eligible: ARM64 reaches `GLIBC_2.29`, ARMHF reaches `GLIBC_2.7` and
`GLIBCXX_3.4.21`, and C64 content/full-path media, disks, tapes, cartridges,
optional JiffyDOS, saves and states, controls, audio/video pacing, load/unload,
and sustained performance still require device validation.

VICE xvic is the independently owned VIC-20 variant of that large
mixed-language proof. Its `vice-xvic-mixed-language-v1` contract parses exactly
428 C and 10 C++ compiles per ABI, binds native leading-space version
` 7946cfa0d3` to all 438 commands, and proves the exact ordered C++ link and
zero diagnostics. The selected `actions-sim-build-core-vice_xvic-w3` run is
`github-actions/simulated/local-docker` evidence with E2E content SHA-256
`7ceed43317329dab1fd6e0f455c00ba92c882ac37f847276e31f8023a1e9422c`;
the independent `build-core-vice_xvic-local-w3` run is
`local/native/local-docker` evidence with E2E content SHA-256
`1ff6ea3c539445a94945f0350f49c5468e140cfd4f543d52aea7b889df65c972`.
They reproduce package
`9f69e0fda8cfe3275be2570627bfbcbcb0e318fac70057803b8d0e296e99421a`,
ARM64 artifact
`8b3eda61d9c20032fea521ba24f2e97a690eee6cf2447abd2a02e12255907e0a`,
ARMHF artifact
`8bdec5897cd866061a52cb6e7d2f4428e9727692f66b6959c47efbdb5f94e3f5`,
and metadata
`48b23d8971b40aad47efb526b23b8ce11a5f21edd83a4b10fdd0de63a911e571`
byte for byte. Selected ARM64/ARMHF log hashes are respectively
`91fa54cf885deaca74545323f145dc8d8ec93d0b43800381d3709fa95d1865b1`
and `1d0ddc1dde6e9d5caefc8c3841a8cda75bb193b5b55291e5347599e44543c8e5`;
local hashes are
`51fd930d87faa2dcb795bfdce58d7d1f993b4c54317a3b8097621453c25316d1`
and `2b0eef48b5094369af6d859ba9a84e6b9e0be150dbb26f69e63a8530e00b3a78`.
The differing whole-log hashes reflect parallel line ordering only: each ABI
pair has an identical complete line multiset and every log independently
passes the exact 438-command proof.

Its semantic lifecycle ID is
`vice_xvic-7946cfa0d377-f1e6abfe933c`; the pin, source set, compatibility
manifest, lifecycle test, contract test, release, and channel aliases are owned
by VICE xvic alone. Both fresh runs cloned the pinned source over the network
and used no offline cache, so these records do not prove offline rebuilds.
Metadata advertises display version `3.9`, while the binary identifies
`3.10 7946cfa0d3`. Base VIC-20 ROMs are linked into the artifact, but optional
replacement Kernal, BASIC, character-generator, drive, and cartridge firmware
is neither packaged nor covered by redistribution evidence. Provider and
target-runtime checks remain open, and no device view is eligible: ARM64
reaches `GLIBC_2.29`, ARMHF reaches `GLIBC_2.7`, and VIC-20 no-game startup,
full-path programs, cartridges, archives and playlists, disks, tapes,
snapshots, firmware replacement, saves and states, controls, audio/video
pacing, load/unload, the declared NTSC-interlace limitation, and sustained
performance still require device validation.

fMSX demonstrates the unsuppressed, zero-diagnostic C-only variant. Its
`fmsx-c-only-v1` contract proves exactly 31 C compiles per ABI, binds native
leading-space version ` f013e21` to every compile, and requires the exact
ordered C link with no diagnostics or unmarked compiler, linker, or process
failures. The selected `actions-sim-build-core-fmsx-w3` run is
`github-actions/simulated/local-docker` evidence with E2E content SHA-256
`b28d61b162360e702e873b89e469a1f446bc9aeb752e930e82e64e16f688dc8d`;
the independent `build-core-fmsx-local-w3` run is
`local/native/local-docker` evidence with E2E content SHA-256
`f57a53ef3c116eb22e954b0ed7383b74b9a7740737c477ccbe40c7bff059d12b`.
They reproduce package
`71602b060f5ea76847b0f808803a87e0251d1fa990954f8a4f462bda72099e97`,
metadata
`a7b863ff5e75c538ea77dbf3e7a75d1d57f56abad1b2c946dc5d30c7b206bc98`,
ARM64 artifact
`5e72c1e9d7c6afa31cb1396cd700254c589e94a4327ef4cbcc11aa0fff0663f7`,
ARMHF artifact
`738520c499279643a51900bc5360ecbdc323a46fbfc655f4284aa9624908d67f`,
and the corresponding ABI logs byte for byte. The shared ARM64 and ARMHF log
hashes are respectively
`6c91821864091514e6576c409c67353afc0dd9d181075bcb608f76bbbb701878` and
`cc359c1b9073b241c9f91fc650a72a677e68e54af64d7af2cbe4a980eb82dad6`.

Its semantic lifecycle ID is `fmsx-f013e213458e-b015409bc42c`; the pin,
source set, compatibility manifest, lifecycle test, contract test, release,
and channel aliases are owned by fMSX alone. Both fresh runs cloned pristine
commit `f013e213458e06d9df718e4bc4b09d46f88aa899` over the network and used no
offline cache, so the records do not prove offline rebuilding. Resolver
metadata labels the core `Non-commercial`; the root license is a custom,
non-commercial, non-public-domain license, while compiled NukeYKT code is
GPL-2.0-or-later. Public distribution or release therefore remains a human
legal and policy gate. Metadata display version `6.0` also differs from
artifact version `6.0 f013e21`. External firmware is not packaged: MSX1,
MSX2, and the default MSX2+ mode require different BIOS sets, and `DISK.ROM`,
though optional in metadata, becomes mandatory for DSK, FDI, and M3U use.
Metadata says `supports_no_game=false`, while the source advertises no-game
support, accepts null content, and can boot BASIC, so no-content behavior
remains a target-runtime gate rather than an admitted capability. Firmware
discovery, full-path ROM, disk, tape, and playlist loading, disk persistence
and control, saves and states, input, RGB565 50/60 Hz video, 48 kHz mono audio, frontend
integration, compatibility, and sustained performance still require device
validation. No device view is eligible until those checks and the ARM64
`GLIBC_2.17` and ARMHF `GLIBC_2.4`/`GLIBC_2.7` provider requirements pass on
target hardware. The portable artifacts are build-identity-bound only to
`ra64-universal-v1` and `ra32-a30-v1`; all eight device views remain empty and
ineligible.

blueMSX demonstrates the warning-suppressed mixed-language variant. Its
`bluemsx-mixed-language-v1` contract proves exactly 269 compiles per ABI (255 C
and 14 C++), binds native leading-space version ` 5f595c7` to every C compile
and no C++ compile, requires exactly one upstream `-w` on every compile, and
proves the exact ABI-specific invocations and ordered C++ link. The logs emit
no diagnostics and contain no unmarked compiler, linker, or process failures;
because every compile suppresses warnings, this proves suppression consistency,
not warning-free source code. The selected
`actions-sim-build-core-bluemsx-w3` run is
`github-actions/simulated/local-docker` evidence with E2E content SHA-256
`5dc0241fddb63fbbdff33fd9c37cbe223c1a62bdaf8148428f56b75479deb7da`;
the independent `build-core-bluemsx-local-w3` run is
`local/native/local-docker` evidence with E2E content SHA-256
`c41eaadb2f88ff9ab2c633607d7386b022cd7637e97888fec6cb5f98912a5f78`.
They reproduce package
`e54b047c7a6dc5715823fda797dfc67ce1fc47b13748824322321de410083a0d`,
metadata
`e3840e08ff90f8567beedc9f96ee3597d48ea7a568cfd51aadca20850800257e`,
ARM64 artifact
`14f32f0f61aa7a81d6ad34b244d33db0d88420eb132baa660dc48b7f835978bd`,
ARMHF artifact
`604885f77e8cb3b800b4fa881d875af31bb31d66a94d776e1b2e2c4b6d248c3f`,
and both ABI logs byte for byte. The shared ARM64 and ARMHF log hashes are
respectively
`51ec8ba37ef3a8732b089e751d79f11293ae6ac7b92728548618d2166a4faae6`
and `1cca54101935e09492f630a6073c8a82199d40b11b6c4b1790124f46c473ef61`.

Its semantic lifecycle ID is `bluemsx-5f595c79906f-e600380ac6d7`; its
independent owners are
`pins/core-sets/bluemsx-5f595c79906f-e600380ac6d7.json`,
`pins/source-sets/bluemsx-5f595c79906f-e600380ac6d7.json`,
`manifests/compatibility/bluemsx.json`, `tests/cores/test_bluemsx.py`, and
`tests/test_contract_bluemsx.py`, plus its one-core release and channel aliases.
Both fresh runs cloned pristine commit
`5f595c79906ff3379641b5ee8f3796106214a0a4` over the network and used no
offline cache, so the records do not prove offline rebuilding. Resolver
metadata labels the core GPLv2 and display version `SVN`, while the artifact
identifies `git 5f595c7`. The source inventory describes a mixed tree:
blueMSX-authored BSD-style code, compiled GPL-derived openMSX and fMSXSDL
files, zlib code, and files described only as freeware. The package includes
neither license notices nor corresponding source, so public distribution,
source compliance, and system-data redistribution remain human legal and
policy gates.

The package contains no firmware or machine/database data. The source carries
302 candidate system files: six database files and 296 Machine files,
including 93 ROMs. Only nine C-BIOS ROMs have an explicit bundled
redistribution notice; do not copy the other ROMs into a release without a
separate rights review. Runtime requires correctly staged `Machines` and
`Databases` directories and lawful model-specific firmware. The metadata's two
firmware entries are sentinels, not the complete dependency set; default Auto
selection, C-BIOS, ColecoVision, SVI, SEGA, and SunriseIDE discovery all remain
target-runtime gates.

Metadata declares no-game support, full-path loading, disk control, and the
advertised ROM, disk, cassette, and playlist formats. No-game startup requires
a valid frontend system directory; the source fallback is unsafe for null
content. Machine and mapper selection, ten-image M3U handling, disk insertion,
ejection and replacement, save-directory overlays, and same-basename overlay
collisions all require target testing. Serialized states use a fixed 4 MiB
allocation; deterministic replay requires the non-default fixed-epoch RTC
option and still has a documented printer-port DAC state gap. Do not infer
default determinism or state compatibility across revisions, ABIs, models,
media, or options.

Two controller ports, RetroPad, RetroKeyboard, keyboard mapping, the on-screen
keyboard, Coleco mappings, software RGB565 dynamic geometry, PAL/NTSC pacing,
44.1 kHz stereo audio, unload/reload, compatibility, and sustained performance
remain target-runtime gates. Mouse entry points are stubs. ARM64 additionally
requires its AArch64 loader, libc, and libstdc++ providers through
`GLIBC_2.27` and `GLIBCXX_3.4.21`; ARMHF requires libc, libgcc, libm, and
libstdc++ providers through `GLIBC_2.4`, `GCC_3.5`, `CXXABI_ARM_1.3.3`, and
`GLIBCXX_3.4.21`. The artifacts bind only to `ra64-universal-v1` and
`ra32-a30-v1`; all eight device views remain empty and all 16 device entries
remain ineligible.

Snes9x 2005 demonstrates the reviewed-diagnostic C-only variant. Its
`snes9x2005-c-only-v1` contract proves exactly 35 C compiles per ABI, native
version ` b603569` on every compile, the upstream file-origin default
`USE_BLARGG_APU=0`, the exact ABI-specific invocations and ordered C link, and
exactly 12 reviewed array-bounds warnings with 12 related notes. The selected
`actions-sim-build-core-snes9x2005-w3` run has E2E content SHA-256
`44b8c777cf90ff212ee66a015e4e5893622b82bb24aac2935c233a0b428aa72b`;
the independent `build-core-snes9x2005-local-w3` run has E2E content SHA-256
`450d55fc51f954cfcd3d5a3ff86b8f64c127027bf4c29ca0d2190fd957df88c0`.
They reproduce package
`900db7efba34050edac030de8f7d29b96c5b9b1c53b133239723e58df5505fab`,
metadata
`b77d8b7338e11ac85d7e60106ff56579862ec3fc64c2c58c01912537e2e2620c`,
ARM64 artifact
`c6b13597f672643978e3c24e267f5967d24c47a5f4861d8424ca34585ba5bbe9`,
ARMHF artifact
`4f1bc67226079460aee765875a7036747b798424d14dfe077c7b28b43f25a80b`,
and both ABI logs byte for byte.

Its semantic lifecycle ID is
`snes9x2005-b60356971fc9-23fbb6c59d54`. The one-core pin, source set,
compatibility manifest, `tests/cores/test_snes9x2005.py`, contract test, local
release, and three `.local-e2e/channels/<channel>.snes9x2005.json` aliases are
owned by Snes9x 2005 alone. Both builds bind pristine commit
`b60356971fc9caae02cd0853676dced886a08be7` and clone over the network; the
records do not prove offline rebuilding. Cached toolchain images retain
`dockerfile_linkage=unverified-local-cache`, which is a provenance limitation,
not an observed output difference.

Metadata labels the core `Non-commercial`, and the source combines several
license notices with the Snes9x non-commercial restrictions. The package
carries neither that inventory nor corresponding source, so publication stays
a human legal and policy gate. No firmware is declared or packaged. Content
loading, controls, RGB565 PAL/NTSC video, 32040 Hz audio, saves and states,
accuracy, frontend integration, and sustained performance remain target-runtime
gates. The lower-resource `USE_BLARGG_APU=0` choice is build identity, not a
quality claim. ARM64 requires its AArch64 loader and `GLIBC_2.17`; ARMHF
requires libc and libm through `GLIBC_2.7`. The artifacts bind only to
`ra64-universal-v1` and `ra32-a30-v1`; all device views remain ineligible.

Snes9x 2005 Plus is an independent individual-core lifecycle for the more
accurate Blargg APU build. Its `snes9x2005-plus-c-only-v1` contract proves
exactly 33 C compiles per ABI, native version ` b603569` on every compile,
exactly one direct `-DUSE_BLARGG_APU` flag on every compile when selected with
make variable `USE_BLARGG_APU=1`, the exact ABI-specific invocations and
ordered C link, and the reviewed diagnostic streams. ARM64 has 16 warnings and
12 notes, including four Blargg shift warnings; ARMHF has 12 warnings and 12
notes. The selected
`actions-sim-build-core-snes9x2005_plus-w3` run has E2E content SHA-256
`80d9e318f111217fb540e111021614eb7377dda95963f350ecf0fce9ec71a30b`;
the independent `build-core-snes9x2005_plus-local-w3` run has E2E content
SHA-256
`22c975abd21dddb2b2f91020ab5194b2d0a78bcd91040c3648ac739d95f0879d`.
They reproduce package
`4d8ec2e2ea4e28afef66484d82a3eb0370dcccbd0c1285d1d734c8403dce755c`,
metadata, both ABI artifacts, and both reviewed logs byte for byte.

Its semantic lifecycle ID is
`snes9x2005_plus-b60356971fc9-77ca2d085240`. The one-core pin, source set,
compatibility manifest, `tests/cores/test_snes9x2005_plus.py`, contract test,
local release, and three
`.local-e2e/channels/<channel>.snes9x2005_plus.json` aliases belong to Snes9x
2005 Plus alone. It uses the same pristine upstream commit as the base core,
but its source selection and `USE_BLARGG_APU=1` compile identity are not shared
with that core's lifecycle. Both builds clone over the network, so the records
do not prove offline rebuilding; cached toolchain images retain
`dockerfile_linkage=unverified-local-cache`.

Metadata labels the core `Non-commercial`, and its mixed source-license
inventory and missing package notices keep publication behind a human legal
and policy gate. No firmware is declared or packaged. Content and special-chip
compatibility, controls, RGB565 PAL/NTSC video, 32040 Hz audio, saves and
states, frontend integration, and sustained performance and thermals remain
target-runtime gates. State compatibility with the base core is not claimed.
The artifacts bind only to `ra64-universal-v1` and `ra32-a30-v1`; all device
views remain ineligible.

Cap32's `cap32-c-only-v1` admission composes its GNU Make trace proof with an
exact C-only contract: 44 source/object pairs, every ABI-specific compiler
argv, native version ` 4abfb8b`, Makefile lines 485 and 511, normalized and
raw link objects, the ordered C link, an exact success trailer, and zero
warnings or notes. Selected `actions-sim-build-core-cap32-w3` and reproduction
`build-core-cap32-local-w3` runs have E2E content SHA-256
`09ac1fe2f0c2527c00ebccf0696e844fc769447c66ed74fc65368ebd54f6a0ce`
and `c7ac6cddfa06281ef710502b30fc85bbe750b63077a2a7c846f1cf8c69a86081`.
They reproduce package
`be763dbd6017626b588f0385c3a03bf92d9cf705c75fab5ebed34cdc21110953`,
metadata, and both ABI artifacts byte for byte; parallel logs differ only in
complete-line order and have identical line multisets per ABI.

Its semantic lifecycle ID is `cap32-4abfb8be233b-4f89ee89dec9`. The matching
pin, source set, compatibility manifest, local release, three
`.local-e2e/channels/<channel>.cap32.json` aliases, `tests/cores/test_cap32.py`,
and `tests/test_contract_cap32.py` are independently owned. Resolver metadata
advertises GPLv2 and display version `v4.2.0`, while compiled source includes
non-commercial terms and the binary identifies as `4.5.4 4abfb8b HI`; public
distribution remains a human legal/policy gate. Network-only source checkout,
`dockerfile_linkage=unverified-local-cache`, provider availability, CPC/GX4000
content and disk/tape behavior, keyboard/mouse input, controls, A/V pacing,
saves, states, frontend integration, compatibility, and sustained performance
remain unverified. The artifacts bind only to `ra64-universal-v1` and
`ra32-a30-v1`; all device views remain ineligible.

CrocoDS's `crocods-c-only-v1` admission proves exactly 50 C source/object
pairs per ABI, every ABI-specific compiler invocation, native version
` 87bbb3d`, the normalized and raw link-object identities, ordered C link,
binary version marker, and success trailer. ARM64 preserves five exact
diagnostic streams containing nine warnings and seven notes; ARMHF has no
warnings or notes. Selected `actions-sim-build-core-crocods-w3` and
reproduction `build-core-crocods-local-w3` runs have E2E content SHA-256
`ada4c105bcbef9ed6d76a80ee9b197a27f6873176487040a728e22aa0219889c`
and `f69968b50aa2cd6b81625c1c73a4f61b3af8c60eaa35b53f380503b7cce0b9d7`.
They reproduce package
`897c4e8b34ad69f658a025752f4f53eee6275b4a174dd0c42cd807bb3d4dce0b`,
metadata, and both ABI artifacts byte for byte. ARMHF logs are byte-identical;
ARM64 logs differ only in accepted parallel complete-line order and have equal
line multisets.

Its semantic lifecycle ID is `crocods-87bbb3d9007a-5a44afda913e`. The matching
pin, source set, compatibility manifest, local release, three
`.local-e2e/channels/<channel>.crocods.json` aliases,
`tests/cores/test_crocods.py`, and `tests/test_contract_crocods.py` are
independently owned. Resolver metadata reports MIT and display version `v1`,
while compiled source includes GPLv2-or-later headers, bundled zlib terms, and
embedded CPC data without a local provenance record; public distribution
remains a human legal and policy gate. Network-only source checkout,
`dockerfile_linkage=unverified-local-cache`, provider availability, content,
keyboard focus and controls, disk/tape behavior, A/V pacing, saves and states,
frontend integration, compatibility, and sustained performance remain
unverified. The artifacts bind only to `ra64-universal-v1` and
`ra32-a30-v1`; all device views remain ineligible.

Genesis Plus GX's `genesis-plus-gx-c-link-v1` admission proves exactly
117 C source/object pairs per ABI, every ABI-specific compiler invocation,
native version ` fa4dca5`, the complete ordered C link, binary version
`v1.7.4 fa4dca5`, and the success trailer. ARM64 preserves exactly two
reviewed warnings and one note; ARMHF has no warnings or notes. Selected
`actions-sim-build-core-genesis_plus_gx-w3` and reproduction
`build-core-genesis_plus_gx-local-w3` runs have E2E content SHA-256
`ecca27daaf224d55bf1ca0ced78d7fbd91afe8bfd6869016d3a3cf91ccb74574`
and `e33c54915b30cff9a034630c983bd578c908d658ed3e649c71509473325b4d3f`.
They reproduce package
`227202e9cdc04cd896c22401149c46ff282663680ae94d5222a115d3d4af38ac`,
metadata, and both ABI artifacts byte for byte. ARMHF logs are byte-identical;
ARM64 logs differ only in accepted parallel complete-line order and have equal
line multisets.

Its semantic lifecycle ID is
`genesis_plus_gx-fa4dca561e08-b94a8729a601`. The matching pin, source set,
compatibility manifest, local release, three
`.local-e2e/channels/<channel>.genesis_plus_gx.json` aliases,
`tests/cores/test_genesis_plus_gx.py`, and
`tests/test_contract_genesis_plus_gx.py` are independently owned. The
candidate's core-option and BRAM interface differs from the imported Spruce
generation, imported binaries identify as other commits, and no Base/Wide
state-compatibility claim is made. Non-commercial corresponding-source and
notice obligations keep public distribution behind a human legal/policy
gate. Network-only source checkout,
`dockerfile_linkage=unverified-local-cache`, provider availability, content,
BIOS/CD/BRAM and option migration, controls, A/V pacing, saves and states,
frontend integration, compatibility, and sustained performance remain
unverified. The artifacts bind only to `ra64-universal-v1` and
`ra32-a30-v1`; all device views remain ineligible.

Genesis Plus GX Wide's `genesis-plus-gx-wide-c-link-v1` admission proves
exactly 106 C source/object pairs per ABI, every ABI-specific compiler
invocation, native version ` 29d9d10`, the raw and ordered link identities,
and terminal copy/success framing. ARM64 preserves exactly two reviewed
warnings and one note; ARMHF has no diagnostics. Fresh selected
`actions-sim-build-core-genesis_plus_gx_wide-w3` and reproduction
`build-core-genesis_plus_gx_wide-local-w3` runs have E2E content SHA-256
`9fd6fd7cca4cec46d84834d3008164cfd59e687aad30a773a5d2f1ad5ff6419e`
and `f95ab10542bb0a7c73c57a4cae92715dd58af3993cb1e2eb09f8293caeebb19d`.
They reproduce package
`df36ba0750a558a846dc82012d8fe4c33dbd1e97c60d2e88d4ee42ed5efb6eec`,
metadata, both ABI artifacts, and both logs byte for byte.

Its semantic lifecycle ID is
`genesis_plus_gx_wide-29d9d104338f-5035640f9981`. The matching pin, source
set, compatibility manifest, local release, three
`.local-e2e/channels/<channel>.genesis_plus_gx_wide.json` aliases,
`tests/cores/test_genesis_plus_gx_wide.py`, and
`tests/test_contract_genesis_plus_gx_wide.py` are independently owned.
Spruce ships a different ARM64 Wide binary with state signature 1.7.6, no
ARMHF Wide binary, and the candidate uses signature 1.7.7. Wide option and
state migration, Base/Wide compatibility, provider availability, runtime
behavior, and non-commercial corresponding-source obligations remain
fail-closed. The artifacts bind only to `ra64-universal-v1` and
`ra32-a30-v1`; every device view remains ineligible. The historical logs
under `tests/fixtures/per-core-oracles/genesis_plus_gx_wide/`
remain test-only and were not used for promotion.

O2EM demonstrates the native-version variant. Its `o2em-c-only-v1` proof keeps
the catalog free of a synthetic `git_version`, binds upstream's native
leading-space short hash to all 42 C compiles, and proves the exact C link with
no diagnostics or unmarked linker/process failures. Its individual selected
and reproduction runs are `actions-sim-build-core-o2em-w3` and
`build-core-o2em-local-w3`; its semantic lifecycle ID is
`o2em-e03d3be88f79-a966ff1d0775`.

FreeChaF demonstrates the recursive-source native-version variant. Its
`freechaf-c-only-v1` proof binds libretro-common at
`01c6122931a10a7012973054e7067859d2116420`, the native leading-space short
hash on all 25 C compiles, the exact C link, and its one reviewed warning. Its
individual selected and reproduction runs are
`actions-sim-build-core-freechaf-w3` and `build-core-freechaf-local-w3`; its
semantic lifecycle ID is `freechaf-76c7a84f1f7e-3fc6b43191ef`.

VecX demonstrates the software-renderer native-version variant. Its
`vecx-software-c-only-v1` proof requires `HAS_GPU=0`, binds the native
leading-space short hash to all four C compile commands, proves the complete
ordered link command, binds the exact metadata replacement, and rejects
GL-family inputs, GPU objects, diagnostics, and unmarked process failures. Its
individual selected and reproduction runs are
`actions-sim-build-core-vecx-w3` and `build-core-vecx-local-w3`; its semantic
lifecycle ID is `vecx-8f671cc9d737-599c2197e36a`.

LowRes NX demonstrates the larger native-version C-only variant. Its
`lowresnx-c-only-v1` proof binds the upstream leading-space short hash to all
43 C compile commands, the two reviewed source/object orderings, exact
ABI-specific compiler invocations, the ordered link, metadata replacement,
and fail-closed diagnostic set. Its selected and reproduction runs are
`actions-sim-build-core-lowresnx-w3` and `build-core-lowresnx-local-w3`; its
semantic lifecycle ID is `lowresnx-35adc1a215e9-bcaea00ea240`. ARM64 reaches
`GLIBC_2.29`; provider compatibility and target-runtime behavior remain
unverified, so all device views remain ineligible.

RACE demonstrates the native-version C-only Neo Geo Pocket variant. Its
`race-c-only-v1` proof binds source commit
`c7810dd7f172827bfa2004813bc000b13786636b`, the leading-space short hash on
all 27 C compile commands, the exact ordered C link, success framing, and a
zero-diagnostic envelope for both ABIs. The selected
`actions-sim-build-core-race-w3` and independent
`build-core-race-local-w3` runs reproduce package, resolver metadata, both ABI
artifacts, and both logs byte for byte under semantic ID
`race-c7810dd7f172-c0ea16475d19`. `ngpBios.c` is compiled internal source, not
a packaged or required external firmware blob. Publication remains disabled
behind GPLv2 redistribution review. ARMHF requires `GLIBC_2.7`; reset, core
options, unaligned-access behavior, content loading, frontend integration,
provider compatibility, runtime performance, and every device view remain
provisional and unverified.

Mednafen SuperGrafx demonstrates the C++-scoped native-version mixed-language
variant. Its `mednafen-supergrafx-mixed-language-v1` proof binds source commit
`3c6fcd3deded54ebecd69408f108407ac03d11b5`, native version ` 3c6fcd3` on
29 C++ compiles only, all 60 C compiles, the complete ordered 89-object C++
link, and every reviewed diagnostic block after its owning source compile.
Occurrence-aware assignment covers repeated `zlib_codec_init` headers. Selected
`actions-sim-build-core-mednafen_supergrafx-w3` and independent
`build-core-mednafen_supergrafx-local-w3` runs reproduce package, resolver
metadata, and both ABI artifacts byte for byte under semantic ID
`mednafen_supergrafx-3c6fcd3deded-c84693b9711a`; parallel logs differ while
both satisfy the exact proof.

The core-owned `contracts/mednafen_supergrafx.py`, matching one-core pin, source
set, compatibility manifest, local release, three
`.local-e2e/channels/<channel>.mednafen_supergrafx.json` aliases,
`tests/cores/test_mednafen_supergrafx.py`, and
`tests/test_contract_mednafen_supergrafx.py` are independently owned.
Publication remains disabled behind GPLv2 review. No optional PCE-CD BIOS is
packaged; metadata display version `1.23.0` differs from binary version
`1.29.0`; and ARMHF preserves the reviewed free-nonheap warning risk. SGX,
PCE-CD, CHD, provider, target-runtime, and device behavior remain unverified,
so every device view is ineligible.

Potator demonstrates the native-version C-only Watara Supervision variant. Its
`potator-c-only-v1` proof binds source commit
`227c5f6f3ce74d32e9002ce24c1420288559a860`, native version ` 227c5f6` on
all eight C compiles, the complete ordered C link, and exactly four reviewed
misleading-indentation CPU warning/note pairs. Selected
`actions-sim-build-core-potator-w3` and independent
`build-core-potator-local-w3` runs reproduce package, resolver metadata, both
ABI artifacts, and both logs byte for byte under semantic ID
`potator-227c5f6f3ce7-66e2c96acf38`.

The core-owned `contracts/potator.py`, matching one-core pin, source set,
compatibility manifest, local release, three
`.local-e2e/channels/<channel>.potator.json` aliases,
`tests/cores/test_potator.py`, and `tests/test_contract_potator.py` are
independently owned. Resolver metadata declares `Public Domain`; no firmware is
packaged or required; and the four reviewed warnings remain visible rather
than being normalized away. Publication remains disabled, runtime/device
behavior remains unverified, and every device view is ineligible.

Gearboy and Gearsystem demonstrate separate mixed-language, native-version
lifecycles for the two Gearemu cores. Their `gearboy-mixed-language-v1` and
`gearsystem-mixed-language-v1` proofs bind commits
`36d723ff44109e6d9eefba34e1c9a089c2d50e18` and
`4f029e43f2d5207c5da78792503b0fff89b7b2c5`, native describe values
`3.8.9-8-g36d723f` and `3.9.12-5-g4f029e4`, every source/object compile, the
complete ordered C++ links, and zero diagnostics for both ABIs. Their selected
simulated-Actions and independent native-local runs reproduce package,
metadata, artifacts, and logs byte for byte under semantic IDs
`gearboy-36d723ff4410-34b7df6bcf6b` and
`gearsystem-4f029e43f2d5-0f8b301c259a`.

Each core owns its contract, one-core pin and source set, compatibility
manifest, local release, three individual channel aliases, catalog test, and
contract test. Publication remains disabled behind GPLv3 and version-mismatch
review. Optional boot firmware is not packaged, ARMHF provider compatibility
is unproven because the artifacts require `GLIBCXX_3.4.32`, and no target
runtime evidence exists; every device view therefore remains ineligible.

2048 demonstrates the numeric-ID native-version C-only variant. Its numeric-safe
`contracts/core_2048.py` owner and `core-2048-c-only-v1` proof bind the pinned
source tree, upstream leading-space short hash on all 16 C commands, complete
ordered C link, and zero-diagnostic envelope for both ABIs. Its selected and
reproduction runs are `actions-sim-build-core-2048-w3` and
`build-core-2048-local-w3`; its semantic lifecycle ID is
`2048-c90437d3c391-e1ff15dd7d6a`. The source is eight commits newer than the
shipped baseline and its resolver metadata reports no libretro saves despite
an exposed SaveRAM region, so runtime behavior and every device view remain
ineligible pending target evidence.

EightyOne is the numeric-ID native-generated-source variant. Its
`contracts/core_81.py` owner and `core-81-mixed-language-v1` proof bind source
commit `fa7094910d040baa5fd8b11dbf6a1a618330ecd9`, 16 C and 12 C++ compiler
invocations, the ordered C++ link with `build/link.T`, and exact ordered
per-source diagnostic streams for each ABI. Upstream Make must generate
`src/version.c`; the shared pipeline verifies SHA-256
`5a07d38a3bcd84ee5fa9abbdbe0bd706288d8ec4ee8095485447e35dc28a2862`
after the build and records the exact `build.generated_source` identity. Do not
add `git_version`, set `GIT_VERSION`, or patch/generated-copy this file.
The selected `actions-sim-build-core-81-w3` and independent
`build-core-81-local-w3` runs reproduce package, metadata, and both ABI
artifacts exactly under semantic ID `81-fa7094910d04-22dd2ebacdc6`. Their raw
logs differ because parallel Make interleaves the same diagnostics differently;
both pass the strict stream-order NFA, with 39 warnings/6 notes on ARM64 and 38
warnings/11 notes on ARMHF. The failed v1 oracle remains unpromotable. The
canonical state is static-build-only: dependency-floor drift, the resolver
metadata's unescaped inner quotes, provider/runtime behavior, and redistribution
of compiled bundled ROM headers remain explicit human gates. Publication is
disabled and every device view remains ineligible.

Compatibility validation deliberately reapplies the current registered
core-owned proof after checking the immutable selected recipe snapshot. When a
proof changes what evidence is admissible, reproduce and promote a new
individual-core compatibility successor. Preserve the old pin and any frozen
historical fixture as history; do not weaken the current proof to keep a stale
canonical record green.

Compute the compatibility document's semantic digest after filling every other
field, replacing `CORE_ID` with the actual core ID:

```bash
python3 - manifests/compatibility/CORE_ID.json <<'PY'
import json
import sys
from pathlib import Path
from scripts.core_pipeline_lib.records.compatibility import (
    core_compatibility_content_sha256,
)

path = Path(sys.argv[1])
document = json.loads(path.read_text(encoding="utf-8"))
print(core_compatibility_content_sha256(document))
PY
```

Copy that exact value into `content_sha256`, then run the deep repository and
workspace-evidence validator:

```bash
python3 - manifests/compatibility/CORE_ID.json <<'PY'
import json
import sys
from pathlib import Path
from scripts.core_pipeline import validate_core_compatibility_document

path = Path(sys.argv[1])
document = json.loads(path.read_text(encoding="utf-8"))
report = validate_core_compatibility_document(
    document,
    document_path=path,
    repository_root=Path.cwd(),
    verify_pin=True,
)
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if report["status"] == "valid" else 1)
PY
```

This validation requires the selected pin plus both ignored E2E runs and their
content-addressed store evidence. It performs no build and writes nothing.

### Immutable source locks and source sets: manual contract

After the source and complete artifact selection are proven, the repository
currently records them manually as:

- `pins/sources/<core_id>/<commit>.json`, validated by
  `manifests/core-source-lock.schema.json`
- `pins/source-sets/<source-set-id>.json`, validated by
  `manifests/core-source-set.schema.json` and bound to an immutable evidence pin

There is no supported generator or promotion CLI for these files. Follow an
existing recent source lock/source set exactly, create new files rather than
rewriting old ones, and validate the finished source set with:

```bash
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/<source-set-id>.json
```

The per-file `file_sha256` is the SHA-256 of the final referenced file. Source
lock and source-set `content_sha256` values use the current
`scripts.profile_registry.canonical_content_sha256` contract, which excludes
only `$schema` and `content_sha256`. Until a supported writer exists, print the
expected semantic digest for a manually edited document with:

```bash
python3 - pins/sources/<core_id>/<commit>.json <<'PY'
import json
import sys
from pathlib import Path
from scripts.profile_registry import canonical_content_sha256

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(canonical_content_sha256(document))
PY
```

Copy the result into `content_sha256`, then compute the final file digest with
`sha256sum` for the reference in the new source set. Repeat the semantic-digest
step for the source set itself, then run the read-only `profile_registry.py
report` validator above.

### Build and seal a local full-release candidate

Full-release planning is a fan-out/fan-in layer over the individual-core
commands. It does not replace nightly, pinned, or individual local-release
state, and it has no publication command. Start only from a committed, clean
checkout; every fresh worker build must retain that exact `HEAD`.

This two-core canary exercises the complete simulated-Actions path:

```bash
python3 scripts/core_pipeline.py plan-release \
  --candidate-id release-canary-2048-gambatte-v2 \
  --core 2048 \
  --core gambatte \
  --output .local-e2e/release-plans/release-canary-2048-gambatte-v2.json

python3 scripts/core_pipeline.py release-matrix \
  --plan .local-e2e/release-plans/release-canary-2048-gambatte-v2.json

python3 scripts/core_pipeline.py build-core \
  --runner-profile github-actions-sim \
  --core 2048 \
  --run-id actions-sim-release-canary-2048-v2
python3 scripts/core_pipeline.py build-core \
  --runner-profile github-actions-sim \
  --core gambatte \
  --run-id actions-sim-release-canary-gambatte-v2

python3 scripts/core_pipeline.py record-release-result \
  --plan .local-e2e/release-plans/release-canary-2048-gambatte-v2.json \
  --core 2048 \
  --e2e-record .local-e2e/runs/actions-sim-release-canary-2048-v2/e2e-record.json \
  --output-dir .local-e2e/release-results/release-canary-2048-gambatte-v2/github-actions-sim/2048
python3 scripts/core_pipeline.py record-release-result \
  --plan .local-e2e/release-plans/release-canary-2048-gambatte-v2.json \
  --core gambatte \
  --e2e-record .local-e2e/runs/actions-sim-release-canary-gambatte-v2/e2e-record.json \
  --output-dir .local-e2e/release-results/release-canary-2048-gambatte-v2/github-actions-sim/gambatte

python3 scripts/core_pipeline.py seal-release \
  --plan .local-e2e/release-plans/release-canary-2048-gambatte-v2.json \
  --results-root .local-e2e/release-results/release-canary-2048-gambatte-v2/github-actions-sim \
  --runner-profile github-actions-sim \
  --output-dir .local-e2e/release-candidates/release-canary-2048-gambatte-v2/github-actions-sim
```

Repeat the two builds with runner `local`, distinct local run IDs, result root
`.../local/<core>`, and candidate output `.../local`. The two successful
`candidate.json` files must have equal `asset_set_sha256` and equal per-core
package SHA-256/size values. Their `content_sha256` values intentionally differ
because runner evidence is part of the candidate identity.

For the current canonical set, replace the repeated explicit core selectors
with:

```bash
python3 scripts/core_pipeline.py plan-release \
  --candidate-id canonical-static-v2 \
  --scope canonical \
  --output .local-e2e/release-plans/canonical-static-v2.json
python3 scripts/core_pipeline.py release-matrix \
  --plan .local-e2e/release-plans/canonical-static-v2.json
```

Build and record each `include[].core_id` from the compact matrix through an
independent worker, then seal the exact result set. There is deliberately no
pipeline `--all` flag. The publication-disabled Actions coordinator consumes
the same matrix with `fromJSON` and calls one parameterized reusable worker,
rather than calling one unique reusable workflow per core. A local coordinator
should iterate the same output.

`--scope full-workflow-roster` is the final migration gate. It remains expected
to fail with categorized legacy, uncataloged, pending, and non-shared counts
until every discovered workflow has canonical lifecycle state. Do not weaken
that census or reinterpret it as the current canonical subset.

Plan creation reads only tracked files. Each worker deeply validates its fresh
E2E tree and requires package/artifact bytes, clean repository commit, sources,
toolchains, workflow, blacklist, and pipeline identity to match the plan. The
seal reads only portable worker bundles and rejects any incomplete, extra,
tampered, mixed-plan, or mixed-runner fan-in before exposing output.

The release plan is schema v2 because it binds the coordinator and reusable
worker file identities. Its target model and the v1 result/candidate schemas
remain static-build-only: they bind one current evidence cell per architecture
and make no device eligibility claim. A second build profile for the same
architecture requires a later execution-profile-keyed schema rather than an
overloaded architecture target.

### Release-candidate and release source-role commit IDs: planned

The full-release candidate schemas above bind the exact repository `HEAD` and
source commits, but independent source roles named `release-candidate` and
`release` are not yet represented by a source-lifecycle registry. Do not add ad
hoc mutable fields. Until that registry exists, update the individual catalog
build pin, create new immutable evidence, and treat the commit proven by the
pin, source-set, plan, and sealed-candidate lineage as the effective source
identity. Publishing or advancing a public release remains a separate human
gate.

## Blacklist a source commit

The blacklist is `policies/core-commit-blacklist.json`. Entries match the exact
tuple `(core_id, source_url, commit)`; a near match does not block anything.
There is no bypass parameter.

Append an entry with all required fields:

```json
{
  "core_id": "gambatte",
  "source_url": "https://github.com/libretro/gambatte-libretro.git",
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "disposition": "active",
  "reason": "Reproducible compiler regression in this exact source revision.",
  "evidence": [
    ".local-e2e/runs/actions-sim-gambatte-regression-01/e2e-record.json"
  ]
}
```

Requirements:

- `source_url` is a canonical lowercase-host HTTPS Git URL ending in `.git`.
- `commit` is a full lowercase 40-character ID.
- `reason` is nonblank and `evidence` is a nonempty, duplicate-free list.
- One exact identity may appear only once, regardless of disposition.
- `active` blocks current eligibility. `retired` preserves policy history but is
  eligible again.

Check one exact identity without starting a build (replace the three quoted
arguments together):

```bash
python3 - \
  'gambatte' \
  'https://github.com/libretro/gambatte-libretro.git' \
  'dfc165599f3f1068c40a0b7ad6fe5f161283d483' <<'PY'
import sys
from pathlib import Path
from scripts.core_pipeline_lib.policy.blacklist import (
    load_commit_blacklist,
    report_commit_policy,
)

policy = load_commit_blacklist(Path("policies/core-commit-blacklist.json"))
report = report_commit_policy(policy, *sys.argv[1:4])
print(
    f"eligibility={report.current_eligibility}; "
    f"disposition={report.policy_disposition}"
)
raise SystemExit(1 if report.blocked else 0)
PY
```

The blacklist digest covers every field except `content_sha256`, including
`$schema`. After editing entries, print the new value with:

```bash
python3 - policies/core-commit-blacklist.json <<'PY'
import json
import sys
from pathlib import Path
from scripts.core_pipeline_lib.policy.blacklist import commit_blacklist_content_sha256

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(commit_blacklist_content_sha256(document))
PY
```

Copy the result into `content_sha256`, then validate the strict policy document:

```bash
python3 - <<'PY'
from pathlib import Path
from scripts.core_pipeline_lib.policy.blacklist import load_commit_blacklist

policy = load_commit_blacklist(Path("policies/core-commit-blacklist.json"))
print(f"valid: {policy.policy_id}; entries={len(policy.entries)}")
PY
python3 -m unittest tests.test_commit_blacklist
```

The catalog pins the policy file as well as its semantic content. After the
policy validates, obtain its final file digest:

```bash
sha256sum policies/core-commit-blacklist.json
```

Update `manifests/core-builds.json: commit_blacklist.file_sha256` with that
result and `commit_blacklist.content_sha256` with the semantic digest printed
above. Then run `python3 scripts/core_pipeline.py catalog-check`; a stale policy
reference fails closed.

To retire a blacklist entry, change only its `disposition` from `active` to
`retired`, retain its reason and evidence, recompute `content_sha256`, and rerun
the same policy, file-digest, catalog-reference, and validation steps. Do not
delete the entry or add a duplicate retired copy.

There is currently no dedicated `core_pipeline.py blacklist-*` command. The
shared pipeline nevertheless enforces the referenced policy before `build`,
`e2e`, build-golden promotion, pin composition, local release promotion, and
channel updates. Read-only validation of immutable historical evidence does not
erase or rewrite that evidence when a commit is later blacklisted; current
eligibility is a separate admission decision. Keep the explicit policy and
catalog-reference validation in the operator checklist until a dedicated policy
CLI exists.

## Final operator checklist

Before accepting a new local release lineage, require all of the following:

- the proposed source identity is not actively blacklisted
- catalog and workflow audits pass
- complete local and simulated-Actions E2Es pass with distinct run IDs
- the reproducibility runs have matching package and target artifact SHA-256s
- both architecture golden slots are promoted from the same complete E2E
- the new pin passes `--verify-store --verify-sources`
- the local release passes `--verify-store`
- the new source set passes
  `scripts/profile_registry.py report --source-set pins/source-sets/<semantic-id>.json`
- any channel update uses compare-and-swap, never a force write
- no GitHub, deployment, device, or other external mutation occurred
