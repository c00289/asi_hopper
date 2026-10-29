# Changelog

All notable changes to ASI Hopper are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0 releases may break anything.

## [Unreleased]

### Planned
- 0.2.0: `run steps.jsonl`, `serve --mcp`, `serve --http`; dewey and kletz `jira sync` land in
  those repos; live read smoke tests behind `ASI_HOPPER_LIVE=1`.

## [0.1.6] - 2026-10-29

Broken-windows sweep. No change to the API, the verbs, or the fixtures.

### Fixed
- The README's version line still said 0.1.4 while the package was 0.1.5, and `uv.lock` still carried
  0.1.4; both say 0.1.6 now, and the README has a "What is in 0.1.6" note.
- The compare links at the foot of this file stopped at 0.1.2; 0.1.3 to 0.1.6 and `Unreleased` are
  listed.
- `.github/workflows/ci.yml` said the job runs on windows-latest "where Tk is available, so the GUI
  tests run too"; Hopper has no GUI. The comment now gives the real reason (the platform Hopper runs on).
- The README's Tests paragraph named six test files and missed `test_gateway.py` (added in 0.1.3).

### Checked, nothing to fix
- `ruff check`, `ruff format --check` and the 44 tests were green before the sweep; no test is
  skipped or marked flaky; no TODO or dead code in `src`; no token or secret in the tree
  (`hopper.toml` is git-ignored and holds none); `evidence/open-tickets-2026-10-27` verifies
  against its manifest; `.gitignore` covers `.venv`, caches, build output and the local config.

## [0.1.5] - 2026-10-28

The Kletz window said "Offline: Jira read failed: could not connect to https://mcp.atlassian.com/v1/mcp:
unhandled errors in a TaskGroup (1 sub-exception)" while `auth status` said logged in. The real cause,
one layer down, was "no Atlassian session for this account; run `asi-hopper auth login` once": the stored
session was no longer honoured and the MCP client had fallen back to a fresh sign-in, which a
non-interactive window refuses.

### Fixed
- **The leaf of an exception group is what the caller hears** (`McpGateway._leaf`, used by `_translate`
  and so by both a failed start and a failed call): anyio wraps a failed start in an `ExceptionGroup`,
  so the gateway reported "could not connect ... TaskGroup" and lost the message. An `AuthRequired`
  leaf wins over whatever else failed around it, so the window and the CLI now say to sign in.
- **`auth status` probes the session** (`Auth.status`): `logged_in` still says a session is stored;
  the new `session` field says whether Atlassian honours it: `valid` (with the account, one `whoami`
  with the gateway forced non-interactive, so a status check never opens a browser), `rejected` (a
  warning says to `auth logout` then `auth login`), `unreachable` (the gateway's message), `none`, or
  `not probed` on the replay gateway.

### Tests
- `test_a_failed_start_reports_the_leaf_of_the_exception_group`,
  `test_auth_status_probes_a_stored_session_without_a_browser`.

## [0.1.4] - 2026-10-28

### Changed
- A tool call waits at most `max(60, 2 x timeout_seconds)` seconds for the MCP server (it was ten times
  the timeout, five minutes by default): a page of fifty issues answers in seconds, and a caller should
  learn that the server is gone within a minute. The error now names the wait, and a call that times out
  is tried once more before it is reported (the first answer after a quiet spell can be slow).

## [0.1.3] - 2026-10-28

### Fixed
- A long-lived process (a tool's window) lost Jira after another process had refreshed the same
  session: the MCP client keeps its tokens in memory, so once a sibling process rotated the refresh
  token this process's next refresh failed and the client asked for a full sign-in, which a
  non-interactive gateway refuses. `McpGateway.call` now reconnects once with a fresh client (which
  re-reads the rotated token from the store) and retries before raising `AuthRequired`; the count is
  `gateway.reconnects`.
- A connection attempt that timed out left its thread registered, so every later call in that
  process timed out too ("timed out connecting to the Atlassian MCP server"). The stuck thread is
  abandoned and the next call connects afresh.

## [0.1.2] - 2026-10-28

Broken-windows sweep. No change to the API, the verbs, or the fixtures.

### Fixed
- The README's version line still said 0.1.0 while the package was 0.1.1; it now carries
  "What is in 0.1.1" and "What is in 0.1.2" notes above the 0.1.0 one.
- `hopper.example.toml` lacked `cloud_id`, `gateway.url`, `gateway.callback_port`,
  `gateway.client_name`, `gateway.fixtures` and `gateway.record`, all of which `config.py` reads;
  every key now has a one-line comment, the gateway comment no longer lists `dryrun` and `rest`
  kinds that do not exist, and the policy comments say the keys are parsed and reported only.
- Sandbox wording: the example's "requested from the Jira admin" comment, the proposal's "Action
  for the owner" in decision 2, its "maybe next week, maybe never" in section 14, and the last
  "parked" in this file and in the proposal's revision history now all say the write side is
  delayed indefinitely by owner decision (2026-10-27) and no sandbox will be requested.
- `ASI_HOPPER_CLOUD_ID` is read by `config.py` but was missing from the README's environment list.
- README "Layout" now lists `errors.py` and `version.py`; the Tests paragraph names the six test
  files; the functional-safety paragraph no longer says the write side comes "when it comes".
- `asi-hopper auth login` printed its sign-in prompt to stdout ahead of the JSON Result; the prompt
  goes to stderr so stdout stays one JSON document.
- `--actor` help, `PolicyViolation`'s docstring, the `GatewaySettings.kind` comment, and the
  `GatewayFactory` and `adf.convert` docstrings no longer promise the journal, a `dryrun` gateway
  or write verbs.
- `ruff format` on `gateway/mcp_gateway.py`: the `streamable_http_client` call from 0.1.1 was
  wrapped by hand.
- The `### Planned` block had slipped under the 0.1.1 entry when that entry was inserted; it is
  back under `[Unreleased]`, and the delayed-indefinitely decision is recorded under 0.1.1
  "Decided".
- Compare links at the foot of this file, in the form the siblings use.
- Proposal section 4 said asi_dewey's window "will get" a Jira screen; the JIRA Live Data
  windows shipped in asi_dewey 0.5.0 and asi_kletz 0.5.0.
- `.gitignore` no longer describes the journal and plan files as runtime data that exists.

## [0.1.1] - 2026-10-27

### Fixed
- A live search of a real project failed with `SSE stream failed: Server-sent event exceeded the
  1048576 byte limit`: a 100-issue page with descriptions rendered to Markdown is larger than one
  server-sent event the MCP transport accepted. The transport limit is now `gateway.max_event_mb`
  in `hopper.toml` (default 16, `0` for no limit), `Hopper.search` takes `page_size` (default 50,
  was a fixed 100), and `asi_hopper.LIST_FIELDS` names the default fields without `description`
  and `issuelinks` so a list view never pulls bodies it does not show.

### Decided
- Delayed indefinitely by owner decision (2026-10-27), not to be raised again: write verbs, policy
  enforcement with the per-project test lock, the SQLite journal, `plan` / `apply` / `undo`, the
  provenance footer. The design stays in `docs/proposal.md` as a record only.

## [0.1.0] - 2026-10-27

Read-only Jira, importable by the siblings.

### Added
- `Hopper`: configuration, gateway, services and dispatcher wired together; `execute`,
  `execute_dict` (asi_dewey wire format), `get`, `search`, `whoami`, context manager.
- Configuration (`hopper.toml`, `ASI_HOPPER_*`, explicit overrides): site, evidence dir,
  gateway settings, policy (mode, protected statuses, per-project `test` flag).
- Model: frozen `IssueRecord`, `IssueRef`, `Link`, `LinkType`, `Comment`, `Transition`,
  `FieldMeta`, `Project`, `User`, `Status`, `IssueType`; `to_dict`, `to_row`, `ROW_FIELDS`;
  normalisers for the Remote MCP Server and REST shapes.
- ADF <-> Markdown converter for the subset Jira descriptions use (headings, marks, lists, task
  lists, code, quotes, rules, tables, panels, mentions, media placeholders).
- Gateways: `McpGateway` (MCP Python SDK client to `mcp.atlassian.com` over OAuth 2.1 with
  dynamic client registration, PKCE, refresh; a background event loop with one long-lived
  session task; retry and rate limit), `ReplayGateway` (fixtures via `index.json`),
  `RecordingGateway` (`--record`), `GatewayFactory`, `JiraApi` (every tool call in one place).
- OAuth session store in Windows Credential Manager through `keyring` (chunked to fit the
  2560-character limit), with a file fallback when no keyring backend exists; local HTTP
  callback on `127.0.0.1:53680`; non-interactive mode raises `AuthRequired` for siblings.
- Services: `IssueService` (get, paged search, transitions, links, comments), `MetaService`
  (whoami, resources, projects, issue types, create-meta fields, link types),
  `EvidenceService` (snapshot bundles with SHA-256 manifest, verify, diff vs bundle or live).
- Verbs: `whoami`, `projects`, `types`, `fields`, `link-types`, `get`, `search`, `transitions`,
  `links`, `comments`, `snapshot`, `diff`, `verify`, `schema`, `status`, `auth`.
- CLI `asi-hopper` built from the command signatures; `--config`, `--gateway`, `--fixtures`,
  `--record`, `--site`, `--non-interactive`, `--actor`, `--compact`.
- Fixtures recorded from the live site on 2026-10-27 (account, resources, 33 projects, HWL
  issue types, Story create-meta, HWL-2575, the open-tickets search, transitions, link types).
- Test suite: config precedence, ADF round trip, normalisation, every verb, evidence bundles,
  CLI exit codes.

### Decided
- Personal API tokens are not permitted on the org: the production gateway is the Remote MCP
  Server over OAuth 2.1; there is no Basic auth. OAuth 2.0 (3LO) against REST stays a fallback.
- No sandbox exists and none is requested: Hopper is read-only, and the write design stays in
  the proposal as a record (delayed indefinitely by owner decision; see 0.1.1).
- Undo-of-create would go to Done / Won't Do with label `hopper-undone`; provenance footer on;
  dewey `jira_ticket` schema growth is a dewey change; Confluence out of scope.

## [0.0.0] - 2026-10-27

Design only.

### Added
- `docs/proposal.md`, `README.md`, `hopper.example.toml`, `.gitignore`, `.python-version`,
  and `evidence/open-tickets-2026-10-27/` (format preview pulled through the connector).

[Unreleased]: https://example.invalid/asi-hopper/compare/v0.1.6...HEAD
[0.1.6]: https://example.invalid/asi-hopper/compare/v0.1.5...v0.1.6
[0.1.5]: https://example.invalid/asi-hopper/compare/v0.1.4...v0.1.5
[0.1.4]: https://example.invalid/asi-hopper/compare/v0.1.3...v0.1.4
[0.1.3]: https://example.invalid/asi-hopper/compare/v0.1.2...v0.1.3
[0.1.2]: https://example.invalid/asi-hopper/compare/v0.1.1...v0.1.2
[0.1.1]: https://example.invalid/asi-hopper/compare/v0.1.0...v0.1.1
[0.1.0]: https://example.invalid/asi-hopper/compare/v0.0.0...v0.1.0
[0.0.0]: https://example.invalid/asi-hopper/releases/tag/v0.0.0
