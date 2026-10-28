"""GatewayFactory: kind -> gateway. A new kind is added by registration, not by editing this module."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import Config
from ..errors import ConfigError
from .base import JiraGateway
from .recording import RecordingGateway

Builder = Callable[[Config, dict[str, Any]], JiraGateway]


class GatewayFactory:
    def __init__(self) -> None:
        self._builders: dict[str, Builder] = {}

    def register(self, kind: str, builder: Builder) -> None:
        self._builders[kind] = builder

    def kinds(self) -> list[str]:
        return list(self._builders)

    def create(self, config: Config, **options: Any) -> JiraGateway:
        kind = config.gateway.kind
        try:
            builder = self._builders[kind]
        except KeyError:
            raise ConfigError(f"unknown gateway {kind!r}; known: {', '.join(self.kinds())}") from None
        gateway = builder(config, options)
        if config.gateway.record:
            gateway = RecordingGateway(gateway, config.resolve(config.gateway.record))
        return gateway


def _build_replay(config: Config, _: dict[str, Any]) -> JiraGateway:
    from .replay import ReplayGateway

    assert config.gateway.fixtures  # load_config guarantees it
    return ReplayGateway(config.resolve(config.gateway.fixtures))


def _build_mcp(config: Config, options: dict[str, Any]) -> JiraGateway:
    from .mcp_gateway import McpGateway

    gw = config.gateway
    return McpGateway(
        gw.url,
        interactive=bool(options.get("interactive", True)),
        timeout=gw.timeout_seconds,
        max_retries=gw.max_retries,
        requests_per_second=gw.requests_per_second,
        callback_port=gw.callback_port,
        client_name=gw.client_name,
        max_event_bytes=gw.max_event_bytes,
    )


default_gateway_factory = GatewayFactory()
default_gateway_factory.register("replay", _build_replay)
default_gateway_factory.register("mcp", _build_mcp)
