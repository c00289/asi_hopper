"""MetaService: who am I, which projects, which issue types, which fields, which link types."""

from __future__ import annotations

from typing import Any

from ..errors import NotFound
from ..gateway.api import JiraApi
from ..model import (
    FieldMeta,
    IssueType,
    LinkType,
    Project,
    fields_from_raw,
    issue_types_from_raw,
    link_types_from_raw,
    projects_from_raw,
    user_from_raw,
)


class MetaService:
    def __init__(self, api: JiraApi, site: str) -> None:
        self.api = api
        self.site = site

    def whoami(self) -> dict[str, Any]:
        return user_from_raw(self.api.myself())

    def resources(self) -> list[dict[str, Any]]:
        payload = self.api.resources()
        items = payload if isinstance(payload, list) else []
        merged: dict[str, dict[str, Any]] = {}
        for item in items:
            entry = merged.setdefault(
                item.get("id", ""),
                {"id": item.get("id"), "url": item.get("url"), "name": item.get("name"), "scopes": []},
            )
            entry["scopes"] = sorted(set(entry["scopes"]) | set(item.get("scopes") or []))
        return list(merged.values())

    def projects(self, search: str | None = None) -> list[Project]:
        out: list[Project] = []
        start = 0
        while True:
            payload = self.api.projects(search, start_at=start)
            page = projects_from_raw(payload)
            out.extend(page)
            if not isinstance(payload, dict) or payload.get("isLast", True) or not page:
                return out
            start += len(page)

    def project(self, key: str) -> Project:
        key = key.strip().upper()
        for p in self.projects(key):
            if p.key == key:
                return p
        raise NotFound(f"project {key} not visible to this account")

    def issue_types(self, project: str) -> list[IssueType]:
        return issue_types_from_raw(self.api.issue_types(project.strip().upper()))

    def resolve_issue_type(self, project: str, name_or_id: str) -> IssueType:
        wanted = name_or_id.strip().lower()
        types = self.issue_types(project)
        for t in types:
            if t.id == wanted or t.name.lower() == wanted:
                return t
        raise NotFound(f"issue type {name_or_id!r} not in {project}; known: {', '.join(t.name for t in types)}")

    def fields(self, project: str, issue_type: str, *, required_only: bool = True) -> list[FieldMeta]:
        t = self.resolve_issue_type(project, issue_type)
        assert t.id is not None
        return fields_from_raw(self.api.fields_for(project.strip().upper(), t.id, required_only=required_only))

    def link_types(self) -> list[LinkType]:
        return link_types_from_raw(self.api.link_types())
