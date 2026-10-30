import json

from asi_hopper.model import (
    fields_from_raw,
    issue_from_get,
    issue_from_raw,
    issues_from_search,
    projects_from_raw,
    transitions_from_raw,
    user_from_raw,
)

from .conftest import FIXTURES

SITE = "https://asirobots.atlassian.net"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_issue_from_get_normalises_everything() -> None:
    record = issue_from_get(_load("getJiraIssue_HWL-2575.json"), SITE)
    assert record is not None
    assert record.key == "HWL-2575"
    assert record.project == "HWL" and record.project_name == "Wheel Loader (Haulage)"
    assert record.issue_type == "Story"
    assert record.status == "To Do" and record.status_category == "new" and record.is_open
    assert record.priority == "Un-Groomed"
    assert record.assignee == "Ann Lee - C" and record.assignee_id.startswith("557058:")
    assert record.reporter == "Zed Young"
    assert record.parent is not None and record.parent.key == "HWL-1915" and record.parent.issue_type == "Epic"
    assert record.url == "https://asirobots.atlassian.net/browse/HWL-2575"
    assert "- [ ] Step 3 UCAs complete" in (record.description or "")
    assert len(record.links) == 1
    link = record.links[0]
    assert link.type == "Blocks" and link.direction == "inward" and link.description == "is blocked by"
    assert link.other.key == "HWL-2574" and link.other.status == "To Do"
    assert record.comments == ()
    assert record.custom == {}


def test_to_dict_is_json_serialisable_and_flat_where_it_matters() -> None:
    record = issue_from_get(_load("getJiraIssue_HWL-2575.json"), SITE)
    data = record.to_dict()
    json.dumps(data)
    assert "raw" not in data
    assert data["links"][0]["other"]["key"] == "HWL-2574"
    row = record.to_row()
    assert row["parent"] == "HWL-1915" and row["labels"] == ""
    assert "raw" in record.to_dict(include_raw=True)


def test_issues_from_search_and_paging_token() -> None:
    records, token = issues_from_search(_load("searchJiraIssuesUsingJql_open.json"), SITE)
    assert [r.key for r in records] == ["HWL-2572", "HWL-2575", "HWL-2620"]
    assert token is None
    bug = records[2]
    assert bug.labels == ("VAT", "e-stop", "safety", "test-failure")
    assert bug.priority == "High" and bug.parent is None
    records2, token2 = issues_from_search(
        {"issues": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "abc"}}}, SITE
    )
    assert records2 == [] and token2 == "abc"


def test_rest_shapes_are_accepted_too() -> None:
    rest = {
        "issues": [
            {
                "key": "X-1",
                "id": "1",
                "fields": {"summary": "s", "status": {"name": "Done", "statusCategory": {"key": "done"}}},
            }
        ]
    }
    records, _ = issues_from_search(rest, SITE)
    assert records[0].key == "X-1" and not records[0].is_open and records[0].url.endswith("/browse/X-1")
    single = issue_from_raw(
        {
            "key": "X-2",
            "fields": {
                "summary": "t",
                "description": {
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "adf"}]}],
                },
            },
        },
        SITE,
    )
    assert single.description == "adf\n"


def test_transitions_projects_fields_user() -> None:
    transitions = transitions_from_raw(_load("getTransitionsForJiraIssue_HWL-2575.json"))
    assert [t.name for t in transitions] == ["In Progress", "Blocked", "Ready for Approval", "Done"]
    assert transitions[-1].to.category == "done"
    projects = projects_from_raw(_load("getVisibleJiraProjects.json"))
    hwl = next(p for p in projects if p.key == "HWL")
    assert hwl.name == "Wheel Loader (Haulage)" and hwl.style == "classic" and hwl.category == "Construction"
    assert "Story" in [t.name for t in hwl.issue_types]
    fields = fields_from_raw(_load("getJiraIssueTypeMetaWithFields_HWL_10001.json"))
    assert [f.id for f in fields] == ["issuetype", "project", "summary"]
    assert fields[0].allowed_values == ("Story",) and fields[2].required
    me = user_from_raw(_load("atlassianUserInfo.json"))
    assert me["name"] == "Ann Lee - C" and me["job_title"] == "Functional Safety Engineer"


def test_list_fields_drop_the_bodies() -> None:
    from asi_hopper import DEFAULT_FIELDS, LIST_FIELDS

    assert "description" in DEFAULT_FIELDS and "issuelinks" in DEFAULT_FIELDS
    assert "description" not in LIST_FIELDS and "issuelinks" not in LIST_FIELDS
    assert set(LIST_FIELDS) < set(DEFAULT_FIELDS) and "summary" in LIST_FIELDS and "status" in LIST_FIELDS


def test_search_page_size_is_fifty_by_default() -> None:
    import inspect

    from asi_hopper import Hopper

    assert inspect.signature(Hopper.search).parameters["page_size"].default == 50
