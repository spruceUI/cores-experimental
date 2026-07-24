# Core pipeline command-line reference

This is the exhaustive command-line reference for
`scripts/core_pipeline.py` (see also `scripts/toolchain_archive.py
--help` for the archive lock CLI — `import-lock` takes
`--arm64/--armhf/--rust`, `verify-downloads` requires the two C archives
and takes `--rust` optionally). It covers parser-visible options, runtime
constraints, and the local or external data each invocation consumes. For the
recommended promotion sequence, see the
[core pipeline operator guide](core-pipeline-operations.md).

The entry script is local-only. It has no publication command and does not call
the GitHub API.

## Entry point and help

Run commands from the repository root:

```bash
python3 scripts/core_pipeline.py --help
python3 scripts/core_pipeline.py <command> --help
```

The script is executable, so `./scripts/core_pipeline.py` is equivalent when
the shebang can find Python 3. Both `-h` and `--help` are valid. Top-level help
lists all 20 commands; command help lists that command's parser-visible flags.
Help exits successfully without executing a command.

The execution grammar is:

```text
python3 scripts/core_pipeline.py [--catalog PATH] COMMAND [COMMAND-OPTIONS]
```

`--catalog` is a top-level option and must appear before `COMMAND`. Its default
is `manifests/core-builds.json`. Relative path arguments and `~` are expanded
and made absolute against the invoking shell without resolving symlinks before
the handler runs. This preserves lexical path components for the handlers'
symlink-traversal checks. The catalog's
own references remain repository-rooted, so a custom catalog is not an
arbitrary self-contained manifest from another directory.

The following commands read `--catalog`:

- `catalog-check`, `audit-workflows`, `build`, `build-core`, `e2e`, `promote`,
  `derive-core-id`, `compose-core-golden`, `compose-pin-set`, `promote-release`,
  `update-channel`, `plan-release`, `release-matrix`, `record-release-result`,
  and `seal-release`

The parser also accepts the global option for `import-golden`,
`validate-golden`, `validate-pin-set`, `validate-release`, and
`validate-channel`, but those handlers do not read it. Supplying it to those
commands is valid but has no effect.

### How combinations are specified below

For each command, choose one entry from every row in its **Valid forms** table.
Rows marked independent form a Cartesian product; that product is the complete
set of supported, canonical flag combinations. A repeatable value may occur any
number of times allowed by its stated minimum. Python's argument parser may
accept a redundant repeat of some scalar flags and keep the last value; those
repeats are non-canonical and are not separate supported combinations. Runtime
restrictions listed after a table further narrow the combinations where noted.

In command examples, uppercase names such as `CORE`, `PATH`, and `RUN_ID` are
values supplied by the operator, not literal text.

## Shared runtime inputs

Commands consume only local files and build services, but some require data
that is not encoded on the command line:

- Python 3 and Git are required throughout the normal workflow. `readelf` is
  required when importing, building, or revalidating ELF artifacts.
- Build commands require a working Docker daemon and the exact
  `cores-arm64:latest` and/or `cores-armhf:latest` image IDs pinned by the
  catalog and toolchain lock.
- Build containers must be able to fetch the catalog-pinned source commit and
  any submodules from their Git remotes. There is no source-directory or source
  archive flag.
- The tracked catalog, workflow files, policy, schemas, toolchain lock,
  resolver inputs, metadata replacements, and build overlays must retain their
  pinned identities.
- Store-backed promotion and deep validation require the ignored local
  `.local-e2e/store/` bytes created by earlier promotion steps. A fresh clone
  does not contain those bytes.
- Pipeline commands that use `--verify-sources` verify referenced source-golden
  documents and parent documents under `pins/core-sets/`. They do not read the
  separate per-core locks under `pins/sources/`; validate those through the
  source-set contract with
  `scripts/profile_registry.py report --source-set PATH`. The source-set option
  is required; there is no aggregate default.

No command accepts GitHub credentials, a publication token, or a remote release
destination.

## Runner profiles

`build-core` and `e2e` share these profiles. Full-release worker records use
the same persisted runner contracts, and `seal-release` requires the matching
selector. Their `--output-root` defaults to
`.local-e2e/runs`. It must resolve to `.local-e2e/` itself or a location below
it; paths elsewhere in the repository are rejected. If the output root already
exists, it must be a directory, and the path must remain safely contained by
the repository. The
selected `<output-root>/<run-id>` must not already exist or be a symlink.

| Selector | Valid `--run-id` form | Required environment and checkout state |
| --- | --- | --- |
| `local` (default) | Omit it for a UTC `YYYYMMDDTHHMMSSZ` value, or supply a valid ID. | `GITHUB_ACTIONS` must be unset, empty, or exactly `false`. |
| `github-actions-sim` | Required and must match `actions-sim-*`. | `GITHUB_ACTIONS` must be unset, empty, or exactly `false`. |
| `github-actions` | Omit it, or supply exactly `actions-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`. | `GITHUB_ACTIONS=true`, `CI=true`, exact `GITHUB_WORKSPACE`, lowercase 40-character `GITHUB_SHA` equal to `HEAD`, positive decimal `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT`, and a clean tracked checkout. |

A general run ID is 1–128 characters, starts with an ASCII letter or digit, and
then contains only letters, digits, `.`, `_`, or `-`. A simulated-Actions ID
must start with `actions-sim-` and have at least one letter or digit after that
prefix. User-supplied local and simulated-Actions IDs for new runs must not
use a reserved historical name (any ID containing `tranche`).
That creation rule does not invalidate frozen records when they are read or
audited. The native profile derives its numeric identity from Actions
environment data; do not fake that environment for local tests. Use
`github-actions-sim` instead.

All three selectors record local-only, publication-disabled evidence. The
simulation selector records normalized profile `github-actions`, mode
`simulated`, and backend `local-docker`.

## Commands

### `catalog-check`

Validate the catalog and all repository files whose exact identities it binds.

```text
catalog-check
```

**Valid forms:** one form only; there are no command-specific flags. The global
catalog may be defaulted or supplied before the command.

**External data:** the catalog, commit-blacklist policy, toolchain lock and
validator, workflow/build inputs, source metadata, and every repository file
whose path or digest is part of the catalog contract. Docker images and source
network access are not used. With the repository's default catalog, the command
also requires exact, disjoint coverage by effective compatibility state or
path-bound `manifests/compatibility/pending/<core>.json` transition records.
Effective compatibility is either a current canonical admission or an
immutable legacy bridge row, with canonical state superseding a frozen row for
the same core. The output reports separate canonical-admission, legacy-bridge,
effective-coverage, and pending counts plus the pending core IDs. Pending
records never count as canonical compatibility or golden sources.

### `audit-workflows`

Audit the independent per-core workflow inventory. The audit requires exactly
one `.github/workflows/build-<CORE>.yml` owner for every catalog core, reports
missing or uncataloged per-core owners, verifies that every catalog owner calls
the shared E2E command exactly once with `--runner-profile github-actions` and
its filename-bound `--core CORE`, and rejects active `build-all*.yml` or
`build-all*.yaml` aggregate workflow files. The same command also audits the
exact `release-candidate.yml` coordinator and `_build-one-core.yml` reusable
worker: triggers, read-only permissions, pinned approved actions, bounded
matrix fan-out, shared CLI commands, artifact layout, toolchain staging, and
the absence of publication paths all fail closed. Their complete reviewed byte
identities are pinned, so any extra or malformed YAML, unknown step, runner,
shell, service, container, action option, or command is rejected even when it
does not match a named blacklist rule.

```text
audit-workflows [--output PATH]
```

| Independent choice | Valid values |
| --- | --- |
| Report file | omit `--output`, or supply it once |

Without `--output`, the summary is printed only. With it, the complete report
is atomically written to `PATH` and the summary is still printed. An existing
report path may be replaced.

**External data:** the selected catalog plus the complete local
`.github/workflows/build-*.yml` inventory, including any disallowed
`build-all*.yml` or `build-all*.yaml` file that the audit must report, plus the
two canonical release-orchestration workflows. The retired aggregate build-all
records live only in git history and are not workflow-audit inputs. Docker, build artifacts, and network access
are not used. The command exits nonzero if either the per-core census or the
release-orchestration contract is invalid.

### `import-golden`

Create an artifact-only golden baseline from a SpruceOS checkout.

```text
import-golden --core CORE [--spruceos PATH] --output PATH [--allow-missing]
```

| Independent choice | Valid values |
| --- | --- |
| Core | exactly one `--core CORE` |
| SpruceOS checkout | omit for sibling `spruceOS`, or supply `--spruceos PATH` once |
| New golden | exactly one `--output .local-e2e/nightlies/<CORE>-candidate-<LABEL>/golden.json` |
| Missing selected-core baseline | omit `--allow-missing`, or supply it once |

`--core` and `--output` are required. The two optional choices are independent,
giving four canonical flag-presence combinations. `CORE` must be a known core
workflow. The output is create-only, must have the exact candidate shape shown
above, and must stay below `.local-e2e/nightlies/`; `LABEL` is a nonempty part
of the repository's local-ID syntax. The complete candidate ID must also pass
the reserved historical-name guard (any ID containing `tranche` is rejected).

The output is schema-v2 singleton state: `core_id` is `CORE`, and both `cores`
and `build_goldens` have exactly that key. `--allow-missing` can write the
candidate when the selected core has no valid shipped baseline. That imported
evidence remains incomplete and is not itself promotable; the flag does not
relax the complete E2E promotion contract or make a missing or invalid artifact
valid. Every validation failure other than the selected core having no valid
imported artifact remains fatal.

**External data:** `PATH` must be a Git checkout with `.git`, a resolvable
`HEAD`, and any selected-core files at
`RetroArch/.retroarch/cores64/<CORE>_libretro.so` and
`RetroArch/.retroarch/cores/<CORE>_libretro.so`. The local workflow roster and
`readelf` are also consumed. The catalog is not read.

### `validate-golden`

Validate an imported/build-golden document, optionally against source files and
the local content-addressed store.

```text
validate-golden --golden PATH [--spruceos PATH]
                [--verify-files] [--verify-store]
```

| Independent choice | Supported values |
| --- | --- |
| Golden | supply exactly one `--golden PATH` |
| SpruceOS checkout | omit for sibling `spruceOS`, or supply `--spruceos PATH` once |
| Shipped-file verification | omit `--verify-files`, or supply it once |
| Store verification | omit `--verify-store`, or supply it once |

The three optional parser choices form all eight flag-presence combinations.
`--spruceos` is read only when `--verify-files` is present; supplying it without
`--verify-files` is accepted but operationally inert. The four meaningful
verification modes are: structural only, structural plus shipped files,
structural plus local store, and all three checks.

There is no implicit golden input. Active validation, import, promotion,
composition, pin, and channel operations use singleton schema-v2 golden state.
The retired aggregate schema-v1 baseline lives only in git history and has no
operator lifecycle command.

**External data:** the golden and current workflow roster are always required.
`--verify-files` also needs the referenced SpruceOS artifact tree and
`readelf`; `--verify-store` needs all locally stored evidence referenced by
build goldens. The catalog is not read.

### `build`

Build one explicitly selected core architecture. This is a diagnostic build;
it does not create a complete-core package or an E2E record.

```text
build --core CORE --arch {arm64,armhf} --output PATH
```

**Valid forms:** all three flags are required exactly once. `CORE` must be a
catalog key, `--arch` must be enabled in that core's catalog `targets`, and the
exact source identity must not be actively blacklisted. `PATH` must not already
exist. Unlike an E2E output root, this path is not required by the handler to be
inside the repository, although `.local-e2e/` is the supported location.

**External data:** the catalog and all of its bound inputs, the selected Docker
image, Docker source-network access, Git, and `readelf`. The output directory
must be writable and mountable by Docker.

### `build-core`

Build and package exactly one catalog core with the parameters declared for
that core. This is the single-core complete-build entry point.

```text
build-core [--runner-profile {local,github-actions,github-actions-sim}]
           --core CORE [--run-id RUN_ID] [--output-root PATH]
```

| Choice | Valid values |
| --- | --- |
| Runner | omit for `local`, or select exactly one of the three profiles |
| Core | exactly one `--core CORE` |
| Run ID | use the selected profile's form in [Runner profiles](#runner-profiles) |
| Output root | omit for `.local-e2e/runs`, or supply once |

There is deliberately no `--arch` option. The command obtains the core's
ordered target list, build driver, source pin, toolchain, metadata, overlays,
and compatibility parameters from the catalog. It enables fail-fast behavior,
builds every declared target, and packages only that core. An unknown or
ineligible core is rejected, and there is no flag with which to substitute a
different target architecture or build recipe.

**External data:** all `build` dependencies for every target declared by the
core, plus the selected runner-profile environment and a Git `HEAD`. An
`e2e-record.json` is always written for a completed run. The complete package is
written below `<output-root>/<run-id>/` only if the target set and metadata are
complete and valid.

### `e2e`

Run the build/package flow for exactly one catalog core, optionally restricting
the run to one or more of that core's architectures for diagnostics.

```text
e2e [--runner-profile {local,github-actions,github-actions-sim}]
    --core CORE [--arch {arm64,armhf}]...
    [--run-id RUN_ID] [--output-root PATH] [--fail-fast]
```

| Choice | Valid values |
| --- | --- |
| Runner | omit for `local`, or select exactly one profile |
| Core scope | exactly one `--core CORE` |
| Architecture scope | omit every `--arch` for the core's complete declared target set, or repeat it for one or more unique architectures enabled by that core |
| Run ID | use the selected profile's form in [Runner profiles](#runner-profiles) |
| Output root | omit for `.local-e2e/runs`, or supply once |
| Failure traversal | omit `--fail-fast` to attempt the remaining selected architectures, or supply it once to stop after the first failed target |

The rows form the exhaustive set of supported combinations, subject to
these runtime restrictions:

- Omitting `--core` or supplying it more than once is an error; one E2E run
  never coordinates multiple cores.
- Repeating the same architecture is an error.
- The selected core must exist, be currently eligible, and enable every
  explicitly selected architecture.
- With no `--arch`, the core uses its exact catalog target set and can package.
- With explicit `--arch`, the core packages only when the selected set exactly
  equals its catalog target set. A proper subset is an intentional per-core
  diagnostic run: it writes build and E2E evidence, records
  `not_packaged`/`failed`, exits nonzero, and cannot be promoted.
- Selecting both unique architectures is package-capable only for a core whose
  exact target set is those two architectures.

**External data:** the `build` dependencies for every selected target of the
one core, the runner-profile environment, and repository `HEAD`/clean state as
required by that profile. Packaging uses only artifacts produced in the new
run directory.

### `promote`

Promote one architecture record from a complete passing E2E into an empty slot
in an existing golden.

```text
promote --golden PATH --record PATH --e2e-record PATH
```

| Choice | Valid values |
| --- | --- |
| Golden | exactly one `--golden PATH` below `.local-e2e/nightlies/` |
| Build record | exactly one `--record PATH` |
| E2E record | exactly one `--e2e-record PATH` |

The build record and E2E record must be below `.local-e2e/`, belong to the same
complete passing core run, match the current catalog and recipe identities, and
bind a package containing every declared target. Active evidence must use exact
schema version 2, contain valid runner evidence, and contain no build or package
for another core. Schema-v1, aggregate, and partial diagnostic E2E records are
not valid promotion evidence. The selected golden must already be valid, live
below `.local-e2e/nightlies/`, identify the build record's core in `core_id`,
and contain exactly that key in both `cores` and `build_goldens`. Its selected
architecture slot must be empty. This makes the working candidate core-owned
before its first promotion.
The command mutates that golden and adds exact evidence bytes to
`.local-e2e/store/`; it never overwrites a filled slot or adds a second core.

**External data:** the existing golden, passed E2E/package/build/log/recipe
files, current catalog and blacklist, and writable local store.

### `derive-core-id`

Read a complete core-owned candidate and report its deterministic lifecycle ID
and canonical output paths without writing files.

```text
derive-core-id --core CORE --source-golden PATH
```

**Valid forms:** `--core` and `--source-golden` are both required exactly once,
so there is one command-specific form. The global catalog may be defaulted or
supplied before the command. `CORE` must be a current catalog key.

The source must be a regular, non-symlink file inside the repository, validate
as a golden, contain complete stored build evidence for exactly `CORE`, and
contain no promoted evidence for another core. The command derives
`<CORE>-<SOURCE-COMMIT-12>-<SELECTION-SHA256-12>` and prints the canonical
nightly golden, pin-set, and release paths. It is the read-only preflight for
`compose-core-golden`; copy the reported `nightly_golden` path into that
command's `--output` argument.

**External data:** the catalog, candidate golden, and every local-store object
referenced by the selected complete bundle. No Docker build, source fetch,
tracked pin, release, or channel pointer is read or written.

### `compose-core-golden`

Create an exact-one-core nightly golden from an existing promoted golden.

```text
compose-core-golden --core CORE --source-golden PATH --output PATH
```

**Valid forms:** `--core`, `--source-golden`, and `--output` are all required
exactly once, so there is one command-specific form. The global catalog may be
defaulted or supplied before the command. `CORE` must be a current catalog key.
Repeating any scalar flag is non-canonical.

The source must be a regular, non-symlink file contained by the repository. It
must be a structurally valid, core-owned golden whose `build_goldens` map has
exactly the key `CORE`, with a complete stored bundle. Every target in that
bundle must name the same full source commit and the bundle must have a valid
selection SHA-256.

The output has one exact supported shape:

```text
.local-e2e/nightlies/<CORE>-<SOURCE-COMMIT-12>-<SELECTION-SHA256-12>/golden.json
```

The directory name is the semantic ID derived by the command from the selected
bundle, not an arbitrary run label. The output must use that exact ID, must stay
below `.local-e2e/nightlies/`, and must not already exist or be a symlink. The
write is create-only. The resulting document retains the source golden's
provenance and immutable source timestamp but replaces `build_goldens` with
exactly one key, `CORE`, then recomputes its content hash. Successful JSON output reports the
semantic ID, path, file SHA-256, and content SHA-256.

**External data:** the catalog, the promoted source golden, and every
content-addressed-store object referenced by the selected complete bundle. No
Docker build, source fetch, pin set, source lock, release, or channel pointer is
read. Use this exact-scope document as the schema-v2 `nightly` target and as the
source for the new one-core pin; aggregate working goldens are not valid inputs
for an individual nightly alias.

### `compose-pin-set`

Create one immutable parentless core-package selection.

```text
compose-pin-set --pin-id ID --core CORE --source-golden PATH --output PATH
```

| Choice | Valid values |
| --- | --- |
| Pin identity | exactly one semantic `--pin-id <core>-<source12>-<selection12>` |
| Scope | exactly one `--core CORE` |
| Candidate source | exactly one `--source-golden PATH` |
| Output | exactly one `--output PATH` |

The source must be the exact one-core output of `compose-core-golden` at
`.local-e2e/nightlies/ID/golden.json`. `ID` is derived from its selected source
commit and selection digest; the command rejects a guessed ID, another output
filename, multiple cores/sources, parent lineage, and failed-candidate inputs.
The output is exactly `pins/core-sets/ID.json`, must not exist, and may not
traverse a symlink. Legacy aggregate pins remain readable validation fixtures;
there is no aggregate composition writer in the active pipeline.

**External data:** the exact one-core golden, all of its content-addressed-store
evidence, and the catalog for current blacklist eligibility. Per-core source
locks and source sets are a separate registry validation step.

### `validate-pin-set`

Validate an immutable pin-set document.

```text
validate-pin-set --pin-set PATH [--verify-store] [--verify-sources]
```

| Independent choice | Valid values |
| --- | --- |
| Pin set | exactly one `--pin-set PATH` |
| Store | omit `--verify-store`, or supply it once |
| Referenced sources | omit `--verify-sources`, or supply it once |

The two verification flags are independent, giving four modes: structural,
structural plus store, structural plus referenced sources, and all checks. `PATH`
must be below `pins/core-sets/`. Structural validation checks referenced source
and parent identity shapes, digests, and contained path forms, but does not load
those referenced documents.

**External data:** structural mode needs only the pin document.
`--verify-store` additionally requires all selected packages and retained
evidence in `.local-e2e/store/`. `--verify-sources` loads and recursively
validates the referenced source-golden documents and parent pin lineage. It
does not validate per-core source locks or a source set; run
`scripts/profile_registry.py report --source-set PATH` separately for that
contract. The catalog is not read, so this command validates historical
evidence without applying current blacklist admission.

### Profile registry reporting

Normal source/profile reporting has one active form:

```text
python3 scripts/profile_registry.py report --source-set PATH [--json]
```

`PATH` is required, must remain below `pins/source-sets/`, and must name an
exact-one-core source set. The command validates its source lock, evidence pin,
catalog mirror, execution profiles, and runtime contracts without writing.
Immutable multi-core history is rejected here; the retired aggregate audit
form lives only in git history.

### `promote-release`

Copy a valid pin's exact package bytes into a new local release.

```text
promote-release --pin-set PATH --output PATH
```

**Valid forms:** both flags are required exactly once. The pin must be the
canonical parentless one-core `pins/core-sets/ID.json`; the output is exactly
the new `.local-e2e/releases/ID` directory. The command rejects aggregate,
parented, nonsemantic, renamed, and symlink-traversing inputs. An existing
destination is rejected. The command rebuilds and repacks nothing.

**External data:** a pin that passes store and referenced-source verification,
its exact packages in `.local-e2e/store/`, its source-golden documents and
parent lineage, and the current catalog/blacklist for admission. Per-core source
locks remain a separate source-set validation gate.

### `validate-release`

Verify a local release against the immutable pin supplied by the operator.

```text
validate-release --pin-set PATH --release PATH [--verify-store]
```

| Independent choice | Valid values |
| --- | --- |
| Pin set | exactly one `--pin-set PATH` |
| Release directory | exactly one `--release PATH` |
| Canonical store | omit `--verify-store`, or supply it once |

The pin must be below `pins/core-sets/` and the release must be below
`.local-e2e/releases/`. Referenced source-golden and parent-lineage verification
is always enabled. Release assets and `release-manifest.json` are always
verified against the supplied pin; `--verify-store` additionally checks the
pin's canonical stored evidence.

**External data:** the pin, its referenced source-golden documents and parent
lineage, the release manifest, and every released ZIP. The ignored local store
is additionally required with `--verify-store`. The catalog, current blacklist,
per-core source locks, and source-set documents are not read.

### `plan-release`

Create one immutable, runner-neutral full-release plan from tracked state.
Exactly one selector family is valid:

```text
plan-release --candidate-id ID --core CORE [--core CORE]...
             --output .local-e2e/release-plans/ID.json

plan-release --candidate-id ID
             --scope {canonical,full-workflow-roster}
             --output .local-e2e/release-plans/ID.json
```

| Choice | Valid values |
| --- | --- |
| Candidate | exactly one valid `--candidate-id ID` |
| Core selection | one or more unique repeated `--core CORE`, or exactly one `--scope` |
| Named scope | `canonical` or `full-workflow-roster`; mutually exclusive with every `--core` |
| Output | exactly `.local-e2e/release-plans/ID.json` |

There is no `--all` alias. `canonical` selects every current canonical
individual compatibility owner. `full-workflow-roster` means every discovered
per-core workflow and fails with categorized counts while any workflow is
uncataloged, legacy-bridge-only, pending, non-shared, or missing from canonical
state. Explicit cores must already be canonical and use the shared pipeline.

The repository must be completely clean. Planning binds `HEAD`, the catalog,
toolchain lock, blacklist, full tracked Python source bundle, full tracked
workflow roster, workflow topology, the audited release coordinator and
reusable worker, each core workflow, one-core pin, source set and source lock,
compatibility record, package bytes, target artifact identities, and the
current execution-profile cell. Every referenced pipeline or workflow source
must be Git-tracked. Planning intentionally does not read `.local-e2e`
evidence or package bytes.

**External data:** a clean Git checkout and every tracked record named above.
Docker, source-network access, ignored build evidence, and GitHub credentials
are not used. The global `--catalog` may be written before the command, but the
handler accepts only the canonical `manifests/core-builds.json` path.

### `release-matrix`

Project one immutable plan into the exact one-core matrix consumed by the
publication-disabled Actions coordinator:

```text
release-matrix --plan .local-e2e/release-plans/ID.json
```

**Valid forms:** `--plan` is required exactly once and has no combinable
command-specific flags. The plan must use its canonical candidate-derived
path, pass schema and semantic validation, and exactly match the current clean
tracked repository. The global `--catalog` may precede the command, but only
the canonical catalog is accepted during repository reconstruction.

Success writes exactly one compact JSON line to stdout, with no status wrapper
or diagnostic text:

```json
{"include":[{"core_id":"2048"},{"core_id":"gambatte"}]}
```

Rows retain the plan's sorted core order. Projection rejects more than 256
rows, matching the Actions matrix ceiling. The command does not build, write a
file, fetch data, call GitHub, or publish anything.

**External data:** the canonical plan and every clean tracked repository input
needed to reconstruct it, including both release-orchestration workflows.
Docker, ignored E2E evidence, network access, and GitHub credentials are not
used.

### `record-release-result`

Turn one fresh, complete one-core E2E run into a portable worker bundle:

```text
record-release-result
  --plan .local-e2e/release-plans/ID.json
  --core CORE
  --e2e-record .local-e2e/runs/RUN_ID/e2e-record.json
  --output-dir .local-e2e/release-results/ID/RUNNER/CORE
```

**Valid forms:** all four command-specific flags are required exactly once.
`RUNNER` is derived from the deeply validated E2E record and is exactly one of
`local`, `github-actions`, or `github-actions-sim`; there is deliberately no
separate runner flag. The plan must contain `CORE`, match the clean current
repository exactly, and use its canonical path. The output path must contain
the same candidate ID, derived runner, and core, and must not already exist.

The E2E record must be schema v2, one-core, passed, local-only, and
publication-disabled. It must contain the complete catalog target set and one
valid package. Every build record, build log, artifact, metadata file, ZIP
member, source/tree/submodule identity, toolchain, workflow, blacklist, catalog,
and current pipeline recipe is revalidated. Every target must have been built
from the clean commit stored in the plan. Fresh package and artifact bytes must
match the pinned expectations; historical build-record hashes are evidence,
not an equality requirement for the newly generated records.

**External data:** the tracked plan inputs, the fresh run tree below
`.local-e2e/runs/RUN_ID/`, its Docker-built artifacts and logs, and the packaged
ZIP. The command writes only `result.json` and `CORE_libretro.zip` in the new
worker bundle. It performs no build, fetch, publication, or GitHub operation.

### `seal-release`

Fail closed while assembling the exact worker fan-in into one candidate:

```text
seal-release
  --plan .local-e2e/release-plans/ID.json
  --results-root .local-e2e/release-results/ID/RUNNER
  --runner-profile {local,github-actions,github-actions-sim}
  --output-dir .local-e2e/release-candidates/ID/RUNNER
```

**Valid forms:** all four flags are required exactly once. The results and
output paths must use the plan candidate ID and selected runner exactly. The
output must not exist and may not be inside the results tree.

Sealing revalidates the plan against the clean current repository, then
requires exactly one result directory for every planned core. Missing,
duplicate, unexpected, failed, tampered, mixed-plan, mixed-runner, wrong-core,
extra-file, symlink, and package-byte drift all fail before a final output is
visible. A successful candidate contains `candidate.json`, `plan.json`, one ZIP
per core under `assets/`, and one portable result record per core under
`results/`. `asset_set_sha256` covers only sorted package identities, so equal
local and simulated-Actions builds have the same asset-set identity even though
their runner-bound candidate content hashes differ.

The release-plan schema is v2 so it can bind the coordinator and reusable
worker identities. Its target model, and the v1 worker-result/candidate
schemas, remain static-build-only and carry no device claims. Targets are
unique by architecture because current pins and E2E records expose one
evidence cell per architecture (`ra64-universal-v1` and `ra32-a30-v1`). A
future same-architecture sparse device override requires a later
execution-profile-keyed schema revision; it must not be squeezed into the
current architecture-keyed model.

**External data:** the canonical plan plus the complete portable worker-result
tree. Docker, source trees, the original E2E directories, credentials, and
network access are not needed by the seal itself. The result remains local-only
and publication-disabled; a separate explicitly approved publication workflow
would have to consume a sealed candidate.

### `update-channel`

Create or compare-and-swap one local channel pointer.

```text
update-channel --channel {nightly,pinned,release} --target PATH
               --core CORE
               (--expect-absent | --expect-current SHA256)
```

| Choice | Valid values |
| --- | --- |
| Channel | exactly one of `nightly`, `pinned`, or `release` |
| Target | exactly one `--target PATH` with the channel-specific shape below |
| Namespace | exactly one cataloged `--core CORE` for its individual v2 alias |
| Expected state | exactly one of `--expect-absent` or `--expect-current SHA256` |

The channel and expectation rows are independent, producing `3 × 2 = 6` valid
operation families. The target and core rows are required in every family.
Omitting both expectation flags, supplying both, omitting `--core`, or supplying a
non-lowercase/non-64-character current SHA-256 is invalid.
`--expect-absent` is valid only when the pointer in the selected namespace
does not exist. `--expect-current` must equal that pointer's exact file hash;
there is no force update. Repeating scalar flags is non-canonical.

The pointer written is `.local-e2e/channels/<channel>.<CORE>.json`, using
schema v2 with `core_id` exactly equal to `CORE`.

| Channel | Required target shape | Individual target rule |
| --- | --- | --- |
| `nightly` | `.local-e2e/nightlies/<semantic-id>/golden.json` | `build_goldens` has exactly the one key `CORE`, whose bundle is complete |
| `pinned` | `pins/core-sets/<semantic-id>.json` | the canonical pin validates and its scope is exactly `[CORE]` |
| `release` | `.local-e2e/releases/<semantic-id>/release-manifest.json` | the release validates and its resolved pin scope is exactly `[CORE]` |

Targets are deeply validated, must be backed by required store/source evidence,
must remain unchanged during the operation, and may not traverse a symlink.
Their source identities must also pass current catalog/blacklist admission. For an individual update,
`CORE` must be a current catalog key. Every schema-v2 target is deliberately
restricted to exact one-core scope: a nightly golden may not retain evidence
for any other core, a pin's scope must be exactly `[CORE]`, and a release must
resolve to such a pin.

The retired aggregate v1 pointers live only in git history. Active channel
commands cannot create, advance, or select that aggregate namespace. Updating Handy cannot change
Stella 2014's pointer, or vice versa.

**External data:** the target and all of its transitive pin, release, store, and
source-golden data; the current pointer for compare-and-swap; and the catalog
for current admission and individual-core membership. The selected individual
pointer must be absent for `--expect-absent`, or must be a valid matching v2
document for `--expect-current`. Use `validate-channel` with the same
`--channel` and `--core` to
obtain `pointer_file_sha256`. Per-core source locks and source-set documents
are not read directly.

### `validate-channel`

Deeply validate a channel pointer and its immutable target.

```text
validate-channel --channel {nightly,pinned,release} --core CORE
```

| Choice | Valid values |
| --- | --- |
| Channel | exactly one of `nightly`, `pinned`, or `release` |
| Namespace | exactly one `--core CORE` for its individual v2 alias |

There are three active forms, one for each channel, and no pointer-path or
aggregate namespace override. Validation reads
`.local-e2e/channels/<channel>.<CORE>.json`, requires schema v2 with the same
`core_id`, and enforces the channel-specific one-core target rule documented
for `update-channel`. The archived schema-v1 documents are regression fixtures,
not CLI inputs. `CORE` must use the core-ID syntax
`[a-z0-9][a-z0-9_]*`; this read-only command validates the pointer and target
rather than checking current catalog membership.

**External data:** the pointer, its exact channel-specific target, and all
transitive store, release, source-golden, and pin-lineage data required by that
target. The command prints `pointer_file_sha256`, which is the value required by
a later `update-channel` using the same namespace and
`--expect-current`. Validation also needs the one-core pin or release identity
named by the target. The catalog, current blacklist, per-core source locks, and
source-set documents are not read.

## Exit status and output

- `0`: the command completed successfully, validation passed, or help was
  displayed.
- `1`: a completed audit, build, E2E, or validation reported a non-passing
  result.
- `2`: argument parsing failed or the pipeline rejected an invalid identity,
  path, environment, manifest, or operation.

Most commands print JSON summaries to standard output. Builds also stream the
container log. Errors are printed to standard error. Treat a partial E2E's
nonzero status as expected only when the run was intentionally diagnostic; its
evidence is not package or promotion evidence.
