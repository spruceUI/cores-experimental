"""Runner-profile resolution for local and GitHub Actions execution.

Runner profiles describe where the shared build implementation is running.
They are deliberately separate from the device execution profiles that
describe where a compiled core may eventually run.
"""

from .errors import RunnerProfileError
from .model import RunnerContext, RunnerRequest
from .resolve import resolve_runner_context
from .evidence import runner_evidence, runner_evidence_is_well_formed

__all__ = [
    "RunnerContext",
    "RunnerProfileError",
    "RunnerRequest",
    "resolve_runner_context",
    "runner_evidence",
    "runner_evidence_is_well_formed",
]
