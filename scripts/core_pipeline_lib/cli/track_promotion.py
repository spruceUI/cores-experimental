"""Canonical stable-promotion command registration."""

from __future__ import annotations

import argparse

from ..chipsets import CHIPSETS
from ..tracks import CORE_TRACKS
from .model import ParserHandlers


def register_track_promotion_parser(
    subparsers: argparse._SubParsersAction,
    *,
    handlers: ParserHandlers,
) -> None:
    promotion = subparsers.add_parser(
        "core-track-promote",
        help="approve one exact effective TEST cell as track-local stable",
    )
    promotion.add_argument("--track", choices=CORE_TRACKS, required=True)
    promotion.add_argument("--core", required=True)
    promotion.add_argument("--chipset", choices=CHIPSETS, required=True)
    promotion.add_argument("--approved-by", required=True)
    promotion.add_argument("--reason", required=True)
    promotion.add_argument(
        "--expected-test-variant",
        required=True,
        help="reviewed 64-hex TEST variant identity used as a compare-and-swap gate",
    )
    promotion.add_argument(
        "--expected-current-stable",
        required=True,
        metavar="absent|SHA256",
        help=(
            "reviewed current stable state: literal 'absent' or its exact "
            "64-hex variant identity"
        ),
    )
    promotion.add_argument(
        "--approved-at",
        help="optional exact UTC YYYY-MM-DDTHH:MM:SSZ timestamp",
    )
    promotion.set_defaults(handler=handlers.core_track_promote)
