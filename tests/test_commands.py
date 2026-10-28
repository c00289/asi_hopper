import json

from asi_hopper import Hopper, IssueRecord
from asi_hopper.errors import NotRecorded

from .conftest import OPEN_JQL


def test_whoami_and_status(hopper: Hopper) -> None:
    r = hopper.execute("whoami")
    assert r.ok and r.verb == "whoami"
    assert r.data["account"]["email"] == "c00289@contractor.asirobots.com"
    assert r.data["gateway"] == "replay" and r.data["policy_mode"] == "read"
    s = hopper.execute("status")
    assert s.ok and s.data["gateway"]["name"] == "replay" and "get" in s.data["commands"]
    json.dumps(s.data)


def test_projects_types_fields_link_types(hopper: Hopper) -> None:
    projects = hopper.execute("projects")
    assert projects.ok and len(projects.data) == 33
    assert any(p["key"] == "FSS" for p in projects.data)
    types = hopper.execute("types", project="hwl")
    assert types.ok and [t["name"] for t in types.data][:2] == ["Epic", "Story"]
    fields = hopper.execute("fields", project="HWL", type="Story")
    assert fields.ok and [f["id"] for f in fields.data] == ["issuetype", "project", "summary"]
    by_id = hopper.execute("fields", project="HWL", type="10001")
    assert by_id.ok
    missing = hopper.execute("fields", project="HWL", type="Nope")
    assert not missing.ok and "known: Epic" in missing.errors[0]
    lt = hopper.execute("link-types")
    assert lt.ok and lt.data[0]["name"] == "Blocks"


def test_get_search_transitions_links_comments(hopper: Hopper) -> None:
    got = hopper.execute("get", key="hwl-2575")
    assert got.ok and got.data["key"] == "HWL-2575" and got.data["parent"]["key"] == "HWL-1915"
    assert "raw" not in got.data
    with_raw = hopper.execute("get", key="HWL-2575", raw=True)
    assert with_raw.ok and with_raw.data["raw"]["key"] == "HWL-2575"
    found = hopper.execute("search", jql=OPEN_JQL)
    assert found.ok and [i["key"] for i in found.data] == ["HWL-2572", "HWL-2575", "HWL-2620"]
    limited = hopper.execute("search", jql=OPEN_JQL, limit=2)
    assert limited.ok and len(limited.data) == 2
    tr = hopper.execute("transitions", key="HWL-2575")
    assert tr.ok and "Done" in [t["name"] for t in tr.data]
    links = hopper.execute("links", key="HWL-2575")
    assert links.ok and links.data[0]["other"]["key"] == "HWL-2574"
    comments = hopper.execute("comments", key="HWL-2575")
    assert comments.ok and comments.data == []


def test_typed_shortcuts(hopper: Hopper) -> None:
    issue = hopper.get("HWL-2575")
    assert isinstance(issue, IssueRecord) and issue.summary.startswith("STPA Step 4")
    issues = hopper.search(OPEN_JQL)
    assert all(isinstance(i, IssueRecord) for i in issues) and len(issues) == 3
    assert hopper.whoami()["account_id"].startswith("712020:")


def test_wire_format_matches_dewey(hopper: Hopper) -> None:
    r = hopper.execute_dict({"verb": "get", "args": {"key": "HWL-2575"}, "actor": "agent"})
    d = r.to_dict()
    assert set(d) == {"ok", "verb", "data", "errors", "warnings"}
    assert d["ok"] and d["verb"] == "get"
    bad = hopper.execute_dict({"args": {}})
    assert not bad.ok
    bad2 = hopper.execute_dict({"verb": "get", "args": []})
    assert not bad2.ok


def test_errors_become_results(hopper: Hopper) -> None:
    unknown = hopper.execute("teleport")
    assert not unknown.ok and "unknown command" in unknown.errors[0]
    missing = hopper.execute("get")
    assert not missing.ok and "missing required argument 'key'" in missing.errors[0]
    extra = hopper.execute("get", key="HWL-2575", bogus=1)
    assert not extra.ok and "unknown argument 'bogus'" in extra.errors[0]
    unrecorded = hopper.execute("get", key="HWL-9999")
    assert not unrecorded.ok and "no fixture" in unrecorded.errors[0]
    bad_choice = hopper.execute("auth", action="dance")
    assert not bad_choice.ok and "must be one of" in bad_choice.errors[0]


def test_replay_never_touches_the_network(hopper: Hopper) -> None:
    import pytest

    with pytest.raises(NotRecorded):
        hopper.api.get_issue("HWL-1")
    assert hopper.gateway.calls[-1][0] == "getJiraIssue"


def test_schema_describes_verbs(hopper: Hopper) -> None:
    all_verbs = hopper.execute("schema")
    assert all_verbs.ok and "summary" in all_verbs.data["default_fields"]
    verbs = {v["verb"] for v in all_verbs.data["verbs"]}
    assert {
        "whoami",
        "projects",
        "types",
        "fields",
        "get",
        "search",
        "transitions",
        "links",
        "comments",
        "snapshot",
        "diff",
        "verify",
        "schema",
        "status",
        "auth",
        "link-types",
    } <= verbs
    assert all(not v["writes"] for v in all_verbs.data["verbs"])
    one = hopper.execute("schema", name="search")
    assert one.ok and one.data["verb"] == "search"


def test_auth_status_and_login_refusal_on_replay(hopper: Hopper) -> None:
    status = hopper.execute("auth", action="status")
    assert status.ok and "logged_in" in status.data
    login = hopper.execute("auth", action="login")
    assert not login.ok and "needs the mcp gateway" in login.errors[0]
