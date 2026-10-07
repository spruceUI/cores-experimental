# History

Until October 2026 this repository was a provenance pipeline: a track registry
(main, nightly and edge × stable and test × chipset) with compare-and-swap
promotion, campaign and authority stages, a content-addressed evidence store,
per-core build-log contracts and 100 per-core workflows. That was about 210,000
lines of Python and tests generating 190 build scripts.

Its validation depended on a 28 GB local evidence store that was later lost, so
it could no longer check its own catalog, build a release, or run a third of its
tests. Adding a build option meant changing about 100 files, because every
per-core contract pinned its exact compile lines.

The reduction kept the recipes, patches, metadata and toolchain images and
replaced the rest with `scripts/cores.py` and `scripts/corebuild/`. The new
driver runs the same build commands as the old pipeline for 185 of the 190
core/arch pairs; the other five drop lines that only produced log output. To
read the old pipeline, check out the parent of the commit "Remove the
provenance pipeline".

At the time of the reduction (October 2026), 98 of the 100 cores built and
loaded at the `universal` + `release` baseline; the two that did not are the
Flycast candidates. Building every core for every board at `max` gave 568 builds,
of which 558 loaded, 2 were the Rust core (not load-tested) and 8 were the Flycast
candidates.
