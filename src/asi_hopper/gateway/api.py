"""JiraApi: builds every tool call in one place so gateways, fixtures, and services agree on arguments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..model.normalise import DEFAULT_FIELDS
from .base import (
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
