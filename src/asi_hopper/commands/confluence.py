"""The Confluence verb (reads only) and the tool inventory verb.

``confluence`` follows the ``auth`` precedent: one verb, an ``action`` positional, so the CLI reads
``asi-hopper confluence spaces``, ``confluence pages STPA``, ``confluence page 399343803``,
``confluence search "<cql>"``, ``confluence comments 399343803``, ``confluence snapshot 399343803 --depth 2``.
No action writes to Confluence; ``snapshot`` writes an evidence bundle to the local evidence folder.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..errors import ValidationError
from ..gateway.base import (
    CONFLUENCE_READ_TOOLS,
    CONFLUENCE_WRITE_TOOLS,
    LIST_TOOLS,
    READ_TOOLS,
    TOOL_CONTENT_FORMAT_GUIDE,
    TOOL_FETCH,
    TOOL_ROVO_SEARCH,
)
from ..model.confluence import BODY_FORMATS, COMMENT_KINDS, PageRecord
from ..model.pagetext import Section, find_section
from ..services.confluence import DEFAULT_CQL, PAGE_SIZE
from ..services.evidence import PageSource
from .base import Argument, Command, Context, Result
from .factory import register_command

ACTIONS = ("spaces", "pages", "page", "children", "search", "comments", "replies", "snapshot")

_TARGET_HELP = {
    "spaces": "space keys to look up (comma-separated); all visible spaces when omitted",
    "pages": "space key or id",
    "page": "page id (or the tiny-link id from a /wiki/x/ URL)",
    "children": "page id",
    "search": f'CQL; default "{DEFAULT_CQL}"',
    "comments": "page id",
    "replies": "comment id (needs --kind footer or inline)",
    "snapshot": "page ids (comma-separated), one page id with --depth N (the tree below it), or a CQL (--space)",
}


@register_command
class Confluence(Command):
    verb = "confluence"
    help = (
        "Read Confluence: spaces | pages <space> | page <id> | children <id> | search [cql] | comments <id> | replies"
        " | snapshot <ids | id --depth N | cql> (an evidence bundle with hashed Markdown bodies)"
    )
    arguments = (
        Argument("action", " | ".join(ACTIONS), required=True, choices=ACTIONS),
        Argument("target", "; ".join(f"{k}: {v}" for k, v in _TARGET_HELP.items())),
        Argument("limit", f"page size, 1-250 (default {PAGE_SIZE})", flag=True, type="int", default=PAGE_SIZE),
        Argument("all", "pages, children, search: follow every page", flag=True, type="bool", default=False),
        Argument("max", "pages, search: stop after this many items", flag=True, type="int"),
        Argument("space", "search: restrict the CQL to one space key", flag=True),
        Argument("format", "page: body format", flag=True, choices=BODY_FORMATS, default="markdown"),
        Argument("kind", "comments, replies: footer | inline (comments also: all)", flag=True, default=None),
        Argument(
            "depth",
            "children: levels below the page, 1-10 (default 1); snapshot: the tree below one page id",
            flag=True,
            type="int",
        ),
        Argument("replies", "comments: include each comment's replies", flag=True, type="bool", default=False),
        Argument("raw", "page: include the raw payload", flag=True, type="bool", default=False),
        Argument(
            "section",
            "page: one section by heading (equal, case-insensitive; else the first heading containing the text)",
            flag=True,
        ),
        Argument(
            "sections",
            "page: list the sections (heading, anchor, level, chars, sha256) without their text",
            flag=True,
            type="bool",
            default=False,
        ),
        Argument(
            "out", "snapshot: directory to write under (default: evidence_dir from config)", flag=True, type="path"
        ),
        Argument("name", "snapshot: folder name (default: <slug>-<date>)", flag=True),
        Argument("title", "snapshot: title for the readable view", flag=True),
        Argument(
            "comments",
            "snapshot: include each page's footer and open inline comments",
            flag=True,
            type="bool",
            default=False,
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        action = args["action"]
        target = (args.get("target") or "").strip()
        if action != "spaces" and action != "search" and not target:
            raise ValidationError(f"confluence {action}: a target is required ({_TARGET_HELP[action]})")
        svc = ctx.hopper.confluence
        limit = int(args.get("limit") or PAGE_SIZE)
        if action == "snapshot":
            source = PageSource.parse(target, depth=int(args.get("depth") or 0), space=args.get("space"))
            out = ctx.hopper.config.resolve(args.get("out") or ctx.hopper.config.evidence_dir)
            manifest = ctx.hopper.evidence.snapshot_pages(
                source, out, name=args.get("name"), comments=bool(args.get("comments")), title=args.get("title")
            )
            return Result.success(manifest)
        if action == "spaces":
            keys = [k.strip() for k in target.split(",") if k.strip()] or None
            return Result.success([asdict(s) for s in svc.spaces(keys, limit=limit)])
        if action == "pages":
            refs = svc.pages(target, limit=limit, all_pages=bool(args.get("all")), max_items=args.get("max"))
            return Result.success([asdict(r) for r in refs])
        if action == "page":
            record = svc.page(target, content_format=args.get("format") or "markdown")
            if args.get("section") or args.get("sections"):
                return _page_sections(record, args.get("section"))
            return Result.success(record.to_dict(include_raw=bool(args.get("raw"))))
        if action == "children":
            refs = svc.children(target, depth=int(args.get("depth") or 1), limit=limit, all_pages=bool(args.get("all")))
            return Result.success([asdict(r) for r in refs])
        if action == "search":
            cql = svc.scoped_cql(target or None, args.get("space"))
            refs = svc.search(cql, limit=limit, all_pages=bool(args.get("all")), max_items=args.get("max"))
            warnings = [] if target else [f"no CQL given; ran the user-scoped default: {cql}"]
            return Result.success([asdict(r) for r in refs], warnings)
        if action == "comments":
            kind = args.get("kind") or "all"
            comments = svc.comments(target, kind=kind, limit=limit, replies=bool(args.get("replies")))
            return Result.success([asdict(c) for c in comments])
        kind = args.get("kind")
        if kind not in COMMENT_KINDS:
            raise ValidationError(f"confluence replies: --kind must be one of {', '.join(COMMENT_KINDS)}")
        return Result.success([asdict(c) for c in svc.replies(target, kind, limit=limit)])


def _section_entry(record: PageRecord, section: Section, *, text: bool) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "heading": section.heading,
        "anchor": section.anchor,
        "anchor_url": record.anchor_url(section.heading),
        "level": section.level,
        "chars": section.chars,
        "sha256": section.sha256,
    }
    if text:
        entry["text"] = section.text
    return entry


def _page_sections(record: PageRecord, heading: str | None) -> Result:
    """``--sections``: every section without its text; ``--section H``: the one section, text included."""
    found = record.sections()
    if record.body_format != "markdown":
        return Result.failure(
            f"confluence page {record.id}: sections are read from the markdown body, not {record.body_format}"
        )
    if not heading:
        return Result.success([_section_entry(record, s, text=False) for s in found])
    section = find_section(found, heading)
    if section is None:
        present = ", ".join(repr(s.heading) for s in found if s.heading) or "none"
        return Result.failure(f"confluence page {record.id}: no section {heading!r}; headings present: {present}")
    return Result.success(_section_entry(record, section, text=True))


# Jira tools that write; the server does not flag them, so the inventory does (Hopper calls none).
_JIRA_WRITE_TOOLS = frozenset(
    {
        "createJiraIssue",
        "editJiraIssue",
        "transitionJiraIssue",
        "addCommentToJiraIssue",
        "addWorklogToJiraIssue",
        "createIssueLink",
    }
)


def classify_tool(name: str) -> dict[str, Any]:
    """Product, whether the tool writes, and whether Hopper uses it: the inventory's verdict on one tool."""
    lowered = name.lower()
    if name in (TOOL_FETCH, TOOL_ROVO_SEARCH):
        product = "atlassian"  # cross-product; not used by Hopper
    elif "confluence" in lowered or name == TOOL_CONTENT_FORMAT_GUIDE:
        product = "confluence"
    elif "jira" in lowered or "issue" in lowered:
        product = "jira"
    else:
        product = "atlassian"
    writes = name in CONFLUENCE_WRITE_TOOLS or name in _JIRA_WRITE_TOOLS
    return {"product": product, "writes": writes, "used_by_hopper": name in READ_TOOLS or name in CONFLUENCE_READ_TOOLS}


@register_command
class Tools(Command):
    verb = "tools"
    help = "The tools the Atlassian MCP server exposes, classified: product, writes, used by Hopper"
    arguments = (
        Argument("product", "only this product", flag=True, choices=("jira", "confluence", "atlassian")),
        Argument("schema", "include each tool's input schema", flag=True, type="bool", default=False),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        inventory = ctx.hopper.gateway.call(LIST_TOOLS, {})
        out: list[dict[str, Any]] = []
        for tool in inventory if isinstance(inventory, list) else []:
            name = str(tool.get("name") or "")
            entry = {"name": name, **classify_tool(name), "description": tool.get("description") or ""}
            schema = tool.get("input_schema") or {}
            entry["required"] = list(schema.get("required") or [])
            entry["optional"] = [k for k in (schema.get("properties") or {}) if k not in entry["required"]]
            if args.get("schema"):
                entry["input_schema"] = schema
            if not args.get("product") or entry["product"] == args["product"]:
                out.append(entry)
        return Result.success(out)
