# Fail-open workflow migration (COMPLETE)

**Finished 2026-07-24: 98 of 98 shipped-core workflows are canonical**
(audit: `unmigrated_workflow_count: 0`, `masked_build_failure_paths: 0`,
`info_only_risk_workflows: 0`), the full-roster release plan constructs,
and GitHub Actions runs reproduce the pinned builds. This page is the
compact record of that migration; the full working runbook — dated status
logs, the blocker log, planning tables, and per-core case studies — is
preserved in this file's git history. For onboarding a core today use
[`adding-a-new-core.md`](adding-a-new-core.md); for current status see
[`pipeline-overview.md`](pipeline-overview.md).

## What was migrated, and why

The retired workflows were fail-open: `permissions: contents: write`
(could mint releases), a free-form `core_ref` input (built arbitrary,
unpinned refs), `|| true` masks (failed builds still "passed"), and
builds against latest upstream with no pinned commit or tree. At kickoff
the audit reported 88 masked-failure paths and 44 unmigrated workflows,
after six legacy bridge cores had already been converted.

Each core was onboarded as one atomic unit: pin the source (commit +
tree), catalog it, compose its source lock, prove its build log against
a reviewed contract, replace its workflow with the shared read-only
dispatcher, and promote a byte-reproducible dual-build. The shared
dispatcher gives every core `permissions: contents: read`, pinned
actions, verified toolchain archives, and no release/ref/masking paths.

## Durable machinery the migration produced

These capabilities were built for specific cores and remain available to
every future onboarding:

- **Drivers**: `direct-make` (+ `make_subdir`, `make_args`),
  `direct-cmake` (+ `source_subdir`, `defines`, non-root `output_path`),
  and `direct-cargo` (Rust via cargo-zigbuild in the locked `cores-rust`
  image, Cargo.lock-shaped proof) alongside `libretro-super`.
- **Reviewed opt-in proof relaxations** (each inert unless configured):
  `sha_pinned_object_names`, archive-membership mode, forced-include
  operand parity, `allow_embedded_tilde`, absolute-build-root and
  subdirectory-output aliases, `cxx_compiler_compiles_c`.
- **Build-time overlays** (`build.overlays`, sha-pinned git-apply): used
  to unsilence `@`-prefixed Makefiles (artifact provably byte-identical)
  and to repair broken-at-pin upstreams (km_parallel_n64's five patches).
- **Source controls**: branch pins, `submodules`/`recursive_submodules`
  toggles, `source_date_epoch` (committer date), URL case
  canonicalization, repo-pinned metadata for cores absent from
  libretro-super.
- **Reproduction normalizations** (validation-layer only): CMake
  progress/timing prefixes, GCC temp-file names, `make
  --output-sync=recurse` for the portable-FFmpeg profile, parallel-make
  line-multiset comparison.
- **String-valued `make_variables`** gated on reviewed per-core profiles
  (the reserved-`ARCH` workaround: name the non-reserved switches and
  prove byte-identity).

## Lessons worth keeping

- Replace the workflow **before** the sim/local builds — recipe identity
  includes `workflow_sha256`.
- Never edit the catalog or the hashed pipeline bundle between a core's
  builds and its promote; never add a core mid-suite-run.
- GitHub canonicalizes repo-name casing; pin the canonical URL
  (`gh api repos/<owner>/<repo> --jq .full_name`) or promote fails on
  `resolved_url`.
- The libretro-super rules files (not naming patterns) are the source-URL
  authority; several cores live in upstream-author repos.
- A core that executes a cross-built tool at configure time needs
  qemu-user + the target loader in the image (squirreljme), and an image
  that lacks a required toolchain blocks onboarding outright until the
  image is re-pinned (flycast/easyrpg CMake, libgametank Rust) — image
  changes re-pin toolchain identity and are taken deliberately.
- `DT_NEEDED` is blind to hardware capability: libretro HW rendering is
  frontend-mediated, so device eligibility reads `.info`
  `hw_render`/provider observations, not linked sonames. flycast is the
  only genuinely GPU-required core in the catalog.

## The final six

The queue closed with flycast (the v2 images' CMake unblocked it;
direct-cmake dual-ABI), yabasanshiro (one generic dual-ABI build replaced
three device-tuned vendor variants), easyrpg (pinned static dependency
prefix for both ABIs), squirreljme (qemu path; armhf-only),
libgametank (first Rust core, direct-cargo), and
km_parallel_n64_xtreme_amped_turbo (overlay-repaired at its pinned
commit; armhf-only).

Four shipped binaries remain uncataloged because this repository has no
build recipe for them; they are tracked in the uncataloged tail in
[`pipeline-overview.md`](pipeline-overview.md) with per-core reasons.
