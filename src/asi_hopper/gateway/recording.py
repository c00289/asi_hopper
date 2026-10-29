"""RecordingGateway: wraps any gateway and writes every payload into a replay fixtures directory."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import JiraGateway, canonical_args
from .replay import INDEX_NAME

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class RecordingGateway:
    def __init__(self, inner: JiraGateway, fixtures: str | Path) -> None:
        self.inner = inner
        self.name = f"recording({inner.name})"
        self.root = Path(fixtures)
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / INDEX_NAME
        self._entries: list[dict[str, Any]] = []
        if self._index_path.is_file():
            self._entries = json.loads(self._index_path.read_text(encoding="utf-8"))

    @staticmethod
    def _filename(tool: str, args: dict[str, Any]) -> str:
        hint = (
            args.get("issueIdOrKey")
            or args.get("projectIdOrKey")
            or args.get("pageId")
            or args.get("spaceId")
            or args.get("commentId")
            or args.get("toolName")
            or ""
        )
        if args.get("issueTypeId"):
            hint = f"{hint}_{args['issueTypeId']}"
        for text_key in ("jql", "cql", "query"):
            if args.get(text_key):
                hint = _SAFE.sub("_", str(args[text_key]))[:60].strip("_")
        if args.get("searchString"):
            hint = f"search_{_SAFE.sub('_', str(args['searchString']))[:40]}"
        base = _SAFE.sub("_", f"{tool}_{hint}" if hint else tool).strip("_")
        return f"{base}.json"

    def call(self, tool: str, args: dict[str, Any]) -> Any:
        payload = self.inner.call(tool, args)
        key = canonical_args(args)
        file = self._filename(tool, args)
        # same tool + args: overwrite the previous recording; different args, same hint: suffix
        existing = next((e for e in self._entries if e["tool"] == tool and canonical_args(e["args"]) == key), None)
        if existing:
            file = existing["file"]
        else:
            taken = {e["file"] for e in self._entries}
            stem, n = file[:-5], 2
            while file in taken:
                file = f"{stem}_{n}.json"
                n += 1
            self._entries.append({"tool": tool, "args": {}, "file": file})
            existing = self._entries[-1]
        existing["args"] = {k: v for k, v in args.items() if k != "cloudId"}
        existing["recorded_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        (self.root / file).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self._index_path.write_text(json.dumps(self._entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload

    def close(self) -> None:
        self.inner.close()
