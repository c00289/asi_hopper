"""Confluence records and normalisers: raw Remote MCP Server payloads -> frozen dataclasses.

Shapes as recorded on 2026-10-29 (see docs/confluence-sandbox-2026-10-29.md): v2-style lists carry
``results`` and ``_links.next`` (a relative URL whose ``cursor`` query parameter is the next page);
CQL carries ``results`` with a ``content`` object plus ``start``/``limit``/``size``/``totalSize``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

from .pagetext import Section, heading_anchor, sections

BODY_FORMATS = ("markdown", "adf", "html")
COMMENT_KINDS = ("footer", "inline")


@dataclass(frozen=True)
class Space:
    id: str
    key: str
    name: str
    type: str | None = None  # global | personal
    status: str | None = None  # current | archived
    homepage_id: str | None = None
    url: str = ""


@dataclass(frozen=True)
class PageRef:
    """A page as a list names it: space pages, descendants, and CQL hits (which may be other content types)."""

    id: str
    title: str
    status: str | None = None
    type: str = "page"  # page | blogpost | comment | attachment (CQL can return any)
    space_id: str | None = None
    space_key: str | None = None
    parent_id: str | None = None
    depth: int | None = None  # descendants only
    last_modified: str | None = None
    excerpt: str | None = None  # CQL only
    url: str = ""


@dataclass(frozen=True)
class PageComment:
    id: str
    kind: str  # footer | inline
    body: str
    author_id: str | None = None
    created: str | None = None
    status: str | None = None
    title: str | None = None
    resolution: str | None = None  # inline: open | resolved | dangling | reopened
    selection: str | None = None  # inline: the page text the comment is anchored on
    replies: tuple[PageComment, ...] = ()


@dataclass(frozen=True)
class PageRecord:
    """One page with its body. ``to_dict()`` is the sibling-facing shape; ``to_row()`` the flat one."""

    id: str
    title: str
    status: str | None
    type: str
    space_id: str | None
    parent_id: str | None
    parent_type: str | None
    author_id: str | None
    owner_id: str | None
    created: str | None
    updated: str | None  # the current version's createdAt
    version: int | None
    version_message: str | None
    version_author_id: str | None
    body_format: str
    body: Any  # str for markdown and html, the ADF document (dict) for adf
    url: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    ROW_FIELDS: ClassVar[tuple[str, ...]] = (
        "id",
        "title",
        "status",
        "space_id",
        "parent_id",
        "version",
        "created",
        "updated",
        "url",
    )

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data.pop("raw", None)
        return data

    def to_row(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.ROW_FIELDS}

    def sections(self) -> list[Section]:
        """The page's sections (``model.pagetext.sections``) for a Markdown body; empty for any other body."""
        if self.body_format != "markdown" or not isinstance(self.body, str):
            return []
        return sections(self.body)

    def anchor_url(self, heading: str) -> str:
        """The page URL with the heading's anchor, the link a citation uses to point at one section.

        The text before the first heading has no anchor: its URL is the page's.
        """
        anchor = heading_anchor(heading)
        return f"{self.url}#{anchor}" if anchor else self.url


# ----------------------------------------------------------------------------- normalisers


def _wiki(site: str) -> str:
    return f"{site.rstrip('/')}/wiki"


def page_url(site: str, page_id: str) -> str:
    """A stable page URL that needs no space key (Confluence redirects to the pretty one)."""
    return f"{_wiki(site)}/pages/viewpage.action?pageId={page_id}"


def next_cursor(payload: Any) -> str | None:
    """The ``cursor`` of ``_links.next`` (v2 lists and CQL alike), or None on the last page."""
    if not isinstance(payload, dict):
        return None
    links = payload.get("_links") or {}
    nxt = links.get("next") if isinstance(links, dict) else None
    if not nxt:
        return None
    cursor = parse_qs(urlparse(str(nxt)).query).get("cursor")
    return cursor[0] if cursor else None


def _results(payload: Any) -> list[dict[str, Any]]:
    items = payload.get("results") if isinstance(payload, dict) else payload
    return [r for r in items or [] if isinstance(r, dict)]


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def spaces_from_raw(payload: Any, site: str) -> list[Space]:
    out: list[Space] = []
    for s in _results(payload):
        if not s.get("key"):
            continue
        links = s.get("_links") or {}
        webui = links.get("webui") if isinstance(links, dict) else None
        out.append(
            Space(
                id=str(s.get("id") or ""),
                key=str(s["key"]),
                name=(s.get("name") or "").strip(),
                type=s.get("type"),
                status=s.get("status"),
                homepage_id=_str(s.get("homepageId")),
                url=f"{_wiki(site)}{webui}" if webui else f"{_wiki(site)}/spaces/{s['key']}",
            )
        )
    return out


def page_from_raw(payload: Any, site: str, body_format: str = "markdown") -> PageRecord | None:
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    version = payload.get("version") if isinstance(payload.get("version"), dict) else {}
    body = payload.get("body")
    if isinstance(body, dict) and body_format != "adf" and isinstance(body.get("value"), str):
        body = body["value"]  # a REST-shaped body: {"representation", "value"}
    page_id = str(payload["id"])
    return PageRecord(
        id=page_id,
        title=payload.get("title") or "",
        status=payload.get("status"),
        type=payload.get("type") or "page",
        space_id=_str(payload.get("spaceId")),
        parent_id=_str(payload.get("parentId")),
        parent_type=payload.get("parentType"),
        author_id=payload.get("authorId"),
        owner_id=payload.get("ownerId"),
        created=payload.get("createdAt"),
        updated=version.get("createdAt"),
        version=version.get("number"),
        version_message=version.get("message") or None,
        version_author_id=version.get("authorId"),
        body_format=body_format,
        body=body,
        url=page_url(site, page_id),
        raw=payload,
    )


def pages_from_raw(payload: Any, site: str) -> tuple[list[PageRef], str | None]:
    """``getPagesInConfluenceSpace`` -> refs (bodies dropped) plus the next cursor."""
    refs: list[PageRef] = []
    for p in _results(payload):
        if not p.get("id"):
            continue
        version = p.get("version") if isinstance(p.get("version"), dict) else {}
        refs.append(
            PageRef(
                id=str(p["id"]),
                title=p.get("title") or "",
                status=p.get("status"),
                type=p.get("type") or "page",
                space_id=_str(p.get("spaceId")),
                parent_id=_str(p.get("parentId")),
                last_modified=version.get("createdAt"),
                url=page_url(site, str(p["id"])),
            )
        )
    return refs, next_cursor(payload)


def descendants_from_raw(payload: Any, site: str) -> tuple[list[PageRef], str | None]:
    refs: list[PageRef] = []
    for p in _results(payload):
        if not p.get("id"):
            continue
        refs.append(
            PageRef(
                id=str(p["id"]),
                title=p.get("title") or "",
                status=p.get("status"),
                type=p.get("type") or "page",
                parent_id=_str(p.get("parentId")),
                depth=p.get("depth"),
                last_modified=p.get("lastModified"),
                url=page_url(site, str(p["id"])),
            )
        )
    return refs, next_cursor(payload)


def _space_key_from_container(container: Any) -> str | None:
    if not isinstance(container, dict):
        return None
    url = str(container.get("displayUrl") or "")
    parts = url.strip("/").split("/")
    return parts[1] if len(parts) >= 2 and parts[0] == "spaces" else None


def cql_from_raw(payload: Any, site: str) -> tuple[list[PageRef], str | None]:
    """``searchConfluenceUsingCql`` -> refs (any content type) plus the next cursor."""
    refs: list[PageRef] = []
    base = _wiki(site)
    if isinstance(payload, dict) and isinstance(payload.get("_links"), dict) and payload["_links"].get("base"):
        base = str(payload["_links"]["base"]).rstrip("/")
    for r in _results(payload):
        content = r.get("content") if isinstance(r.get("content"), dict) else {}
        page_id = content.get("id")
        if not page_id:
            continue
        rel = r.get("url")
        refs.append(
            PageRef(
                id=str(page_id),
                title=content.get("title") or r.get("title") or "",
                status=content.get("status"),
                type=content.get("type") or "page",
                space_key=_space_key_from_container(r.get("resultGlobalContainer")),
                last_modified=r.get("lastModified"),
                excerpt=r.get("excerpt") or None,
                url=f"{base}{rel}" if isinstance(rel, str) and rel.startswith("/") else page_url(site, str(page_id)),
            )
        )
    return refs, next_cursor(payload)


def cql_total(payload: Any) -> int | None:
    return payload.get("totalSize") if isinstance(payload, dict) else None


def _comment(c: dict[str, Any], kind: str) -> PageComment:
    body = c.get("body")
    if isinstance(body, dict):
        from ..adf import adf_to_markdown  # an ADF body when contentFormat was adf

        body = adf_to_markdown(body) if body.get("type") == "doc" else str(body.get("value") or body)
    props = c.get("properties") if isinstance(c.get("properties"), dict) else {}
    replies = tuple(_comment(r, kind) for r in c.get("replies") or [] if isinstance(r, dict))
    return PageComment(
        id=str(c.get("id") or ""),
        kind=kind,
        body=body or "",
        author_id=c.get("authorId"),
        created=c.get("createdAt"),
        status=c.get("status"),
        title=c.get("title"),
        resolution=c.get("resolutionStatus"),
        selection=props.get("inlineOriginalSelection") or props.get("inline-original-selection"),
        replies=replies,
    )


def comments_from_raw(payload: Any, kind: str) -> tuple[list[PageComment], str | None]:
    """Footer or inline comments (or a comment's children) plus the next cursor."""
    return [_comment(c, kind) for c in _results(payload)], next_cursor(payload)
