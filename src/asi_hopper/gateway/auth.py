"""OAuth 2.1 session with Atlassian's Remote MCP Server: token storage and the browser callback.

There is no API token anywhere. ``asi-hopper auth login`` registers Hopper as an OAuth client with
``mcp.atlassian.com`` (dynamic client registration), opens the consent page in the browser, catches
the redirect on ``http://127.0.0.1:<port>/callback``, and keeps the resulting tokens in the Windows
Credential Manager through ``keyring``. The MCP SDK refreshes the access token on its own.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..errors import AuthRequired, GatewayError

log = logging.getLogger(__name__)

SERVICE = "asi_hopper"
_CHUNK = 1200  # Windows Credential Manager caps a secret at 2560 chars; JWTs are longer


# ----------------------------------------------------------------------------- storage


class _KeyringBackend:
    """Chunked string storage on top of keyring, with a JSON-file fallback when no backend works."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._file: Path | None = None
        try:
            import keyring
            from keyring.errors import NoKeyringError

            self._keyring = keyring
            try:
                keyring.get_password(SERVICE, f"{namespace}:probe")
            except NoKeyringError:
                self._keyring = None
        except Exception:  # keyring missing or broken: fall back to a file
            self._keyring = None
        if self._keyring is None:
            import os

            base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "asi_hopper"
            base.mkdir(parents=True, exist_ok=True)
            self._file = base / "auth.json"
            log.warning("no keyring backend available; storing the OAuth session in %s", self._file)

    def _read_file(self) -> dict[str, str]:
        if self._file and self._file.is_file():
            return json.loads(self._file.read_text(encoding="utf-8"))
        return {}

    def _write_file(self, data: dict[str, str]) -> None:
        assert self._file is not None
        self._file.write_text(json.dumps(data), encoding="utf-8")

    def get(self, key: str) -> str | None:
        name = f"{self.namespace}:{key}"
        if self._keyring is None:
            return self._read_file().get(name)
        count = self._keyring.get_password(SERVICE, f"{name}:n")
        if not count:
            return None
        parts = [self._keyring.get_password(SERVICE, f"{name}:{i}") or "" for i in range(int(count))]
        return "".join(parts)

    def set(self, key: str, value: str) -> None:
        name = f"{self.namespace}:{key}"
        if self._keyring is None:
            data = self._read_file()
            data[name] = value
            self._write_file(data)
            return
        self.delete(key)
        chunks = [value[i : i + _CHUNK] for i in range(0, len(value), _CHUNK)] or [""]
        for i, chunk in enumerate(chunks):
            self._keyring.set_password(SERVICE, f"{name}:{i}", chunk)
        self._keyring.set_password(SERVICE, f"{name}:n", str(len(chunks)))

    def delete(self, key: str) -> None:
        name = f"{self.namespace}:{key}"
        if self._keyring is None:
            data = self._read_file()
            data.pop(name, None)
            self._write_file(data)
            return
        count = self._keyring.get_password(SERVICE, f"{name}:n")
        if count:
            for i in range(int(count)):
                try:
                    self._keyring.delete_password(SERVICE, f"{name}:{i}")
                except Exception:
                    pass
            try:
                self._keyring.delete_password(SERVICE, f"{name}:n")
            except Exception:
                pass

    @property
    def where(self) -> str:
        return str(self._file) if self._file else "keyring (Windows Credential Manager)"


class SessionStore:
    """Implements the MCP SDK's ``TokenStorage`` protocol. One namespace per MCP server URL."""

    def __init__(self, server_url: str, backend: _KeyringBackend | None = None) -> None:
        self.server_url = server_url
        self.backend = backend or _KeyringBackend(urlparse(server_url).netloc or server_url)

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        raw = self.backend.get("tokens")
        return OAuthToken.model_validate_json(raw) if raw else None

    async def set_tokens(self, tokens) -> None:
        self.backend.set("tokens", tokens.model_dump_json(exclude_none=True))

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        raw = self.backend.get("client")
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def set_client_info(self, client_info) -> None:
        self.backend.set("client", client_info.model_dump_json(exclude_none=True))

    # -- sync helpers for the CLI --------------------------------------------------------
    def has_session(self) -> bool:
        return bool(self.backend.get("tokens"))

    def describe(self) -> dict[str, Any]:
        raw = self.backend.get("tokens")
        client = self.backend.get("client")
        info: dict[str, Any] = {"server": self.server_url, "stored_in": self.backend.where, "logged_in": bool(raw)}
        if raw:
            data = json.loads(raw)
            info["scope"] = data.get("scope")
            info["has_refresh_token"] = bool(data.get("refresh_token"))
        if client:
            info["client_id"] = json.loads(client).get("client_id")
        return info

    def clear(self) -> None:
        self.backend.delete("tokens")
        self.backend.delete("client")


# ----------------------------------------------------------------------------- browser callback


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, Any] = {}
    event: threading.Event | None = None

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        url = urlparse(self.path)
        if url.path.rstrip("/") != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        type(self).result = params
        body = (
            "<html><body style='font-family:sans-serif;padding:2em'>"
            + (
                "<h2>ASI Hopper is signed in.</h2><p>You can close this window.</p>"
                if "code" in params
                else f"<h2>Sign-in failed</h2><pre>{params}</pre>"
            )
            + "</body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if type(self).event:
            type(self).event.set()

    def log_message(self, *_: Any) -> None:  # keep the console quiet
        return None


class BrowserLogin:
    """Redirect and callback handlers for ``OAuthClientProvider`` using a tiny local HTTP server."""

    def __init__(self, port: int, *, timeout: float = 300.0, opener: Callable[[str], Any] | None = None) -> None:
        self.port = port
        self.timeout = timeout
        self.opener = opener or webbrowser.open
        self.redirect_uri = f"http://127.0.0.1:{port}/callback"
        self.last_url: str | None = None

    async def redirect(self, url: str) -> None:
        self.last_url = url
        # stderr: the CLI's stdout carries exactly one JSON Result
        print(
            f"Opening the Atlassian sign-in page. If the browser does not open, visit:\n{url}",
            file=sys.stderr,
            flush=True,
        )
        try:
            self.opener(url)
        except Exception as exc:  # pragma: no cover - browser launch is best effort
            log.warning("could not open a browser: %s", exc)

    async def callback(self):
        from mcp.shared.auth import AuthorizationCodeResult

        handler = type("Handler", (_CallbackHandler,), {"result": {}, "event": threading.Event()})
        try:
            server = HTTPServer(("127.0.0.1", self.port), handler)
        except OSError as exc:
            raise GatewayError(
                f"cannot listen on 127.0.0.1:{self.port} for the OAuth callback ({exc}); "
                "set [gateway] callback_port in hopper.toml to a free port"
            ) from None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            loop = asyncio.get_running_loop()
            ok = await loop.run_in_executor(None, handler.event.wait, self.timeout)
        finally:
            server.shutdown()
            server.server_close()
        if not ok:
            raise GatewayError(f"no OAuth callback received within {int(self.timeout)} s")
        params = handler.result
        if "error" in params:
            raise GatewayError(f"authorization refused: {params.get('error')} {params.get('error_description', '')}")
        return AuthorizationCodeResult(code=params.get("code", ""), state=params.get("state"), iss=params.get("iss"))


class NonInteractiveLogin:
    """Used by library callers: never opens a browser, tells the user what to run instead."""

    def __init__(self, port: int) -> None:
        self.redirect_uri = f"http://127.0.0.1:{port}/callback"

    async def redirect(self, url: str) -> None:
        raise AuthRequired("no Atlassian session for this account; run `asi-hopper auth login` once")

    async def callback(self):
        raise AuthRequired("no Atlassian session for this account; run `asi-hopper auth login` once")


def build_oauth_provider(server_url: str, store: SessionStore, *, port: int, interactive: bool, client_name: str):
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    login: BrowserLogin | NonInteractiveLogin = BrowserLogin(port) if interactive else NonInteractiveLogin(port)
    metadata = OAuthClientMetadata(
        client_name=client_name,
        redirect_uris=[login.redirect_uri],  # type: ignore[list-item]
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=metadata,
        storage=store,
        redirect_handler=login.redirect,
        callback_handler=login.callback,
    )
