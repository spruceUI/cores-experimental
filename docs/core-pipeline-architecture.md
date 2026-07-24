# Core pipeline Python architecture

`scripts/core_pipeline.py` is the stable executable and composition root.
New implementation code belongs in `scripts/core_pipeline_lib/`; do not add a
new core, runner, or policy by growing another branch in the launcher.

**In one paragraph:** the launcher stays frozen; packages under
`core_pipeline_lib/` own contracts (per-core identity + build-log
proofs on shared engines: `c_only`, `mixed_language`, `c_asm`,
`cargo`, plus catalog-driven direct-cmake/direct-cargo), records,
policies, release orchestration, and errors. Contract modules
self-register by introspection (a registry row plus module-level
naming conventions — no launcher edits). The sections below give the
package boundaries, the recipe for adding a core contract or runner
profile, release orchestration internals, and record ownership.

The package uses the useful part of SpruceOS PyUI's Python organization:
domain-first directories, one implementation module per core or platform, small
typed state objects, and a narrow selector at the entry boundary. Build tooling
remains stricter than UI runtime code: failures are never swallowed, no-op
delegates are not permitted, wire values are stable strings rather than
`Enum.auto()`, and every package has explicit imports and focused unit tests.

## Package boundaries

- `foundation.py` contains the still-shared process, hashing, containment,
  locking, and atomic-file primitives. As it grows, split by those
  responsibilities; do not create a generic `utils` package.
- `runtime/` resolves where the shared implementation is executing.
  `local.py` and `github_actions.py` own environment-specific checks,
  `paths.py` owns common containment, `model.py` owns immutable requests and
  contexts, and `resolve.py` only selects a profile.
- `policy/` owns source-admission policy. `blacklist.py` parses and reports the
  immutable exact-commit policy; `admission.py` binds that policy to state-
  creating operations. Historical validators remain separate from current
  admission.
- `contracts/` owns compiler-command semantics and individual-core build-log
  proofs. Shared syntax belongs in identity-free parser modules such as
  `command_line.py`, `compiler.py`, `c_only.py`, and narrowly scoped
  `<platform>_common.py` helpers. Every migrated core owns its immutable
  identity, proof parameters, and proof callable in `<core>.py`;
  `registry.py` contains only singleton entries. Paired compatibility modules
  do not belong in production code; historical paired behavior is fixture-only.
- `cli/` owns parser construction. `model.py` receives the entrypoint's handlers,
  paths, and finite choices as frozen dependencies; `parser.py` declares the
  public command surface without importing the entrypoint. The composition root
  only wires those dependencies and keeps the process-level error boundary.
- `source_bundle.py` inventories the executable and every Python package source.
  New build records bind that complete bundle, so moving logic between modules
  cannot silently preserve an old recipe identity. Generation rejects a
  missing, uncontained, or symlink-traversed package tree rather than degrading
  to a launcher-only identity.
- `records/` owns tracked record composition. Individual compatibility
  documents live at `manifests/compatibility/<core_id>.json` and bind exactly
  one immutable one-core pin. Each document binds the selected and reproduction
  E2E content SHA-256 values as well as their paths. The selected run must be
  `github-actions/simulated/local-docker`; the distinct reproduction run must
  be `local/native/local-docker`. Both runs are checked against the promoted
  content-addressed recipe snapshot, so historical validation proves the
  recorded source, toolchain/archive, and build contract without comparing
  immutable evidence with the current recipe. Build logs normally match by
  digest; when parallel output changes only line order, the validator permits
  a different digest only after proving every other build field and the exact
  log-line multiset match the selected content-addressed log. The
  loader overlays those canonical files on the legacy aggregate matrix: a
  canonical record supersedes the immutable legacy row for the same core,
  while duplicate ownership among canonical files fails closed.
- `release/` owns runner-neutral full-release planning, portable one-core
  worker results, and fail-closed candidate sealing. `repository.py` rebuilds a
  plan only from clean, tracked repository state; `worker.py` binds one fresh,
  deeply validated E2E run to that plan; and `seal.py` accepts only the exact
  planned fan-in. `cli/release.py` declares the four command parsers while the
  composition root supplies their filesystem and validation services.

The next broad domains to extract are catalog validation, build execution,
evidence/snapshots, artifact promotion, and CLI command handlers. Each
extraction must leave only composition and process-boundary wiring in the
executable and move its tests into a matching focused test module.

## Add an individual core contract

1. Put the immutable source identity, constants, and proof in
   `core_pipeline_lib/contracts/<core>.py`, with matching focused coverage in
   `tests/test_contract_<core>.py`.
2. Reuse the shared command-line, compiler, and language-contract modules. A
   related core family may share a neutral parser/helper, but each migrated core
   keeps its identity and proof entry in its own file.
3. Register the core exactly once in `contracts/registry.py` with a stable
   contract ID, individual proof name, and operator-facing failure message.
4. Import that individual proof into `core_pipeline.py` for registry dispatch;
   do not add family maps, multi-core dispatchers, or paired compatibility APIs.
5. Add direct parser/proof tests and boundary tests proving that live builds,
   promotion, and stored evidence all invoke the registered proof.

Every canonical core with a per-core contract follows this layout (89 of
the 98; direct-cmake, direct-cargo, and make-variable cores use the
generic catalog-driven proofs and need no per-core module). Shared
mechanics live in neutral helpers; source identities and registered
proofs never share a file or registry entry. What each contract proves —
its exact compile set, native-version scope, link identity, and reviewed
diagnostic streams — is stated by its own
`contracts/<core>.py` module and pinned by `tests/test_contract_<core>.py`;
this document no longer duplicates those descriptions (older prose
summaries live in its git history). Two boundary rules worth naming:
cores sharing an upstream source commit (the Snes9x 2005 pair, the VICE
machines, the Genesis Plus GX pair) still keep fully separate contracts,
pins, and lifecycles — shared source never merges build identity; and
parallel builds may reorder complete log lines, but every proof pins the
line multiset, compile pairs, invocation digests, and link identity, so
ordering tolerance never weakens content identity.

Portable artifacts stay shared by ABI/build flavor. A device-specific family
module is justified only by captured ABI, GPU, performance, packaging, or
runtime evidence—not by the number of device profiles that consume it.

## Add a runner profile

1. Add an immutable selector/wire value to `runtime/model.py`.
2. Implement the profile in its own `runtime/<profile>.py` delegate.
3. Keep filesystem and repository-state checks in `runtime/paths.py` when they
   are shared; keep environment identity checks inside the delegate.
4. Add one exact route in `runtime/resolve.py` and persist its normalized
   evidence through `runtime/evidence.py`.
5. Add focused resolver/evidence tests, then exercise the shared E2E command.

All profiles are local-only from the pipeline's perspective. Native GitHub
Actions changes the execution backend, not the publication policy; this
repository exposes no publication command.

`e2e` is an individual-core execution boundary: each invocation requires
exactly one `--core`. Its repeatable `--arch` selector can narrow that one
core's target set for diagnostics, but it cannot introduce another core or an
all-core default. A complete package and promotable schema-v2 record still
require the selected architecture set to equal that core's catalog targets.

The workflow audit enforces the same ownership boundary. It requires one
independent `.github/workflows/build-<core>.yml` owner per catalog core and
requires that owner to invoke the shared E2E command exactly once with
`--runner-profile github-actions --core <core>`. It rejects missing or
mis-bound catalog owners and active `build-all*.yml` or `build-all*.yaml`
aggregate workflows. The retired aggregate build-all records live only in git history. A separate fail-closed projection audits the two release workflows:
only manual coordinator dispatch, reusable-worker calls, read-only permissions,
pinned approved actions, bounded matrix fan-out, canonical artifact layout,
and publication-disabled shared commands are admitted.

## Full-release orchestration

The current full-release surface is local-only and publication-disabled. From
a clean committed checkout, `plan-release` freezes the repository and selected
canonical cores, `record-release-result` converts one fresh per-core E2E run
into a portable worker bundle, and `seal-release` admits only the complete
runner-consistent result set:

```bash
python3 scripts/core_pipeline.py plan-release \
  --candidate-id ID --scope canonical \
  --output .local-e2e/release-plans/ID.json
python3 scripts/core_pipeline.py release-matrix \
  --plan .local-e2e/release-plans/ID.json
python3 scripts/core_pipeline.py record-release-result \
  --plan .local-e2e/release-plans/ID.json --core CORE \
  --e2e-record .local-e2e/runs/RUN_ID/e2e-record.json \
  --output-dir .local-e2e/release-results/ID/RUNNER/CORE
python3 scripts/core_pipeline.py seal-release \
  --plan .local-e2e/release-plans/ID.json \
  --results-root .local-e2e/release-results/ID/RUNNER \
  --runner-profile RUNNER \
  --output-dir .local-e2e/release-candidates/ID/RUNNER
```

Run the result command once for every core in the immutable plan. `RUNNER` is
one of `local`, `github-actions`, or `github-actions-sim`; the result command
derives it from the E2E record rather than accepting a separate selector. See
[core-pipeline-operations.md](core-pipeline-operations.md) for the complete
runnable canary and full-scope procedures.

The top-level `release-candidate.yml` coordinator generates the plan, derives
its matrix, and fans rows out to one parameterized reusable
`_build-one-core.yml` worker. GitHub limits a call tree to 50 unique reusable
workflows, so calling
50 distinct per-core wrappers would consume the entire allowance and leave no
nesting margin. A matrix may contain 256 jobs; the current canonical roster can
therefore invoke the same reusable worker once per core while counting as only
one unique reusable workflow. Individual `build-<core>.yml` entrypoints remain
useful for direct builds, but the release coordinator must bypass those
wrappers so the individual and aggregate paths share the same worker contract.
Its `candidate_label` input is not the durable identity by itself: the
coordinator appends the Actions run ID and attempt, passes that derived ID
through the plan output, and binds it into every worker and seal path. Result
artifact names also include the executing attempt, while the portable result
upload is the worker's final step; this permits failed-job reruns without
colliding with an already successful immutable artifact.

The coordinator and worker are publication-disabled. Candidate sealing
does not create a GitHub release, advance a public channel, or upload to a
distribution endpoint. A future, separately approved `publish-release.yml`
may consume an already sealed candidate, but it must not rebuild its assets.
The workflow audit pins the complete reviewed bytes of both YAML files and the
exact commits of their allowed actions. Any workflow edit requires an explicit
reviewed hash update; unmodeled YAML or commands cannot pass by omission.

Release-plan schema v2 binds both orchestration workflow identities. Its target
model and the v1 result/candidate schemas still key each core's evidence by
architecture. That matches today's single `ra64-universal-v1` and
`ra32-a30-v1` evidence cells and makes no device eligibility claim. Multiple
execution profiles for the same architecture require a later
execution-profile-keyed schema revision; the current model must not encode
such variants as duplicate architecture targets.

## Individual record and test ownership

Newly migrated cores own their lifecycle records independently:

- `.local-e2e/nightlies/<core>-candidate-<label>/golden.json` is create-only
  schema-v2 working state whose `core_id` names the one exact key in both
  `cores` and `build_goldens`;
- `.local-e2e/nightlies/<core>-<source12>-<selection12>/golden.json` is a
  create-only projection whose `cores` and `build_goldens` maps contain exactly
  that core;
- `pins/core-sets/<core>-<source12>-<selection12>.json` contains exactly that
  core and has no aggregate parent;
- `pins/source-sets/<same-id>.json` binds its one immutable source lock to the
  one-core pin;
- `manifests/compatibility/<core>.json` is the canonical tracked
  compatibility record;
- `tests/cores/test_<core>.py` owns the pin, source-set, compatibility, and
  individual channel contract for that core; and
- `.local-e2e/channels/<channel>.<core>.json` is the ignored schema-v2
  nightly, pinned, or release alias.

Every canonical core (all 98) owns its records under this model.
Shared loading helpers belong in `tests/cores/support.py`, while assertions
about one core's source, package, ABI artifacts, caveats, and pointer isolation
stay in that core's test module.
A cross-core test is justified only for shared registry, namespace isolation,
or aggregate-compatibility behavior.

Canonical compatibility manifests are current admission records layered over
immutable pins. Deep validation uses each pin's frozen recipe snapshot for
catalog, workflow, pipeline, and toolchain identity, then reapplies the current
registered core-owned log proof. If that proof's accepted evidence changes,
create a new individual-core compatibility successor; do not rewrite the
immutable pin or grandfather newly invalid compiler evidence. Frozen aggregate
rows remain regression fixtures and are not passed through this current
admission gate.

A newly cataloged core that still needs clean selected and reproduction builds
owns one temporary
`manifests/compatibility/pending/<core>.json` record. That record binds the
entire catalog core specification, source commit, and exact target set while
making no artifact, package, golden, release, runtime, or device claim. Pending
records are disjoint from both canonical compatibility admission and the
effective compatibility coverage supplied by a current canonical record or an
immutable legacy bridge row. `catalog-check` requires every catalog core to
have exactly one effective compatibility-or-pending state; a canonical record
supersedes any frozen row for the same core. The pending file is removed in the
same lifecycle change that adds
`manifests/compatibility/<core>.json`; it is never loaded into
`golden_sources` and no pin, release, or channel command consumes it. This
provides a clean committed recipe for local E2E without weakening admission or
rewriting the frozen legacy matrix.

The pending set is currently empty: every cataloged core is canonical.

Each canonical core's current semantic ID, pin, source set,
compatibility owner, lifecycle test, run IDs, and remaining
static-build-only caveats are recorded in its
`manifests/compatibility/<core>.json` document and enforced by
`tests/cores/test_<core>.py`; per-core narratives are not duplicated
here (older ones live in this file's git history). All promoted evidence
is static-build-only and binds to `ra64-universal-v1` / `ra32-a30-v1`
execution profiles; runtime and device claims stay explicit gates.

This ownership model lets multiple device buildsets reuse the same immutable
core record. Device grouping does not justify copying a universal core pin;
only a proven build-flavor or ABI difference creates another selection.

## Legacy aggregate containment

Legacy aggregate core sets, source sets, releases, channel snapshots, and their
compatibility rows are immutable history. Keep their schema-v1 readers and
regression fixtures, but never rename, rewrite, or use their batch identifiers
for new work. Duplicate core ownership among canonical files is invalid; the
compatibility coverage is asserted per-core-only since the legacy-tranche
retirement of 2026-07-23.

Historical batch chronology, build-all records, and explanatory notes live
only in git history. Production workflows, contracts, manifests,
source sets, lifecycle commands, run IDs, and operator examples are named for
one core at a time.

The retired aggregate channel pointers live only in git history. The
active namespace contains only
schema-v2 `.local-e2e/channels/<channel>.<core>.json` aliases, and both channel
commands require `--core`. In particular, a schema-v2 nightly pointer accepts
only an exact-one-core projection created by `compose-core-golden`. Active
promotion candidates are likewise core-owned:
their `build_goldens` map contains exactly their core, whose object starts empty
and may acquire only that core's architecture evidence. Each promotion must
come from a runner-bound schema-v2 E2E whose build and package lists contain
only that core. The active E2E command rejects omitted or repeated `--core`
arguments; architecture subsets are its only partial diagnostic scope.
Aggregate goldens remain schema-v1 historical inputs for read-only validation
and cannot be mutated, promoted into, or reused as individual targets.

The schema-v2 golden content digest binds the core and pin identities, local
publication policy, imported baseline, core record, and build evidence.
Timestamps and the derived summary are excluded from that semantic projection;
their exact fields and types are still validated, and immutable lifecycle
references bind the complete rendered file SHA256.

## Error and model conventions

- Domain leaves raise their narrow error (`RunnerProfileError`,
  `CommitBlacklistError`); a boundary translates it to `PipelineError` once.
- Catch only expected exceptions and preserve the cause with `raise ... from`.
- Use frozen, slotted dataclasses for validated internal state. JSON schema
  boundaries remain strict dictionaries because their exact key sets are part
  of provenance.
- Pass environment, Git state, roots, and clocks as explicit inputs. Do not add
  mutable service locators or module singletons.
- A failed proof returns false only when false is the contract result; malformed
  configuration and unsupported architecture raise a typed error.

## Extraction acceptance checks

For every code split:

1. direct tests cover the extracted module;
2. CLI signatures and individual proof monkeypatch boundaries remain compatible;
3. historical recipe/snapshot schemas still validate;
4. new recipes bind the complete source bundle;
5. the core pipeline module, workflow audit, and `git diff --check` pass;
6. build-affecting splits reproduce at least one local and one simulated-
   Actions E2E before promotion resumes.

See [core-pipeline-operations.md](core-pipeline-operations.md) for runnable
commands and lifecycle procedures.
