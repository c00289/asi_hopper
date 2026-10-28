"""ReplayGateway: serves recorded payloads from a fixtures directory. Unrecorded calls raise, never hit the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import ConfigError, NotRecorded
from .base import canonical_args

INDEX_NAME = "index.json"


class ReplayGateway:
    name = "replay"

    def __init__(self, fixtures: str | Path) -> None:
        self.root = Path(fixtures)
        index_path = self.root / INDEX_NAME
        if not index_path.is_file():
            raise ConfigError(f"no {INDEX_NAME} in fixtures directory {self.root}")
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{index_path}: {exc}") from None
        self._index: dict[tuple[str, str], str] = {}
        for entry in entries:
            self._index[(entry["tool"], canonical_args(entry.get("args") or {}))] = entry["file"]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, args: dict[str, Any]) -> Any:
        self.calls.append((tool, dict(args)))
        key = (tool, canonical_args(args))
        file = self._index.get(key)
        if file is None:
            raise NotRecorded(
                f"no fixture for {tool} {key[1]} in {self.root}; run the same command once with --record {self.root}"
            )
        path = self.root / file
        if not path.is_file():
            raise NotRecorded(f"fixture file missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def close(self) -> None:
        return None

    def __repr__(self) -> str:
        return f"ReplayGateway({self.root!s}, {len(self._index)} fixtures)"
