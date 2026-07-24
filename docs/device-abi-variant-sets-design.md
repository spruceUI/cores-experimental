# Device-pinned ABI variant sets — design proposal

Status: **proposal / RFC** · Scope: build + device-eligibility architecture ·
Preserves: fail-closed, hash-locked, publication-disabled invariants.

> **Status update (2026-07-24):** the Mini-family ceiling this proposal
> opens with is resolved — the family's bundled libstdc++ provider is now
> the A30 build (Lever B, shipped as spruceOS `ee825739d`), raising the
> effective armhf fleet ceiling to GLIBCXX 3.4.32. No pinned core is over
> any probed device's ceiling today; the flavor machinery below remains
> the design of record for future ceiling or GPU-provider divergence.

## 1. Problem

Today a core builds exactly two artifacts — one per ABI (`arm64` →
`ra64-universal-v1`, `armhf` → `ra32-a30-v1`, bound in
[`profile_registry.py`](../scripts/profile_registry.py) `PROFILE_BINDING`). The
`armhf` artifact is compiled against the A30 toolchain, whose `libstdc++`
exposes symbols up to `GLIBCXX_3.4.32`.

Device eligibility is then a **binary static screen**
([`device_sets.py`](../scripts/device_sets.py) `classify_core`): a C++ core is
`eligible` iff its required `GLIBCXX_x.y.z` ≤ the device's provider ceiling,
else `over_ceiling`. The Miyoo Mini family's packaged-fallback `libstdc++` caps
at `GLIBCXX_3.4.24`, so every C++ core that needs more is **excluded outright**:

```
MINI_OVER_CEILING = { fbneo, gambatte, gearboy, gearcoleco, gearsystem,
                      mednafen_pcfx, mednafen_supafaust, neocd, nestopia,
                      retro8, snes9x, stella2014, uzem }
```

That is 11 cores the Mini class can never see, purely because one shared
artifact was compiled against a newer `libstdc++`. The same `.so` runs fine on
the A30. The screen has no way to say "run a *different, still-proven* build of
this core here." That is the gap this proposal closes.

## 2. Key insight — the flavor machinery already exists, dormant

The pipeline already reserves every hook needed for per-device variants; only
one narrow use (a GPU-accelerated ffmpeg) is wired:

| Existing hook | Where | Today |
|---|---|---|
| `build_flavor_id` (`^[a-z0-9-]+-v[0-9]+$`) | `device-runtime-contracts.schema.json` `$defs.acceleratedCandidate` | one value: `trimui-a133p-pvr-v0` |
| `candidate_build_flavors[]` per device | every device contract | all `[]` except the Trimui PVR case |
| `accelerated_candidates[]` per core | `core_policies.ffmpeg` | binds a flavor → runtime contracts + families + `status` |
| `provider_observations[]` with `role` | each device | `bundled-first-search-path-provider` (A30 @3.4.32) vs `packaged-fallback-provider` (Mini @3.4.24), all `enforcing:false` |
| `compatibility_constraints[]` | contracts | `mini-cxx-provider-unverified-v0` records gearboy/gearsystem needing `GLIBCXX_3.4.32` on Mini |

And the architecture doc already carves the escape hatch explicitly
([`core-pipeline-architecture.md`](core-pipeline-architecture.md)): *"Device
grouping does not justify copying a universal core pin; **only a proven
build-flavor or ABI difference creates another selection**."* A variant is not a
new concept to sell — it is the activation of a reserved, already-blessed one.

## 3. Invariants the design must not break

1. **Fail-closed / hash-locked.** Every artifact a device can select is
   sim+local byte-reproducible, contract-proven (the shared compile/link
   standard), golden-imported, promoted, and pinned. No exceptions for variants.
2. **No copied pins.** A variant earns its own semantic id from its own content
   hash; it is a distinct proven selection, never a relabel of the universal pin.
3. **Static-ABI-only screening.** The resolver still makes *no runtime claim*;
   variant sets stay `provisional`/`ineligible` until a target-runtime smoke gate
   (a human/hardware gate) clears them, exactly as canonical cores are today.
4. **Publication disabled** throughout.

## 4. Two independent levers

Coverage = (core's required ceiling) ≤ (device's effective ceiling). There are
two ways to close a gap, and the design supports both:

- **Lever A — lower the core's requirement (build-flavor variant).** Produce an
  additional artifact of the *same source* that depends on a lower ceiling (or
  none). This is a new build identity `(core_id, flavor_id)`.
- **Lever B — raise the device's effective ceiling (provider bundle).** Ship a
  vetted newer `libstdc++.so.6` in the device's first search path, exactly like
  the A30 already does (`bundled-first-search-path-provider`). This is a device
  runtime-contract change, no rebuild.

## 5. Flavor strategies (Lever A) and the provider bundle (Lever B)

| Strategy | Mechanism | Effect on `version_requirements`/`needed` | Cost | Recommendation |
|---|---|---|---|---|
| **`static-libstdcxx-v0`** | link `-static-libstdc++ -static-libgcc` | drops `libstdc++.so.6` from `needed`; GLIBCXX ceiling stops applying — only the (universally-met) `GLIBC` ceiling remains | +~1–2 MB per `.so`; no new toolchain | **Primary.** Clears ~all of `MINI_OVER_CEILING`. |
| **provider bundle (Lever B)** | ship `libstdc++.so.6`@3.4.32 in Mini set's search path | device effective ceiling 3.4.24 → 3.4.32; **no rebuild**, shared by all cores | one vetted lib per device; storage amortized across cores | Strong complement when many cores would each pay the static size cost. Very "Spruce." |
| **`glibcxx-3.4.24-v0`** | second `armhf` toolchain capped at Mini's ceiling | genuinely lower-ceiling **shared** binary | second toolchain; possible C++17 friction | Reserve for cores where static linking is problematic. |

Notes:
- Static `libstdc++`/`libgcc` is license-safe under the **GCC Runtime Library
  Exception** — worth stating for the licensing gate.
- libretro cores are `dlopen`ed one at a time by the frontend; a core carrying
  its own static `libstdc++` is the standard, proven libretro portability fix.
  The cross-boundary C++ ABC concern is covered by the existing
  `needs-target-runtime` smoke gate — we do not claim runtime, we gate on it.
- Lever B is the most Spruce-idiomatic (the firmware already bundles the A30
  lib); it reuses the `provider_observations` model verbatim by adding a
  `bundled-first-search-path-provider` row to the Mini contract with real
  `sha256`, then flipping `enforcing:true` once captured.

## 6. Data-model changes

All additive; each defaults to today's behavior so an empty rollout is
byte-inert (the pattern proven by the overlay/patch layer).

**6.1 Catalog — declare flavors per core.**
```jsonc
// manifests/core-builds.json  →  cores.<id>.build
"abi_flavors": {                     // optional; absent ⇒ {"default": …} only
  "static-libstdcxx-v0": {
    "link_append": ["-static-libstdc++", "-static-libgcc"],
    "targets": ["armhf"]             // only build the flavor where a gap exists
  }
}
```
The implicit `default` flavor is today's shared build. A flavor is a *recipe
delta* over the default (extra link/compile flags, or a toolchain override for
the low-ABI strategy) — validated by a closed schema exactly like `overlays`.

**6.2 Build identity — `(core_id, flavor_id)`.**
`build-core --core fbneo --flavor static-libstdcxx-v0`. The default flavor keeps
today's CLI (no `--flavor`). Every downstream identity gains a flavor segment:

```
semantic id:  fbneo-<commit>-<content>            (default, unchanged)
              fbneo+static-libstdcxx-v0-<commit>-<content>
pin:          pins/core-sets/<semantic-id>.json
golden:       .local-e2e/nightlies/<semantic-id>/golden.json
compat:       manifests/compatibility/<core>.json   → targets.<arch>.flavors[]
```
Each flavor reuses the **entire** existing promote chain (import-golden →
promote → derive-core-id → compose-core-golden → compose-pin-set →
compose-lifecycle) and its own log contract. Nothing bespoke.

**6.3 Contract — one per flavor.** The `static-libstdcxx-v0` flavor's
mixed/c-only contract pins *its* link options (now including
`-static-libstdc++`) and *its* captured `needed`/`version_requirements` (with
`libstdc++.so.6` absent). This is just another registered
`<core>_<flavor>_log_proves_contract`.

**6.4 Device variant set — the new pinned artifact.** A composed, hash-locked
manifest per device family that records, for each core, which flavor pin the
device selects:
```jsonc
// manifests/device-sets/device-miyoo-mini-family-v0.json  (composed, not hand-authored)
{
  "device_contract_id": "device-miyoo-mini-family-v0",
  "effective_ceiling": "3.4.24",            // or 3.4.32 if a provider bundle is enforced
  "selections": {
    "fbneo":   { "flavor": "static-libstdcxx-v0", "pin": "pins/core-sets/fbneo+static-libstdcxx-v0-….json", "cleared_by": "static-runtime" },
    "gambatte":{ "flavor": "static-libstdcxx-v0", "pin": "…", "cleared_by": "static-runtime" },
    "2048":    { "flavor": "default", "pin": "…", "cleared_by": "c-only" },
    "picodrive_over_only_example": { "excluded": "no-clearing-flavor" }
  },
  "content_sha256": "…"
}
```

**6.5 Resolver — `classify_core` becomes multi-flavor.** Signature moves from
`(target, ceiling) → bucket` to
`(targets_by_flavor, ceiling, provider_bundle) → (bucket, chosen_flavor)`.

## 7. Resolver algorithm

For each `(device, core)`:
1. Gather every promoted flavor target for the core on the device's arch,
   including `default`.
2. Compute each flavor's **effective need**: `max GLIBCXX_*` in its
   `version_requirements`, or *none* if the flavor does not list
   `libstdc++.so.6` in `needed` (static/C-only clears any ceiling).
3. Device **effective ceiling** = max(packaged-fallback ceiling, any
   `enforcing:true` bundled-provider ceiling) — Lever B raises this.
4. **Select** the *lowest-cost* flavor whose need ≤ effective ceiling, by the
   deterministic cost order: `default` (smallest) → provider-bundle-cleared
   `default` → `static-libstdcxx-v0` → `glibcxx-3.4.24-v0`.
5. If no flavor clears → `over_ceiling` (genuinely uncovered) with the reason.

Determinism and static-only semantics are unchanged; the only new freedom is
picking among *proven* artifacts instead of a single one.

## 8. Worked example — Miyoo Mini

Effective ceiling 3.4.24. Today: 11 C++ cores `over_ceiling`. After Phase 3:

| Core | Default need | Selected flavor | Result |
|---|---|---|---|
| `2048`, `race`, … (C-only) | none | `default` | eligible (unchanged) |
| `fbneo`, `snes9x`, `nestopia`, `uzem`, `mednafen_pcfx`, `mednafen_supafaust` | 3.4.29–3.4.32 | `static-libstdcxx-v0` | **now eligible** |
| `gearboy`, `gearsystem`, `gearcoleco`, `gambatte`, `stella2014` | 3.4.29–3.4.32 | `static-libstdcxx-v0` | **now eligible**; retire `mini-cxx-provider-unverified-v0` |

Alternatively, one Lever-B provider bundle (`libstdc++`@3.4.32 in the Mini
search path) clears **all 11 at once with zero rebuilds** — at the cost of
shipping and vetting one shared library. The two levers compose: bundle where a
shared lib is acceptable, static-link the residual.

## 9. Why this stays a fail-closed win

- Every device-selectable artifact is still individually reproducible +
  contract-proven + promoted; the variant set only *chooses among* them.
- The variant-set manifest is composed and content-hashed like every other
  pin — no hand authoring, mirroring `promote_core.py compose-lifecycle`.
- The screen remains `static-abi-only`; variants inherit the same
  `needs-target-runtime` gate and stay `provisional`/ineligible until a hardware
  smoke result — no new runtime claim is minted.
- A new `missing_evidence` value (`variant-runtime-validation`) makes the
  provisional state explicit and machine-checkable.

## 10. Phased rollout

- **Phase 0 — model, byte-inert.** Land `abi_flavors` schema, `build-core
  --flavor`, the semantic-id flavor segment, and the `default`-only resolver
  path. Zero flavors declared ⇒ every existing hash and test unchanged (the
  overlay-layer playbook).
- **Phase 1 — one core, end to end.** Add `static-libstdcxx-v0` to **gearboy**
  (it already carries the `mini-cxx-provider-unverified-v0` constraint). Build +
  prove + promote the flavor; compose the Mini variant set; show gearboy move
  `over_ceiling → eligible(static)`. One reviewable vertical slice.
- **Phase 2 — resolver + variant-set manifests.** Generalize `classify_core`,
  emit `manifests/device-sets/*.json` for Mini/A30/Trimui, update
  `test_device_sets.py` from binary buckets to best-flavor selection.
- **Phase 3 — sweep.** Roll `static-libstdcxx-v0` across `MINI_OVER_CEILING`;
  retire the now-covered `compatibility_constraints`.
- **Phase 4 — Lever B (optional).** Add the Mini `bundled-first-search-path-provider`
  observation with a real `sha256`; once `enforcing:true`, the resolver prefers
  the smaller `default` artifact over static where the bundle covers it.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Combinatorial build growth (cores × flavors × arches) | Build a flavor **only** for cores that need it, **only** on the constrained arch (`armhf`); the `candidate_build_flavors`/`accelerated_candidates` scoping already expresses this. |
| Static `libstdc++` size on small storage | Prefer Lever B (one shared lib) where acceptable; static only the residual. |
| C++ ABI across core/frontend boundary | Standard libretro `dlopen` isolation; gate on the existing `needs-target-runtime` smoke, don't claim it statically. |
| Low-ABI toolchain C++17 friction | Keep `glibcxx-3.4.24-v0` a last resort; static-link covers the common case. |
| Divergent behavior between a core's flavors | Both flavors are byte-reproducible and independently proven; a variant set records exactly which pin ships, so drift is auditable. |

## 12. Open questions (human/hardware gates)

1. Runtime smoke: does a `static-libstdcxx` core load + play on a real Mini?
   (Unblocks moving variant sets from `provisional` → eligible.)
2. Storage budget per device — informs the Lever A vs Lever B split.
3. Provider-bundle provenance: which `libstdc++.so.6` do we ship for Mini, and
   from what sysroot, to fill `provider_observations[].sha256` credibly.

## 13. Companion tool — on-device capture

[`scripts/device_probe.sh`](../scripts/device_probe.sh) is the zero-argument,
read-only capture tool that turns the resolver's *uncaptured*/*unverified*
ceilings into real evidence. Run it on the device (locally or
`ssh dev 'sh -s' < scripts/device_probe.sh`); it writes one on-device log and
prints a machine-readable `CAPTURE` block whose `effective_cxx_provider`,
`effective_max_glibcxx`, `effective_max_cxxabi`, `effective_cxx_hash`, and
`dynamic_loader`/`pipeline_target` map straight onto a
`device-runtime-contracts.json` `provider_observations[]` row (with
`enforcing:false` until reviewed). It is busybox/POSIX-safe and reads version
symbols with `strings`, so it needs no `readelf`/`ldd` on the firmware. This
directly retires the `effective-runtime-provider-capture`,
`target-loader-capture`, and (runtime-side) `target-sysroot-capture`
missing-evidence categories, and supplies the credible provider `sha256` that
open question 3 and the Lever-B provider bundle both depend on.

**v3 (2026-07-22) — beyond the libstdc++ ceiling.** The resolver's ceiling math
only ever asked one question: is the device's `libstdc++` new enough? That was
sufficient while every core's needs were a subset of libc/libstdc++, and it
stopped being sufficient with `parallel_n64`, the first core whose artifact
links a graphics library outright (`libGLESv2.so.2` in `DT_NEEDED`). v3 adds
three evidence classes so the eligibility join has something real to read:

1. **Loader-truth resolution** (`capture.cores_scanned` /
   `cores_resolvable` / `cores_unresolvable` / `missing_sonames`). For every
   installed core, the device's *own* dynamic loader resolves the dependency
   graph via `LD_TRACE_LOADED_OBJECTS` — the same mechanism `ldd` uses, which
   reports without running the object. Only the real loader accounts for the
   actual search path, `ld.so.cache`, symlink farms and vendor blob layouts. A
   core that reports no missing sonames is loadable; one that reports any is
   not, whatever the ceiling math says. Empty loader output is treated as
   **undetermined**, never as success (a foreign-ABI object or firmware without
   `ldd` produces silence), and falls back to a `DT_NEEDED`-vs-search-path
   scan, recorded as `via=dt-needed`. Cores built for the other ABI are
   reported separately as `cores_foreign_abi` rather than resolved.
2. **A soname → provider table** (`lib:` lines, `capture.libs_absent`) over the
   union of libraries the catalog's cores need, with path, ELF target and
   hash — so a *non-versioned* provider can be transcribed into
   `provider_observations[]` the same way the `libstdc++` ceiling already is.
3. **Graphics stack and frontend capability** (`capture.gpu_apis`,
   `gpu_nodes`, `gles2_provider*`, `egl_provider`, `frontend_video_apis`).
   GPU nodes are recorded with readability, not just existence, since a node
   the frontend's user cannot open provides nothing. The frontend's own linked
   video APIs matter more than any single core's: HW render is
   frontend-mediated for every core *except* parallel_n64, so the frontend's
   ability to create a context is what actually gates that whole class.

The probe also harvests the `LD_LIBRARY_PATH` that launcher scripts export
(`launcher-ld-library-path`), because the path a core is loaded with at play
time is not the one the probe inherits over SSH. `PROBE_CORE_DIRS` is an
optional environment override for firmware whose core layout matches none of
the known paths; the tool remains zero-argument by default.

**The join (2026-07-22).** `classify_core` no longer screens on the
`libstdc++` ceiling alone. It runs two independent screens and reports the
most definite outcome first:

1. `missing_provider` — a soname in the core's `DT_NEEDED` that the device's
   probe recorded as **absent**. This outranks every version comparison: no
   ceiling arithmetic matters for a library that is not there.
2. `over_ceiling` — the pre-existing GLIBCXX screen, unchanged.
3. `provider_uncaptured` — a library observed neither present nor absent, or a
   device with no probe at all. Absence of evidence fails closed; it is never
   read as availability.

Definite disqualifications are deliberately reported ahead of uncertainty, so
an unprobed device still surfaces what *is* known about it rather than
collapsing every finding into "uncaptured". The ELF interpreter
(`ld-linux-aarch64.so.1` / `ld-linux-armhf.so.3`) is excluded from the provider
screen: it is implied by the ABI the device runs, not a library it must supply
separately.

**Fleet capture, 2026-07-22.** Seven devices probed (`device-probe-v3`), six
runtime contracts now carrying `library_observations` with
`resolution_method: loader`:

| contract | ABI | GLIBCXX | result |
|---|---|---|---|
| trimui-a133p (Brick + TSP) | arm64 | 3.4.28 | 88/88 eligible |
| trimui-smart-pro-s | arm64 | 3.4.28 | 88/88 eligible |
| miyoo-flip | arm64 | 3.4.32 | 88/88 eligible |
| gkd-pixel2 | arm64 | 3.4.33 | 88/88 eligible |
| miyoo-a30 | armhf | 3.4.32 | 87/87 eligible |
| miyoo-mini-family (Mini Plus) | armhf | 3.4.24 | 66 eligible, 21 over-ceiling |

Every live ceiling matched the value already recorded, which independently
validates the pre-probe `provider_observations`. Brick and TSP agreed
byte-for-byte on every field the manifest tracks, confirming the shared family
entry. Two labels were corrected against live evidence: the Mini's provider is
`bundled-first-search-path-provider` (it is first on the search path at
`/mnt/SDCARD/miyoo/lib`), not the `packaged-fallback-provider` the pre-probe
entry had guessed — same file, `sha256` unchanged.

**The finding that justifies the screen.** The Mini Plus has **no
`libGLESv2.so.2` at all**, and its shipped armhf `flycast` fails to load with
exactly that missing soname. No catalog core is affected yet — `parallel_n64`,
the only one linking GLES directly, is arm64-only — but a GL-linking *armhf*
core would have been called eligible on the Mini by the old ceiling-only
screen and would have failed to load on the device.
`tests/test_device_sets.py` pins this against the Mini's real captured
absent-set.

Probing also found shipped cores that cannot load anywhere: `easyrpg` is broken
on all five arm64 devices (`liblcf.so.0`, `libfluidsynth.so.3`,
`libspeexdsp.so.1`, `libharfbuzz.so.0`), and TSPS — a PowerVR device, unlike
its Mali siblings — cannot load the Mali-built `yabasanshiro` variants.

What the probe still does **not** establish: it resolved the *shipped* cores on
each device, not the artifacts this pipeline builds, so
`target-rootfs-load-validation` and `target-playback-validation` remain in
every contract's `missing_evidence`, `status` stays `provisional`, and
`enforcing` stays `false`.

## 14. CPU tuning — a third, deferred lever (evaluated 2026-07-21)

Levers A/B above are about **coverage** (can a core run: ceiling math). A
separate axis is **performance**: `-mcpu`/`-mfpu`/`-mtune` tuning to a device's
actual core. `device_probe.sh` v2 captures the inputs — `cpu_core`,
`cpu_implementer`/`cpu_part`, and an advisory `suggested_opt_flags` — from
`/proc/cpuinfo` (the reliable identity, since `model name`/`Hardware` are blank
on these SoCs). The eight-device fleet capture resolved to:

| Runtime family | ABI | CPU core | Advisory flags |
|---|---|---|---|
| trimui-a133p (Brick, SmartPro) | arm64 | Cortex-A53 | `-mcpu=cortex-a53` |
| trimui-smart-pro-s (A523) | arm64 | Cortex-A55 | `-mcpu=cortex-a55` |
| miyoo-flip (RK3566) | arm64 | Cortex-A55 | `-mcpu=cortex-a55` |
| gkd-pixel2 (RK3326) | arm64 | Cortex-A35 | `-mcpu=cortex-a35` |
| miyoo-a30 (A33) | armhf | Cortex-A7 | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` |
| miyoo-mini-family (SSD202D) | armhf | Cortex-A7 | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` |

Useful structural finding: **the entire armhf fleet is Cortex-A7.** So if armhf
tuning is ever adopted, a *single* `-mcpu=cortex-a7 -mfpu=neon-vfpv4` shared
armhf build serves every armhf device with **zero fragmentation** — no per-device
flavor needed. arm64 is a mix (A53/A55/A35, all base `armv8-a`); the safe shared
choice there is `-mtune=cortex-a53` (tunes scheduling for the lowest/most-common
core while staying binary-compatible with A55/A35). GPU and RAM were captured too
(`gpu_apis`, `mem_total_kb`): they are **not** gcc inputs — GPU selects a GL
core's *video-backend* flavor (Mini/A30 are GLES2-only; the rest add Vulkan), and
the **~100 MB** Mini RAM is a hard viability gate for heavy cores regardless of
ABI.

**Decision: defer — not appropriate to implement now.** Reasons:
1. Every form of tuning fights the manifest's own
   `portable-shared-default-sparse-family-override-on-evidence` policy. Per-device
   flavors multiply the hash-locked catalog (cores × device targets); retuning the
   shared per-ABI build re-invalidates the compile-argv sha256 of **all** 67
   canonical cores (full re-extract/re-proof/re-promote). Neither is warranted by
   *evidence a core needs it* — the trigger the policy names.
2. Tuning is a pure performance change; nothing is incorrect without it (the
   generic `armv8-a` / `armv7+neon` builds already run everywhere in-ABI).
3. On the mostly-2D interpreter catalog these deltas are marginal; the genuine
   CPU-bound wins are the exotic Tier-4 cores (N64/PSX/DOS/Saturn/heavy DSP),
   which are not yet onboarded and typically already do runtime dynarec/CPU
   detection.

**When it becomes appropriate**, do it as a scoped `candidate_build_flavors`
entry (Lever-A machinery, already present) for a *profiled* CPU-bound shortlist —
or fold `-mcpu=cortex-a7 -mfpu=neon-vfpv4` into the armhf build at the next
wholesale armhf re-promotion, which is the one zero-fragmentation opportunity
(uniform A7 fleet). The per-device `-mcpu` targets above are recorded so that
step is turnkey. The probe already emits everything needed; no further capture
work is required for this axis.
