# Build harness consolidation

Status: complete local-only long-horizon migration. H0-H7, the first H3
production transition, and the post-Gambatte generation-two authority
transition are complete. Publication remains disabled.

## Purpose

The pipeline has strong fail-closed checks, but campaign orchestration has
grown by copying executable generators and adapting earlier private functions.
That makes a small authority refresh depend on thousands of lines of inherited
Python, mutable module state, repeated transaction code, and hand-maintained
provenance constants.

The replacement is one tracked, versioned harness engine driven by small
declarative transition records. Historical evidence and codecs remain
immutable. New campaign work must not add executable Python under
`.local-e2e/`.

## Architectural boundary

The harness is a functional core with an imperative shell:

1. Strictly decode and authenticate immutable inputs.
2. Resolve a declarative intent into one immutable plan.
3. Run an ordered graph of named checks against that plan.
4. Stage content-addressed immutable objects.
5. Commit authority by replacing one small compare-and-swap pointer.
6. While the transaction lock is still held, emit durable post-commit evidence
   that names the exact plan, checks, inputs, outputs, and selected pointer.

The store is byte-opaque. Legacy matrix codecs, strict campaign records, and
future normalized roots are caller-owned validators over authenticated byte
snapshots; the transaction owner never imports a domain codec or derives
campaign content. This lets the existing legacy matrix pointer remain H3's
sole commit point while `StateRoot` is introduced as immutable evidence, not a
second mutable authority.

Declarative data says what is authorized. One reviewed engine says how the
authorization is validated and committed.

The four central records are:

- `CoreSpec`: reviewed source, build, target, contract-engine, and exceptional
  proof parameters for one core.
- `TransitionPlan`: resolved predecessor, immutable input references, exact
  allowed delta, required checks, engine bundle, and predicted output.
- `Receipt`: one validator or executor's exact plan, input, output, log, and
  result identities.
- `StateRoot`: an immutable track, freeze, or matrix root selected by one small
  mutable pointer.

## Non-negotiable invariants

- Existing raw bytes, semantic digests, schemas, and historical generators are
  never rewritten to fit the new engine.
- New identity JSON uses duplicate-key rejection, sorted compact UTF-8 bytes,
  `allow_nan=False`, strict JSON scalar types, and no floats. Comparisons use
  canonical bytes, not Python equality (`3`, `3.0`, `false`, and `0` must not
  alias).
- Observed live audit counts are report-only. A semantic object may bind a
  fixed floor, frozen prefix, and selected entries, but never a moving tail
  count.
- Reads reject path escape, symlink traversal, non-regular inputs, unexpected
  modes/link counts, and byte or semantic identity drift.
- Exactly one transaction implementation owns mutation and locking. Apply
  reauthenticates every input under one exclusive lock, creates immutable
  objects with no-follow/create-only semantics, fsyncs files and directories,
  validates the candidate closure, and replaces the pointer as its final
  authority mutation. Passed post-commit evidence and the immutable StateRoot
  are created only after the new pointer is visible. The transaction is not
  successful until both are durable and validated; a later failure restores
  the owned pointer while retaining unreachable immutable evidence.
- A valid content-addressed object published before a later failure is retained
  as an unreachable, immutable staging object. Retry verifies and reuses it;
  the transaction never needs reference counting or compensating CAS deletion.
  Only owned temporary files and an owned pointer replacement are rollback
  surfaces.
- Prewrite validation expects the old pointer. Postwrite validation expects the
  new pointer while authenticating the old immutable snapshot and CAS object.
- A failed transaction may remove only exact objects/inodes it created. A
  foreign replacement is preserved and reported.
- Transaction serialization assumes cooperating local writers use the one
  campaign lock and that untrusted principals cannot mutate the state
  directories.  The store reauthenticates lock and pointer inodes at every
  observable boundary and preserves a detected foreign replacement.  Portable
  POSIX APIs do not provide an atomic compare-by-inode-and-unlink operation, so
  a privileged or out-of-protocol writer racing the final checked syscall is a
  filesystem-permission threat, not a supported transaction participant.
- A missing, skipped, unknown, or environment-gated required check cannot be
  reported as a pass.
- Publication, deployment, device mutation, and external-service mutation are
  not harness operations.

## Package target

```text
scripts/core_pipeline_lib/
  campaign/
    json_wire.py      strict identity JSON and canonical delta comparisons
    model.py          immutable references, specs, plans, receipts, state roots
    store.py          no-follow reads, CAS objects, and pointer transaction
    validate.py       ordered phase-aware validators and stable check results
    transition.py     pure legacy-matrix planning and validation
    workflow.py       check/stage/commit/verify orchestration and receipts
    cli.py            thin consolidated campaign command entry point
    check_adapter.py  registered-check campaign evidence and receipts
    transition_model.py  generic strict transition records and validation
    transition_registry.py  static code-owned transition policies
    phase_freeze.py   strict PhaseFreeze planning and validation
    matrix_model.py   normalized strict cell, shard, and root records
    matrix_materialize.py  pure summary, expansion, and legacy-byte derivation
    matrix_store.py   prevalidated cell-to-shard-to-root persistence/hydration
  checks/
    registry.py       stable check IDs and tier graph
    runner.py         subprocess isolation, complete logs, JSON/JUnit results
    service.py        exact local subprocess and artifact capture boundary
    artifacts.py      authenticated structured-output parsing and binding
  core_spec.py        strict normalized 98-core identity and proof bindings
  immutable_evidence.py  verified snapshots and create-only evidence storage
  pipeline_inputs.py     catalog, policy, toolchain, and host input contracts
  catalog_contracts.py   build-contract and native catalog dispatch
  catalog_validation.py  catalog, source-candidate, ELF, and workflow checks
  candidate_models.py    tuning, output, and host-reproduction records
  build_contracts.py     compile, dependency, and log-proof contracts
  build_recipes.py       deterministic shell and container recipe rendering
  build_execution.py     group planning, provenance, and local execution
  evidence_validation.py live evidence and artifact validation
  stored_evidence.py     immutable stored-evidence validation
  pin_lifecycle.py       pin, source, and compatibility lifecycle
  release_lifecycle.py   release, channel, promotion, and package lifecycle
  cli/
    catalog_build.py       catalog/build command handlers
    track_commands.py      track transaction command handlers
    promotion_commands.py  promotion command handlers
    full_release_commands.py  full-release command handlers
```

`scripts/core_pipeline.py` remains the stable CLI composition root and
compatibility facade. Its declarative registry installs exact-signature
facades whose reviewed targets and dependency factories are resolved at call
time. New domain logic and new callers belong in the public library modules,
not in handwritten launcher branches.

## Lifecycle

- `check`: read-only resolution, validation, predicted delta, and plan digest.
- `stage`: consume an exact plan digest and create immutable objects or build
  receipts without changing a current pointer.
- `commit`: consume exact staged receipts and the expected-current identity,
  then perform the single-pointer transaction.
- `verify`: deeply validate any plan, receipt, immutable closure, or current
  pointer.

Resume uses receipts and plan identities, not executable inheritance or a
filename chronology.

### H3 command boundary

The pilot exposes exactly four verbs through
`python3 -m scripts.core_pipeline_lib.campaign.cli`: `check`, `stage`,
`commit`, and `verify`. `check` and `stage` require
`--process-receipt-ref`; `commit` requires `--staged-receipt`; and `verify`
requires `--state-root`. Each option names a canonical repo-relative file
containing an immutable `artifact` envelope whose exact bytes are one strict
`EvidenceRef` document. The campaign helper creates this envelope only after
the referenced object authenticates, so resume needs no shell redirection or
ad hoc file write. There are no generator, script, publication, build, Git,
audit, or external-action options.

The read-only library entry point `predict_transition(store)` authenticates
the fixed spec, engine, schema, predecessor, and freeze, enforces the live
engine identity, and returns the fully validated `TransitionPlan` without a
receipt or state write. That breaks the production dependency cycle: H4 runs
with `TransitionPlan.content_sha256` as its exact subject, stores the resulting
process receipt, and only then can H3 `check` or `stage` bind that receipt.

The H4 process receipt remains a separate wire model. Its authenticated
rendering is staged as byte-opaque `check-log` evidence by the outer H4
adapter. H3 does not import or reinterpret H4 records: it requires that exact
reference and places the same reference, with no omission or substitution, in
all six campaign semantic check results. The semantic passes come from the H3
transition validator; the H4 receipt records process provenance only.

`check` writes nothing. Its stdout reference is explicitly reported as a
predicted, not-yet-staged plan identity. `stage` copies the authenticated spec,
engine bundle, schema, predecessor, and freeze into canonical immutable store
objects; stages the successor, exact two legacy aliases, plan, and only the
`check`/`staged` receipts; and prints the exact staged-receipt reference.
Fixed tracked input paths remain plan provenance but are not the durable byte
source for later verification.

`commit` consumes that staged reference. Its locked pre callback creates the
pre-commit receipt only after re-planning against the old pointer and immutable
copies. Its post callback creates the post-commit receipt and first-generation
StateRoot only after the successor pointer is visible and the closure has been
revalidated. The reference topology is acyclic:

```text
StateRoot -> post-commit -> pre-commit -> staged -> check
```

`verify` consumes the exact StateRoot reference, authenticates that full
immutable chain from staged CAS copies, and requires the exact live successor
pointer under the existing shared campaign lock. It never treats the
StateRoot alone as authority. Historical verification does not compare an old
engine bundle to the current tracked source tree, so later compatible harness
additions do not invalidate committed evidence; stage and both commit
callbacks do perform that live comparison before mutation is accepted.

## Phased migration and acceptance

### H0 — boundary and characterization

- Record this architecture and the measured legacy boundary.
- Preserve held campaign generators and current sealed authorities unchanged.
- Add regression cases for every recent generator failure class.

The 2026-08-14 baseline is 21,621 lines in `scripts/core_pipeline.py` plus 77
ignored campaign Python files totaling 5,789,294 bytes and 143,092 lines. Of
those ignored sources, 30 freeze generators total 1,257,756 bytes and 11 matrix
generators total 1,055,394 bytes. These are preserved evidence, not migration
inputs or templates. The replacement grows only under the tracked library and
test trees, and new campaign authority is data rather than executable source.

Acceptance: the work manifest names every later tranche, the post-Gambatte
freeze/matrix split is accurate, and no replacement generator exists.

### H1 — canonical wire model

Status: complete. The strict wire/model boundary passed 46 focused checks and
two independent inert reviews.

- Add strict identity JSON, exact canonical comparisons, typed immutable
  references, transition specs/plans, receipts, and state-root records.
- Characterize duplicate keys, non-finite numbers, floats, scalar aliases,
  Unicode, stable rendering, exact keys, and closed reference shapes.

Acceptance: focused tests pass with no cache/bytecode artifacts and existing
record codecs remain unchanged.

### H2 — one store and transaction owner

Status: complete. The final byte-opaque store and transaction owner passed 71
focused fault/boundary checks plus independent inert review, including the
no-follow bootstrap snapshot seam.

- Add no-follow authenticated reads, content-addressed object creation, one
  pointer lock, compare-and-swap, pointer-last commit, and receipts.
- Inject failure at every create/fsync/validate/replace boundary and prove
  ownership-safe cleanup and foreign-replacement preservation.

Acceptance: all fault-injection cases pass in temporary roots; no production
state is mutated.

### H3 — declarative transition pilot

Status: complete. The legacy finite-float codec, exact RFC 6901 projection,
pure transition planner, generic four-verb imperative shell, and production
commit/verification are complete. The exact production identities are
recorded below.

- Express the post-Gambatte authority-only matrix refresh as data.
- Pure planning must deep-copy the authenticated `9119385c` predecessor,
  preserve all 2,538 supported cells and 108 exclusions byte-semantically, and
  update only the reviewed root/input authority fields for freeze `0c57e201`.
- Keep the finite-float legacy matrix codec separate from strict new campaign
  records. Delete exactly the seven authorized RFC 6901 leaves to form the
  preserved projection; its authenticated compact legacy-JSON SHA-256 is
  `05ef400c659b28933354d6e952c5be643d41465531f7615e9b1157eeafd24d07`.
  The legacy 11 check IDs remain schema evidence, while the six new plan checks
  authorize the transition; neither ledger embeds a moving audit tail.
- Shadow-check first, then temp-root commit/verify. A production commit requires
  the exact reviewed plan and a fresh precommit reauthentication.
- Stage only check/staged receipts. The passed pre-commit receipt is created
  inside the locked pre-commit callback; the passed post-commit receipt and
  immutable StateRoot are created only inside the post-commit callback after
  the exact successor pointer is visible. A StateRoot never authorizes a
  transition by itself: committed verification also authenticates the live
  pointer under the campaign lock.
- Stage the consolidated immutable successor and, through the same store
  primitive, create-or-verify the two legacy compatibility aliases named by
  the preserved matrix hash model: the semantic snapshot and raw matrix CAS.
  The pure planner derives their exact references; it never writes them.  The
  mutable legacy campaign-matrix file remains the only pointer.

Acceptance: the plan is deterministic, an independent reconstruction agrees,
and the legacy 40 MB materialization has exact predicted bytes. Held matrix
v1/v2 remain unexecuted and no matrix-v3 generator is created.

### H4 — one check front door

Status: complete. The registry, isolated runner, and campaign check adapter
provide one stable front door. The recorded full-static run completed in
920.478 seconds with 1,546 passes and two preserved environment-gated skips,
below the 1,009.085-second acceptance ceiling.

- Register stable check IDs and tiers (`quick`, `static`, `evidence`,
  `rebuild`).
- Initially wrap existing commands in isolated subprocesses without changing
  their semantics. Preserve full stdout/stderr, duration, subject, phase, and
  result in structured output.

Acceptance: every documented mandatory check maps to one stable ID; required
skips fail the claimed tier; full static runtime is no worse than 1.10 times
the 917.35-second baseline and adds no skips.

### H5 — core specs and generated mechanics

Status: complete. The generic strict-transition, `CoreSpec`, and `PhaseFreeze`
surfaces closed with 90 focused passes. The normalized catalog covers all 98
distinct core identities, with proof bindings partitioned into 89 registered
log-contract bindings and nine legacy-validator bindings.

- Move common contract parameters to reviewed `CoreSpec` data evaluated by the
  existing handwritten proof engines.
- Keep exceptional proof plugins pure and narrow. Generate aggregate catalog,
  registry, documentation tables, and thin workflow owners with drift checks.

Acceptance: all 98 cores retain distinct identities and required negative
oracles; common contract-test volume drops without losing a check ID.

### H6 — normalized matrix storage

Status: complete. The strict normalized model, deterministic materializer, and
store form a closed immutable seam. The one-shot stage created exactly 2,745
objects in dependency order: 2,646 cells, 98 shards, then one root. Its
canonical root `EvidenceRef` has content SHA-256
`a2054e8f56e9f3c0d54768e7d6f5229a66490bff7a62fde5c0d41f0e3a52d5e2`,
target semantic SHA-256
`3a5f769f2fab18cb1177c59728b2dc12084dd0ba4f5be11ca929b69a93b9e94d`,
raw SHA-256
`a678088790bb1fa65a9f8421361191e7836fd2892a25dae745368dd2e5bc753a`,
and size 131,790 bytes. Recursive root-only hydration reproduced the exact H3
legacy matrix at semantic/raw
`a9194ec841924410fcb544ff28fd0c5cf97e6bbf507c08aeda24ecb93cee412d`
/ `7a402f0295c49a339aeaf458662beb9f6165e0dee4ff056f62ee9b981c211381`
as 40,405,538 exact bytes with all 2,538 supported and 108 excluded
coordinates. Staging and independent verification left the live legacy pointer
and its inode metadata unchanged; the normalized store creates neither a
mutable pointer nor an index.

- Introduce content-addressed root, shard, and cell objects plus a deterministic
  legacy materializer.
- Treat summaries as derived views rather than authority.

Acceptance: historical fixtures materialize byte-for-byte; an authority-only
refresh changes only a root; a cell transition changes only its shard and
root; coordinate coverage remains exactly 2,538 supported and 108 excluded.

### H7 — launcher extraction and closeout

Status: complete. Eight domain/handler extraction waves plus the declarative
facade/import closeout reduced `scripts/core_pipeline.py` from the H0 baseline
of 21,621 lines to 1,593 lines and 61,234 bytes (SHA-256
`4abe0aa46fb5a1f288126dcc81d876568ec878f1585b53da5e16f43a355bd23f`).
That removes 20,028 lines, or 92.6 percent, from the composition root.

- Extract catalog, build planning/execution, evidence, promotion, and command
  handlers behind public services.
- Retain only CLI composition and compatibility adapters in the launcher.
- Generate 277 exact compatibility facades from one code-owned registry. Each
  facade resolves its leaf target and dependency factory afresh, closes over
  routing state rather than exposing hidden override parameters, and rejects
  caller-supplied service, I/O, resolver, and routing controls.
- Route the 98 per-core tests through `tests/cores/support.py` and the common
  contract family through `tests/core_contract_helpers.py`. Preserve only the
  eight tests that deliberately load a fresh launcher module for isolation.
- Enforce the compatibility budget structurally: the final tree has 16 test
  loader files and one production compatibility bridge, 17 total, with an AST
  test requiring fewer than 20 and an explicit retained-loader allowlist.

Acceptance: `core_pipeline.py` crossed below 5,000 lines at the handler
milestone and is below 2,000 at completion; fewer than 20 compatibility/CLI tests
import it; milestone checks pass and the architecture/TODO/audit agree. The
final post-repair repository suite passed 1,838 tests with the same two
intentional environment-gated skips and no failures in 1,028.54 seconds.
Independent review exhaustively approved all 277 target/factory routes, all
private-injection rejection paths, the final import graph, and the absence of a
reverse launcher dependency or cycle.

## Production transitions

### Generation-one pilot

The sealed post-Gambatte Phase-1 freeze is semantic/raw
`0c57e20111a6c704c1481993f60fcce0b58cf1c52b00cbd4b969aab18fb7de1c`
/ `6bdeb20ef855ceb47e2825726edb7280953e60f883f2e45d716c6c0c03d2f70f`.
The predecessor matrix semantic/raw identity was
`9119385c8d6b57fb4800ad1bc9248ecef2071f54af9e5c8faa5534969dbd8601`
/ `2dac212759e6c55b0351019c5d3a7471a6256fdf8eb25b0df51e36183e545940`.
The consolidated H3 transaction committed and independently verified its
authority-only successor at semantic/raw
`a9194ec841924410fcb544ff28fd0c5cf97e6bbf507c08aeda24ecb93cee412d`
/ `7a402f0295c49a339aeaf458662beb9f6165e0dee4ff056f62ee9b981c211381`.
The immutable generation-one StateRoot is semantic/raw
`ec7c4915240f4e7944fbe112abeb07d4f9b031ac5166aee2bdabb0e1d5e95415`
/ `136ec08e6f0efeca53718217298d1ad6d36eb7e0b0e4a41079a1902240399612`.
The predecessor snapshot and CAS remain immutable, the successor pointer and
two compatibility aliases are byte-identical distinct inodes, and both the
API and the four-verb CLI verifier pass under the campaign lock.

H5 built on that proven consolidated commit path with a separate generic
strict-transition family, `CoreSpec`, and PhaseFreeze v1 rather than widening
the matrix-specific H3 records or reviving historical executable generators.
H6 persists a normalized immutable view and reproduces the legacy bytes; it
does not rewrite historical evidence, select new authority, or enable
publication.

The H3 matrix at semantic/raw SHA-256 `a9194ec841924410fcb544ff28fd0c5cf97e6bbf507c08aeda24ecb93cee412d`
/ `7a402f0295c49a339aeaf458662beb9f6165e0dee4ff056f62ee9b981c211381`,
the H6 root at raw/semantic/reference SHA-256
`a678088790bb1fa65a9f8421361191e7836fd2892a25dae745368dd2e5bc753a`
/ `3a5f769f2fab18cb1177c59728b2dc12084dd0ba4f5be11ca929b69a93b9e94d`
/ `a2054e8f56e9f3c0d54768e7d6f5229a66490bff7a62fde5c0d41f0e3a52d5e2`,
and the StateRoot at raw/semantic SHA-256
`136ec08e6f0efeca53718217298d1ad6d36eb7e0b0e4a41079a1902240399612`
/ `ec7c4915240f4e7944fbe112abeb07d4f9b031ac5166aee2bdabb0e1d5e95415`
are now immutable predecessor/generation-one evidence.

### Post-Gambatte generation-two closeout

The repaired combined authority plan is raw/semantic/reference SHA-256
`80a9193c2cf608fd99840a47f64227fecb31134b9505b33ad0583f05266c0582`
/ `24ec2b6d636d2dcf7cdaab92209aa628d4b827520303363dd343a42363a8f8af`
/ `22bb9e4c38ea3a4dadace79a15251076e0e01b063eb8a250b836d718a738221d`.
Its accepted H4 receipt passed all ten required checks. The byte-opaque check-log is
raw/reference SHA-256
`700ee85b28f27f12ad96215761279ad98b288c038ec0a83be6fca4f78408a2bd`
/ `2aa05b15fd63c7ea562d5193382ea7ae4ac88431d9545eb2a727bde2af4e4fb4`;
the full-static check passed 1,897 tests with the two expected
environment-gated skips and produced JSON/JUnit SHA-256
`8c137f54b0e8de09845a899a26a0866b90749134ed61f935984a080646bbdc29`
/ `e0243cb1d620c1b251e84da15771c47bab3b9ac1098c7219b82479f44afed089`.

The deeply reloadable staged receipt was published last at
raw/semantic/reference SHA-256
`48654d504c3878a6776c797343ddf51dc5d4caa92cd23834f40cea020d464fb9`
/ `b2c97a1420fbddadd4ea6d21f7f261bcf01e8c0602aa7d009d37a79b1b093050`
/ `c880630b41511e92d2ba74939e304274f46b6957763f0015799b8b66a931b7f7`.
The H5 PhaseFreeze successor is raw/semantic SHA-256
`099c57183bd780d94a1d59666e89f8770e4dfca73ab011a41b49016240ee7502`
/ `8b22a58f85e4bfe75214e3e00f7437caa07a5e0d376bd5055717af72b39a1cac`;
the refreshed normalized H6 root is raw/semantic SHA-256
`c9e45411c33a9de6cc47ae3d2052b5d2282439a4b1cd5873285b0667e590a271`
/ `8f3c8faac63d4a01ce2fbceb7639107ef0385d6ede2f4d9071f68007c5cebcf4`.

After independent staged reauthentication, one commit created the pre-commit
receipt at raw/semantic/reference SHA-256
`321f53a33068a5c597b5bd61d82ec96e98a48df48cb8a804e08fe89e485fd18f`
/ `d05598394fa343aeb5905f7040eaee01a67439ca11d573a39123f14d28c34a4b`
/ `c2d0859503a2deb4e81ce3c0d73a7c1f2d5a553675346f3ea938a40c4fdd32ef`,
then the post-commit receipt at raw/semantic/reference SHA-256
`950468c4448225eda53f1b9b74c4034440e3fea08f7b063bfc8653a20ba93a22`
/ `bd63eae6e11e10a71389cada3ab6427bf0167709a81d88c8d79a3e88beaa1d14`
/ `a086da74d84972f0ff2d68a3c5dc8d8ec3d4a6affbbe6a2c760898f98618540f`.
The live legacy pointer is the exact raw/semantic successor
`d7931f38f64a0592638ba2f00d312088f1836be391dc361e8f0d8e6d6f031ab9`
/ `5c57d8cef907ee25d5ea526e95a83d2299a0a7428d50971c985cae6f09d590d9`.
The resulting generation-two StateRoot was deeply verified at
raw/semantic/reference SHA-256
`bb90d97971e275867408d5a2c4427159779e4cd9bcc93bfdd49460298123ba9d`
/ `156956ac39723f13166d0c84359f213eec73d3640554349173dcececf9df4ee6`
/ `c79042e266f503207c4cd95426394154dde8a6fb0420fa73ec7eb2813434959f`.

The closed snapshot has Main effective TEST 12 / deferred 86; Nightly
effective TEST 12 / deferred 86 with 11 direct TEST assignments; Edge TEST 11
/ deferred 87; and Stable zero. Its normalized coordinates are 315 admitted,
2,223 deferred, and 108 unsupported. The remaining 86 cores need fresh
hardened proof, ranked `freechaf`, `mednafen_lynx`, then `mednafen_ngp`.
Stable promotion and publication remain separate authorization gates, and
publication remains disabled. The authority-source checkpoint was `7a95aa8`;
this generation-two evidence and its closeout documentation remain local-only
and unpushed.
