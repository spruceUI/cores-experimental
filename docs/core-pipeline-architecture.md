# Core pipeline Python architecture

`scripts/core_pipeline.py` is the stable executable and composition root.
New implementation code belongs in `scripts/core_pipeline_lib/`; do not add a
new core, runner, or policy by growing another branch in the launcher.

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

Cap32, CrocoDS, Genesis Plus GX, Genesis Plus GX Wide, Snes9x, Snes9x 2005,
Snes9x 2005 Plus, Mednafen Supafaust, Mednafen Virtual Boy, Mednafen
Lynx, Mednafen PCE Fast, Mednafen SuperGrafx, Mednafen WonderSwan, Mednafen
PC-FX, PokéMini, Potator, Gearboy, Gearsystem, GearColeco, fMSX, blueMSX,
VICE x64,
VICE xvic, O2EM, FreeChaF,
VecX, LowRes NX, RACE, 2048, and EightyOne follow this layout.
Their shared mechanics live in neutral helpers; their source identities and registered
proofs do not share a file or registry entry. Mednafen Supafaust's
`mednafen-supafaust-cxx-link-v1` contract is owned by
`contracts/mednafen_supafaust.py` and proves the exact 44-command C++ compile
set per ABI, `GIT_VERSION` scope, link inputs/options, and ordered ABI-specific
diagnostic streams while permitting valid parallel-stream interleaving.
O2EM's `o2em-c-only-v1` contract lives in `contracts/o2em.py`; it preserves
the absence of an injected catalog version, binds upstream's native
leading-space short hash on 42 C compiles, proves the exact C link, and rejects
compiler, linker, and process failures.
FreeChaF's `freechaf-c-only-v1` contract lives in `contracts/freechaf.py`; it
also binds the exact recursive libretro-common gitlink, the native leading-space
short hash on 25 C compiles, the exact C link, and its single reviewed warning.
VecX's `vecx-software-c-only-v1` contract lives in `contracts/vecx.py`; it
requires `HAS_GPU=0`, binds the native leading-space short hash on four exact C
compiles, proves the complete ordered link command, binds the reviewed metadata
replacement, and rejects GPU or GL-family build inputs.
LowRes NX's `lowresnx-c-only-v1` contract lives in `contracts/lowresnx.py`; it
binds the native leading-space short hash on 43 exact C compiles, both reviewed
source/object orderings, every ABI-specific compiler invocation, the complete
ordered link command, and the reviewed metadata replacement while rejecting
unreviewed diagnostics and semantic path aliases.
RACE's `race-c-only-v1` contract lives in `contracts/race.py`; it binds the
native leading-space short hash on 27 exact C compiles, the complete ordered C
link, exact source and success framing, and a zero-diagnostic envelope for both
ABIs. Its compatibility owner treats `ngpBios.c` as compiled internal source,
not a packaged or required external firmware blob.
Potator's `potator-c-only-v1` contract lives in `contracts/potator.py`; it binds
native leading-space version ` 227c5f6` to eight exact C compiles, proves the
complete ordered C link and source/success framing, and admits only the four
reviewed misleading-indentation CPU warning/note pairs before that link.
Gearboy's `gearboy-mixed-language-v1` and Gearsystem's
`gearsystem-mixed-language-v1` contracts live in their matching core modules.
They bind exact native `git describe` values to all 40 and 46 mixed-language
compiles respectively, prove the complete ordered C++ links, and require zero
diagnostics. Their ordered preambles additionally bind the clone, detached
HEAD, native-version marker, toolchains, clean/build job count, compile block,
link, copy, and success trailer; setup mutation, wrapper compilers, response
files, and shell indirection fail closed.
2048's `core-2048-c-only-v1` contract lives in `contracts/core_2048.py`; the
numeric-safe module name owns the exact pinned source identity, native-version
16-command C compile trace, ordered C link, and zero-diagnostic envelope for
both ABIs. Its canonical one-core pin and source set select the promoted
simulated-Actions evidence; the compatibility record separately binds the
byte-identical native-local reproduction. The resulting artifacts remain
static-build-only and cannot admit a device view without runtime evidence.
EightyOne's `core-81-mixed-language-v1` contract lives in
`contracts/core_81.py`. It binds the exact 16 C and 12 C++ invocations, ordered
C++ link and version script, exact ordered per-source diagnostic streams, and
the SHA-256 of `src/version.c` after upstream Make generates it from the pinned
commit. The
catalog `build.generated_source` field is normalized into build records,
provenance identities, schema-v10 recipe snapshots, and promoted goldens; the
pipeline never supplies `GIT_VERSION` or patches that source. Selected and
independent runs reproduce the package, metadata, and ABI artifacts exactly;
their raw logs intentionally differ only in permitted parallel diagnostic
interleaving. The resulting canonical evidence remains static-build-only.
Mednafen Virtual Boy's `mednafen-vb-mixed-language-v1` contract lives in
`contracts/mednafen_vb.py`. It binds native leading-space version ` 38e7a0e`
to all 10 C and three C++ compiles, proves the ordered 13-object C++ link,
requires a diagnostic-clean ARM64 build, and admits only the two exact reviewed
GCC psABI notes on ARMHF.
Mednafen Neo Geo Pocket's `mednafen-ngp-mixed-language-v1` contract lives in
`contracts/mednafen_ngp.py`. It binds native leading-space version ` a50d5ac`
to all 32 C and five C++ compiles, proves the ordered 37-object C++ link, and
requires exactly three reviewed missing-braces warnings on both ABIs plus two
reviewed GCC psABI notes on ARMHF. Parallel builds may place the two complete
diagnostic blocks in either order, but may not split, mutate, or move them past
the final link.
Mednafen Lynx's `mednafen-lynx-mixed-language-v1` contract lives in
`contracts/mednafen_lynx.py`. It binds native leading-space version ` fcdefcf`
only to the 16 C++ compiles, requires all 13 C compiles, and proves the complete
ordered 29-object C++ link. Each ABI requires its exact truncation warning and
associated note; ARMHF additionally admits only the two reviewed GCC 7.1 psABI
notes. Its two complete diagnostic blocks may appear in either order but may
not split, mutate, or cross the link boundary.
Mednafen PCE Fast's `mednafen-pce-fast-c-only-v1` contract lives in
`contracts/mednafen_pce_fast.py`. It requires exactly 92 C compiles, rejects C++
compiles and injected or native version tokens, proves the complete ordered
92-object C++ link and exact source/success framing, and rejects every warning,
note, error, and fatal diagnostic.
Mednafen SuperGrafx's `mednafen-supergrafx-mixed-language-v1` contract lives in
`contracts/mednafen_supergrafx.py`. It binds native leading-space version
` 3c6fcd3` only to the 29 C++ compiles, requires all 60 C compiles, proves the
complete ordered 89-object C++ link, and accepts only its exact reviewed
diagnostic streams. Occurrence-aware stream assignment binds every diagnostic
block—including repeated `zlib_codec_init` headers—to its owning source compile
before permitting valid parallel interleaving.
Mednafen WonderSwan's `mednafen-wswan-mixed-language-v1` contract lives in
`contracts/mednafen_wswan.py`; Mednafen PC-FX's
`mednafen-pcfx-mixed-language-v1` contract lives in
`contracts/mednafen_pcfx.py`. Each owns its exact source, native version,
mixed-language compile set, C++ link, and reviewed diagnostics independently.
PC-FX additionally owns the typed `IS_X86=0` host-specialization guard so
host-x86 inference cannot select ARM-incompatible x86/SSE paths. Its proof
requires 60 C and 34 C++ compiles, scopes the native leading-space version to
the C++ commands only, proves the ordered 94-object C++ link, and admits only
reviewed per-stream ordering under parallel log interleaving. That policy is
not a shared Mednafen-family setting.
PokéMini's `pokemini-c-only-v1` contract lives in `contracts/pokemini.py`; it
owns the exact native version on every C compile, the complete C compile and
link command identities, and the reviewed per-ABI diagnostic streams.
GearColeco's `gearcoleco-mixed-language-v1` contract lives in
`contracts/gearcoleco.py`; it owns the exact native `git describe` value on its
mixed C/C++ compile set, ordered C++ link, build-complete marker, and reviewed
per-ABI warning stream.
fMSX's `fmsx-c-only-v1` and blueMSX's `bluemsx-mixed-language-v1` contracts
live in separate core modules. fMSX proves its exact 31-command C compile set,
native version scope, ordered C link, and an unsuppressed zero-diagnostic
build; blueMSX proves its exact 255-C/14-C++ compile set, C-only native-version
scope, ordered C++ link, and exactly one upstream `-w` on every compile. Its
zero emitted diagnostics prove suppression consistency, not warning-free
source code.
Snes9x 2005's `snes9x2005-c-only-v1` contract lives in
`contracts/snes9x2005.py`; it owns the base core's exact 35-command C compile
set, native leading-space version, file-origin `USE_BLARGG_APU=0` default,
ABI-specific invocations, ordered C link, and reviewed 12-warning/12-note
diagnostic stream. Its parallel-log parser admits whole-block interleaving but
preserves every diagnostic block's exact members and order. Snes9x 2005 Plus's
`snes9x2005-plus-c-only-v1` contract lives in
`contracts/snes9x2005_plus.py`; its 33-command C build, direct
`-DUSE_BLARGG_APU` compile flag selected by make variable
`USE_BLARGG_APU=1`, ABI-specific invocations, ordered link, and reviewed
diagnostics belong to a separate per-core lifecycle. Sharing the upstream
source commit with the base core does not merge their build identity, pin,
compatibility record, release, or channels.
Cap32's `cap32-c-only-v1` contract lives in `contracts/cap32.py`; it composes
the CPC Make-trace proof with exact 44-pair source/object and ABI-specific
compiler-argv fingerprints, native version ` 4abfb8b`, exact normalized/raw
link objects and ordered link invocation, zero diagnostics, and an exact
success trailer. Parallel line ordering may vary without weakening any of
those identities.
CrocoDS's `crocods-c-only-v1` contract lives in `contracts/crocods.py`; it
proves the exact 50-pair C compile set and ABI-specific invocations, native
version ` 87bbb3d`, the complete ordered C link, binary version marker, and
success trailer. Its ARM64 admission preserves five exact diagnostic streams
containing nine warnings and seven notes, while ARMHF admits no diagnostics;
parallel complete-line ordering may vary without changing those identities.
Genesis Plus GX's `genesis-plus-gx-c-link-v1` contract lives in
`contracts/genesis_plus_gx.py`; it proves the base core's exact 117-pair C
compile set and ABI-specific invocations, native version ` fa4dca5`, complete
ordered C link, binary version marker, and success trailer. Its ARM64
admission preserves exactly two reviewed warnings and one note, while ARMHF
admits no diagnostics; complete-line ordering may vary without weakening the
proof. Genesis Plus GX Wide retains a separate contract and now owns its own
pin, compatibility record, release, and channel lifecycle.
Genesis Plus GX Wide's `genesis-plus-gx-wide-c-link-v1` contract lives in
`contracts/genesis_plus_gx_wide.py`; it independently binds its forked source,
106-pair C compile set and ABI-specific invocations, raw and ordered C link,
native version ` 29d9d10`, reviewed ARM64 diagnostic streams, diagnostic-free
ARMHF build, complete log-line multiset, and terminal copy/success framing.
The ordered prelude is exact except that the same positive `-jN` value on its
reviewed clean and build commands is canonicalized as non-semantic scheduler
capacity; spelling, equality, surrounding argv, and phase position remain
fail-closed. The Base proof applies the same bounded rule.
Its immutable historical oracles remain test-only inputs, not promotion
evidence. Fresh core-named schema-v2 runs supplied its independent lifecycle
record; the historical logs were not promoted.
VICE x64's `vice-x64-mixed-language-v1` contract lives in
`contracts/vice_x64.py`; it owns its deployable identity, exact native-short10
and epoch contract, 564-command mixed-language compile set, ordered C++ link,
and zero-diagnostic proof independently of other VICE machines.
VICE xvic's `vice-xvic-mixed-language-v1` contract likewise lives in
`contracts/vice_xvic.py`; its exact 428-C/10-C++ compile set, VIC-20 machine
definition, ordered C++ link, zero-diagnostic proof, and build evidence are not
routed through a VICE-family facade.
Historical paired pin and run chronology was retired to git history on
2026-07-23. Active work is organized by individual core files and
semantic IDs, never by historical grouping.

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

Handy, Stella 2014, FCEUmm, Gambatte, TGB Dual, QuickNES, Nestopia, A5200,
ProSystem, Snes9x, Mednafen Supafaust, Mednafen Virtual Boy, Mednafen Neo Geo
Pocket, Mednafen Lynx, Mednafen PCE Fast, Mednafen SuperGrafx, Mednafen
WonderSwan, Mednafen PC-FX, PokéMini, Potator, Gearboy, Gearsystem, GearColeco,
VICE x64, VICE xvic, fMSX,
blueMSX, Snes9x 2005, Snes9x 2005 Plus, Cap32, CrocoDS, Genesis Plus GX,
Genesis Plus GX Wide, O2EM, FreeChaF, VecX, LowRes NX, RACE, 2048, and
EightyOne are current owners under this model.
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

The current pending set is Atari800, FBNeo, MAME 2003-Plus, and PicoDrive.
FBNeo's core module already binds its exact source, native version/date tuple,
command-scoped Make invocation, and ARMHF header-compatibility definitions, but
intentionally does not register a complete build-log oracle. Its retained
controls predate the finalized provenance markers and its ARMHF artifact needs
`GLIBCXX_3.4.29`; neither those controls nor the pending record admit a pin,
release, channel, runtime, or device claim.

Mednafen Supafaust's current semantic ID is
`mednafen_supafaust-2b93c0d7dff5-21be3575be39`. Its pin and source set use
that exact individual-core ID; its compatibility and lifecycle owners are
`manifests/compatibility/mednafen_supafaust.json` and
`tests/cores/test_mednafen_supafaust.py`; and its exact build proof remains in
`tests/test_contract_mednafen_supafaust.py`. The selected
`actions-sim-build-core-mednafen_supafaust-v2` and reproduction
`build-core-mednafen_supafaust-local-v2` run IDs are individual-core evidence,
as are `.local-e2e/channels/<channel>.mednafen_supafaust.json` aliases. New
canonical contract, pin, manifest, test, and run identities must retain this
individual-core ownership.

Mednafen Virtual Boy's current semantic ID is
`mednafen_vb-38e7a0ec9ac7-20575c76c389`. Its independent owners are
`scripts/core_pipeline_lib/contracts/mednafen_vb.py`,
`pins/core-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json`,
`pins/source-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json`,
`manifests/compatibility/mednafen_vb.json`, `tests/cores/test_mednafen_vb.py`,
and `tests/test_contract_mednafen_vb.py`. The selected
`actions-sim-build-core-mednafen_vb-v1` and reproduction
`build-core-mednafen_vb-local-v1` runs bind the same package and ABI artifacts.
The local release lives at
`.local-e2e/releases/mednafen_vb-38e7a0ec9ac7-20575c76c389`; the nightly,
pinned, and release aliases are respectively
`.local-e2e/channels/nightly.mednafen_vb.json`,
`.local-e2e/channels/pinned.mednafen_vb.json`, and
`.local-e2e/channels/release.mednafen_vb.json`. These records remain
publication-disabled static-build evidence, and no device view is eligible
without target-runtime validation.

Mednafen Neo Geo Pocket's current semantic ID is
`mednafen_ngp-a50d5ac288a8-d2dabb68d075`. Its independent owners are
`scripts/core_pipeline_lib/contracts/mednafen_ngp.py`,
`pins/core-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json`,
`pins/source-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json`,
`manifests/compatibility/mednafen_ngp.json`,
`tests/cores/test_mednafen_ngp.py`, and
`tests/test_contract_mednafen_ngp.py`. The selected
`actions-sim-build-core-mednafen_ngp-v1` and reproduction
`build-core-mednafen_ngp-local-v1` runs bind the same package, metadata, and ABI
artifacts; their complete log-line multisets match while parallel placement may
differ. The local release lives at
`.local-e2e/releases/mednafen_ngp-a50d5ac288a8-d2dabb68d075`; the nightly,
pinned, and release aliases are respectively
`.local-e2e/channels/nightly.mednafen_ngp.json`,
`.local-e2e/channels/pinned.mednafen_ngp.json`, and
`.local-e2e/channels/release.mednafen_ngp.json`. These records remain
publication-disabled static-build evidence, and no device view is eligible
without target-runtime validation.

Mednafen Lynx's current semantic ID is
`mednafen_lynx-fcdefcfb3c11-c2247f1f6de1`. Its independent owners are
`scripts/core_pipeline_lib/contracts/mednafen_lynx.py`,
`pins/core-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json`,
`pins/source-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json`,
`manifests/compatibility/mednafen_lynx.json`,
`tests/cores/test_mednafen_lynx.py`, and
`tests/test_contract_mednafen_lynx.py`. The selected
`actions-sim-build-core-mednafen_lynx-v1` and reproduction
`build-core-mednafen_lynx-local-v1` runs bind the same package, metadata, and
ABI artifacts. The local release lives at
`.local-e2e/releases/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1`; the nightly,
pinned, and release aliases are respectively
`.local-e2e/channels/nightly.mednafen_lynx.json`,
`.local-e2e/channels/pinned.mednafen_lynx.json`, and
`.local-e2e/channels/release.mednafen_lynx.json`. These records remain
publication-disabled static-build evidence. Required, unbundled
`lynxboot.img`, legal and policy review, and target-runtime coverage for
content, controls, rotation, A/V, saves, states, compatibility, frontend
integration, and performance keep every device view ineligible.

Mednafen PCE Fast's current semantic ID is
`mednafen_pce_fast-0bc6c8692834-8e747136926e`. Its independent owners are
`scripts/core_pipeline_lib/contracts/mednafen_pce_fast.py`,
`pins/core-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json`,
`pins/source-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json`,
`manifests/compatibility/mednafen_pce_fast.json`,
`tests/cores/test_mednafen_pce_fast.py`, and
`tests/test_contract_mednafen_pce_fast.py`. The selected
`actions-sim-build-core-mednafen_pce_fast-v1` and reproduction
`build-core-mednafen_pce_fast-local-v1` runs bind the same package, metadata,
and ABI artifacts. The local release lives at
`.local-e2e/releases/mednafen_pce_fast-0bc6c8692834-8e747136926e`; the nightly,
pinned, and release aliases are respectively
`.local-e2e/channels/nightly.mednafen_pce_fast.json`,
`.local-e2e/channels/pinned.mednafen_pce_fast.json`, and
`.local-e2e/channels/release.mednafen_pce_fast.json`. These records remain
publication-disabled static-build evidence. HuCard and BIOS-backed PCE-CD
loading, the unbundled system-card BIOS, controls, A/V, saves, states,
compatibility boundaries, frontend integration, and performance keep every
device view ineligible pending target-runtime validation.

Mednafen WonderSwan's current semantic ID is
`mednafen_wswan-da6d0d9acb8d-cc4a98ceff16`. Its pin and source set use that
exact individual-core ID; its compatibility and lifecycle owners are
`manifests/compatibility/mednafen_wswan.json` and
`tests/cores/test_mednafen_wswan.py`; and its exact build proof remains in
`tests/test_contract_mednafen_wswan.py`. The selected
`actions-sim-build-core-mednafen_wswan-v1` and reproduction
`build-core-mednafen_wswan-local-v1` runs bind the same package and ABI
artifacts, while `.local-e2e/channels/<channel>.mednafen_wswan.json` aliases
retain exact one-core ownership.

Mednafen PC-FX's current semantic ID is
`mednafen_pcfx-650c30ea2203-5c0f9a256d9a`. Its pin and source set use that
exact individual-core ID; its compatibility and lifecycle owners are
`manifests/compatibility/mednafen_pcfx.json` and
`tests/cores/test_mednafen_pcfx.py`; and its exact build proof remains in
`tests/test_contract_mednafen_pcfx.py`. The selected
`actions-sim-build-core-mednafen_pcfx-v1` and reproduction
`build-core-mednafen_pcfx-local-v1` runs bind the same package and ABI
artifacts while tolerating only valid parallel-log interleaving. The three
`.local-e2e/channels/<channel>.mednafen_pcfx.json` aliases retain exact
one-core ownership. Its records remain static-build evidence: `pcfx.rom` is
required but unbundled, the metadata and compiled versions differ, and no
device view is eligible until provider and target-runtime gates pass.

PokéMini's current semantic ID is
`pokemini-bb009b1379ad-2f63e84b7b68`. Its matching one-core files are
`pins/core-sets/pokemini-bb009b1379ad-2f63e84b7b68.json`,
`pins/source-sets/pokemini-bb009b1379ad-2f63e84b7b68.json`,
`manifests/compatibility/pokemini.json`, `tests/cores/test_pokemini.py`, and
`tests/test_contract_pokemini.py`. These are its independent owners. The selected
`actions-sim-build-core-pokemini-v1` and reproduction
`build-core-pokemini-local-v1` runs bind identical package, metadata, and ABI
artifacts. ARM64 whole-log ordering differs under parallel compilation, while
each log still proves the exact 43-command C build and reviewed diagnostic
streams. The three `.local-e2e/channels/<channel>.pokemini.json` aliases remain
one-core pointers. Its records are static-build-only network-clone evidence:
the optional unbundled `bios.min`, the unresolved potential `.eep` path
overflow, provider inspection, and target runtime all remain external gates.

GearColeco's current semantic ID is
`gearcoleco-112345747c04-046c086031cf`. Its independent owners are
`pins/core-sets/gearcoleco-112345747c04-046c086031cf.json`,
`pins/source-sets/gearcoleco-112345747c04-046c086031cf.json`,
`manifests/compatibility/gearcoleco.json`, `tests/cores/test_gearcoleco.py`, and
`tests/test_contract_gearcoleco.py`. The selected
`actions-sim-build-core-gearcoleco-v2` run has E2E content SHA-256
`43c20dfc81e417c9c74cb935710c4a50d3e8766ae39b137738e3c7467ddc178b` and
uses `github-actions/simulated/local-docker`; the independent
`build-core-gearcoleco-local-v1` run has E2E content SHA-256
`29653ff1ed53ec3a72e604f520d7c9ca0672c2e75370f77c490a0b56752c4a30` and
uses `local/native/local-docker`. They reproduce package, metadata, ABI
artifacts, and logs byte for byte. The core-owned proof still models parallel
ordering explicitly: the Processor compile must precede its exact diagnostic
block, unrelated compile echoes may follow that block, and every compile and
diagnostic must precede the link. Its three
`.local-e2e/channels/<channel>.gearcoleco.json` aliases remain one-core
pointers.

VICE x64's current semantic ID is
`vice_x64-7946cfa0d377-290256f3bebd`. Its independent owners are
`pins/core-sets/vice_x64-7946cfa0d377-290256f3bebd.json`,
`pins/source-sets/vice_x64-7946cfa0d377-290256f3bebd.json`,
`manifests/compatibility/vice_x64.json`, `tests/cores/test_vice_x64.py`, and
`tests/test_contract_vice_x64.py`. The selected
`actions-sim-build-core-vice_x64-v1` run has E2E content SHA-256
`34005d085b8b1df201cc4dec35dd9373a7b3ffc2e60ad96f748952c32c892378` and
uses `github-actions/simulated/local-docker`; the independent
`build-core-vice_x64-local-v1` run has E2E content SHA-256
`5c729210b41a25651e8202449616989db00c2591b17394d1b4f27927bd4b6e75` and
uses `local/native/local-docker`. The runs reproduce the package, metadata, and
both ABI artifacts exactly. Their four build-log hashes differ because of
parallel ordering, but each ABI pair has the same complete line multiset and
each log independently proves the exact 536-C/28-C++ command set, ordered C++
link, and zero diagnostics. The three
`.local-e2e/channels/<channel>.vice_x64.json` aliases retain one-core ownership.

This is static-build-only, network-clone evidence with no offline source cache.
The metadata reports display version `3.9` while the binary identifies
`3.10 7946cfa0d3`; provider and target-runtime evidence remain absent. No
device view is eligible until ABI requirements and C64 content/full-path media,
disk, tape, cartridge, optional JiffyDOS, save/state, controls, audio/video,
load/unload, and sustained-performance gates pass on target devices.

VICE xvic's current semantic ID is
`vice_xvic-7946cfa0d377-6f9943958478`. Its independent owners are
`pins/core-sets/vice_xvic-7946cfa0d377-6f9943958478.json`,
`pins/source-sets/vice_xvic-7946cfa0d377-6f9943958478.json`,
`manifests/compatibility/vice_xvic.json`, `tests/cores/test_vice_xvic.py`, and
`tests/test_contract_vice_xvic.py`. The selected
`actions-sim-build-core-vice_xvic-v1` run has E2E content SHA-256
`7ceed43317329dab1fd6e0f455c00ba92c882ac37f847276e31f8023a1e9422c` and
uses `github-actions/simulated/local-docker`; the independent
`build-core-vice_xvic-local-v1` run has E2E content SHA-256
`1ff6ea3c539445a94945f0350f49c5468e140cfd4f543d52aea7b889df65c972` and
uses `local/native/local-docker`. The runs reproduce package
`9f69e0fda8cfe3275be2570627bfbcbcb0e318fac70057803b8d0e296e99421a`, metadata
`48b23d8971b40aad47efb526b23b8ce11a5f21edd83a4b10fdd0de63a911e571`,
and both ABI artifacts exactly. Their four build-log hashes differ because of
parallel ordering, but each ABI pair has the same complete line multiset and
each log independently proves the exact 428-C/10-C++ command set, ordered C++
link, and zero diagnostics. The three
`.local-e2e/channels/<channel>.vice_xvic.json` aliases retain one-core
ownership.

This is static-build-only, network-clone evidence with no offline source cache.
The metadata reports display version `3.9` while the binary identifies
`3.10 7946cfa0d3`. Base VIC-20 ROMs are linked into the artifact; optional
replacement Kernal, BASIC, character-generator, drive, and cartridge firmware
is not packaged and has no redistribution evidence. No device view is eligible
until ABI/provider requirements and VIC-20 no-game startup, full-path programs,
cartridges, archives and playlists, disks, tapes, snapshots, firmware
replacement, saves/states, controls, audio/video, load/unload, the declared
NTSC-interlace limitation, and sustained-performance gates pass on target
devices.

fMSX's current semantic ID is `fmsx-f013e213458e-194b406b9096`. Its
independent owners are
`pins/core-sets/fmsx-f013e213458e-194b406b9096.json`,
`pins/source-sets/fmsx-f013e213458e-194b406b9096.json`,
`manifests/compatibility/fmsx.json`, `tests/cores/test_fmsx.py`, and
`tests/test_contract_fmsx.py`. The selected
`actions-sim-build-core-fmsx-v1` run has E2E content SHA-256
`b28d61b162360e702e873b89e469a1f446bc9aeb752e930e82e64e16f688dc8d` and
uses `github-actions/simulated/local-docker`; the independent
`build-core-fmsx-local-v1` run has E2E content SHA-256
`f57a53ef3c116eb22e954b0ed7383b74b9a7740737c477ccbe40c7bff059d12b` and
uses `local/native/local-docker`. Both runs bind pristine source commit
`f013e213458e06d9df718e4bc4b09d46f88aa899` and reproduce package
`71602b060f5ea76847b0f808803a87e0251d1fa990954f8a4f462bda72099e97`, metadata
`a7b863ff5e75c538ea77dbf3e7a75d1d57f56abad1b2c946dc5d30c7b206bc98`,
both ABI artifacts, and both ABI logs byte for byte. Each log proves the exact
31-command native-version C build, ordered C link, and zero diagnostics. The
three `.local-e2e/channels/<channel>.fmsx.json` aliases retain one-core
ownership.

This is static-build-only, network-clone evidence with no offline source
cache. Resolver metadata labels the core `Non-commercial`, and the source
root license is custom, non-commercial, and non-public-domain while compiled
NukeYKT code is GPL-2.0-or-later, so publication remains a human legal and
policy gate. Metadata display version `6.0` differs from artifact version
`6.0 f013e21`. External model-specific MSX firmware is not packaged; the
required BIOS set changes between MSX1, MSX2, and the default MSX2+ mode, and
metadata-optional `DISK.ROM` is conditionally required for DSK, FDI, and M3U.
Metadata says `supports_no_game=false`, while the source advertises no-game
support, accepts null content, and can boot BASIC. No device view is eligible
until firmware discovery, no-content behavior, full-path content,
disk/tape/playlist loading, disk persistence and control, saves/states, input,
RGB565 50/60 Hz video, 48 kHz mono audio, frontend integration, compatibility,
sustained performance, and the ABI provider gates pass on target devices. The
portable artifacts are build-identity-bound only to `ra64-universal-v1` and
`ra32-a30-v1`; all eight device views remain empty and ineligible.

blueMSX's current semantic ID is `bluemsx-5f595c79906f-a1c1fd914a76`. Its
independent owners are
`pins/core-sets/bluemsx-5f595c79906f-a1c1fd914a76.json`,
`pins/source-sets/bluemsx-5f595c79906f-a1c1fd914a76.json`,
`manifests/compatibility/bluemsx.json`, `tests/cores/test_bluemsx.py`, and
`tests/test_contract_bluemsx.py`. The selected
`actions-sim-build-core-bluemsx-v1` run has E2E content SHA-256
`5dc0241fddb63fbbdff33fd9c37cbe223c1a62bdaf8148428f56b75479deb7da` and
uses `github-actions/simulated/local-docker`; the independent
`build-core-bluemsx-local-v1` run has E2E content SHA-256
`c41eaadb2f88ff9ab2c633607d7386b022cd7637e97888fec6cb5f98912a5f78` and
uses `local/native/local-docker`. Both runs bind pristine source commit
`5f595c79906ff3379641b5ee8f3796106214a0a4` and reproduce package
`e54b047c7a6dc5715823fda797dfc67ce1fc47b13748824322321de410083a0d`, metadata
`e3840e08ff90f8567beedc9f96ee3597d48ea7a568cfd51aadca20850800257e`,
ARM64 artifact
`14f32f0f61aa7a81d6ad34b244d33db0d88420eb132baa660dc48b7f835978bd`,
ARMHF artifact
`604885f77e8cb3b800b4fa881d875af31bb31d66a94d776e1b2e2c4b6d248c3f`,
and the ARM64 and ARMHF logs byte for byte. Their log hashes are respectively
`51ec8ba37ef3a8732b089e751d79f11293ae6ac7b92728548618d2166a4faae6` and
`1cca54101935e09492f630a6073c8a82199d40b11b6c4b1790124f46c473ef61`.
Each log proves exactly 255 C and 14 C++ compiles, native version ` 5f595c7`
only on the C commands, exactly one `-w` per compile, the ordered C++ link, and
zero emitted diagnostics. The three
`.local-e2e/channels/<channel>.bluemsx.json` aliases retain one-core ownership.

This is static-build-only, network-clone evidence with no offline source
cache. Metadata says GPLv2 and display version `SVN`, while the artifact says
`git 5f595c7`. The source mixes BSD-style blueMSX code, compiled GPL-derived
openMSX and fMSXSDL files, zlib code, and files described only as freeware;
the package carries neither notices nor corresponding source. Publication and
source compliance remain human legal and policy gates. The package also omits
the required `Machines` and `Databases` system data. Of the source's 93 ROMs,
only nine C-BIOS ROMs have an explicit bundled redistribution notice, so all
other ROMs require separate rights review and must not be copied wholesale.

No-game startup requires a valid frontend system directory, and the source's
fallback is unsafe for null content. Full-path content, model and mapper
selection, ten-image playlists, disks and cassettes, disk control, save-path
overlays and basename collisions, and SunriseIDE all remain runtime gates.
States use a fixed 4 MiB allocation; deterministic replay requires the
non-default fixed-epoch RTC option and retains a printer-port DAC state gap.
Input and keyboard mappings, software RGB565 dynamic PAL/NTSC video, 44.1 kHz
stereo audio, unload/reload, compatibility, and sustained performance remain
unverified; mouse entry points are stubs. ARM64 reaches `GLIBC_2.27` and
`GLIBCXX_3.4.21`, while ARMHF reaches `GLIBC_2.4`, `GCC_3.5`,
`CXXABI_ARM_1.3.3`, and `GLIBCXX_3.4.21`. The artifacts bind only to
`ra64-universal-v1` and `ra32-a30-v1`; all eight device views remain empty and
all 16 device entries remain ineligible.

Snes9x 2005's current semantic ID is
`snes9x2005-b60356971fc9-06b9f12c860c`. Its independent owners are the
matching files under `pins/core-sets/`, `pins/source-sets/`, and
`manifests/compatibility/`, plus `tests/cores/test_snes9x2005.py` and
`tests/test_contract_snes9x2005.py`. The selected
`actions-sim-build-core-snes9x2005-v1` and reproduction
`build-core-snes9x2005-local-v1` runs bind pristine source commit
`b60356971fc9caae02cd0853676dced886a08be7`. They reproduce package
`900db7efba34050edac030de8f7d29b96c5b9b1c53b133239723e58df5505fab`,
metadata, both ABI artifacts, and both reviewed logs byte for byte. The three
`.local-e2e/channels/<channel>.snes9x2005.json` aliases retain one-core
ownership.

This is static-build-only, network-clone evidence with no offline source
cache. Cached toolchain images retain the explicit
`dockerfile_linkage=unverified-local-cache` limitation. Metadata and source
licensing keep publication behind a human legal and policy gate; no firmware
is packaged. The preserved `USE_BLARGG_APU=0` default is lower-resource build
identity, not a runtime accuracy or audio-quality claim. Content, controls,
video and audio pacing, saves and states, compatibility, frontend integration,
and sustained performance remain target-runtime gates. The artifacts bind
only to `ra64-universal-v1` and `ra32-a30-v1`; all device views remain
ineligible.

Snes9x 2005 Plus's current semantic ID is
`snes9x2005_plus-b60356971fc9-32f28e9ec741`. Its independent owners are the
matching files under `pins/core-sets/`, `pins/source-sets/`, and
`manifests/compatibility/`, plus `tests/cores/test_snes9x2005_plus.py` and
`tests/test_contract_snes9x2005_plus.py`. The selected
`actions-sim-build-core-snes9x2005_plus-v1` and reproduction
`build-core-snes9x2005_plus-local-v1` runs bind pristine source commit
`b60356971fc9caae02cd0853676dced886a08be7`. They reproduce package
`4d8ec2e2ea4e28afef66484d82a3eb0370dcccbd0c1285d1d734c8403dce755c`,
metadata, both ABI artifacts, and both reviewed logs byte for byte. The three
`.local-e2e/channels/<channel>.snes9x2005_plus.json` aliases retain one-core
ownership.

This is a distinct `USE_BLARGG_APU=1` build and lifecycle, not an alias of the
base core's lower-resource default. It remains static-build-only,
network-clone evidence with no offline source cache, and cached toolchain image
linkage remains unverified. Licensing and missing package notices keep
publication behind a human legal and policy gate; no firmware is declared or
packaged. Content, special-chip compatibility, controls, A/V pacing, saves and
states, frontend integration, sustained performance, and thermals remain
target-runtime gates. Cross-variant state compatibility is not claimed. The
artifacts bind only to `ra64-universal-v1` and `ra32-a30-v1`; all device views
remain ineligible.

Cap32's current semantic ID is `cap32-4abfb8be233b-afbc043051e8`. Its
independent owners are the matching files under `pins/core-sets/`,
`pins/source-sets/`, and `manifests/compatibility/`, plus
`tests/cores/test_cap32.py` and `tests/test_contract_cap32.py`. Selected
`actions-sim-build-core-cap32-v2` and reproduction
`build-core-cap32-local-v2` runs bind pristine source commit
`4abfb8be233bec630f369379fb6c1d92d31f1c7d` and reproduce package
`be763dbd6017626b588f0385c3a03bf92d9cf705c75fab5ebed34cdc21110953`,
metadata, and both ABI artifacts byte for byte. Their per-ABI build-log line
multisets are equal and each ordering passes the exact contract. The three
`.local-e2e/channels/<channel>.cap32.json` aliases retain one-core ownership.

This remains static-build-only network-clone evidence with no offline source
bundle. Cached-image Dockerfile linkage, metadata/binary version drift,
compiled-source redistribution terms, provider availability, content and
disk/tape behavior, keyboard/mouse input, controls, A/V pacing, saves and
states, frontend integration, compatibility, and sustained performance remain
explicit gates. The artifacts bind only to `ra64-universal-v1` and
`ra32-a30-v1`; all device views remain ineligible.

CrocoDS's current semantic ID is `crocods-87bbb3d9007a-7b4aa1fce1f1`. Its
matching one-core files are
`pins/core-sets/crocods-87bbb3d9007a-7b4aa1fce1f1.json`,
`pins/source-sets/crocods-87bbb3d9007a-7b4aa1fce1f1.json`,
`manifests/compatibility/crocods.json`, `tests/cores/test_crocods.py`, and
`tests/test_contract_crocods.py`. Selected
`actions-sim-build-core-crocods-v1` and reproduction
`build-core-crocods-local-v1` runs reproduce the package, metadata, and both
ABI artifacts byte for byte. ARMHF logs are byte-identical. ARM64 logs differ
only by valid parallel complete-line ordering; their line multisets match and
both independently prove the exact 50-command C build plus the five reviewed
diagnostic streams.

This is static-build-only, network-clone evidence. Resolver metadata reports
MIT and display version `v1`, while compiled source includes GPLv2-or-later
headers, bundled zlib terms, and embedded CPC data without a local provenance
record; public distribution remains a human legal and policy gate. Cached
images retain `dockerfile_linkage=unverified-local-cache`, provider and target
runtime evidence remain absent, and no device view is eligible. The three
`.local-e2e/channels/<channel>.crocods.json` aliases retain one-core local
ownership.

Genesis Plus GX's current semantic ID is
`genesis_plus_gx-fa4dca561e08-0e5a55ff8180`. Its matching one-core files are
`pins/core-sets/genesis_plus_gx-fa4dca561e08-0e5a55ff8180.json`,
`pins/source-sets/genesis_plus_gx-fa4dca561e08-0e5a55ff8180.json`,
`manifests/compatibility/genesis_plus_gx.json`,
`tests/cores/test_genesis_plus_gx.py`, and
`tests/test_contract_genesis_plus_gx.py`. Selected
`actions-sim-build-core-genesis_plus_gx-v1` and reproduction
`build-core-genesis_plus_gx-local-v1` runs reproduce the package, metadata,
and both ABI artifacts byte for byte. ARMHF logs are byte-identical. ARM64
logs differ only by valid parallel complete-line ordering; their line
multisets match and both independently prove the exact 117-command C build,
native ` fa4dca5` version, and reviewed diagnostic streams.

This is static-build-only, network-clone evidence. The candidate's core-option
and BRAM interfaces differ from the imported Spruce generation, the imported
binaries identify as different commits, and no Base/Wide state-compatibility
claim is made. Cached images retain
`dockerfile_linkage=unverified-local-cache`; corresponding-source and notice
obligations, provider availability, content coverage, BIOS/CD/BRAM and option
migration, controls, A/V pacing, saves and states, frontend integration, and
sustained performance remain explicit gates. The artifacts bind only to
`ra64-universal-v1` and `ra32-a30-v1`; all device views remain ineligible. The
three `.local-e2e/channels/<channel>.genesis_plus_gx.json` aliases retain
one-core local ownership.

Genesis Plus GX Wide's current semantic ID is
`genesis_plus_gx_wide-29d9d104338f-7907e7e03389`. Its matching one-core files
are `pins/core-sets/genesis_plus_gx_wide-29d9d104338f-7907e7e03389.json`,
`pins/source-sets/genesis_plus_gx_wide-29d9d104338f-7907e7e03389.json`,
`manifests/compatibility/genesis_plus_gx_wide.json`,
`tests/cores/test_genesis_plus_gx_wide.py`, and
`tests/test_contract_genesis_plus_gx_wide.py`. Fresh selected
`actions-sim-build-core-genesis_plus_gx_wide-v1` and reproduction
`build-core-genesis_plus_gx_wide-local-v1` runs reproduce the package,
metadata, both ABI artifacts, and both logs byte for byte while independently
proving the exact 106-command C build.

This remains static-build-only, network-clone evidence. Spruce ships a
different ARM64 Wide binary with state signature 1.7.6 and no ARMHF Wide
binary; the candidate uses state signature 1.7.7. Runtime behavior, Wide
option and state migration, Base/Wide compatibility, provider availability,
and non-commercial corresponding-source obligations remain explicit gates.
The artifacts bind only to `ra64-universal-v1` and `ra32-a30-v1`; all device
views remain ineligible. The three
`.local-e2e/channels/<channel>.genesis_plus_gx_wide.json` aliases retain
one-core local ownership.

O2EM's current semantic ID is `o2em-e03d3be88f79-ede84c3862de`. Its selected
`actions-sim-build-core-o2em-v1` and reproduction `build-core-o2em-local-v1`
runs bind `pins/core-sets/o2em-e03d3be88f79-ede84c3862de.json`, the matching
source set, `manifests/compatibility/o2em.json`, `tests/cores/test_o2em.py`, and
the three `.local-e2e/channels/<channel>.o2em.json` aliases.

FreeChaF's current semantic ID is
`freechaf-76c7a84f1f7e-0fced3806666`. Its selected
`actions-sim-build-core-freechaf-v1` and reproduction
`build-core-freechaf-local-v1` runs bind the matching one-core pin and source
set, `manifests/compatibility/freechaf.json`,
`tests/cores/test_freechaf.py`, and the three
`.local-e2e/channels/<channel>.freechaf.json` aliases.

VecX's current semantic ID is `vecx-8f671cc9d737-4686ef94bf56`. Its selected
`actions-sim-build-core-vecx-v2` and reproduction
`build-core-vecx-local-v1` runs bind the matching one-core pin and source set,
`manifests/compatibility/vecx.json`, `tests/cores/test_vecx.py`, and the three
`.local-e2e/channels/<channel>.vecx.json` aliases.

LowRes NX's current semantic ID is
`lowresnx-35adc1a215e9-837092a5ffca`. Its selected
`actions-sim-build-core-lowresnx-v1` and reproduction
`build-core-lowresnx-local-v1` runs bind the matching one-core pin and source
set, `manifests/compatibility/lowresnx.json`,
`tests/cores/test_lowresnx.py`, and the three
`.local-e2e/channels/<channel>.lowresnx.json` aliases. ARM64 reaches
`GLIBC_2.29`; provider compatibility and target-runtime behavior remain
unverified, so every device view stays ineligible even though the artifacts
are build-identity-bound to `ra64-universal-v1` and `ra32-a30-v1`.

RACE's current semantic ID is `race-c7810dd7f172-c3119de987bf`. Its selected
`actions-sim-build-core-race-v1` and reproduction
`build-core-race-local-v1` runs bind the matching one-core pin and source set,
`manifests/compatibility/race.json`, `tests/cores/test_race.py`, and the three
`.local-e2e/channels/<channel>.race.json` aliases. Both ABIs reproduce the
package, metadata, artifacts, and exact logs byte for byte. Publication remains
disabled behind GPLv2 redistribution review; ARMHF requires `GLIBC_2.7`, while
reset, core options, unaligned-access behavior, provider compatibility, target
runtime, and every device view remain provisional and unverified.

Mednafen SuperGrafx's current semantic ID is
`mednafen_supergrafx-3c6fcd3deded-6f92f2753900`. Its independent owners are
`scripts/core_pipeline_lib/contracts/mednafen_supergrafx.py`,
`pins/core-sets/mednafen_supergrafx-3c6fcd3deded-6f92f2753900.json`,
`pins/source-sets/mednafen_supergrafx-3c6fcd3deded-6f92f2753900.json`,
`manifests/compatibility/mednafen_supergrafx.json`,
`tests/cores/test_mednafen_supergrafx.py`, and
`tests/test_contract_mednafen_supergrafx.py`. Selected
`actions-sim-build-core-mednafen_supergrafx-v1` and reproduction
`build-core-mednafen_supergrafx-local-v1` runs reproduce package, metadata, and
both ABI artifacts exactly. Parallel logs differ, but both pass the exact
occurrence-aware proof. The local release is
`.local-e2e/releases/mednafen_supergrafx-3c6fcd3deded-6f92f2753900`; the three
`.local-e2e/channels/<channel>.mednafen_supergrafx.json` aliases retain one-core
ownership. Publication remains disabled behind GPLv2 review; no optional PCE-CD
BIOS candidate is packaged. Metadata display version `1.23.0` differs from
binary version `1.29.0`, ARMHF preserves the reviewed free-nonheap warning risk,
and SGX/CD/CHD, provider, runtime, and device behavior remain unverified. Every
device view is ineligible.

Potator's current semantic ID is `potator-227c5f6f3ce7-1617e2249087`. Its
independent owners are `scripts/core_pipeline_lib/contracts/potator.py`,
`pins/core-sets/potator-227c5f6f3ce7-1617e2249087.json`,
`pins/source-sets/potator-227c5f6f3ce7-1617e2249087.json`,
`manifests/compatibility/potator.json`,
`tests/cores/test_potator.py`, and `tests/test_contract_potator.py`. Selected
`actions-sim-build-core-potator-v1` and reproduction
`build-core-potator-local-v1` runs reproduce package, metadata, both ABI
artifacts, and both logs byte for byte. Resolver metadata declares
`Public Domain`, no firmware is packaged or required, and all four reviewed
misleading-indentation CPU warning/note pairs remain preserved. The local
release is `.local-e2e/releases/potator-227c5f6f3ce7-1617e2249087`; the three
`.local-e2e/channels/<channel>.potator.json` aliases retain one-core ownership,
but publication remains disabled and runtime/device behavior remains unverified;
every device view is ineligible.

Gearboy's current semantic ID is `gearboy-36d723ff4410-f6f1b63e8798`, and
Gearsystem's is `gearsystem-4f029e43f2d5-35212fbb9d9a`. Each independently
owns its contract, one-core pin, matching source set, compatibility record,
lifecycle test, and exact contract test. Selected
`actions-sim-build-core-gearboy-v1` and
`actions-sim-build-core-gearsystem-v1` reproduce their respective
`build-core-*-local-v1` packages, metadata, both ABI artifacts, and both build
logs byte for byte. Their local releases and per-core nightly, pinned, and
release channels remain publication-disabled. GPLv3 review, optional boot-ROM
handling, metadata display-version drift, provider and target-runtime
validation, and all device claims remain open; ARMHF's `GLIBCXX_3.4.32`
requirement leaves every Mini device view ineligible.

EightyOne's current semantic ID is `81-fa7094910d04-a82f6eb4a7cc`. Its selected
`actions-sim-build-core-81-v2` and reproduction `build-core-81-local-v1` runs
bind the matching one-core pin and source set,
`manifests/compatibility/81.json`, `tests/cores/test_81.py`, and the three
`.local-e2e/channels/<channel>.81.json` aliases. The proof admits exactly 39
warnings/6 notes on ARM64 and 38 warnings/11 notes on ARMHF while preserving
every owning diagnostic stream's order. ABI dependency drift, copied metadata
parsing, bundled-ROM redistribution, and target runtime are unverified; both
artifacts bind only to `ra64-universal-v1` and `ra32-a30-v1`, and every device
view remains ineligible.

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
