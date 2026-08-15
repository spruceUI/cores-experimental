"""Explicit immutable dependencies for the core-pipeline command line."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


CommandHandler = Callable[[argparse.Namespace], int]
PathValue = Callable[[str], Path]


class AppendUniqueAction(argparse.Action):
    """Append one selector value while rejecting duplicates."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        selected = list(getattr(namespace, self.dest, None) or ())
        if values in selected:
            parser.error(f"{option_string} value may be specified only once: {values}")
        selected.append(values)
        setattr(namespace, self.dest, selected)


def _choice_tuple(label: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} choices must be an iterable of strings")
    choices = tuple(values)
    if not choices:
        raise ValueError(f"{label} choices must not be empty")
    if any(not isinstance(choice, str) or not choice for choice in choices):
        raise ValueError(f"{label} choices must be non-empty strings")
    if len(set(choices)) != len(choices):
        raise ValueError(f"{label} choices must be unique")
    return choices


@dataclass(frozen=True, slots=True)
class ParserHandlers:
    """Entrypoint-owned command handlers bound by the CLI parser."""

    catalog_check: CommandHandler
    core_source_candidate_rebase: CommandHandler
    core_source_candidate_prepare: CommandHandler
    core_track_inventory: CommandHandler
    core_track_promote: CommandHandler
    core_track_plan_test: CommandHandler
    core_track_set_test: CommandHandler
    audit_workflows: CommandHandler
    import_golden: CommandHandler
    validate_golden: CommandHandler
    build: CommandHandler
    build_core: CommandHandler
    e2e: CommandHandler
    promote: CommandHandler
    promote_host_reproduction: CommandHandler
    promote_source_candidate: CommandHandler
    promote_tuned_variant: CommandHandler
    derive_core_id: CommandHandler
    compose_core_golden: CommandHandler
    compose_pin_set: CommandHandler
    validate_pin_set: CommandHandler
    promote_release: CommandHandler
    validate_release: CommandHandler
    update_channel: CommandHandler
    validate_channel: CommandHandler
    prepare_release_source_graph: CommandHandler
    convert_release_overlay: CommandHandler
    plan_release: CommandHandler
    release_matrix: CommandHandler
    record_release_result: CommandHandler
    seal_release: CommandHandler

    def __post_init__(self) -> None:
        handler_names = (
            "catalog_check",
            "core_source_candidate_rebase",
            "core_source_candidate_prepare",
            "core_track_inventory",
            "core_track_promote",
            "core_track_plan_test",
            "core_track_set_test",
            "audit_workflows",
            "import_golden",
            "validate_golden",
            "build",
            "build_core",
            "e2e",
            "promote",
            "promote_host_reproduction",
            "promote_source_candidate",
            "promote_tuned_variant",
            "derive_core_id",
            "compose_core_golden",
            "compose_pin_set",
            "validate_pin_set",
            "promote_release",
            "validate_release",
            "update_channel",
            "validate_channel",
            "prepare_release_source_graph",
            "convert_release_overlay",
            "plan_release",
            "release_matrix",
            "record_release_result",
            "seal_release",
        )
        for name in handler_names:
            if not callable(getattr(self, name)):
                raise TypeError(f"{name} handler must be callable")


@dataclass(frozen=True, slots=True)
class ParserConfig:
    """Paths, converters, and finite choices supplied by the entrypoint."""

    description: str | None
    path_value: PathValue
    default_catalog: Path
    default_runs: Path
    default_spruceos: Path
    arch_choices: tuple[str, ...]
    runner_profile_choices: tuple[str, ...]
    default_runner_profile: str
    channel_choices: tuple[str, ...]
    release_scope_choices: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("parser description must be a string or None")
        if not callable(self.path_value):
            raise TypeError("path_value must be callable")
        for name in (
            "default_catalog",
            "default_runs",
            "default_spruceos",
        ):
            if not isinstance(getattr(self, name), Path):
                raise TypeError(f"{name} must be a Path")
        object.__setattr__(
            self,
            "arch_choices",
            _choice_tuple("architecture", self.arch_choices),
        )
        object.__setattr__(
            self,
            "runner_profile_choices",
            _choice_tuple("runner profile", self.runner_profile_choices),
        )
        if self.default_runner_profile not in self.runner_profile_choices:
            raise ValueError("default runner profile must be one of its choices")
        object.__setattr__(
            self,
            "channel_choices",
            _choice_tuple("channel", self.channel_choices),
        )
        object.__setattr__(
            self,
            "release_scope_choices",
            _choice_tuple("release scope", self.release_scope_choices),
        )
