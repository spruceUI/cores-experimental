# Pipeline overview and reference

For ordered `main`/`nightly`/`edge` build-pin/deferred selections,
track-local stable approval, typed chipset profiles, and the empty `universal`
fallback, see [Core tracks, stability, and chipset
selection](core-track-groups.md).

Moved from the repository README, which keeps only the purpose summary
and the device x core compatibility matrix. This document reads top-down
from light to heavy: where things stand, then the concepts, then the
full operational reference. The focused runbooks in this directory go
deeper on each area.

**Contents:**
[Repository map](#repository-map) ·
[Current status](#current-status) ·
[Concepts](#concepts) ·
[Operational reference](#operational-reference)

## Repository map

| Path | Role |
|---|---|
| `manifests/` | The reviewed build catalog (`core-builds.json`), its schemas, per-core compatibility documents, device runtime contracts, execution profiles |
| `pins/` | Content-addressed provenance: per-core source locks, source-sets, core-sets, generated evidence indexes, and the toolchain archive lock |
| `scripts/` | The pipeline (`core_pipeline.py` + `core_pipeline_lib/`), promotion tooling (`promote_core.py`, `evidence_index.py`), verification sweep (`verify_core.py`), profile registry, toolchain-archive validator, device probe |
| `patches/` | Reviewed per-core build overlays, sha-pinned pre- and post-image |
| `metadata/` | Repo-pinned `.info` files for cores absent from libretro-super |
| `toolchain-inputs/` | Pinned docker build context for the three toolchain images (see its README) |
| `Dockerfile.arm64`, `Dockerfile.armhf`, `Dockerfile.rust` | The three locked compiler images (`.base` files are historical records) |
| `Dockerfile.tests`, `requirements-test.txt` | Separate version-locked host/test environment for mandatory JSON Schema validation; never a core compiler image |
| `.github/workflows/` | 98 read-only per-core dispatchers plus the release orchestration pair |
| `tests/` | The suite; migration scoreboard literals live in `tests/expected_counts.py` |
| `docs/` | Architecture, operations, and onboarding runbooks |
| `policies/`, `runtime/` | Admission policy and runtime smoke assets |

## Current status

Everything in this section is measured state, regenerable from the
repository: the migration scoreboard, the ABI floor/ceiling join, and
the uncataloged tail.

### Migration status

- **The first release candidate is sealed** (2026-07-24, run
  30124953754): all 98 cores rebuilt on GitHub Actions byte-identical to
  their local pins after wildcard source enumeration was made
  deterministic, and the fail-closed seal accepted the complete fan-in.
- **All 98 shipped-core workflows are migrated** to the shared,
  source-pinned, publication-disabled fail-closed pipeline: every cataloged
  core is a canonical individual-core record with a pinned source
  (url + commit + tree), a per-arch build-log proof, dual-build byte-identical
  reproduction (simulated-Actions + independent local), and a
  `manifests/compatibility/<core>.json` document binding the evidence. The
  pending bucket is empty; the audit reports 98/98 catalog cores on the
  shared dispatcher with zero masked failure paths.
- The toolchain lock holds **three images**: the v4 C cross pair
  (CMake 3.31.6, qemu-user, per-ABI inih, libpng dev, and one isolated
  static dependency prefix per ABI at `/usr/local/easyrpg-deps-<abi>`)
  plus the standalone Rust image for the `direct-cargo` driver
  (pinned Rust 1.90 / zig 0.13). Every image input is a repo-tracked,
  sha-pinned tarball, and `pins/toolchains/local-cache-v1.json` locks
  all three portable archives to their compressed bytes, image IDs, and
  Dockerfile descriptions. **Every pin-set records the current image
  ids** (the catalog was re-promoted onto this lock 2026-07-24).
- The canonical evidence index is `manifests/compatibility/*.json`: each
  document's `golden_source` names the core's current pin under
  `pins/core-sets/`, with its source set under `pins/source-sets/`. All
  active lifecycles use individual core files and semantic IDs; grouped
  identifiers are retired history, and the candidate-id guard rejects
  historical batch names ("tranche").

Nothing in `scripts/core_pipeline.py` publishes to GitHub. Local output is
written beneath `.local-e2e/`, which is ignored by Git.

### ABI floors and ceilings (glibc / libstdc++)

**With the Mini family's bundled libstdc++ updated to the A30 provider
(libstdc++ 6.0.32, GLIBCXX 3.4.32 — spruceOS Development `97f9fb558`),
no currently pinned core is blocked by a glibc or libstdc++ floor or
ceiling on any probed device.** The over-ceiling (`C`) class in the
device matrix is empty; every eligibility miss that remains is a missing
library or an unprobed device, never a symbol-version ceiling. This
holds for spruce builds carrying that provider — on older Mini firmware
the packaged fallback provider stops at GLIBCXX 3.4.24, which would put
the modern-toolchain C++ cores back over the ceiling.

Effective requirements, measured across all 98 pinned cores (the maximum
any core's artifact demands):

| Arch | max GLIBC | max GLIBCXX | max CXXABI | set by |
|---|---|---|---|---|
| arm64 | 2.29 | 3.4.26 | 1.3.11 | tyrquake / neocd / flycast |
| armhf | 2.18 | 3.4.32 | 1.3.13 (+ CXXABI_ARM 1.3.3) | libgametank / nestopia / km_parallel_n64 |

Captured per-device libstdc++ provider ceilings (loader-truth probe):

| Device family | ABI | GLIBCXX ceiling | Headroom vs pinned max |
|---|---|---|---|
| Miyoo A30 | armhf | 3.4.32 (A30 provider) | 0 — requirement sits exactly at the ceiling |
| Miyoo Mini family | armhf | 3.4.32 (bundled A30 provider) | 0 — same; 3.4.24 on the pre-update fallback |
| Miyoo Flip | arm64 | 3.4.32 | +6 minor versions |
| Trimui Brick / Smart Pro | arm64 | 3.4.28 | +2 |
| Trimui Smart Pro S | arm64 | 3.4.28 | +2 |
| GKD Pixel 2 | arm64 | 3.4.33 | +7 |
| Anbernic H700 family | — | not probed | fails closed (`?` in the matrix) |
| MagicX Zero28 | — | not probed | fails closed (`?` in the matrix) |

Two consequences worth keeping in view:

- **armhf has zero ceiling headroom.** The armhf toolchain (GCC 13.2)
  emits GLIBCXX 3.4.32 symbols and the fleet provider supplies exactly
  3.4.32: any future armhf toolchain bump that emits newer symbols
  exceeds every armhf device at once, and would need a provider-bundle
  update to land first (the Lever-B mechanism in
  [device-abi-variant-sets-design.md](device-abi-variant-sets-design.md)).
- **glibc floors clear with similar margins.** The armhf maximum
  (GLIBC 2.18, libgametank's zigbuild floor) equals the weakest device's
  glibc; the arm64 maximum (2.29) resolves on every probed arm64 device
  — proven by the loader-truth join behind each matrix `Y`, which
  verifies the full needed-set resolution, glibc included.

### Uncataloged shipped binaries (custom-build tail)

These cores are shipped by spruceOS but can't be built from libretro-super and need custom build processes:

- [ ] **mkxp-z** — hyphen in name breaks libretro-super's bash variable parsing
- [ ] **mupen64plus** — removed from libretro-super (replaced by mupen64plus_next)
- [ ] **km_flycast_xtreme** — KMFDManic/morpheuscast_xtreme fork uses bare `as` for ARM64 assembly, not cross-compile friendly
- [ ] **km_ludicrousn64_2k22_xtreme_amped** — KMFDManic fork has broken aarch64 dynarec source and missing includes

## Concepts

The ideas the evidence model is built on: golden tiers (what a record
is allowed to claim), and where evidence physically lives plus what the
validation gate does and does not cover.

### Golden tiers

- `imported_baseline` pins the SHA256 and validated ELF metadata of the binaries
  currently shipped by the sibling SpruceOS checkout. Active imports create a
  schema-v2 candidate whose `cores` and `build_goldens` maps each contain
  exactly the selected core. It is a byte-level starting point, not
  reproducible build provenance.
- `build_golden` is an append-only, local static-build pin. It requires an exact
  source and tree commit, coherent submodules, exact Docker image ID, recipe
  hashes, exact portable-archive lock provenance, a complete passing ARM64/ARMHF
  E2E package, and valid target ELFs with the required libretro exports. The
  schema-v1 aggregate remains immutable historical evidence; active promotion
  and lifecycle records use singleton schema-v2 state.

An imported baseline is never silently promoted. Failed and foreign-architecture
artifacts remain recorded as rejected evidence.

### Evidence locality and validation scope

The aggregate-era chronology (tranches, grouped pins, their fixtures and
readers) was retired on 2026-07-23 and lives only in git history (last
present at `dd82cc4`). Each top-level `manifests/compatibility/*.json`
file with its one-core pin, source set, and focused test is the current
record; anything under `manifests/compatibility/pending/` is a
transition record making no compatibility claim.

The store and run directories are intentionally ignored and local-only:
paths in per-core records identify workspace-local evidence, not files
available from a fresh clone. Preserve them with the workspace — a fresh
clone can read pin metadata but cannot recover the source-built bytes.
The cached image archive bytes and IDs are portable and immutable
through the toolchain lock, while the Dockerfiles remain explicitly
unverified descriptions of those caches.

The JSON schemas, including the toolchain-lock, core-set, and local-release
schemas, are editor and documentation aids. The normative executable checks are
`catalog-check`, `validate-golden`, `validate-pin-set`, `validate-release`,
`toolchain_archive.py validate-lock`, `toolchain_archive.py verify-downloads`,
artifact validation, E2E package
validation, and the unit suite; schema conformance is not claimed as a runtime
gate.

There is currently no target RetroArch/QEMU runner or redistributable ROM fixture
in this repository. The present build/package E2E gate therefore covers the
shared command's containerized compilation, packaging, ABI, recorded dependency
metadata, and libretro API surface. It does not validate GitHub Actions runtime
semantics, target dependency availability, version floors, loadability, gameplay,
or runtime compatibility, so build goldens are explicitly marked
`static-build-only`.

## Operational reference

The heavy matter: full walkthroughs of the build/package path, the
toolchain archive lock, and per-core pinned/release validation. The
condensed operator flow lives in
[core-pipeline-operations.md](core-pipeline-operations.md); onboarding a
new core is [adding-a-new-core.md](adding-a-new-core.md).

Verification is two named tiers: the local static tier
(`scripts/verify_core.py --all` plus the unit suite — minutes, proves
every tracked binding against promoted disk evidence) and the roster
rebuild tier (the GitHub Actions release-candidate workflow — hours, the
only place from-source rebuild reproducibility is proven).

### Local build/package simulation

For the concise operator workflow—including runner profiles, unit tests,
source-commit lifecycle status, promotion, and commit blacklisting—see
[`docs/core-pipeline-operations.md`](core-pipeline-operations.md).
Every entry-script command, valid flag combination, runner environment, and
external input is covered by the
[`docs/core-pipeline-cli-reference.md`](core-pipeline-cli-reference.md).
The package boundaries and extension rules are documented in
[`docs/core-pipeline-architecture.md`](core-pipeline-architecture.md).

Project the built cores into per-device candidate sets — the cores that build
for a device's architecture and clear its captured libstdc++ provider ceiling —
with `scripts/device_sets.py`. This is a static ABI screen only (necessary, not
sufficient); every device view stays provisional until a target-runtime smoke
test is captured, and nothing here promotes, packages, or publishes:

```bash
python3 scripts/device_sets.py report
python3 scripts/device_sets.py report --device device-miyoo-mini-family-v0
```

Project each core's tracked evidence into a compact device-fitness record — the
authoritative pin reference plus, per ABI, the artifact hash, execution profile,
toolchain image id, runtime deps, and ABI floors — with `scripts/fitness_record.py`.
It references the pin for full identity rather than duplicating provenance; the
`runtime_smoke` field stays `pending` until a target-runtime smoke test exists:

```bash
python3 scripts/fitness_record.py report
python3 scripts/fitness_record.py report --core gearboy
```

After the build/promote/derive/compose-golden/compose-pin chain, compose the
two remaining lifecycle artifacts (source-set + compatibility manifest)
deterministically instead of by hand, with the device-eligibility caveat derived
from the captured `version_requirements`:

```bash
python3 scripts/promote_core.py compose-lifecycle \
  --core CORE --semantic-id SEMANTIC_ID \
  --selected-run SELECTED_RUN_ID --reproduction-run REPRO_RUN_ID
```

Review the tiered promotion gate — heavy (registered exact-transcript contract)
vs light (valid static build golden plus a passing target-runtime smoke); the
runtime smoke is required for a full promotion in both tiers:

```bash
python3 scripts/contract_tier.py report
python3 scripts/contract_tier.py gate --core CORE --smoke pass
```

Validate the active catalog, workflow inventory, and individual records:

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
  --source-set pins/source-sets/mednafen_pcfx-650c30ea2203-d3672dc81b75.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/pokemini-bb009b1379ad-3abb4885cf09.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearcoleco-112345747c04-cc2d4bc38005.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_x64-7946cfa0d377-4b611c28b848.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_xvic-7946cfa0d377-e23a9971f265.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fmsx-f013e213458e-e649daf16694.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/bluemsx-5f595c79906f-5d1ea1b42de8.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005-b60356971fc9-89b3519fa99d.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005_plus-b60356971fc9-1d19ddd8a238.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/cap32-4abfb8be233b-82ddcfcacee0.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/crocods-87bbb3d9007a-987ab7429a42.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/genesis_plus_gx_wide-29d9d104338f-6184c4659fe1.json
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
  --source-set pins/source-sets/81-fa7094910d04-8504f7df5dd8.json
python3 -B -m pytest --import-mode=importlib -p no:cacheprovider tests/ -q
```

Run one complete core through the shared build/package path used by migrated
workflows. Replace the core and run ID for any cataloged core; the command reads
that core's exact targets and recipe from the catalog.

```bash
python3 scripts/core_pipeline.py build-core \
  --runner-profile local \
  --core handy \
  --run-id local-handy

python3 scripts/core_pipeline.py build-core \
  --runner-profile github-actions-sim \
  --core stella2014 \
  --run-id actions-sim-stella2014
```

The E2E command verifies the pinned image ID, checks out the exact core source commit
before updating submodules, sanitizes compiler variables, builds both targets,
validates ELF/ABI and libretro symbols, and creates a local ZIP only when all
catalog targets pass. The ZIP preserves the legacy `cores/`, `cores64/`, and
`<core>_libretro.info` layout.

Per-target compatibility definitions are restricted to sorted, unique
`NAME=unsigned-integer` catalog entries. The runner clears inherited flags before
exporting only those definitions, records the exact selected list, and requires
every target-compiler `-c` line in the immutable build log to contain the exact
definitions with no conflicting redefinition or undefine before a build can pass
or be promoted. Arbitrary compiler or linker flags are not accepted. This is
fail-closed command-line build-log evidence, not a kernel-level compiler
execution trace or proof against source-level macro changes.

Registry-owned chipset tuning uses the same sanitized compiler boundary but a
closed mapping from typed properties to machine arguments. A new tuned pin is
bootstrapped with two separate `e2e --tuning-profile PROFILE` runs and
`promote-tuned-variant`: each log must prove the contract independently, while
artifact, metadata, and complete one-ABI package bytes must match exactly.
Different valid log hashes are permitted. The promoted recipe snapshots the
exact tuning registry and both E2E proof sides. `core-track-set-test` then
admits a hardened host-reproduction-bearing pin under direct-cell, complete
assignment, and new-variant CAS without changing stable approval. Its required
UTC-second slice is immutable assignment/tranche identity but is excluded from
build variant identity. Nightly and Edge additionally CAS and capture both the
current effective parent variant and parent registry, including the parent's
slice/history, for assignment-time ordering. Later parent movement leaves that
child binding intact. The command also supports an untuned `universal-v1` pin
with explicit fallback applicability and corresponding ABI coverage. See
[Core tracks, stability, and chipset selection](core-track-groups.md).

An optional per-core `build.source_date_epoch` is an exact integer recipe input.
The runner first clears any inherited value, exports it only for the declaring
core, and after checkout requires it to equal the pinned commit timestamp before
building. This makes compiler expansions such as `__DATE__` and `__TIME__`
repeatable without patching upstream source. The selected value is recorded in
the build record, recipe snapshot, promoted golden, stored evidence, and
provenance identity. It does not claim to sanitize arbitrary mtime-based source
generators.

An optional `build.git_version` is a closed, core-specific version contract.
Reviewed derivations include an injected hyphen-prefixed short hash, native
Makefile leading-space short hashes of fixed length, and an exact native
`git describe` value. The runner clears ambient version and Git-config state,
applies a derivation-specific recursive-Make input or fixed Git setting only
when required, records the injected or native Make origin, and requires the
exact quoted macro on every compiler command in that contract's C/C++ scope
with no conflicting token. The full 40-character source commit remains
authoritative; the derived value is deterministic source/runtime identity for
the ABI builds, not a substitute pin.

Per-core contracts follow a small set of archetypes — exact-transcript
proofs, native-version C-only and mixed-language proofs (with or without
reviewed diagnostic streams), host-specialization portability recipes,
and recursive-source or numeric-ID variants. Each core's
`scripts/core_pipeline_lib/contracts/<core>.py` module and
`tests/test_contract_<core>.py` are the authoritative reference for its
shape; per-core example narratives are not duplicated here (older ones
live in this file's git history).

The `direct-cmake` driver uses fixed `/tmp/core-source` and `/tmp/core-build`
paths, typed target-system and cross-tool arguments, and a post-configure cache
proof before compilation. Target-scoped source overlays are content-addressed,
single-file patches: the runner verifies patch, preimage, postimage, and exact
dirty paths before CMake runs. A core may also reject catalog-bound dynamic
dependency families during both build and durable store validation.

This is build/package E2E, not a local GitHub Actions runner. It does not execute
the Actions checkout implementation, toolchain-release download, cache/archive
loading, permission enforcement, or reusable-workflow orchestration. Those YAML
surfaces are parsed and audited separately; the migrated jobs then invoke the
same shared command documented above.

Promotion requires both a target record and the complete passed, schema-v2
E2E record for exactly that one core. Architecture-subset E2E runs remain
diagnostic and cannot be promoted; multi-core E2E runs are not supported:

```bash
python3 scripts/core_pipeline.py promote \
  --golden .local-e2e/nightlies/mgba-candidate-01/golden.json \
  --record .local-e2e/runs/local-mgba/mgba/arm64/build-record.json \
  --e2e-record .local-e2e/runs/local-mgba/e2e-record.json
```

Promotion copies the artifact, `.info`, both target build records and logs,
exact snapshots of the selected dirty-worktree recipe surfaces for both targets,
the E2E record, and the package into
the local content-addressed store at `.local-e2e/store/`. An existing
core/architecture golden cannot be overwritten; a future candidate must use a
new core-owned candidate golden and pin. Recipe snapshot v3 explicitly binds the sanitized build environment
and target definitions; v4 additionally binds a declared source-date epoch; v5
binds typed direct-CMake systems, target-scoped overlays, and exact patch bytes;
v6 binds the portable FFmpeg Make contract, and v7 binds a commit-derived
`GIT_VERSION` contract. Recipe snapshot v8 binds the normalized combination of
a native `GIT_VERSION` contract and typed Make variables, including the exact
per-compile variant proof used by Snes9x 2005 Plus.
Deep pin validation also rechecks legacy v2 snapshots against their embedded
catalog source/build contract and immutable compiler log.

### Local toolchain archive lock

The cached images are preserved as gzip-compressed hybrid OCI/Docker-save
archives. Importing them is create-only and local: it fully validates each
archive, stages the original compressed bytes by SHA256, and then creates the
tracked metadata lock without invoking Docker:

```bash
python3 scripts/toolchain_archive.py import-lock \
  --arm64 /tmp/cores-arm64.tar.gz \
  --armhf /tmp/cores-armhf.tar.gz \
  --rust /tmp/cores-rust.tar.gz
python3 scripts/toolchain_archive.py validate-lock
python3 scripts/toolchain_archive.py validate-lock --verify-store
python3 scripts/toolchain_archive.py verify-downloads \
  --lock pins/toolchains/local-cache-v1.json \
  --arm64 /tmp/cores-arm64.tar.gz \
  --armhf /tmp/cores-armhf.tar.gz \
  --rust /tmp/cores-rust.tar.gz
```

Metadata-only validation does not require the ignored local store.
`--verify-store` streams the staged archives again. It checks the outer size and
SHA256, gzip CRC/end size, bounded canonical tar layout, every blob filename
digest, strict duplicate-free JSON, the complete OCI descriptor/config/layer
graph, Docker `manifest.json`/`repositories`/`LayerSources` agreement, ordered
rootfs diff IDs, the `linux/amd64` container platform, `/libretro-super`
working directory, and target `HOST_CC`.

The exact compressed identities are
`8a3bdd7f…` (502,531,978 bytes, ARM64), `f297cbf9…` (835,303,648 bytes,
ARMHF), and `38ad84b2…` (999,801,265 bytes, Rust); the lock file is
authoritative. CAS paths are
`.local-e2e/store/toolchain-archives/sha256/<first-two>/<sha256>`. Import uses a
chunked temporary file plus a create-only hard link; an existing regular file
must reproduce its name digest and size, while symlinks and collisions fail
closed. The read-only `verify-downloads` gate checks the downloaded filenames,
sizes, and SHA256 identities before any image can be loaded, and every
per-core workflow runs that gate between download and `docker load`. The
catalog and build records bind the exact lock file/content identity and
selected architecture archive, plus the exact checksum-verifier implementation.

The lock explicitly retains `unverified-local-cache` Dockerfile linkage: the
archive proves the cached image bytes and runtime build environment, but it
cannot retroactively prove that the image was built from the current Dockerfile.

### Individual-core pinned and release validation

New migrations use one immutable pin, source set, compatibility record, test
module, and channel namespace per core. The complete operator procedure is in
[`docs/core-pipeline-operations.md`](core-pipeline-operations.md), and all
flag combinations and required external data are in
[`docs/core-pipeline-cli-reference.md`](core-pipeline-cli-reference.md).

Validate the current Handy lifecycle independently:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/handy-bc55d462f0b2-c82a2178b4f0.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/handy-bc55d462f0b2-c82a2178b4f0.json \
  --release .local-e2e/releases/handy-bc55d462f0b2-c82a2178b4f0 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel --channel pinned --core handy
```

Every canonical core has the same isolated lifecycle under its own
semantic ID (`<core>-<source12>-<selection12>`): substitute it into the
four commands above. The per-core bindings — semantic ID, selected and
reproduction run IDs, package/artifact digests, proof shape, and the
remaining static-build-only caveats — are recorded in each core's
`manifests/compatibility/<core>.json` and enforced by
`tests/cores/test_<core>.py`; per-core walkthrough narratives are not
duplicated here (older ones live in this file's git history).

Use `tests/cores/test_<core>.py` for core-owned contract tests. Device buildsets
may reference the same portable core record; they do not create another pin
unless captured ABI or build-flavor evidence requires different artifacts.

### Release path in brief

Use the per-core commands above or the complete
[`docs/core-pipeline-operations.md`](core-pipeline-operations.md) runbook.
The local full-release path is plan, per-core result fan-out, and exact fan-in
sealing:

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

Run the result command once per planned core after its fresh E2E build. The
publication-disabled `release-candidate.yml` coordinator derives that same
matrix and calls one reusable `_build-one-core.yml` worker per row. This avoids
the call-tree limit of 50 unique reusable workflows: the current canonical
roster uses one matrix row per core and one reusable workflow, within the
256-job matrix limit, rather than one distinct reusable wrapper per core.
Individual workflows remain direct-build
entrypoints and are not chained by the coordinator. Actions treats
`candidate_label` only as an operator label: run ID and attempt are appended to
form the plan's immutable candidate ID, and result artifacts are
attempt-qualified for safe failed-job reruns.

Planning, worker results, and sealing are publication-disabled. A future
separate, explicitly approved publish workflow may consume a sealed candidate
without rebuilding it. Release-plan schema v3 binds the coordinator and worker
identities plus an explicit nullable track-group contract, while its target
model and the v2 result/candidate schemas remain architecture-keyed and
static-build-only. A second execution profile for the
same architecture needs a later execution-profile-keyed schema revision and
cannot be represented by duplicating an architecture target.
