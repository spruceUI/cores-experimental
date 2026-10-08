"""Unit tests for the build driver; run with `python3 -m unittest discover tests`."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from corebuild import build, recipe, release, standalone  # noqa: E402
from corebuild.catalog import Repo, known_good  # noqa: E402
from corebuild.variants import parse_flags, plan  # noqa: E402

REPO = Repo()


def builds(core, boards, profiles, flags=(), arch=None, runtimes=("shared",), strip=False):
    return plan(REPO.cores[core], REPO.boards, REPO.profiles, boards, profiles, flags, arch, runtimes, strip)


class CatalogTest(unittest.TestCase):
    def test_repository_is_consistent(self):
        self.assertEqual(REPO.check(), [])

    def test_every_core_renders_for_every_target(self):
        for core, spec in REPO.cores.items():
            for arch in spec["targets"]:
                with self.subTest(core=core, arch=arch):
                    script = recipe.render(core, spec, arch)
                    self.assertIn(f"/output/{spec['build']['artifact_name']}", script.text)
                    for host, _ in script.mounts:
                        self.assertTrue((ROOT / host).is_file(), host)

    def test_selection_rejects_unknown_names(self):
        with self.assertRaises(ValueError):
            REPO.select("np2kai nosuchcore")
        self.assertEqual(REPO.select("all"), sorted(REPO.cores))


class PlanTest(unittest.TestCase):
    def test_boards_with_identical_flags_share_a_build(self):
        variants = builds("np2kai", ["a523", "rk3566", "a33", "ssd202d"], ["max"])
        self.assertEqual(sorted((v.name, v.boards) for v in variants), [
            ("max-arm64-cortex-a55", ("a523", "rk3566")),
            ("max-armhf-cortex-a7-neon-vfpv4", ("a33", "ssd202d")),
        ])

    def test_universal_builds_every_target_and_boards_only_their_arch(self):
        self.assertEqual({v.arch for v in builds("np2kai", ["universal"], ["release"])}, {"arm64", "armhf"})
        self.assertEqual({v.arch for v in builds("np2kai", ["universal"], ["release"], arch="armhf")}, {"armhf"})
        arm64_only = next(c for c, s in REPO.cores.items() if s["targets"] == ["arm64"])
        self.assertEqual(builds(arm64_only, ["a33"], ["max"]), [])

    def test_baseline_is_the_catalog_build(self):
        (variant,) = builds("np2kai", ["universal"], ["release"], arch="arm64")
        self.assertTrue(variant.is_baseline)
        self.assertNotIn("cores-variant", recipe.render("np2kai", REPO.cores["np2kai"], "arm64", variant).text)

    def test_cargo_cores_take_profiles_but_not_board_flags(self):
        variants = builds("libgametank", ["a133p", "universal"], ["debug"], arch="arm64")
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].flags, ())
        self.assertEqual(dict(variants[0].cargo), {"opt-level": "0", "debug": "true"})

    def test_extra_flags_are_validated_and_named(self):
        self.assertEqual(parse_flags("-O2 -fno-plt -DFOO=1"), ("-O2", "-fno-plt", "-DFOO=1"))
        for bad in ("-specs=/x", "--sysroot=/", "-I/tmp", "-O3;id", "-fplugin=../x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_flags(bad)
        (variant,) = builds("np2kai", ["a133p"], ["max"], ("-fno-plt",))
        self.assertRegex(variant.name, r"^max-arm64-cortex-a53-x[0-9a-f]{8}$")
        self.assertEqual(variant.flags, ("-mcpu=cortex-a53", "-O3", "-fno-plt"))

    def test_runtime_and_strip_make_named_builds(self):
        shared, static = builds("np2kai", ["universal"], ["release"], arch="armhf",
                                runtimes=("shared", "static"), strip=True)
        self.assertEqual((shared.name, static.name),
                         ("release-armhf-generic-stripped", "release-armhf-generic-static-stripped"))
        self.assertEqual(shared.flags, ())
        self.assertEqual(static.flags, ("-static-libstdc++", "-static-libgcc", "-Wl,--exclude-libs,ALL"))
        # Rust links its std statically anyway, so the runtime choice makes one build.
        (rust,) = builds("libgametank", ["universal"], ["release"], arch="arm64",
                         runtimes=("shared", "static"), strip=True)
        self.assertEqual((rust.name, rust.boards), ("release-arm64-generic-stripped", ("universal",)))


class RecipeTest(unittest.TestCase):
    def render(self, core, arch, boards=("universal",), profiles=("release",)):
        (variant,) = [v for v in builds(core, list(boards), list(profiles)) if v.arch == arch]
        return recipe.render(core, REPO.cores[core], arch, variant).text

    def test_variant_flags_are_appended_last_by_the_wrapper(self):
        text = self.render("np2kai", "arm64", ["a133p"], ["max"])
        self.assertLess(text.index('export PATH="/tmp/cores-variant:$PATH"'), text.index("./libretro-build.sh"))
        work = Path(tempfile.mkdtemp())
        compiler = work / "cc"
        compiler.write_text('#!/bin/sh\necho "$@"\n')
        compiler.chmod(0o755)
        body = text.split("<<'CORES_WRAPPER'\n", 1)[1].split("\nCORES_WRAPPER\n", 1)[0]
        wrapper = work / "wrapper"
        wrapper.write_text(body.replace("@REAL@", str(compiler))
                           .replace("/output/variant-calls.log", str(work / "calls.log")) + "\n")
        run = lambda *args: subprocess.run(["sh", str(wrapper), *args], capture_output=True, text=True).stdout.split()
        self.assertEqual(run("-c", "a.c", "-O2"), ["-c", "a.c", "-O2", "-mcpu=cortex-a53", "-O3"])
        # max never lowers a compile that already uses -Ofast; the board flags still apply.
        self.assertEqual(run("-c", "b.c", "-Ofast"), ["-c", "b.c", "-Ofast", "-mcpu=cortex-a53"])
        self.assertEqual((work / "calls.log").read_text().splitlines(), ["-c a.c -O2", "-c b.c -Ofast"])

    def test_static_runtime_survives_the_ofast_skip(self):
        (variant,) = builds("np2kai", ["a133p"], ["max"], runtimes=("static",))
        text = recipe.render("np2kai", REPO.cores["np2kai"], "arm64", variant).text
        self.assertIn('exec @REAL@ "$@" -mcpu=cortex-a53 -static-libstdc++ -static-libgcc -Wl,--exclude-libs,ALL ;;', text)

    def test_strip_runs_before_the_load_test(self):
        (variant,) = builds("np2kai", ["universal"], ["release"], arch="arm64", strip=True)
        text = recipe.render("np2kai", REPO.cores["np2kai"], "arm64", variant).text
        self.assertNotIn("cores-variant", text)
        self.assertLess(text.index('"$STRIP" --strip-unneeded /output/np2kai_libretro.so'), text.index("/tmp/smoke-loader"))
        (rust,) = builds("libgametank", ["universal"], ["release"], arch="arm64", strip=True)
        self.assertIn("export CARGO_PROFILE_RELEASE_STRIP=symbols",
                      recipe.render("libgametank", REPO.cores["libgametank"], "arm64", rust).text)

    def test_cargo_profile_is_set_through_cargo(self):
        text = self.render("libgametank", "arm64", profiles=["debug"])
        self.assertIn("export CARGO_PROFILE_RELEASE_OPT_LEVEL=0", text)
        self.assertNotIn("smoke", text)

    def test_commit_derived_values_follow_the_pinned_commit(self):
        self.assertIn("""export MAKEFLAGS='-- GIT_VERSION="\\ 9d3bcf2"'""", self.render("atari800", "arm64"))
        self.assertIn("export GIT_REVISION=-f0d4a011", self.render("picodrive", "arm64"))
        self.assertIn('export SOURCE_DATE_EPOCH="$(git -C libretro-fbneo show -s --format=%ct HEAD)"',
                      self.render("fbneo", "arm64"))

    def test_git_abbrev_pins_the_short_hash_length(self):
        text = self.render("hatari", "arm64")
        self.assertIn("export GIT_CONFIG_PARAMETERS=\"'core.abbrev=8'\"", text)
        self.assertLess(text.index("GIT_CONFIG_PARAMETERS"), text.index("./libretro-build.sh hatari"))

    def test_neon_switches_apply_only_to_neon_armhf_builds(self):
        self.assertIn("NOSSE=1 HAVE_NEON=1 CC=", self.render("km_parallel_n64_xtreme_amped_turbo", "armhf", ["a33"], ["max"]))
        self.assertNotIn("HAVE_NEON", self.render("km_parallel_n64_xtreme_amped_turbo", "armhf"))

    def test_neon_switches_reach_each_driver(self):
        (neon,) = builds("np2kai", ["a33"], ["release"])
        def render(core, entries):
            spec = json.loads(json.dumps(REPO.cores[core]))
            spec["build"]["neon"] = entries
            return recipe.render(core, spec, "armhf", neon).text
        self.assertIn("export MAKEFLAGS=HAVE_NEON=1", render("np2kai", ["HAVE_NEON=1"]))
        self.assertIn("GIT_VERSION=\"\\ {}\" HIDE= HAVE_NEON=1' ./libretro-build.sh".format(
            REPO.cores["mame2003_plus"]["source"]["commit"][:8]), render("mame2003_plus", ["HAVE_NEON=1"]))
        self.assertIn(" -DHAVE_NEON=ON", render("flycast", ["HAVE_NEON=ON"]))
        self.assertIn("export CFLAGS=-D__NEON_OPT\n", render("np2kai", ["-D__NEON_OPT"]))

    def test_special_recipes(self):
        self.assertIn("/usr/bin/gmake -f Makefile.libretro", self.render("picodrive", "armhf"))
        self.assertIn("MAKEFLAGS='-- GIT_VERSION=9d7716aa2 GIT_DATE=260503 HIDE=' ./libretro-build.sh fbneo",
                      self.render("fbneo", "arm64"))
        self.assertIn("apply -p4 --check", self.render("flycast", "armhf"))
        self.assertIn("timeout 300 qemu-arm /tmp/smoke-loader", self.render("np2kai", "armhf"))


class KnownGoodTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.spec = self.repo.cores["np2kai"]
        self.spec["known_good"] = {k: json.loads(json.dumps(self.spec[k])) for k in ("source", "build", "metadata")}
        self.spec["known_good"]["source"]["commit"] = "1" * 40

    def test_known_good_is_checked_like_the_current_recipe(self):
        self.assertEqual(self.repo.check(), [])
        self.spec["known_good"]["build"]["overlays"]["arm64"][0]["patch"] = "patches/missing.patch"
        self.assertIn("np2kai: known_good: missing patch patches/missing.patch", self.repo.check())

    def test_a_failed_build_falls_back_to_the_known_good_recipe(self):
        def fake(repo, core, variant, out, repeat=1, spec=None):
            out.mkdir(parents=True)
            commit = (spec or repo.cores[core])["source"]["commit"]
            rec = {"status": "usable" if commit == "1" * 40 else "failed", "seconds": 0,
                   "source": {"commit": commit}}
            (out / "record.json").write_text(json.dumps(rec))
            return rec

        original, build.build_one = build.build_one, fake
        try:
            out = Path(tempfile.mkdtemp())
            (variant,) = builds("np2kai", ["universal"], ["release"], arch="arm64")
            (rec,) = build.build_core(self.repo, "np2kai", [variant], out, fallback=True)
        finally:
            build.build_one = original
        self.assertEqual((rec["status"], rec["source"]["commit"]), ("usable", "1" * 40))
        self.assertEqual(rec["fallback"]["from_commit"], self.spec["source"]["commit"])
        self.assertTrue((out / "np2kai" / variant.name / "current-attempt" / "record.json").is_file())
        self.assertIsNone(known_good(Repo().cores["np2kai"]))


def record(core, name, arch, boards, status="usable", sha="a" * 64, reproducible=None, profile="max", suffix=""):
    return {
        "core": core, "status": status, "source": {"commit": "c" * 40},
        "variant": {"name": name, "arch": arch, "profile": profile, "boards": boards, "flags": [], "suffix": suffix},
        "toolchain": {"image_id": "sha256:" + "0" * 64},
        "artifact": {"name": f"{core}_libretro.so", "sha256": sha, "size": 1} if status != "failed" else None,
        "metadata": {"name": f"{core}_libretro.info", "sha256": "b" * 64},
        "reproducible": reproducible,
    }


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.results = self.tmp / "results"

    def add(self, rec):
        directory = self.results / rec["core"] / rec["variant"]["name"]
        directory.mkdir(parents=True)
        (directory / "record.json").write_text(json.dumps(rec))
        if rec["artifact"]:
            (directory / rec["artifact"]["name"]).write_text("so")
            (directory / rec["metadata"]["name"]).write_text("info")

    def test_bundles_use_the_device_layout(self):
        self.add(record("yabasanshiro", "max-arm64-cortex-a53", "arm64", ["a133p", "h700"]))
        self.add(record("np2kai", "max-armhf-generic", "armhf", ["universal"]))
        self.add(record("broken", "max-arm64-cortex-a53", "arm64", ["a133p"], status="failed"))
        summary = release.bundle(self.results, self.tmp / "bundles")
        a133p = self.tmp / "bundles/a133p-max/RetroArch/.retroarch"
        self.assertTrue((a133p / "cores64/yabasanshiro_a133p_libretro.so").is_file())
        self.assertTrue((a133p / "info/yabasanshiro_libretro.info").is_file())
        self.assertTrue((self.tmp / "bundles/universal-max/RetroArch/.retroarch/cores/np2kai_libretro.so").is_file())
        self.assertEqual(summary["a133p-max"]["broken"]["arm64"]["status"], "failed")
        self.assertFalse((a133p / "cores64/broken_libretro.so").exists())

    def test_static_and_stripped_builds_get_their_own_bundle(self):
        self.add(record("np2kai", "release-armhf-generic-stripped", "armhf", ["universal"],
                        profile="release", suffix="-stripped"))
        self.add(record("np2kai", "release-armhf-generic-static-stripped", "armhf", ["universal"],
                        profile="release", suffix="-static-stripped"))
        summary = release.bundle(self.results, self.tmp / "bundles")
        self.assertEqual(sorted(summary), ["universal-release-static-stripped", "universal-release-stripped"])

    def test_freeze_requires_reproducible_builds_and_checks_a_manifest(self):
        self.add(record("np2kai", "release-arm64-generic", "arm64", ["universal"], reproducible=True))
        self.add(record("mgba", "release-arm64-generic", "arm64", ["universal"], reproducible=False))
        manifest, problems = release.freeze(self.results, "test", "f" * 40)
        self.assertEqual(len(manifest["builds"]), 2)
        self.assertEqual(problems, ["mgba release-arm64-generic: second build differs (None)"])
        frozen = self.tmp / "frozen.json"
        manifest["builds"][1]["artifact"]["sha256"] = "d" * 64
        frozen.write_text(json.dumps(manifest))
        _, problems = release.freeze(self.results, "test", "f" * 40, frozen)
        self.assertIn("np2kai release-arm64-generic: rebuilt bytes differ from the frozen release", problems)

    def test_a_failed_script_step_fails_the_build_even_with_an_artifact(self):
        rec = {"artifact": {"name": "x.so"}, "exit_code": 1, "usability": {"probed": False}}
        self.assertEqual(build.status(rec), "failed")
        rec["exit_code"] = 0
        self.assertEqual(build.status(rec), "built")

    def test_usability_needs_every_smoke_step(self):
        out = self.tmp / "smoke"
        out.mkdir()
        (out / "smoke.txt").write_text("".join(f"CHECK {s} pass\n" for s in build.SMOKE_STEPS))
        self.assertTrue(build.usability(out)["loaded"])
        (out / "smoke.txt").write_text("CHECK dlopen pass\nCHECK retro_api_version pass\nexit 139\n")
        self.assertFalse(build.usability(out)["loaded"])
        mid_line = "".join(f"core output without newline CHECK {s} pass\n" for s in build.SMOKE_STEPS)
        (out / "smoke.txt").write_text(mid_line)
        self.assertTrue(build.usability(out)["loaded"])


if __name__ == "__main__":
    unittest.main()


class StandaloneTest(unittest.TestCase):
    def setUp(self):
        self.spec = standalone.load(REPO)["flycast-standalone"]

    def test_recipes_are_consistent(self):
        self.assertEqual(standalone.check(REPO), [])

    def test_script_pins_the_source_and_bundles_the_libraries(self):
        text = standalone.render("flycast-standalone", self.spec, REPO.toolchains[self.spec["toolchain"]]).text
        self.assertIn(f"checkout -q {self.spec['source']['commit']}", text)
        self.assertIn(self.spec["source"]["tree"], text)
        self.assertIn(f"SOURCE_DATE_EPOCH={self.spec['source_date_epoch']}", text)
        for soname in self.spec["output"]["bundled_libraries"]:
            self.assertIn(f"/output/lib/{soname}", text)
        self.assertLess(text.index("cmake --build"), text.index("strip -s /output/flycast"))

    def test_contract_names_forbidden_and_unaccounted_libraries(self):
        ok = ["libSDL2-2.0.so.0", "libcurl.so.4", "libc.so.6"]
        self.assertEqual(standalone.contract_problems(self.spec, ok, ["libssl.so.1.1", "libz.so.1"]), [])
        problems = standalone.contract_problems(self.spec, ok + ["libvulkan.so.1", "libfoo.so.1"], [])
        self.assertEqual(problems, ["libvulkan.so.1 is forbidden", "libfoo.so.1 is neither on the device nor bundled"])

