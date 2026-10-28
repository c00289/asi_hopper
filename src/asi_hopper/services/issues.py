"""IssueService: get, search (with paging), transitions, links, comments."""

from __future__ import annotations

from collections.abc import Sequence

from ..errors import NotFound
from ..gateway.api import JiraApi
from ..model import (
    Comment,
    IssueRecord,
    Link,
    Transition,
    issue_from_get,
    issues_from_search,
    transitions_from_raw,
)

MAX_PAGES = 200  # 100 issues a page: a hard stop so `--all` on a bad JQL cannot run forever


class IssueService:
    def __init__(self, api: JiraApi, site: str) -> None:
        self.api = api
        self.site = site

    def get(self, key: str, *, fields: Sequence[str] | None = None, comments: bool = False) -> IssueRecord:
        key = key.strip().upper()
        record = issue_from_get(self.api.get_issue(key, fields, comments=comments), self.site)
        if record is None:
            raise NotFound(f"issue {key} not found or not visible to this account")
        return record

    def search(
        self,
        jql: str,
        *,
        fields: Sequence[str] | None = None,
        max_results: int = 50,
        all_pages: bool = False,
        limit: int | None = None,
    ) -> list[IssueRecord]:
        """Run JQL. ``all_pages`` follows the cursor; ``limit`` caps the total either way."""
        records: list[IssueRecord] = []
        token: str | None = None
        pages = 0
        while True:
            page, token = issues_from_search(
                self.api.search(jql, fields, max_results=max_results, next_page_token=token), self.site
            )
            records.extend(page)
            pages += 1
            if limit is not None and len(records) >= limit:
                return records[:limit]
            if not all_pages or not token or not page or pages >= MAX_PAGES:
                return records

    def transitions(self, key: str) -> list[Transition]:
        return transitions_from_raw(self.api.transitions(key.strip().upper()))

    def links(self, key: str) -> list[Link]:
        return list(self.get(key, fields=["summary", "status", "issuetype", "project", "issuelinks"]).links)

    def comments(self, key: str) -> list[Comment]:
        return list(self.get(key, fields=["summary", "status", "issuetype", "project"], comments=True).comments)
