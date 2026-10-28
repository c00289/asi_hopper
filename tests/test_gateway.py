"""McpGateway heals itself: a rotated token means one reconnect, a stuck start is abandoned."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from asi_hopper.errors import AuthRequired, GatewayError
from asi_hopper.gateway.mcp_gateway import McpGateway

URL = "https://example.invalid/mcp"


class _Store:
    def __init__(self, session: bool) -> None:
        self.session = session

    def has_session(self) -> bool:
        return self.session


class _Loop:
    """Stands in for the serve loop: resolves each queued call with the next scripted outcome."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes

    def call_soon_threadsafe(self, _put, item) -> None:
        _tool, _args, future = item
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            future.set_exception(outcome)
        else:
            future.set_result(outcome)


def _gateway(monkeypatch, outcomes: list[object], *, session: bool = True) -> tuple[McpGateway, list[int]]:
    gw = McpGateway(URL, store=_Store(session), interactive=False, requests_per_second=0)  # type: ignore[arg-type]
    gw._loop = _Loop(outcomes)  # type: ignore[assignment]
    gw._queue = SimpleNamespace(put_nowait=lambda item: None)  # type: ignore[assignment]
    gw._thread = object()  # type: ignore[assignment]
    monkeypatch.setattr(gw, "_ensure_started", lambda: None)
    restarts: list[int] = []
    monkeypatch.setattr(gw, "_restart", lambda: restarts.append(1))
    return gw, restarts


def test_auth_failure_with_a_session_reconnects_once_and_retries(monkeypatch) -> None:
    gw, restarts = _gateway(monkeypatch, [AuthRequired("no Atlassian session"), {"issues": []}])
    assert gw.call("searchJiraIssuesUsingJql", {"jql": "x"}) == {"issues": []}
    assert restarts == [1] and gw.reconnects == 1 and gw.calls == 2


def test_auth_failure_twice_raises_after_the_one_reconnect(monkeypatch) -> None:
    gw, restarts = _gateway(monkeypatch, [AuthRequired("stale"), AuthRequired("still stale")])
    with pytest.raises(AuthRequired, match="still stale"):
        gw.call("getJiraIssue", {"issueIdOrKey": "HWL-1"})
    assert restarts == [1] and gw.reconnects == 1


def test_auth_failure_without_a_session_raises_at_once(monkeypatch) -> None:
    gw, restarts = _gateway(monkeypatch, [AuthRequired("no Atlassian session")], session=False)
    with pytest.raises(AuthRequired):
        gw.call("atlassianUserInfo", {})
    assert restarts == [] and gw.reconnects == 0


def test_a_failed_start_reports_the_leaf_of_the_exception_group(monkeypatch) -> None:
    """anyio wraps a failed start in "unhandled errors in a TaskGroup"; the caller hears the leaf."""
    import asi_hopper.gateway.mcp_gateway as module

    class _Thread:  # the serve thread never runs: the test plants the startup error itself
        def __init__(self, target=None, name="", daemon=False) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr(module.threading, "Thread", _Thread)
    gw = McpGateway(URL, store=_Store(True), interactive=False, timeout=0.01)  # type: ignore[arg-type]
    monkeypatch.setattr(gw._ready, "wait", lambda timeout=None: True)
    auth = AuthRequired("no Atlassian session for this account; run `asi-hopper auth login` once")
    group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [auth])
    gw._startup_error = McpGateway._translate(group)
    with pytest.raises(AuthRequired, match="no Atlassian session"):
        gw._ensure_started()
    assert gw._thread is None  # abandoned, so the next call tries again
    inner = BaseExceptionGroup("inner", [ConnectionError("[Errno 11001] getaddrinfo failed")])
    gw._startup_error = McpGateway._translate(BaseExceptionGroup("outer", [inner]))
    with pytest.raises(GatewayError, match=r"could not connect to .*ConnectionError: \[Errno 11001\]"):
        gw._ensure_started()
    # an AuthRequired leaf wins over whatever else failed around it
    mixed = BaseExceptionGroup("outer", [ConnectionError("x"), BaseExceptionGroup("inner", [auth])])
    assert isinstance(McpGateway._translate(mixed), AuthRequired)
    assert McpGateway._leaf(ValueError("plain")).args == ("plain",)


def test_a_start_that_times_out_is_abandoned_not_repeated(monkeypatch) -> None:
    import asi_hopper.gateway.mcp_gateway as module

    starts: list[str] = []

    class _Thread:
        def __init__(self, target=None, name="", daemon=False) -> None:
            self.name = name

        def start(self) -> None:
            starts.append(self.name)

    monkeypatch.setattr(module.threading, "Thread", _Thread)
    gw = McpGateway(URL, store=_Store(True), interactive=False, timeout=0.01)  # type: ignore[arg-type]
    monkeypatch.setattr(gw._ready, "wait", lambda timeout=None: False)
    with pytest.raises(GatewayError, match="timed out connecting"):
        gw._ensure_started()
    assert gw._thread is None  # abandoned, so the next call tries again
    with pytest.raises(GatewayError, match="timed out connecting"):
        gw._ensure_started()
    assert starts == ["asi-hopper-mcp", "asi-hopper-mcp"]


def test_a_timed_out_call_is_retried_once_then_reported(monkeypatch) -> None:
    import concurrent.futures

    gw = McpGateway(URL, store=_Store(True), interactive=False, timeout=30.0, requests_per_second=0)  # type: ignore[arg-type]
    gw._queue = SimpleNamespace(put_nowait=lambda item: None)  # type: ignore[assignment]
    gw._thread = object()  # type: ignore[assignment]
    monkeypatch.setattr(gw, "_ensure_started", lambda: None)
    waits: list[float] = []

    class _Loop:
        def call_soon_threadsafe(self, _put, item) -> None:
            _tool, _args, future = item
            real = future.result

            def result(timeout=None):
                waits.append(timeout)
                raise concurrent.futures.TimeoutError

            future.result = result  # type: ignore[method-assign]
            del real

    gw._loop = _Loop()  # type: ignore[assignment]
    with pytest.raises(GatewayError, match="within 60 s"):
        gw.call("getJiraIssue", {"issueIdOrKey": "HWL-1"})
    assert waits == [60.0, 60.0]  # one retry on a timed-out call, then the error
