import csv
import hashlib
import json
from pathlib import Path

from asi_hopper import Hopper

from .conftest import OPEN_JQL


def test_snapshot_writes_a_verifiable_bundle(hopper: Hopper, tmp_path: Path) -> None:
    r = hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="open", title="Open tickets")
    assert r.ok, r.errors
    folder = tmp_path / "open"
    assert {p.name for p in folder.iterdir()} == {"issues.json", "issues.csv", "issues.md", "manifest.json"}
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
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


def test_diff_between_snapshots_and_against_live(hopper: Hopper, tmp_path: Path) -> None:
    hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="a")
    hopper.execute("snapshot", jql=OPEN_JQL, out=str(tmp_path), name="b")
    same = hopper.execute("diff", before=str(tmp_path / "a"), after=str(tmp_path / "b"))
    assert same.ok and same.data["same"] and same.data["changed"] == []
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
