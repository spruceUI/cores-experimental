# Waves of cores

cores-experimental tracks four waves of cores, plus everything else it pins. Each wave is one generated manifest in
`manifests/waves/`, written by `scripts/waves.py`. The catalog and `standalone-builds.json` hold the recipes
(how a core builds); a wave says which files it means and which recipe and commit, if any, reproduces each one.

| wave | defined by | manifest |
|---|---|---|
| `pixel2-twiguinext` | a TwigUI-Next release's card (the cores and standalones it writes over spruce's) and the base-image files spruce uses | `waves/pixel2-twiguinext.json` ([details](twigui-next.md)) |
| `spruce-nightly` | the spruceOS `Development` commit a spruce nightly was built from (the newest one audited) | `waves/spruce-nightly.json` |
| `spruce-stable46` | spruceOS `v4.6.0` | `waves/spruce-stable46.json` |
| `edge` | each recipe source's newest release tag (`vN.N…` or `rN`) when its commit is newer than the recipe's pin, else the requested branch's tip | `waves/edge.json` |
| `custom` | the recipes no other wave uses: experiments, variants, candidates | `waves/custom.json` |

## Entries

A file entry (spruce and TwigUI-Next waves) has the file's `sha256` and a `status`:

- spruce waves: the coverage status (`reproduces`, `recipe`, `no recipe`, …, see [inventory](inventory.md)), the
  `recipes` that build the path, the device `families` that load or run it, `spare: true` for a shipped core no
  device loads from that folder, and for a reproduced file its `pin` (recipe, source URL and commit). A
  `not shipped` core entry is a folder a device loads it from where spruce ships nothing;
- `pixel2-twiguinext`: `pinned` (the package and its source pin are recorded), `reproduced` (rebuilt byte for byte,
  `verified` says how) or `near` (rebuilt, with a known difference in `verified`).

A manifest is generated: regenerate it rather than editing it. The hand-kept facts of an entry (`pin`, `evidence`,
`verified`) carry over to the next run while the entry's sha256 stays the same.

## Regenerate

```
python3 scripts/waves.py spruce spruce-nightly --spruceos <spruceOS> --nightly latest   # or --rev <commit>
python3 scripts/waves.py spruce spruce-stable46 --spruceos <spruceOS> --rev v4.6.0
python3 scripts/waves.py twigui pixel2-twiguinext ...        # docs/twigui-next.md
python3 scripts/waves.py edge                                # git ls-remote per source, GitHub API for dates
python3 scripts/waves.py custom                              # after the others
python3 scripts/waves.py summary
```

`waves.py summary` prints each wave's counts. `recipe` counts the files a recipe builds but does not reproduce
yet. A wave's history is its manifest's git log: `git log -p -- manifests/waves/spruce-nightly.json`.

## Nightly audit

The spruce waves are the audit of what spruce ships. A spruce wave's `records` section checks every `shipped`
record (a catalog core's or a standalone recipe's) against the tree: does that spruceOS commit ship the bytes
the record names, at the record's card paths? A file missing from the tree is also looked for in its system
folder's `.7z` files, where spruce packs ScummVM.

| record status | meaning |
|---|---|
| `match` | every file the record names ships with those bytes |
| `partial` | some do; `differ` lists the others (`other bytes` or `absent`), `by` the records that match there |
| `replaced` | none do, and another record matches at its paths (`by`) |
| `not shipped` | none do, and no other record matches there |
| `retired` | every file is in the record's `shipped.retired`: spruce removed them, and the record stays as history |
| `elsewhere` | the record is of a package outside spruceOS (`shipped.source`, no `spruceos`), such as Game Nursery's FreeJ2ME |

Files in `shipped.retired` (`{file: "spruceOS <commit>: why"}`) are left out of the check, and a record's
`retired` gives their count.

For each new nightly:

```
git -C <spruceOS> fetch origin
python3 scripts/waves.py spruce spruce-nightly --spruceos <spruceOS> --nightly latest   # or --nightly <tag>
python3 scripts/waves.py diff spruce-nightly        # what changed since the committed manifest
python3 scripts/waves.py custom
git commit -m "spruce-nightly: nightly <tag>" -- manifests/waves/   # the diff's lines as the body
```

`--nightly` reads the Development commit from the nightly's `create-nightly` run log ("Release tag for this run",
"Current Development commit") and records the tag, run and time in `defined_by.nightly`. The release notes name
the commit too, but old releases are deleted, and spruceOSNightlies' tags all point at one README commit.

This replaced `AUDIT.md` (kept, frozen at v4.5.5-20261018). It covers every shipped core and every recipe with
a `shipped` record, not only 30 recipes. It does not repeat AUDIT.md's check of each published OTA package
against the tree, which tests spruce's packaging rather than these recipes, nor its `moved` status (recorded
bytes at another path): such a record shows as `not shipped`.

## Notes

- The spruce waves come from the emulator inventory, which follows spruce's emulator menus and the folder each
  device loads from. Every shipped core is in them, spare or not, so a recipe that builds a spare file is not
  `custom`; apps such as vTree are in no wave, so their recipes are. At d7ce3dc52, spruce-nightly has 44 spare
  cores (43 that no menu offers, plus `cores64/mupen64plus`: N64 offers `mupen64plus` only on 32-bit lists), and 7
  folder gaps: `cores/` flycast2021 and flycast2024 (the 32-bit RA Build on the Flip, the XX and dArkMoss), the
  Mini's puae, km_puae_xtreme_amped and km_mame2003_xtreme, and freej2me_plus in both folders. At fbe86ef2b
  (2026-11-21) 42 are spare: spruce's new PC-FX system offers both `mednafen_pcfx` cores.
- A core without a reproducing recipe carries a hand-kept `pin` (`confidence`: `unambiguous`, `likely` or
  `ambiguous`; `verified`) and its `evidence`. A build at the pin that matches makes it `reproduces`. On 11-19
  spruce-nightly had 49 such GCC 9.4 cores, 37 of them from spruceOS 327c258ee (built 2025-05-05/06). Nine pins
  are left: bluemsx, px68k (verified code, build ID differs) and km_ludicrousn64_2k22_xtreme_amped of
  cobaltgit's builds, the two Flycast-campaign cores, armsnes (`likely`), and the three vendor files below.
- The 2025-05-06 batch (41 cores) was cobaltgit's local libretro-super build, at `/root/libretro-super`, with
  Ubuntu's GCC 9.4 and exported `-mcpu=cortex-a53 -fomit-frame-pointer`, plus `-ffast-math` for some cores.
  Their short hashes are 8 characters in big repos (full clones), and vice and puae2021 embed their build time.
  At those flags (flag fan-out rounds 1-4, 11-19/20), eight cores have spruce's code and data sections. Such an
  entry's `verified` says so, and its status stays `recipe`. CE's catalog recipes keep their portable flags.
- The build was native: GNU ld's build ID covers `.strtab`'s size, and the native linker's `crti.o`/`crtn.o` paths are
  20 characters shorter than the cross ones. With CFLAGS/CXXFLAGS `-mcpu=cortex-a53 -fomit-frame-pointer
  -ffast-math` exported, which a Makefile adds to compiles but rarely to the link (so `crtfastmath.o` stays out),
  and a wrapper that adds `-B` pointing at the native paths, CE's cross toolchain reproduces 22 cores byte for byte
  (round 7). Their `<core>-arm64-20250506` recipes extend `batch1-arm64-20250506`, which carries that build; six more
  (a5200, nestopia, prosystem, quicknes, snes9x, tyrquake) match with the Makefiles' own `" <hash>"` version strings
  and tyrquake's embedded build time, 28 in all. crocods (29) links its sources in the builder filesystem's
  `$(wildcard)` order, recovered from spruce's file (function sizes place code objects, data offsets and a linker map
  the data-only ones, `.dynstr` the rest) and listed explicitly by a patch; genesis_plus_gx and mednafen_supergrafx
  (31) the same way. chailove (32) is C++, where an inline function stays in whichever object links first: its order
  came from simulating ld's placement (cold, startup, then main code), checked on CE's own build and linker map, until
  the function sizes equalled spruce's; fbneo and fbalpha2012 (35) the same way. px68k differs
  only in its build ID (round 7), so its pin is recorded as verified code and its recipe lists the build ID in
  `shipped.differs`. vice_xvic (33) was built after vice_x64 in the same tree with libretro-super's clean skipped
  (`NOCLEAN=1`), so x64's stale objects link in; its recipe repeats both builds.
- Files that Cores-spruce workflows built are reproduced by standalone recipes in CE's copies of its images
  (`cores-spruce-arm64`, `cores-spruce-armhf`), repeating the run's commands. Two traps: CE's build script clears
  the image's `CMAKE_TOOLCHAIN_FILE`, which CMake cores need back; and a workflow that builds a runner-owned
  checkout as root gets no git hash (git refuses the checkout), which `chown -R 1001:1001 <source>` reproduces.
- The nightly files that had no recipe (traced with the Emu Inventory session on 11-19 and 11-20) carry their
  provenance as `evidence` (and a source `pin` where one is known). These now reproduce byte for byte: `OpenBOR_mod`
  and `OpenBOR_new` (steward-fu's A30 ports), advmame and `OpenBOR_64_mod` (wakeboxer's CI builds, in their builder
  images), and `cores64/uae4arm` (Lakka v4.x's RPi3-Composite build, rebuilt with Lakka's own build system). Three
  are vendor binaries whose toolchain is not published, so they stay `no recipe`: Miyoo's `OpenBOR_Flip` and A30
  `cores/mupen64plus`, and TrimUI's `cores64/mupen64plus` (spare).
- Parked, recipe kept: mkxp-z (PR #255's CI) has the same code and ZIPs, but a 6 MB binary blob in `.rodata`
  (after the Theora decoder's strings, no archive or wasm signature) differs almost throughout (consistent
  with a heap snapshot taken at build time; unconfirmed). GameTank's arm64 core reproduces since 11-21 (outline atomics came from the
  image's aarch64 gcc-cross, which clang in zig detects).
- The 15 third-party core files with a catalog recipe that does not reproduce them carry their provenance too
  (Flycast campaign builds, christianhaitian and Onion prebuilts, KMFDManic's builds, private LLVM builds). One is a
  risk on the device: `cores64/np2kai_libretro.so` needs `GLIBC_2.34`, above the TrimUI devices' 2.33.
- DSperate v3.4.0 reproduces on both builds of 504e78012: the A30 build at the v3.4.0 tag, and the aarch64 build
  at 109ecfd5 with upstream's PGO profile, in `standalone-dsperate-v2` ([standalone](standalone.md#status)).
- DSperate v4.0.1 (c6e34cf9e) reproduces on both builds too. The aarch64 one needs the wrapper's ccache history: three
  earlier PGO builds whose objects focal's ccache reused under the new profile ([standalone](standalone.md#status)).
  armNES v1.5 (4497d1d58) is Cores-spruce's build of main f88b792d, two commits after the tag (Thumb-2 on ARMv7):
  the catalog's `armnes` at that commit matches both builds.
- The spare `armnes_arcade` (3345ffa1d, Cores-spruce's per-core run at the v1.4.1 tag) matches the catalog's recipe at
  that tag, both builds. evolver79's `gamate` core (0d619dc59, MIT with BSD-3-Clause MAME parts) reproduces in
  Cores-spruce's images (`gamate-*-20261124`).
