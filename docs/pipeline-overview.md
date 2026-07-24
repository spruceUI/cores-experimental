# Pipeline overview and reference

Moved from the repository README, which now keeps only the purpose
summary and the device x core compatibility matrix. This document is the
narrative reference for how the pipeline is laid out and operated; the
focused runbooks in this directory go deeper on each area.

## Repository map

| Path | Role |
|---|---|
| `manifests/` | The reviewed build catalog (`core-builds.json`), its schemas, per-core compatibility documents, device runtime contracts, execution profiles |
| `pins/` | Content-addressed provenance: per-core source locks, source-sets, core-sets, and the toolchain archive lock |
| `scripts/` | The pipeline (`core_pipeline.py` + `core_pipeline_lib/`), promotion tooling, profile registry, toolchain-archive validator, device probe |
| `patches/` | Reviewed per-core build overlays, sha-pinned pre- and post-image |
| `metadata/` | Repo-pinned `.info` files for cores absent from libretro-super |
| `toolchain-inputs/` | Pinned docker build context for the three toolchain images (see its README) |
| `Dockerfile.*` | The three locked toolchain images (`.base` files are historical records) |
| `.github/workflows/` | 98 read-only per-core dispatchers plus the release orchestration pair |
| `tests/` | The suite; migration scoreboard literals live in `tests/expected_counts.py` |
| `docs/` | Architecture, operations, and onboarding runbooks |
| `policies/`, `runtime/` | Admission policy and runtime smoke assets |

## Migration status

- **All 98 shipped-core workflows are migrated** to the shared,
  source-pinned, publication-disabled fail-closed pipeline: every cataloged
  core is a canonical individual-core record with a pinned source
  (url + commit + tree), a per-arch build-log proof, dual-build byte-identical
  reproduction (simulated-Actions + independent local), and a
  `manifests/compatibility/<core>.json` document binding the evidence. The
  pending bucket is empty; the audit reports 98/98 catalog cores on the
  shared dispatcher with zero masked failure paths.
- The toolchain lock holds **three images** (the v4 C cross pair plus the
  standalone Rust image for the cargo driver): the v2
  base (CMake 3.31.6, qemu-user, per-ABI inih, arm64
  pixman/fmt/expat/icu apt set) plus libpng dev in both sysroots and one
  isolated static dependency prefix per ABI
  (`/usr/local/easyrpg-deps-<abi>`: pinned pixman, expat, fmt, ogg,
  vorbis, mpg123, sndfile, and ICU 78.3 static with EasyRPG's trimmed
  converter data). Every image input is a repo-tracked, sha-pinned
  tarball; the dep block stays one COPY + one RUN per image because the
  lock captures small tar members under a bounded aggregate. The 96
  pre-v4 pin-sets still record their v2 image ids — a deferred-hygiene
  re-promote wave, byte-identical by layer inheritance (v2-cutover
  precedent `cdff35a`/`9d95cda`).
- The canonical evidence index is `manifests/compatibility/*.json`: each
  document's `golden_source` names the core's current pin under
  `pins/core-sets/`, with its source set under `pins/source-sets/`. New
  migrations use individual core files and semantic IDs for pins, source
  sets, compatibility documents, tests, run IDs, and channel aliases; active
  work never uses a historical grouping.
- **Zero fail-open workflows remain.** The final two migrated 2026-07-24:
  `easyrpg` (full static dependency closure; its rebuilt artifacts need
  only the loader base set plus the capture-proven
  `libpng16.so.16`/`libz.so.1`, eligible on every probed device where the
  previously shipped arm64 build loaded on none) and `libgametank` (the
  first `direct-cargo` core: upstream's committed Cargo.lock is the
  checksummed dependency pin, builds run `--locked` inside the third
  locked image — a standalone pinned Rust 1.90/zig 0.13 toolchain — and
  the log proof pins the lock digest, the exact zigbuild invocation, and
  the 69-crate compiled multiset).
- The aggregate-era chronology (tranches, `golden-start` composer, frozen
  fixtures and their regression readers) was retired on 2026-07-23 and is
  preserved only in git history. Never use a historical batch identifier
  ("tranche") for new work; the candidate-id guard rejects such names.
- `pins/toolchains/local-cache-v1.json` locks the three portable cached-image
  archives (arm64/armhf C cross plus the Rust image for the cargo driver) to their compressed bytes, complete OCI/Docker-save graphs, image
  IDs, cross-compiler environments, and current Dockerfile descriptions.

Nothing in `scripts/core_pipeline.py` publishes to GitHub. Local output is
written beneath `.local-e2e/`, which is ignored by Git.

## ABI floors and ceilings (glibc / libstdc++)

**With the Mini family's bundled libstdc++ updated to the A30 provider
(libstdc++ 6.0.32, GLIBCXX 3.4.32 — spruceOS Development `ee825739d`),
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

## Golden tiers

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

## Local build/package simulation

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
  --source-set pins/source-sets/handy-bc55d462f0b2-6923119e1743.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/stella2014-4a7da82595d2-1fb14ddbab91.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fceumm-718c5a2e1757-741c3fcc6002.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gambatte-dfc165599f3f-9a6aa3658c05.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/tgbdual-bf816b096f1d-8118d938b91c.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/quicknes-26bb785c9ded-2f0351a7573f.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/nestopia-b0fd87dd07e3-7393d0fca106.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/a5200-23c1ea482afb-f37877a31d37.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/prosystem-363b6dfbd3e2-cb86034fdd05.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x-185488cd83aa-1007f6c98b6b.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supafaust-2b93c0d7dff5-21be3575be39.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supergrafx-3c6fcd3deded-6f92f2753900.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_wswan-da6d0d9acb8d-cc4a98ceff16.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pcfx-650c30ea2203-5c0f9a256d9a.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/pokemini-bb009b1379ad-2f63e84b7b68.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearcoleco-112345747c04-046c086031cf.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_x64-7946cfa0d377-290256f3bebd.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vice_xvic-7946cfa0d377-6f9943958478.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/fmsx-f013e213458e-194b406b9096.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/bluemsx-5f595c79906f-a1c1fd914a76.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005-b60356971fc9-06b9f12c860c.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/snes9x2005_plus-b60356971fc9-32f28e9ec741.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/cap32-4abfb8be233b-afbc043051e8.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/crocods-87bbb3d9007a-7b4aa1fce1f1.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/genesis_plus_gx_wide-29d9d104338f-7907e7e03389.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/o2em-e03d3be88f79-ede84c3862de.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/freechaf-76c7a84f1f7e-0fced3806666.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/vecx-8f671cc9d737-4686ef94bf56.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/lowresnx-35adc1a215e9-837092a5ffca.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/race-c7810dd7f172-c3119de987bf.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/potator-227c5f6f3ce7-1617e2249087.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearboy-36d723ff4410-f6f1b63e8798.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/gearsystem-4f029e43f2d5-35212fbb9d9a.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/2048-c90437d3c391-86ed146bc647.json
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/81-fa7094910d04-a82f6eb4a7cc.json
python3 -m unittest discover -s tests -v
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

Mednafen Supafaust is a core-owned exact-contract example: its registered proof
requires 44 C++ compile commands per ABI with `GIT_VERSION="-2b93c0d"`, the
exact compile/output and link-object identities, the reviewed link options, and
the complete ordered diagnostic streams even when parallel jobs interleave
those streams.

Mednafen Virtual Boy is a native-version mixed-language example. Its core-owned
proof binds the exact native leading-space version ` 38e7a0e` to all 10 C and
three C++ compile commands and proves the complete ordered 13-object C++ link.
ARM64 must remain diagnostic-clean; ARMHF admits only its two exact reviewed GCC
psABI notes.

Mednafen Lynx is the C++-scoped native-version mixed-language example. Its
core-owned proof binds native leading-space version ` fcdefcf` only to the 16
C++ compiles, requires all 13 C compiles and the complete ordered 29-object C++
link, and requires the exact per-ABI truncation warning and associated note.
ARMHF additionally admits only its two exact reviewed GCC 7.1 psABI notes; the
two complete diagnostic blocks may appear in either order but remain
fail-closed internally.

Mednafen PCE Fast is the no-version C-only compile example. Its core-owned proof
requires exactly 92 C compiles, no C++ compiles or injected/native version
token, the complete ordered 92-object C++ link, exact source and success
framing, and zero warnings, notes, errors, or fatal diagnostics.

Mednafen SuperGrafx is the C++-scoped native-version mixed-language example.
Its core-owned `mednafen-supergrafx-mixed-language-v1` proof binds native
leading-space version ` 3c6fcd3` only to 29 C++ compiles, requires all 60 C
compiles and the complete ordered 89-object C++ link, and binds every reviewed
diagnostic occurrence to its owning source compile while admitting valid
parallel-stream interleaving.

Mednafen WonderSwan is the native-version mixed-language example. Its
core-owned proof binds upstream's leading-space short hash to all 14 C and one
C++ compile commands, the complete ordered 15-object C++ link, and the exact
architecture-specific warning and GCC psABI note streams.

Mednafen PC-FX is the host-specialization portability example. Its recipe
requires the typed `IS_X86=0` Make input so host-x86 detection cannot add
ARM-incompatible x86/SSE paths. Its core-owned proof binds the native
leading-space short hash only to the 34 C++ compiles, requires all 60 C
compiles and the complete ordered 94-object C++ link, and accepts only the
reviewed per-stream diagnostic ordering when parallel output interleaves.

PokéMini is the native-version C-only example with reviewed diagnostics. Its
core-owned proof binds the leading-space short hash to all 43 C compiles, the
complete ordered 43-object C link, and exactly five warnings plus five notes per
ABI. The `.eep` path `sprintf` warning remains an unresolved potential overflow
risk rather than being normalized away.

O2EM is the native-version C-only example. Its catalog intentionally has no
synthetic `git_version`; the core-owned proof instead binds upstream's native
leading-space short hash on all 42 C compiles, the exact 42-object C link, and
zero compiler, linker, or process-failure diagnostics.

FreeChaF is the native-version C-only example with a recursive source. Its
core-owned proof binds the exact libretro-common gitlink, upstream's native
leading-space short hash on all 25 C compiles, the exact 25-object C link, and
the single reviewed unused-variable warning while rejecting any other
compiler, linker, or process-failure diagnostic.

VecX is the software-renderer native-version example. Its core-owned
`vecx-software-c-only-v1` proof requires `HAS_GPU=0`, binds the native
leading-space short hash on all four C compile commands, and proves the
complete ordered link command. It also binds the exact whole-file metadata
replacement and rejects GL-family inputs, GPU objects, compiler diagnostics,
and process failures.

LowRes NX is the larger native-version C-only example. Its core-owned
`lowresnx-c-only-v1` proof binds upstream's leading-space short hash to all 43
C compile commands, every ABI-specific compiler invocation, both reviewed
source/object orderings, and the complete ordered link command while rejecting
unreviewed diagnostics and path aliases outside the exact semantic scope.

RACE is the native-version C-only Neo Geo Pocket example. Its core-owned
`race-c-only-v1` proof binds the leading-space short hash to all 27 C compile
commands and the complete ordered C link with a zero-diagnostic envelope for
both ABIs. `ngpBios.c` is compiled internal source, not a packaged or required
external firmware blob. GPLv2 review remains a publication gate, ARMHF requires
`GLIBC_2.7`, and reset, options, unaligned-access behavior, frontend/runtime
integration, and every device claim remain unverified.

Potator is the native-version C-only Watara Supervision example. Its core-owned
`potator-c-only-v1` proof binds native leading-space version ` 227c5f6` to all
eight C compiles, proves the complete ordered C link, and preserves exactly the
four reviewed misleading-indentation CPU warning/note pairs while rejecting
unreviewed diagnostics and process failures.

Gearboy and Gearsystem are native-describe mixed-language examples. Their
core-owned proofs bind exact upstream descriptions `3.8.9-8-g36d723f` and
`3.9.12-5-g4f029e4` to all 40 and 46 compiles respectively, prove the complete
ordered C++ links, and require zero diagnostics. Each proof also binds the
complete source, toolchain, clean, compile, link, copy, and success sequence so
setup-region mutation, wrapper compilers, response files, and shell indirection
fail closed.

2048 is the numeric-ID native-version C-only example. Its core-owned
`core-2048-c-only-v1` proof binds the pinned source tree and upstream
leading-space short hash to all 16 C compile commands and the complete ordered
C link for both ABIs. The selected simulated-Actions run and independent local
run reproduce the package, metadata, logs, and both ABI artifacts exactly; its
canonical lifecycle remains static-build-only pending target-runtime evidence.

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

## Local toolchain archive lock

The cached images are preserved as gzip-compressed hybrid OCI/Docker-save
archives. Importing them is create-only and local: it fully validates each
archive, stages the original compressed bytes by SHA256, and then creates the
tracked metadata lock without invoking Docker:

```bash
python3 scripts/toolchain_archive.py import-lock \
  --arm64 /tmp/cores-arm64.tar.gz \
  --armhf /tmp/cores-armhf.tar.gz
python3 scripts/toolchain_archive.py validate-lock
python3 scripts/toolchain_archive.py validate-lock --verify-store
python3 scripts/toolchain_archive.py verify-downloads \
  --lock pins/toolchains/local-cache-v1.json \
  --arm64 /tmp/cores-arm64.tar.gz \
  --armhf /tmp/cores-armhf.tar.gz
```

Metadata-only validation does not require the ignored local store.
`--verify-store` streams the staged archives again. It checks the outer size and
SHA256, gzip CRC/end size, bounded canonical tar layout, every blob filename
digest, strict duplicate-free JSON, the complete OCI descriptor/config/layer
graph, Docker `manifest.json`/`repositories`/`LayerSources` agreement, ordered
rootfs diff IDs, the `linux/amd64` container platform, `/libretro-super`
working directory, and target `HOST_CC`.

The exact compressed identities are
`4dbf81aa...d9038d` (259,229,571 bytes, ARM64) and
`8a5cfa01...95919` (652,844,275 bytes, ARMHF). Their CAS paths are
`.local-e2e/store/toolchain-archives/sha256/<first-two>/<sha256>`. Import uses a
chunked temporary file plus a create-only hard link; an existing regular file
must reproduce its name digest and size, while symlinks and collisions fail
closed. The read-only `verify-downloads` gate checks both downloaded filenames,
sizes, and SHA256 identities before either image can be loaded. Every migrated
workflow listed above runs that gate between download and `docker load`. The
catalog and new v2 build records bind the exact lock file/content identity and
selected architecture archive, plus the exact checksum-verifier implementation;
existing v1 goldens and pin bytes remain unchanged.

The lock explicitly retains `unverified-local-cache` Dockerfile linkage: the
archive proves the cached image bytes and runtime build environment, but it
cannot retroactively prove that the image was built from the current Dockerfile.

## Individual-core pinned and release validation

New migrations use one immutable pin, source set, compatibility record, test
module, and channel namespace per core. The complete operator procedure is in
[`docs/core-pipeline-operations.md`](core-pipeline-operations.md), and all
flag combinations and required external data are in
[`docs/core-pipeline-cli-reference.md`](core-pipeline-cli-reference.md).

Validate the current Handy lifecycle independently:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/handy-bc55d462f0b2-6923119e1743.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/handy-bc55d462f0b2-6923119e1743.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/handy-bc55d462f0b2-6923119e1743.json \
  --release .local-e2e/releases/handy-bc55d462f0b2-6923119e1743 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel --channel pinned --core handy
```

Stella 2014 has the same isolated lifecycle:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/stella2014-4a7da82595d2-1fb14ddbab91.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/stella2014-4a7da82595d2-1fb14ddbab91.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/stella2014-4a7da82595d2-1fb14ddbab91.json \
  --release .local-e2e/releases/stella2014-4a7da82595d2-1fb14ddbab91 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core stella2014
```

Mednafen Supafaust uses the same individual-core lifecycle under semantic ID
`mednafen_supafaust-2b93c0d7dff5-21be3575be39`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_supafaust-2b93c0d7dff5-21be3575be39.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_supafaust-2b93c0d7dff5-21be3575be39.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_supafaust-2b93c0d7dff5-21be3575be39.json \
  --release .local-e2e/releases/mednafen_supafaust-2b93c0d7dff5-21be3575be39 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_supafaust
```

Its build contract, pin, source set, compatibility manifest, lifecycle test,
and selected/reproduction run IDs are all individual-core:
`scripts/core_pipeline_lib/contracts/mednafen_supafaust.py`,
`manifests/compatibility/mednafen_supafaust.json`,
`tests/cores/test_mednafen_supafaust.py`,
`actions-sim-build-core-mednafen_supafaust-v2`, and
`build-core-mednafen_supafaust-local-v2`. Exact build-log proof coverage stays
in `tests/test_contract_mednafen_supafaust.py`.

Mednafen Virtual Boy uses semantic ID
`mednafen_vb-38e7a0ec9ac7-20575c76c389`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json \
  --release .local-e2e/releases/mednafen_vb-38e7a0ec9ac7-20575c76c389 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_vb
```

Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_vb.py`,
`pins/core-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json`,
`pins/source-sets/mednafen_vb-38e7a0ec9ac7-20575c76c389.json`,
`manifests/compatibility/mednafen_vb.json`,
`tests/cores/test_mednafen_vb.py`, and
`tests/test_contract_mednafen_vb.py`. Selected and reproduction evidence use
`actions-sim-build-core-mednafen_vb-v1` and
`build-core-mednafen_vb-local-v1`. The local release is
`.local-e2e/releases/mednafen_vb-38e7a0ec9ac7-20575c76c389`; its three aliases
are `.local-e2e/channels/nightly.mednafen_vb.json`,
`.local-e2e/channels/pinned.mednafen_vb.json`, and
`.local-e2e/channels/release.mednafen_vb.json`. Publication remains disabled,
and all device views remain ineligible pending target-runtime validation.

Mednafen Neo Geo Pocket uses semantic ID
`mednafen_ngp-a50d5ac288a8-d2dabb68d075`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json \
  --release .local-e2e/releases/mednafen_ngp-a50d5ac288a8-d2dabb68d075 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_ngp
```

Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_ngp.py`,
`pins/core-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json`,
`pins/source-sets/mednafen_ngp-a50d5ac288a8-d2dabb68d075.json`,
`manifests/compatibility/mednafen_ngp.json`,
`tests/cores/test_mednafen_ngp.py`, and
`tests/test_contract_mednafen_ngp.py`. Selected and reproduction evidence use
`actions-sim-build-core-mednafen_ngp-v1` and
`build-core-mednafen_ngp-local-v1`. The local release is
`.local-e2e/releases/mednafen_ngp-a50d5ac288a8-d2dabb68d075`; its three aliases
are `.local-e2e/channels/nightly.mednafen_ngp.json`,
`.local-e2e/channels/pinned.mednafen_ngp.json`, and
`.local-e2e/channels/release.mednafen_ngp.json`. Publication remains disabled,
and all device views remain ineligible pending target-runtime validation.

Mednafen Lynx uses semantic ID
`mednafen_lynx-fcdefcfb3c11-c2247f1f6de1`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json \
  --release .local-e2e/releases/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_lynx
```

Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_lynx.py`,
`pins/core-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json`,
`pins/source-sets/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json`,
`manifests/compatibility/mednafen_lynx.json`,
`tests/cores/test_mednafen_lynx.py`, and
`tests/test_contract_mednafen_lynx.py`. Selected and reproduction evidence use
`actions-sim-build-core-mednafen_lynx-v1` and
`build-core-mednafen_lynx-local-v1`. The local release is
`.local-e2e/releases/mednafen_lynx-fcdefcfb3c11-c2247f1f6de1`; its three aliases
are `.local-e2e/channels/nightly.mednafen_lynx.json`,
`.local-e2e/channels/pinned.mednafen_lynx.json`, and
`.local-e2e/channels/release.mednafen_lynx.json`. Publication remains disabled.
The required, unbundled `lynxboot.img` firmware, content, controls, rotation,
A/V, saves, states, compatibility, frontend integration, and performance remain
legal, policy, and target-runtime gates, so no device view is eligible.

Mednafen PCE Fast uses semantic ID
`mednafen_pce_fast-0bc6c8692834-8e747136926e`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json \
  --release .local-e2e/releases/mednafen_pce_fast-0bc6c8692834-8e747136926e \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_pce_fast
```

Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_pce_fast.py`,
`pins/core-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json`,
`pins/source-sets/mednafen_pce_fast-0bc6c8692834-8e747136926e.json`,
`manifests/compatibility/mednafen_pce_fast.json`,
`tests/cores/test_mednafen_pce_fast.py`, and
`tests/test_contract_mednafen_pce_fast.py`. Selected and reproduction evidence
use `actions-sim-build-core-mednafen_pce_fast-v1` and
`build-core-mednafen_pce_fast-local-v1`. The local release is
`.local-e2e/releases/mednafen_pce_fast-0bc6c8692834-8e747136926e`; its three
aliases are `.local-e2e/channels/nightly.mednafen_pce_fast.json`,
`.local-e2e/channels/pinned.mednafen_pce_fast.json`, and
`.local-e2e/channels/release.mednafen_pce_fast.json`. Publication remains
disabled. HuCard and BIOS-backed PCE-CD loading, the unbundled system-card BIOS,
controls, A/V, saves, states, compatibility boundaries, frontend integration,
and performance remain target-runtime gates, so no device view is eligible.

Mednafen WonderSwan uses semantic ID
`mednafen_wswan-da6d0d9acb8d-cc4a98ceff16`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_wswan-da6d0d9acb8d-cc4a98ceff16.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_wswan-da6d0d9acb8d-cc4a98ceff16.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_wswan-da6d0d9acb8d-cc4a98ceff16.json \
  --release .local-e2e/releases/mednafen_wswan-da6d0d9acb8d-cc4a98ceff16 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_wswan
```

Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_wswan.py`,
`manifests/compatibility/mednafen_wswan.json`,
`tests/cores/test_mednafen_wswan.py`, and
`tests/test_contract_mednafen_wswan.py`. Selected and reproduction evidence use
`actions-sim-build-core-mednafen_wswan-v1` and
`build-core-mednafen_wswan-local-v1`; local aliases are
`.local-e2e/channels/<channel>.mednafen_wswan.json`.

Mednafen PC-FX uses semantic ID
`mednafen_pcfx-650c30ea2203-5c0f9a256d9a`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/mednafen_pcfx-650c30ea2203-5c0f9a256d9a.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/mednafen_pcfx-650c30ea2203-5c0f9a256d9a.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/mednafen_pcfx-650c30ea2203-5c0f9a256d9a.json \
  --release .local-e2e/releases/mednafen_pcfx-650c30ea2203-5c0f9a256d9a \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core mednafen_pcfx
```

Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_pcfx.py`,
`manifests/compatibility/mednafen_pcfx.json`,
`tests/cores/test_mednafen_pcfx.py`, and
`tests/test_contract_mednafen_pcfx.py`. Selected and reproduction evidence use
`actions-sim-build-core-mednafen_pcfx-v1` and
`build-core-mednafen_pcfx-local-v1`; local aliases are
`.local-e2e/channels/<channel>.mednafen_pcfx.json`. This is static build
evidence only: every device view remains ineligible pending target runtime and
provider validation. Operators must also supply the unbundled `pcfx.rom` BIOS
and review the metadata display version `v0.9.33.3` versus compiled version
`v0.9.36.5 650c30e` before any publication decision.

PokéMini uses semantic ID `pokemini-bb009b1379ad-2f63e84b7b68`:

```bash
python3 scripts/core_pipeline.py validate-pin-set \
  --pin-set pins/core-sets/pokemini-bb009b1379ad-2f63e84b7b68.json \
  --verify-store --verify-sources
python3 scripts/profile_registry.py report \
  --source-set pins/source-sets/pokemini-bb009b1379ad-2f63e84b7b68.json
python3 scripts/core_pipeline.py validate-release \
  --pin-set pins/core-sets/pokemini-bb009b1379ad-2f63e84b7b68.json \
  --release .local-e2e/releases/pokemini-bb009b1379ad-2f63e84b7b68 \
  --verify-store
python3 scripts/core_pipeline.py validate-channel \
  --channel pinned --core pokemini
```

Its canonical owners are `scripts/core_pipeline_lib/contracts/pokemini.py`,
`pins/core-sets/pokemini-bb009b1379ad-2f63e84b7b68.json`,
`pins/source-sets/pokemini-bb009b1379ad-2f63e84b7b68.json`,
`manifests/compatibility/pokemini.json`, `tests/cores/test_pokemini.py`, and
`tests/test_contract_pokemini.py`. Selected and reproduction evidence use
`actions-sim-build-core-pokemini-v1` and `build-core-pokemini-local-v1`; local
aliases are `.local-e2e/channels/<channel>.pokemini.json`. This is local static
build evidence gathered through network source clones, not an offline or target
runtime result. The optional, unbundled `bios.min` and the unresolved `.eep`
path overflow warning remain runtime-review gates; every device view is
ineligible pending provider inspection and target validation.

Cap32 uses semantic ID `cap32-4abfb8be233b-afbc043051e8`. Its canonical
owners are `scripts/core_pipeline_lib/contracts/cap32.py`, the matching
one-core pin and source set, `manifests/compatibility/cap32.json`,
`tests/cores/test_cap32.py`, and `tests/test_contract_cap32.py`. Selected
`actions-sim-build-core-cap32-v2` and reproduction
`build-core-cap32-local-v2` builds reproduce the package, metadata, and both
ABI artifacts byte for byte; parallel log order varies while the complete
line multisets and exact 44-command proof remain equal. Metadata/runtime
version drift, non-commercial compiled-source terms, network-only checkout,
cached-image provenance, and all target runtime behavior remain explicit
gates. The three `.local-e2e/channels/<channel>.cap32.json` aliases are local
only, and every device view remains ineligible.

CrocoDS uses semantic ID `crocods-87bbb3d9007a-7b4aa1fce1f1`. Its canonical
owners are `scripts/core_pipeline_lib/contracts/crocods.py`, the matching
one-core pin and source set, `manifests/compatibility/crocods.json`,
`tests/cores/test_crocods.py`, and `tests/test_contract_crocods.py`. Selected
`actions-sim-build-core-crocods-v1` and reproduction
`build-core-crocods-local-v1` builds reproduce the package, metadata, and both
ABI artifacts byte for byte. ARMHF logs are byte-identical; parallel ARM64
logs have equal complete-line multisets and independently pass the exact
50-command C proof with nine reviewed warnings and seven notes. Metadata and
compiled-license differences, embedded CPC data without local provenance,
network-only checkout, cached-image provenance, provider availability, and
all target-runtime behavior remain explicit human or device gates. The three
`.local-e2e/channels/<channel>.crocods.json` aliases are local only, and every
device view remains ineligible.

Genesis Plus GX uses semantic ID
`genesis_plus_gx-fa4dca561e08-0e5a55ff8180`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/genesis_plus_gx.py`, the matching
one-core pin and source set, `manifests/compatibility/genesis_plus_gx.json`,
`tests/cores/test_genesis_plus_gx.py`, and
`tests/test_contract_genesis_plus_gx.py`. Selected
`actions-sim-build-core-genesis_plus_gx-v1` and reproduction
`build-core-genesis_plus_gx-local-v1` builds reproduce the package, metadata,
and both ABI artifacts byte for byte. ARMHF logs are byte-identical; parallel
ARM64 logs have equal complete-line multisets and independently pass the exact
117-command C proof with two reviewed warnings and one note. Network-only
checkout, cached-image provenance, imported-binary version drift, core-option
and BRAM migration, content and runtime behavior, cross-variant state
compatibility, and non-commercial corresponding-source obligations remain
explicit gates. The three
`.local-e2e/channels/<channel>.genesis_plus_gx.json` aliases are local only,
and every device view remains ineligible.

The Base and Wide proofs exact-match their ordered fetch/build preludes but
canonicalize only the matching positive `-jN` token on the reviewed clean and
build commands. Container-visible CPU capacity is scheduler input, not core
recipe identity; the two job counts must still match, and every surrounding
command byte and phase boundary remains exact.

Genesis Plus GX Wide independently owns semantic lifecycle
`genesis_plus_gx_wide-29d9d104338f-7907e7e03389`, its one-core pin and source
set, `manifests/compatibility/genesis_plus_gx_wide.json`,
`tests/cores/test_genesis_plus_gx_wide.py`, and
`tests/test_contract_genesis_plus_gx_wide.py`. Fresh selected
`actions-sim-build-core-genesis_plus_gx_wide-v1` and reproduction
`build-core-genesis_plus_gx_wide-local-v1` runs reproduce package
`df36ba0750a558a846dc82012d8fe4c33dbd1e97c60d2e88d4ee42ed5efb6eec`,
metadata, both ABI artifacts, and both logs byte for byte while independently
passing its exact 106-command C proof. The three
`.local-e2e/channels/<channel>.genesis_plus_gx_wide.json` aliases are local
only. Provider and target-runtime behavior, Wide option and state migration,
Base/Wide compatibility, non-commercial corresponding-source obligations,
and every device view remain fail-closed gates. The tracked historical Wide
logs remain immutable test oracles and were not used for promotion.

O2EM's corresponding semantic lifecycle is
`o2em-e03d3be88f79-ede84c3862de`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/o2em.py`,
`manifests/compatibility/o2em.json`, `tests/cores/test_o2em.py`, and
`tests/test_contract_o2em.py`; selected and reproduction evidence use
`actions-sim-build-core-o2em-v1` and `build-core-o2em-local-v1`. The local
nightly, pinned, and release aliases are `.local-e2e/channels/<channel>.o2em.json`.

FreeChaF's corresponding semantic lifecycle is
`freechaf-76c7a84f1f7e-0fced3806666`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/freechaf.py`,
`manifests/compatibility/freechaf.json`, `tests/cores/test_freechaf.py`, and
`tests/test_contract_freechaf.py`; selected and reproduction evidence use
`actions-sim-build-core-freechaf-v1` and `build-core-freechaf-local-v1`. The
local aliases are `.local-e2e/channels/<channel>.freechaf.json`.

VecX's corresponding semantic lifecycle is
`vecx-8f671cc9d737-4686ef94bf56`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/vecx.py`,
`manifests/compatibility/vecx.json`, `tests/cores/test_vecx.py`, and
`tests/test_contract_vecx.py`; selected and reproduction evidence use
`actions-sim-build-core-vecx-v2` and `build-core-vecx-local-v1`. The local
aliases are `.local-e2e/channels/<channel>.vecx.json`.

LowRes NX's corresponding semantic lifecycle is
`lowresnx-35adc1a215e9-837092a5ffca`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/lowresnx.py`,
`manifests/compatibility/lowresnx.json`, `tests/cores/test_lowresnx.py`, and
`tests/test_contract_lowresnx.py`; selected and reproduction evidence use
`actions-sim-build-core-lowresnx-v1` and `build-core-lowresnx-local-v1`. The
local aliases are `.local-e2e/channels/<channel>.lowresnx.json`. The records
remain static-build-only: ARM64 reaches `GLIBC_2.29`, provider compatibility
is unverified, and every device view remains ineligible pending target-runtime
evidence.

RACE's corresponding semantic lifecycle is
`race-c7810dd7f172-c3119de987bf`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/race.py`,
`manifests/compatibility/race.json`, `tests/cores/test_race.py`, and
`tests/test_contract_race.py`; selected and reproduction evidence use
`actions-sim-build-core-race-v1` and `build-core-race-local-v1`. The local
aliases are `.local-e2e/channels/<channel>.race.json`. Package, metadata,
artifacts, and logs reproduce byte for byte, but publication remains disabled:
GPLv2 redistribution review and all provider, runtime, and device validation
remain human gates, including ARMHF's `GLIBC_2.7` floor.

Mednafen SuperGrafx's semantic lifecycle is
`mednafen_supergrafx-3c6fcd3deded-6f92f2753900`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/mednafen_supergrafx.py`,
`pins/core-sets/mednafen_supergrafx-3c6fcd3deded-6f92f2753900.json`,
`pins/source-sets/mednafen_supergrafx-3c6fcd3deded-6f92f2753900.json`,
`manifests/compatibility/mednafen_supergrafx.json`,
`tests/cores/test_mednafen_supergrafx.py`, and
`tests/test_contract_mednafen_supergrafx.py`. Selected
`actions-sim-build-core-mednafen_supergrafx-v1` and independent
`build-core-mednafen_supergrafx-local-v1` runs reproduce the package, metadata,
and both ABI artifacts byte for byte; parallel logs differ while both satisfy
the exact occurrence-aware proof. The local release is
`.local-e2e/releases/mednafen_supergrafx-3c6fcd3deded-6f92f2753900`; its three
`.local-e2e/channels/<channel>.mednafen_supergrafx.json` aliases remain
publication-disabled. GPLv2 review, the optional PCE-CD BIOS candidates (none
packaged), display version `1.23.0` versus binary version `1.29.0`, ARMHF's
preserved free-nonheap warning risk, and SGX/CD/CHD, provider, runtime, and
device validation remain open, so every device view is ineligible.

Potator's semantic lifecycle is `potator-227c5f6f3ce7-1617e2249087`. Its
canonical owners are `scripts/core_pipeline_lib/contracts/potator.py`,
`pins/core-sets/potator-227c5f6f3ce7-1617e2249087.json`,
`pins/source-sets/potator-227c5f6f3ce7-1617e2249087.json`,
`manifests/compatibility/potator.json`,
`tests/cores/test_potator.py`, and `tests/test_contract_potator.py`. Selected
`actions-sim-build-core-potator-v1` and independent
`build-core-potator-local-v1` runs reproduce the package, metadata, both ABI
artifacts, and both logs byte for byte. Resolver metadata declares
`Public Domain`, no firmware is packaged or required, and all four reviewed
misleading-indentation CPU warning/note pairs remain visible. The local release
is `.local-e2e/releases/potator-227c5f6f3ce7-1617e2249087`; its three
`.local-e2e/channels/<channel>.potator.json` aliases are publication-disabled;
runtime and device validation remain open, so every device view is ineligible.

Gearboy's semantic lifecycle is `gearboy-36d723ff4410-f6f1b63e8798`, and
Gearsystem's is `gearsystem-4f029e43f2d5-35212fbb9d9a`. Their canonical owners
are the matching files under `scripts/core_pipeline_lib/contracts/`,
`pins/core-sets/`, `pins/source-sets/`, `manifests/compatibility/`,
`tests/cores/`, and `tests/test_contract_*.py`. Selected
`actions-sim-build-core-gearboy-v1` and
`actions-sim-build-core-gearsystem-v1` runs reproduce their independent
`build-core-*-local-v1` package, metadata, both ABI artifacts, and both logs
byte for byte. Their local releases and three per-core channel aliases remain
publication-disabled. GPLv3 review, optional firmware handling, stale metadata
display versions, provider compatibility, target-runtime behavior, and every
device claim remain open; ARMHF's `GLIBCXX_3.4.32` requirement leaves the Mini
profile ineligible.

2048's corresponding semantic lifecycle is
`2048-c90437d3c391-86ed146bc647`. Its canonical owners are
`scripts/core_pipeline_lib/contracts/core_2048.py`,
`manifests/compatibility/2048.json`, `tests/cores/test_2048.py`, and
`tests/test_contract_2048.py`; selected and reproduction evidence use
`actions-sim-build-core-2048-v2` and `build-core-2048-local-v1`. The local
aliases are `.local-e2e/channels/<channel>.2048.json`. Both artifacts are
portable build-identity records only; the source is eight commits newer than
the shipped baseline, its SaveRAM metadata disagrees with the exposed memory
API, and every device view remains ineligible pending target-runtime evidence.

EightyOne's semantic lifecycle is `81-fa7094910d04-a82f6eb4a7cc`. Its selected
`actions-sim-build-core-81-v2` and independent
`build-core-81-local-v1` runs reproduce the package, metadata, and both ABI
artifacts byte for byte. Parallel warning/note ordering makes the raw logs
byte-different, but both independently satisfy the exact per-owner diagnostic
NFA. Its 16-C/12-C++ contract preserves upstream's native `src/version.c`
generation and never injects `GIT_VERSION`. The canonical record remains
static-build-only: ABI drift, the copied metadata's unescaped inner quotes,
compiled ROM licensing, provider compatibility, and all target-runtime/device
claims remain explicit gates.

Use `tests/cores/test_<core>.py` for core-owned contract tests. Device buildsets
may reference the same portable core record; they do not create another pin
unless captured ABI or build-flavor evidence requires different artifacts.

## Legacy aggregate history (read-only)

The former aggregate composition, release, channel, hash, and migration
chronology — including the tranche fixtures and their regression readers —
was retired from the working tree on 2026-07-23 and is preserved in git
history (last present at commit `dd82cc4`). It was immutable audit context,
not active operator guidance.

Each top-level `manifests/compatibility/*.json` file and its matching
one-core pin, source set, and focused test is a current individual-core
record. Temporary transition records live only below
`manifests/compatibility/pending/` and make no compatibility claim. All
current validation remains local-only; nothing is published.

The store and run directories are intentionally ignored and local-only. Exact
paths in the legacy compatibility matrix and canonical per-core records
therefore identify workspace-local evidence, not files available from a fresh
clone. Preserve them with the workspace: a fresh clone can read the pin
metadata but cannot
recover these source-built bytes. The cached image archive bytes and IDs are now
portable and immutable through the toolchain lock, while the current Dockerfiles
remain explicitly unverified descriptions of those older caches.

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

## Usage

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
without rebuilding it. Release-plan schema v2 binds the coordinator and worker
identities, while its target model and the v1 result/candidate schemas remain
architecture-keyed and static-build-only. A second execution profile for the
same architecture needs a later execution-profile-keyed schema revision and
cannot be represented by duplicating an architecture target.

## TODO: cores not yet buildable

These cores are shipped by spruceOS but can't be built from libretro-super and need custom build processes:

- [ ] **mkxp-z** — hyphen in name breaks libretro-super's bash variable parsing
- [ ] **mupen64plus** — removed from libretro-super (replaced by mupen64plus_next)
- [ ] **km_flycast_xtreme** — KMFDManic/morpheuscast_xtreme fork uses bare `as` for ARM64 assembly, not cross-compile friendly
- [ ] **km_ludicrousn64_2k22_xtreme_amped** — KMFDManic fork has broken aarch64 dynarec source and missing includes
