"""Configuration: hopper.toml, environment, and explicit overrides, in that order of precedence (lowest first).

Nothing here holds a credential. The OAuth session lives in the keyring (see ``gateway.auth``).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import ConfigError

DEFAULT_SITE = "https://asirobots.atlassian.net"
DEFAULT_MCP_URL = "https://mcp.atlassian.com/v1/mcp"
DEFAULT_CALLBACK_PORT = 53680
CONFIG_FILENAME = "hopper.toml"
ENV_PREFIX = "ASI_HOPPER_"


@dataclass(frozen=True)
class ProjectPolicy:
    key: str
    test: bool = False


@dataclass(frozen=True)
class Policy:
    mode: str = "read"  # read | plan | write (only read exists in 0.1.x)
    protected_statuses: tuple[str, ...] = ("Done",)
    max_writes_per_apply: int = 50
    require_reason: bool = True
    footer: bool = True
    cancelled_status: str = "Done"
    cancelled_resolution: str = "Won't Do"
    production_writes_approved_by: str | None = None
    projects: tuple[ProjectPolicy, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "protected_statuses": list(self.protected_statuses),
            "max_writes_per_apply": self.max_writes_per_apply,
            "require_reason": self.require_reason,
            "footer": self.footer,
            "cancelled_status": self.cancelled_status,
            "cancelled_resolution": self.cancelled_resolution,
            "production_writes_approved_by": self.production_writes_approved_by,
            "projects": [{"key": p.key, "test": p.test} for p in self.projects],
        }


@dataclass(frozen=True)
class GatewaySettings:
    kind: str = "mcp"  # mcp | replay (the proposal's rest fallback is not built)
    url: str = DEFAULT_MCP_URL
    timeout_seconds: float = 30.0
    max_retries: int = 4
    requests_per_second: float = 5.0
    fixtures: str | None = None  # replay gateway: directory with index.json
    record: str | None = None  # wrap the gateway and record every call here
    callback_port: int = DEFAULT_CALLBACK_PORT
    client_name: str = "asi_hopper"
    max_event_mb: float = 16.0  # largest server-sent event the MCP transport accepts; 0 = no limit

    @property
    def max_event_bytes(self) -> int | None:
        return int(self.max_event_mb * 1024 * 1024) if self.max_event_mb > 0 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "url": self.url,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "requests_per_second": self.requests_per_second,
            "fixtures": self.fixtures,
            "record": self.record,
            "callback_port": self.callback_port,
            "max_event_mb": self.max_event_mb,
        }


@dataclass(frozen=True)
class Config:
    site: str = DEFAULT_SITE
    cloud_id: str | None = None  # None: the site host is used, which the MCP tools accept
    journal: str = "hopper.db"
    evidence_dir: str = "evidence"
    gateway: GatewaySettings = field(default_factory=GatewaySettings)
    policy: Policy = field(default_factory=Policy)
    path: str | None = None  # where this config was read from, for `status`

    @property
    def cloud(self) -> str:
        """What the MCP tools get as ``cloudId``: the explicit cloud id or the site host."""
        return self.cloud_id or urlparse(self.site).netloc or self.site

    @property
    def base_dir(self) -> Path:
        return Path(self.path).parent if self.path else Path.cwd()

    def resolve(self, relative: str | Path) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else (self.base_dir / p)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "cloud_id": self.cloud,
            "journal": self.journal,
            "evidence_dir": self.evidence_dir,
            "gateway": self.gateway.to_dict(),
            "policy": self.policy.to_dict(),
            "path": self.path,
        }


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _from_toml(data: Mapping[str, Any], path: Path) -> Config:
    gw = dict(data.get("gateway") or {})
    pol = dict(data.get("policy") or {})
    projects_raw = data.get("projects") or pol.get("projects") or []
    projects: list[ProjectPolicy] = []
    for entry in projects_raw:
        if isinstance(entry, str):
            projects.append(ProjectPolicy(entry))
        elif isinstance(entry, Mapping) and entry.get("key"):
            projects.append(ProjectPolicy(str(entry["key"]), _bool(entry.get("test", False))))
        else:
            raise ConfigError(f"{path}: each [[projects]] entry needs a key")
    policy = Policy(
        mode=str(pol.get("mode", "read")),
        protected_statuses=tuple(pol.get("protected_statuses", ("Done",))),
        max_writes_per_apply=int(pol.get("max_writes_per_apply", 50)),
        require_reason=_bool(pol.get("require_reason", True)),
        footer=_bool(pol.get("footer", True)),
        cancelled_status=str(pol.get("cancelled_status", "Done")),
        cancelled_resolution=str(pol.get("cancelled_resolution", "Won't Do")),
        production_writes_approved_by=pol.get("production_writes_approved_by"),
        projects=tuple(projects),
    )
    gateway = GatewaySettings(
        kind=str(gw.get("kind", "mcp")),
        url=str(gw.get("url", DEFAULT_MCP_URL)),
        timeout_seconds=float(gw.get("timeout_seconds", 30.0)),
        max_retries=int(gw.get("max_retries", 4)),
        requests_per_second=float(gw.get("requests_per_second", 5.0)),
        fixtures=gw.get("fixtures"),
        record=gw.get("record"),
        callback_port=int(gw.get("callback_port", DEFAULT_CALLBACK_PORT)),
        client_name=str(gw.get("client_name", "asi_hopper")),
        max_event_mb=float(gw.get("max_event_mb", 16.0)),
    )
    return Config(
        site=str(data.get("site", DEFAULT_SITE)).rstrip("/"),
        cloud_id=data.get("cloud_id"),
        journal=str(data.get("journal", "hopper.db")),
        evidence_dir=str(data.get("evidence_dir", "evidence")),
        gateway=gateway,
        policy=policy,
        path=str(path),
    )


def _apply_env(config: Config, env: Mapping[str, str]) -> Config:
    gw = config.gateway
    if env.get(ENV_PREFIX + "SITE"):
        config = replace(config, site=env[ENV_PREFIX + "SITE"].rstrip("/"))
    if env.get(ENV_PREFIX + "CLOUD_ID"):
        config = replace(config, cloud_id=env[ENV_PREFIX + "CLOUD_ID"])
    if env.get(ENV_PREFIX + "GATEWAY"):
        gw = replace(gw, kind=env[ENV_PREFIX + "GATEWAY"])
    if env.get(ENV_PREFIX + "MCP_URL"):
        gw = replace(gw, url=env[ENV_PREFIX + "MCP_URL"])
    if env.get(ENV_PREFIX + "FIXTURES"):
        gw = replace(gw, fixtures=env[ENV_PREFIX + "FIXTURES"])
    if env.get(ENV_PREFIX + "RECORD"):
        gw = replace(gw, record=env[ENV_PREFIX + "RECORD"])
    if env.get(ENV_PREFIX + "MODE"):
        config = replace(config, policy=replace(config.policy, mode=env[ENV_PREFIX + "MODE"]))
    return replace(config, gateway=gw)


def _apply_overrides(config: Config, overrides: Mapping[str, Any]) -> Config:
    gw = config.gateway
    for key, value in overrides.items():
        if value is None:
            continue
        if key in {"kind", "gateway"}:
            gw = replace(gw, kind=str(value))
        elif key in {"fixtures", "record", "url"}:
            gw = replace(gw, **{key: str(value)})
        elif key == "callback_port":
            gw = replace(gw, callback_port=int(value))
        elif key in {"site", "cloud_id", "journal", "evidence_dir"}:
            config = replace(config, **{key: str(value)})
        elif key == "mode":
            config = replace(config, policy=replace(config.policy, mode=str(value)))
        else:
            raise ConfigError(f"unknown configuration override {key!r}")
    return replace(config, gateway=gw)


def load_config(
    path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """Load configuration.

    Precedence, lowest first: built-in defaults, ``hopper.toml`` (explicit ``path``, else
    ``$ASI_HOPPER_CONFIG``, else ``./hopper.toml`` if it exists), ``ASI_HOPPER_*`` environment
    variables, then explicit ``overrides`` (what the CLI flags and ``Hopper(...)`` arguments pass).
    Pass ``env={}`` to ignore the process environment, which is what the tests do.
    """
    env = os.environ if env is None else env
    base = Path(cwd) if cwd else Path.cwd()
    file: Path | None = None
    if path:
        file = Path(path)
        if not file.is_file():
            raise ConfigError(f"configuration file not found: {file}")
    elif env.get(ENV_PREFIX + "CONFIG"):
        file = Path(env[ENV_PREFIX + "CONFIG"])
        if not file.is_file():
            raise ConfigError(f"$ASI_HOPPER_CONFIG points to a missing file: {file}")
    elif (base / CONFIG_FILENAME).is_file():
        file = base / CONFIG_FILENAME

    if file is not None:
        try:
            data = tomllib.loads(file.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{file}: {exc}") from None
        config = _from_toml(data, file.resolve())
    else:
        config = Config()
    config = _apply_env(config, env)
    if overrides:
        config = _apply_overrides(config, overrides)
    if config.gateway.kind == "replay" and not config.gateway.fixtures:
        raise ConfigError(
            "the replay gateway needs a fixtures directory (--fixtures, ASI_HOPPER_FIXTURES, or [gateway] fixtures)"
        )
    return config
