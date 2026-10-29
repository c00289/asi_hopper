"""Confluence, read only: the verb, the typed shortcuts, the normalisers and the closed write side, all on fixtures."""

from __future__ import annotations

import json

import pytest

from asi_hopper import Hopper
from asi_hopper.errors import WriteSideClosed
from asi_hopper.gateway import ClosedConfluenceWriteSide, ConfluenceWriteSide
from asi_hopper.gateway.base import CONFLUENCE_READ_TOOLS, CONFLUENCE_WRITE_TOOLS, LIST_TOOLS
from asi_hopper.model import PageRecord, PageRef
from asi_hopper.model.confluence import cql_from_raw, next_cursor, page_from_raw
from asi_hopper.services.confluence import DEFAULT_CQL, ConfluenceService

from .conftest import FIXTURES

PAGE = "399343803"  # Locator Safety Function STPA, space STPA
SITE = "https://asirobots.atlassian.net"


def test_spaces(hopper: Hopper) -> None:
    r = hopper.execute("confluence", action="spaces", limit=5)
    assert r.ok and [s["key"] for s in r.data] == ["VSP", "OPT", "MOBIUS", "MP", "EP"]
    assert r.data[0]["url"] == f"{SITE}/wiki/spaces/VSP" and r.data[0]["type"] == "global"
    named = hopper.execute("confluence", action="spaces", target="STPA,FST")
    assert named.ok and [(s["key"], s["id"]) for s in named.data] == [("STPA", "5791547559"), ("FST", "7664632664")]


def test_pages_of_a_space_by_key_and_by_id(hopper: Hopper) -> None:
    by_key = hopper.execute("confluence", action="pages", target="stpa", limit=5)
    assert by_key.ok and len(by_key.data) == 5
    first = by_key.data[0]
    assert first["id"] == "262996144" and first["title"] == "V2X to VCU STPA (Old Format)"
    assert first["parent_id"] == "5852037127" and first["space_id"] == "5791547559"
    assert first["url"] == f"{SITE}/wiki/pages/viewpage.action?pageId=262996144"
    assert first["last_modified"].startswith("2026-10-13")
    # the key was resolved through one getConfluenceSpaces call; an id needs none
    tools = [t for t, _ in hopper.gateway.calls]
    assert tools == ["getConfluenceSpaces", "getPagesInConfluenceSpace"]
    by_id = hopper.execute("confluence", action="pages", target="5791547559", limit=5, max=2)
    assert by_id.ok and len(by_id.data) == 2 and hopper.gateway.calls[-1][0] == "getPagesInConfluenceSpace"


def test_page_in_every_body_format(hopper: Hopper) -> None:
    md = hopper.execute("confluence", action="page", target=PAGE)
    assert md.ok and md.data["title"] == "Locator Safety Function STPA"
    assert md.data["space_id"] == "5791547559" and md.data["parent_id"] == "6051201086"
    assert md.data["version"] == 45 and md.data["updated"].startswith("2021-10-20")
    assert md.data["body_format"] == "markdown" and md.data["body"].startswith("Related Links:")
    assert "raw" not in md.data and md.data["url"].endswith(f"pageId={PAGE}")
    adf = hopper.execute("confluence", action="page", target=PAGE, format="adf", raw=True)
    assert adf.ok and adf.data["body"]["type"] == "doc" and adf.data["raw"]["id"] == PAGE
    html = hopper.execute("confluence", action="page", target=PAGE, format="html")
    assert html.ok and html.data["body"].startswith("<section")
    bad = hopper.execute("confluence", action="page", target=PAGE, format="wiki")
    assert not bad.ok and "must be one of" in bad.errors[0]


def test_children_search_and_comments(hopper: Hopper) -> None:
    kids = hopper.execute("confluence", action="children", target=PAGE, limit=5)
    assert kids.ok and [k["title"] for k in kids.data] == [
        "Low-precision GPS loss scenario details",
        "Proximity Monitor Risk Scenarios",
    ]
    assert kids.data[0]["depth"] == 1 and kids.data[0]["parent_id"] == PAGE

    mine = hopper.execute("confluence", action="search", limit=5)
    assert mine.ok and mine.data == []  # the owner has not edited a page: the default CQL finds none
    assert mine.warnings == [f"no CQL given; ran the user-scoped default: {DEFAULT_CQL}"]
    assert hopper.gateway.calls[-1][1]["cql"] == DEFAULT_CQL

    stpa = hopper.execute(
        "confluence", action="search", target="type = page ORDER BY lastmodified DESC", space="stpa", limit=3
    )
    assert stpa.ok and stpa.warnings == [] and len(stpa.data) == 3
    assert hopper.gateway.calls[-1][1]["cql"] == "space = STPA AND (type = page) ORDER BY lastmodified DESC"
    hit = stpa.data[0]
    assert hit["space_key"] == "STPA" and hit["type"] == "page" and hit["excerpt"].startswith("Table of Contents")
    assert hit["url"] == f"{SITE}/wiki/spaces/STPA/pages/262996144/V2X+to+VCU+STPA+Old+Format"

    comments = hopper.execute("confluence", action="comments", target=PAGE, limit=5)
    assert comments.ok and [c["kind"] for c in comments.data] == ["inline"] * 3  # no footer comments
    first = comments.data[0]
    assert first["id"] == "5351964709" and first["resolution"] == "open"
    assert first["selection"] == "Feedback data does not reflect the world"
    assert first["body"].startswith("We could add a requirement")
    footer_only = hopper.execute("confluence", action="comments", target=PAGE, kind="footer", limit=5)
    assert (
        footer_only.ok and footer_only.data == [] and hopper.gateway.calls[-1][0] == "getConfluencePageFooterComments"
    )

    replies = hopper.execute("confluence", action="replies", target="5351964709", kind="inline", limit=5)
    assert replies.ok and replies.data == []
    no_kind = hopper.execute("confluence", action="replies", target="5351964709")
    assert not no_kind.ok and "--kind" in no_kind.errors[0]


def test_argument_errors_become_results(hopper: Hopper) -> None:
    missing = hopper.execute("confluence", action="page")
    assert not missing.ok and "a target is required" in missing.errors[0]
    bad = hopper.execute("confluence", action="burn")
    assert not bad.ok and "must be one of" in bad.errors[0]
    unknown = hopper.execute("confluence", action="page", target="1")
    assert not unknown.ok and "no fixture" in unknown.errors[0]


def test_typed_shortcuts(hopper: Hopper) -> None:
    page = hopper.page(PAGE)
    assert isinstance(page, PageRecord) and page.to_row()["version"] == 45
    assert set(page.to_row()) == set(PageRecord.ROW_FIELDS)
    refs = hopper.cql("type = page ORDER BY lastmodified DESC", space="STPA", page_size=3)
    assert all(isinstance(r, PageRef) for r in refs) and len(refs) == 3
    assert hopper.cql(page_size=5) == []


def test_tools_inventory_classifies_every_tool(hopper: Hopper) -> None:
    r = hopper.execute("tools")
    assert r.ok and len(r.data) == 32 and hopper.gateway.calls[-1][0] == LIST_TOOLS
    by_name = {t["name"]: t for t in r.data}
    assert by_name["getConfluencePage"] == {
        "name": "getConfluencePage",
        "product": "confluence",
        "writes": False,
        "used_by_hopper": True,
        "description": by_name["getConfluencePage"]["description"],
        "required": ["cloudId", "pageId"],
        "optional": ["contentType", "contentFormat"],
    }
    assert {t["name"] for t in r.data if t["writes"]} >= CONFLUENCE_WRITE_TOOLS | {"createJiraIssue", "editJiraIssue"}
    assert {t["name"] for t in r.data if t["used_by_hopper"]} >= CONFLUENCE_READ_TOOLS
    assert "search" in by_name and by_name["search"]["product"] == "atlassian"  # Rovo: not used by Hopper
    confluence = hopper.execute("tools", product="confluence", schema=True)
    assert confluence.ok and len(confluence.data) == 13 and "properties" in confluence.data[0]["input_schema"]
    json.dumps(confluence.data)


def test_the_write_side_refuses_without_touching_the_gateway(hopper: Hopper) -> None:
    writes = hopper.confluence_api.writes
    assert isinstance(writes, ClosedConfluenceWriteSide) and isinstance(writes, ConfluenceWriteSide)
    before = len(hopper.gateway.calls)
    with pytest.raises(WriteSideClosed, match="create_page would call createConfluencePage"):
        writes.create_page("5791547559", "A page", "body")
    with pytest.raises(WriteSideClosed, match="updateConfluencePage"):
        writes.update_page(PAGE, body="x")
    with pytest.raises(WriteSideClosed, match="createConfluenceFooterComment"):
        writes.create_footer_comment(PAGE, "hello")
    with pytest.raises(WriteSideClosed, match="createConfluenceInlineComment"):
        writes.create_inline_comment(PAGE, "hello", selection="Feedback data")
    assert len(hopper.gateway.calls) == before  # nothing reached the gateway
    assert set(ClosedConfluenceWriteSide.TOOLS.values()) == CONFLUENCE_WRITE_TOOLS
    with pytest.raises(TypeError):  # the contract itself cannot be instantiated
        ConfluenceWriteSide()  # type: ignore[abstract]
    # no verb writes, so policy mode "read" lets every verb run
    schema = hopper.execute("schema")
    assert schema.ok and all(not v["writes"] for v in schema.data["verbs"])


def test_scoped_cql_keeps_order_by_outside_the_parentheses() -> None:
    assert ConfluenceService.scoped_cql(None) == DEFAULT_CQL
    assert ConfluenceService.scoped_cql(None, "stpa") == (
        "space = STPA AND (contributor = currentUser() AND type = page) ORDER BY lastmodified DESC"
    )
    assert ConfluenceService.scoped_cql("title ~ 'STPA'", "FST") == "space = FST AND (title ~ 'STPA')"


def test_normalisers_on_recorded_shapes() -> None:
    cql = json.loads((FIXTURES / "searchConfluenceUsingCql_space_STPA.json").read_text(encoding="utf-8"))
    refs, cursor = cql_from_raw(cql, SITE)
    assert len(refs) == 3 and cursor and cursor.startswith("_t_")  # taken from _links.next
    assert next_cursor({"_links": {"base": "x"}}) is None and next_cursor([]) is None
    raw = json.loads((FIXTURES / "getConfluencePage_399343803_markdown.json").read_text(encoding="utf-8"))
    page = page_from_raw(raw, SITE)
    assert page is not None and page.version_message is None and page.author_id.startswith("557058:")
    assert page_from_raw({"body": "no id"}, SITE) is None
    rest_shaped = page_from_raw({"id": "7", "title": "t", "body": {"representation": "storage", "value": "<p/>"}}, SITE)
    assert rest_shaped is not None and rest_shaped.body == "<p/>" and rest_shaped.updated is None
