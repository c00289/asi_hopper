"""McpGateway: a synchronous facade over an MCP client session to Atlassian's Remote MCP Server.

The MCP SDK is asyncio; Hopper's API is synchronous so siblings and the CLI stay simple. One
background thread runs an event loop with a single long-lived task that owns the session and
serves calls from a queue, which keeps every anyio cancel scope in the task that created it.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import threading
import time
from typing import Any

from ..errors import AuthRequired, GatewayError
from .auth import SessionStore, build_oauth_provider

log = logging.getLogger(__name__)

_TRANSIENT = ("429", "502", "503", "504", "timed out", "timeout", "connection", "reset", "temporarily")


class McpGateway:
    name = "mcp"

    def __init__(
        self,
        url: str,
        *,
        store: SessionStore | None = None,
        interactive: bool = True,
        timeout: float = 30.0,
        max_retries: int = 4,
        requests_per_second: float = 5.0,
        callback_port: int = 53680,
        client_name: str = "asi_hopper",
        max_event_bytes: int | None = 16 * 1024 * 1024,
    ) -> None:
        self.url = url
        self.max_event_bytes = max_event_bytes  # None: the transport accepts any event size
        self.store = store or SessionStore(url)
        self.interactive = interactive
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self.callback_port = callback_port
        self.client_name = client_name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._queue: asyncio.Queue | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._last_call = 0.0
        self._lock = threading.Lock()
        self.calls = 0
        self.reconnects = 0  # how many times call() rebuilt the client after an auth failure

    # -- lifecycle --------------------------------------------------------------------------
    def _ensure_started(self) -> None:
        if self._thread is not None:
            return
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run_thread, name="asi-hopper-mcp", daemon=True)
            self._thread.start()
        # the login can take minutes (a person is in the loop), so wait generously
        if not self._ready.wait(timeout=600 if self.interactive else self.timeout + 30):
            # abandon the stuck daemon thread: the next call must try a fresh connection, not wait
            # on this one forever (a long-lived window otherwise times out on every call)
            with self._lock:
                self._thread = None
                self._ready.clear()
            raise GatewayError("timed out connecting to the Atlassian MCP server")
        if self._startup_error is not None:
            err = self._startup_error
            self._thread = None
            self._startup_error = None
            self._ready.clear()
            if isinstance(err, AuthRequired):
                raise err
            raise GatewayError(f"could not connect to {self.url}: {err}") from err

    def _run_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        self._queue = asyncio.Queue()
        try:
            provider = build_oauth_provider(
                self.url,
                self.store,
                port=self.callback_port,
                interactive=self.interactive,
                client_name=self.client_name,
            )
            http = create_mcp_http_client(
                auth=provider, timeout=httpx2.Timeout(self.timeout, read=max(300.0, self.timeout))
            )
            async with http:
                transport = streamable_http_client(self.url, http_client=http, max_sse_event_size=self.max_event_bytes)
                async with Client(transport, read_timeout_seconds=max(60.0, self.timeout * 4)) as client:
                    self._ready.set()
                    while True:
                        item = await self._queue.get()
                        if item is None:
                            break
                        tool, args, future = item
                        try:
                            result = await client.call_tool(tool, args)
                            future.set_result(self._decode(result))
                        except BaseException as exc:  # hand every failure back to the caller
                            future.set_exception(self._translate(exc))
        except BaseException as exc:
            # anyio wraps a failed start in an ExceptionGroup ("unhandled errors in a TaskGroup"); the
            # caller must hear the leaf: "no Atlassian session ..." or the connection error itself
            self._startup_error = self._translate(exc)
            self._ready.set()

    @staticmethod
    def _leaf(exc: BaseException) -> BaseException:
        """The exception that matters inside an ``ExceptionGroup`` tree: an ``AuthRequired`` leaf if there is
        one (a sign-in is the fix, whatever else failed around it), else the first leaf; a plain exception
        is its own leaf."""
        if not isinstance(exc, BaseExceptionGroup):
            return exc
        leaves = [McpGateway._leaf(inner) for inner in exc.exceptions]
        for leaf in leaves:
            if "no Atlassian session" in str(leaf) or "AuthRequired" in type(leaf).__name__:
                return leaf
        return leaves[0] if leaves else exc

    @staticmethod
    def _translate(exc: BaseException) -> Exception:
        exc = McpGateway._leaf(exc)
        text = str(exc)
        if "No redirect handler" in text or "no Atlassian session" in text or "AuthRequired" in type(exc).__name__:
            return AuthRequired(text)
        if isinstance(exc, GatewayError):
            return exc
        return GatewayError(f"{type(exc).__name__}: {text}")

    @staticmethod
    def _decode(result: Any) -> Any:
        if getattr(result, "is_error", False):
            texts = [getattr(c, "text", "") for c in getattr(result, "content", []) or []]
            raise GatewayError("tool error: " + (" ".join(t for t in texts if t) or "unknown"))
        structured = getattr(result, "structured_content", None)
        if structured not in (None, {}):
            return structured
        texts = [getattr(c, "text", None) for c in getattr(result, "content", []) or []]
        text = "\n".join(t for t in texts if t)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    # -- calls ------------------------------------------------------------------------------
    def call(self, tool: str, args: dict[str, Any]) -> Any:
        self._ensure_started()
        assert self._loop is not None and self._queue is not None
        attempt = 0
        reconnected = False
        timed_out = 0
        while True:
            self._throttle()
            future: concurrent.futures.Future = concurrent.futures.Future()
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (tool, dict(args), future))
            try:
                self.calls += 1
                # one page of 50 issues answers in seconds; a minute means the server is gone, and a
                # caller (a window's worker thread, a CLI) should hear that, not wait five minutes
                return future.result(timeout=max(60.0, self.timeout * 2))
            except AuthRequired:
                # The MCP client loads the tokens once per process and refreshes from memory. When
                # another process (the other tool, a CLI call, a test) has rotated the refresh token
                # since, this process's refresh fails and the client asks for a full sign-in. If the
                # store still holds a session, a fresh client re-reads the rotated token: reconnect
                # once and retry before telling the caller to sign in again.
                if reconnected or not self.store.has_session():
                    raise
                reconnected = True
                self.reconnects += 1
                log.warning("%s: the Atlassian session needs a fresh client; reconnecting once", tool)
                self._restart()
                continue
            except GatewayError as exc:
                attempt += 1
                if attempt > self.max_retries or not any(h in str(exc).lower() for h in _TRANSIENT):
                    raise
                delay = min(30.0, 1.5 * 2 ** (attempt - 1))
                log.warning("%s failed (%s); retry %d/%d in %.1fs", tool, exc, attempt, self.max_retries, delay)
                time.sleep(delay)
            except concurrent.futures.TimeoutError:
                # the first answer after a quiet spell can be slow; one more try before giving up
                timed_out += 1
                if timed_out <= 1:
                    log.warning("%s: no answer within %.0f s; trying once more", tool, max(60.0, self.timeout * 2))
                    continue
                raise GatewayError(
                    f"{tool}: no answer from the Atlassian MCP server within {max(60.0, self.timeout * 2):.0f} s"
                ) from None

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        wait = self._last_call + self.min_interval - now
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _restart(self) -> None:
        """Stop the serve loop, forget the thread and connect again with a fresh client."""
        self.close()
        with self._lock:
            self._ready.clear()
            self._startup_error = None
            self._loop = None
            self._queue = None
        self._ensure_started()

    def close(self) -> None:
        if self._loop is None or self._queue is None or self._thread is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            self._thread.join(timeout=15)
        except RuntimeError:
            pass
        self._thread = None

    def __repr__(self) -> str:
        return f"McpGateway({self.url!r}, interactive={self.interactive})"
