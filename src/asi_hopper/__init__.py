"""ASI Hopper: a read-only, audited, replayable door into Jira Cloud.

Hopper is a library first and a CLI second. Everything a front end can do goes
through the same command path (see ``asi_hopper.commands``), so a human at a
shell, a sibling tool such as asi_dewey, or an AI agent all drive the same core
and get the same ``Result``.

Quick start::

    from asi_hopper import Hopper

    with Hopper() as hopper:                       # reads hopper.toml, logs in once
        result = hopper.execute("get", key="HWL-2572")
        print(result.ok, result.data["status"])

        for issue in hopper.search("project = HWL AND assignee = currentUser()"):
            print(issue.key, issue.summary, issue.status)

Tests and offline work use the replay gateway::

    with Hopper(gateway="replay", fixtures="tests/fixtures") as hopper:
        ...
"""

from .model.normalise import DEFAULT_FIELDS, LIST_FIELDS
from .version import RECORD_VERSION, __version__

__all__ = ["Hopper", "IssueRecord", "Result", "DEFAULT_FIELDS", "LIST_FIELDS", "RECORD_VERSION", "__version__"]


def __getattr__(name: str):
    # Lazy imports keep ``import asi_hopper`` cheap and avoid import cycles.
    if name == "Hopper":
        from .hopper import Hopper

        return Hopper
    if name == "IssueRecord":
        from .model import IssueRecord

        return IssueRecord
    if name == "Result":
        from .commands import Result

        return Result
    raise AttributeError(name)
