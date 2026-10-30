"""Raw Jira / MCP payloads -> records. Accepts both the Remote MCP Server shapes and plain REST shapes."""

from __future__ import annotations

from typing import Any

from ..adf import adf_to_markdown
from .records import (
    Comment,
    FieldMeta,
    IssueRecord,
    IssueRef,
    IssueType,
    Link,
    LinkType,
    Project,
    Status,
    Transition,
    User,
)

DEFAULT_FIELDS: tuple[str, ...] = (
    "summary",
    "description",
    "status",
    "issuetype",
    "priority",
    "labels",
    "components",
    "assignee",
    "reporter",
    "created",
    "updated",
    "resolution",
    "project",
    "parent",
    "duedate",
    "issuelinks",
)

# The fields a list view needs: everything above except the two that carry a body per issue.
# A 100-issue page with descriptions rendered to Markdown can pass the transport's event size
# limit; a page of these never does.
LIST_FIELDS: tuple[str, ...] = tuple(f for f in DEFAULT_FIELDS if f not in ("description", "issuelinks"))


def _name(obj: Any) -> str | None:
    if isinstance(obj, dict):
        return obj.get("name") or obj.get("displayName") or obj.get("value")
    return None if obj is None else str(obj)


def _text(value: Any) -> str | None:
    """Description or comment body: Markdown string, ADF document, or nothing."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("type") == "doc":
        return adf_to_markdown(value)
    return str(value)


def _status(obj: Any) -> Status | None:
    if not isinstance(obj, dict):
        return None
    cat = obj.get("statusCategory") or {}
    return Status(obj.get("id"), obj.get("name", ""), cat.get("key"))


def _issue_type(obj: Any) -> IssueType | None:
    if not isinstance(obj, dict):
        return None
    return IssueType(obj.get("id"), obj.get("name", ""), bool(obj.get("subtask")), obj.get("hierarchyLevel"))


def _user(obj: Any) -> User | None:
    if not isinstance(obj, dict):
        return None
    return User(
        obj.get("accountId"), obj.get("displayName") or obj.get("name"), obj.get("emailAddress"), obj.get("active")
    )


def _ref(obj: Any) -> IssueRef | None:
    if not isinstance(obj, dict) or not obj.get("key"):
        return None
    f = obj.get("fields") or {}
    st = _status(f.get("status"))
    return IssueRef(
        key=obj["key"],
        id=obj.get("id"),
        summary=f.get("summary"),
        status=st.name if st else None,
        status_category=st.category if st else None,
        issue_type=_name(f.get("issuetype")),
    )


def _links(items: Any) -> tuple[Link, ...]:
    out: list[Link] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        t = item.get("type") or {}
        if item.get("outwardIssue"):
            other = _ref(item["outwardIssue"])
            if other:
                out.append(Link(item.get("id"), t.get("name", ""), "outward", t.get("outward", ""), other))
        if item.get("inwardIssue"):
            other = _ref(item["inwardIssue"])
            if other:
                out.append(Link(item.get("id"), t.get("name", ""), "inward", t.get("inward", ""), other))
    return tuple(out)


def _comments(obj: Any) -> tuple[Comment, ...]:
    items = obj.get("comments") if isinstance(obj, dict) else obj
    out: list[Comment] = []
    for c in items or []:
        if not isinstance(c, dict):
            continue
        author = _user(c.get("author"))
        out.append(
            Comment(
                c.get("id"),
                author.display_name if author else None,
                author.account_id if author else None,
                c.get("created"),
                c.get("updated"),
                _text(c.get("body")) or "",
            )
        )
    return tuple(out)


def issue_from_raw(raw: dict[str, Any], site: str) -> IssueRecord:
    """Turn one raw issue (``{"key", "id", "fields": {...}}``) into an IssueRecord."""
    f = raw.get("fields") or {}
    key = raw.get("key") or ""
    st = _status(f.get("status"))
    it = _issue_type(f.get("issuetype"))
    project = f.get("project") or {}
    assignee = _user(f.get("assignee"))
    reporter = _user(f.get("reporter"))
    custom = {k: v for k, v in f.items() if k.startswith("customfield_") and v not in (None, [], {})}
    return IssueRecord(
        key=key,
        id=raw.get("id"),
        project=project.get("key"),
        project_name=project.get("name"),
        issue_type=it.name if it else None,
        summary=f.get("summary") or "",
        status=st.name if st else None,
        status_category=st.category if st else None,
        resolution=_name(f.get("resolution")),
        priority=_name(f.get("priority")),
        assignee=assignee.display_name if assignee else None,
        assignee_id=assignee.account_id if assignee else None,
        reporter=reporter.display_name if reporter else None,
        reporter_id=reporter.account_id if reporter else None,
        labels=tuple(f.get("labels") or ()),
        components=tuple(_name(c) or "" for c in f.get("components") or ()),
        parent=_ref(f.get("parent")),
        created=f.get("created"),
        updated=f.get("updated"),
        due=f.get("duedate"),
        url=raw.get("webUrl") or f"{site.rstrip('/')}/browse/{key}",
        description=_text(f.get("description")),
        links=_links(f.get("issuelinks")),
        comments=_comments(f.get("comment")),
        custom=custom,
        raw=raw,
    )


def _nodes(payload: Any) -> list[dict[str, Any]]:
    """Issues from a search or get payload, whichever shape it has."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if not isinstance(payload, dict):
        return []
    issues = payload.get("issues")
    if isinstance(issues, dict):  # Remote MCP Server: {"issues": {"nodes": [...], ...}}
        return [n for n in issues.get("nodes") or [] if isinstance(n, dict)]
    if isinstance(issues, list):  # REST: {"issues": [...]}
        return [n for n in issues if isinstance(n, dict)]
    if payload.get("key") and "fields" in payload:  # a single REST issue
        return [payload]
    return []


def issues_from_search(payload: Any, site: str) -> tuple[list[IssueRecord], str | None]:
    """Records plus the token for the next page (None when there is none)."""
    records = [issue_from_raw(n, site) for n in _nodes(payload)]
    token: str | None = None
    if isinstance(payload, dict):
        issues = payload.get("issues")
        page = (issues.get("pageInfo") if isinstance(issues, dict) else None) or payload.get("pageInfo") or {}
        if page.get("hasNextPage"):
            token = page.get("endCursor")
        token = token or payload.get("nextPageToken")
    return records, token


def issue_from_get(payload: Any, site: str) -> IssueRecord | None:
    nodes = _nodes(payload)
    return issue_from_raw(nodes[0], site) if nodes else None


def transitions_from_raw(payload: Any) -> list[Transition]:
    items = payload.get("transitions") if isinstance(payload, dict) else payload
    out: list[Transition] = []
    for t in items or []:
        st = _status(t.get("to")) or Status(None, "", None)
        out.append(Transition(str(t.get("id")), t.get("name", ""), st, bool(t.get("isAvailable", True))))
    return out


def link_types_from_raw(payload: Any) -> list[LinkType]:
    items = payload.get("issueLinkTypes") if isinstance(payload, dict) else payload
    return [
        LinkType(str(t.get("id")), t.get("name", ""), t.get("inward", ""), t.get("outward", "")) for t in items or []
    ]


def fields_from_raw(payload: Any) -> list[FieldMeta]:
    items = payload.get("fields") if isinstance(payload, dict) else payload
    if isinstance(items, dict):  # REST createmeta keyed by field id
        items = [dict(v, fieldId=k) for k, v in items.items()]
    out: list[FieldMeta] = []
    for f in items or []:
        schema = f.get("schema") or {}
        allowed = tuple(str(_name(v)) for v in f.get("allowedValues") or () if _name(v) is not None)
        out.append(
            FieldMeta(
                id=f.get("fieldId") or f.get("key") or "",
                name=f.get("name", ""),
                required=bool(f.get("required")),
                type=schema.get("type"),
                allowed_values=allowed,
                has_default=bool(f.get("hasDefaultValue")),
            )
        )
    return out


def issue_types_from_raw(payload: Any) -> list[IssueType]:
    items = payload.get("issueTypes") if isinstance(payload, dict) else payload
    return [t for t in (_issue_type(i) for i in items or []) if t]


def projects_from_raw(payload: Any) -> list[Project]:
    items = payload.get("values") if isinstance(payload, dict) else payload
    out: list[Project] = []
    for p in items or []:
        if not isinstance(p, dict) or not p.get("key"):
            continue
        out.append(
            Project(
                id=str(p.get("id")),
                key=p["key"],
                name=(p.get("name") or "").strip(),
                type=p.get("projectTypeKey"),
                style=p.get("style"),
                category=_name(p.get("projectCategory")),
                issue_types=tuple(issue_types_from_raw(p.get("issueTypes") or [])),
            )
        )
    return out


def user_from_raw(payload: Any) -> dict[str, Any]:
    """``atlassianUserInfo`` (or REST ``/myself``) -> a small flat dict."""
    if not isinstance(payload, dict):
        return {}
    profile = payload.get("extended_profile") or {}
    return {
        "account_id": payload.get("account_id") or payload.get("accountId"),
        "name": payload.get("name") or payload.get("displayName"),
        "email": payload.get("email") or payload.get("emailAddress"),
        "job_title": profile.get("job_title"),
        "department": profile.get("department"),
        "locale": payload.get("locale"),
        "account_status": payload.get("account_status"),
    }
