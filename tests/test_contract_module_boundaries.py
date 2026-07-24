from __future__ import annotations

from pathlib import Path
import unittest

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import bluemsx
from scripts.core_pipeline_lib.contracts import fmsx
from scripts.core_pipeline_lib.contracts import freeintv
from scripts.core_pipeline_lib.contracts import gearboy
from scripts.core_pipeline_lib.contracts import gearcoleco
from scripts.core_pipeline_lib.contracts import gearsystem
from scripts.core_pipeline_lib.contracts import genesis_plus_gx
from scripts.core_pipeline_lib.contracts import mednafen_lynx
from scripts.core_pipeline_lib.contracts import mednafen_ngp
from scripts.core_pipeline_lib.contracts import mednafen_pce_fast
from scripts.core_pipeline_lib.contracts import mednafen_pcfx
from scripts.core_pipeline_lib.contracts import mednafen_supergrafx
from scripts.core_pipeline_lib.contracts import mednafen_vb
from scripts.core_pipeline_lib.contracts import mednafen_wswan
from scripts.core_pipeline_lib.contracts import mgba
from scripts.core_pipeline_lib.contracts import pokemini
from scripts.core_pipeline_lib.contracts import potator
from scripts.core_pipeline_lib.contracts import race
from scripts.core_pipeline_lib.contracts import snes9x2005
from scripts.core_pipeline_lib.contracts import uzem
from scripts.core_pipeline_lib.contracts import vemulator
from scripts.core_pipeline_lib.contracts import vice_x64
from scripts.core_pipeline_lib.contracts import vice_xvic


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "scripts" / "core_pipeline_lib" / "contracts"


class ContractModuleBoundaryTests(unittest.TestCase):
    def test_potator_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            potator.POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.potator",
            pipeline.potator_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(potator, "POTATOR_CORE_IDS"))
        self.assertFalse(hasattr(potator, "potator_variant_log_proves_contract"))

    def test_race_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            race.RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.race",
            pipeline.race_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(race, "RACE_CORE_IDS"))
        self.assertFalse(hasattr(race, "race_variant_log_proves_contract"))

    def test_gearboy_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            gearboy.GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
            pipeline.GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.gearboy",
            pipeline.gearboy_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(gearboy, "GEARBOY_CORE_IDS"))
        self.assertFalse(
            hasattr(gearboy, "gearboy_variant_log_proves_contract")
        )

    def test_gearsystem_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
            pipeline.GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.gearsystem",
            pipeline.gearsystem_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(gearsystem, "GEARSYSTEM_CORE_IDS"))
        self.assertFalse(
            hasattr(gearsystem, "gearsystem_variant_log_proves_contract")
        )

    def test_uzem_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            uzem.UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.uzem",
            pipeline.uzem_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(uzem, "UZEM_CORE_IDS"))
        self.assertFalse(hasattr(uzem, "uzem_variant_log_proves_contract"))

    def test_vemulator_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            vemulator.VEMULATOR_SOURCE_IDENTITY_MARKER,
            pipeline.VEMULATOR_SOURCE_IDENTITY_MARKER,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.vemulator",
            pipeline.vemulator_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(vemulator, "VEMULATOR_CORE_IDS"))
        self.assertFalse(
            hasattr(vemulator, "vemulator_variant_log_proves_contract")
        )

    def test_mgba_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            mgba.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.mgba",
            pipeline.mgba_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(mgba, "MGBA_CORE_IDS"))
        self.assertFalse(hasattr(mgba, "mgba_variant_log_proves_contract"))

    def test_freeintv_contract_is_owned_by_its_individual_module(self) -> None:
        self.assertEqual(
            freeintv.FREEINTV_SOURCE_IDENTITY_MARKER,
            pipeline.FREEINTV_SOURCE_IDENTITY_MARKER,
        )
        self.assertEqual(
            "core_pipeline_lib.contracts.freeintv",
            pipeline.freeintv_log_proves_contract.__module__,
        )
        self.assertFalse(hasattr(freeintv, "FREEINTV_CORE_IDS"))
        self.assertFalse(
            hasattr(freeintv, "freeintv_variant_log_proves_contract")
        )

    def test_removed_multi_core_facade_modules_do_not_return(self) -> None:
        for module_name in (
            "cpc.py",
            "handy_stella.py",
            "mednafen_wswan_pcfx.py",
        ):
            with self.subTest(module=module_name):
                self.assertFalse((CONTRACTS / module_name).exists())

    def test_pipeline_exports_only_individual_contract_symbols(self) -> None:
        aggregate_names = (
            "CPC_CORE_IDS",
            "CPC_SOURCE_IDENTITIES",
            "cpc_variant_log_proves_contract",
            "handy_stella_variant_log_proves_contract",
            "GENESIS_PLUS_GX_CORE_IDS",
            "GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITIES",
            "genesis_plus_gx_variant_log_proves_contract",
            "SNES9X2005_CORE_IDS",
            "SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITIES",
            "snes9x2005_variant_log_proves_contract",
            "pcfx_combined_golden_build_contract_is_well_formed",
            "VICE_NATIVE_GIT_VERSION_SOURCE_IDENTITY",
            "VICE_NATIVE_GIT_VERSION_SPEC_IDENTITIES",
        )
        for name in aggregate_names:
            with self.subTest(name=name):
                self.assertFalse(hasattr(pipeline, name))

    def test_individual_modules_have_no_family_maps_or_dispatch(self) -> None:
        for module, names in (
            (
                genesis_plus_gx,
                (
                    "GENESIS_PLUS_GX_CORE_IDS",
                    "GENESIS_PLUS_GX_EXPECTED_C_COMPILE_COUNTS",
                    "GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "genesis_plus_gx_variant_log_proves_contract",
                ),
            ),
            (
                mednafen_vb,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                ),
            ),
            (
                mednafen_ngp,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                ),
            ),
            (
                mednafen_lynx,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                ),
            ),
            (
                mednafen_pcfx,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                    "pcfx_combined_golden_build_contract_is_well_formed",
                ),
            ),
            (
                mednafen_supergrafx,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                ),
            ),
            (
                mednafen_pce_fast,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                ),
            ),
            (
                mednafen_wswan,
                (
                    "MEDNAFEN_CORE_IDS",
                    "mednafen_variant_log_proves_contract",
                ),
            ),
            (
                pokemini,
                (
                    "NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "pokemini_variant_log_proves_contract",
                ),
            ),
            (
                gearboy,
                (
                    "NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES",
                    "gearboy_variant_log_proves_contract",
                ),
            ),
            (
                gearsystem,
                (
                    "NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES",
                    "gearsystem_variant_log_proves_contract",
                ),
            ),
            (
                gearcoleco,
                (
                    "NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES",
                    "gearcoleco_variant_log_proves_contract",
                ),
            ),
            (
                uzem,
                (
                    "NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "uzem_variant_log_proves_contract",
                ),
            ),
            (
                vemulator,
                (
                    "SOURCE_NATIVE_SPEC_IDENTITIES",
                    "vemulator_variant_log_proves_contract",
                ),
            ),
            (
                mgba,
                (
                    "NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "mgba_variant_log_proves_contract",
                ),
            ),
            (
                freeintv,
                (
                    "SOURCE_NATIVE_SPEC_IDENTITIES",
                    "freeintv_variant_log_proves_contract",
                ),
            ),
            (
                fmsx,
                (
                    "NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "msx_variant_log_proves_contract",
                ),
            ),
            (
                bluemsx,
                (
                    "NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "msx_variant_log_proves_contract",
                ),
            ),
            (
                vice_x64,
                (
                    "VICE_CORE_IDS",
                    "VICE_NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "vice_variant_log_proves_contract",
                ),
            ),
            (
                vice_xvic,
                (
                    "VICE_CORE_IDS",
                    "VICE_NATIVE_GIT_VERSION_SPEC_IDENTITIES",
                    "vice_variant_log_proves_contract",
                ),
            ),
            (
                snes9x2005,
                (
                    "snes9x2005_variant_log_markers",
                    "snes9x2005_variant_shell",
                ),
            ),
        ):
            for name in names:
                with self.subTest(module=module.__name__, name=name):
                    self.assertFalse(hasattr(module, name))


if __name__ == "__main__":
    unittest.main()
