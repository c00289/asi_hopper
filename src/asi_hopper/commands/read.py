"""The read verbs. Every one is allowed in every policy mode; none touches Jira state."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..errors import AuthRequired, GatewayError
from ..model.normalise import DEFAULT_FIELDS
from .base import Argument, Command, Context, Result
from .factory import register_command

_KEY = Argument("key", "issue key, e.g. HWL-2572", required=True)


@register_command
class WhoAmI(Command):
    verb = "whoami"
    help = "The signed-in account, the site, and the policy mode"

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        h = ctx.hopper
        return Result.success(
            {
                "account": h.meta.whoami(),
                "site": h.config.site,
                "cloud_id": h.config.cloud,
                "gateway": h.gateway.name,
                "policy_mode": h.config.policy.mode,
            }
        )


@register_command
class Projects(Command):
    verb = "projects"
    help = "Visible Jira projects with their issue types"
    arguments = (Argument("search", "filter by key or name", flag=True),)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        projects = ctx.hopper.meta.projects(args.get("search"))
        return Result.success(
            [
                {
                    "key": p.key,
                    "name": p.name,
                    "id": p.id,
                    "type": p.type,
                    "style": p.style,
                    "category": p.category,
                    "issue_types": [t.name for t in p.issue_types],
                }
                for p in projects
            ]
        )


@register_command
class Types(Command):
    verb = "types"
    help = "Issue types of one project"
    arguments = (Argument("project", "project key, e.g. HWL", required=True),)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success([asdict(t) for t in ctx.hopper.meta.issue_types(args["project"])])


@register_command
class Fields(Command):
    verb = "fields"
    help = "Create-meta for a project and issue type: required fields, allowed values, custom field ids"
    arguments = (
        Argument("project", "project key, e.g. HWL", required=True),
        Argument("type", "issue type name or id, e.g. Story", required=True),
        Argument("all", "include optional fields too", flag=True, type="bool", default=False),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        fields = ctx.hopper.meta.fields(args["project"], args["type"], required_only=not args.get("all"))
        return Result.success([asdict(f) | {"allowed_values": list(f.allowed_values)} for f in fields])


@register_command
class LinkTypes(Command):
    verb = "link-types"
    help = "Issue link types on the site (Blocks, Relates, ...)"

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success([asdict(t) for t in ctx.hopper.meta.link_types()])


@register_command
class Get(Command):
    verb = "get"
    help = "One issue as a normalised record"
    arguments = (
        _KEY,
        Argument("comments", "include comments", flag=True, type="bool", default=False),
        Argument("raw", "include the raw Jira payload", flag=True, type="bool", default=False),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        record = ctx.hopper.issues.get(args["key"], comments=bool(args.get("comments")))
        return Result.success(record.to_dict(include_raw=bool(args.get("raw"))))


@register_command
class Search(Command):
    verb = "search"
    help = "Issues matching a JQL query, as normalised records"
    arguments = (
        Argument("jql", 'JQL, e.g. "project = HWL AND assignee = currentUser()"', required=True),
        Argument("fields", "field ids to fetch (default: the standard set)", flag=True, multiple=True),
        Argument("max", "page size, 1-100", flag=True, type="int", default=50),
        Argument("all", "follow every page", flag=True, type="bool", default=False),
        Argument("limit", "stop after this many issues", flag=True, type="int"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        fields = args.get("fields") or None
        records = ctx.hopper.issues.search(
            args["jql"],
            fields=fields,
            max_results=int(args.get("max") or 50),
            all_pages=bool(args.get("all")),
            limit=args.get("limit"),
        )
        warnings = []
        if fields and "summary" not in fields:
            warnings.append("summary not requested; records show an empty summary")
        return Result.success([r.to_dict() for r in records], warnings)


@register_command
class Transitions(Command):
    verb = "transitions"
    help = "Transitions available on an issue from its current status"
    arguments = (_KEY,)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success([asdict(t) for t in ctx.hopper.issues.transitions(args["key"])])


@register_command
class Links(Command):
    verb = "links"
    help = "Issue links of an issue"
    arguments = (_KEY,)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success([asdict(link) for link in ctx.hopper.issues.links(args["key"])])


@register_command
class Comments(Command):
    verb = "comments"
    help = "Comments on an issue, as Markdown"
    arguments = (_KEY,)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success([asdict(c) for c in ctx.hopper.issues.comments(args["key"])])


@register_command
class Snapshot(Command):
    verb = "snapshot"
    help = "Evidence bundle for a JQL: issues.json, issues.csv, issues.md, manifest.json with SHA-256"
    arguments = (
        Argument("jql", "JQL to snapshot", required=True),
        Argument("out", "directory to write under (default: evidence_dir from config)", flag=True, type="path"),
        Argument("name", "folder name (default: <slug>-<date>)", flag=True),
        Argument("title", "title for the readable view", flag=True),
        Argument(
            "comments", "fetch comments for every issue (one extra call each)", flag=True, type="bool", default=False
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        out = ctx.hopper.config.resolve(args.get("out") or ctx.hopper.config.evidence_dir)
        manifest = ctx.hopper.evidence.snapshot(
            args["jql"], out, name=args.get("name"), comments=bool(args.get("comments")), title=args.get("title")
        )
        return Result.success(manifest)


@register_command
class Diff(Command):
    verb = "diff"
    help = "Compare two evidence bundles (Jira or Confluence), or one bundle against live"
    arguments = (
        Argument("before", "bundle folder (or its issues.json / pages.json)", required=True, type="path"),
        Argument("after", "second bundle of the same kind; omit to compare against live", type="path"),
        Argument("jql", "Jira bundles: JQL for the live side (default: the manifest's)", flag=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success(ctx.hopper.evidence.diff(args["before"], args.get("after"), jql=args.get("jql")))


@register_command
class Verify(Command):
    verb = "verify"
    help = "Recompute every SHA-256 an evidence bundle's manifest lists (Jira or Confluence)"
    arguments = (Argument("snapshot", "bundle folder", required=True, type="path"),)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        report = ctx.hopper.evidence.verify(args["snapshot"])
        broken = [f["file"] for f in report["files"] if not f["intact"]]
        errors = [f"{len(broken)} file(s) do not match the manifest: {', '.join(broken)}"] if broken else []
        if not report["files"]:
            errors = ["the manifest lists no files"]
        return Result(report["intact"], report, errors)


@register_command
class Schema(Command):
    verb = "schema"
    help = "Describe every verb and its arguments (or one verb)"
    arguments = (Argument("name", "a verb to describe"),)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        factory = ctx.hopper.dispatcher.factory
        if args.get("name"):
            return Result.success(factory.get(args["name"]).signature())
        return Result.success({"verbs": factory.signatures(), "default_fields": list(DEFAULT_FIELDS)})


@register_command
class Status(Command):
    verb = "status"
    help = "Configuration, gateway, session, and call counters"

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return Result.success(ctx.hopper.status())


@register_command
class Auth(Command):
    verb = "auth"
    help = "OAuth session with the Atlassian MCP server: login (opens a browser once), status, logout"
    arguments = (Argument("action", "login | status | logout", required=True, choices=("login", "status", "logout")),)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        store = ctx.hopper.session_store()
        action = args["action"]
        if action == "status":
            return self.status(ctx, store.describe())
        if action == "logout":
            store.clear()
            return Result.success({"logged_in": False, "server": store.server_url})
        if ctx.hopper.gateway.name != "mcp":
            return Result.failure(f"auth login needs the mcp gateway, not {ctx.hopper.gateway.name!r}")
        account = ctx.hopper.meta.whoami()  # forces the connection, and the browser flow if needed
        return Result.success({"logged_in": True, "account": account, **store.describe()})

    @staticmethod
    def status(ctx: Context, info: dict[str, Any]) -> Result:
        """``logged_in`` says a session is stored; ``session`` says whether Atlassian still honours it.

        The probe is one ``whoami`` with the gateway forced non-interactive, so a status check never
        opens a browser: ``valid`` (with the account), ``rejected`` (sign in again: the refresh token
        or the registered client was rotated away, as the window's "could not connect ... TaskGroup"
        of 2026-10-28 turned out to be) or ``unreachable`` (the network or the server).
        """
        gateway = ctx.hopper.gateway
        if not info.get("logged_in") or gateway.name != "mcp":
            info["session"] = "none" if not info.get("logged_in") else "not probed"
            return Result.success(info)
        previous = getattr(gateway, "interactive", None)
        if previous is not None:
            gateway.interactive = False
        try:
            info["account"] = ctx.hopper.meta.whoami()
            info["session"] = "valid"
            return Result.success(info)
        except AuthRequired as exc:
            info["session"] = "rejected"
            hint = f"{exc}; `asi-hopper auth logout` first clears the stale client registration"
            return Result.success(info, warnings=[hint])
        except GatewayError as exc:
            info["session"] = "unreachable"
            return Result.success(info, warnings=[str(exc)])
        finally:
            if previous is not None:
                gateway.interactive = previous
