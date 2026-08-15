# Ordered core tracks, stability, and chipset selection

The core pipeline has a versioned selection layer for keeping several
ordered build inventories at the same time. A selection tag has the exact
form:

```text
<track>-<marker>:<chipset>
```

- `track` is `main`, `nightly`, or `edge`;
- `marker` is `stable` or `test`; and
- `chipset` is `universal`, `h700`, `a133p`, `a523`, `a33`, `rk3566`,
  `rk3326`, or `ssd202d`. `a523` identifies Trimui Smart Pro S and `a33`
  identifies Miyoo A30.

For example:

```bash
python3 -B scripts/core_pipeline.py core-track-inventory \
  --group-tag main-stable:h700
python3 -B scripts/core_pipeline.py core-track-inventory \
  --group-tag nightly-test:a133p --core mgba
```

`stable` and `test` are markers inside a track, not independent rosters.
Likewise, the existing local `pinned` channel is not a track.

## Track and promotion model

TEST and deferred assignments inherit in one direction: `main` to `nightly`
to `edge`. A child track without a direct cell follows that inheritance. A
direct child cell replaces it, even when it deliberately selects the same pin
as its parent; that equal assignment is a frozen version-level decision rather
than an alias that moves with the parent. The track names describe manually
curated version levels:

- `main` is the Spruce stable/Main version label;
- `nightly` is the Spruce Development version label; and
- `edge` is an exact upstream branch tip captured and reviewed when it is
  admitted. It is frozen to that captured ref, commit, and tree rather than
  following a remote after admission.

Selecting a Main or Development version level is a manual policy decision; it
does not claim that a new artifact is byte-identical to a historical Spruce
binary or that the historical binary reveals its source revision. Once a
source is selected, every track pin still records its exact repository, ref,
commit, tree, submodule graph, recipe, and output evidence.

The separate Spruce branch artifact bases are immutable comparison evidence.
Each basis records the reviewed branch commit/tree, both core subtree
identities, Git blob and SHA-256 identities for shipped binaries, and a
complete catalog/ABI cell matrix in
[`spruce-core-branch-bases.json`](../manifests/spruce-core-branch-bases.json).
They are not source-selection authority and are not an artifact-byte admission
oracle. Changing any recorded branch or artifact identity requires an explicit
new comparison basis and track-registry identity.

The initial v3 registry deliberately has no direct TEST or STABLE build pins.
All 98 `main:test:universal` cells are `deferred` with reason
`no-reviewed-version-channel-build-pin`; nightly and edge inherit those
states. This is a complete policy roster, but not a complete build inventory.
Inventories list these cells in `deferred_cores`, report
`inventory_state: "deferred"`, and retain `complete: false`. Deferred entries
never resolve into executable build rows.

The historical v4.3 roster's machine-readable `correlation_model` is
`logical-core-name-correlation-only-v1`. The binding correlates logical names
only and is retained as historical correlation, not selection authority. A
branch basis proves shipped artifact bytes, but does not infer an upstream
source commit, submodule graph, build recipe, or toolchain from those bytes.
Therefore it is not a reproducible build pin.

Registry build cells use `build_pin_id`, distinct from branch-artifact
identity. For every track and catalog core, the effective universal state must
be build-pinned XOR deferred. Admitting the first universal build pin removes
the matching deferred state atomically. The pin is admitted against its track's
version-level and source-ordering policy, not by reproducing branch-basis
artifact bytes. An invalid historical branch ABI remains quarantined in the
comparison basis and makes no claim about a newly built pin. Pin files and
earlier evidence remain preserved even when no registry cell references them.

For admitted build pins, the default source policy is
`main <= nightly <= edge` for every core at child-assignment time. A new or
replacement Nightly/Edge TEST cell CASes the current effective parent and
stores an immutable `source_order_parent_bindings` record containing the
parent cell, variant, pin, source, inherited origin/lineage, reviewed registry
identity, child identity, and binding digest. Equality is allowed, so Main and
Nightly may deliberately select the same source when their version labels are
the same; the direct equal child is still frozen by its binding. Otherwise,
parent and child must use the same repository and Git must prove that the
captured parent's exact commit is an ancestor of the child's exact commit. Pin
hashes, timestamps, branch names, and version-like strings are never treated as
commit chronology.

Later movement of Main or Nightly does not retroactively invalidate an existing
child binding. It changes what an inheriting track sees and what the next child
assignment must CAS, but it does not rewrite an already reviewed child. An Edge
binding to a direct Nightly parent also carries Nightly's captured lineage, so
the assignment-time chain remains independently verifiable after either parent
moves.

Only an exact, reviewed TEST outlier authorization recorded with the registry
may bypass the repository-equality or ancestry requirement for the specific
assignment-time edge it names. It binds the parent-binding digest and complete
child variant/pin/source identity and must not act as a wildcard for another
core, repository, commit, tree, or track edge. Missing, stale, or inexact
authorization fails closed. A commit/tree inconsistency is never authorizable:
if the same commit is paired with a different tree, validation must fail rather
than treating it as an ordering outlier.

Production commands use only pre-existing bare mirrors at
`.local-e2e/source-repositories/<core-id>.git`. The mirror's sole origin URL
must exactly match the pin. Validation never fetches; it fails closed when the
mirror or either commit is missing, when the clone is shallow/incomplete, or
when ancestry cannot be proved. Replacement objects, grafts, alternate object
stores, lazy object fetching, and Git environment repository overrides are not
accepted as ancestry evidence.

Global inventory, coordinator, and seal validation prove every captured
differing-commit edge or validate its exact recorded outlier authorization.
They do not substitute a child's current moving parent for its recorded parent
binding. A one-core build
resolver uses an explicit selected-core ancestry scope:
it still validates the complete registry, pins, tuning, roster, hashes,
repository consistency, and equal-commit trees, but requires a local Git graph
only for the selected core. Unrelated external graph edges are deferred, not
reported as globally valid, and remain mandatory at the full-graph gates. This
lets an isolated worker hydrate one core mirror without turning a missing
unrelated mirror into an implicit ancestry approval.

STABLE approval is a separate marker from the Main/Nightly/Edge version level.
It is direct and track-local and never inherits from a parent track or another
chipset. A stable entry records the exact promoted test
variant plus the approving operator assertion, timestamp, reason, and source
registry digest. That digest must resolve to the canonical repository snapshot
at `pins/core-track-registry-snapshots/<digest>.json`; validation recomputes the
snapshot registry identity and proves that the stable cell was the effective
TEST cell of the approval track, including its inherited origin. A bare digest
or unavailable Git history is not accepted. The approval metadata is preserved
in a resolved stable row. Edge latest-head validation applies to the current
effective TEST cell only; an older Edge STABLE approval remains historical and
is validated through its approval snapshot rather than against today's reviewed
Edge head. Every prior stable snapshot is validated recursively;
memoization makes shared history deterministic, while cycles and provenance
chains deeper than 64 snapshots fail closed.
The registry plus its source snapshot is the review boundary; both files must
be reviewed and committed together before the approval is durable.
`approved_by` is not a
cryptographic signature.

The initial registry has no stable approvals or TEST build pins. A
stable-marked inventory therefore reports deferred cells until exact,
policy-compliant track pins are admitted. After admission it uses TEST fallbacks and
reports `inventory_state: "unstable"` until cores are explicitly approved.

Promote one reviewed exact TEST cell with a compare-and-swap variant identity:

```bash
python3 -B scripts/core_pipeline.py core-track-promote \
  --track main --core mgba --chipset a523 \
  --expected-test-variant <64-hex-variant-id> \
  --expected-current-stable absent \
  --approved-by <operator> --reason <review-reason>
```

Both sides of the promotion are compare-and-swap gates. For a first approval,
`--expected-current-stable absent` asserts that the exact track/core/chipset
stable cell does not exist. To advance an existing approval, pass that cell's
reviewed 64-hex `approved_test_variant_id` instead. The command refuses an
implicit universal fallback, a changed TEST variant, or any absent/different
current stable state. It freezes the entire pre-promotion registry—including
the prior stable approval—before atomically updating the registry, and records
that prior variant (or `null`) as `previous_stable_variant_id` so validation
can prove the CAS state against the snapshot. Approval
timestamps must be real, canonical UTC seconds (`YYYY-MM-DDTHH:MM:SSZ`), and
the approver and reason must contain non-whitespace text. This is still static
build-selection policy; it does not authorize release, publication, or
deployment.

## Universal fallback

`universal` means the catalog's default build with no chipset-specific tuning.
Its resolved property object and compiler argument list must both be empty.
A pin that already binds non-universal tuning cannot be relabeled universal.

For a real-chipset stable inventory, each build-pinned core resolves in this
order:

1. exact-chipset stable;
2. compatible universal stable;
3. exact-chipset test, marked `unstable_fallback`;
4. compatible universal test, marked `unstable_fallback`; or
5. deferred (reported separately, never as a build row); or
6. unsupported.

This means an approved universal build outranks an unapproved tuned test build.
For a test inventory, resolution is exact-chipset test and then compatible
universal test; stable entries are never substituted. There is no fallback
from one real chipset to another.

Every resolved build row records the requested track's exact
`spruce_branch_basis` comparison-evidence binding in addition to the requested
and selected chipset, selected ABI, build-pin and source identities, tuning
identity, resolution reason, stability, and test-origin track. The basis does
not select or approve the build pin. A universal selection for a real chipset
selects only that chipset's ABI. A `:universal` request deliberately selects
every ABI carried by the portable build pin.

## Typed tuning profiles

[`chipset-tunings.json`](../manifests/chipset-tunings.json) is a closed,
content-hashed registry. The accepted properties are:

- `cpu_target`: `cortex-a7`, `cortex-a35`, `cortex-a53`, or `cortex-a55`;
- `tune_target`: the same closed CPU set;
- `fpu`: `neon-vfpv4`; and
- `float_abi`: `hard`.

Code owns the only mapping to `-mcpu`, `-mtune`, `-mfpu`, and
`-mfloat-abi`. The registry pins that mapping as `gcc-machine-flags-v1`; the
mapping version and resolved compiler-argument list are part of the resolved
tuning content identity and every core-variant identity. Changing the mapping
therefore requires a new mapping version and new identities. Raw flags,
environment values, Make/CMake fragments, and shell text are not registry
properties. The A33 and SSD202D ARMHF profiles require the complete reviewed
Cortex-A7/NEON-VFPv4/hard-float tuple. The A523 profile uses Cortex-A55. H700
currently has no reviewed tuned profile and therefore resolves through an ARM64
universal cell.

A real-chipset cell is admitted only when its immutable pin already records the
same resolved tuning identity. Merely adding a profile to the registry does not
rewrite or bless old artifacts. When present, a pin's `chipset_tuning` record
has exactly two fields, `profile_id` and `content_sha256`; extra flag or command
fields are rejected rather than interpreted.

Every pin used by the registry first passes the pipeline's authoritative
immutable-pin validator and canonical parentless one-core identity gate. The
smaller source/tuning projection in the track index runs only after that
admission; it cannot accept a structurally minimal document merely because its
top-level digest and source commit look plausible. Ignored artifact-store
bytes are not required for this structural lifecycle admission.

## Group-selected build reproduction

`build-core` and `e2e` can consume one canonical group tag directly:

```bash
python3 -B scripts/core_pipeline.py build-core \
  --core mgba --group-tag main-test:a523 --run-id mgba-main-test-a523
```

The group is resolved before the run directory is created. Each row carries an
exact `execution_source` projection: URL, requested ref, commit, tree, and the
unique sorted path/commit list for every submodule. All ABI records in the pin
must agree on that projection. The repository URL must equal the current
catalog repository, but the ref, commit, tree, and submodule graph may differ;
this is what lets `main`, `nightly`, and `edge` select distinct upstream
revisions concurrently. The selected commit, rather than the catalog's default
commit, passes the blacklist gate.

Execution copies the current catalog recipe and substitutes the selected
source without mutating the catalog. The selected pin's normalized target build
contract and output names must remain compatible with that current recipe. The
selected-pin and execution core-spec digests are both recorded; a digest
difference is allowed only when those execution-critical projections still
agree, and exact pinned output hashes remain the acceptance oracle. The live
checkout must reproduce the selected URL, commit, tree, clean submodule states,
and exact submodule pins. Build-log and source-date proofs also receive the
selected source identity. The pipeline does not interpret a historical recipe
snapshot or invent a historical log contract; an incompatible revision fails
as unsupported.

The resolved row owns the architecture set. A real chipset builds only its ABI,
including when it selects a universal fallback; `:universal` builds every ABI
in the portable pin. `--group-tag` and the diagnostic `e2e --arch` selector are
therefore mutually exclusive.

Typed tuning is re-resolved from the content-hashed registry at execution time.
Catalog compile definitions and mapped tuning arguments share one sanitized
`CFLAGS`/`CXXFLAGS` export, so tuning cannot overwrite the catalog definitions.
A tuned build passes only if every visible target compiler `-c` invocation
contains the exact mapped machine arguments and no conflicting machine flag.
Non-empty tuned `direct-cargo` execution is currently unsupported and fails
before Docker runs.

This path is a pinned-output reproduction gate. Each selected artifact and the
metadata must exactly match the pin's hashes and sizes. The package must also
match when the selected ABI set equals the pin's complete package scope. When a
real-chipset request projects one ABI from a multi-ABI universal pin, the record
marks package comparison `not_applicable_projected_architectures`; the selected
artifact and metadata comparisons remain mandatory.

Build records and the digest-bound E2E record preserve the exact group,
registry, variant, pin, complete execution source, ABI, tuning, and
expected-output identities.
The build recipe also records the selected tuning profile and tuning-content
digest. Group records remain deliberately rejected by the legacy
golden/pin promotion path; use the separate candidate flow below to create a
new tuned pin rather than projecting or relabeling a universal package.

## One-ABI tuning bootstrap and TEST admission

Create two fresh, independent candidate runs from the same current registry
profile. `--tuning-profile` is mutually exclusive with `--group-tag` and
`--arch`, resolves exactly one non-universal profile and ABI, and writes the
full registry/profile/mapping/property/argument identity into the build
record, E2E digest, and ZIP manifest:

```bash
python3 -B scripts/core_pipeline.py e2e \
  --runner-profile github-actions-sim \
  --core mgba --tuning-profile a523-cortex-a55-v1 \
  --run-id actions-sim-mgba-a523-selected
python3 -B scripts/core_pipeline.py e2e \
  --runner-profile local \
  --core mgba --tuning-profile a523-cortex-a55-v1 \
  --run-id local-mgba-a523-reproduction
```

Promote only after both runs passed, using an empty, active one-core candidate
golden as the lifecycle source:

```bash
python3 -B scripts/core_pipeline.py promote-tuned-variant \
  --core mgba --tuning-profile a523-cortex-a55-v1 \
  --source-golden .local-e2e/nightlies/mgba-candidate-a523/golden.json \
  --selected-e2e .local-e2e/runs/actions-sim-mgba-a523-selected/e2e-record.json \
  --reproduction-e2e .local-e2e/runs/local-mgba-a523-reproduction/e2e-record.json
```

The two E2Es, build records, run IDs, and build logs must be distinct. Each log
is validated independently against the typed tuning and core-owned log
contracts, so its content hash may differ. Source, normalized recipe, tuning,
ABI, artifact, metadata, and complete one-ABI ZIP identity must agree, and the
artifact, metadata, and ZIP bytes must match exactly. The command stores both
proofs, snapshots the exact tuning-registry file into the historical recipe,
deep-validates the result, and creates an immutable one-core one-ABI golden and
pin. A projected universal package, grouped reproduction record, changed
registry, or tuned `direct-cargo` recipe is not eligible.

Admit the reviewed pin to one exact track-local TEST cell with direct-cell,
new-variant, and parent CAS:

```bash
python3 -B scripts/core_pipeline.py core-track-set-test \
  --track nightly --core mgba --chipset a523 \
  --pin-id <promoted-pin-id> --tuning-profile a523-cortex-a55-v1 \
  --slice-time 2026-08-10T12:00:00Z \
  --expected-current-test absent \
  --expected-current-assignment absent \
  --expected-parent-variant <reviewed-main-variant-id> \
  --expected-parent-registry <reviewed-main-registry-content-sha256> \
  --expected-new-variant <reviewed-64-hex-variant-id>
```

For a default, untuned fallback pin, select `--chipset universal`, require
`--tuning-profile universal-v1`, and repeat `--applicable-chipset` in sorted
order for every reviewed real chipset. Every applicable ABI must exist in the
pin, so a portable pin may explicitly cover both ARM64 and ARMHF:

```bash
python3 -B scripts/core_pipeline.py core-track-set-test \
  --track edge --core mgba --chipset universal \
  --pin-id <portable-pin-id> --tuning-profile universal-v1 \
  --slice-time 2026-08-10T12:00:00Z \
  --applicable-chipset a33 --applicable-chipset a523 \
  --expected-current-test absent \
  --expected-current-assignment absent \
  --expected-parent-variant <reviewed-nightly-variant-id> \
  --expected-parent-registry <reviewed-nightly-registry-content-sha256> \
  --expected-new-variant <reviewed-64-hex-variant-id>
```

Use the current direct TEST variant instead of `absent` when replacing a cell.
The inventory row's direct-coordinate
`current_assignment_content_sha256` is the durable source for
`--expected-current-assignment`; use `absent` only when it is `null`.
`--slice-time` is immutable UTC-second assignment/tranche metadata. It is
excluded from build variant identity but frozen into the complete assignment
digest, comparison basis, and child parent history. For Nightly and Edge,
`--expected-parent-variant` names the current effective parent and
`--expected-parent-registry` names the reviewed current parent registry; the
command creates/verifies the returned parent snapshot before the registry
write. The command revalidates the authoritative pin, current tuning registry,
assignment-time source ordering (or an exact recorded outlier authorization),
and all CAS expectations before atomically writing the registry.
It removes the matching effective deferred state in the same registry
transition. It does not change any stable approval; `core-track-promote`
remains the separate operator approval step.

Fresh TEST/STABLE admission requires a non-null hardened
`host_reproduction` proof in the pin selection. The proof binds an independent
`github-actions-sim` selected run and `local` reproduction plus their immutable
telemetry/profile/schema/tool CAS references. Historical proof-less pins remain
readable but are not eligible for a new assignment.

## Exact-package group releases

The publication-disabled full-release path has a separate group selector:

```bash
python3 -B scripts/core_pipeline.py plan-release \
  --candidate-id main-stable-universal-candidate \
  --group-tag main-stable:universal \
  --output .local-e2e/release-plans/main-stable-universal-candidate.json
```

`--group-tag` is mutually exclusive with the legacy `--core` and `--scope`
selectors and always resolves the complete tracked workflow roster. Planning
resolves every core before composing any release row. Each selected source and
normalized recipe must remain executable, and each row must have
`expected_outputs.package.comparison: "exact"`. A real-chipset selector that
projects one ABI from a multi-ABI package therefore fails during planning,
before a matrix or worker exists; its grouped E2E remains useful as diagnostic
evidence but cannot be sealed as a release asset.

The immutable plan binds the exact group tag plus the tracked track, tuning,
Spruce branch-basis comparison evidence, and historical roster identities.
Per-core rows preserve the selected stable, unstable-fallback, or test state;
pin, variant, requested and selected chipset, architecture set, tuning,
complete execution source
(URL/ref/commit/tree/submodules), recipe compatibility, and exact output
oracle. The Actions matrix passes the exact tag to every reusable
worker. Results retain the complete selection, while the sealed candidate and
file-overlay manifest carry compact per-core markers and stable versus
unstable-fallback inventory counts. Registry, tuning, roster, pin, recipe,
artifact, package, or tag drift fails revalidation.

This is still local-only and publication-disabled. It creates a sealed
candidate and deterministic drop-in overlay; it does not publish either one,
advance a channel, deploy to a device, or establish device-runtime fitness.

## Evidence boundary

The inventory command produces a deterministic, local-only,
publication-disabled `static-build-selection-only` inventory. The registry's
`applicability_scope` is `architecture-only`: an applicable universal cell says
that the pin contains the required ABI, not that the core passed device runtime
compatibility. Device/provider eligibility and publication remain separate
fail-closed gates. Exact full-package release fan-out and overlay inventory
preservation are available only through the group-release contract above.
In particular, an inventory is not permission to deploy an ABI-incompatible or
runtime-ineligible core.

The schemas are:

- [`core-tracks.schema.json`](../manifests/core-tracks.schema.json)
- [`chipset-tunings.schema.json`](../manifests/chipset-tunings.schema.json)
- [`core-track-inventory.schema.json`](../manifests/core-track-inventory.schema.json)
- [`core-track-source-snapshot.schema.json`](../manifests/core-track-source-snapshot.schema.json)
- [`spruce-core-branch-bases.schema.json`](../manifests/spruce-core-branch-bases.schema.json)
- [`spruce-release-roster.schema.json`](../manifests/spruce-release-roster.schema.json)

`catalog-check` validates the live track and tuning registries alongside the
catalog, exact Spruce branch comparison bases, historical release correlation,
and every referenced build pin through the authoritative lifecycle validator.
`core-track-inventory` repeats those gates and fails on stale hashes, malformed
or overlapping pinned/deferred cells, tuned-as-universal pins, unknown cores,
an unproved child-source ordering edge without exact outlier authorization, a
same-commit/different-tree inconsistency, or unsupported selector spelling.
