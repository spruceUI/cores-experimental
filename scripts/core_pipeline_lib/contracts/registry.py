"""Declarative registry for individual-core build-log proof contracts.

The registry stores proof names rather than callables. The composition root
binds those names to the individual proof callables so focused boundary tests
can replace one proof at a time. New cores register one singleton contract here
and put their parser/proof implementation in a core-named sibling module.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


CONTRACT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*-v[1-9][0-9]*$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
PROOF_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ProofKind = Literal["core-arch", "core-arch-source"]


@dataclass(frozen=True, slots=True)
class CoreLogContract:
    """One exact build-log proof owned by one core."""

    contract_id: str
    core_ids: frozenset[str]
    proof_name: str
    proof_kind: ProofKind
    failure_message: str

    def __post_init__(self) -> None:
        if CONTRACT_ID_RE.fullmatch(self.contract_id) is None:
            raise ValueError("core log contract ID is malformed")
        if len(self.core_ids) != 1 or any(
            CORE_ID_RE.fullmatch(core_id) is None for core_id in self.core_ids
        ):
            raise ValueError(
                "core log contract must own exactly one well-formed core ID"
            )
        if PROOF_NAME_RE.fullmatch(self.proof_name) is None:
            raise ValueError("core log contract proof name is malformed")
        if self.proof_kind not in {"core-arch", "core-arch-source"}:
            raise ValueError("core log contract proof kind is malformed")
        if not self.failure_message.strip():
            raise ValueError("core log contract failure message is empty")


CORE_LOG_CONTRACTS = (
    CoreLogContract(
        contract_id="mame2003-plus-c-only-v1",
        core_ids=frozenset({"mame2003_plus"}),
        proof_name="mame2003_plus_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove MAME 2003-Plus's exact source-native "
            "1807-command C compile argv, visible clean, ordered C link, "
            "source framing, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="picodrive-source-root-v1",
        core_ids=frozenset({"picodrive"}),
        proof_name="picodrive_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Picodrive's exact source-root C/assembly "
            "compile argv, ordered C link, native Cyclone generator, and "
            "reviewed-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="fbneo-mixed-language-v1",
        core_ids=frozenset({"fbneo"}),
        proof_name="fbneo_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove FBNeo's exact 61-C/1029-C++ compile argv "
            "and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="ecwolf-mixed-language-v1",
        core_ids=frozenset({"ecwolf"}),
        proof_name="ecwolf_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove ECWolf's exact 79-C/134-C++ compile argv "
            "and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="neocd-mixed-language-v1",
        core_ids=frozenset({"neocd"}),
        proof_name="neocd_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove NeoCD's exact 86-C/43-C++ compile argv "
            "and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="pcsx-rearmed-c-asm-v1",
        core_ids=frozenset({"pcsx_rearmed"}),
        proof_name="pcsx_rearmed_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove PCSX ReARMed's exact per-arch C and "
            "assembly compile argv and ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="gpsp-c-asm-v1",
        core_ids=frozenset({"gpsp"}),
        proof_name="gpsp_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove gpSP's exact per-arch C, C++, and "
            "assembly compile argv and ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="libgametank-cargo-v1",
        core_ids=frozenset({"libgametank"}),
        proof_name="libgametank_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove the exact Cargo.lock digest, zigbuild "
            "invocation, and 69-crate compiled multiset"
        ),
    ),
    CoreLogContract(
        contract_id="km-parallel-n64-c-asm-v1",
        core_ids=frozenset({"km_parallel_n64_xtreme_amped_turbo"}),
        proof_name="km_parallel_n64_xtreme_amped_turbo_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove the KM parallel-n64 fork's exact C, "
            "C++, and assembly compile argv and ordered GLES C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="yabasanshiro-c-asm-v2",
        core_ids=frozenset({"yabasanshiro"}),
        proof_name="yabasanshiro_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove YabaSanshiro's exact C, C++, and "
            "assembly compile argv and ordered GLES C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="snes9x2010-c-only-v1",
        core_ids=frozenset({"snes9x2010"}),
        proof_name="snes9x2010_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Snes9x 2010's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="snes9x2002-c-only-v1",
        core_ids=frozenset({"snes9x2002"}),
        proof_name="snes9x2002_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Snes9x 2002's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="tyrquake-c-only-v1",
        core_ids=frozenset({"tyrquake"}),
        proof_name="tyrquake_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove TyrQuake's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="prboom-c-only-v1",
        core_ids=frozenset({"prboom"}),
        proof_name="prboom_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove PrBoom's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="fuse-c-only-v1",
        core_ids=frozenset({"fuse"}),
        proof_name="fuse_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Fuse's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="gme-mixed-language-v1",
        core_ids=frozenset({"gme"}),
        proof_name="gme_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove gme's exact mixed C/C++ compile argv "
            "and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="frodo-mixed-language-v1",
        core_ids=frozenset({"frodo"}),
        proof_name="frodo_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Frodo's exact mixed C/C++ compile argv "
            "and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="quasi88-mixed-language-v1",
        core_ids=frozenset({"quasi88"}),
        proof_name="quasi88_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove QUASI88's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="retro8-mixed-language-v1",
        core_ids=frozenset({"retro8"}),
        proof_name="retro8_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove retro8's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="reminiscence-mixed-language-v1",
        core_ids=frozenset({"reminiscence"}),
        proof_name="reminiscence_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove REminiscence's exact mixed C/C++ "
            "compile argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="gw-c-only-v1",
        core_ids=frozenset({"gw"}),
        proof_name="gw_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove gw's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="mu-mixed-language-v1",
        core_ids=frozenset({"mu"}),
        proof_name="mu_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mu's exact mixed C/C++ compile argv "
            "and ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="hatari-c-only-v1",
        core_ids=frozenset({"hatari"}),
        proof_name="hatari_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Hatari's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="theodore-c-only-v1",
        core_ids=frozenset({"theodore"}),
        proof_name="theodore_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Theodore's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="bk-c-only-v1",
        core_ids=frozenset({"bk"}),
        proof_name="bk_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove BK's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="numero-mixed-language-v1",
        core_ids=frozenset({"numero"}),
        proof_name="numero_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Numero's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="opera-c-only-v1",
        core_ids=frozenset({"opera"}),
        proof_name="opera_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Opera's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="fbalpha2012-mixed-language-v1",
        core_ids=frozenset({"fbalpha2012"}),
        proof_name="fbalpha2012_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove FB Alpha 2012's exact mixed C/C++ "
            "compile argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="chimerasnes-c-only-v1",
        core_ids=frozenset({"chimerasnes"}),
        proof_name="chimerasnes_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove ChimeraSNES's exact C compile argv "
            "and ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="px68k-mixed-language-v1",
        core_ids=frozenset({"px68k"}),
        proof_name="px68k_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove PX68K's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="x1-mixed-language-v1",
        core_ids=frozenset({"x1"}),
        proof_name="x1_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove X1's exact all-C compile argv and "
            "ordered C++-driver link"
        ),
    ),
    CoreLogContract(
        contract_id="daphne-mixed-language-v1",
        core_ids=frozenset({"daphne"}),
        proof_name="daphne_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Daphne's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="uae4arm-mixed-language-v1",
        core_ids=frozenset({"uae4arm"}),
        proof_name="uae4arm_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove UAE4ARM's exact armhf mixed C/C++ "
            "compile argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="puae2021-c-only-v1",
        core_ids=frozenset({"puae2021"}),
        proof_name="puae2021_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove PUAE 2021's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="lutro-c-only-archive-v1",
        core_ids=frozenset({"lutro"}),
        proof_name="lutro_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Lutro's exact C compile argv, Lua "
            "archive membership, and ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="np2kai-mixed-language-v1",
        core_ids=frozenset({"np2kai"}),
        proof_name="np2kai_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove NP2kai's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="sameduck-c-only-v1",
        core_ids=frozenset({"sameduck"}),
        proof_name="sameduck_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove SameDuck's exact C compile argv, "
            "ordered C link, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="puzzlescript-mixed-language-v1",
        core_ids=frozenset({"puzzlescript"}),
        proof_name="puzzlescript_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove PuzzleScript's exact mixed C/C++ "
            "compile argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="fake08-mixed-language-v1",
        core_ids=frozenset({"fake08"}),
        proof_name="fake08_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove fake-08's exact mixed C/C++ compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="uw8-c-only-v1",
        core_ids=frozenset({"uw8"}),
        proof_name="uw8_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove uw8's exact C compile argv and "
            "ordered C link"
        ),
    ),
    CoreLogContract(
        contract_id="mupen64plus-next-c-asm-v1",
        core_ids=frozenset({"mupen64plus_next"}),
        proof_name="mupen64plus_next_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mupen64Plus-Next's exact per-arch C, "
            "C++, and assembly compile argv and ordered GLES C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="parallel-n64-c-asm-v1",
        core_ids=frozenset({"parallel_n64"}),
        proof_name="parallel_n64_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Parallel N64's exact per-arch C, C++, "
            "and assembly compile argv and ordered GLES C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="dosbox-pure-mixed-language-v1",
        core_ids=frozenset({"dosbox_pure"}),
        proof_name="dosbox_pure_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove DOSBox Pure's exact 112-C++ compile argv "
            "and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="chailove-c-asm-v1",
        core_ids=frozenset({"chailove"}),
        proof_name="chailove_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove ChaiLove's exact C/C++/assembly compile "
            "argv and ordered C++ link"
        ),
    ),
    CoreLogContract(
        contract_id="atari800-c-only-v1",
        core_ids=frozenset({"atari800"}),
        proof_name="atari800_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Atari800's exact C-only native-version "
            "compile argv, ordered link, and reviewed-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="snes9x2005-c-only-v1",
        core_ids=frozenset({"snes9x2005"}),
        proof_name="snes9x2005_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Snes9x 2005's exact source, default "
            "APU, native-version C compile argv, C link, and reviewed "
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="snes9x2005-plus-c-only-v1",
        core_ids=frozenset({"snes9x2005_plus"}),
        proof_name="snes9x2005_plus_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Snes9x 2005 Plus's exact source, "
            "Blargg APU, native-version C compile argv, C link, and "
            "reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="cap32-make-trace-v1",
        core_ids=frozenset({"cap32"}),
        proof_name="cap32_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Cap32's exact make trace and C-only "
            "compile contract"
        ),
    ),
    CoreLogContract(
        contract_id="crocods-c-only-v1",
        core_ids=frozenset({"crocods"}),
        proof_name="crocods_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove CrocoDS's exact C argv, link-object, "
            "and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="genesis-plus-gx-c-link-v1",
        core_ids=frozenset({"genesis_plus_gx"}),
        proof_name="genesis_plus_gx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Genesis Plus GX's exact source, C argv, "
            "ordered link, diagnostics, and success contract"
        ),
    ),
    CoreLogContract(
        contract_id="genesis-plus-gx-wide-c-link-v1",
        core_ids=frozenset({"genesis_plus_gx_wide"}),
        proof_name="genesis_plus_gx_wide_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Genesis Plus GX Wide's exact source, "
            "C argv, ordered link, diagnostics, and success contract"
        ),
    ),
    CoreLogContract(
        contract_id="fceumm-c-only-v1",
        core_ids=frozenset({"fceumm"}),
        proof_name="fceumm_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove FCEUmm's exact C-only compile argv "
            "and link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="gambatte-mixed-language-v1",
        core_ids=frozenset({"gambatte"}),
        proof_name="gambatte_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Gambatte's exact mixed-language compile "
            "argv and link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="tgbdual-cxx-link-v1",
        core_ids=frozenset({"tgbdual"}),
        proof_name="tgbdual_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove TGB Dual's exact C++ compile argv "
            "and link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="quicknes-cxx-link-v1",
        core_ids=frozenset({"quicknes"}),
        proof_name="quicknes_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove QuickNES's exact C++ compile argv "
            "and link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="nestopia-cxx-link-v1",
        core_ids=frozenset({"nestopia"}),
        proof_name="nestopia_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Nestopia's exact C++ compile argv "
            "and link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="a5200-c-only-v1",
        core_ids=frozenset({"a5200"}),
        proof_name="a5200_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove A5200's exact C compile argv "
            "and raw/semantic link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="prosystem-c-only-v1",
        core_ids=frozenset({"prosystem"}),
        proof_name="prosystem_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove ProSystem's exact C compile argv, "
            "C link, and reviewed warning contract"
        ),
    ),
    CoreLogContract(
        contract_id="snes9x-mixed-language-v1",
        core_ids=frozenset({"snes9x"}),
        proof_name="snes9x_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Snes9x's exact mixed-language compile "
            "argv, C++ link, and reviewed warning contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-supafaust-cxx-link-v1",
        core_ids=frozenset({"mednafen_supafaust"}),
        proof_name="mednafen_supafaust_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen Supafaust's exact C++ compile "
            "argv, link-object, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-wswan-mixed-language-v1",
        core_ids=frozenset({"mednafen_wswan"}),
        proof_name="mednafen_wswan_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen WonderSwan's exact mixed-"
            "language compile argv, C++ link, native version, and reviewed "
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-vb-mixed-language-v1",
        core_ids=frozenset({"mednafen_vb"}),
        proof_name="mednafen_vb_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen Virtual Boy's exact 10-C/"
            "3-C++ compile argv, all-compiler native version, ordered C++ "
            "link, success, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-ngp-mixed-language-v1",
        core_ids=frozenset({"mednafen_ngp"}),
        proof_name="mednafen_ngp_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen Neo Geo Pocket's exact 32-C/"
            "5-C++ compile argv, native-version multiplicity, ordered C++ "
            "link, success, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-lynx-mixed-language-v1",
        core_ids=frozenset({"mednafen_lynx"}),
        proof_name="mednafen_lynx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen Lynx's exact 13-C/16-C++ "
            "compile argv, C++-only native version, ordered C++ link, success, "
            "and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-pcfx-mixed-language-v1",
        core_ids=frozenset({"mednafen_pcfx"}),
        proof_name="mednafen_pcfx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen PC-FX's exact mixed-language "
            "compile argv, C++ link, portable make variables, native version, "
            "and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-supergrafx-mixed-language-v1",
        core_ids=frozenset({"mednafen_supergrafx"}),
        proof_name="mednafen_supergrafx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen SuperGrafx's exact 60-C/29-C++ "
            "compile argv, C++-only native version, ordered C++ link, success, "
            "and reviewed parallel diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mednafen-pce-fast-c-only-v1",
        core_ids=frozenset({"mednafen_pce_fast"}),
        proof_name="mednafen_pce_fast_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Mednafen PCE Fast's exact 92-command C "
            "compile argv, ordered C++ link, source, success, and zero-"
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="pokemini-c-only-v1",
        core_ids=frozenset({"pokemini"}),
        proof_name="pokemini_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove PokéMini's exact native-version C "
            "compile argv, C link, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="mgba-c-only-v1",
        core_ids=frozenset({"mgba"}),
        proof_name="mgba_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove mGBA's exact native-version C compile "
            "argv, ordered C link, source framing, and reviewed diagnostic "
            "contract"
        ),
    ),
    CoreLogContract(
        contract_id="uzem-mixed-language-v1",
        core_ids=frozenset({"uzem"}),
        proof_name="uzem_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Uzem's exact native-version 12-C/6-C++ "
            "compile argv, ordered C++ link, source framing, and reviewed "
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="vemulator-mixed-language-v1",
        core_ids=frozenset({"vemulator"}),
        proof_name="vemulator_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove VEmulator's exact source-native 13-C/"
            "14-C++ compile argv, ordered C++ link, source framing, and "
            "reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="gearboy-mixed-language-v1",
        core_ids=frozenset({"gearboy"}),
        proof_name="gearboy_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Gearboy's exact native-describe "
            "1-C/39-C++ compile argv, ordered C++ link, source framing, and "
            "zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="gearsystem-mixed-language-v1",
        core_ids=frozenset({"gearsystem"}),
        proof_name="gearsystem_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Gearsystem's exact native-describe "
            "2-C/44-C++ compile argv, ordered C++ link, source framing, and "
            "zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="gearcoleco-mixed-language-v1",
        core_ids=frozenset({"gearcoleco"}),
        proof_name="gearcoleco_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove GearColeco's exact native-describe "
            "mixed-language compile argv, C++ link, and reviewed warning "
            "contract"
        ),
    ),
    CoreLogContract(
        contract_id="fmsx-c-only-v1",
        core_ids=frozenset({"fmsx"}),
        proof_name="fmsx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove fMSX's exact native-version C compile "
            "argv, C link, and zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="bluemsx-mixed-language-v1",
        core_ids=frozenset({"bluemsx"}),
        proof_name="bluemsx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove blueMSX's exact C-scoped native "
            "version, mixed-language compile argv, warning suppression, "
            "and C++ link contract"
        ),
    ),
    CoreLogContract(
        contract_id="core-2048-c-only-v1",
        core_ids=frozenset({"2048"}),
        proof_name="core_2048_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove 2048's exact source framing, C-scoped "
            "native version, 16-command C compile argv, ordered C link, "
            "zero-diagnostic contract, and successful lifecycle"
        ),
    ),
    CoreLogContract(
        contract_id="core-81-mixed-language-v1",
        core_ids=frozenset({"81"}),
        proof_name="core_81_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove EightyOne's native generated-version "
            "source, exact 16-C/12-C++ argv, ordered C++ link, and reviewed "
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="lowresnx-c-only-v1",
        core_ids=frozenset({"lowresnx"}),
        proof_name="lowresnx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove LowRes NX's exact C-scoped native "
            "version, parent-relative C compile argv, raw/semantic link "
            "objects, and zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="potator-c-only-v1",
        core_ids=frozenset({"potator"}),
        proof_name="potator_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Potator's exact C-scoped native version, "
            "8-command C compile argv, ordered C link, source framing, and "
            "reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="race-c-only-v1",
        core_ids=frozenset({"race"}),
        proof_name="race_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove RACE's exact C-scoped native version, "
            "27-command C compile argv, ordered C link, source framing, and "
            "zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="vice-x64-mixed-language-v1",
        core_ids=frozenset({"vice_x64"}),
        proof_name="vice_x64_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove VICE x64's exact native-short10 "
            "mixed-language compile argv, C++ link, epoch, and zero-"
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="vice-xvic-mixed-language-v1",
        core_ids=frozenset({"vice_xvic"}),
        proof_name="vice_xvic_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove VICE xvic's exact native-short10 "
            "mixed-language compile argv, C++ link, epoch, and zero-"
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="o2em-c-only-v1",
        core_ids=frozenset({"o2em"}),
        proof_name="o2em_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove O2EM's exact native-version C compile "
            "argv, raw/semantic link-object, and zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="freechaf-c-only-v1",
        core_ids=frozenset({"freechaf"}),
        proof_name="freechaf_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove FreeChaF's exact C compile argv, "
            "link-object, and reviewed diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="freeintv-c-only-v1",
        core_ids=frozenset({"freeintv"}),
        proof_name="freeintv_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove FreeIntv's exact source-native C "
            "compile argv, ordered C link, source framing, and reviewed "
            "diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="vecx-software-c-only-v1",
        core_ids=frozenset({"vecx"}),
        proof_name="vecx_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove VecX's exact software-renderer C "
            "compile argv, link-object, marker, and zero-diagnostic contract"
        ),
    ),
    CoreLogContract(
        contract_id="handy-mixed-language-v1",
        core_ids=frozenset({"handy"}),
        proof_name="handy_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Handy's exact mixed-language compile "
            "argv and link-object contract"
        ),
    ),
    CoreLogContract(
        contract_id="stella2014-mixed-language-v1",
        core_ids=frozenset({"stella2014"}),
        proof_name="stella2014_log_proves_contract",
        proof_kind="core-arch-source",
        failure_message=(
            "build log does not prove Stella 2014's exact mixed-language "
            "compile argv and link-object contract"
        ),
    ),
)


def _registry_by_core() -> dict[str, CoreLogContract]:
    result: dict[str, CoreLogContract] = {}
    contract_ids: set[str] = set()
    proof_names: set[str] = set()
    for contract in CORE_LOG_CONTRACTS:
        if contract.contract_id in contract_ids:
            raise ValueError(f"duplicate core log contract ID: {contract.contract_id}")
        if contract.proof_name in proof_names:
            raise ValueError(f"duplicate core log proof name: {contract.proof_name}")
        contract_ids.add(contract.contract_id)
        proof_names.add(contract.proof_name)
        for core_id in contract.core_ids:
            if core_id in result:
                raise ValueError(f"duplicate core log contract for {core_id}")
            result[core_id] = contract
    return result


_CORE_LOG_CONTRACT_BY_CORE = _registry_by_core()


def core_log_contract_for(core_id: object) -> CoreLogContract | None:
    if not isinstance(core_id, str):
        return None
    return _CORE_LOG_CONTRACT_BY_CORE.get(core_id)


def registered_core_log_contract_ids() -> frozenset[str]:
    return frozenset(_CORE_LOG_CONTRACT_BY_CORE)
