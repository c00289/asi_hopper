"""EvidenceService: dated, hashed snapshots of what Jira and Confluence said, and diffs between them.

Two bundle kinds share one folder layout and one manifest shape:

- ``jira``: ``issues.json`` (records), ``issues.csv``, ``issues.md``, ``manifest.json``.

Every hashed file is written with LF line endings on every platform, so a bundle hashes the same wherever
it is taken or checked; the CSVs are Excel's (CRLF rows) and are not hashed.
- ``confluence``: ``pages.json`` (records without bodies, with comments and, since 0.1.9, the sections of a
  Markdown body with their hashes), one ``pages/<id>.md`` per page holding the Markdown body byte for byte,
  ``pages.csv``, ``pages.md``, ``manifest.json``.

``manifest.json`` names the kind, the source (JQL, or page ids / a page tree / a CQL), the account, the
time, every file with its SHA-256, and for Confluence every page with its version and body hash. ``verify``
recomputes every hash; ``diff`` compares two bundles of the same kind, or one bundle against live.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import NotFound, ValidationError
from ..model import IssueRecord, PageRecord
from ..version import RECORD_VERSION, __version__
from .issues import IssueService

if TYPE_CHECKING:
    from .confluence import ConfluenceService

ISSUES_FILE = "issues.json"
CSV_FILE = "issues.csv"
MD_FILE = "issues.md"
MANIFEST_FILE = "manifest.json"
PAGES_FILE = "pages.json"
PAGES_CSV = "pages.csv"
PAGES_MD = "pages.md"
PAGES_DIR = "pages"
KINDS = ("jira", "confluence")
LIST_LIMIT = 250  # the server's cap: a tree or a CQL is fetched in pages of 250
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
_PAGE_COMPARE_FIELDS = ("title", "status", "version", "updated", "parent_id", "body_sha256", "comment_count")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _folder(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_dir() else p.parent


def _read_manifest(folder: Path) -> dict[str, Any]:
    manifest_path = folder / MANIFEST_FILE
    if not manifest_path.is_file():
        raise NotFound(f"no {MANIFEST_FILE} in {folder}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def bundle_kind(manifest: dict[str, Any]) -> str:
    """``jira`` or ``confluence``; bundles written before 0.1.8 carry no ``kind`` and are Jira."""
    kind = manifest.get("kind") or "jira"
    if kind not in KINDS:
        raise ValidationError(f"unknown bundle kind {kind!r}")
    return kind


@dataclass(frozen=True)
class PageSource:
    """What a Confluence bundle covers: explicit page ids, a page tree, or a CQL (optionally in one space)."""

    kind: str  # pages | tree | cql
    ids: tuple[str, ...] = ()
    root: str | None = None
    depth: int = 0
    cql: str | None = None
    space: str | None = None

    @classmethod
    def parse(cls, target: str, *, depth: int = 0, space: str | None = None) -> PageSource:
        """Digits (comma-separated) are page ids; one id with ``depth`` > 0 is a tree; anything else is CQL."""
        text = (target or "").strip()
        if not text:
            raise ValidationError("confluence snapshot needs page ids, a page id with --depth, or a CQL")
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if all(p.isdigit() for p in parts):
            if depth and len(parts) == 1:
                return cls("tree", root=parts[0], depth=min(int(depth), 10))
            if depth:
                raise ValidationError("--depth applies to one root page id, not a list")
            return cls("pages", ids=tuple(parts))
        return cls("cql", cql=text, space=space.strip().upper() if space else None)

    def describe(self) -> str:
        if self.kind == "tree":
            return f"page {self.root} and descendants to depth {self.depth}"
        if self.kind == "pages":
            return f"page(s) {', '.join(self.ids)}"
        return f"CQL {self.cql!r}" + (f" in space {self.space}" if self.space else "")

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready: the kind, then only the fields the kind uses (ids as a list, as they read back)."""
        data: dict[str, Any] = {"kind": self.kind}
        if self.ids:
            data["ids"] = list(self.ids)
        if self.root is not None:
            data["root"] = self.root
        if self.depth:
            data["depth"] = self.depth
        if self.cql is not None:
            data["cql"] = self.cql
        if self.space is not None:
            data["space"] = self.space
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageSource:
        return cls(
            kind=str(data.get("kind") or "pages"),
            ids=tuple(str(i) for i in data.get("ids") or ()),
            root=data.get("root"),
            depth=int(data.get("depth") or 0),
            cql=data.get("cql"),
            space=data.get("space"),
        )


class EvidenceService:
    def __init__(
        self,
        issues: IssueService,
        site: str,
        account: dict[str, Any] | None = None,
        confluence: ConfluenceService | None = None,
    ) -> None:
        self.issues = issues
        self.site = site
        self.account = account if account is not None else {}
        self.confluence = confluence

    # -- shared -----------------------------------------------------------------------------
    def _manifest_head(self, kind: str, taken: datetime) -> dict[str, Any]:
        return {
            "kind": kind,
            "tool": f"asi_hopper {__version__}",
            "record_version": RECORD_VERSION,
            "site": self.site,
            "account": {k: self.account.get(k) for k in ("account_id", "name", "email") if self.account.get(k)},
            "taken_at": taken.isoformat(timespec="seconds"),
        }

    @staticmethod
    def _write_manifest(folder: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        (folder / MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        return manifest

    # -- Jira -------------------------------------------------------------------------------
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
            json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
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
        (folder / MD_FILE).write_text("\n".join(md), encoding="utf-8", newline="\n")
        manifest = {
            **self._manifest_head("jira", taken),
            "jql": jql,
            "comments": comments,
            "count": len(records),
            "keys": [r.key for r in records],
            "files": {"issues": ISSUES_FILE, "csv": CSV_FILE, "readable": MD_FILE},
            "sha256": {ISSUES_FILE: _sha256(issues_path)},
            "folder": str(folder),
        }
        return self._write_manifest(folder, manifest)

    # -- Confluence -------------------------------------------------------------------------
    def _resolve_pages(self, source: PageSource) -> list[str]:
        """The page ids a source covers, in a stable order, each once."""
        assert self.confluence is not None
        if source.kind == "pages":
            ids = list(source.ids)
        elif source.kind == "tree":
            assert source.root is not None
            refs = self.confluence.children(source.root, depth=source.depth, limit=LIST_LIMIT, all_pages=True)
            ids = [source.root, *(r.id for r in refs)]
        else:
            refs = self.confluence.search(source.cql, space=source.space, limit=LIST_LIMIT, all_pages=True)
            ids = [r.id for r in refs if r.type == "page"]
        return list(dict.fromkeys(ids))

    def _page_entry(self, record: PageRecord, comments: bool) -> tuple[dict[str, Any], str]:
        """The pages.json entry for one page and its Markdown body (the file content)."""
        assert self.confluence is not None
        body = record.body if isinstance(record.body, str) else json.dumps(record.body, ensure_ascii=False)
        entry = record.to_dict()
        entry.pop("body")
        entry["body_file"] = f"{PAGES_DIR}/{record.id}.md"
        entry["body_sha256"] = _sha256_text(body)
        entry["body_chars"] = len(body)
        entry["sections"] = [
            {"heading": s.heading, "anchor": s.anchor, "sha256": s.sha256, "chars": s.chars} for s in record.sections()
        ]
        entry["comments"] = []
        if comments:
            found = self.confluence.comments(record.id, kind="all", limit=LIST_LIMIT, replies=True)
            entry["comments"] = [asdict(c) for c in found]
        entry["comment_count"] = len(entry["comments"])
        return entry, body

    def snapshot_pages(
        self,
        source: PageSource,
        out_dir: str | Path,
        *,
        name: str | None = None,
        comments: bool = False,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Write pages.json, pages/<id>.md, pages.csv, pages.md and manifest.json under ``out_dir/<name>``."""
        if self.confluence is None:
            raise ValidationError("this Hopper has no Confluence service")
        taken = datetime.now().astimezone()
        ids = self._resolve_pages(source)
        records = [self.confluence.page(page_id) for page_id in ids]
        label = title or (records[0].title if source.kind == "tree" and records else source.describe())
        name = name or f"{_slug(label)}-{taken:%Y-%m-%d}"
        folder = Path(out_dir) / name
        (folder / PAGES_DIR).mkdir(parents=True, exist_ok=True)

        entries: list[dict[str, Any]] = []
        hashes: dict[str, str] = {}
        for record in records:
            entry, body = self._page_entry(record, comments)
            (folder / entry["body_file"]).write_bytes(body.encode("utf-8"))
            hashes[entry["body_file"]] = entry["body_sha256"]
            entries.append(entry)
        pages_path = folder / PAGES_FILE
        pages_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        hashes = {PAGES_FILE: _sha256(pages_path), **hashes}

        with (folder / PAGES_CSV).open("w", newline="", encoding="utf-8") as fh:
            fields = [*PageRecord.ROW_FIELDS, "body_sha256", "body_chars", "comment_count"]
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for e in entries:
                writer.writerow({k: e.get(k) for k in fields})
        md = [
            f"# {label} — {taken:%Y-%m-%d %H:%M}",
            "",
            f"Site {self.site}. Source: {source.describe()}. {len(entries)} page(s)"
            + (", comments included" if comments else "")
            + f". Taken by asi_hopper {__version__}"
            + (f" as {self.account.get('name')}" if self.account.get("name") else "")
            + ".",
            "",
            "| Page | Title | Version | Updated | Comments | Body SHA-256 |",
            "|---|---|---|---|---|---|",
        ]
        for e in entries:
            md.append(
                f"| [{e['id']}]({e['url']}) | {(e['title'] or '').replace('|', '\\|')} | {e['version'] or ''} "
                f"| {(e['updated'] or '')[:16].replace('T', ' ')} | {e['comment_count']} | `{e['body_sha256'][:12]}…` |"
            )
        md += [
            "",
            f"Files: `{PAGES_FILE}` (records and comments), `{PAGES_DIR}/<id>.md` (one Markdown body per page, "
            f"byte for byte), `{PAGES_CSV}` (Excel), `{MANIFEST_FILE}` (source, time, account, SHA-256 of every file).",
            "",
        ]
        (folder / PAGES_MD).write_text("\n".join(md), encoding="utf-8", newline="\n")
        manifest = {
            **self._manifest_head("confluence", taken),
            "source": source.to_dict(),
            "comments": comments,
            "count": len(entries),
            "pages": [
                {
                    "id": e["id"],
                    "title": e["title"],
                    "version": e["version"],
                    "updated": e["updated"],
                    "body_sha256": e["body_sha256"],
                }
                for e in entries
            ],
            "files": {"pages": PAGES_FILE, "bodies": f"{PAGES_DIR}/", "csv": PAGES_CSV, "readable": PAGES_MD},
            "sha256": hashes,
            "folder": str(folder),
        }
        return self._write_manifest(folder, manifest)

    # -- verify and diff --------------------------------------------------------------------
    @staticmethod
    def load(path: str | Path) -> list[dict[str, Any]]:
        """The records of a bundle: issues.json or pages.json, whichever the folder holds."""
        p = Path(path)
        if p.is_dir():
            manifest_path = p / MANIFEST_FILE
            kind = (
                bundle_kind(json.loads(manifest_path.read_text(encoding="utf-8")))
                if manifest_path.is_file()
                else "jira"
            )
            p = p / (PAGES_FILE if kind == "confluence" else ISSUES_FILE)
        if not p.is_file():
            raise NotFound(f"snapshot not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def verify(self, path: str | Path) -> dict[str, Any]:
        """Recompute every SHA-256 the manifest lists. ``intact`` is true only if all of them match."""
        folder = _folder(path)
        manifest = _read_manifest(folder)
        files: list[dict[str, Any]] = []
        for rel, expected in (manifest.get("sha256") or {}).items():
            target = folder / rel
            actual = _sha256(target) if target.is_file() else None
            files.append({"file": rel, "expected": expected, "actual": actual, "intact": actual == expected})
        intact = bool(files) and all(f["intact"] for f in files)
        head = files[0] if files else {"expected": None, "actual": None}
        return {
            "folder": str(folder),
            "kind": bundle_kind(manifest),
            "files": files,
            "expected": head["expected"],
            "actual": head["actual"],
            "intact": intact,
        }

    def diff(self, before: str | Path, after: str | Path | None = None, *, jql: str | None = None) -> dict[str, Any]:
        """Compare two bundles of the same kind, or one bundle against live (``after=None``)."""
        folder = _folder(before)
        manifest = _read_manifest(folder) if (folder / MANIFEST_FILE).is_file() else {}
        kind = bundle_kind(manifest)
        if after is not None:
            other = _folder(after)
            other_kind = bundle_kind(_read_manifest(other)) if (other / MANIFEST_FILE).is_file() else "jira"
            if other_kind != kind:
                raise ValidationError(f"cannot diff a {kind} bundle against a {other_kind} bundle")
        if kind == "confluence":
            return self._diff_pages(before, after, manifest)
        return self._diff_issues(before, after, jql, manifest)

    def _diff_issues(
        self, before: str | Path, after: str | Path | None, jql: str | None, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        a = {r["key"]: r for r in self.load(before)}
        if after is not None:
            b = {r["key"]: r for r in self.load(after)}
            source = str(after)
        else:
            jql = jql or manifest.get("jql")
            if not jql:
                raise NotFound("live diff needs the snapshot's manifest.json (for its JQL) or an explicit jql")
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
            "kind": "jira",
            "before": str(before),
            "after": source,
            "added": sorted(b.keys() - a.keys()),
            "removed": sorted(a.keys() - b.keys()),
            "changed": changed,
            "same": not changed and a.keys() == b.keys(),
        }

    def _diff_pages(self, before: str | Path, after: str | Path | None, manifest: dict[str, Any]) -> dict[str, Any]:
        a = {e["id"]: e for e in self.load(before)}
        if after is not None:
            b = {e["id"]: e for e in self.load(after)}
            source = str(after)
        else:
            if self.confluence is None or not manifest.get("source"):
                raise NotFound("live diff needs the bundle's manifest.json (for its source) and a Confluence service")
            page_source = PageSource.from_dict(manifest["source"])
            comments = bool(manifest.get("comments"))
            b = {}
            for page_id in self._resolve_pages(page_source):
                entry, _ = self._page_entry(self.confluence.page(page_id), comments)
                b[entry["id"]] = entry
            source = f"live: {page_source.describe()}"
        changed: list[dict[str, Any]] = []
        for page_id in sorted(a.keys() & b.keys()):
            for field in _PAGE_COMPARE_FIELDS:
                x, y = a[page_id].get(field), b[page_id].get(field)
                if x != y:
                    changed.append(
                        {"id": page_id, "title": a[page_id].get("title"), "field": field, "before": x, "after": y}
                    )
        return {
            "kind": "confluence",
            "before": str(before),
            "after": source,
            "added": sorted(b.keys() - a.keys()),
            "removed": sorted(a.keys() - b.keys()),
            "changed": changed,
            "same": not changed and a.keys() == b.keys(),
        }


def record_to_dict(record: IssueRecord) -> dict[str, Any]:
    return asdict(record)
