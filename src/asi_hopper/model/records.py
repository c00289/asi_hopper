"""Frozen dataclasses for everything Hopper reads from Jira."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

STATUS_CATEGORIES = ("new", "indeterminate", "done")


@dataclass(frozen=True)
class User:
    account_id: str | None
    display_name: str | None
    email: str | None = None
    active: bool | None = None


@dataclass(frozen=True)
class Status:
    id: str | None
    name: str
    category: str | None  # new | indeterminate | done


@dataclass(frozen=True)
class IssueType:
    id: str | None
    name: str
    subtask: bool = False
    hierarchy_level: int | None = None


@dataclass(frozen=True)
class IssueRef:
    key: str
    id: str | None = None
    summary: str | None = None
    status: str | None = None
    status_category: str | None = None
    issue_type: str | None = None


@dataclass(frozen=True)
class Link:
    id: str | None
    type: str  # "Blocks"
    direction: str  # inward | outward, from the point of view of the issue holding the link
    description: str  # "is blocked by" / "blocks"
    other: IssueRef


@dataclass(frozen=True)
class LinkType:
    id: str
    name: str
    inward: str
    outward: str


@dataclass(frozen=True)
class Comment:
    id: str | None
    author: str | None
    author_id: str | None
    created: str | None
    updated: str | None
    body: str


@dataclass(frozen=True)
class Transition:
    id: str
    name: str
    to: Status
    available: bool = True


@dataclass(frozen=True)
class FieldMeta:
    id: str
    name: str
    required: bool
    type: str | None
    allowed_values: tuple[str, ...] = ()
    has_default: bool = False


@dataclass(frozen=True)
class Project:
    id: str
    key: str
    name: str
    type: str | None = None
    style: str | None = None
    category: str | None = None
    issue_types: tuple[IssueType, ...] = ()


@dataclass(frozen=True)
class IssueRecord:
    """One Jira issue, flattened. ``to_dict()`` is the evidence and sibling-facing shape."""

    key: str
    id: str | None
    project: str | None
    project_name: str | None
    issue_type: str | None
    summary: str
    status: str | None
    status_category: str | None
    resolution: str | None
    priority: str | None
    assignee: str | None
    assignee_id: str | None
    reporter: str | None
    reporter_id: str | None
    labels: tuple[str, ...]
    components: tuple[str, ...]
    parent: IssueRef | None
    created: str | None
    updated: str | None
    due: str | None
    url: str
    description: str | None
    links: tuple[Link, ...] = ()
    comments: tuple[Comment, ...] = ()
    custom: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_subtask(self) -> bool:
        return bool(self.raw.get("fields", {}).get("issuetype", {}).get("subtask"))

    @property
    def is_open(self) -> bool:
        return self.status_category != "done"

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["labels"] = list(self.labels)
        data["components"] = list(self.components)
        data["links"] = [asdict(link) for link in self.links]
        data["comments"] = [asdict(c) for c in self.comments]
        if not include_raw:
            data.pop("raw", None)
        return data

    ROW_FIELDS: ClassVar[tuple[str, ...]] = (
        "key",
        "type",
        "summary",
        "status",
        "status_category",
        "priority",
        "assignee",
        "reporter",
        "labels",
        "parent",
        "created",
        "updated",
        "due",
        "url",
    )

    def to_row(self) -> dict[str, Any]:
        """Flat, scalar-only view for CSV and for a sibling's table (columns: ``ROW_FIELDS``)."""
        return {
            "key": self.key,
            "type": self.issue_type,
            "summary": self.summary,
            "status": self.status,
            "status_category": self.status_category,
            "priority": self.priority,
            "assignee": self.assignee,
            "reporter": self.reporter,
            "labels": ";".join(self.labels),
            "parent": self.parent.key if self.parent else None,
            "created": self.created,
            "updated": self.updated,
            "due": self.due,
            "url": self.url,
        }
