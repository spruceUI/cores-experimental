"""Public command-line construction API for the core pipeline."""

from .model import CommandHandler, ParserConfig, ParserHandlers, PathValue
from .parser import build_parser

__all__ = [
    "CommandHandler",
    "ParserConfig",
    "ParserHandlers",
    "PathValue",
    "build_parser",
]
