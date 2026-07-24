from __future__ import annotations

import unittest

from tests import expected_counts
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import (
    CORE_LOG_CONTRACTS,
    CoreLogContract,
    core_log_contract_for,
    registered_core_log_contract_ids,
)


class CoreLogContractRegistryTests(unittest.TestCase):
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
