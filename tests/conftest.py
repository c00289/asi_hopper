"""Shared fixtures. No test reads the developer's hopper.toml, environment, or keyring, and none touches the network."""

from __future__ import annotations

from pathlib import Path

import pytest

from asi_hopper import Hopper
from asi_hopper.config import Config

FIXTURES = Path(__file__).parent / "fixtures"
OPEN_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY status ASC, updated DESC"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CONFIG", "SITE", "CLOUD_ID", "GATEWAY", "MCP_URL", "FIXTURES", "RECORD", "MODE"):
        monkeypatch.delenv(f"ASI_HOPPER_{name}", raising=False)


@pytest.fixture
def hopper() -> Hopper:
    with Hopper(config=Config(), gateway="replay", fixtures=str(FIXTURES), interactive=False) as h:
        yield h


@pytest.fixture
def empty_config(tmp_path: Path) -> Path:
    """An explicit, empty config file so CLI tests never pick up ./hopper.toml."""
    p = tmp_path / "hopper.toml"
    p.write_text("# empty\n", encoding="utf-8")
    return p
