"""EvidenceService: dated, hashed snapshots of what Jira said, and diffs between them."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..errors import NotFound
from ..model import IssueRecord
from ..version import RECORD_VERSION, __version__
from .issues import IssueService

ISSUES_FILE = "issues.json"
CSV_FILE = "issues.csv"
MD_FILE = "issues.md"
MANIFEST_FILE = "manifest.json"
_COMPARE_FIELDS = (
    "summary",
    "status",
    "status_category",
    "resolution",
    "priority",
    "assignee",
    "reporter",
    "labels",
    "components",
    "parent",
    "due",
    "issue_type",
    "description",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:48] or "snapshot"


def _md_table(records: list[IssueRecord]) -> list[str]:
    head = "| Key | Type | Summary | Status | Priority | Assignee | Updated |"
    rows = [head, "|---|---|---|---|---|---|---|"]
    for r in records:
        summary = (r.summary or "").replace("|", "\\|")
        rows.append(
            f"| [{r.key}]({r.url}) | {r.issue_type or ''} | {summary} | {r.status or ''} | {r.priority or ''} "
            f"| {r.assignee or ''} | {(r.updated or '')[:16].replace('T', ' ')} |"
        )
    return rows


class EvidenceService:
    def __init__(self, issues: IssueService, site: str, account: dict[str, Any] | None = None) -> None:
        self.issues = issues
        self.site = site
        self.account = account if account is not None else {}

    def snapshot(
        self,
        jql: str,
        out_dir: str | Path,
        *,
        name: str | None = None,
        comments: bool = False,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Write issues.json, issues.csv, issues.md and manifest.json under ``out_dir/<name>``."""
        taken = datetime.now().astimezone()
        name = name or f"{_slug(title or jql)}-{taken:%Y-%m-%d}"
        folder = Path(out_dir) / name
        folder.mkdir(parents=True, exist_ok=True)
        records = self.issues.search(jql, all_pages=True, max_results=100)
        if comments:
            records = [self.issues.get(r.key, comments=True) for r in records]

        issues_path = folder / ISSUES_FILE
        issues_path.write_text(
            json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        with (folder / CSV_FILE).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(IssueRecord.ROW_FIELDS))
            writer.writeheader()
            for r in records:
                writer.writerow(r.to_row())
        md = [
            f"# {title or 'Jira snapshot'} — {taken:%Y-%m-%d %H:%M}",
            "",
            f"Site {self.site}. JQL: `{jql}`. {len(records)} issue(s). Taken by asi_hopper {__version__}"
            + (f" as {self.account.get('name')}" if self.account.get("name") else "")
            + ".",
            "",
            *_md_table(records),
            "",
            f"Files: `{ISSUES_FILE}` (records), `{CSV_FILE}` (Excel), `{MANIFEST_FILE}` (JQL, time, account, SHA-256).",
            "",
        ]
        (folder / MD_FILE).write_text("\n".join(md), encoding="utf-8")
        manifest = {
            "tool": f"asi_hopper {__version__}",
            "record_version": RECORD_VERSION,
            "site": self.site,
            "account": {k: self.account.get(k) for k in ("account_id", "name", "email") if self.account.get(k)},
            "taken_at": taken.isoformat(timespec="seconds"),
            "jql": jql,
            "comments": comments,
            "count": len(records),
            "keys": [r.key for r in records],
            "files": {"issues": ISSUES_FILE, "csv": CSV_FILE, "readable": MD_FILE},
            "sha256": {ISSUES_FILE: _sha256(issues_path)},
            "folder": str(folder),
        }
        (folder / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest

    # -- diff -------------------------------------------------------------------------------
    @staticmethod
    def load(path: str | Path) -> list[dict[str, Any]]:
        p = Path(path)
        if p.is_dir():
            p = p / ISSUES_FILE
        if not p.is_file():
            raise NotFound(f"snapshot not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def verify(self, path: str | Path) -> dict[str, Any]:
        folder = Path(path)
        folder = folder if folder.is_dir() else folder.parent
        manifest_path = folder / MANIFEST_FILE
        if not manifest_path.is_file():
            raise NotFound(f"no {MANIFEST_FILE} in {folder}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = (manifest.get("sha256") or {}).get(ISSUES_FILE)
        actual = _sha256(folder / ISSUES_FILE)
        return {"folder": str(folder), "expected": expected, "actual": actual, "intact": expected == actual}

    def diff(self, before: str | Path, after: str | Path | None = None, *, jql: str | None = None) -> dict[str, Any]:
        """Compare two snapshots, or a snapshot against live Jira (``after=None`` + the manifest's JQL)."""
        a = {r["key"]: r for r in self.load(before)}
        if after is not None:
            b = {r["key"]: r for r in self.load(after)}
            source = str(after)
        else:
            folder = Path(before)
            folder = folder if folder.is_dir() else folder.parent
            if jql is None:
                manifest_path = folder / MANIFEST_FILE
                if not manifest_path.is_file():
                    raise NotFound("live diff needs the snapshot's manifest.json (for its JQL) or an explicit jql")
                jql = json.loads(manifest_path.read_text(encoding="utf-8"))["jql"]
            b = {r.key: r.to_dict() for r in self.issues.search(jql, all_pages=True, max_results=100)}
            source = f"live: {jql}"
        changed: list[dict[str, Any]] = []
        for key in sorted(a.keys() & b.keys()):
            for field in _COMPARE_FIELDS:
                x, y = a[key].get(field), b[key].get(field)
                if isinstance(x, dict) or isinstance(y, dict):
                    x, y = (x or {}).get("key"), (y or {}).get("key")
                if x != y:
                    changed.append({"key": key, "field": field, "before": x, "after": y})
        return {
            "before": str(before),
            "after": source,
            "added": sorted(b.keys() - a.keys()),
            "removed": sorted(a.keys() - b.keys()),
            "changed": changed,
            "same": not changed and a.keys() == b.keys(),
        }


def record_to_dict(record: IssueRecord) -> dict[str, Any]:
    return asdict(record)
