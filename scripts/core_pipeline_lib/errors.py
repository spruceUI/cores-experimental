"""Shared exception types for pipeline contract failures."""


class PipelineError(RuntimeError):
    """A user-facing contract or build failure."""
