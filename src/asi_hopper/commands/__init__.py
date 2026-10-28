"""The command layer: one path for the CLI, the Python API, scripts, and agents."""

from . import read as _read  # noqa: F401  (registers the verbs)
from .base import Argument, Command, Context, Result, parse_kv
from .dispatcher import Dispatcher
from .factory import CommandFactory, default_command_factory, register_command

__all__ = [
    "Argument",
    "Command",
    "CommandFactory",
    "Context",
    "Dispatcher",
    "Result",
    "default_command_factory",
    "parse_kv",
    "register_command",
]
