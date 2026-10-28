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


@runtime_checkable
class JiraGateway(Protocol):
    name: str

    def call(self, tool: str, args: dict[str, Any]) -> Any:
        """Invoke one tool and return its decoded payload (dict, list, or str)."""
        ...

    def close(self) -> None: ...


def canonical_args(args: dict[str, Any]) -> str:
    """Stable string for matching fixtures. ``cloudId`` is ignored so fixtures are site-independent."""
    clean = {k: v for k, v in args.items() if k != "cloudId" and v is not None}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str)
