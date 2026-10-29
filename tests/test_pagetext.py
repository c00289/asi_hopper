"""Page anatomy (0.1.9): sections, tables, links and the formatting facts, on the synthetic fixture page and by hand.

The fixture page is synthetic: it has the shape the Remote MCP Server renders (four ``##`` sections, a context
table with glued bold runs and a struck fragment, a loss-scenario table), with neutral text. Its codes are data.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from asi_hopper.model import PageLink, Section, Table
from asi_hopper.model.confluence import page_from_raw
from asi_hopper.model.pagetext import (
    bold_runs,
    find_section,
    heading_anchor,
    links,
    page_id_of,
    section_sha256,
    sections,
    split_on_bold,
    strike,
    tables,
)

from .conftest import FIXTURES

SITE = "https://asirobots.atlassian.net"
HEADINGS = ["Losses and Hazards", "Control Structure", "Context Table", "Loss Scenarios"]
ANCHORS = ["Losses-and-Hazards", "Control-Structure", "Context-Table", "Loss-Scenarios"]


@pytest.fixture(scope="module")
def body() -> str:
    raw = json.loads((FIXTURES / "getConfluencePage_399343803_markdown.json").read_text(encoding="utf-8"))
    return raw["body"]


# -- the synthetic fixture page -----------------------------------------------------------------
def test_sections_of_the_fixture_page(body: str) -> None:
    found = sections(body)
    assert [s.level for s in found] == [0, 2, 2, 2, 2]
    assert [s.heading for s in found] == ["", *HEADINGS] and [s.anchor for s in found] == ["", *ANCHORS]
    lines = body.splitlines()
    preamble = found[0]
    assert preamble.start == 0 and preamble.text.startswith("Related Links:") and "## " not in preamble.text
    for section in found[1:]:
        assert lines[section.start] == f"## {section.heading}"  # start is the heading line
        assert not section.text.startswith("#")  # text excludes it
    assert [s.start for s in found[1:]] == [s.end for s in found[:-1]]  # contiguous spans
    assert found[-1].end == len(lines)
    context = found[3]
    assert context.text.startswith("| **Controller**") and context.text.endswith("---")
    assert context.sha256 == hashlib.sha256(context.text.encode("utf-8")).hexdigest() == section_sha256(context)
    assert context.chars == len(context.text) and len(context.sha256) == 64
    assert [s.sha256 for s in sections(body)] == [s.sha256 for s in found]  # stable
    assert len({s.sha256 for s in found}) == 5
    assert isinstance(context, Section) and context == found[3]


def test_find_section_equal_then_containing(body: str) -> None:
    found = sections(body)
    assert find_section(found, "context table").heading == "Context Table"
    assert find_section(found, "Hazards").heading == "Losses and Hazards"
    assert find_section(found, "Appendix") is None and find_section(found, "") is None
    both = sections("# Table\n\na\n\n# Context Table\n\nb\n")
    assert find_section(both, "table").heading == "Table"  # an equal heading beats a containing one
    assert find_section(both, "Context").heading == "Context Table"


def test_tables_of_the_fixture_page(body: str) -> None:
    found = sections(body)
    context = tables(find_section(found, "Context Table").text)
    assert len(context) == 1 and isinstance(context[0], Table)
    table = context[0]
    assert table.width == 6 and table.header[:2] == ("**Controller**", "**Control Action**")
    assert table.header[2] == "**Not Providing**Missing"
    assert len(table.rows) == 3 and all(len(r) == 6 for r in table.rows)
    assert [r[0] for r in table.rows] == ["Stop Controller", "Planner", "Motion Controller"]
    assert table.rows[1][3] == "" and table.rows[1][5] == ""  # empty cells stay empty
    assert table.rows[2][2].startswith("[Braking STPA](") and table.rows[2][3:] == ("", "", "")
    lines = find_section(found, "Context Table").text.splitlines()
    assert lines[table.start].startswith("| **Controller**") and table.end == table.start + 5

    scenarios = tables(find_section(found, "Loss Scenarios").text)
    assert len(scenarios) == 1
    table = scenarios[0]
    assert table.header == ("", "**UCA**", "**Type**", "**Causal Factors**", "**Constraints**")
    assert len(table.rows) == 12 and all(len(r) == 5 for r in table.rows)
    assert [r[0] for r in table.rows] == [str(n) for n in range(1, 13)]
    assert table.rows[11] == ("12", "", "**Type 3: **Control Path**Type 4: **Controlled Process", "", "")
    assert tables(find_section(found, "Control Structure").text) == []
    assert len(tables(body)) == 2


def test_links_of_the_fixture_page(body: str) -> None:
    found = links(body)
    assert all(isinstance(link, PageLink) for link in found)
    assert [(link.label, link.page_id) for link in found] == [
        ("Top-level STPA", "100000001"),
        ("Sibling Function STPA", "100000002"),
        ("Braking STPA", "100000003"),
    ]
    assert found[0].url == "https://example.invalid/wiki/spaces/STPA/pages/100000001/Top-level+STPA"
    cell = tables(find_section(sections(body), "Context Table").text)[0].rows[2][2]
    assert links(cell) == [
        PageLink("Braking STPA", "https://example.invalid/wiki/spaces/STPA/pages/100000003", "100000003")
    ]


def test_strike_on_the_struck_cells(body: str) -> None:
    found = sections(body)
    cell = tables(find_section(found, "Context Table").text)[0].rows[0][2]
    assert "~~" in cell
    clean, struck = strike(cell)
    assert struck and "~~" not in clean
    assert "**UCA3 **When the planner is guiding the vehicle into another machine. *\\[H1\\] (duplicate of" in clean
    assert strike(cell[: cell.index("~~")]) == (cell[: cell.index("~~")], False)  # the unstruck part
    row = tables(find_section(found, "Loss Scenarios").text)[0].rows[4]
    assert row[0] == "5" and [strike(c)[1] for c in row] == [False, True, True, True, True]
    assert strike(row[4]) == ("**CSTR1**", True)


def test_split_on_bold_on_the_first_context_cell(body: str) -> None:
    cell = tables(find_section(sections(body), "Context Table").text)[0].rows[0][2]
    clean, _ = strike(cell)
    pairs = split_on_bold(clean)
    assert [label for label, _ in pairs] == ["UCA1", "UCA2", "UCA3", "UCA7"]
    assert pairs[0] == ("UCA1", "When the vehicle enters another machine's radius. *\\[H1\\]*")
    assert pairs[1] == ("UCA2", "When its own radius is being broadcast. *\\[H1, H2, H2.1\\]*")
    assert pairs[2] == ("UCA3", "When the planner is guiding the vehicle into another machine. *\\[H1\\] (duplicate of")
    assert pairs[3] == ("UCA7", ")*")  # the reference inside the note is a bold run like any other
    assert bold_runs(cell) == ["UCA1", "UCA2", "~~UCA3 ~~", "UCA7"]  # strike first when the markers matter
    assert bold_runs(clean) == ["UCA1", "UCA2", "UCA3", "UCA7"]


def test_bold_runs_in_the_scenario_table(body: str) -> None:
    rows = tables(find_section(sections(body), "Loss Scenarios").text)[0].rows
    assert bold_runs(rows[1][4]) == ["CSTR1", "CSTR2", "CSTR3"]  # ``**CSTR1 **and **CSTR2 ****CSTR3 **text``
    assert split_on_bold(rows[1][4]) == [
        ("CSTR1", "and"),
        ("CSTR2", ""),
        ("CSTR3", "The motion controller must latch a Soft Stop until the stop is achieved."),
    ]
    assert split_on_bold(rows[3][4]) == [("CSTR1", "and"), ("CSTR3", "")]
    assert split_on_bold(rows[10][1]) == [("", "UCA8 The planner provides Operational Stop too late *\\[H1\\]*")]
    assert split_on_bold(rows[11][1]) == []


def test_page_record_sections_and_anchor_url() -> None:
    raw = json.loads((FIXTURES / "getConfluencePage_399343803_markdown.json").read_text(encoding="utf-8"))
    page = page_from_raw(raw, SITE)
    assert page is not None and [s.heading for s in page.sections()] == ["", *HEADINGS]
    assert page.anchor_url("Context Table") == f"{page.url}#Context-Table"
    assert page.anchor_url("") == page.url  # the preamble has no anchor
    assert (
        page.anchor_url("Losses and Hazards")
        == f"{SITE}/wiki/pages/viewpage.action?pageId=399343803#Losses-and-Hazards"
    )
    adf = json.loads((FIXTURES / "getConfluencePage_399343803_adf.json").read_text(encoding="utf-8"))
    assert page_from_raw(adf, SITE, body_format="adf").sections() == []
    html = json.loads((FIXTURES / "getConfluencePage_399343803_html.json").read_text(encoding="utf-8"))
    assert page_from_raw(html, SITE, body_format="html").sections() == []


# -- hand-written edge cases --------------------------------------------------------------------
def test_sections_edge_cases() -> None:
    assert sections("") == [] and sections("\n\n") == []
    assert sections("no headings here\n\njust text") == [Section(0, "", "", 0, 3, "no headings here\n\njust text")]
    assert sections("# Only\n") == [Section(1, "Only", "Only", 0, 1, "")]  # no blank preamble
    assert sections("a\r\n# H\r\nx\r\n") == sections("a\n# H\nx\n")  # CRLF reads like LF and hashes the same
    assert [s.sha256 for s in sections("a\r\n# H\r\nx\r\n")] == [s.sha256 for s in sections("a\n# H\nx\n")]
    fenced = sections("```\n# not a heading\n```\n# Real\ntext")
    assert [s.heading for s in fenced] == ["", "Real"] and fenced[0].text == "```\n# not a heading\n```"
    levels = sections("# One\n## Two ##\n###### Six\n####### Seven\n#NoSpace\n")
    assert [(s.level, s.heading) for s in levels] == [(1, "One"), (2, "Two"), (6, "Six")]
    assert levels[2].text == "####### Seven\n#NoSpace"
    assert sections("# A\n\n\ntext\n\n\n# B")[0].text == "text"  # blank lines around the text are dropped


def test_heading_anchor_rule() -> None:
    assert heading_anchor("Context Table") == "Context-Table"
    assert heading_anchor("Losses and Hazards") == "Losses-and-Hazards"
    assert heading_anchor("Step 2: Items (draft)") == "Step-2-Items-draft"
    assert heading_anchor("  keep_underscores  ") == "keep_underscores"
    assert heading_anchor("Two  spaces") == "Two--spaces" and heading_anchor("") == ""


def test_tables_edge_cases() -> None:
    assert tables("| a | b |\n|---|---|\n") == [Table(("a", "b"), (), 0, 2)]  # a header with no body rows
    assert tables("a | b\n--- | ---\n1 | 2 | 3\n| 4 |\n") == [Table(("a", "b"), (("1", "2 | 3"), ("4", "")), 0, 4)]
    assert tables("| a \\| b | c |\n|---|---|\n| x \\| y | z |\n") == [Table(("a | b", "c"), (("x | y", "z"),), 0, 3)]
    assert tables("| :--- | ---: |\n| --- | --- |\n") == []  # a separator is not a header
    assert tables("text\n\n---\n\nmore") == [] and tables("") == []
    two = tables("| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n| 3 |\n")
    assert [(t.header, len(t.rows), t.start, t.end) for t in two] == [(("a",), 1, 0, 3), (("b",), 2, 4, 8)]
    assert tables("| a | b |\n| :-: | --- |\n|  | 2 |\n")[0].rows == (("", "2"),)


def test_links_edge_cases() -> None:
    assert page_id_of("https://x.atlassian.net/wiki/pages/viewpage.action?pageId=399343803") == "399343803"
    assert page_id_of("https://x.atlassian.net/wiki/spaces/S/pages/123/Title") == "123"
    assert page_id_of("https://x.atlassian.net/wiki/spaces/S/pages/123") == "123"
    assert page_id_of("https://x.atlassian.net/wiki/spaces/S/pages/abc") is None
    assert page_id_of("https://x.atlassian.net/browse/HWL-1") is None and page_id_of("") is None
    text = 'see [a](http://a.invalid/ "title") and ![img](http://i.invalid/x.png) and [b](http://b.invalid)'
    assert links(text) == [PageLink("a", "http://a.invalid/"), PageLink("b", "http://b.invalid")]
    assert links("no links") == [] and links("") == []


def test_bold_and_strike_edge_cases() -> None:
    assert bold_runs("*italic **bold** more*") == ["bold"]  # nested bold inside italics
    assert split_on_bold("*italic **bold** more*") == [("", "*italic"), ("bold", "more*")]
    assert split_on_bold("**A **x**B **y") == [("A", "x"), ("B", "y")]  # glued close and open
    assert split_on_bold("*i***B **y") == [("", "*i*"), ("B", "y")]  # ``***`` is an italic close and a bold open
    assert split_on_bold("") == [] and split_on_bold("   ") == [] and bold_runs("") == []
    assert split_on_bold("plain") == [("", "plain")]
    assert strike("~~a~~ and ~~b~~") == ("a and b", True)
    assert strike("~~unmatched") == ("~~unmatched", False) and strike("") == ("", False)
