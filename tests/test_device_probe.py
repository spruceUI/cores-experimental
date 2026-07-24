"""Guardrails for the on-device capture tool.

`device_probe.sh` is pasted onto handheld firmware over SSH and its `CAPTURE`
block is transcribed into `device-runtime-contracts.json`, so two properties
are load-bearing and worth pinning: it must stay read-only, and its capture key
set must not drift silently.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "device_probe.sh"

# Every `capture.<key>=` the probe emits. Adding or removing one changes what a
# reviewer transcribes into a device contract, so it should be a deliberate
# edit rather than a side effect.
EXPECTED_CAPTURE_KEYS = {
    # identity / toolchain
    "schema",
    "machine",
    "pipeline_target",
    "dynamic_loader",
    "libc_max_glibc",
    "cpu_core",
    "cpu_implementer",
    "cpu_part",
    "suggested_mcpu",
    "suggested_opt_flags",
    "mem_total_kb",
    "enforcing",
    # C++ provider ceiling
    "effective_cxx_provider",
    "effective_cxx_role",
    "effective_cxx_hash",
    "effective_cxx_elf",
    "effective_max_glibcxx",
    "effective_max_cxxabi",
    "cxx_provider_count",
    "secondary_abi",
    "secondary_abi_max_glibcxx",
    # graphics stack (v3)
    "gpu_apis",
    "gpu_nodes",
    "gles2_provider",
    "gles2_provider_hash",
    "gles2_provider_elf",
    "egl_provider",
    # frontend (v3)
    "frontend_binary",
    "frontend_video_apis",
    "frontend_missing_deps",
    # loader-truth dependency resolution (v3)
    "dependency_resolution_method",
    "cores_scanned",
    "cores_resolvable",
    "cores_unresolvable",
    "cores_foreign_abi",
    "missing_sonames",
    "libs_absent",
}


class DeviceProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PROBE.read_text(encoding="utf-8")

    def test_script_parses_as_posix_sh(self) -> None:
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("no POSIX sh available")
        result = subprocess.run(
            [shell, "-n", str(PROBE)], capture_output=True, text=True
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_capture_block_keys_are_exactly_the_reviewed_set(self) -> None:
        found = set(re.findall(r'say "capture\.([a-z0-9_]+)=', self.text))
        self.assertEqual(EXPECTED_CAPTURE_KEYS, found)

    def test_probe_schema_version_is_consistent(self) -> None:
        versions = set(re.findall(r"device-probe-(v[0-9]+)", self.text))
        self.assertEqual({"v3"}, versions)

    def test_probe_stays_read_only(self) -> None:
        """The only write is the log file and one write-probe touch file."""

        # Matched in command position only, so reading /proc/mounts does not
        # look like running mount(8).
        forbidden = re.compile(
            r"^\s*(rm\s+-[a-z]*r|mkfs|dd\s|chmod\s|chown\s|mount\s|umount\s"
            r"|modprobe\s|insmod\s|reboot|shutdown|halt)",
            re.MULTILINE,
        )
        self.assertIsNone(forbidden.search(self.text), "destructive command")
        self.assertNotIn(">/dev/sd", self.text)
        self.assertNotIn("> /dev/sd", self.text)
        # `rm -f` appears exactly once, removing the write-probe file it made.
        self.assertEqual(1, self.text.count("rm -f "))
        self.assertIn('rm -f "$d/.probe_write_test"', self.text)

    def test_dependency_resolution_never_reads_silence_as_success(self) -> None:
        """Empty loader output means undetermined, not "all resolved".

        A foreign-ABI object, a missing loader, or firmware without ldd all
        produce no output; treating that as a clean result would report an
        unloadable core as eligible, which is the exact fail-open this section
        exists to close.
        """

        self.assertIn('[ -n "$deps" ]', self.text)
        self.assertIn("method=dt-needed", self.text)
        self.assertIn("foreign-abi", self.text)

    def test_loader_resolution_uses_the_trace_mechanism(self) -> None:
        """LD_TRACE_LOADED_OBJECTS resolves without running the object."""

        self.assertIn("LD_TRACE_LOADED_OBJECTS=1", self.text)


if __name__ == "__main__":
    unittest.main()
