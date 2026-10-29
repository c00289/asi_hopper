"""ConfluenceService: spaces, pages of a space, one page, children, CQL search, comments. Reads only.

The JIRA Live Data conventions apply here too: nothing connects at construction (the gateway connects
on the first call), every list is one page unless ``all_pages`` is asked for, and the default CQL is
scoped to the signed-in user (``DEFAULT_CQL``). Callers in a window run these off the UI thread.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..errors import NotFound, ValidationError
from ..gateway.api import ConfluenceApi
from ..model.confluence import (
    BODY_FORMATS,
    COMMENT_KINDS,
    PageComment,
    PageRecord,
    PageRef,
    Space,
    comments_from_raw,
    cql_from_raw,
    descendants_from_raw,
    page_from_raw,
    pages_from_raw,
    spaces_from_raw,
)

# What `confluence search` runs when no CQL is given: the pages the signed-in user has touched, newest first.
DEFAULT_CQL = "contributor = currentUser() AND type = page ORDER BY lastmodified DESC"
PAGE_SIZE = 25  # the server's own default; 250 is its cap
MAX_PAGES = 40  # a hard stop for --all: 40 x 250 items


class ConfluenceService:
    def __init__(self, api: ConfluenceApi, site: str) -> None:
        self.api = api
        self.site = site

    # -- spaces -----------------------------------------------------------------------------
    def spaces(self, keys: Sequence[str] | None = None, *, limit: int = PAGE_SIZE) -> list[Space]:
        """Spaces visible to the account, or the ones named by ``keys``. One page of at most 250."""
        return spaces_from_raw(self.api.spaces(keys, limit=limit), self.site)

    def space(self, key_or_id: str) -> Space:
        wanted = key_or_id.strip()
        if wanted.isdigit():
            for s in self.spaces(limit=250):
                if s.id == wanted:
                    return s
        else:
            for s in self.spaces([wanted.upper()], limit=1):
                if s.key.upper() == wanted.upper():
                    return s
        raise NotFound(f"space {key_or_id!r} not visible to this account")

    def _space_id(self, key_or_id: str) -> str:
        wanted = key_or_id.strip()
        return wanted if wanted.isdigit() else self.space(wanted).id

    # -- pages ------------------------------------------------------------------------------
    def pages(
        self,
        space: str,
        *,
        limit: int = PAGE_SIZE,
        all_pages: bool = False,
        max_items: int | None = None,
        sort: str = "-modified-date",
        title: str | None = None,
    ) -> list[PageRef]:
        """Pages of a space (key or id), newest change first. ``all_pages`` follows the cursor."""
        space_id = self._space_id(space)
        refs: list[PageRef] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            page, cursor = pages_from_raw(
                self.api.pages(space_id, limit=limit, cursor=cursor, sort=sort, title=title), self.site
            )
            refs.extend(page)
            if max_items is not None and len(refs) >= max_items:
                return refs[:max_items]
            if not all_pages or not cursor or not page:
                break
        return refs

    def page(self, page_id: str, *, content_format: str = "markdown") -> PageRecord:
        if content_format not in BODY_FORMATS:
            raise ValidationError(f"format must be one of {', '.join(BODY_FORMATS)}")
        record = page_from_raw(self.api.page(page_id.strip(), content_format=content_format), self.site, content_format)
        if record is None:
            raise NotFound(f"page {page_id} not found or not visible to this account")
        return record

    def children(
        self, page_id: str, *, depth: int = 1, limit: int = PAGE_SIZE, all_pages: bool = False
    ) -> list[PageRef]:
        """Descendants of a page down to ``depth`` (1 = direct children, at most 10)."""
        refs: list[PageRef] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            page, cursor = descendants_from_raw(
                self.api.descendants(page_id.strip(), limit=limit, depth=depth, cursor=cursor), self.site
            )
            refs.extend(page)
            if not all_pages or not cursor or not page:
                break
        return refs

    # -- search -----------------------------------------------------------------------------
    @staticmethod
    def scoped_cql(cql: str | None, space: str | None = None) -> str:
        """The CQL to run: ``DEFAULT_CQL`` when none is given, restricted to ``space`` when one is."""
        text = (cql or DEFAULT_CQL).strip()
        if not space:
            return text
        where, sep, order = text.partition(" ORDER BY ")
        return f"space = {space.strip().upper()} AND ({where})" + (f"{sep}{order}" if sep else "")

    def search(
        self,
        cql: str | None = None,
        *,
        space: str | None = None,
        limit: int = PAGE_SIZE,
        all_pages: bool = False,
        max_items: int | None = None,
    ) -> list[PageRef]:
        query = self.scoped_cql(cql, space)
        refs: list[PageRef] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            page, cursor = cql_from_raw(self.api.cql(query, limit=limit, cursor=cursor), self.site)
            refs.extend(page)
            if max_items is not None and len(refs) >= max_items:
                return refs[:max_items]
            if not all_pages or not cursor or not page:
                break
        return refs

    # -- comments ---------------------------------------------------------------------------
    def comments(
        self, page_id: str, *, kind: str = "all", limit: int = PAGE_SIZE, replies: bool = False
    ) -> list[PageComment]:
        """Footer and/or inline comments of a page (open inline comments only), one page each."""
        if kind not in (*COMMENT_KINDS, "all"):
            raise ValidationError(f"kind must be one of {', '.join(COMMENT_KINDS)}, all")
        out: list[PageComment] = []
        page_id = page_id.strip()
        if kind in ("footer", "all"):
            out.extend(comments_from_raw(self.api.footer_comments(page_id, limit=limit, replies=replies), "footer")[0])
        if kind in ("inline", "all"):
            out.extend(comments_from_raw(self.api.inline_comments(page_id, limit=limit, replies=replies), "inline")[0])
        return out

    def replies(self, comment_id: str, kind: str, *, limit: int = PAGE_SIZE) -> list[PageComment]:
        if kind not in COMMENT_KINDS:
            raise ValidationError(f"kind must be one of {', '.join(COMMENT_KINDS)}")
        return comments_from_raw(self.api.comment_children(comment_id.strip(), kind, limit=limit), kind)[0]
