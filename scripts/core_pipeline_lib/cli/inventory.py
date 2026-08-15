"""Read-only core-track inventory command registration."""

from __future__ import annotations

import argparse

from ..chipsets import CHIPSETS
from ..tracks import CORE_TRACKS, TRACK_MARKERS, canonical_group_tag
from .model import AppendUniqueAction, ParserHandlers


CORE_TRACK_GROUP_TAG_CHOICES = tuple(
    canonical_group_tag(track, marker, chipset)
    for track in CORE_TRACKS
    for marker in TRACK_MARKERS
    for chipset in CHIPSETS
)


def register_inventory_parser(
    subparsers: argparse._SubParsersAction,
    *,
    handlers: ParserHandlers,
) -> None:
    """Register deterministic resolution of one exact core-track group."""

    inventory = subparsers.add_parser(
        "core-track-inventory",
        help="resolve one pinned track, stability marker, and chipset inventory",
    )
    inventory.add_argument(
        "--group-tag",
        choices=CORE_TRACK_GROUP_TAG_CHOICES,
        required=True,
        help="exact <track>-<stable|test>:<chipset> selector",
    )
    inventory.add_argument(
        "--core",
        action=AppendUniqueAction,
        help="optional catalog core selector; repeat only for unique cores",
    )
    inventory.set_defaults(handler=handlers.core_track_inventory)
