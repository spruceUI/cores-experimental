# Core pipeline operator guide

This guide covers the local-only core build pipeline in this repository. Run
all commands from the repository root.

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
[Core tracks](core-track-groups.md) ·
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
- `main`, `nightly`, and `edge` are ordered build-pin/deferred policies;
  `stable` and `test` are separate per-track markers. Main is the manually
  selected Spruce stable/Main version level, nightly is the manually selected
  Spruce Development version level, and edge is an exact upstream branch tip
  captured and reviewed at admission. Exact source commits and trees remain
  pinned. Each direct child TEST assignment must satisfy
  `main <= nightly <= edge` against its then-current effective parent by Git
  ancestry or equality and records that parent binding. Later parent movement
  does not retroactively change the child. Only an exact recorded outlier
  authorization may bypass repository/ancestry ordering; a
  same-commit/different-tree inconsistency may never bypass validation. These
  names are separate from the mutable local `nightly` and `pinned` channels
  above.

The immutable `Spruce:main` and `Spruce:Development` artifact bases remain
comparison evidence only. They do not select source revisions and new pins do
not have to reproduce their artifact bytes.

There is currently only one default source-commit field per catalog core.
Track cells do not add mutable `pinned_commit`, `release_candidate_commit`, or
`release_commit` fields. Each effective universal state is either deferred or
references an immutable build pin whose complete execution source can differ
from the catalog default and coexist with other tracks. Deferred groups stop
before build, run-directory, plan, or matrix creation. See
[Core tracks](core-track-groups.md) and
[Source commit lifecycle](#source-commit-lifecycle).
Every active lifecycle uses an individual core file and semantic ID. Grouped
artifact-set names and aggregate chronology were retired on 2026-07-23 and are
preserved only in git history; canonical core-track group tags are a separate
selection layer.

## Prerequisites

- Python 3, Git, and Docker must be available. Install the exact host-side test
  dependencies before running validation:

  ```bash
  python3 -m pip install --requirement requirements-test.txt
  ```

  `jsonschema` 4.19.2 matches the Debian 13 host package and is mandatory
  because the inventory schema test is fail-closed; a missing validator is an
  environment failure, not a skipped test.
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
- New local and simulated-Actions E2Es use the shared
  `host-8c-4g-noswap-v1` execution class: eight jobs/eight CPUs, 4 GiB memory,
  1,024 PIDs, matrix parallelism one, and sequential selected/reproduction
  runs. Docker `MemorySwap=4 GiB` is the total memory-plus-swap limit; because
  it equals `Memory=4 GiB`, usable swap is disabled (`memory.swap.max=0`).
  This initial hardened tranche supports `libretro-super` builds and fails
  closed for unsupported drivers.

Useful preflight checks:

```bash
python3 scripts/core_pipeline.py catalog-check
python3 scripts/core_pipeline.py core-track-inventory --group-tag main-stable:h700
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
remains ignored by Git. This standalone diagnostic path does not create an E2E,
package, or campaign-admissible telemetry record.

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

To reproduce one resolved track variant against its immutable pin, add a group
tag. This preflight runs before the output directory is created:

```bash
python3 scripts/core_pipeline.py build-core \
  --runner-profile local \
  --core mgba \
  --group-tag main-test:a523 \
  --run-id local-mgba-main-test-a523-01
```

The resolved group selects the ABI set and typed tuning, and every selected
artifact plus metadata must match the pin. Do not combine `e2e --group-tag`
with `--arch`. Grouped records are reproduction evidence and are not accepted
by the legacy promotion/release commands.

To create an ordinary proof-bearing pin, run the selected side with the
simulated-Actions selector and then reproduce it locally under the equivalent
resource class:

```bash
python3 scripts/core_pipeline.py e2e \
  --runner-profile github-actions-sim --core handy \
  --run-id actions-sim-handy-selected-01
python3 scripts/core_pipeline.py e2e \
  --runner-profile local --core handy \
  --run-id local-handy-reproduction-01

python3 scripts/core_pipeline.py promote-host-reproduction \
  --core handy \
  --source-golden .local-e2e/nightlies/handy-candidate-host/golden.json \
  --selected-e2e .local-e2e/runs/actions-sim-handy-selected-01/e2e-record.json \
  --reproduction-e2e .local-e2e/runs/local-handy-reproduction-01/e2e-record.json
```

The source golden must be an empty active one-core candidate. Both E2Es are
deep-validated through their content-addressed telemetry, profile, schema,
wrapper, build-record, and output references. Source, selector-neutral recipe,
toolchain, ABI, artifact, metadata, and package bytes must agree exactly;
container IDs, timings, counters, and log bytes may differ. The create-only
promotion writes a new proof-bearing golden and pin and never overwrites the
candidate or an existing result.

To bootstrap a new non-universal tuning pin, run the same current registry
profile twice as separate one-ABI E2Es. Do not use a group tag or architecture
selector for these candidate runs:

```bash
python3 scripts/core_pipeline.py e2e \
  --runner-profile github-actions-sim --core mgba \
  --tuning-profile a523-cortex-a55-v1 \
  --run-id actions-sim-mgba-a523-selected
python3 scripts/core_pipeline.py e2e \
  --runner-profile local --core mgba \
  --tuning-profile a523-cortex-a55-v1 \
  --run-id local-mgba-a523-reproduction
```

Each run must independently prove its typed compiler arguments and core-owned
log contract. The log bytes may differ, but source, recipe, tuning, ABI,
artifact, metadata, and one-ABI ZIP identity must agree exactly. Promote the
pair through the separate fail-closed path:

```bash
python3 scripts/core_pipeline.py promote-tuned-variant \
  --core mgba --tuning-profile a523-cortex-a55-v1 \
  --source-golden .local-e2e/nightlies/mgba-candidate-a523/golden.json \
  --selected-e2e .local-e2e/runs/actions-sim-mgba-a523-selected/e2e-record.json \
  --reproduction-e2e .local-e2e/runs/local-mgba-a523-reproduction/e2e-record.json
```

The source golden must be an empty active one-core candidate. Promotion stores
both proofs, snapshots the tuning registry in the historical recipe, verifies
the complete store, and creates the semantic one-core golden and pin. It does
not edit track policy. First run the read-only planner with the proposed pin,
profile, slice, and applicability. Review its `set_test_arguments`; the
planner and setter share the complete transition engine. Then admit the pin
with the emitted source-registry, direct-cell, new-variant, and parent CAS:

```bash
python3 scripts/core_pipeline.py core-track-plan-test \
  --track nightly --core mgba --chipset a523 \
  --pin-id <promoted-pin-id> --tuning-profile a523-cortex-a55-v1 \
  --slice-time 2026-08-10T12:00:00Z
```

```bash
python3 scripts/core_pipeline.py core-track-set-test \
  --track nightly --core mgba --chipset a523 \
  --pin-id <promoted-pin-id> --tuning-profile a523-cortex-a55-v1 \
  --slice-time 2026-08-10T12:00:00Z \
  --expected-source-registry <reviewed-source-registry-content-sha256> \
  --expected-current-test absent \
  --expected-current-assignment absent \
  --expected-parent-variant <reviewed-main-variant-id> \
  --expected-parent-registry <reviewed-main-registry-content-sha256> \
  --expected-new-variant <reviewed-64-hex-variant-id>
```

To advance an untuned fallback instead, use `--chipset universal`,
`--tuning-profile universal-v1`, and repeat `--applicable-chipset` in sorted
order for each reviewed target chipset. A dual-ABI portable pin can cover both
ARM64 and ARMHF applicability. TEST admission never changes stable state;
approve it later with `core-track-promote` after review.
The slice is immutable assignment/tranche metadata and is excluded from build
variant identity but included in the complete assignment digest. Obtain
`--expected-current-assignment` from the inventory row's direct-coordinate
`current_assignment_content_sha256` (`null` means `absent`). The child
admission captures the exact effective parent registry, selection, slice, and
history and reports its content-addressed binding. Advancing Main later does
not invalidate this Nightly assignment; replacing Nightly performs new parent
variant/registry and direct-assignment CAS checks. Fresh admission requires the
pin's hardened `host_reproduction` proof; tuned and source-candidate promotions
layer that proof automatically when supplied the required hardened pair.

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

Verification has two named tiers. The **local static tier** — the unit
suite, `verify_core.py`, and the per-command validators below — proves in
minutes that every tracked binding is consistent with the promoted disk
evidence. The **roster rebuild tier** — the GitHub Actions
release-candidate workflow — is the only place full from-source rebuild
reproducibility is proven, in hours. Don't duplicate rebuild proof
locally; don't read a green static tier as a rebuild claim.

The host suite consumes the exact versions in `requirements-test.txt`. For an
isolated run of the track and inventory schema tests, build the separate test
image and mount the checkout read-only:

```bash
docker build --file Dockerfile.tests --tag cores-tests .
docker run --rm --volume "$PWD:/workspace:ro" cores-tests
```

This image is test infrastructure only. It is not part of the toolchain lock,
does not build cores, and does not change the arm64, armhf, or Rust compiler
image identities.

Sweep every promoted surface for one core (or `--all` for the catalog):
golden, pin-set (store + sources), source-set registry, release, and all
three channels, discovered from the core id alone:

```bash
python3 scripts/verify_core.py --core handy
python3 scripts/verify_core.py --all
```

Each core's promotion-derived bindings (semantic ID, run IDs, package,
record/log digests, repository state) live in the generated
`pins/evidence/<core>.json`, written by `promote_core.py` at promotion
time and regenerated-and-compared by the suite
(`tests/test_evidence_index.py`) — never hand-edit one.

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
python3 -B -m pytest --import-mode=importlib -p no:cacheprovider tests/ -q
```

Run the focused per-core evidence and contract tests while changing a
canonical core's records or lifecycle behavior — every promoted core has
`tests.cores.test_<core>` and, where it carries a per-core contract,
`tests.test_contract_<core>`:

```bash
python3 -m unittest tests.cores.test_handy tests.test_contract_gearboy
```

Also validate the tracked contracts affected by a source or artifact
update — one `report` per promoted core's current source set (the exact
path is the core's semantic ID under `pins/source-sets/`):

```bash
python3 scripts/core_pipeline.py catalog-check
python3 scripts/core_pipeline.py audit-workflows
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/handy-bc55d462f0b2-c82a2178b4f0.json
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
pin-set and compatibility manifest are renamed aside (never
deleted) and restored on any failure; they are removed only after the whole
chain, catalog-check included, succeeds. A failed refresh therefore cannot
destroy a core's promoted outputs. Caveats are NOT carried over implicitly:
pass the core's caveat set explicitly on every refresh (read it from the
current compatibility document first), or the refreshed document falls back
to the generic caveats.

Three re-promotion invariants learned the hard way — the first two are
now enforced by the tooling itself:

- **Channel pointers invalidate on every re-promotion.** Goldens and pin-sets
  embed `created_at`, so re-composed documents change bytes even when the
  evidence is identical. `run` finishes the promotion automatically:
  it materializes the release, repoints all three channels (falling back
  to remove + `--expect-absent` when the stale pointer no longer
  deep-validates), validates them, and regenerates the core's evidence
  index. Pass `--no-finish` to skip that tail; `--carry-caveats` carries
  the promoted document's extra caveats through a refresh instead of
  retyping each `--caveat`.
- **Clean-tree evidence.** Build records snapshot `repository_head` and
  `repository_dirty`; per-core tests enforce
  `repository_dirty=false` on the bound records. Rebuilds meant for promotion
  must run with a committed, clean tree — and since promotion itself dirties
  tracked pins, a multi-core rebuild must be TWO-PHASE: build every core
  first (builds write only gitignored `.local-e2e` paths, so the tree stays
  clean), then promote every core after. `promote_core.py wave --core …
  --label <label> [--refresh --carry-caveats]` encodes exactly this: it
  refuses a dirty tree, builds every listed core, then promotes and
  finishes each.
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
directory. Its source and output each have exactly one `build_goldens` key. The
same derive/project sequence applies to every core, producing
`.local-e2e/nightlies/<semantic-id>/golden.json` from its promoted working
candidate.

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

Every promoted core is validated with the same one-core form —
substitute the core's semantic ID from `derive-core-id`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/<semantic-id>.json \
  --verify-store \
  --verify-sources
```

For another core or revision, use the exact values printed by
`derive-core-id`; never guess or shorten a different digest. New individual
pins have exactly one core in `scope`, no parent, and no retained selection.
Legacy aggregate pins remain readable validation fixtures, but the active
pipeline has no aggregate composition writer.

The source lock and one-core source set are not files: they are composed in
memory from the catalog and the pin by the single composer
(`scripts/core_pipeline_lib/records/source.py`) — see
[Composed source locks and source sets](#composed-source-locks-and-source-sets).
Validate the composed source set with:

```bash
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/<semantic-id>.json
```

That separate registry check—not `core_pipeline.py --verify-sources`—fails
closed when the selected source lacks its exact per-core lock.

Materialize and validate the exact pinned package bytes (same
parametric form for every promoted core):

```bash
python3 scripts/core_pipeline.py promote-release \
  --pin-set pins/core-sets/<semantic-id>.json \
  --output .local-e2e/releases/<semantic-id>

python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/<semantic-id>.json \
  --release .local-e2e/releases/<semantic-id> \
  --verify-store
```

`promote-release` refuses an existing destination and never builds, repacks, or
publishes. The source commit is carried transitively through the build record,
golden, pin selection, and release manifest.

## Update local artifact channels

**Frozen surface.** The channel layer has no consumer yet — pointers are
maintained automatically by `promote_core.py run`/`wave` and validated
by the suite, and that is all the investment it receives until a
publication consumer exists. Do not extend it; revisit the design when
the publication path is taken up.


New work uses individual schema-v2 pointers, one per core and channel,
at `.local-e2e/channels/<channel>.<core>.json`. Create a pointer with
`--expect-absent` only when the alias is absent; the three channels for
any promoted core take the same parametric form:

```bash
python3 scripts/core_pipeline.py update-channel \
  --channel nightly --core <core> \
  --target .local-e2e/nightlies/<semantic-id>/golden.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel pinned --core <core> \
  --target pins/core-sets/<semantic-id>.json \
  --expect-absent

python3 scripts/core_pipeline.py update-channel \
  --channel release --core <core> \
  --target .local-e2e/releases/<semantic-id>/release-manifest.json \
  --expect-absent
```

After a re-promotion the previous pointers no longer deep-validate (the
old pin is retired), so the compare-and-swap below fails; remove the
pointer file and re-create it with `--expect-absent`, then run
`validate-channel` for each of the three channels.

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

Use the same namespace and compare-and-swap pattern for the other
states. Targets per channel, for any core's semantic ID:

| Channel | Target | Pointer |
| --- | --- | --- |
| `nightly` | `.local-e2e/nightlies/<semantic-id>/golden.json` | `.local-e2e/channels/nightly.<core>.json` |
| `pinned` | `pins/core-sets/<semantic-id>.json` | `.local-e2e/channels/pinned.<core>.json` |
| `release` | `.local-e2e/releases/<semantic-id>/release-manifest.json` | `.local-e2e/channels/release.<core>.json` |

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

The pending bucket is currently empty: every cataloged core is
canonical, so `manifests/compatibility/pending/` holds only its README.

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
5. Promote into a new golden/pin/release lineage. Once accepted, create or
   replace that core's canonical `manifests/compatibility/<core_id>.json`
   record with the actual run and artifact evidence (the source lock and
   source set are composed, never written). The merged registry lets this
   canonical file supersede the immutable legacy matrix row for the same
   core. Never edit an older pin set, release, or legacy matrix row to
   point at the new commit; duplicate ownership among canonical
   compatibility files is invalid.

The canonical compatibility record must name distinct run IDs and bind both
E2E semantic digests: `selected_e2e_content_sha256` belongs to an exact
`github-actions/simulated/local-docker` run, while
`reproduction_e2e_content_sha256` belongs to an exact
`local/native/local-docker` run. Do not copy a selected run into a second path
as reproduction evidence. Deep validation reads each recorded log, proves its
digest and compile contract, and checks both runs against the selected pin's
historical content-addressed recipe snapshot; it deliberately does not require
the immutable record to match today's catalog or pipeline bytes. Selected and
reproduction logs may have different `log_sha256` values: log bytes identify
the evidence from one execution, while reproducibility approval is based on the
exact package and target artifact hashes and sizes. Each log is still rehashed
and must independently satisfy the complete build and core-owned log contract;
different logs do not excuse a missing, malformed, or invalid proof.

Every core's current lifecycle bindings — semantic pin/source-set ID,
selected and reproduction run IDs, package and artifact digests, and the
proof its logs satisfy — are recorded in the core's
`manifests/compatibility/<core>.json` document and enforced by its
`tests/cores/test_<core>.py` lifecycle test; per-core narratives are not
duplicated here (older ones live in this file's git history). New
canonical build, pin, manifest, test, channel, and run IDs must remain
individual-core; historical grouped identifiers are rejected by the
candidate-id guard.

### Composed source locks and source sets

The source lock and the one-core source set are pure functions of tracked
state — the lock of the catalog's source block (URL, ref, commit, tree,
resolved submodule pins), the source-set of the composed lock plus the
evidence pin — so neither is stored as a file. The single composer is
`scripts/core_pipeline_lib/records/source.py`; `promote_core.py`,
`profile_registry.py`, and the release planner all compose through it.

The historical `pins/sources/<core_id>/<commit>.json` and
`pins/source-sets/<source-set-id>.json` strings survive as identity
coordinates inside the documents and their references (and as the
`--source-set` CLI argument), and the shapes remain governed by
`manifests/core-source-lock.schema.json` and
`manifests/core-source-set.schema.json`. Reference `file_sha256` values are
computed over the canonical serialization (`serialize_record`), which
reproduces the retired files' bytes exactly, so digests embedded in pins,
goldens, release manifests, and evidence indexes keep binding.
`content_sha256` values use the
`scripts.profile_registry.canonical_content_sha256` contract, which excludes
only `$schema` and `content_sha256`. Validate any core's composed set with:

```bash
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/<source-set-id>.json
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

For a track-group release, replace both legacy selector forms with one exact
full-roster tag:

```bash
python3 scripts/core_pipeline.py plan-release \
  --candidate-id main-stable-universal-v1 \
  --group-tag main-stable:universal \
  --output .local-e2e/release-plans/main-stable-universal-v1.json
```

Every matrix row includes that same `group_tag`; pass it to both `build-core`
and `record-release-result`. Planning admits only complete exact pinned
packages. A chipset selector that projects one ABI from a multi-ABI pin fails
before the matrix is produced. Stable and unstable-fallback selections may
coexist in the same plan and remain marked in every result, the seal, and the
overlay manifest.

A fleet run that fails on an **out-of-repo transient** (runner death, a
GitHub 500 serving a toolchain asset) does not need a full rebuild:
`gh run rerun <run-id> --failed` re-executes only the failed workers and
the seal. The plan job is not re-run — its immutable plan artifact and
candidate identity persist across attempts, worker result artifacts are
attempt-suffixed so they cannot collide, the seal merges results across
all attempts, and no fan-in check binds the attempt number. Every
re-run is pinned to the original commit, so this is only ever a
completion of the same plan; an in-repo fix still forces a new commit,
a new plan, and a full roster by construction. (Validated on run
30124953754: 97 attempt-1 results plus one attempt-2 rebuild sealed the
first release candidate.)

Legacy `--scope full-workflow-roster` admits every discovered workflow into the
census and constructs since the migration completed (98/98 canonical);
the GitHub Actions release-candidate coordinator applies that same complete
census through its required group tag. Do not weaken that census.

Plan creation reads only tracked files. Each worker deeply validates its fresh
E2E tree and requires package/artifact bytes, clean repository commit, sources,
toolchains, workflow, blacklist, and pipeline identity to match the plan. The
seal reads only portable worker bundles and rejects any incomplete, extra,
tampered, mixed-plan, or mixed-runner fan-in before exposing output.

The release plan is schema v3 because it binds the coordinator and reusable
worker file identities plus the nullable exact track group. Its target model
and the v2 result/candidate schemas remain static-build-only: they bind one
selected evidence cell per architecture and make no device eligibility claim.
A second build profile for the same
architecture requires a later execution-profile-keyed schema rather than an
overloaded architecture target.

The three published full-release JSON Schemas are structural interoperability
contracts only. Plan, worker-result, seal, and overlay operations always run
the mandatory Python cross-field validators, and repository-facing operations
also reconstruct the exact tracked state. JSON Schema acceptance by itself is
never release eligibility or approval.

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
