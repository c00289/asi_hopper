from pathlib import Path

import pytest

from asi_hopper.config import DEFAULT_MCP_URL, DEFAULT_SITE, Config, load_config
from asi_hopper.errors import ConfigError


def test_defaults(tmp_path: Path) -> None:
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.site == DEFAULT_SITE
    assert cfg.cloud == "asirobots.atlassian.net"
    assert cfg.gateway.kind == "mcp"
    assert cfg.gateway.url == DEFAULT_MCP_URL
    assert cfg.policy.mode == "read"
    assert cfg.path is None


def test_toml_in_cwd_and_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "hopper.toml").write_text(
        "\n".join(
            [
                'site = "https://example.atlassian.net/"',
                'evidence_dir = "out"',
                "[gateway]",
                'kind = "replay"',
                'fixtures = "fx"',
                "callback_port = 60000",
                "[policy]",
                'mode = "read"',
                "[[projects]]",
                'key = "HWL"',
                "test = false",
                "[[projects]]",
                'key = "FSBX"',
                "test = true",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.site == "https://example.atlassian.net"
    assert cfg.gateway.kind == "replay"
    assert cfg.gateway.callback_port == 60000
    assert cfg.resolve(cfg.gateway.fixtures) == tmp_path / "fx"
    assert [p.key for p in cfg.policy.projects] == ["HWL", "FSBX"]
    assert cfg.policy.projects[1].test is True
    assert cfg.to_dict()["policy"]["projects"][0] == {"key": "HWL", "test": False}


def test_env_beats_file_and_overrides_beat_env(tmp_path: Path) -> None:
    (tmp_path / "hopper.toml").write_text('site = "https://file.atlassian.net"\n', encoding="utf-8")
    env = {"ASI_HOPPER_SITE": "https://env.atlassian.net", "ASI_HOPPER_GATEWAY": "replay", "ASI_HOPPER_FIXTURES": "x"}
    cfg = load_config(env=env, cwd=tmp_path)
    assert cfg.site == "https://env.atlassian.net"
    assert cfg.gateway.kind == "replay"
    cfg2 = load_config(env=env, cwd=tmp_path, overrides={"site": "https://arg.atlassian.net"})
    assert cfg2.site == "https://arg.atlassian.net"


def test_explicit_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.toml", env={})


def test_replay_needs_fixtures(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(env={"ASI_HOPPER_GATEWAY": "replay"}, cwd=tmp_path)


def test_bad_toml(tmp_path: Path) -> None:
    (tmp_path / "hopper.toml").write_text("site = \n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(env={}, cwd=tmp_path)


def test_config_is_frozen() -> None:
    cfg = Config()
    with pytest.raises(AttributeError):
        cfg.site = "x"  # type: ignore[misc]


def test_gateway_event_size_limit(tmp_path: Path) -> None:
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.gateway.max_event_mb == 16.0 and cfg.gateway.max_event_bytes == 16 * 1024 * 1024
    assert cfg.gateway.to_dict()["max_event_mb"] == 16.0
    (tmp_path / "hopper.toml").write_text("[gateway]\nmax_event_mb = 0\n", encoding="utf-8")
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.gateway.max_event_mb == 0 and cfg.gateway.max_event_bytes is None  # 0 = no limit
    (tmp_path / "hopper.toml").write_text("[gateway]\nmax_event_mb = 2.5\n", encoding="utf-8")
    assert load_config(env={}, cwd=tmp_path).gateway.max_event_bytes == int(2.5 * 1024 * 1024)


def test_mcp_gateway_carries_the_event_size_limit(tmp_path: Path) -> None:
    from asi_hopper.gateway.factory import _build_mcp
    from asi_hopper.gateway.mcp_gateway import McpGateway

    (tmp_path / "hopper.toml").write_text("[gateway]\nmax_event_mb = 4\n", encoding="utf-8")
    cfg = load_config(env={}, cwd=tmp_path)
    gateway = _build_mcp(cfg, {"interactive": False})
    assert isinstance(gateway, McpGateway) and gateway.max_event_bytes == 4 * 1024 * 1024
    assert McpGateway(DEFAULT_MCP_URL, interactive=False).max_event_bytes == 16 * 1024 * 1024
