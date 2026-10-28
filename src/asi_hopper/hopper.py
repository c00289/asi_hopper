"""Hopper: wires configuration, gateway, services, and the dispatcher. The in-process API for siblings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .commands import Dispatcher, Result
from .config import Config, load_config
from .errors import ConfigError
from .gateway import JiraApi, JiraGateway, default_gateway_factory
from .gateway.auth import SessionStore
from .model import IssueRecord
from .services import EvidenceService, IssueService, MetaService
from .version import __version__


class Hopper:
    """One Jira door.

    ``Hopper()`` reads ``hopper.toml`` and opens the live gateway lazily (the first call connects, and
    logs in through the browser if there is no session yet). ``Hopper(gateway="replay",
    fixtures="tests/fixtures")`` never touches the network. ``interactive=False`` makes a missing
    session an error instead of a browser window, which is what a sibling tool wants.
    """

    def __init__(
        self,
        config_path: str | None = None,
        *,
        config: Config | None = None,
        gateway: str | JiraGateway | None = None,
        fixtures: str | None = None,
        record: str | None = None,
        site: str | None = None,
        interactive: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> None:
        overrides: dict[str, Any] = {"fixtures": fixtures, "record": record, "site": site}
        if isinstance(gateway, str):
            overrides["gateway"] = gateway
        if config is None:
            self.config = load_config(config_path, env=env, overrides=overrides)
        else:
            from .config import _apply_overrides

            self.config = _apply_overrides(config, overrides)
        if isinstance(gateway, str) or gateway is None:
            self.gateway = default_gateway_factory.create(self.config, interactive=interactive)
        else:
            if not hasattr(gateway, "call"):
                raise ConfigError("gateway must be a kind name or an object with call(tool, args)")
            self.gateway = gateway
        self.interactive = interactive
        self.api = JiraApi(self.gateway, self.config.cloud)
        self.issues = IssueService(self.api, self.config.site)
        self.meta = MetaService(self.api, self.config.site)
        self.evidence = EvidenceService(self.issues, self.config.site, _LazyAccount(self.meta))
        self.dispatcher = Dispatcher(self)

    # -- the command path -----------------------------------------------------------------
    def execute(self, verb: str, args: dict[str, Any] | None = None, *, actor: str = "python", **kwargs: Any) -> Result:
        """``hopper.execute("get", key="HWL-2572")`` or ``hopper.execute("get", {"key": "HWL-2572"})``."""
        merged = dict(args or {})
        merged.update(kwargs)
        return self.dispatcher.execute(verb, merged, actor)

    def execute_dict(self, payload: dict[str, Any], actor: str | None = None) -> Result:
        return self.dispatcher.execute_dict(payload, actor)

    # -- typed shortcuts for siblings -------------------------------------------------------
    def get(self, key: str, *, comments: bool = False) -> IssueRecord:
        return self.issues.get(key, comments=comments)

    def search(
        self,
        jql: str,
        *,
        fields: Sequence[str] | None = None,
        all_pages: bool = True,
        limit: int | None = None,
        page_size: int = 50,
    ) -> list[IssueRecord]:
        """Run JQL. ``fields`` defaults to ``DEFAULT_FIELDS``; list views pass ``LIST_FIELDS``.

        ``page_size`` is capped at 100 by Jira; 50 keeps a page of default fields under the
        transport's event size limit (``gateway.max_event_mb``).
        """
        return self.issues.search(jql, fields=fields, max_results=page_size, all_pages=all_pages, limit=limit)

    def whoami(self) -> dict[str, Any]:
        return self.meta.whoami()

    # -- housekeeping -----------------------------------------------------------------------
    def session_store(self) -> SessionStore:
        store = getattr(self.gateway, "store", None)
        return store if isinstance(store, SessionStore) else SessionStore(self.config.gateway.url)

    def status(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "app_version": __version__,
            "config": self.config.to_dict(),
            "gateway": {"name": self.gateway.name, "calls": getattr(self.gateway, "calls", None)},
            "commands": self.dispatcher.factory.verbs(),
        }
        if self.gateway.name == "mcp":
            info["session"] = self.session_store().describe()
        return info

    def close(self) -> None:
        self.gateway.close()

    def __enter__(self) -> Hopper:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Hopper(site={self.config.site!r}, gateway={self.gateway.name!r})"


class _LazyAccount(dict):
    """Looks like the account dict but only calls whoami when a snapshot actually needs it."""

    def __init__(self, meta: MetaService) -> None:
        super().__init__()
        self._meta = meta
        self._loaded = False

    def _load(self) -> None:
        if not self._loaded:
            self._loaded = True
            try:
                self.update(self._meta.whoami())
            except Exception:  # evidence without an account name is still evidence
                pass

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        self._load()
        return super().get(key, default)
