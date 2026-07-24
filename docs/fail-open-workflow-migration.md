# Fail-open workflow migration — runbook

Status as of 2026-07-23: **canonical 92, unmigrated 6** (audit:
`masked_build_failure_paths: 12`, `info_only_risk_workflows: 4`,
`unmigrated_workflow_count: 6`), with the whole catalog re-promoted onto the
v2 toolchain images (commits `9d95cda` + `dd82cc4`, full suite green). The
remaining six, with their blocking condition:

- **flycast** — GL/3D, the only genuinely GPU-required core (no software
  rasterizer); direct-cmake onboarding next, device eligibility gated on a
  GLES provider (Mini family exclusion already evidence-established).
- **yabasanshiro** — shipped as three device-tuned vendor variants; probe
  whether one generic-GLES build can replace all three before onboarding.
- **easyrpg** — v2 images carry CMake 3.31.6, but the player still needs
  SDL/liblcf/fluidsynth dependencies staged; try
  `-DPLAYER_TARGET_PLATFORM=libretro -DPLAYER_BUILD_LIBLCF=ON`.
- **squirreljme** — was blocked on running a cross-built tool at configure
  time; the v2 images now include qemu-user + `QEMU_LD_PREFIX`, so this is
  an exploratory retry, not a blocker.
- **libgametank** — Rust; cargo/zig lives in the separate `cores-rust`
  image (the locked toolchain archive's 2 GiB member cap refused bundling
  it), so this needs a `cargo` driver + Cargo.lock-shaped proof model.
- **km_parallel_n64_xtreme_amped_turbo** — fork broken upstream at the
  pinned HEAD (GLdouble under GLES2); bisect for a building commit or
  replace with upstream's armhf build.

Historical goal statement (2026-07-21): retire the 44 uncataloged, fail-open
core CI workflows by onboarding each core into the fail-closed, hash-locked
catalog and replacing its workflow with the shared read-only pipeline
dispatcher. After the six legacy bridges were retired (canonical 54, legacy
bridge 0), these 44 were the remaining `unmigrated_workflows` reported by
`scripts/core_pipeline.py audit-workflows`.

## What "fail-open" means here

A current workflow such as `.github/workflows/build-ardens.yml` is fail-open:

- `permissions: contents: write` (can mint/overwrite releases),
- a free-form `core_ref` input (builds an arbitrary, unpinned ref),
- `gh release create … || true` and other `|| echo` masks (a failed build
  still "passes"),
- `./libretro-fetch.sh <core>` + `./libretro-build.sh <core>` against **latest**
  upstream (no pinned commit/tree, no reproducibility).

At kickoff the audit reported `masked_build_failure_paths: 88`,
`info_only_risk_workflows: 40`, `unmigrated_workflow_count: 44`.

The migrated target is the shared dispatcher already used by all 54 canonical
cores (see `build-ecwolf.yml`): `permissions: contents: read`, pinned
`actions/checkout`, `scripts/toolchain_archive.py verify-downloads`,
`--runner-profile github-actions --core <core>`, and **no** `core_ref`, `gh
release create/upload`, or `|| echo`.

## Per-core onboarding recipe (each is ONE atomic unit)

A core cannot be half-onboarded: the moment it is in `manifests/core-builds.json`
it must also be covered (canonical/bridge/pending) or `audit-workflows` /
compatibility coverage fails the suite. Complete every step before committing.

1. **Pin the source.** `git ls-remote <url> HEAD` → commit; shallow-fetch that
   commit and `git rev-parse <commit>^{tree}` → tree. (Confirmed working from
   this environment.)
2. **Catalog entry** in `manifests/core-builds.json` — driver
   (`libretro-super` / `direct-make` / `direct-cmake`), `source_dir`,
   `output_path`, `artifact_name`, plus any `git_version`, `compile_definitions`,
   `make_variables`, `overlays` the build actually uses.
3. **Per-core schema `$def`** in `manifests/core-builds.schema.json`
   (`#/$defs/<core>Core`, ~1.7 KB exact shape) + the `properties.cores` ref.
   The catalog schema is `additionalProperties: false`; there is no generic
   core shape.
4. **Source lock** `pins/sources/<core>/<commit>.json`
   (`promote_core.py compose-source-lock`).
5. **Exploratory sim build** → classify the compile set (C-only / mixed /
   C+asm) and extract the sha256 constants (scratchpad `extract_conly` /
   `extract_mixed` / `extract_casm`).
6. **Contract/proof** — reuse a shared standard (`c_only`, `mixed_language`,
   `c_asm`) or the generic `direct_cmake` / make-variable proofs; register it
   (`registry.py` + `core_pipeline.py` import / spec-dispatch / proof map) and
   bump `tests/test_core_contract_registry.py`. Direct-cmake and make-variable
   cores need **no** per-core contract.
7. **Golden schema branches** where the build type needs them (git_version,
   make_variables — see the fbneo golden-start/core-golden branches).
8. **Build sim + local** (no pipeline edits between the two) → verify the
   package sha matches → `import-golden` → `promote` (per arch) →
   `derive-core-id` → `compose-core-golden` → `compose-pin-set` →
   `promote_core.py compose-lifecycle`.
9. **Replace the workflow** with the shared dispatcher; delete the fail-open
   release/`core_ref`/masking steps.
10. **Tests** (`tests/cores/test_<core>.py`) + `MINI_OVER_CEILING` if the armhf
    C++ build needs `GLIBCXX > 3.4.24`; run the full suite; checkpoint-commit.

Reproducibility gotchas already solved and reusable: CMake `[NN%]` progress
counters (`_reproduction_comparable_log_multiset`) and parallel-make stderr
interleave (`make --output-sync=recurse`, profile-scoped).

## Re-evaluation of the remaining 31 (2026-07-21, evidence-based)

Data per core is authoritative from the `libretro-fetch` rule (URL + submodule
flag) and the fail-open workflow (driver + output path + GL markers). "Matches"
names an already-canonical core with the same proof shape; language/asm/
date-embed still need the step-5 exploratory build to confirm.

**Tier 1 — Low (clean libretro-super, no submodules; the fuse/gme recipe as-is):**
| core | repo | matches | expected proof |
|---|---|---|---|
| theodore | `Zlika/theodore` | fuse/gw | c_only |
| bk | `libretro/bk-emulator` | fuse | c_only |
| numero | `nbarkhina/numero` | gme | c_only/mixed |
| chimerasnes | `jamsilva/chimerasnes` | **snes9x2002** | c_only |
| opera | `libretro/opera-libretro` | quasi88 | mixed (mostly C) |
| fbalpha2012 | `libretro/fbalpha2012` | **fbneo** | mixed — large set |

**Tier 2 — Medium (one known wrinkle — see note):**
| core | repo | wrinkle | matches |
|---|---|---|---|
| px68k | `libretro/px68k-libretro` | may embed date → epoch | quasi88 |
| x1 | `libretro/xmil-libretro` | JP retro computer | quasi88 |
| np2kai | `libretro/NP2kai` | PC-98, mixed | quasi88 |
| puae2021 | `libretro/libretro-uae` | Amiga | quasi88 |
| uae4arm | `libretro/uae4arm-libretro` | may carry ARM asm → **c_asm** | pcsx_rearmed/gpsp |
| daphne | `libretro/daphne` | laserdisc, mixed | gme |
| arduous | `libretro/arduous` | **submodules** (gitlink pin) | frodo |
| ardens (RESOLVED) | `tiberiusbrown/Ardens` | direct-cmake + ARDENS_* defines skip SDL/GL desktop | — |
| puzzlescript | `nwhitehead/pzretro` | **submodules** | gme |

**Tier 3 — High (large upstream and/or many submodules):**
`chailove` (**RESOLVED**, canonical — see below), `dosbox_pure`
(**RESOLVED**, canonical — see below), `easyrpg` (`EasyRPG/Player`,
upstream + liblcf/deps), `tic80` (`libretro/TIC-80`, many language runtimes as
subs), `uw8` (`libretro/uw8-libretro`, subs + a WASM runtime — may be partly
exotic). Proof engine still `mixed_language`, but each is a multi-day-shaped
unit and several will need `source_date_epoch` and submodule pinning.

**Tier 4 — Exotic / blocked (new machinery, new driver, GL/3D, or a blocker):**
| core | why exotic |
|---|---|
| flycast | **BLOCKED on image**: needs CMake >= 3.22.1, image has 3.16.3 (same class as easyrpg). Device evidence already recorded: it links `libGLESv2.so.2`, which the **Mini Plus does not have**, so that device could never run it regardless. |
| mupen64plus_next | **RESOLVED** (canonical, arm64-only) — reused the parallel_n64 make-variable pattern; needed `build.submodules: false` for a stray gitlink |
| parallel_n64 | **RESOLVED** (canonical, arm64-only) — see below |
| yabasanshiro | Saturn GL, large — GL/3D |
| libgametank | **Rust/cargo-zigbuild** — blocked on image (no cargo/rustc/zig); new `cargo` driver + Cargo.lock proof (see (c)) |
| squirreljme | **BLOCKED on image**: C `nanocoat` CMake core, shipped armhf-only; configure executes a cross-built host tool (needs qemu-arm + armhf loader). Also an upstream ARM32 `elseif` bug (1-token overlay). |
| fake08 | **RESOLVED** (canonical): direct-make + `make_subdir`/`make_args`/`cxx_compiler_compiles_c` (see (c)) |
| sameduck | **RESOLVED** (canonical): NOT silent — c_only with `sha_pinned_object_names` for `_libretro.c.o` naming |
| lutro | **RESOLVED** (canonical): c_only archive-membership mode + `("obj/player/","")` alias |
| km_duckswanstation_xtreme_amped | **RESOLVED** (canonical, armhf-only) — no new driver needed; see below |
| km_parallel_n64_xtreme_amped_turbo | **BLOCKED upstream at HEAD** (investigated 2026-07-22, reverted cleanly): direct-make fits (`platform=unix ARCH=arm WITH_DYNAREC=arm FORCE_GLES=1`, armhf-only, repo-pinned metadata ready in `metadata/`), but commit `be8d13e6` fails to compile — its bundled libretro-common `glsm/glsmsym.h` uses `GLdouble`/`rglClearDepth` under GLES2 (`-DHAVE_OPENGLES2` confirmed present on the failing argv), which GLES2 headers do not define for the C++ `gles2rice` files. The shipped artifact predates this breakage. Next: bisect for the last building commit, or overlay-patch the glsm header. |

Recommended order: Tier 1 → Tier 2 (submodule cores after a gitlink-pin helper
is confirmed) → decide Tier 3/4 policy (GL cores likely `default_selection:
excluded` / software-diagnostic like ffmpeg; km_* likely excluded outright;
Rust/Java need new build drivers). Do each as a self-contained, individually
committed unit; never add a core to the catalog while a suite is running.

## Lessons from snes9x2010 (the reference implementation)

The first onboarding (canonical 54 → 55, unmigrated 44 → 43) settled several
things that make the remaining 43 faster:

- **No per-core schema `$def` is needed** for a plain or `git_version`
  libretro-super core. `properties.cores.additionalProperties` falls back to
  `#/$defs/nonNativeCore`, which already permits `git_version` and forbids only
  `recipe_profile`. Only the 32 legacy "special" cores carry an explicit `$def`;
  new plain cores just get a catalog entry (schema validates automatically —
  `catalog-check` then reports only the coverage gap, not a schema error).
- **Replace the workflow *before* the sim/local builds.** The build record's
  recipe identity includes `workflow_sha256`; changing the workflow after the
  build makes `promote` fail with `recipe identity mismatch: workflow_sha256`.
  Order: catalog + source lock + contract + **workflow swap**, then build.
- **Compute the sha256 constants with the real `c_only`/`mixed_language`
  functions, not the scratchpad `extract_*` helpers** — `extract_conly` produced
  a wrong armhf invocation sha256 (the arm64 value was correct). Parse the log
  with `c_only_compile_invocation` + `c_only_compile_invocation_sha256` per arch.
- An embedded, commit-derived `GIT_VERSION` token needs **no** catalog
  `git_version` field and no extra guard: the per-arch invocation sha256 pins the
  exact token, and the pinned `source_commit` ties it to the commit.
- The spruceOS baseline may ship **only one arch** (`not_shipped` for the other,
  as `arm64` was for snes9x2010); `promote` still binds both arches from the
  reproducible build.

## Blockers found while executing (unblock before resuming)

**0. Process note (self-inflicted, avoid):** never add a core to the catalog
while a full-suite run is in flight — the suite reads the working-tree catalog
and reports the new, still-uncovered core as ~29 coverage/audit/roster failures.
Finish and commit one core (or revert it) before starting the next core's
exploratory build if a suite is running.

**3. Some libretro-super cores build silently via CMake.** `sameduck` (a
SameBoy fork) is driven by `libretro-build.sh` but compiles through CMake with
**no compile commands in the log** (0 gcc `-c` lines, 0 CMake progress lines);
the objects only appear in the final link (`..//build/obj/Core/gb_libretro.c.o`,
i.e. `<source>.c.o` names in a build tree separate from the sources). The
argv-based `c_only`/`mixed`/`c_asm` proofs have nothing to verify. Proving it
needs either a VERBOSE build to surface the compile commands (recipe change,
unclear if `libretro-build.sh` allows it) or a direct-cmake-style
marker/config proof for a libretro-super core — a design decision. It also
embeds a build date, so it will need `source_date_epoch` regardless.


1. **Source URLs are not uniformly `libretro/<core>` — RESOLVED authoritatively
   (2026-07-21).** The fail-open workflows run `./libretro-fetch.sh <core>`
   inside the toolchain Docker image (`cores-arm64`), which clones
   `libretro/libretro-super` at `/libretro-super`. That script resolves the URL
   from `libretro_<source_key>_git_url` in `/libretro-super/rules.d/core-rules.sh`
   (the `.d` files, not the naming patterns). This is the authority; read it with
   `docker run --rm cores-arm64 bash -lc 'grep libretro_<key>_git_ /libretro-super/rules.d/*.sh'`.

   **Full audit result:** every one of the 65 cataloged libretro-super cores'
   `source.url` matches its `libretro-fetch` rule *exactly* (including the
   `REminiscence`/`Mu` casings and the two non-libretro-super cores gpsp/
   swanstation). `compose-source-lock` records active submodule gitlinks in
   `source.submodules` (freechaf/ecwolf populated; gw/neocd/picodrive have a
   `.gitmodules` but zero active gitlinks at the pinned commit → correctly `[]`).
   Nothing in the current catalog is mis-sourced.

   **The previously-"unresolved" cores, resolved from the rules** — most live in
   *upstream author* repos, which is why the three libretro/* patterns missed
   them (verify each commit/tree + submodules before pinning):
   - theodore → `Zlika/theodore` (master)
   - numero → `nbarkhina/numero` (master)
   - chimerasnes → `jamsilva/chimerasnes` (master)
   - bk → `libretro/bk-emulator` (master) — repo is `bk-emulator`
   - puzzlescript → `nwhitehead/pzretro` (main, **submodules=yes**)
   - uw8 → `libretro/uw8-libretro` (main, **submodules=yes**)
   - squirreljme → `XerTheSquirrel/SquirrelJME` (trunk) — Java project, exotic
   - ardens → `tiberiusbrown/Ardens` (master, **submodules=yes**)

   **Two are NOT libretro-super** (their workflow does a direct `git clone`, not
   `libretro-fetch`, and a non-`dist/unix` build path — treat as separate
   drivers): fake08 → `jtothebell/fake-08` (submodules, builds
   `platform/libretro/`); libgametank → `dwbrite/gametank-sdk` (**Rust/cargo**,
   builds `target/<triple>/release/`).
2. **`c_only` (and the mirrored `c_asm`) compile parser does not handle forced
   includes.** `c_only_compile_invocation` only treats `-I` as a flag with a
   file operand; a compile using `-include <file>` (or `-isystem`/`-iquote`/
   `-imacros`/`-idirafter`) has its operand mistaken for a second source, so the
   invocation is rejected and the whole proof fails. **tyrquake** hit this (its
   bundled libvorbis compiles with `-include deps/libvorbis/lib/fvorbis_rename.h`
   for symbol renaming). Fix: add those flags to the option-operand set in
   `c_only_compile_invocation` (mirroring `-I`) and the same block in
   `c_asm_compile_invocation`; byte-inert for cores that don't use them, so
   verify with the full suite. This unblocks tyrquake and any bundled-dep core.

**4. Some cores link the shared object into a build subdirectory.** `lutro`
compiles cleanly (113 C `-c` lines, no CMake, no assembly, gcc link driver) and
is reproducible, but its Makefile emits the artifact into `obj/player/`:
`-o obj/player/lutro_libretro.so`, with every link operand under
`obj/player/./...`. Both shared link proofs (`c_only_link_command`,
`mixed_language_link_command`) reject this: after `output = semantic_log_path(
raw_output, ".so", aliases)` they additionally require
`raw_output.removeprefix("./") == output` (c_only) / `raw_output == output`
(mixed) — an anti-path-escape guard that forbids *any* directory component in
the artifact output, so no `semantic_path_aliases` entry can rescue it.
`lutro`'s `-DGIT_VERSION=" 1df938b"` is commit-derived and reproducible (a
`git_version` spec like ProSystem), so it is **not** the blocker.
**Recommended fix (needs approval — shared, security-adjacent machinery used by
all 60 cores):** relax the artifact-output guard to accept a contained
subdirectory *only when an explicit `semantic_path_aliases` entry maps it to the
bare artifact name*. `semantic_log_path` already returns `None` on `..` escape,
so containment is preserved; the change is purely additive (cores with a
root-level output configure no such alias and behave identically). This would
unblock `lutro` and any other `obj/<platform>/`-linking libretro-super core.
`lutro` is now onboarded (c_only archive-membership mode; see blocker #6).

**5. Some cores build with absolute object paths.** `chimerasnes` (a snes9x
fork) compiles cleanly (50 C `-c` lines, no C++, no CMake) and is C-only, but
its Makefile emits objects to an **absolute** `OBJDIR`:
`-c -o/libretro-super/libretro-chimerasnes/source/apu.o /libretro-super/libretro-chimerasnes/source/apu.c`
(both the `-o` output and the source are absolute, on both ABIs).
`semantic_log_path` hard-rejects any value that `startswith("/")` **before** the
alias substitution runs, so — unlike a `../` traversal — no
`semantic_path_aliases` entry can normalize it. The path is deterministic (same
container build root `/libretro-super/libretro-<core>/` in sim and local), so the
argv is stable; only the proof engine can't consume it. **Recommended fix (same
approval-gated, shared-machinery class as #4):** apply a configured absolute
build-root alias *before* the `startswith("/")` guard — e.g. map
`/libretro-super/libretro-chimerasnes/source/` → `source/` — so a reviewed,
core-specific prefix is contained while every other absolute path stays rejected.
`semantic_log_path`'s existing dot-component check then guarantees no `..` escape.
This unblocks `chimerasnes` and any `$(CURDIR)`/absolute-`OBJDIR` core. Until
approved, `chimerasnes` is deferred (cleanly reverted, no catalog trace).

**#4 and #5 are RESOLVED (2026-07-21, approved + committed cd5356c/7b9f667).**
`semantic_log_path` applies the reviewed alias before the leading-`/` guard, and
the link-output guard relies on it for containment; the compile guards also admit
an inert attached `-Wl,...` token (chimerasnes ships `-Wl,--gc-sections`). A
differential test proved 0 behaviour change across all catalog aliases, and the
full suite (all 73 cores) stays green. **chimerasnes onboarded** (absolute
OBJDIR). The #4 subdir-output relaxation is implemented and containment-tested;
no canonical core uses it yet (see #6).

**6. Some cores build objects into an intermediate static archive** (RESOLVED).
`lutro` is C-only and (with #4's `("obj/player/","")` alias, which also handles
the subdir output) normalizes fine, **but** its Makefile compiles the bundled
Lua interpreter (29 `.o`) and `ar rcu deps/lua/src/liblua.a <objects>`, then
links the `.a` — so the final link references `deps/lua/src/liblua.a` instead of
those 29 objects (113 compiled vs 84 linked + one `.a`), violating the shared
`link_objects == compile_objects` invariant. Resolved by an **opt-in
archive-membership mode** on the c_only engine (gated on
`expected_archive_member_sha256`, zero behaviour change when unset): a strict
`c_only_archive_command` parses each `ar <flags> <archive>.a <member>.o …` line
(dropping the trailing `# comment` before the control-char gate), and the proof
switches its object check to `link_direct_objects ∪ archive_members ==
compile_objects` while additionally pinning the exact 29-member Lua set and the
archive name. `lutro` onboarded as a 2-ABI `c_only-archive` core (reproducible,
no libstdc++). The single alias `("obj/player/","")` covers #4's subdir output
and the object prefix at once, so #4 now has a live consumer too.

## Status

**Onboarded and committed (25):** snes9x2010, snes9x2002, tyrquake, prboom, fuse,
gme, frodo, quasi88, retro8, reminiscence, gw, mu, hatari, theodore, bk, numero,
opera, fbalpha2012, **chimerasnes** (#5 resolved), **px68k, x1, daphne** (plus
the 3 pre-session), then **arduous** (direct-cmake), **uae4arm** (armhf-only),
**puae2021** (2.6.1 branch pin, c_only), **lutro** (c_only archive-membership,
#4+#6 resolved), **np2kai** (mixed, `../` subdir build, GCC-verbose-link temp-file
reproduction normalization), **sameduck** (c_only, opt-in `sha_pinned_object_names`
relaxation for non-standard object naming), **puzzlescript** (mixed, opt-in
`build.recursive_submodules: false` for the nested quickjs-ng/test262 submodule),
**fake08** (non-super direct-make + `make_subdir`/`make_args`/`cxx_compiler_compiles_c`).
**uw8** (c_only, embeds wasm3), **tic80** (direct-cmake via new `cmake.source_subdir` + `cmake.defines` extension; CPU-rendered, no GL). **ardens** (direct-cmake; its ARDENS_* defines skip the SDL/GL desktop build).
**chailove** (c_asm, 71 C / 30 C++ / 1 NEON `.S`; needed a `build.overlays`
echo-unsilencing patch and a `mixed_language` option-operand parity fix — see
below), **dosbox_pure** (mixed, all-C++; the same overlay technique plus two
`~`-name guard relaxations), **parallel_n64** (c_asm, arm64-only, the first
GL-linking core). Catalog at **90 canonical, 8 unmigrated**. Tier 1 done;
Tier 2 done; Tier 3 down to easyrpg (image-blocked); Tier 4's GL/3D group
opened, then **mupen64plus_next** (c_asm, arm64-only, second GL-linking core).
Catalog at **91 canonical, 7 unmigrated**.

**squirreljme is BLOCKED (not a Java problem).** Its libretro core is plain C
(`nanocoat`) built by CMake, and it is shipped **armhf-only**. Two upstream
issues: (1) `nanocoat/cmake/system-map.cmake:406` omits a trailing `OR` in the
ARM32 `elseif`, breaking configure (a one-token `build.overlays` patch fixes
this); (2) the real blocker — CMake cross-builds a host utility
(`util/decode/decode`) for the target and **executes it during configure** to
decode assets, so armhf dies with `qemu-arm: Could not open
'/lib/ld-linux-armhf.so.3'`. Onboarding it needs `qemu-arm` + the armhf runtime
loader in the pinned images, or an upstream host-tools split — the same
image-toolchain class as libgametank. arm64 configures fine but is not shipped.

**Object-naming finding (blocker #3 corrected).** The "silent compiles" framing
was a partial misdiagnosis. `sameduck` is NOT silent-CMake — it is a normal
13-file C Makefile whose compiles are fully visible; its real blocker was
**object naming**: it names objects `build/obj/<path>/<name>_libretro.c.o` for
source `<path>/<name>.c`, which the engine's rigid `object == <source-stem>.o`
check rejected. Modern libretro Makefiles use many such schemes (`foo.c.o`,
`foo_libretro.c.o`, `dir~foo.cpp.o`). Resolved by an **opt-in**
`sha_pinned_object_names` flag on the c_only engine (zero change to existing
cores, differentially confirmed): it drops only the `<stem>.o` naming check — the
exact per-compile object/source pairing stays pinned by the compile pair and
invocation sha256 (the source operand must still be a lone contained `.c`). This
is a principled relaxation: the invocation sha already pins the full `-o <obj>
-c <src>` argv, so the naming check was redundant defense-in-depth imposing a
convention. The same relaxation belongs in the mixed engine for C++ cores.
`dosbox_pure` is **RESOLVED** (see its section below): it did need both the
silence `@`-strip overlay and the naming relaxation, and a third guard nobody
had hit before — `~` is in the shared line-level `FORBIDDEN_SHELL_CHARACTERS`.

**#4/#5 engine relaxation** (approved, committed): `semantic_log_path` applies a
reviewed alias before the `/` guard, the link-output guard relies on it, and the
compile guards admit an inert attached `-Wl,...`; 0 behaviour change on existing
cores. `chimerasnes` (absolute OBJDIR) is onboarded via it. The #4 subdir-output
relaxation now has a live consumer: `lutro` (its `("obj/player/","")` alias
covers both the subdir output and the object prefix).

**Tier-2 deferrals found by exploratory build (uae4arm + puae2021 now RESOLVED):**
- `uae4arm` — **armhf-only** (RESOLVED, committed `4ce10db`): the arm64 build
  fails to assemble armv7 inline asm (`rev16 r2,x0`), so it ships armhf-only
  (the first single-ABI armhf successor; the compatibility-matrix ABI-shape
  bridge was upgraded to admit `{"armhf"}`). Mixed C/C++, over the Mini ceiling.
- `puae2021` — **branch pin, NOT make-variable** (RESOLVED): it is the shared
  `libretro/libretro-uae` repo checked out at branch `2.6.1`
  (`libretro_puae2021_post_fetch_cmd="git checkout 2.6.1"`), which the
  libretro-super driver applies automatically, so the pin is carried entirely by
  the source identity (`requested_ref: refs/heads/2.6.1`, commit `0fece7d9`,
  tree `90e86c3`). No make-variable path was needed. Onboarded as a 2-ABI
  `c_only` core (176 C TUs, `build/./` object-prefix alias, `source_date_epoch`
  pinned to the committer date for reproducible `__DATE__`/build-id). Pure C, no
  libstdc++ → fleet-wide eligible.
- `arduous` (and likely `ardens`) — **silent CMake** (`[NN%] Building CXX
  object …`, no explicit compile argv). Submodule fetch works (`simavr` pulled
  via `git submodule update --init --recursive`, so the pipeline handles
  submodules regardless of the source-lock list), but the CMake build needs the
  `direct_cmake` proof path (like swanstation), not the mixed/c_only argv proof.
  Same class as blocker #3 (sameduck). Reverted cleanly.

**Remaining 18 — build system is NOT visible from the workflow** (all call
`libretro-build.sh <core>`; the make-vs-cmake choice is inside libretro-super's
recipe), so each needs an exploratory build to classify. Known-clean-make cores
are exhausted for now; the branch-pin (puae2021) and single-arch (uae4arm) paths
are proven and done. The rest split across silent-CMake/direct-cmake
(ardens/sameduck), Rust/Java
(libgametank/squirreljme), non-super driver (fake08), GL/3D
(flycast/mupen64plus_next/parallel_n64/yabasanshiro), and large multi-submodule
(chailove/dosbox_pure/easyrpg/tic80/uw8 — classify each).

Device eligibility since the arm64 fleet scrape: arm64 ceilings are captured
(a133p 3.4.28 lowest, up to gkd 3.4.33), armhf Mini 3.4.24. Every core onboarded
after the scrape (theodore/bk/opera C-only; numero/fbalpha2012 need only
GLIBCXX_3.4.21) is eligible fleet-wide. retro8 remains the only
`MINI_OVER_CEILING` case (armhf 3.4.32). A newly-onboarded core that needed
arm64 GLIBCXX > 3.4.28 would now fail the `device_sets` captured-devices test
closed — the scrape turned the arm64 ceiling into a real gate.

Device eligibility (Miyoo Mini @ GLIBCXX_3.4.24): retro8 needs `GLIBCXX_3.4.32`
→ in `MINI_OVER_CEILING`; every other core this batch stays Mini-eligible
(gme/frodo/quasi88/reminiscence; mu's 4 C++ objects are libstdc++-free and
C-linked; gw/hatari are C-only).

**Gotchas learned this batch:**
- *URL casing.* GitHub canonicalizes repo names; a lowercase pin clones but
  `promote` fails `pinned and resolved source URLs differ`. reminiscence needs
  `libretro/REminiscence.git`, mu needs `libretro/Mu.git`. Preempt with
  `gh api repos/libretro/<repo> --jq .full_name`; if wrong, fix the pin and
  rebuild sim+local (a catalog source change invalidates the build records).
- *source_date_epoch.* hatari embeds `__DATE__ __TIME__` and a build-id derived
  from it → non-reproducible. `build.source_date_epoch` must equal the commit's
  **committer** date epoch (the pipeline validates it), not the author date;
  read it with `--jq .commit.committer.date`. The epoch is an env var and does
  not change the compile argv, so extracted sha256 constants stay valid.
- *C-linked mixed cores.* mu compiles 4 C++ TUs but links with the C driver
  (`expected_link_language="c"`) because those objects are libstdc++-free; its
  objects sit one dir up, needing `semantic_path_aliases=(("./../",""),("../",""))`.

Still open: blocker #1 (residual source URLs), blocker #3 (silent-CMake, e.g.
sameduck). Blockers #4 (subdirectory link output) and #6 (intermediate static
archive) are RESOLVED — both landed as `lutro`'s c_only archive-membership
onboarding. Of the earlier remaining set: URLs still unresolved by pattern
(theodore, numero, chimerasnes, bk, fake08, libgametank, puzzlescript, uw8,
squirreljme, ardens); clean and resolvable next (opera, arduous, chailove,
fbalpha2012, easyrpg, daphne — daphne has two candidate repos, verify against
the libretro-super recipe); the rest are large/GL/exotic (flycast, parallel_n64,
mupen64plus_next, dosbox_pure, tic80, px68k, x1, np2kai, uae4arm, puae2021,
yabasanshiro) or custom forks (km_duckswanstation_xtreme_amped,
km_parallel_n64_xtreme_amped_turbo). Execute one atomic unit at a time; never
add a new core to the catalog while a suite is running.

**Continuation findings — the "tractable submodule" batch is NOT mechanical
(canonical 81, unmigrated 17).** After np2kai, two exploratory onboardings of the
supposedly-tractable submodule cores each hit a genuine, non-mechanical blocker;
both reverted cleanly (no catalog trace):
- `puzzlescript` (`nwhitehead/pzretro`, which git keeps as-is despite the
  GitHub rename to `amberwhitehead` — so `resolved_url` still matches and the pin
  is fine): **nested-submodule fetch failure**. Its `.gitmodules` nests
  `src/quickjs-ng/test262` (the huge ECMAScript test suite) inside `quickjs-ng`;
  `git submodule update --init --recursive` fails with `Skipping submodule
  '../src/quickjs-ng/'` → `fatal: not a git repository: '.git'` → `failed to
  recurse into submodule 'test262'`. Needs selective/robust submodule pinning
  (skip test262), i.e. new fetch machinery. (tic80 nests `nesbox/TIC-80` and is
  likely the same class.)
- `dosbox_pure` (`libretro/dosbox-pure`, no real submodules — cleanest by that
  measure): **silent compiles**. Its Makefile compiles with a hardcoded
  `@$(CXX) … -c` rule (line ~274), so no compile argv is echoed; the build
  succeeds and produces a byte-artifact, but the argv-proof engines
  (c_only/mixed/c_asm) have nothing to prove. Same class as blocker #3
  (sameduck's silent CMake) — **generalize blocker #3 to "silent compiles
  (CMake OR `@`-prefixed Makefile)".** Fixable per-core with a reviewed
  `build.overlays` patch that strips the `@` (the artifact stays byte-identical —
  the picodrive overlay pattern), which would unblock a whole class
  (dosbox_pure, sameduck, and likely others), but that is overlay-patch work, not
  mechanical onboarding.

Net: the cleanly-mechanical cores are exhausted. The remaining ones need one of:
(a) the object-naming relaxation ± an `@`-strip overlay per silent core
(**a DONE** — `sha_pinned_object_names` + `sameduck`; `dosbox_pure` still needs
the overlay + mixed-engine port), (b) selective submodule fetch for
nested-submodule cores (**b DONE** — `build.recursive_submodules: false` +
`puzzlescript`; `tic80` is the same class), (c) new drivers (Rust `libgametank`,
Java `squirreljme`, non-super/direct-clone `fake08`), or (d) the GL/3D + `km_*`
class — analyzed next.

## (d) The "exclusion" class analysis — nothing can be excluded

**Decisive test: a core shipped in `../spruceOS` must be covered fail-closed**
(the whole point of the catalog is to account for every shipped binary). The
shipped set has **104 distinct cores; 21 are still uncataloged**. Splitting the
21 by whether this repo carries a build workflow:

**Have a build workflow (must BUILD — the migration scope):**
- **GL/3D — `flycast`, `mupen64plus_next`, `parallel_n64`, `yabasanshiro`.**
  These are NOT exclusion candidates. Their workflows call the standard
  `./libretro-fetch.sh`/`./libretro-build.sh` (libretro-super driver) with **no**
  GL flags in the workflow — the GL choice lives in the libretro-super recipe.
  So they onboard through the *existing* driver; the real gates are (i) whether
  the `cores-arm64/armhf` images carry the GL/EGL/Vulkan dev headers the recipe
  needs, and (ii) runtime **device eligibility** — a core that needs a GPU/EGL
  provider only runs on devices that have one. Eligibility is a *device-runtime*
  concern with machinery already half-built (`build_flavor_id`,
  `accelerated_candidates`, `provider_observations`; the lone wired case is the
  `trimui-a133p-pvr-v0` accelerated ffmpeg). Plan: build them like any
  libretro-super core, then gate their device sets on a GPU/EGL provider rather
  than excluding them.
- **`km_*` personal forks — `km_duckswanstation_xtreme_amped`
  (`KMFDManic/swanstation`), `km_parallel_n64_xtreme_amped_turbo`
  (`KMFDManic/parallel-n64`).** Shipped, so must be covered. Their workflows
  **direct-clone `--depth 1`** a personal GitHub fork (the same non-super driver
  class as `fake08`, item c). A shallow direct-clone cannot pin/verify a
  commit+tree the way the fail-closed pipeline requires, so onboarding them means
  either (1) pin an exact fork commit and build through the new direct-clone
  driver, or (2) import them **artifact-only** (no reproducible source build)
  with a documented provenance caveat. Given they are one maintainer's tuned
  forks of cores we already build canonically (swanstation, parallel_n64),
  artifact-only import is the pragmatic path unless the fork is pinned.

**No build workflow here (must IMPORT artifact-only — shipped but unbuildable in
this repo):** `mkxp-z`, `mupen64plus`, the device-specific
`yabasanshiro_a133p` / `yabasanshiro_smartpros` (arm64-only, per-device tuned
Saturn builds for TrimUI A133P / SmartProS), `km_ludicrousn64_2k22_xtreme_amped`,
`km_flycast_xtreme`. These have no recipe in the repo, so the only way to cover
them fail-closed is `import-golden` artifact-only (hash-locked shipped bytes,
`package_state` static-only, no source reproduction) — or add a build recipe.
The device-specific yabasanshiro variants especially must be covered so their
target devices keep a Saturn core.

**Conclusion for (d): the "exclude the GL/km_* class" option is off the table —
every member is shipped and therefore must be covered.** The actionable split
is: GL/3D → build via the existing libretro-super driver + a GPU/EGL device
eligibility gate; `km_*` forks + the workflow-less shipped set → build via the
new direct-clone driver if a fork commit is pinned, else `import-golden`
artifact-only with a provenance caveat. The only genuinely *optional* cores are
any shipped binary a device never selects — none here qualify.

## (c) The "new driver" cores — two of three collapse

Investigating the three supposed new-driver cores changed the picture:

- **`fake08` — non-super direct-clone (RESOLVED, canonical).** Its workflow
  direct-clones `jtothebell/fake-08` and runs `make -C platform/libretro`. This
  did **not** need a new driver: the existing `direct-make` driver (git-fetch +
  make, used by gpsp) was extended with two optional, byte-inert fields —
  `build.make_subdir` (a `-C <dir>`) and `build.make_args` (a list of extra
  `KEY=VALUE` args, distinct from the libretro-super `make_variables` profile).
  `make_args: ["V=1"]` flips fake08's `Q := @` echo guard so the compile argv is
  visible (artifact byte-identical). fake08's Makefile also sets `CC = $(CXX)`,
  compiling all 56 units (36 C, 20 C++) with g++, which needed one more opt-in
  mixed-engine relaxation — `cxx_compiler_compiles_c` (admits a `.c` under g++;
  a `.cpp` under gcc is still rejected; the exact compiler stays pinned by the
  invocation sha256). Reproducible, promoted.
- **`squirreljme` — NOT a new driver.** Its workflow calls the standard
  `./libretro-build.sh squirreljme` (libretro-super driver). The "Java ME"
  label describes what the core *runs*, not how it is *built* — the libretro
  core is a normal C/C++ build. It should be re-examined as an ordinary
  libretro-super onboarding (exploratory build to classify), not new machinery.
- **`libgametank` — genuinely Rust, blocked on the Docker image.** Its workflow
  does `cargo install cargo-zigbuild` + `cargo zigbuild --target
  <triple>.2.23 --release` producing `target/<triple>/release/libgametank_libretro.so`.
  The `cores-arm64`/`cores-armhf` images have **no** `cargo`/`rustc`/`zig`
  (verified), so it cannot be built here at all until the Rust + `cargo-zigbuild`
  + zig toolchain is added to the pinned images — a Docker-image change outside
  this repo. Design for when the toolchain lands: a new `cargo` driver that
  fetches, then runs `cargo zigbuild --locked --target <triple> --release`; the
  fail-closed proof does **not** map to per-object argv — instead pin
  `Cargo.lock` (the exact crate graph + registry checksums), the exact `cargo`
  invocation and target triple, and the rustc/cargo-zigbuild/zig versions, with
  reproducibility via `--locked` + a pinned rustc + `SOURCE_DATE_EPOCH` +
  `--remap-path-prefix`. Until the image ships Rust, `import-golden` artifact-only
  is the only fail-closed coverage.

Net (c): the non-super driver class is delivered (fake08); squirreljme folds
into the ordinary pipeline; only libgametank needs genuinely new machinery, and
it is gated on a toolchain the pinned build images do not yet carry.

**Terminal step — historical-oracle retirement (DONE, 2026-07-23).** The
legacy-tranche cohort is retired in full: the fallback oracle
`registered_historical_core_log_contract_proves`, the per-core
`*_historical_*` helpers and constants, the mgba golden-start bridge branch,
the aggregate `golden-start` composer, the legacy-matrix input to the
compatibility coverage loader, `tests/legacy_tranches/`, and
`tests/fixtures/legacy-tranches/` are all gone; coverage is asserted
per-core-only. `freeintv`, `mgba`, and `vemulator` keep their ACTIVE
envelope proofs (marker-backed, unchanged); marker-free logs are now simply
rejected with no fallback. Reviewed per-core oracle log fixtures — current
regression inputs, not chronology — were relocated to
`tests/fixtures/per-core-oracles/`. Successor coverage for the retired
active-surface assertions lives in `tests/test_canonical_surfaces.py`. The
candidate-id guard still rejects "tranche" names so retired identifiers are
never reused. The chronology is preserved in git history (last present at
`dd82cc4`).

## chailove (RESOLVED, canonical `chailove-5fa2014d9a13-f10fcc3308fc`)

`libretro/ChaiLove` bundles ChaiScript, PhysicsFS, libz and libretro-common:
**71 C + 30 C++ + 1 assembly** (`sinc_resampler_neon.S`) TUs, linked by the C++
driver — the plain `c_asm` standard once two obstacles were cleared.

**1. Silent Makefile → `build.overlays`.** Its Makefile sets an unconditional
`Q=@` (the `VERBOSE` switch that was supposed to guard it is never consulted),
so no compile argv ever reaches the log. `patches/chailove/makefile-echo-compile.patch`
flips that one token to `Q=`. It is echo-only: both profiles reproduced
byte-identically (arm64 `1c19c132…`, armhf `0ce222a2…`), so the artifact is
unaffected. This is the same `git-apply-v1` overlay machinery used elsewhere,
with the pre/post/patch digests all pinned in the contract.

**2. `mixed_language` option-operand parity fix (engine bug, now fixed).**
Every chailove compile carries `-include retro_endianness.h`. `c_only` and
`c_asm` already exclude `FILE_OPERAND_FLAGS` operands (`-I`/`-include`/
`-isystem`/`-iquote`/`-imacros`/`-idirafter`) when locating the source operand;
`mixed_language` did not, so it read the forced-include header as a *second*
source and rejected all 102 compiles. Fixed in `mixed_language.py` for parity.
The fix is a strict relaxation of a previously-unreachable rejection: the whole
suite is unchanged by it, and chailove itself ended up on `c_asm` anyway (the
one `.S` file rules `mixed_language` out).

**Note for the next Tier-3 core:** the URL-pinning gotcha bit again —
`libretro-super`'s rule points at `https://github.com/libretro/ChaiLove.git`
(capital L's), which is what the catalog must record; `git remote get-url`
inside a clone reports the same, but GitHub's redirect means a lowercase guess
would silently diverge from the rule's URL.

armhf needs `GLIBCXX_3.4.32`, so chailove joins `MINI_OVER_CEILING`
(Miyoo Mini ineligible; A30 and up fine).

## dosbox_pure (RESOLVED, canonical `dosbox_pure-a4a0bab7f893-9faece3e3c8a`)

112 C++ translation units, no C at all (`expected_language_counts` is just
`{"cxx": 112}`), linked by the C++ driver — the `mixed_language` standard. It
had been deferred as needing two relaxations; it actually needed three, and the
third is the interesting one.

**1. Silent `COMPILE` define → `build.overlays`** (the chailove technique).
`define COMPILE` ends in `@$(CXX) ...`, so no compile argv reached the log; the
link recipe was already visible. `patches/dosbox_pure/makefile-echo-compile.patch`
drops that one `@`. Reproducible byte-for-byte on both arches
(arm64 `251c9d32…`, armhf `bfa06c14…`), so the overlay is provably echo-only.

**2. `sha_pinned_object_names` in `mixed_language`** (parity with `c_only`).
The Makefile flattens the tree into one object dir by mangling `/` to `~`:
`src/hardware/vga.cpp` → `build/release/src~hardware~vga.cpp.o`. The object
name is no longer `<stem>.o`, so the naming check is dropped; the exact
object/source pairing is still pinned by the compile-pair and per-arch
invocation sha256.

**3. Two `~` guard relaxations — the part worth reviewing.** `~` is a shell
metacharacter, and it was blocked in *two* independent shared guards:

* `semantic_log_path`'s per-segment charset. Relaxed **globally** to admit a
  `~` that is not the first character of a segment. This is safe on its own
  terms: a leading `~` (`~/x.o`, `~user/x.o`) is exactly the home-directory
  escape the containment guard exists to catch — make runs recipes through
  `/bin/sh`, so such a path is expanded before the compiler sees it and the log
  echoes only the unexpanded text. Non-leading `~` is an ordinary filename
  character with no expansion behaviour.
* `command_line_is_lexically_safe`'s `FORBIDDEN_SHELL_CHARACTERS`. This one is
  the coarse "no shell metacharacters anywhere in the line" guard, so it was
  **not** relaxed globally. It gained an opt-in `allow_embedded_tilde`
  parameter, surfaced as a `MixedLanguageLogContract` field, that admits `~`
  only when the preceding character is itself an ordinary path character
  (`[A-Za-z0-9_+./-]`). A `~` at line start or after whitespace, a quote, `:`
  or `=` stays forbidden; every other metacharacter is untouched; and left
  unset the guard is byte-for-byte the original. Only dosbox_pure sets it, and
  `tests/cores/test_dosbox_pure.py` pins both the admitted shape and the
  rejected escapes.

armhf needs `GLIBCXX_3.4.29`, so dosbox_pure joins `MINI_OVER_CEILING`.

## parallel_n64 (RESOLVED, canonical `parallel_n64-00c6c9df91d2-be061373ae12`)

The first core in the catalog whose artifact **directly links a graphics
library**. Everything onboarded before it reaches GL through the frontend
(`SET_HW_RENDER` + `get_proc_address`), which is why `DT_NEEDED` had been blind
to HW capability; the shipped SpruceOS `parallel_n64_libretro.so` carries
`libGLESv2.so.2` outright. It is also shipped **arm64 only**, so the catalog
targets one ABI.

**The build problem.** Its Makefile defaults `ARCH` to `uname -m`, which is
`x86_64` on the cross-build host, so the stock build selects the x86 dynarec and
`-msse -msse2` — flags the aarch64 compiler rejects outright. `ARCH` is a
*reserved* make-variable name (the pipeline owns toolchain identity and refuses
to let the catalog set `ARCH`/`CC`/`CFLAGS`/...), so the obvious fix was closed.

**The way through.** The Makefile keys everything that matters off non-reserved
switches: `WITH_DYNAREC` (which merely *defaults* to `$(ARCH)`) selects the
dynarec and its `linkage_arm64.S` assembly, the `-msse` block is gated on
`WITH_DYNAREC` being x86-shaped rather than on `ARCH`, and `NOSSE=1` suppresses
it regardless. So `WITH_DYNAREC=aarch64 GLES=1 NOSSE=1` reaches the same
configuration without naming a reserved variable. That equivalence was
*verified, not assumed*: a full build with `ARCH=aarch64 GLES=1` and one with
the non-reserved set produced a byte-identical `parallel_n64_libretro.so`
(`f47da51e…`).

**The one extension.** `WITH_DYNAREC=aarch64` is a string, and
`build.make_variables` accepted only the exact integers 0 and 1. It now also
accepts an identifier-shaped string (`[A-Za-z0-9_][A-Za-z0-9_.-]*`) — but the
type check is not what admits it. As with the four existing profiles, the value
mapping must equal a reviewed per-core profile constant
(`parallel-n64-aarch64-gles-v1`), so no free-form string can reach the make
command line. Three other spots needed the new profile threaded through: the
`make_variable_shell` makefile selection, the golden build contract, and the
recipe-snapshot validator (the last two were hardcoded to the portable-FFmpeg
shape, which pins a `source_date_epoch`; parallel_n64 forbids one).

**GLES is pinned by the proof.** `-lGLESv2` is part of the contract's exact link
options, so a build that silently lost the GLES renderer stops proving the
contract. `tests/cores/test_parallel_n64.py` asserts that directly.

250 translation units (215 C, 34 C++, 1 assembly), reproducible byte for byte
(`7b35b431…`). Being arm64-only it never reaches the Miyoo Mini armhf ceiling.
Device eligibility for it is a **new question**, though: it is the first core
that needs a GLES2 *provider* on the device, not just a matching libc.

## mupen64plus_next (RESOLVED, canonical `mupen64plus_next-98c1b0d87754-c2f40f19482c`)

The second GL-linking core, and the first onboarded *after* the fleet capture —
so device eligibility was known before the build rather than after.

**Reused wholesale from parallel_n64:** the same reserved-`ARCH` problem
(`WITH_DYNAREC ?= $(ARCH)`, `ARCH ?= uname -m` = x86_64 on the cross host) and
the same answer — name the non-reserved switches instead. Here that is
`WITH_DYNAREC=aarch64` plus the Makefile's own documented `FORCE_GLES=1`. Again
verified rather than assumed: a build with `ARCH=aarch64 FORCE_GLES=1` and one
with the non-reserved pair produced a byte-identical artifact (`8cfb735c…`).
The string-valued `make_variables` machinery needed no extension, only a second
reviewed profile — which is what that machinery was built for.

**One new relaxation — `build.submodules: false`.** Its tree declares **no
submodules at all** (there is no `.gitmodules`) yet carries a dangling gitlink
at `mupen64plus-rsp-paraLLEl/lightning/gnulib`. `git submodule update --init`
fails on it with or without `--recursive`, so the existing
`recursive_submodules: false` was not enough; and `git submodule status` fails
on it too, which broke provenance capture as well. With submodules disabled the
checkout skips the fetch entirely and provenance records the gitlink straight
from the tree (`git ls-tree -r HEAD`, filtered to `commit` entries), so the
pinned SHA `e54b645f…` stays visible rather than hidden. Nothing is lost:
`HAVE_PARALLEL_RSP` defaults to 0, so none of those sources are compiled.

**Device evidence, known in advance.** Our artifact needs the *versioned*
`libGLESv2.so.2` and `libEGL.so.1` — unlike the shipped build, which linked the
unversioned dev symlinks. Both versioned sonames are in the fleet's captured
library observations, so the join reports it eligible on all four probed arm64
devices, `provider_uncaptured` on the two unprobed ones, and `no_arch_target`
on the armhf pair. 272 translation units (141 C, 130 C++, 1 assembly),
reproducible byte for byte (`22c156c6…`).

## flycast — BLOCKED on the image's CMake (investigated 2026-07-22, reverted cleanly)

Attempted after mupen64plus_next on the assumption it was buildable. It is not,
and the earlier "buildable" assessment was wrong: it was based on the
libretro-super rule and the device capture, neither of which says anything
about the build image. `flycast/CMakeLists.txt:6` requires **CMake >= 3.22.1**
and the pinned `cores-arm64` image ships **3.16.3**, so configure fails before
a single source is compiled. Reverted with no catalog trace.

**This is now a two-core blocker with one cause.** `easyrpg` needs CMake >=
3.18 and `flycast` needs >= 3.22.1, so a single image bump to CMake >= 3.22.1
unblocks both — a third of what remains. That is an image change, which
re-pins the toolchain identity every recipe hash covers, so it is a decision to
take deliberately rather than a side effect of onboarding one core.

Two things are already known about flycast for when it is unblocked:

* It links `libGLESv2.so.2` on **both** ABIs. The fleet capture shows the
  **Mini Plus has no GLES2 provider at all**, and its shipped armhf flycast
  fails to load there today with exactly that missing soname. So the Mini Plus
  exclusion is established evidence, not a prediction — the provider screen
  will report `missing_provider` the moment an armhf flycast is onboarded.
* It carries 22 submodules and a `flycast_libretro` CMake target with
  `LIBRETRO=ON`, so it is a `direct-cmake` core needing no per-core contract.

**The KM forks are also not one-step.** `libretro-super`'s rule file has **no
`km_*` entries at all** (`grep -c km_` returns 0), so neither
`km_duckswanstation_xtreme_amped` nor `km_parallel_n64_xtreme_amped_turbo` can
use the `libretro-super` driver. They need the direct-clone driver that (d)
describes, which is separate machinery from anything landed so far.

## km_duckswanstation_xtreme_amped (RESOLVED, canonical `km_duckswanstation_xtreme_amped-be16ead371a6-3cd0293f7e46`)

The predicted "direct-clone driver" dissolved on inspection: the KM fork is a
plain CMake tree that keeps upstream's `swanstation_libretro` target, so the
existing **direct-cmake** driver covers it. Three small, reviewed extensions
were the whole cost:

1. **Repo-pinned metadata.** No `km_*` info exists in the image's
   libretro-super (`grep -c km_` = 0), but SpruceOS ships the info files — the
   authoritative deployed metadata. The catalog now accepts
   `metadata: {repo_path: metadata/<core>_libretro.info, sha256, artifact_name}`;
   the file is mounted read-only, its sha256 re-verified inside the container,
   and a `CORE_PIPELINE_METADATA_REPO|<sha256>` marker lands in the build log.
2. **Rebrand rename, restricted to the core's own name.** The fork builds
   `swanstation_libretro.so` and ships as
   `km_duckswanstation_xtreme_amped_libretro.so`. The direct-cmake rules now
   allow `output_path` basename ≠ `artifact_name` **only** when the artifact is
   `<source_dir>_libretro.so` (and source_dir == core_id is already enforced),
   so an artifact can never impersonate another core.
3. **A reviewed rename table in the golden validator**
   (`DIRECT_CMAKE_RENAMED_TARGETS`), pinning the exact upstream target per
   renamed core.

armhf-only (matching the shipped SpruceOS cores/ directory), reproducible byte
for byte (`51502e60…`). Needs `GLIBCXX_3.4.32` → `MINI_OVER_CEILING`; the
*shipped* fork (older toolchain) did load on the Mini, so the Mini keeps its
shipped copy story while every newer-ceiling device gets the fail-closed build.

**km_parallel_n64_xtreme_amped_turbo** follows the same path via direct-make
(`platform=unix WITH_DYNAREC=arm FORCE_GLES=1`, armhf-only) — in progress.