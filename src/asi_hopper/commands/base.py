"""Command, Argument, Context, and Result: the vocabulary of the command layer (same shape as asi_dewey)."""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..hopper import Hopper


@dataclass
class Result:
    """Structured outcome of a command. Serialises to JSON for every transport."""

    ok: bool = True
    data: Any = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verb: str | None = None

    @classmethod
    def success(cls, data: Any = None, warnings: list[str] | tuple[str, ...] = (), verb: str | None = None) -> Result:
        return cls(True, data, [], list(warnings), verb)

    @classmethod
    def failure(cls, *errors: str, data: Any = None, verb: str | None = None) -> Result:
        return cls(False, data, list(errors), [], verb)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "verb": self.verb, "data": self.data, "errors": self.errors, "warnings": self.warnings}

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class Argument:
    """Declares one command argument; the CLI and ``schema`` output are built from these."""

    name: str
    help: str = ""
    required: bool = False
    flag: bool = False  # True: --option, False: positional
    type: str = "str"  # str | int | json | kv | path | bool
    choices: tuple[str, ...] = ()
    default: Any = None
    multiple: bool = False

    @property
    def dest(self) -> str:
        return self.name.replace("-", "_")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "help": self.help,
            "required": self.required,
            "flag": self.flag,
            "type": self.type,
            "choices": list(self.choices),
            "default": self.default,
            "multiple": self.multiple,
        }


@dataclass
class Context:
    hopper: Hopper
    actor: str = "python"


class Command(abc.ABC):
    verb: ClassVar[str] = ""
    help: ClassVar[str] = ""
    arguments: ClassVar[tuple[Argument, ...]] = ()
    writes: ClassVar[bool] = False  # no verb writes in 0.1.x; the flag is what policy will key on

    @abc.abstractmethod
    def run(self, ctx: Context, args: dict[str, Any]) -> Result: ...

    @classmethod
    def signature(cls) -> dict[str, Any]:
        return {
            "verb": cls.verb,
            "help": cls.help,
            "writes": cls.writes,
            "arguments": [a.to_dict() for a in cls.arguments],
        }


def parse_kv(items: Any) -> dict[str, Any]:
    """Turn ``["k=v", ...]`` (or a dict) into a dict."""
    if items is None:
        return {}
    if isinstance(items, dict):
        return dict(items)
    out: dict[str, Any] = {}
    for item in items:
        if "=" not in str(item):
            raise ValueError(f"expected key=value, got {item!r}")
        k, v = str(item).split("=", 1)
        out[k.strip()] = v
    return out
