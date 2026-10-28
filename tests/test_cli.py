import json
from pathlib import Path

import pytest

from asi_hopper.automation.cli import build_parser, main

from .conftest import FIXTURES, OPEN_JQL


def _run(capsys: pytest.CaptureFixture[str], empty_config: Path, *argv: str) -> tuple[int, dict]:
    code = main(["--config", str(empty_config), "--gateway", "replay", "--fixtures", str(FIXTURES), *argv])
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_get_prints_json_result(capsys: pytest.CaptureFixture[str], empty_config: Path) -> None:
    code, data = _run(capsys, empty_config, "get", "HWL-2575")
    assert code == 0 and data["ok"] and data["data"]["key"] == "HWL-2575"


def test_search_with_flags(capsys: pytest.CaptureFixture[str], empty_config: Path) -> None:
    code, data = _run(capsys, empty_config, "--compact", "search", OPEN_JQL, "--limit", "1")
    assert code == 0 and len(data["data"]) == 1


def test_failure_exit_code(capsys: pytest.CaptureFixture[str], empty_config: Path) -> None:
    code, data = _run(capsys, empty_config, "get", "HWL-1")
    assert code == 1 and not data["ok"]


def test_config_error_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--config", "does-not-exist.toml", "whoami"])
    assert code == 2
    data = json.loads(capsys.readouterr().out)
    assert not data["ok"] and "not found" in data["errors"][0]


def test_parser_has_every_verb() -> None:
    parser = build_parser()
    text = parser.format_help()
    for verb in ("whoami", "get", "search", "snapshot", "diff", "verify", "auth"):
        assert verb in text


def test_bool_flags_and_multiple(capsys: pytest.CaptureFixture[str], empty_config: Path) -> None:
    code, data = _run(capsys, empty_config, "get", "HWL-2575", "--comments", "--raw")
    assert code == 0 and "raw" in data["data"]
    code, data = _run(capsys, empty_config, "fields", "HWL", "Story")
    assert code == 0 and data["data"][0]["required"] is True
