# Optimization level machinery

Two routes to per-chipset, per-optimization core builds, plus the ad-hoc action
that drives either one. Both need code; neither is a configuration-only change.

## The constraint that shapes both routes

An injected `-O` cannot win. Measured on a real np2kai arm64 build in the pinned
`cores-arm64` image: the environment's `CFLAGS` (which carries the registry's
machine flags) lands at character 85 of the compile line, and the core makefile's
own `-O2` at character 303. GCC resolves `-O` last-wins, so appending `-O3` or
`-O0` to `CFLAGS` is silently discarded. 351 of 351 target compiles used `-O2`.

The lever that does work is the libretro convention. `np2kai/sdl/Makefile.libretro`
declares `DEBUG ?= 0` at line 1 and gates optimization on it:

- `:728 ifeq ($(DEBUG), 1)` -> `:737 COMMONFLAGS += -O0 -g -DDEBUG -D_DEBUG -DTRACE`
- else -> `:746`/`:748 COMMONFLAGS += -O2 -DNDEBUG -D_NDEBUG`

`?=` means a make-level override wins, and MAKEFLAGS entries are command-line
overrides. So `DEBUG=1` reaches the build; `-O3` has no knob at all and needs a
source overlay, which is why the registry states an expected level instead of
assuming one took effect.

**Every profile therefore asserts its outcome in the build log.** `release-o3-v1`
fails on a core whose makefile hardcodes `-O2` rather than passing while shipping
`-O2` under an `-O3` label. Asserting the input instead would make the machinery
lie, which is the one failure mode worth designing against.

## Route B: one orthogonal dimension (implemented here)

`manifests/optimization-profiles.json` plus `core_pipeline_lib/optimizations.py`,
modelled on the chipset tuning registry: typed intent only, code owns the mapping,
identity hashed per profile.

| profile | make variables | build log must prove |
|---|---|---|
| `release-v1` | *(none)* | *(nothing)* |
| `debug-v1` | `DEBUG=1` | `-O0`, `-g` |
| `release-o3-v1` | `DEBUG=0` | `-O3` |

`release-v1` is schema-constrained to the exact empty profile so an unselected
dimension reproduces the recorded goldens byte for byte.

The catalog stays at 100 cores and the cross product is computed per run.
`--optimization-profile` exists on `e2e` and `build-core`, and currently **fails
closed** for any non-baseline value: the registry and identity are complete, but
make-variable injection and the log proof are not wired into the drivers, and a
flag that records a profile it never applied is worse than no flag.

Remaining: inject the resolved make variables into the canonical MAKEFLAGS, emit a
`CORE_PIPELINE_OPTIMIZATION|` marker beside the existing
`CORE_PIPELINE_CHIPSET_TUNING|` one, verify the expected tokens on every target
compile line, and fold the profile identity into the build identity so debug and
release artifacts cannot collide in the content-addressed store.

## Route A: specialized per-core variant entries

The repo's existing idiom for build variants is separate catalog entries --
`flycastslim`, `flycastslim-lto`, `flycastslim-vk`, `flycastslim-ppr` -- fed by the
per-core `build.make_variables` field, which already carries full
`CORE_PIPELINE_MAKE_VARIABLE|name|value|origin` verification.

This route is **not** configuration-only. `make_variable_profile` admits only a
closed set of reviewed named profiles compared by equality, deliberately, "so no
free-form string ever reaches the make command line". A `DEBUG=1` entry therefore
needs a new `MakeVariableProfileFacts` in `build_contracts.py` as well as:

- a catalog entry per core per variant (300 entries for 100 cores x 3),
- a `build-<core>-<variant>.yml` workflow per entry,
- reviewed edits to `CATALOG_CORE_COUNT` and `CORE_WORKFLOW_COUNT` in
  `tests/expected_counts.py`.

It buys per-core specialisation: one core can take a bespoke variant without
touching a global registry, and each variant is independently pinned and promoted.
It costs a tripled catalog and tripled workflow count.

## Recommendation

Route B for breadth, Route A for exceptions. The cross product is a property of a
run, not of a core, so encoding it as 300 catalog entries triples the two counts
the migration scoreboard tracks. Keep Route A for a core that genuinely needs a
bespoke variant, which is what `flycastslim-*` already demonstrates.

## The ad-hoc action

`.github/workflows/_build-core-variant.yml` takes `core_id`, `chipset`,
`track_tag` and `optimization_profile`, resolves the group before downloading
~500MB of toolchains so a bad pair fails in seconds, and builds that core's
complete declared target set within the chipset's architecture. A chipset
selection narrows to one architecture because a typed tuning profile is
architecture-bound.

`_build-one-core.yml` is deliberately **not** touched. The release audit pins
exactly three orchestration workflows -- coordinator, worker and overlay -- by
shape and by byte identity, with `unique_reusable_workflow_count: 1`, and
`_build-one-core.yml` is the worker. Threading an optimization input through it
invalidated that pinned identity: 8 `test_full_release_repository` failures plus
the audit's own validity check. The release path should produce canonical
baseline artifacts reproducibly, so the tunable axis lives only in the ad-hoc
entry point. Driving the release path at a non-baseline level is a deliberate
change to the pinned orchestration contract and belongs in its own review.

The underscore prefix keeps the ad-hoc file out of the core-workflow count;
`audit-workflows` still reports 100 shared pipeline workflows with no
uncataloged entries.

## Verification

Measured on a WSL build host against a pristine worktree at the same base commit, with the
evidence-bound families excluded because a fresh worktree has no `.local-e2e`
store (`tests/cores` and the 89 `test_contract_*` files):

| tree | failed | passed | errors |
|---|---|---|---|
| pristine `d9e09c9` | 24 | 906 | 83 |
| with this change | 24 | 925 | 83 |

Identical failures and errors; passes up by exactly the 19 new tests. A baseline
build also reproduces the recorded golden byte for byte (np2kai a53
`c61c6fc8...`, pipeline exit 0), which is what proves `release-v1` is inert.

Two traps worth recording for whoever wires the injection. Verifying by
`git apply` without committing produces 17 phantom failures, because several
contracts legitimately reject untracked orchestration and roster files. And
That host's umask is 002, so a fresh worktree checks out 664/775 while the
source-bundle gate demands exactly 0644/0755 -- normalise from
`git ls-files -s` before building or testing.

## Redundancy, measured

Tuned np2kai arm64 artifacts collapse further than the registry predicts.
`-mcpu=cortex-a53` and `-mcpu=cortex-a55` produce byte-identical output
(`c61c6fc8...`), verified across three independent builds each doing 360 target
compiles, with GCC reporting the flags distinctly. So `a133p`, `a523` and `rk3566`
share one artifact and only `rk3326` (`-mcpu=cortex-a35`) is distinct. This is
per-core -- a core using A55-only features would split -- so the grouping must be
measured per core, not assumed.
