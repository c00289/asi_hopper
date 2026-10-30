"""CLI front end: ``asi-hopper <verb> ...``. Built from the command signatures, prints a JSON Result."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..commands import CommandFactory, default_command_factory
from ..errors import HopperError
from ..gateway import default_gateway_factory
from ..version import __version__


def _bool(text: str) -> bool:
    return str(text).strip().lower() in {"1", "true", "yes", "y", "on"}


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from None


_TYPES = {"str": str, "path": str, "int": int, "json": _json, "kv": str, "bool": _bool}


def build_parser(factory: CommandFactory | None = None) -> argparse.ArgumentParser:
    factory = factory or default_command_factory
    parser = argparse.ArgumentParser(
        prog="asi-hopper",
        description="ASI Hopper: read-only door into Jira and Confluence. Every verb prints a JSON Result.",
    )
    parser.add_argument("--config", help="hopper.toml to use (default: $ASI_HOPPER_CONFIG or ./hopper.toml)")
    parser.add_argument("--gateway", choices=default_gateway_factory.kinds(), help="override the gateway kind")
    parser.add_argument("--fixtures", help="replay gateway: fixtures directory")
    parser.add_argument("--record", help="record every call into this fixtures directory")
    parser.add_argument("--site", help="override the Jira site URL")
    parser.add_argument("--non-interactive", action="store_true", help="never open a browser; fail if not logged in")
    parser.add_argument("--actor", default="cli", help="who is driving (recorded in every Result)")
    parser.add_argument("--compact", action="store_true", help="print single-line JSON")
    parser.add_argument("--version", action="version", version=f"asi-hopper {__version__}")
    sub = parser.add_subparsers(dest="verb", metavar="<verb>", required=True)
    for command in factory.commands():
        sp = sub.add_parser(command.verb, help=command.help, description=command.help)
        for arg in command.arguments:
            kwargs: dict[str, Any] = {"help": arg.help, "type": _TYPES.get(arg.type, str)}
            if arg.choices:
                kwargs["choices"] = list(arg.choices)
            if arg.flag:
                if arg.type == "bool":
                    sp.add_argument(
                        f"--{arg.name}", dest=arg.dest, action="store_true", default=arg.default, help=arg.help
                    )
                    continue
                if arg.multiple:
                    kwargs["action"] = "append"
                kwargs["default"] = arg.default
                kwargs["required"] = arg.required
                kwargs["dest"] = arg.dest
                sp.add_argument(f"--{arg.name}", **kwargs)
            else:
                if arg.multiple:
                    kwargs["nargs"] = "+" if arg.required else "*"
                elif not arg.required:
                    kwargs["nargs"] = "?"
                    kwargs["default"] = arg.default
                sp.add_argument(arg.dest, metavar=arg.name, **kwargs)
    return parser


def _print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:  # Windows consoles without UTF-8
        sys.stdout.buffer.write(text.encode("utf-8", "replace") + b"\n")


def main(argv: list[str] | None = None) -> int:
    from ..commands import Result
    from ..hopper import Hopper

    factory = default_command_factory
    parser = build_parser(factory)
    ns = parser.parse_args(argv)
    command = factory.get(ns.verb)
    args = {a.dest: getattr(ns, a.dest, None) for a in command.arguments}
    try:
        hopper = Hopper(
            ns.config,
            gateway=ns.gateway,
            fixtures=ns.fixtures,
            record=ns.record,
            site=ns.site,
            interactive=not ns.non_interactive,
        )
    except HopperError as exc:
        _print(Result.failure(str(exc), verb=ns.verb).to_json(indent=None if ns.compact else 2))
        return 2
    with hopper:
        result = hopper.execute(ns.verb, args, actor=ns.actor)
    _print(result.to_json(indent=None if ns.compact else 2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
