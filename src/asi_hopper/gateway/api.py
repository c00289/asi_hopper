"""JiraApi and ConfluenceApi: every tool call built in one place so gateways, fixtures and services agree."""

from __future__ import annotations

import abc
from collections.abc import Sequence
from typing import Any

from ..errors import WriteSideClosed
from ..model.normalise import DEFAULT_FIELDS
from .base import (
    TOOL_CONFLUENCE_COMMENT_CHILDREN,
    TOOL_CONFLUENCE_CQL,
    TOOL_CONFLUENCE_CREATE_FOOTER_COMMENT,
    TOOL_CONFLUENCE_CREATE_INLINE_COMMENT,
    TOOL_CONFLUENCE_CREATE_PAGE,
    TOOL_CONFLUENCE_DESCENDANTS,
    TOOL_CONFLUENCE_FOOTER_COMMENTS,
    TOOL_CONFLUENCE_INLINE_COMMENTS,
    TOOL_CONFLUENCE_PAGE,
    TOOL_CONFLUENCE_PAGES,
    TOOL_CONFLUENCE_SPACES,
    TOOL_CONFLUENCE_UPDATE_PAGE,
    TOOL_FIELDS,
    TOOL_GET_ISSUE,
    TOOL_ISSUE_TYPES,
    TOOL_LINK_TYPES,
    TOOL_PROJECTS,
    TOOL_REMOTE_LINKS,
    TOOL_RESOURCES,
    TOOL_SEARCH,
    TOOL_TRANSITIONS,
    TOOL_USER_INFO,
    JiraGateway,
)


class JiraApi:
    def __init__(self, gateway: JiraGateway, cloud_id: str) -> None:
        self.gateway = gateway
        self.cloud_id = cloud_id

    # -- identity ---------------------------------------------------------------------------
    def myself(self) -> Any:
        return self.gateway.call(TOOL_USER_INFO, {})

    def resources(self) -> Any:
        return self.gateway.call(TOOL_RESOURCES, {})

    # -- metadata ---------------------------------------------------------------------------
    def projects(self, search: str | None = None, *, start_at: int = 0, max_results: int = 50) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "action": "browse",
            "expandIssueTypes": True,
            "maxResults": max_results,
            "startAt": start_at,
        }
        if search:
            args["searchString"] = search
        return self.gateway.call(TOOL_PROJECTS, args)

    def issue_types(self, project: str) -> Any:
        return self.gateway.call(TOOL_ISSUE_TYPES, {"cloudId": self.cloud_id, "projectIdOrKey": project})

    def fields_for(self, project: str, issue_type_id: str, *, required_only: bool = True) -> Any:
        return self.gateway.call(
            TOOL_FIELDS,
            {
                "cloudId": self.cloud_id,
                "projectIdOrKey": project,
                "issueTypeId": str(issue_type_id),
                "requiredFieldsOnly": required_only,
            },
        )

    def link_types(self) -> Any:
        return self.gateway.call(TOOL_LINK_TYPES, {"cloudId": self.cloud_id})

    # -- issues -----------------------------------------------------------------------------
    def get_issue(self, key: str, fields: Sequence[str] | None = None, *, comments: bool = False) -> Any:
        wanted = list(fields or DEFAULT_FIELDS)
        if comments and "comment" not in wanted:
            wanted.append("comment")
        return self.gateway.call(
            TOOL_GET_ISSUE,
            {"cloudId": self.cloud_id, "issueIdOrKey": key, "fields": wanted, "responseContentFormat": "markdown"},
        )

    def search(
        self,
        jql: str,
        fields: Sequence[str] | None = None,
        *,
        max_results: int = 50,
        next_page_token: str | None = None,
    ) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "jql": jql,
            "fields": list(fields or DEFAULT_FIELDS),
            "maxResults": max(1, min(int(max_results), 100)),
            "responseContentFormat": "markdown",
        }
        if next_page_token:
            args["nextPageToken"] = next_page_token
        return self.gateway.call(TOOL_SEARCH, args)

    def transitions(self, key: str) -> Any:
        return self.gateway.call(TOOL_TRANSITIONS, {"cloudId": self.cloud_id, "issueIdOrKey": key})

    def remote_links(self, key: str) -> Any:
        return self.gateway.call(TOOL_REMOTE_LINKS, {"cloudId": self.cloud_id, "issueIdOrKey": key})


# ----------------------------------------------------------------------------- Confluence


class ConfluenceWriteSide(abc.ABC):
    """The Confluence write contract: signatures and docstrings only.

    The write side is closed by owner decision (Jira 2026-10-27, Confluence 2026-10-29). This class
    records what a write adapter would have to offer so that a sibling can code against it and a
    reviewer can see the whole surface; the only implementation, ``ClosedConfluenceWriteSide``, refuses
    every call with ``WriteSideClosed`` before anything is built or sent. Nothing in Hopper calls the
    four write tools (``CONFLUENCE_WRITE_TOOLS``).
    """

    @abc.abstractmethod
    def create_page(
        self,
        space_id: str,
        title: str,
        body: str,
        *,
        parent_id: str | None = None,
        content_format: str = "markdown",
    ) -> Any:
        """Would call ``createConfluencePage`` (space, title, body in markdown or HTML, optional parent)."""

    @abc.abstractmethod
    def update_page(
        self,
        page_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        content_format: str = "markdown",
        version_message: str | None = None,
    ) -> Any:
        """Would call ``updateConfluencePage`` (a new version of the page; title and/or body)."""

    @abc.abstractmethod
    def create_footer_comment(self, page_id: str, body: str, *, parent_comment_id: str | None = None) -> Any:
        """Would call ``createConfluenceFooterComment`` (a page comment, or a reply when a parent is given)."""

    @abc.abstractmethod
    def create_inline_comment(
        self,
        page_id: str,
        body: str,
        *,
        selection: str,
        match_index: int = 0,
        match_count: int = 1,
    ) -> Any:
        """Would call ``createConfluenceInlineComment`` anchored on ``selection`` (the exact page text, which
        occurrence of it, and how many occurrences the page holds; the server rejects a wrong count)."""


class ClosedConfluenceWriteSide(ConfluenceWriteSide):
    """Every write method raises ``WriteSideClosed``. No argument is inspected, no gateway is held."""

    TOOLS = {
        "create_page": TOOL_CONFLUENCE_CREATE_PAGE,
        "update_page": TOOL_CONFLUENCE_UPDATE_PAGE,
        "create_footer_comment": TOOL_CONFLUENCE_CREATE_FOOTER_COMMENT,
        "create_inline_comment": TOOL_CONFLUENCE_CREATE_INLINE_COMMENT,
    }

    @classmethod
    def _refuse(cls, method: str) -> Any:
        raise WriteSideClosed(
            f"{method} would call {cls.TOOLS[method]}; the Confluence write side is closed by owner decision "
            "(2026-10-29): Hopper reads Confluence and never writes it"
        )

    def create_page(self, space_id: str, title: str, body: str, *, parent_id=None, content_format="markdown") -> Any:
        return self._refuse("create_page")

    def update_page(
        self, page_id: str, *, title=None, body=None, content_format="markdown", version_message=None
    ) -> Any:
        return self._refuse("update_page")

    def create_footer_comment(self, page_id: str, body: str, *, parent_comment_id=None) -> Any:
        return self._refuse("create_footer_comment")

    def create_inline_comment(self, page_id: str, body: str, *, selection: str, match_index=0, match_count=1) -> Any:
        return self._refuse("create_inline_comment")


def _limit(value: int, cap: int = 250) -> int:
    return max(1, min(int(value), cap))


class ConfluenceApi:
    """Every Confluence read call in one place; ``writes`` is the closed contract above.

    Arguments mirror the Remote MCP Server's tool schemas (recorded 2026-10-29): page lists and comment
    lists page with an opaque ``cursor`` taken from ``_links.next``; CQL pages the same way; spaces take a
    ``start`` offset; ``limit`` caps at 250 everywhere. Bodies come back in the ``contentFormat`` asked for:
    ``markdown`` (default here), ``adf`` (a JSON document) or, for one page, ``html``.
    """

    def __init__(self, gateway: JiraGateway, cloud_id: str) -> None:
        self.gateway = gateway
        self.cloud_id = cloud_id
        self.writes: ConfluenceWriteSide = ClosedConfluenceWriteSide()

    def spaces(self, keys: Sequence[str] | None = None, *, limit: int = 25, start: int = 0) -> Any:
        args: dict[str, Any] = {"cloudId": self.cloud_id, "limit": _limit(limit)}
        if keys:
            args["keys"] = [str(k) for k in keys]
        if start:
            args["start"] = int(start)
        return self.gateway.call(TOOL_CONFLUENCE_SPACES, args)

    def pages(
        self,
        space_id: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
        sort: str = "-modified-date",
        title: str | None = None,
        content_format: str = "markdown",
    ) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "spaceId": str(space_id),
            "limit": _limit(limit),
            "sort": sort,
            "contentFormat": content_format,
        }
        if title:
            args["title"] = title
        if cursor:
            args["cursor"] = cursor
        return self.gateway.call(TOOL_CONFLUENCE_PAGES, args)

    def page(self, page_id: str, *, content_format: str = "markdown", content_type: str = "page") -> Any:
        args: dict[str, Any] = {"cloudId": self.cloud_id, "pageId": str(page_id), "contentFormat": content_format}
        if content_type != "page":
            args["contentType"] = content_type
        return self.gateway.call(TOOL_CONFLUENCE_PAGE, args)

    def descendants(self, page_id: str, *, limit: int = 25, depth: int = 1, cursor: str | None = None) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "pageId": str(page_id),
            "limit": _limit(limit),
            "depth": _limit(depth, 10),
        }
        if cursor:
            args["cursor"] = cursor
        return self.gateway.call(TOOL_CONFLUENCE_DESCENDANTS, args)

    def cql(self, cql: str, *, limit: int = 25, cursor: str | None = None) -> Any:
        args: dict[str, Any] = {"cloudId": self.cloud_id, "cql": cql, "limit": _limit(limit)}
        if cursor:
            args["cursor"] = cursor
        return self.gateway.call(TOOL_CONFLUENCE_CQL, args)

    def footer_comments(
        self,
        page_id: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
        content_format: str = "markdown",
        replies: bool = False,
    ) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "pageId": str(page_id),
            "limit": _limit(limit),
            "contentFormat": content_format,
        }
        if replies:
            args["includeReplies"] = True
        if cursor:
            args["cursor"] = cursor
        return self.gateway.call(TOOL_CONFLUENCE_FOOTER_COMMENTS, args)

    def inline_comments(
        self,
        page_id: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
        content_format: str = "markdown",
        resolution: str = "open",
        replies: bool = False,
    ) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "pageId": str(page_id),
            "limit": _limit(limit),
            "contentFormat": content_format,
            "resolutionStatus": resolution,
        }
        if replies:
            args["includeReplies"] = True
        if cursor:
            args["cursor"] = cursor
        return self.gateway.call(TOOL_CONFLUENCE_INLINE_COMMENTS, args)

    def comment_children(
        self,
        comment_id: str,
        kind: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
        content_format: str = "markdown",
    ) -> Any:
        args: dict[str, Any] = {
            "cloudId": self.cloud_id,
            "commentId": str(comment_id),
            "commentType": kind,
            "limit": _limit(limit),
            "contentFormat": content_format,
        }
        if cursor:
            args["cursor"] = cursor
        return self.gateway.call(TOOL_CONFLUENCE_COMMENT_CHILDREN, args)
