import csv
import hashlib
import json
from pathlib import Path

from asi_hopper import Hopper
from asi_hopper.model.pagetext import sections
from asi_hopper.services.evidence import PageSource

from .conftest import OPEN_JQL

PAGE = "399343803"  # Locator Safety Function STPA; children 5763236170 and 5779062840
REPO_BUNDLE = Path(__file__).resolve().parent.parent / "evidence" / "open-tickets-2026-10-27"


def test_snapshot_writes_a_verifiable_bundle(hopper: Hopper, tmp_path: Path) -> None:
    r = hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="open", title="Open tickets")
    assert r.ok, r.errors
    folder = tmp_path / "open"
    assert {p.name for p in folder.iterdir()} == {"issues.json", "issues.csv", "issues.md", "manifest.json"}
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "jira"
    assert manifest["count"] == 3 and manifest["keys"] == ["HWL-2572", "HWL-2575", "HWL-2620"]
    assert manifest["jql"] == OPEN_JQL and manifest["account"]["name"] == "Roy Mendoza - C"
    digest = hashlib.sha256((folder / "issues.json").read_bytes()).hexdigest()
    assert manifest["sha256"]["issues.json"] == digest
    with (folder / "issues.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[2]["labels"] == "VAT;e-stop;safety;test-failure" and rows[0]["parent"] == "HWL-1915"
    md = (folder / "issues.md").read_text(encoding="utf-8")
    assert md.startswith("# Open tickets") and "[HWL-2620](https://asirobots.atlassian.net/browse/HWL-2620)" in md
    assert hopper.execute("verify", snapshot=str(folder)).ok


def test_verify_detects_tampering(hopper: Hopper, tmp_path: Path) -> None:
    hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="a")
    issues = tmp_path / "a" / "issues.json"
    issues.write_text(issues.read_text(encoding="utf-8").replace("To Do", "Done"), encoding="utf-8")
    r = hopper.execute("verify", snapshot=str(tmp_path / "a"))
    assert not r.ok and r.data["intact"] is False
    assert r.errors == ["1 file(s) do not match the manifest: issues.json"]


def test_diff_between_snapshots_and_against_live(hopper: Hopper, tmp_path: Path) -> None:
    hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="a")
    hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="b")
    same = hopper.execute("diff", before=str(tmp_path / "a"), after=str(tmp_path / "b"))
    assert same.ok and same.data["kind"] == "jira" and same.data["same"] and same.data["changed"] == []
    data = json.loads((tmp_path / "b" / "issues.json").read_text(encoding="utf-8"))
    data[0]["status"] = "Done"
    data.pop()  # HWL-2620 removed
    data.append({"key": "HWL-9", "summary": "new"})
    (tmp_path / "b" / "issues.json").write_text(json.dumps(data), encoding="utf-8")
    changed = hopper.execute("diff", before=str(tmp_path / "a"), after=str(tmp_path / "b" / "issues.json"))
    assert changed.ok and not changed.data["same"]
    assert changed.data["added"] == ["HWL-9"] and changed.data["removed"] == ["HWL-2620"]
    assert {"key": "HWL-2572", "field": "status", "before": "In Progress", "after": "Done"} in changed.data["changed"]
    live = hopper.execute("diff", before=str(tmp_path / "a"))
    assert live.ok and live.data["same"] and live.data["after"].startswith("live:")
    missing = hopper.execute("diff", before=str(tmp_path / "nope"))
    assert not missing.ok


# -- Confluence bundles (0.1.8) ----------------------------------------------------------------
def _tree(hopper: Hopper, out: Path, name: str) -> Path:
    r = hopper.execute("confluence", action="snapshot", target=PAGE, depth=1, comments=True, out=str(out), name=name)
    assert r.ok, r.errors
    return out / name


def rows_header(folder: Path) -> list[str]:
    with (folder / "pages.csv").open(encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def test_page_entry_sections_are_empty_for_a_non_markdown_body(hopper: Hopper) -> None:
    record = hopper.confluence.page(PAGE, content_format="adf")
    entry, body = hopper.evidence._page_entry(record, False)
    assert entry["sections"] == [] and body.startswith("{")  # the ADF document, serialised


def test_confluence_snapshot_of_a_page_tree(hopper: Hopper, tmp_path: Path) -> None:
    folder = _tree(hopper, tmp_path, "tree")
    assert {p.name for p in folder.iterdir()} == {"pages.json", "pages", "pages.csv", "pages.md", "manifest.json"}
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "confluence" and manifest["tool"].startswith("asi_hopper ")
    assert manifest["source"] == {"kind": "tree", "root": PAGE, "depth": 1} and manifest["comments"] is True
    assert [p["id"] for p in manifest["pages"]] == [PAGE, "5763236170", "5779062840"] and manifest["count"] == 3
    assert manifest["account"]["name"] == "Roy Mendoza - C"
    # every body is on disk byte for byte, and its hash is in both the page entry and the file list
    for p in manifest["pages"]:
        body = (folder / "pages" / f"{p['id']}.md").read_bytes()
        assert hashlib.sha256(body).hexdigest() == p["body_sha256"] == manifest["sha256"][f"pages/{p['id']}.md"]
    assert (
        (folder / "pages" / "5763236170.md")
        .read_text(encoding="utf-8")
        .lstrip()
        .startswith("[Positioning reference A]")
    )
    entries = json.loads((folder / "pages.json").read_text(encoding="utf-8"))
    assert manifest["sha256"]["pages.json"] == hashlib.sha256((folder / "pages.json").read_bytes()).hexdigest()
    first = entries[0]
    assert "body" not in first and first["body_file"] == f"pages/{PAGE}.md" and first["version"] == 45
    assert [e["comment_count"] for e in entries] == [8, 2, 0]
    # since 0.1.9 every entry lists the sections of its Markdown body, hashed, so a citation can name one
    assert [s["heading"] for s in first["sections"]] == [
        "",
        "Losses and Hazards",
        "Control Structure",
        "Context Table",
        "Loss Scenarios",
    ]
    assert all(set(s) == {"heading", "anchor", "sha256", "chars"} for s in first["sections"])
    assert first["sections"][3]["anchor"] == "Context-Table"
    page_body = (folder / "pages" / f"{PAGE}.md").read_text(encoding="utf-8")
    assert [s["sha256"] for s in first["sections"]] == [s.sha256 for s in sections(page_body)]
    assert [len(e["sections"]) for e in entries] == [5, 2, 1]  # the last child has no heading: one section
    assert "sections" not in rows_header(folder) and "sections" not in (folder / "pages.md").read_text(encoding="utf-8")
    assert first["comments"][0]["kind"] == "inline" and first["comments"][0]["id"] == "5351964709"
    footer = entries[1]["comments"][1]
    assert footer["kind"] == "footer" and len(footer["replies"]) == 1  # one reply, fetched with the comment
    with (folder / "pages.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["id"] for r in rows] == [PAGE, "5763236170", "5779062840"] and rows[1]["parent_id"] == PAGE
    assert rows[0]["body_sha256"] == manifest["pages"][0]["body_sha256"] and rows[0]["comment_count"] == "8"
    md = (folder / "pages.md").read_text(encoding="utf-8")
    assert md.startswith("# Locator Safety Function STPA") and "descendants to depth 1" in md
    assert f"[{PAGE}](https://asirobots.atlassian.net/wiki/pages/viewpage.action?pageId={PAGE})" in md
    verified = hopper.execute("verify", snapshot=str(folder))
    assert verified.ok and verified.data["kind"] == "confluence" and len(verified.data["files"]) == 4


def test_confluence_snapshot_names_the_folder_after_the_root_page(hopper: Hopper, tmp_path: Path) -> None:
    r = hopper.execute("confluence", action="snapshot", target=PAGE, depth=1, out=str(tmp_path))
    assert r.ok, r.errors
    folder = Path(r.data["folder"])
    assert folder.parent == tmp_path and folder.name.startswith("locator-safety-function-stpa-20")
    assert r.data["comments"] is False
    entries = json.loads((folder / "pages.json").read_text(encoding="utf-8"))
    assert all(e["comments"] == [] and e["comment_count"] == 0 for e in entries)
    tools = [t for t, _ in hopper.gateway.calls]
    assert "getConfluencePageFooterComments" not in tools and "getConfluencePageInlineComments" not in tools


def test_confluence_snapshot_by_page_ids(hopper: Hopper, tmp_path: Path) -> None:
    r = hopper.execute(
        "confluence", action="snapshot", target="5763236170, 5779062840", out=str(tmp_path), name="two", title="Two"
    )
    assert r.ok, r.errors
    assert r.data["source"] == {"kind": "pages", "ids": ["5763236170", "5779062840"]} and r.data["count"] == 2
    assert (tmp_path / "two" / "pages.md").read_text(encoding="utf-8").startswith("# Two")
    assert hopper.gateway.calls[0][0] == "getConfluencePage"  # ids need no descendants call


def test_verify_detects_a_tampered_page_body(hopper: Hopper, tmp_path: Path) -> None:
    folder = _tree(hopper, tmp_path, "a")
    body = folder / "pages" / "5779062840.md"
    body.write_bytes(body.read_bytes() + b"\nedited after the fact\n")
    r = hopper.execute("verify", snapshot=str(folder))
    assert not r.ok and r.data["intact"] is False
    broken = [f["file"] for f in r.data["files"] if not f["intact"]]
    assert broken == ["pages/5779062840.md"] and "pages/5779062840.md" in r.errors[0]
    (folder / "pages" / "5763236170.md").unlink()
    r = hopper.execute("verify", snapshot=str(folder))
    missing = next(f for f in r.data["files"] if f["file"] == "pages/5763236170.md")
    assert not r.ok and missing["actual"] is None and missing["intact"] is False


def test_diff_between_page_bundles_and_against_live(hopper: Hopper, tmp_path: Path) -> None:
    _tree(hopper, tmp_path, "a")
    _tree(hopper, tmp_path, "b")
    same = hopper.execute("diff", before=str(tmp_path / "a"), after=str(tmp_path / "b"))
    assert same.ok and same.data["kind"] == "confluence" and same.data["same"] and same.data["changed"] == []
    data = json.loads((tmp_path / "b" / "pages.json").read_text(encoding="utf-8"))
    data[0]["version"] = 46
    data[0]["body_sha256"] = "0" * 64
    data.pop()  # 5779062840 removed
    data.append({"id": "9", "title": "new"})
    (tmp_path / "b" / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    changed = hopper.execute("diff", before=str(tmp_path / "a"), after=str(tmp_path / "b" / "pages.json"))
    assert changed.ok and not changed.data["same"]
    assert changed.data["added"] == ["9"] and changed.data["removed"] == ["5779062840"]
    fields = [(c["id"], c["field"]) for c in changed.data["changed"]]
    assert fields == [(PAGE, "version"), (PAGE, "body_sha256")]
    assert changed.data["changed"][0] == {
        "id": PAGE,
        "title": "Locator Safety Function STPA",
        "field": "version",
        "before": 45,
        "after": 46,
    }
    live = hopper.execute("diff", before=str(tmp_path / "a"))
    assert live.ok and live.data["same"] and live.data["after"] == f"live: page {PAGE} and descendants to depth 1"


def test_diff_refuses_to_mix_bundle_kinds(hopper: Hopper, tmp_path: Path) -> None:
    hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="jira")
    _tree(hopper, tmp_path, "pages")
    r = hopper.execute("diff", before=str(tmp_path / "jira"), after=str(tmp_path / "pages"))
    assert not r.ok and "cannot diff a jira bundle against a confluence bundle" in r.errors[0]
    r = hopper.execute("diff", before=str(tmp_path / "pages"), after=str(tmp_path / "jira"))
    assert not r.ok and "cannot diff a confluence bundle against a jira bundle" in r.errors[0]


def test_page_source_parsing(hopper: Hopper, tmp_path: Path) -> None:
    assert PageSource.parse("1,2") == PageSource("pages", ids=("1", "2"))
    assert PageSource.parse("1", depth=99) == PageSource("tree", root="1", depth=10)
    cql = PageSource.parse("title ~ 'STPA'", space="stpa")
    assert cql == PageSource("cql", cql="title ~ 'STPA'", space="STPA")
    assert cql.describe() == "CQL \"title ~ 'STPA'\" in space STPA"
    assert PageSource.from_dict(cql.to_dict()) == cql
    assert PageSource.from_dict(PageSource.parse("1", depth=2).to_dict()) == PageSource("tree", root="1", depth=2)
    r = hopper.execute("confluence", action="snapshot", target="1,2", depth=1, out=str(tmp_path))
    assert not r.ok and "--depth applies to one root page id" in r.errors[0]
    r = hopper.execute("confluence", action="snapshot", out=str(tmp_path))
    assert not r.ok and "a target is required" in r.errors[0]


def test_a_bundle_written_before_0_1_8_is_jira(hopper: Hopper) -> None:
    manifest = json.loads((REPO_BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert "kind" not in manifest
    r = hopper.execute("verify", snapshot=str(REPO_BUNDLE))
    assert r.ok and r.data["kind"] == "jira" and [f["file"] for f in r.data["files"]] == ["issues.json"]
    assert len(hopper.evidence.load(REPO_BUNDLE)) == manifest["count"]
