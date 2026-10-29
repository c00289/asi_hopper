# ASI Hopper

One of the [ASI FuSa tools](https://github.com/c00289/c00289/blob/main/README.md) by Roy Mendoza; the master README there lists every sibling.

A read-only, audited, replayable door into Jira, and since 0.1.7 into Confluence, for the Wheel Loader
programme: a Python library, a command line, and a fixture-replay gateway so that siblings and tests
never touch the network. Version **0.1.7**, alpha. Named after Grace Hopper, who built the first compiler
so people could instruct a machine in their own words.

The idea, in one sentence: Jira is the source of truth for the programme's work, Hopper is the
one way our tools and agents read it, and what it read on a given day can be proven.

> **Scope, decided 2026-10-27 (Jira) and 2026-10-29 (Confluence):** read only. There is no write verb,
> no API token (the org does not permit them), and no sandbox project. Hopper signs in to Atlassian's Remote MCP Server
> with OAuth 2.1 once, through the browser, and reads with your own account.
> See [docs/proposal.md](docs/proposal.md) for the design. The write side is delayed indefinitely by owner
> decision (2026-10-27): no sandbox will be requested and the question is closed.

## What is in 0.1.7

Confluence, read only, sandboxed on 2026-10-29 at the owner's request ("what can we retrieve ... no writes
at all for now but plan for them in the adapter"): one `confluence` verb with the actions `spaces`, `pages`,
`page`, `children`, `search`, `comments`, `replies`; `hopper.page()` and `hopper.cql()`; frozen `Space`,
`PageRef`, `PageRecord`, `PageComment` records; `ConfluenceApi` with every read call in one place and a
write contract (`ConfluenceWriteSide`) whose only implementation refuses every call with `WriteSideClosed`;
a `tools` verb that lists and classifies the server's 32 tools; fixtures recorded from the live site and
`tests/test_confluence.py`. The findings, tool by tool, are in
[docs/confluence-sandbox-2026-10-29.md](docs/confluence-sandbox-2026-10-29.md).

## What is in 0.1.6

Housekeeping from the 2026-10-29 broken-windows sweep, no change to the API or the verbs: the
version line here, `uv.lock` and the CHANGELOG's compare links had fallen behind the package;
the CI comment described a Tk GUI that Hopper does not have; the test list below names
`test_gateway.py`. The CHANGELOG lists every fix.

## What is in 0.1.5

A rejected session is named, not hidden: the gateway reports the leaf of anyio's exception group
("no Atlassian session for this account; run `asi-hopper auth login` once") instead of "unhandled
errors in a TaskGroup", and `auth status` probes the stored session with one browser-free `whoami`
and answers `session: valid | rejected | unreachable`, with a warning saying what to run when it is
rejected. 0.1.3 and 0.1.4 are in the CHANGELOG.

## What is in 0.1.2

Housekeeping from the 2026-10-28 broken-windows sweep, no change to the API or the verbs:
`hopper.example.toml` carries every key `config.py` reads with a comment each; README, CHANGELOG,
the example and the proposal say the same thing about the write side (delayed indefinitely by
owner decision, 2026-10-27, no sandbox requested); `ASI_HOPPER_CLOUD_ID` is documented; the
sign-in prompt of `auth login` goes to stderr so stdout stays one JSON `Result`. The CHANGELOG
lists every fix.

## What is in 0.1.1

The event-size fix: `gateway.max_event_mb` in `hopper.toml` (default 16 MiB, `0` for no limit)
sets the largest server-sent event the MCP transport accepts, `Hopper.search(page_size=)`
defaults to 50 (was a fixed 100), and `asi_hopper.LIST_FIELDS` names the default fields without
`description` and `issuelinks` so a list view never pulls bodies it does not show.

## What is in 0.1.0

- **One command path**: `whoami`, `projects`, `types`, `fields`, `link-types`, `get`, `search`,
  `transitions`, `links`, `comments`, `snapshot`, `diff`, `verify`, `schema`, `status`, `auth`.
  Every command returns a structured `Result` (`ok`, `verb`, `data`, `errors`, `warnings`) that
  serialises to JSON, byte-compatible with asi_dewey's so an agent learns one dialect.
- **Gateways behind a factory**: `mcp` (a Python MCP client to `mcp.atlassian.com`, OAuth 2.1
  with dynamic client registration, tokens in Windows Credential Manager, retry and rate limit)
  and `replay` (recorded fixtures; an unrecorded call raises, so no test can hit the network).
  Any gateway can be wrapped with `--record <dir>` to produce fixtures from live calls.
- **Normalised model**: frozen `IssueRecord`, `IssueRef`, `Link`, `Comment`, `Transition`,
  `FieldMeta`, `Project`; nothing outside the gateway sees raw Jira JSON. Descriptions and
  comments arrive as Markdown; an ADF converter handles the other direction and ADF payloads.
- **Evidence**: `snapshot "<jql>"` writes `issues.json`, `issues.csv`, `issues.md` and a
  `manifest.json` with the JQL, time, account and SHA-256; `verify` checks a bundle; `diff`
  compares two bundles or one bundle against live Jira.
- **Policy**: read mode, project allowlist and the per-project `test` flag are parsed and
  reported, and the dispatcher refuses any verb marked as writing while mode is `read`. No
  verb is marked as writing.
- **Tests** run against fixtures recorded from the live site on 2026-10-27 (`tests/fixtures`,
  each entry carries its source and date).

ASI Hopper is a sister of asi_dewey, asi_kletz, asi_gutenberg, and asi_escher. It shares no
code, data, configuration, or environment variable with any of them; siblings consume it as a
path dependency. Hopper never imports a sibling.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- `mcp` (the MCP Python SDK, client side) and `keyring`; both come with `uv sync`
- `pytest` and `ruff` for development
- Your own Atlassian account on `asirobots.atlassian.net`. No API token.

## Install

```powershell
cd asi_hopper
uv sync
```

That creates `.venv` with the package in editable mode and the `asi-hopper` command on
`.venv\Scripts`. OneDrive rejects hardlinks from the uv cache, so `pyproject.toml` pins
`tool.uv.link-mode = "copy"`.

From a sibling project:

```powershell
cd ..\asi_dewey
uv add --editable ..\asi_hopper
```

## Configuration

`asi-hopper` looks for `hopper.toml` in the working directory (or at `$ASI_HOPPER_CONFIG`, or
`--config`). Copy `hopper.example.toml` to start; the file is git-ignored.

```toml
site = "https://asirobots.atlassian.net"
evidence_dir = "evidence"

[gateway]
kind = "mcp"            # or "replay" with fixtures = "tests/fixtures"

[policy]
mode = "read"

[[projects]]
key = "HWL"
test = false
```

No credential lives in this file. Sign in once:

```powershell
asi-hopper auth login      # opens the Atlassian consent page; the session goes to Windows Credential Manager
asi-hopper auth status     # since 0.1.5: probes the session; "rejected" means logout, then login again
asi-hopper auth logout
```

Precedence is the explicit argument (`--site`, `--gateway`, `--fixtures`, `--record`), then the
environment (`ASI_HOPPER_SITE`, `ASI_HOPPER_CLOUD_ID`, `ASI_HOPPER_GATEWAY`, `ASI_HOPPER_MCP_URL`,
`ASI_HOPPER_FIXTURES`, `ASI_HOPPER_RECORD`, `ASI_HOPPER_MODE`, `ASI_HOPPER_CONFIG`), then
`hopper.toml`. Relative paths resolve against the config file.

## Quick start

```powershell
asi-hopper whoami
asi-hopper get HWL-2572 --comments
asi-hopper search "project = HWL AND assignee = currentUser() AND statusCategory != Done" --all
asi-hopper transitions HWL-2575
asi-hopper fields HWL Story --all
asi-hopper snapshot "project = HWL AND summary ~ 'STPA'" --title "STPA tickets"
asi-hopper verify evidence\stpa-tickets-2026-10-27
asi-hopper diff evidence\stpa-tickets-2026-10-27            # against live Jira
asi-hopper confluence spaces STPA,FST
asi-hopper confluence pages STPA --limit 10
asi-hopper confluence page 399343803 --format markdown
asi-hopper confluence search "title ~ 'STPA'" --space STPA
asi-hopper confluence comments 399343803 --kind inline
asi-hopper tools --product confluence
```

Offline, against the recorded fixtures (what the tests do):

```powershell
asi-hopper --gateway replay --fixtures tests\fixtures get HWL-2575
```

Record new fixtures from live calls:

```powershell
asi-hopper --record tests\fixtures transitions HWL-2554
```

## Python API

```python
from asi_hopper import Hopper

with Hopper(interactive=False) as hopper:        # a sibling: never opens a browser
    result = hopper.execute("get", key="HWL-2572")
    print(result.ok, result.data["status"], result.warnings)

    # typed records for a sibling's table (this is what asi_dewey's `jira sync` consumes)
    for issue in hopper.search("project = HWL AND assignee = currentUser()"):
        print(issue.key, issue.summary, issue.status, issue.status_category, issue.url)
        row = issue.to_row()            # flat scalars, the same columns as issues.csv

    # the wire format an agent sends; identical shape to asi_dewey
    hopper.execute_dict({"verb": "transitions", "args": {"key": "HWL-2575"}, "actor": "agent"})

    # Confluence, read only (0.1.7): refs for a table, one page with its body on demand
    for ref in hopper.cql("title ~ 'STPA'", space="STPA"):
        print(ref.id, ref.title, ref.url)
    page = hopper.page("399343803")                 # PageRecord: body as markdown, version, updated
    hopper.execute("confluence", action="comments", target="399343803")
```

`Hopper()` reads `hopper.toml`. `Hopper(gateway="replay", fixtures="tests/fixtures")` is fully
offline. If there is no OAuth session and `interactive=False`, the first call fails with
`AuthRequired` telling the user to run `asi-hopper auth login`.

## Confluence (read only)

`asi-hopper confluence <action> [target]` follows the `auth` verb's shape: one verb, an action word.

| Action | Target | Flags | Returns |
|---|---|---|---|
| `spaces` | space keys, comma-separated (optional) | `--limit` | `Space` records |
| `pages` | space key or id | `--limit --all --max` | `PageRef` records, newest change first |
| `page` | page id | `--format markdown/adf/html --raw` | one `PageRecord` with its body |
| `children` | page id | `--depth 1-10 --limit --all` | `PageRef` records |
| `search` | CQL (optional) | `--space KEY --limit --all --max` | `PageRef` records; no CQL runs the user-scoped default and says so in `warnings` |
| `comments` | page id | `--kind footer/inline/all --replies --limit` | `PageComment` records (open inline comments carry the text they hang on) |
| `replies` | comment id | `--kind footer/inline --limit` | `PageComment` records |

No action writes. The write side is a contract only: `ConfluenceWriteSide` in `gateway/api.py` names the
four methods a write adapter would have, and `ConfluenceApi.writes` (a `ClosedConfluenceWriteSide`) raises
`WriteSideClosed` on each before touching anything. `asi-hopper tools` lists what the server exposes and
which tools write; Hopper calls none of those. Recorded shapes, limits and errors are in
[docs/confluence-sandbox-2026-10-29.md](docs/confluence-sandbox-2026-10-29.md).

## Evidence

A snapshot folder holds `issues.json` (records), `issues.csv` (Excel, columns in
`IssueRecord.ROW_FIELDS`), `issues.md` (a readable table), and `manifest.json` (tool version,
site, account, time, JQL, keys, SHA-256 of `issues.json`). `verify` recomputes the hash.
`diff a b` lists added, removed, and changed keys and fields; `diff a` compares against live
Jira using the manifest's JQL. `evidence/open-tickets-2026-10-27/` is the first real bundle,
written by `snapshot` on 2026-10-27 after the first OAuth sign-in and verified against live Jira.

## Layout

```
src/asi_hopper/
  hopper.py           Hopper: wires everything, in-process API, hopper.toml loading
  config.py           Config, Policy, GatewaySettings, precedence
  errors.py           HopperError and its subclasses (ConfigError, AuthRequired, NotRecorded, ...)
  version.py          __version__ and RECORD_VERSION
  model/              records (frozen dataclasses) and normalise (raw payload -> record);
                      confluence (Space, PageRef, PageRecord, PageComment and their normalisers)
  adf/                ADF <-> Markdown
  gateway/            JiraGateway protocol, JiraApi and ConfluenceApi (every tool call in one place),
                      ConfluenceWriteSide (the closed write contract), McpGateway (OAuth, background
                      event loop, tool inventory), ReplayGateway, RecordingGateway,
                      auth (session store, browser callback), GatewayFactory
  services/           IssueService, MetaService, EvidenceService, ConfluenceService
  commands/           Result, Command, CommandFactory, Dispatcher, the read verbs, confluence and tools
  automation/         CLI (`python -m asi_hopper` runs the same main)
tests/                pytest; fixtures/ recorded from the live site with dates
```

## Tests

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests
```

Every test runs against `tests/fixtures` through `ReplayGateway`; `tests/conftest.py` clears the
`ASI_HOPPER_*` environment and builds the replay `Hopper`. The files: `test_config.py` (precedence,
`max_event_mb`), `test_adf.py` (ADF round trip), `test_model.py` (normalisation, `LIST_FIELDS`),
`test_commands.py` (every verb), `test_evidence.py` (bundles, verify, diff), `test_cli.py` (exit
codes), `test_gateway.py` (the MCP gateway's reconnect, timeout and exception-group handling,
with the serve loop stubbed), `test_confluence.py` (every Confluence action, the normalisers, the tool
inventory, and the write contract refusing). Tests never read the developer's `hopper.toml`, environment, or keyring. Live smoke tests
do not exist yet; run the CLI by hand after `auth login`.

## Functional-safety posture

Hopper is a tool in the safety lifecycle. It cannot change a safety record, in Jira or in Confluence:
there is no write verb. What it reads is normalised deterministically, tests run on recorded fixtures with their
provenance, and evidence bundles are content-hashed so a reviewer can prove what Jira said on a
given day. The write side is delayed indefinitely by owner decision (2026-10-27); its design
(plan/apply, journaling, undo, a per-project test lock) stays in the proposal as a record only.
