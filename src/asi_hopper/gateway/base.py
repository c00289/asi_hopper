"""The gateway protocol: ``call(tool, args) -> payload``. Tool names are the Atlassian Remote MCP Server's."""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

# Tool names exposed by https://mcp.atlassian.com (the same ones the claude.ai connector shows).
TOOL_USER_INFO = "atlassianUserInfo"
TOOL_RESOURCES = "getAccessibleAtlassianResources"
TOOL_PROJECTS = "getVisibleJiraProjects"
TOOL_ISSUE_TYPES = "getJiraProjectIssueTypesMetadata"
TOOL_FIELDS = "getJiraIssueTypeMetaWithFields"
TOOL_GET_ISSUE = "getJiraIssue"
TOOL_SEARCH = "searchJiraIssuesUsingJql"
TOOL_TRANSITIONS = "getTransitionsForJiraIssue"
TOOL_LINK_TYPES = "getIssueLinkTypes"
TOOL_REMOTE_LINKS = "getJiraIssueRemoteIssueLinks"

# Confluence, read side (exercised live on 2026-10-29; see docs/confluence-sandbox-2026-10-29.md).
TOOL_CONFLUENCE_SPACES = "getConfluenceSpaces"
TOOL_CONFLUENCE_PAGES = "getPagesInConfluenceSpace"
TOOL_CONFLUENCE_PAGE = "getConfluencePage"
TOOL_CONFLUENCE_DESCENDANTS = "getConfluencePageDescendants"
TOOL_CONFLUENCE_CQL = "searchConfluenceUsingCql"
TOOL_CONFLUENCE_FOOTER_COMMENTS = "getConfluencePageFooterComments"
TOOL_CONFLUENCE_INLINE_COMMENTS = "getConfluencePageInlineComments"
TOOL_CONFLUENCE_COMMENT_CHILDREN = "getConfluenceCommentChildren"
# Read tools the adapter does not use: ``fetch`` (a page by ARI, a subset of getConfluencePage), ``search``
# (Rovo, cross-product, "may consume up to 10 Rovo Credits" a call) and ``getContentFormatGuide``
# (authoring guidance for the write tools). Named so the inventory can classify them.
TOOL_FETCH = "fetch"
TOOL_ROVO_SEARCH = "search"
TOOL_CONTENT_FORMAT_GUIDE = "getContentFormatGuide"

# Confluence, write side: named so the contract can say what it refuses. Hopper never calls one.
TOOL_CONFLUENCE_CREATE_PAGE = "createConfluencePage"
TOOL_CONFLUENCE_UPDATE_PAGE = "updateConfluencePage"
TOOL_CONFLUENCE_CREATE_FOOTER_COMMENT = "createConfluenceFooterComment"
TOOL_CONFLUENCE_CREATE_INLINE_COMMENT = "createConfluenceInlineComment"

READ_TOOLS = frozenset(
    {
        TOOL_USER_INFO,
        TOOL_RESOURCES,
        TOOL_PROJECTS,
        TOOL_ISSUE_TYPES,
        TOOL_FIELDS,
        TOOL_GET_ISSUE,
        TOOL_SEARCH,
        TOOL_TRANSITIONS,
        TOOL_LINK_TYPES,
        TOOL_REMOTE_LINKS,
    }
)

CONFLUENCE_READ_TOOLS = frozenset(
    {
        TOOL_CONFLUENCE_SPACES,
        TOOL_CONFLUENCE_PAGES,
        TOOL_CONFLUENCE_PAGE,
        TOOL_CONFLUENCE_DESCENDANTS,
        TOOL_CONFLUENCE_CQL,
        TOOL_CONFLUENCE_FOOTER_COMMENTS,
        TOOL_CONFLUENCE_INLINE_COMMENTS,
        TOOL_CONFLUENCE_COMMENT_CHILDREN,
    }
)

CONFLUENCE_WRITE_TOOLS = frozenset(
    {
        TOOL_CONFLUENCE_CREATE_PAGE,
        TOOL_CONFLUENCE_UPDATE_PAGE,
        TOOL_CONFLUENCE_CREATE_FOOTER_COMMENT,
        TOOL_CONFLUENCE_CREATE_INLINE_COMMENT,
    }
)


# A pseudo tool name: ``call(LIST_TOOLS, {})`` answers with the server's tool inventory (name,
# description, input schema) instead of invoking a tool, so the inventory records and replays
# like any other payload.
LIST_TOOLS = "__list_tools__"


@runtime_checkable
class JiraGateway(Protocol):
    """The gateway protocol. The name is historical: the same gateway serves the Confluence tools."""

    name: str

    def call(self, tool: str, args: dict[str, Any]) -> Any:
        """Invoke one tool and return its decoded payload (dict, list, or str)."""
        ...

    def close(self) -> None: ...


def canonical_args(args: dict[str, Any]) -> str:
    """Stable string for matching fixtures. ``cloudId`` is ignored so fixtures are site-independent."""
    clean = {k: v for k, v in args.items() if k != "cloudId" and v is not None}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str)
