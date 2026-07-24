from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import shlex
import unittest
import zipfile

from scripts.core_pipeline_lib.contracts import c_only, freeintv
from scripts.core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)
from scripts.core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from scripts.core_pipeline_lib.foundation import sha256_file


ROOT = Path(__file__).resolve().parents[1]
ORACLE_RUNS = (
    "tranche9b-freeintv-golden-v1",
    "tranche9b-freeintv-repro-v1",
)
ORACLE_E2E_FILE_SHA256 = {
    ORACLE_RUNS[0]: (
        "828f0123672a6422bc09d68c61d6a45a3d779acee2432e8ea125e87c4b5c91b9"
    ),
    ORACLE_RUNS[1]: (
        "c11787e78a45b09ad719ef290b9c4d2000df7e8b0d4f3c474078e73e00830942"
    ),
}
ORACLE_E2E_CONTENT_SHA256 = {
    ORACLE_RUNS[0]: (
        "2621d6c0f9a2d562497de4abf96cfe8153fb9bdfc42cd4d930109e05f0df0f79"
    ),
    ORACLE_RUNS[1]: (
        "bfe45506cb833d9b6d37bfe20a4071a06f0a39ef45d7c55229ba48ab45467332"
    ),
}
ORACLE_BUILD_RECORD_SHA256 = {
    ORACLE_RUNS[0]: {
        "arm64": (
            "169474f0b74c08e92f72a80ed1a1a210ee58de6e44c654e6cc7d6a6d19212d65"
        ),
        "armhf": (
            "35eeda2031ad44e661c9af6a6d92ba6ef89715bd13e275096a7b9aad92f932c2"
        ),
    },
    ORACLE_RUNS[1]: {
        "arm64": (
            "13c27e0cf3f44505b21e97f99e2cbb7df93d980749e7efcd2f39798762d65ea2"
        ),
        "armhf": (
            "d0c090ebf20e7eb46e11c789466d09e813a6b846f308614b9325c9a5ecda4e36"
        ),
    },
}
ORACLE_LOG_SHA256 = {
    ORACLE_RUNS[0]: {
        "arm64": (
            "638ca984fb5e8d3156f5f459c1416202d72531a8a95a06ff744de5db367035c5"
        ),
        "armhf": (
            "7ad69f64e97bde7aba63bf0196a33825074b9d58abab915c12afe05df78c5e16"
        ),
    },
    ORACLE_RUNS[1]: {
        "arm64": (
            "92f282572d4f69f53780a4375cc75b02addb4bd9ad9f6213834530f99e85e1f2"
        ),
        "armhf": (
            "c361b30b779f200893c1028b31d1c504e1410286edccfca5393c4440426841aa"
        ),
    },
}
SOURCE_LOCK_PATH = (
    ROOT
    / "pins/sources/freeintv/428915baf2bfc032fc03e645f4f8f9c6c3144979.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "e25d94c392611bf06056998eff60908c7740793418f3521c0b2290ad3cdbbb72"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "97940c9943e49e078154248746d164e4a5c7b7afbe71bc6d9c009d6a9bab06b4"
)
SOURCE_RECORD_IDENTITY = {
    "commit": "428915baf2bfc032fc03e645f4f8f9c6c3144979",
    "requested_ref": "refs/heads/master",
    "resolved_commit": "428915baf2bfc032fc03e645f4f8f9c6c3144979",
    "resolved_url": "https://github.com/libretro/FreeIntv.git",
    "submodules": [],
    "tree": "ca7bcc22845ae696dd0fa011bd7c2486db7990e4",
    "url": "https://github.com/libretro/FreeIntv.git",
}


def catalog_spec() -> dict:
    catalog = json.loads(
        (ROOT / "manifests/core-builds.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(catalog["cores"][freeintv.FREEINTV_CORE_ID])


def active_log(historical_log: str) -> str:
    head = freeintv.FREEINTV_SOURCE_HEAD_MARKER + "\n"
    marker = freeintv.FREEINTV_SOURCE_IDENTITY_MARKER + "\n"
    if historical_log.count(head) != 1:
        raise AssertionError("historical FreeIntv head marker is not unique")
    return historical_log.replace(head, head + marker, 1)


def parse_info(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if " = " not in line or line.startswith("#"):
            continue
        key, value = line.split(" = ", 1)
        result[key] = value.strip('"')
    return result


class FreeIntvContractTests(unittest.TestCase):
    def contract_arguments(
        self, log: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = freeintv.FREEINTV_SPEC_IDENTITY
        return (
            log,
            freeintv.FREEINTV_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def assert_active_rejects(self, log: str, architecture: str) -> None:
        self.assertFalse(
            freeintv.freeintv_log_proves_contract(
                *self.contract_arguments(log, architecture)
            )
        )

    def require_oracle_log(
        self,
        architecture: str,
        run_id: str = ORACLE_RUNS[0],
    ) -> str:
        path = (
            ROOT
            / ".local-e2e/runs"
            / run_id
            / freeintv.FREEINTV_CORE_ID
            / architecture
            / "build.log"
        )
        if not path.is_file():
            self.skipTest(
                "workspace-local FreeIntv oracle evidence is unavailable"
            )
        return path.read_text(encoding="utf-8")

    def test_exact_identity_spec_and_golden_predicates_are_core_owned(
        self,
    ) -> None:
        spec = catalog_spec()
        identity = freeintv.FREEINTV_SPEC_IDENTITY
        self.assertTrue(freeintv.freeintv_spec_is_well_formed(spec))
        self.assertEqual("freeintv-c-only-v1", freeintv.FREEINTV_LOG_CONTRACT_ID)
        self.assertEqual("core-arch-source", freeintv.FREEINTV_LOG_PROOF_KIND)
        self.assertEqual("Makefile", identity["native_makefile"])
        self.assertNotIn("git_version", spec["build"])
        self.assertEqual(
            "native-space-short7-v1",
            identity["native_git_version_derivation"],
        )
        self.assertEqual(" 428915b", identity["native_git_version"])

        def changed(path: tuple[str, ...], value: object) -> dict:
            result = copy.deepcopy(spec)
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return result

        mutations = {
            "workflow": changed(("workflow",), "build.yml"),
            "source-url": changed(("source", "url"), "https://example.com"),
            "source-ref": changed(
                ("source", "requested_ref"), "refs/heads/main"
            ),
            "source-commit": changed(("source", "commit"), "0" * 40),
            "source-tree": changed(("source", "tree"), "0" * 40),
            "driver": changed(("build", "driver"), "direct-make"),
            "source-key": changed(("build", "source_key"), "other"),
            "source-dir": changed(("build", "source_dir"), "other"),
            "output": changed(("build", "output_path"), "other.so"),
            "artifact": changed(
                ("build", "artifact_name"), "other_libretro.so"
            ),
            "metadata-source": changed(
                ("metadata", "source_path"), "/tmp/other.info"
            ),
            "metadata-artifact": changed(
                ("metadata", "artifact_name"), "other.info"
            ),
            "targets": changed(("targets",), ["arm64"]),
        }
        extra = copy.deepcopy(spec)
        extra["unexpected"] = True
        mutations["extra-top-level"] = extra
        injected_version = copy.deepcopy(spec)
        injected_version["build"]["git_version"] = {
            "derivation": "native-space-short7-v1",
            "value": " 428915b",
            "compiler_scope": "c",
        }
        mutations["injected-version"] = injected_version
        for path in (
            ("source", "tree"),
            ("build", "source_dir"),
            ("metadata", "artifact_name"),
        ):
            missing = copy.deepcopy(spec)
            target = missing
            for key in path[:-1]:
                target = target[key]
            target.pop(path[-1])
            mutations["missing-" + "-".join(path)] = missing
        for label, mutation in mutations.items():
            with self.subTest(spec_mutation=label):
                self.assertFalse(
                    freeintv.freeintv_spec_is_well_formed(mutation)
                )
        for malformed in (None, [], "freeintv", {}, {"workflow": "x"}):
            with self.subTest(malformed=malformed):
                self.assertFalse(
                    freeintv.freeintv_spec_is_well_formed(malformed)
                )

        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        source = copy.deepcopy(SOURCE_RECORD_IDENTITY)
        self.assertTrue(
            freeintv.freeintv_golden_source_is_well_formed(
                freeintv.FREEINTV_CORE_ID, source
            )
        )
        self.assertTrue(
            freeintv.freeintv_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                freeintv.FREEINTV_CORE_ID,
                source,
            )
        )
        for key, value in (
            ("url", "https://example.com/FreeIntv.git"),
            ("requested_ref", "refs/heads/main"),
            ("commit", "0" * 40),
            ("tree", "0" * 40),
            ("resolved_commit", "0" * 40),
            ("resolved_url", "https://example.com"),
            ("submodules", [{"path": "foreign", "commit": "0" * 40}]),
        ):
            changed_source = copy.deepcopy(source)
            changed_source[key] = value
            with self.subTest(source_mutation=key):
                self.assertFalse(
                    freeintv.freeintv_golden_source_is_well_formed(
                        freeintv.FREEINTV_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    freeintv.freeintv_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        freeintv.FREEINTV_CORE_ID,
                        changed_source,
                    )
                )
        for key, value in (
            ("driver", "direct-make"),
            ("environment", "inherited"),
            ("compile_definitions", ["SYNTHETIC=1"]),
            ("log", "other.log"),
            ("log_sha256", "not-a-digest"),
        ):
            changed_build = copy.deepcopy(build)
            changed_build[key] = value
            with self.subTest(build_mutation=key):
                self.assertFalse(
                    freeintv.freeintv_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        freeintv.FREEINTV_CORE_ID,
                        source,
                    )
                )

if __name__ == "__main__":
    unittest.main()
