from __future__ import annotations

import copy
import inspect
import unittest

from tests import expected_counts
from unittest import mock

from scripts.core_pipeline_lib.contracts import (
    CORE_LOG_CONTRACTS,
    CoreLogContract,
    core_log_contract_for,
    registered_core_log_contract_ids,
)
from scripts.core_pipeline_lib.contracts.picodrive import PICODRIVE_SUBMODULES
from tests.cores.support import ROOT, evidence_handles, pipeline


class CoreLogContractRegistryTests(unittest.TestCase):
    @staticmethod
    def _reminiscence_candidate_log(arch: str = "arm64") -> tuple[
        str, pipeline.SourceCandidateContractProjection
    ]:
        handles = evidence_handles("reminiscence")
        log_path = (
            ROOT
            / ".local-e2e"
            / "runs"
            / handles["SELECTED_RUN"]
            / "reminiscence"
            / arch
            / "build.log"
        )
        if not log_path.is_file():
            raise unittest.SkipTest("no workspace-local REMiniscence log present")
        candidate_commit = "e6c0b0039258004f8bc377ddb88c0e931db131ce"
        candidate_tree = "ae159556bc8d419843cecceb5ba020728abbdd2d"
        projection = pipeline.SourceCandidateContractProjection(
            core_id="reminiscence",
            candidate_id="a" * 64,
            canonical_commit=handles["SOURCE_COMMIT"],
            canonical_tree=handles["SOURCE_TREE"],
            candidate_commit=candidate_commit,
            candidate_tree=candidate_tree,
            canonical_spec_sha256="b" * 64,
            execution_spec_sha256="c" * 64,
        )
        candidate_log = log_path.read_text(encoding="utf-8").replace(
            handles["SOURCE_COMMIT"][:7],
            candidate_commit[:7],
        )
        return candidate_log, projection

    def test_registry_covers_all_individual_core_contracts(self) -> None:
        self.assertEqual(
            {
                "2048",
                "81",
                "a5200",
                "atari800",
                "cap32",
                "crocods",
                "ecwolf",
                "fbneo",
                "fceumm",
                "fmsx",
                "freechaf",
                "freeintv",
                "bluemsx",
                "gambatte",
                "gearboy",
                "gearcoleco",
                "gearsystem",
                "genesis_plus_gx",
                "genesis_plus_gx_wide",
                "gpsp",
                "km_parallel_n64_xtreme_amped_turbo",
                "libgametank",
                "handy",
                "mednafen_lynx",
                "mednafen_ngp",
                "mednafen_vb",
                "mednafen_pcfx",
                "mednafen_pce_fast",
                "mednafen_supergrafx",
                "mednafen_supafaust",
                "mednafen_wswan",
                "mgba",
                "neocd",
                "nestopia",
                "lowresnx",
                "mame2003_plus",
                "o2em",
                "pcsx_rearmed",
                "picodrive",
                "prboom",
                "fuse",
                "gme",
                "frodo",
                "quasi88",
                "retro8",
                "reminiscence",
                "gw",
                "mu",
                "hatari",
                "theodore",
                "bk",
                "numero",
                "opera",
                "fbalpha2012",
                "chimerasnes",
                "px68k",
                "x1",
                "yabasanshiro",
                "daphne",
                "uae4arm",
                "puae2021",
                "lutro",
                "np2kai",
                "sameduck",
                "puzzlescript",
                "fake08",
                "uw8",
                "chailove",
                "dosbox_pure",
                "parallel_n64",
                "mupen64plus_next",
                "pokemini",
                "potator",
                "prosystem",
                "quicknes",
                "race",
                "snes9x",
                "snes9x2005",
                "snes9x2005_plus",
                "snes9x2002",
                "snes9x2010",
                "stella2014",
                "tyrquake",
                "tgbdual",
                "uzem",
                "vemulator",
                "vecx",
                "vice_x64",
                "vice_xvic",
            },
            set(registered_core_log_contract_ids()),
        )
        self.assertEqual(
            len(CORE_LOG_CONTRACTS), expected_counts.CORE_LOG_CONTRACT_COUNT
        )
        self.assertTrue(
            all(len(contract.core_ids) == 1 for contract in CORE_LOG_CONTRACTS)
        )

    def test_split_contracts_have_individual_ids_and_proofs(self) -> None:
        expected = {
            "2048": (
                "core-2048-c-only-v1",
                "core_2048_log_proves_contract",
            ),
            "81": (
                "core-81-mixed-language-v1",
                "core_81_log_proves_contract",
            ),
            "a5200": (
                "a5200-c-only-v1",
                "a5200_log_proves_contract",
            ),
            "atari800": (
                "atari800-c-only-v1",
                "atari800_log_proves_contract",
            ),
            "fbneo": (
                "fbneo-mixed-language-v1",
                "fbneo_log_proves_contract",
            ),
            "ecwolf": (
                "ecwolf-mixed-language-v1",
                "ecwolf_log_proves_contract",
            ),
            "neocd": (
                "neocd-mixed-language-v1",
                "neocd_log_proves_contract",
            ),
            "pcsx_rearmed": (
                "pcsx-rearmed-c-asm-v1",
                "pcsx_rearmed_log_proves_contract",
            ),
            "gpsp": (
                "gpsp-c-asm-v1",
                "gpsp_log_proves_contract",
            ),
            "prosystem": (
                "prosystem-c-only-v1",
                "prosystem_log_proves_contract",
            ),
            "snes9x": (
                "snes9x-mixed-language-v1",
                "snes9x_log_proves_contract",
            ),
            "mednafen_supafaust": (
                "mednafen-supafaust-cxx-link-v1",
                "mednafen_supafaust_log_proves_contract",
            ),
            "mednafen_wswan": (
                "mednafen-wswan-mixed-language-v1",
                "mednafen_wswan_log_proves_contract",
            ),
            "mednafen_vb": (
                "mednafen-vb-mixed-language-v1",
                "mednafen_vb_log_proves_contract",
            ),
            "mednafen_ngp": (
                "mednafen-ngp-mixed-language-v1",
                "mednafen_ngp_log_proves_contract",
            ),
            "mednafen_lynx": (
                "mednafen-lynx-mixed-language-v1",
                "mednafen_lynx_log_proves_contract",
            ),
            "mednafen_pcfx": (
                "mednafen-pcfx-mixed-language-v1",
                "mednafen_pcfx_log_proves_contract",
            ),
            "mednafen_supergrafx": (
                "mednafen-supergrafx-mixed-language-v1",
                "mednafen_supergrafx_log_proves_contract",
            ),
            "mednafen_pce_fast": (
                "mednafen-pce-fast-c-only-v1",
                "mednafen_pce_fast_log_proves_contract",
            ),
            "pokemini": (
                "pokemini-c-only-v1",
                "pokemini_log_proves_contract",
            ),
            "picodrive": (
                "picodrive-source-root-v1",
                "picodrive_log_proves_contract",
            ),
            "uzem": (
                "uzem-mixed-language-v1",
                "uzem_log_proves_contract",
            ),
            "vemulator": (
                "vemulator-mixed-language-v1",
                "vemulator_log_proves_contract",
            ),
            "mgba": (
                "mgba-c-only-v1",
                "mgba_log_proves_contract",
            ),
            "mame2003_plus": (
                "mame2003-plus-c-only-v1",
                "mame2003_plus_log_proves_contract",
            ),
            "freeintv": (
                "freeintv-c-only-v1",
                "freeintv_log_proves_contract",
            ),
            "gearcoleco": (
                "gearcoleco-mixed-language-v1",
                "gearcoleco_log_proves_contract",
            ),
            "gearboy": (
                "gearboy-mixed-language-v1",
                "gearboy_log_proves_contract",
            ),
            "gearsystem": (
                "gearsystem-mixed-language-v1",
                "gearsystem_log_proves_contract",
            ),
            "fmsx": (
                "fmsx-c-only-v1",
                "fmsx_log_proves_contract",
            ),
            "bluemsx": (
                "bluemsx-mixed-language-v1",
                "bluemsx_log_proves_contract",
            ),
            "lowresnx": (
                "lowresnx-c-only-v1",
                "lowresnx_log_proves_contract",
            ),
            "race": (
                "race-c-only-v1",
                "race_log_proves_contract",
            ),
            "potator": (
                "potator-c-only-v1",
                "potator_log_proves_contract",
            ),
            "vice_x64": (
                "vice-x64-mixed-language-v1",
                "vice_x64_log_proves_contract",
            ),
            "vice_xvic": (
                "vice-xvic-mixed-language-v1",
                "vice_xvic_log_proves_contract",
            ),
            "o2em": (
                "o2em-c-only-v1",
                "o2em_log_proves_contract",
            ),
            "freechaf": (
                "freechaf-c-only-v1",
                "freechaf_log_proves_contract",
            ),
            "vecx": (
                "vecx-software-c-only-v1",
                "vecx_log_proves_contract",
            ),
            "snes9x2005": (
                "snes9x2005-c-only-v1",
                "snes9x2005_log_proves_contract",
            ),
            "snes9x2005_plus": (
                "snes9x2005-plus-c-only-v1",
                "snes9x2005_plus_log_proves_contract",
            ),
            "snes9x2010": (
                "snes9x2010-c-only-v1",
                "snes9x2010_log_proves_contract",
            ),
            "snes9x2002": (
                "snes9x2002-c-only-v1",
                "snes9x2002_log_proves_contract",
            ),
            "tyrquake": (
                "tyrquake-c-only-v1",
                "tyrquake_log_proves_contract",
            ),
            "prboom": (
                "prboom-c-only-v1",
                "prboom_log_proves_contract",
            ),
            "fuse": (
                "fuse-c-only-v1",
                "fuse_log_proves_contract",
            ),
            "gme": (
                "gme-mixed-language-v1",
                "gme_log_proves_contract",
            ),
            "frodo": (
                "frodo-mixed-language-v1",
                "frodo_log_proves_contract",
            ),
            "quasi88": (
                "quasi88-mixed-language-v1",
                "quasi88_log_proves_contract",
            ),
            "retro8": (
                "retro8-mixed-language-v1",
                "retro8_log_proves_contract",
            ),
            "reminiscence": (
                "reminiscence-mixed-language-v1",
                "reminiscence_log_proves_contract",
            ),
            "gw": (
                "gw-c-only-v1",
                "gw_log_proves_contract",
            ),
            "mu": (
                "mu-mixed-language-v1",
                "mu_log_proves_contract",
            ),
            "hatari": (
                "hatari-c-only-v1",
                "hatari_log_proves_contract",
            ),
            "theodore": (
                "theodore-c-only-v1",
                "theodore_log_proves_contract",
            ),
            "bk": (
                "bk-c-only-v1",
                "bk_log_proves_contract",
            ),
            "numero": (
                "numero-mixed-language-v1",
                "numero_log_proves_contract",
            ),
            "opera": (
                "opera-c-only-v1",
                "opera_log_proves_contract",
            ),
            "fbalpha2012": (
                "fbalpha2012-mixed-language-v1",
                "fbalpha2012_log_proves_contract",
            ),
            "chimerasnes": (
                "chimerasnes-c-only-v1",
                "chimerasnes_log_proves_contract",
            ),
            "px68k": (
                "px68k-mixed-language-v1",
                "px68k_log_proves_contract",
            ),
            "x1": (
                "x1-mixed-language-v1",
                "x1_log_proves_contract",
            ),
            "daphne": (
                "daphne-mixed-language-v1",
                "daphne_log_proves_contract",
            ),
            "uae4arm": (
                "uae4arm-mixed-language-v1",
                "uae4arm_log_proves_contract",
            ),
            "puae2021": (
                "puae2021-c-only-v1",
                "puae2021_log_proves_contract",
            ),
            "lutro": (
                "lutro-c-only-archive-v1",
                "lutro_log_proves_contract",
            ),
            "np2kai": (
                "np2kai-mixed-language-v1",
                "np2kai_log_proves_contract",
            ),
            "sameduck": (
                "sameduck-c-only-v1",
                "sameduck_log_proves_contract",
            ),
            "puzzlescript": (
                "puzzlescript-mixed-language-v1",
                "puzzlescript_log_proves_contract",
            ),
            "fake08": (
                "fake08-mixed-language-v1",
                "fake08_log_proves_contract",
            ),
            "uw8": (
                "uw8-c-only-v1",
                "uw8_log_proves_contract",
            ),
            "chailove": (
                "chailove-c-asm-v1",
                "chailove_log_proves_contract",
            ),
            "dosbox_pure": (
                "dosbox-pure-mixed-language-v1",
                "dosbox_pure_log_proves_contract",
            ),
            "parallel_n64": (
                "parallel-n64-c-asm-v1",
                "parallel_n64_log_proves_contract",
            ),
            "mupen64plus_next": (
                "mupen64plus-next-c-asm-v1",
                "mupen64plus_next_log_proves_contract",
            ),
            "cap32": (
                "cap32-make-trace-v1",
                "cap32_log_proves_contract",
            ),
            "crocods": (
                "crocods-c-only-v1",
                "crocods_log_proves_contract",
            ),
            "genesis_plus_gx": (
                "genesis-plus-gx-c-link-v1",
                "genesis_plus_gx_log_proves_contract",
            ),
            "genesis_plus_gx_wide": (
                "genesis-plus-gx-wide-c-link-v1",
                "genesis_plus_gx_wide_log_proves_contract",
            ),
        }
        for core_id, (contract_id, proof_name) in expected.items():
            with self.subTest(core_id=core_id):
                contract = core_log_contract_for(core_id)
                self.assertIsNotNone(contract)
                assert contract is not None
                self.assertEqual(frozenset({core_id}), contract.core_ids)
                self.assertEqual(contract_id, contract.contract_id)
                self.assertEqual(proof_name, contract.proof_name)
                self.assertIn(core_id.split("_")[0].lower(), contract_id)

    def test_lookup_is_exact_and_unknown_cores_have_no_contract(self) -> None:
        contract = core_log_contract_for("handy")
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "handy_log_proves_contract", contract.proof_name
        )
        self.assertEqual("handy-mixed-language-v1", contract.contract_id)
        self.assertEqual("core-arch-source", contract.proof_kind)
        stella_contract = core_log_contract_for("stella2014")
        self.assertIsNotNone(stella_contract)
        assert stella_contract is not None
        self.assertEqual(
            "stella2014_log_proves_contract", stella_contract.proof_name
        )
        self.assertEqual(
            "stella2014-mixed-language-v1", stella_contract.contract_id
        )
        self.assertNotEqual(contract.failure_message, stella_contract.failure_message)
        self.assertIn("Handy", contract.failure_message)
        self.assertNotIn("Stella", contract.failure_message)
        self.assertIn("Stella 2014", stella_contract.failure_message)
        self.assertNotIn("Handy", stella_contract.failure_message)
        self.assertIsNone(core_log_contract_for("Handy"))
        self.assertIsNone(core_log_contract_for(None))

    def test_contract_model_rejects_ambiguous_identity(self) -> None:
        for kwargs in (
            {
                "contract_id": "bad",
                "core_ids": frozenset({"handy"}),
                "proof_name": "proof",
                "proof_kind": "core-arch-source",
                "failure_message": "failure",
            },
            {
                "contract_id": "valid-v1",
                "core_ids": frozenset(),
                "proof_name": "proof",
                "proof_kind": "core-arch-source",
                "failure_message": "failure",
            },
            {
                "contract_id": "valid-v1",
                "core_ids": frozenset({"handy", "stella2014"}),
                "proof_name": "proof",
                "proof_kind": "core-arch-source",
                "failure_message": "failure",
            },
            {
                "contract_id": "valid-v1",
                "core_ids": frozenset({"bad-core"}),
                "proof_name": "proof",
                "proof_kind": "core-arch-source",
                "failure_message": "failure",
            },
            {
                "contract_id": "valid-v1",
                "core_ids": frozenset({"handy"}),
                "proof_name": "Proof",
                "proof_kind": "core-arch-source",
                "failure_message": "failure",
            },
            {
                "contract_id": "valid-v1",
                "core_ids": frozenset({"handy"}),
                "proof_name": "proof",
                "proof_kind": "core-arch-source",
                "failure_message": " ",
            },
            {
                "contract_id": "valid-v1",
                "core_ids": frozenset({"handy"}),
                "proof_name": "proof",
                "proof_kind": "unknown",
                "failure_message": "failure",
            },
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CoreLogContract(**kwargs)

    def test_entrypoint_dispatch_resolves_individual_proofs_by_name(self) -> None:
        source_commit = "a" * 40
        source_tree = "b" * 40
        for contract in CORE_LOG_CONTRACTS:
            core_id = sorted(contract.core_ids)[0]
            expected_args = ["log", core_id, "arm64"]
            if contract.proof_kind == "core-arch-source":
                expected_args.extend([source_commit, source_tree])
            with self.subTest(contract=contract.contract_id), mock.patch.object(
                pipeline, contract.proof_name, return_value=False
            ) as proof:
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(
                        "log",
                        core_id,
                        "arm64",
                        source_commit,
                        source_tree,
                    )
                )
                proof.assert_called_once_with(*expected_args)

    def test_entrypoint_dispatch_treats_unregistered_cores_as_not_applicable(self) -> None:
        self.assertTrue(
            pipeline.registered_core_log_contract_proves(
                "log", "unregistered", "arm64", "a" * 40, "b" * 40
            )
        )

    def test_candidate_git_version_projection_is_always_on_and_command_scoped(
        self,
    ) -> None:
        canonical_commit = "b0eb4ff" + "1" * 33
        candidate_commit = "e6c0b00" + "2" * 33
        for arch, compiler in (
            ("arm64", "aarch64-linux-gnu-g++"),
            ("armhf", "arm-a30-linux-gnueabihf-g++"),
        ):
            projection = pipeline.SourceCandidateContractProjection(
                core_id="reminiscence",
                candidate_id="a" * 64,
                canonical_commit=canonical_commit,
                canonical_tree="b" * 40,
                candidate_commit=candidate_commit,
                candidate_tree="c" * 40,
                canonical_spec_sha256="d" * 64,
                execution_spec_sha256="e" * 64,
            )
            token = f"'-DGIT_VERSION=\" {candidate_commit[:7]}\"'"
            canonical_token = (
                f"'-DGIT_VERSION=\" {canonical_commit[:7]}\"'"
            )
            log = "\n".join(
                (
                    f"CXX = {compiler}",
                    f"HEAD is now at {candidate_commit[:7]} candidate",
                    f"{compiler} -O2 {token} -c engine.cpp -o engine.o",
                    (
                        f"cd src && {compiler} -O2 {token} "
                        "-c game.cpp -o game.o"
                    ),
                )
            ) + "\n"
            expected = log.replace(token, canonical_token)
            with self.subTest(arch=arch):
                projected = (
                    pipeline._candidate_log_with_canonical_git_version_tokens(
                        log,
                        arch,
                        projection,
                    )
                )
                self.assertEqual(expected, projected)
                assert projected is not None
                self.assertIn(f"CXX = {compiler}", projected)
                self.assertIn(
                    f"HEAD is now at {candidate_commit[:7]} candidate",
                    projected,
                )

                def prove(
                    proof_log: str,
                    core_id: str,
                    proof_arch: str,
                    source_commit: str,
                    source_tree: str,
                ) -> bool:
                    self.assertEqual(expected, proof_log)
                    self.assertEqual("reminiscence", core_id)
                    self.assertEqual(arch, proof_arch)
                    self.assertEqual(canonical_commit, source_commit)
                    self.assertEqual(projection.canonical_tree, source_tree)
                    return True

                with mock.patch.object(
                    pipeline,
                    "reminiscence_log_proves_contract",
                    side_effect=prove,
                ):
                    self.assertTrue(
                        pipeline._registered_core_log_contract_proves(
                            log,
                            "reminiscence",
                            arch,
                            candidate_commit,
                            projection.candidate_tree,
                            source_candidate_projection=projection,
                        )
                    )

                for label, changed in (
                    ("missing", log.replace(token, "")),
                    (
                        "malformed",
                        log.replace(
                            token,
                            f"-DGIT_VERSION={candidate_commit[:7]}",
                            1,
                        ),
                    ),
                    (
                        "foreign",
                        log.replace(
                            token,
                            token.replace(candidate_commit[:7], "deadbee"),
                            1,
                        ),
                    ),
                    (
                        "duplicate",
                        log.replace(token, f"{token} {token}", 1),
                    ),
                ):
                    with self.subTest(arch=arch, tamper=label):
                        changed_projection = (
                            pipeline._candidate_log_with_canonical_git_version_tokens(
                                changed, arch, projection
                            )
                        )
                        if label == "missing":
                            self.assertEqual(changed, changed_projection)
                            with mock.patch.object(
                                pipeline,
                                "reminiscence_log_proves_contract",
                                side_effect=lambda proof_log, *_args: (
                                    proof_log == expected
                                ),
                            ):
                                self.assertFalse(
                                    pipeline._registered_core_log_contract_proves(
                                        changed,
                                        "reminiscence",
                                        arch,
                                        candidate_commit,
                                        projection.candidate_tree,
                                        source_candidate_projection=projection,
                                    )
                                )
                        else:
                            self.assertIsNone(changed_projection)

    def test_reminiscence_candidate_projects_only_authenticated_compile_tokens(
        self,
    ) -> None:
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                candidate_log, projection = self._reminiscence_candidate_log(arch)
                self.assertIn(
                    f"HEAD is now at {projection.candidate_commit[:7]}",
                    candidate_log,
                )
                self.assertTrue(
                    pipeline._registered_core_log_contract_proves(
                        candidate_log,
                        "reminiscence",
                        arch,
                        projection.candidate_commit,
                        projection.candidate_tree,
                        source_candidate_projection=projection,
                    )
                )
                projected = pipeline._candidate_log_with_canonical_git_version_tokens(
                    candidate_log,
                    arch,
                    projection,
                )
                self.assertIsNotNone(projected)
                assert projected is not None
                self.assertIn(
                    f"HEAD is now at {projection.candidate_commit[:7]}",
                    projected,
                )

    def test_reminiscence_candidate_rejects_token_tampering(self) -> None:
        for arch in ("arm64", "armhf"):
            candidate_log, projection = self._reminiscence_candidate_log(arch)
            lines = candidate_log.splitlines()
            token = f'-DGIT_VERSION=\\"" {projection.candidate_commit[:7]}"\\"'
            token_line = next(
                index
                for index, line in enumerate(lines)
                if token in line and " -c " in f" {line} "
            )
            missing = list(lines)
            missing[token_line] = missing[token_line].replace(token, "", 1)
            foreign = candidate_log.replace(
                token,
                token.replace(projection.candidate_commit[:7], "deadbee"),
                1,
            )
            split = candidate_log.replace(
                token,
                f'-DGIT_VERSION \\"{projection.candidate_commit[:7]}\\"',
                1,
            )
            c_compilers = set(pipeline.TARGET_COMPILERS[arch])
            c_line = next(
                index
                for index, line in enumerate(lines)
                if any(line.startswith(f"{compiler} ") for compiler in c_compilers)
                and " -c " in f" {line} "
            )
            extra = list(lines)
            extra[c_line] = extra[c_line].replace(" -c ", f" {token} -c ", 1)
            for label, tampered in (
                ("missing", "\n".join(missing)),
                ("foreign", foreign),
                ("split", split),
                ("extra", "\n".join(extra)),
            ):
                with self.subTest(arch=arch, label=label):
                    self.assertFalse(
                        pipeline._registered_core_log_contract_proves(
                            tampered,
                            "reminiscence",
                            arch,
                            projection.candidate_commit,
                            projection.candidate_tree,
                            source_candidate_projection=projection,
                        )
                    )

    def test_public_log_proof_rejects_caller_supplied_projection(self) -> None:
        candidate_log, projection = self._reminiscence_candidate_log()
        with self.assertRaises(TypeError):
            pipeline.registered_core_log_contract_proves(
                candidate_log,
                "reminiscence",
                "arm64",
                projection.candidate_commit,
                projection.candidate_tree,
                source_candidate_projection=projection,
            )

        with self.assertRaises(TypeError):
            pipeline.registered_core_log_contract_proves(
                candidate_log,
                "reminiscence",
                "arm64",
                projection.candidate_commit,
                projection.candidate_tree,
                tuning={},
            )

    def test_public_validators_expose_no_projection_bypass(self) -> None:
        public_signatures = {
            "build": inspect.signature(
                pipeline.validate_build_record_identity
            ).parameters,
            "channel_pointer": inspect.signature(
                pipeline.validate_channel_pointer_document
            ).parameters,
            "channel_sources": inspect.signature(
                pipeline.require_channel_target_sources_eligible
            ).parameters,
            "channel_target": inspect.signature(
                pipeline.derive_channel_target
            ).parameters,
            "group_execution": inspect.signature(
                pipeline.group_execution_spec
            ).parameters,
            "log": inspect.signature(
                pipeline.registered_core_log_contract_proves
            ).parameters,
            "local_store": inspect.signature(
                pipeline.verify_local_store
            ).parameters,
            "local_release": inspect.signature(
                pipeline.validate_local_release
            ).parameters,
            "output_reproduction": inspect.signature(
                pipeline.verify_output_reproduction_bundle
            ).parameters,
            "package": inspect.signature(
                pipeline.verify_pinned_package
            ).parameters,
            "pin": inspect.signature(
                pipeline.validate_pin_set_document
            ).parameters,
            "release_pin": inspect.signature(
                pipeline.resolve_release_pin
            ).parameters,
            "recipe_snapshot": inspect.signature(
                pipeline.verify_recipe_snapshot
            ).parameters,
            "stored": inspect.signature(
                pipeline.verify_stored_e2e_bundle
            ).parameters,
            "historical_recipe_snapshot": inspect.signature(
                pipeline.verify_historical_recipe_snapshot
            ).parameters,
            "tuned_reproduction": inspect.signature(
                pipeline.verify_tuned_reproduction_bundle
            ).parameters,
        }
        for parameters in public_signatures.values():
            for private_parameter in (
                "authenticated_source_candidate_contract",
                "authenticated_recipe_catalog_snapshot",
                "execution_tuning",
                "historical_recipe_proofs",
                "manifest_document",
                "snapshot",
                "source_candidate_projection",
                "target_document",
                "tuning",
                "validated_pin_selection",
                "validation_context",
                "_validation_context",
                "_lineage_paths",
            ):
                self.assertNotIn(private_parameter, parameters)
        self.assertFalse(
            hasattr(pipeline, "validate_source_candidate_execution_catalog")
        )
        self.assertFalse(
            hasattr(
                pipeline,
                "require_catalog_bound_source_candidate_selection",
            )
        )
        with self.assertRaises(TypeError):
            pipeline.require_channel_target_sources_eligible(
                {},
                "nightly",
                ROOT / ".local-e2e" / "forged-channel-target.json",
                target_document={},
            )
        with self.assertRaises(TypeError):
            pipeline.validate_local_release(
                ROOT / ".local-e2e" / "forged-release",
                {},
                "0" * 64,
                manifest_document={},
            )
        for validator in (
            pipeline.verify_recipe_snapshot,
            pipeline.verify_historical_recipe_snapshot,
        ):
            with self.assertRaises(TypeError):
                validator(
                    ROOT / ".local-e2e" / "forged-recipe.json",
                    {},
                    "forged recipe",
                    snapshot={},
                )

    def test_cached_file_bytes_are_rehashed_before_reuse(self) -> None:
        path = ROOT / ".local-e2e" / "forged-cache-entry"
        expected = pipeline.sha256_bytes(b"expected bytes")
        context = pipeline._PinValidationContext()
        context.verified_bytes[(str(path.resolve()), expected)] = b"forged bytes"
        with self.assertRaisesRegex(pipeline.PipelineError, "cached digest drift"):
            pipeline.verified_file_bytes(
                path,
                expected,
                "focused cache entry",
                context,
            )

    def test_changed_core_81_keeps_canonical_generated_source_guard(self) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        canonical_spec = catalog["cores"]["81"]
        candidate_spec = copy.deepcopy(canonical_spec)
        candidate_spec["source"]["commit"] = "1" * 40
        candidate_spec["source"]["tree"] = "2" * 40
        projection = pipeline.SourceCandidateContractProjection(
            core_id="81",
            candidate_id="3" * 64,
            canonical_commit=canonical_spec["source"]["commit"],
            canonical_tree=canonical_spec["source"]["tree"],
            candidate_commit=candidate_spec["source"]["commit"],
            candidate_tree=candidate_spec["source"]["tree"],
            canonical_spec_sha256=pipeline.core_spec_sha256(canonical_spec),
            execution_spec_sha256=pipeline.core_spec_sha256(candidate_spec),
            source_url=canonical_spec["source"]["url"],
            requested_ref=canonical_spec["source"]["requested_ref"],
        )
        shell = pipeline.container_build_script(
            "81",
            "arm64",
            candidate_spec,
            catalog["resolver"],
            source_candidate_contract_spec=canonical_spec,
            source_candidate_projection=projection,
        )
        self.assertIn("CORE_PIPELINE_GENERATED_SOURCE|src/version.c|sha256|", shell)
        self.assertIn(
            'actual_core_81_generated_sha256="$(sha256sum '
            "libretro-81/src/version.c",
            shell,
        )

    def test_candidate_recorded_source_binds_resolved_url_and_submodules(
        self,
    ) -> None:
        candidate_commit = "1" * 40
        candidate_tree = "2" * 40
        submodule_commit = "3" * 40
        projection = pipeline.SourceCandidateContractProjection(
            core_id="reminiscence",
            candidate_id="4" * 64,
            canonical_commit="5" * 40,
            canonical_tree="6" * 40,
            candidate_commit=candidate_commit,
            candidate_tree=candidate_tree,
            canonical_spec_sha256="7" * 64,
            execution_spec_sha256="8" * 64,
            source_url="https://example.invalid/core.git",
            requested_ref="refs/heads/main",
            candidate_submodules=(("deps/example", submodule_commit),),
        )
        recorded_source = {
            "url": projection.source_url,
            "resolved_url": projection.source_url,
            "requested_ref": projection.requested_ref,
            "commit": candidate_commit,
            "resolved_commit": candidate_commit,
            "tree": candidate_tree,
            "submodules": [
                {
                    "path": "deps/example",
                    "commit": submodule_commit,
                    "state": " ",
                },
                {
                    "path": "deps/example/nested",
                    "commit": "a" * 40,
                    "state": " ",
                }
            ],
        }
        self.assertTrue(
            pipeline._recorded_source_matches_source_candidate_projection(
                recorded_source,
                projection,
            )
        )
        for label, key, value in (
            ("resolved-url", "resolved_url", "https://example.invalid/tampered.git"),
            ("submodule-commit", "submodules", [
                {
                    "path": "deps/example",
                    "commit": "9" * 40,
                    "state": " ",
                },
                {
                    "path": "deps/example/nested",
                    "commit": "a" * 40,
                    "state": " ",
                }
            ]),
            ("submodule-state", "submodules", [
                {
                    "path": "deps/example",
                    "commit": submodule_commit,
                    "state": "+",
                },
                {
                    "path": "deps/example/nested",
                    "commit": "a" * 40,
                    "state": " ",
                }
            ]),
            ("foreign-recursive", "submodules", [
                {
                    "path": "deps/example",
                    "commit": submodule_commit,
                    "state": " ",
                },
                {
                    "path": "foreign/nested",
                    "commit": "a" * 40,
                    "state": " ",
                }
            ]),
        ):
            tampered = copy.deepcopy(recorded_source)
            tampered[key] = value
            with self.subTest(label=label):
                self.assertFalse(
                    pipeline._recorded_source_matches_source_candidate_projection(
                        tampered,
                        projection,
                    )
                )

    def test_current_picodrive_candidate_projects_frozen_lifecycle_guards(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        canonical_spec = catalog["cores"]["picodrive"]
        candidate_spec = copy.deepcopy(canonical_spec)
        candidate_commit = "6248b51ffbe212ce441de023ccea6b10fa4d7082"
        candidate_tree = "dd335a1e2430061a971b6f1e43b823ae40dce25d"
        candidate_epoch = 1785296835
        candidate_spec["source"]["commit"] = candidate_commit
        candidate_spec["source"]["tree"] = candidate_tree
        candidate_spec["build"]["source_date_epoch"] = candidate_epoch
        top_level = [
            item
            for item in PICODRIVE_SUBMODULES
            if not any(
                item["path"].startswith(f"{other['path']}/")
                for other in PICODRIVE_SUBMODULES
                if other is not item
            )
        ]
        projection = pipeline.SourceCandidateContractProjection(
            core_id="picodrive",
            candidate_id="a" * 64,
            canonical_commit=canonical_spec["source"]["commit"],
            canonical_tree=canonical_spec["source"]["tree"],
            candidate_commit=candidate_commit,
            candidate_tree=candidate_tree,
            canonical_spec_sha256=pipeline.core_spec_sha256(canonical_spec),
            execution_spec_sha256=pipeline.core_spec_sha256(candidate_spec),
            source_url=canonical_spec["source"]["url"],
            requested_ref=canonical_spec["source"]["requested_ref"],
            candidate_submodules=tuple(
                (item["path"], item["commit"])
                for item in top_level
            ),
            canonical_source_date_epoch=canonical_spec["build"][
                "source_date_epoch"
            ],
        )
        candidate_source = {
            "url": projection.source_url,
            "requested_ref": projection.requested_ref,
            "commit": candidate_commit,
            "tree": candidate_tree,
            "resolved_commit": candidate_commit,
            "resolved_url": projection.source_url,
            "submodules": copy.deepcopy(PICODRIVE_SUBMODULES),
        }
        candidate_build = pipeline.normalized_build_contract(
            candidate_spec,
            "arm64",
            core_id="picodrive",
            source_candidate_contract_spec=canonical_spec,
            source_candidate_projection=projection,
        )
        candidate_build.update(
            {"log": "build.log", "log_sha256": "b" * 64}
        )
        self.assertTrue(
            pipeline._recorded_source_matches_source_candidate_projection(
                candidate_source,
                projection,
            )
        )
        contract_source = pipeline._source_candidate_contract_source_for_guard(
            candidate_source,
            projection,
        )
        contract_build = pipeline._source_candidate_contract_build_for_guard(
            candidate_build,
            projection,
        )
        self.assertTrue(
            pipeline.picodrive_golden_source_is_well_formed(
                "picodrive",
                contract_source,
            )
        )
        self.assertTrue(
            pipeline.picodrive_golden_build_contract_is_well_formed(
                contract_build,
                projection.canonical_commit,
                "picodrive",
                contract_source,
                "arm64",
            )
        )

        missing_top = copy.deepcopy(candidate_source)
        missing_top["submodules"] = missing_top["submodules"][1:]
        self.assertFalse(
            pipeline._recorded_source_matches_source_candidate_projection(
                missing_top,
                projection,
            )
        )
        foreign_nested = copy.deepcopy(candidate_source)
        foreign_nested["submodules"].append(
            {"path": "foreign/nested", "commit": "c" * 40, "state": " "}
        )
        self.assertFalse(
            pipeline._recorded_source_matches_source_candidate_projection(
                foreign_nested,
                projection,
            )
        )
        wrong_nested = copy.deepcopy(candidate_source)
        nested = next(
            item
            for item in wrong_nested["submodules"]
            if item["path"].endswith("external/miniaudio")
        )
        nested["commit"] = "d" * 40
        tampered_contract_source = (
            pipeline._source_candidate_contract_source_for_guard(
                wrong_nested,
                projection,
            )
        )
        self.assertFalse(
            pipeline.picodrive_golden_source_is_well_formed(
                "picodrive",
                tampered_contract_source,
            )
        )

    def test_plain_catalog_validation_cannot_bypass_source_guard(self) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        candidate = copy.deepcopy(catalog)
        candidate["cores"] = {
            "reminiscence": copy.deepcopy(catalog["cores"]["reminiscence"])
        }
        candidate["cores"]["reminiscence"]["source"]["commit"] = "e" * 40
        candidate["cores"]["reminiscence"]["source"]["tree"] = "f" * 40
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "reminiscence core must preserve",
        ):
            pipeline.validate_catalog(candidate)

    def test_plain_catalog_validation_rejects_forged_candidate_provenance(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        catalog["source_candidate"] = {"candidate_id": "0" * 64}
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "ordinary catalog validation rejects source-candidate provenance",
        ):
            pipeline.validate_catalog(catalog)

    def test_deep_candidate_callback_keeps_nonprojected_candidates_valid(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        canonical_spec = copy.deepcopy(catalog["cores"]["easyrpg"])
        catalog["cores"] = {"easyrpg": canonical_spec}
        catalog["source_candidate"] = {"authenticated_by": "private caller"}
        pipeline._validate_source_candidate_execution_catalog(
            catalog,
            "easyrpg",
            canonical_spec,
            None,
        )

    def test_entrypoint_dispatch_validates_every_registered_callable(self) -> None:
        with mock.patch.object(
            pipeline, "cap32_log_proves_contract", None
        ), self.assertRaisesRegex(
            pipeline.PipelineError, "contains a non-callable"
        ):
            pipeline.registered_core_log_contract_proves(
                "log", "snes9x2005", "arm64"
            )


if __name__ == "__main__":
    unittest.main()
