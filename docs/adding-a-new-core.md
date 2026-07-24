# Adding a new core build to the pipeline

This is the end-to-end runbook for onboarding one libretro core into the
fail-closed, hash-locked catalog: from an uncataloged (fail-open) workflow to a
canonical core whose exact compile/link argv is proven by sha256, promoted with
a reproducible build golden, and gated by the full test suite.

It complements two narrower docs:

- [`core-pipeline-architecture.md`](core-pipeline-architecture.md) — *"Add an
  individual core contract"* covers the contract module's internal layering.
- [`core-pipeline-cli-reference.md`](core-pipeline-cli-reference.md) — the exact
  flags for every `core_pipeline.py` / `promote_core.py` subcommand used below.

Work **one core at a time, one atomic commit per core.** Never add a core to the
catalog while a full test suite is running, and never edit a pipeline source
file *between* a core's `sim` and `local` builds (it changes the recipe hash and
the two builds will not reconcile).

---

## 0. Prerequisites

- The pinned Docker toolchain images are loaded: `cores-arm64` and `cores-armhf`
  (they carry libretro-super at `/libretro-super`, with the per-core recipe in
  `/libretro-super/rules.d/core-rules.sh`).
- The shipped baseline tree is checked out at `../spruceOS` (used by
  `import-golden` as the artifact-only starting point).
- You are in a clean working tree on a work branch.

Confirm the core is currently an uncataloged fail-open workflow:

```bash
python3 scripts/core_pipeline.py audit-workflows | grep -A99 unmigrated_workflows
```

## The recipe at a glance

1. Pin the source identity (repo, ref, commit, tree; canonical URL casing).
2. Add the catalog entry + compose the source lock.
3. Swap the fail-open workflow for the fail-closed dispatcher.
4. Exploratory build → **classify** the core (pick the proof engine).
5. Extract the exact constants (counts + sha256 set) from the build log.
6. Author the contract module.
7. Wire it in (registry + 3 points in `core_pipeline.py`).
8. Build `sim` + `local` (identical pipeline state).
9. Verify reproducibility (add `source_date_epoch` if it embeds a timestamp).
10. Run the promote chain (golden → pin-set → lifecycle).
11. Check device eligibility (`MINI_OVER_CEILING`).
12. Update the count tests; run focused tests, then the full suite.
13. Commit atomically.

---

## 1. Pin the source identity

Read the libretro-super rule to learn the real repository and any post-fetch
step (a branch checkout or a make target is applied here, not in the workflow):

```bash
docker run --rm cores-arm64 bash -c 'grep -nE "<core>" /libretro-super/rules.d/core-rules.sh'
# libretro_<core>_git_url        -> the real repo (may be shared, e.g. libretro-uae)
# libretro_<core>_post_fetch_cmd -> e.g. "git checkout 2.6.1" (a branch pin — see puae2021)
# libretro_<core>_build_makefile / _git_submodules
```

Resolve the pin against the ref that libretro-super uses (usually the default
branch, or the `post_fetch_cmd` branch):

```bash
BR=$(gh api repos/libretro/<repo> --jq .default_branch)          # or the post_fetch branch
gh api repos/libretro/<repo> --jq .full_name                     # CANONICAL casing — see gotcha
COMMIT=$(git ls-remote https://github.com/libretro/<repo>.git refs/heads/$BR | cut -f1)
gh api repos/libretro/<repo>/commits/$COMMIT --jq '.commit.tree.sha, .commit.committer.date'
```

> **Gotcha — URL casing.** GitHub canonicalizes repo names. A lowercase pin
> clones fine but `promote` later fails `pinned and resolved source URLs
> differ`. Pin the exact `full_name` casing (e.g. `libretro/REminiscence.git`,
> `libretro/Mu.git`).

## 2. Catalog entry + source lock

Append the entry to `manifests/core-builds.json` (catalog is append-ordered, not
alphabetical). Standard libretro-super shape:

```json
"<core>": {
  "workflow": ".github/workflows/build-<core>.yml",
  "source": {
    "url": "https://github.com/libretro/<repo>.git",
    "requested_ref": "refs/heads/<branch>",
    "commit": "<40-hex>",
    "tree": "<40-hex>"
  },
  "build": {
    "driver": "libretro-super",
    "source_key": "<core>",
    "source_dir": "libretro-<core>",
    "output_path": "dist/unix/<core>_libretro.so",
    "artifact_name": "<core>_libretro.so"
  },
  "metadata": {
    "source_path": "/libretro-super/dist/info/<core>_libretro.info",
    "artifact_name": "<core>_libretro.info"
  },
  "targets": ["arm64", "armhf"]
}
```

Then compose the immutable source lock:

```bash
python3 scripts/promote_core.py compose-source-lock --core <core>
```

`catalog-check` will now fail with *"catalog cores lack compatibility or pending
state"* — expected; the compatibility manifest is written by the promote chain
(step 10). Do not hand-write it.

### Special catalog shapes

- **Single-ABI** (e.g. `uae4arm` armhf-only — arm64 fails to assemble armv7 asm):
  set `"targets": ["armhf"]` (or `["arm64"]`). The compatibility-matrix bridge
  test admits `{arm64,armhf}`, `{arm64}`, and `{armhf}`.
- **Branch-pin variant** (e.g. `puae2021` = `libretro-uae` @ `2.6.1`): the branch
  is carried entirely by `requested_ref`/`commit`/`tree`; libretro-super applies
  the `post_fetch_cmd` checkout automatically. No special pipeline handling.
- **direct-cmake** (e.g. `arduous`, `swanstation`): catalog-driven only, NO
  contract module. Set `driver: "direct-cmake"`, `source_dir == core_id`,
  `output_path == artifact_name`, add a `cmake` block (`generator`, `build_type`,
  `target`, `systems.<arch>`) and `source_date_epoch`. Skip steps 5–7.

## 3. Swap the workflow

Replace the fail-open workflow (it contains `|| echo "::warning::...build
failed"` and `gh release` publish steps) with the fail-closed dispatcher by
copying an onboarded sibling of the same ABI shape:

```bash
sed 's/opera/<core>/g' .github/workflows/build-opera.yml > .github/workflows/build-<core>.yml
# verify: name, --core <core>, no 'opera' leftovers, no 'core_ref', no '|| echo', contents: read
```

The focused workflow test asserts `permissions:\n  contents: read`,
`--runner-profile github-actions`, `--core <core>`, and the absence of
`core_ref`, `gh release create/upload`, `|| echo`, `contents: write`.

## 4. Exploratory build → classify

```bash
python3 scripts/core_pipeline.py build-core --runner-profile local --core <core> --run-id <core>-explore-v1
```

Classify from `.local-e2e/runs/<core>-explore-v1/<core>/<arch>/build.log`:

| Signal in the log | Engine | Example |
|---|---|---|
| all `gcc … -c`, linked by `gcc` | `c_only` | opera, puae2021 |
| `gcc` **and** `g++` compiles, linked by `g++` | `mixed_language` (`expected_link_language="cxx"`) | gme, uae4arm |
| all-C but linked by `g++` | `mixed_language` (`"cxx"`) | x1 |
| C++ objects but linked by `gcc` (libstdc++-free) | `mixed_language` (`expected_link_language="c"`) | mu |
| `.S`/`.s` assembly compiles present | `c_asm` | gpsp, pcsx_rearmed |
| `[NN%] Building CXX object …` (silent CMake) | `direct_cmake` (catalog-only) | arduous |
| `ar rc* lib*.a …` then link references the `.a` | `c_only` **archive mode** | lutro |

Beware false positives: `CXX = …-g++` lines in the Makefile preamble are
variable declarations, not compiles — count only lines with ` -c ` compiling a
`.c`/`.cpp`.

## 5. Extract the exact constants

Reuse the engine's own parser to compute the constants (never hand-hash). Import
`c_only` / `mixed_language`, replay the same tokenization the proof uses, and
print the counts and sha256 sets per arch. The values you need:

- `expected_compile_count`, `expected_language_counts` (mixed).
- `expected_compile_pair_sha256` (arch-invariant), and
  `expected_compile_invocation_sha256` **per arch** (compiler name differs).
- `expected_link_object_sha256`, and `expected_raw_link_object_sha256` when the
  raw operands differ from the normalized ones (i.e. when an alias is in play).
- `expected_link_options` (multiset; order not enforced but store it readably).
- For archive mode: `expected_archive_member_sha256`,
  `expected_archive_names`.

> **Gotcha — `semantic_path_aliases`.** The engine requires each compiled
> object's stem to equal its source stem and the link objects to equal the
> compile objects. When the Makefile writes objects under a prefix
> (`build/./<x>.o`, `obj/player/<x>.o`), links into a subdir
> (`obj/player/<artifact>.so`), or uses an absolute OBJDIR
> (`/libretro-super/…/source/<x>.o`), add ONE reviewed prefix alias to strip it.
> `semantic_log_path` applies the alias first, then drops a single leading `./`,
> then enforces containment — so e.g. `(("obj/player/", ""),)` normalizes both
> `obj/player/./x.o → x.o` and `obj/player/artifact.so → artifact.so`.

Confirm the extracted contract proves BOTH arch logs before wiring anything.

## 6. Author the contract module

Copy the closest sibling under `scripts/core_pipeline_lib/contracts/` (opera for
`c_only`, gme/uae4arm for `mixed_language`, gpsp for `c_asm`, lutro for archive
mode). Fill in `<CORE>_SPEC_IDENTITY`, `<core>_spec_is_well_formed` (must equal
the catalog entry exactly, including `source_date_epoch` if present), the
extracted constants, the `…LogContract`, and `<core>_log_proves_contract`. Keep
the module's identity and proof in its own file — see the architecture doc's
*"Add an individual core contract"* for the layering rules.

## 7. Wire it in

One edit — `core_pipeline.py` needs no changes at all:

1. `contracts/registry.py` — one `CoreLogContract(contract_id=…,
   core_ids=frozenset({"<core>"}), proof_name="<core>_log_proves_contract",
   proof_kind="core-arch-source", failure_message=…)`.

Everything else is discovered from the contract module itself: declare
`SPEC_GUARD_MESSAGE = "the <core> core must preserve its exact …"` beside the
validator, and the guard registry binds `<CORE>_CORE_ID` +
`<core>_spec_is_well_formed` + that message automatically; the proof registry
binds `<core>_log_proves_contract` by its registry name. An unbound registry
entry fails closed at import, so a typo in the proof name cannot slip through.

## 8. Build sim + local

All pipeline edits must be finished before this step. Build both profiles with
the canonical run-ids:

```bash
python3 scripts/core_pipeline.py build-core --runner-profile github-actions-sim --core <core> --run-id actions-sim-build-core-<core>-v1
python3 scripts/core_pipeline.py build-core --runner-profile local            --core <core> --run-id build-core-<core>-local-v1
```

## 9. Reproducibility

Compare the two artifacts per arch:

```bash
sha256sum .local-e2e/runs/actions-sim-build-core-<core>-v1/<core>/*/<core>_libretro.so
sha256sum .local-e2e/runs/build-core-<core>-local-v1/<core>/*/<core>_libretro.so
```

If they differ (usually a small ~20-byte build-id region), the source embeds
`__DATE__`/`__TIME__`. Add `source_date_epoch` = the commit's **committer** date
epoch to the catalog `build` block AND to the contract's spec identity, then
**rebuild both** profiles:

```bash
gh api repos/libretro/<repo>/commits/<commit> --jq .commit.committer.date   # -> epoch
```

`source_date_epoch` is an env var; it does not change the compile argv, so the
extracted sha256 constants stay valid.

## 10. Promote chain

One command sequences the whole chain (import-golden through compose-lifecycle,
then catalog-check), for any target set the catalog declares:

```bash
python3 scripts/promote_core.py run --core <core> \
  --selected-run actions-sim-build-core-<core>-v1 \
  --reproduction-run build-core-<core>-local-v1
```

Pass `--refresh` to re-promote an already-promoted core (retires the previous
source-set, pin-set, and compatibility manifest first) and `--caveat` for any
core-specific caveat. The individual subcommands below remain available when a
step needs to be run in isolation:

```bash
SEL=actions-sim-build-core-<core>-v1
CAND=.local-e2e/nightlies/<core>-candidate-01/golden.json
mkdir -p "$(dirname "$CAND")"

python3 scripts/core_pipeline.py import-golden --core <core> --spruceos ../spruceOS --output "$CAND"
for arch in arm64 armhf; do
  python3 scripts/core_pipeline.py promote --golden "$CAND" \
    --record .local-e2e/runs/$SEL/<core>/$arch/build-record.json \
    --e2e-record .local-e2e/runs/$SEL/e2e-record.json
done
SID=$(python3 scripts/core_pipeline.py derive-core-id --core <core> --source-golden "$CAND" \
      | python3 -c "import json,sys; print(json.load(sys.stdin)['semantic_id'])")

mkdir -p .local-e2e/nightlies/$SID
python3 scripts/core_pipeline.py compose-core-golden --core <core> --source-golden "$CAND" --output .local-e2e/nightlies/$SID/golden.json
python3 scripts/core_pipeline.py validate-golden     --golden .local-e2e/nightlies/$SID/golden.json --verify-store
python3 scripts/core_pipeline.py compose-pin-set --pin-id $SID --core <core> --source-golden .local-e2e/nightlies/$SID/golden.json --output pins/core-sets/$SID.json
python3 scripts/core_pipeline.py validate-pin-set --pin-set pins/core-sets/$SID.json --verify-store --verify-sources
python3 scripts/promote_core.py compose-lifecycle --core <core> --semantic-id $SID \
  --selected-run $SEL --reproduction-run build-core-<core>-local-v1
```

`compose-lifecycle` writes `pins/source-sets/$SID.json` and
`manifests/compatibility/<core>.json`. `catalog-check` should now pass.

## 11. Device eligibility

Read the compatibility manifest's `version_requirements`. If any ABI's needed
set includes `libstdc++.so.6` with `GLIBCXX` above the Miyoo Mini ceiling
(`GLIBCXX_3.4.24`, armhf), add the core to `MINI_OVER_CEILING` in
`tests/test_device_sets.py`. Pure-C cores (no libstdc++) are fleet-wide eligible
and stay out of that set.

### Extracting the constants

Run the real engine parsers over the exploratory log and paste the result:

```bash
python3 scripts/extract_contract.py --core <core> --run-id explore-<core> \
    --engine c_asm   # or c_only / mixed_language
```

`rejected_compiles` must be 0 and `objects_match_compiles` true before the
constants are trustworthy; a nonzero reject count means the engine needs one of
its opt-in relaxations (see the gotchas table), not a transcription workaround.

## 12. Tests

Add `tests/cores/test_<core>.py` (copy a sibling): catalog identity, the
`spec_is_well_formed` load-bearing field, the read-only workflow, the promoted
compatibility, `*_log_proves_contract` over the real run logs, and at least one
negative control (tamper a count / member sha).

Then bump the counts that shift by exactly one onboarded core — all in ONE
file, `tests/expected_counts.py` (the scoreboard literals live only there):

- `tests/test_core_contract_registry.py` — add `"<core>"` to the id set, bump
  `len(CORE_LOG_CONTRACTS)`, add the `(contract_id, proof_name)` mapping entry.
- `tests/test_core_pipeline.py` — add `"<core>"` to the canonical id list and
  bump the `audit_workflows` counts: `catalog_core_count`,
  `catalog_workflow_count`, `shared_pipeline_workflows` (+1);
  `uncataloged`/`unmigrated` (−1); `masked_build_failure_paths` and
  `info_only_risk_workflows` (−1 per removed `|| echo` / info-only path — read
  the real values from `audit-workflows`).
- `tests/test_full_release_repository.py` — the `uncataloged=/nonshared=`
  summary string (−1).

Run focused, then the full suite:

```bash
python3 -m pytest tests/cores/test_<core>.py tests/test_core_contract_registry.py \
  tests/test_core_pipeline.py tests/test_full_release_repository.py tests/test_device_sets.py -q
python3 -m pytest tests/ -q -p no:cacheprovider
```

## 13. Commit

One atomic commit: the workflow, catalog, contract module, wiring, the new
pins/compatibility/source-set, and the test updates. State the engine, the
compile/link shape, reproducibility shas, the SID, and the count deltas.

---

## Appendix — gotchas catalog

| Symptom | Cause | Fix |
|---|---|---|
| `pinned and resolved source URLs differ` | lowercase repo pin | pin GitHub's `full_name` casing |
| artifact sha differs sim vs local (~20 bytes) | `__DATE__`/`__TIME__` in source | `source_date_epoch` = committer-date epoch |
| compile parse fails, object has a prefix | `build/./x.o` vs source `x.c` | `semantic_path_aliases` stripping the prefix |
| link-output guard rejects a subdir output | `obj/<plat>/<artifact>.so` | alias mapping the subdir to `""` |
| `link objects != compile objects` | in-tree `ar` static archive | `c_only` archive mode (member sha + names) |
| arm64 build fails assembling armv7 asm | ARM-optimized core | single-ABI `armhf` only |
| CMake pulls SDL/GL/X11 desktop build | libretro-only flags missing | needs `-D` flags / deferred (see ardens) |
| `ar` line rejected by lexical-safety gate | trailing tab before `# comment` | strip the command after dropping the comment |

## Appendix — the terminal migration step

The historical-envelope oracle and the entire legacy-tranche cohort
(`tests/legacy_tranches/`, `tests/fixtures/legacy-tranches/`, the aggregate
`golden-start` composer, and the mgba golden-start bridge) were retired on
2026-07-23; `freeintv`, `mgba`, and `vemulator` keep their active envelope
proofs, and reviewed per-core oracle fixtures moved to
`tests/fixtures/per-core-oracles/`.
See [`fail-open-workflow-migration.md`](fail-open-workflow-migration.md).
