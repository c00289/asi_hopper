# Changelog

All notable changes to ASI Hopper are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0 releases may break anything.

## [Unreleased]

### Planned
- 0.2.0: `run steps.jsonl`, `serve --mcp`, `serve --http`; dewey and kletz `jira sync` land in
  those repos; live read smoke tests behind `ASI_HOPPER_LIVE=1`.

## [0.1.10] - 2026-10-29

Broken-windows sweep at the end of the day the Confluence side shipped (0.1.7 to 0.1.9, two sessions). No change
to the API, the verbs, or the fixtures' payloads.

### Fixed
- Dead code after the two Confluence sessions: `cql_total` (`model/confluence.py`), `unique_keys`
  (`model/normalise.py`) and `record_to_dict` (`services/evidence.py`) had no caller; the `toolName` file-name
  hint in `RecordingGateway` matched no tool argument. All four are removed. `model/confluence.py` imports the
  ADF converter at module level like `normalise.py` does, instead of inside `_comment`.
- `gateway/base.py` named `fetch`, `search` and `getContentFormatGuide` "so the inventory can classify them",
  but `classify_tool` spelt the one it used as a literal and never looked at the other two; it now uses the
  three constants (the verdicts are unchanged: `fetch` and `search` are `atlassian`, the guide `confluence`).
- `--gateway` offered a hard-coded `mcp | replay`; the choices now come from `default_gateway_factory.kinds()`,
  so a registered kind is accepted on the command line without editing the CLI.
- `tests/fixtures/index.json` listed the `getConfluenceSpaces` lookup of `STPA` with `limit 1` twice, both
  entries naming the same file (the replay gateway took the last); the entry that says where the payload came
  from is kept. Four notes still said the page bodies were "cut to" 160, 1200 or four nodes, which was true
  of the live recordings and not of the synthetic bodies 0.1.8 put in their place; they now say what is there.
- `.github/workflows/ci.yml` runs `ruff format --check` beside `ruff check`, which the sweeps had been running
  by hand; the README's Tests block shows both.
- The README had no list of the documents under `docs/` (`integration-plan.md` was linked from nowhere); a
  "Documents" section names the four, the Confluence integration plan among them.

### Checked, nothing to fix
- `ruff check`, `ruff format --check` and the 78 tests were green before the sweep; versions agree in
  `pyproject.toml`, `version.py`, the README, this file and `uv.lock`; the compare links reach 0.1.9; the
  README's `confluence` table matches `commands/confluence.py` action for action and flag for flag; proposal
  decision 6 and its dated notes still describe what shipped. Every fixture `index.json` names exists and
  every fixture file is named; `evidence/open-tickets-2026-10-27` and the local
  `evidence/locator-safety-function-stpa-2026-10-29` verify file by file; the Confluence fixtures carry only
  synthetic account ids and no `history.createdBy`; no token or secret in the tree; `.gitignore` covers
  `hopper.toml` and `.env`; `hopper.example.toml` carries every key `config.py` reads.

## [0.1.9] - 2026-10-29

The anatomy of a page: Phase C of `docs/confluence-integration-plan.md`. Generic helpers over the Markdown
the Remote MCP Server renders, so that a consumer can cite a part of a page without parsing Markdown itself.
No knowledge of what a page is about enters Hopper.

### Added
- `asi_hopper.model.pagetext`, standard library only, frozen dataclasses: `sections(markdown)` splits a body
  on its ATX headings into `Section(level, heading, anchor, start, end, text)` with a `sha256` over the text
  (the text before the first heading is a section of level 0; headings inside code fences are not headings);
  `find_section(sections, heading)` picks one, equal first and then containing, case-insensitively;
  `heading_anchor(heading)` is the cloud editor's anchor (`Context Table` gives `Context-Table`);
  `tables(text)` reads GitHub pipe tables into `Table(header, rows, start, end)` with stripped cells, `\|`
  unescaped, short rows padded and long rows folded into the last cell; `links(text)` gives
  `Link(label, url, page_id)` with the Confluence page id from `pageId=` or `/pages/<id>`; `strike(text)`,
  `bold_runs(text)` and `split_on_bold(text)` read a cell whose bold labels are glued to their text
  (`**A **one *[x]***B **two` gives `[("A", "one *[x]*"), ("B", "two")]`). Exported from `asi_hopper.model`
  (the link record as `PageLink`, since `Link` is the Jira issue link).
- `PageRecord.sections()` (empty for an ADF or HTML body) and `PageRecord.anchor_url(heading)`.
- `confluence page <id> --section "Context Table"` returns that one section (heading, anchor, anchor_url,
  level, text, sha256); a miss is an error that lists the headings present. `--sections` lists every section
  without its text (heading, anchor, anchor_url, level, chars, sha256). Both need the Markdown body.

### Changed
- Every `pages.json` entry of a Confluence bundle carries `sections: [{heading, anchor, sha256, chars}]`
  (an empty list for a non-Markdown body), so a citation can name a section hash as well as the body hash.
  `record_version` stays 1 (a new key), the compared fields of `diff` are unchanged, `pages.csv` and
  `pages.md` are unchanged; a bundle written by 0.1.8 still verifies and diffs.

### Tests
- `tests/test_pagetext.py` on the synthetic fixture page (its five sections with anchors and stable hashes,
  the two tables with their widths and row counts, the escaped pipe, the padded row, the three links with
  page ids, the struck cell, `split_on_bold` on the first context cell) and by hand (no headings, CRLF,
  code fences, closing hashes, a table without body rows, nested bold inside italics, the `***` boundary).
  `test_confluence.py` covers `--section` hit by equality and by containment, a miss, `--sections`, and the
  refusal on an ADF body; `test_evidence.py` checks the `sections` of every entry against the body files.

## [0.1.8] - 2026-10-29

Confluence evidence bundles. The owner confirmed that Confluence lives in Hopper, read only, and asked for
dated, hashed evidence of what a page said, the way `snapshot` gives it for Jira, before the asi_kletz
integration.

### Added
- `confluence snapshot <ids | id --depth N | cql> [--space KEY] [--comments] [--out DIR] [--name] [--title]`
  writes `pages.json` (records without bodies, with each page's comments when asked), one `pages/<id>.md`
  per page holding the Markdown body byte for byte, `pages.csv`, `pages.md` and `manifest.json` (kind,
  source, account, time, every page's version and body hash, SHA-256 of every file). The source is a list
  of page ids, one page and the tree below it to a depth, or a CQL (optionally in one space); the manifest
  keeps it so the bundle can be compared with live later.
- `EvidenceService.snapshot_pages(PageSource, out_dir, ...)` and `PageSource.parse(...)` for the siblings;
  `Hopper.evidence` now holds the Confluence service too.
- The first real bundle, `evidence/locator-safety-function-stpa-2026-10-29/`: page 399343803 and its two
  children with their comments, taken 2026-10-29 15:15 and verified. It stays on the owner's machine,
  git-ignored: the page text is ASI-internal and this repository is public (the charter's rule on controlled
  documents; `docs/confluence-integration-plan.md`, section 9).

### Changed
- `verify` recomputes every SHA-256 the manifest lists, not only `issues.json`, reports them one by one
  under `files`, and is `intact` only when all of them match; the error names the files that do not.
  A bundle written before 0.1.8 has no `kind` and is read as Jira, so `evidence/open-tickets-2026-10-27`
  still verifies.
- `diff` tells the two bundle kinds apart by the manifest's `kind` and refuses to compare one with the
  other. A page diff compares title, status, version, updated, parent, body hash and comment count;
  `diff <bundle>` alone re-reads the manifest's source from live Confluence.
- `manifest.json` carries `kind` (`jira` or `confluence`); the Jira manifest is otherwise unchanged.

### Fixed
- Bundle files that are hashed (`issues.json`, `pages.json`, the page bodies), the manifests and the
  readable views are written with LF on every platform; before, Python's text mode gave CRLF on Windows,
  so the same page hashed differently on Windows and elsewhere. The CSVs stay Excel's (CRLF rows) and
  are not hashed.
- `.gitattributes` marks `evidence/**` as `-text`, so a bundle of either kind keeps its bytes through git:
  with `core.autocrlf` on (the Windows default) git normalises a CRLF file to LF in the blob while the
  manifest hashes the bytes on disk, and a fresh clone fails `verify`. Checked by cloning with
  `autocrlf=true` and verifying the 2026-10-27 bundle from the clone.

### Fixtures and tests
- Recorded 2026-10-29 from the live site: the two child pages of 399343803 and the footer and inline
  comments of all three pages with replies, at the page size the snapshot uses (250). Every Confluence
  fixture's page body, comment text, inline selection, search excerpt and other people's account ids were
  then replaced by synthetic text of the same shape (ids, titles, versions, timestamps and structure kept):
  the pages are ASI-internal and this repository is public. The synthetic STPA page keeps the four sections,
  the context table with glued bold runs and a struck duplicate, and the loss-scenario table, so the readers
  of `docs/confluence-integration-plan.md` can be tested on it. `test_evidence.py` covers the page bundle, a tampered body file, the diff between two
  page bundles and against live, the kind guard, `PageSource.parse`, and the 2026-10-27 Jira bundle.

### Decided
- Proposal decision 6 is superseded by the owner: Confluence is in play, read only, inside Hopper; Rovo
  `search` stays out of the adapter; page evidence bundles come before the asi_kletz integration.

## [0.1.7] - 2026-10-29

Confluence, read only. The owner asked to "sandbox a test of what we can do with confluence just like we
did with jira ... what can we retrieve ... no writes at all for now but plan for them in the adapter".
Every Confluence read tool of the Remote MCP Server was exercised through Hopper's own client against the
live site with small, user-scoped queries; the findings are in `docs/confluence-sandbox-2026-10-29.md`.

### Added
- `confluence` verb (one verb, an action word, like `auth`): `spaces [KEYS]`, `pages SPACE`, `page ID
  [--format markdown|adf|html] [--raw]`, `children ID [--depth]`, `search [CQL] [--space KEY]`,
  `comments ID [--kind footer|inline|all] [--replies]`, `replies ID --kind`; `--limit`, `--all`, `--max` on
  the lists. No CQL runs `contributor = currentUser() AND type = page ORDER BY lastmodified DESC` and says
  so in `warnings`. Every answer is a `Result`, the Jira verbs' shape, for asi_kletz to consume later.
- `Hopper.page(id, content_format=)` and `Hopper.cql(cql, space=, ...)`; `Hopper.confluence`
  (`ConfluenceService`) and `Hopper.confluence_api` (`ConfluenceApi`).
- Records `Space`, `PageRef`, `PageRecord` (`to_dict`, `to_row`, `ROW_FIELDS`), `PageComment` and the
  normalisers in `model/confluence.py`; cursors are read from `_links.next`.
- `ConfluenceWriteSide`: the write contract, four documented signatures (`create_page`, `update_page`,
  `create_footer_comment`, `create_inline_comment`) and no implementation; `ClosedConfluenceWriteSide`
  raises the new `WriteSideClosed` (a `PolicyViolation`) on each before touching anything.
- `tools` verb: the server's tool inventory (32 tools) classified by product, whether the tool writes and
  whether Hopper uses it; `--schema` adds the input schemas. `McpGateway` serves it through the
  `LIST_TOOLS` pseudo tool so it records and replays like any call.
- `RecordingGateway` names Confluence recordings by page, space, comment, CQL or query.
- Fixtures recorded from the live site on 2026-10-29 (inventory, spaces, STPA pages, one page in three
  formats, children, two CQL searches, comments, replies); the page bodies, comment texts, selections,
  excerpts and other people's account ids are synthetic (see 0.1.8); `tests/test_confluence.py`.

### Decided
- Confluence reads live in Hopper; the proposal's decision 6 of 2026-10-27 ("out of scope, permanently")
  carries a dated note pending the owner's word. The Confluence write side is closed (2026-10-29) the way
  the Jira one is: no write, no test page, no comment, no sandbox.
- Not in the adapter: `search` (Rovo; spends credits per call and is not user-scoped), `fetch` (a subset
  of `getConfluencePage`), `getContentFormatGuide` (authoring guidance for the write tools).

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

[Unreleased]: https://example.invalid/asi-hopper/compare/v0.1.10...HEAD
[0.1.10]: https://example.invalid/asi-hopper/compare/v0.1.9...v0.1.10
[0.1.9]: https://example.invalid/asi-hopper/compare/v0.1.8...v0.1.9
[0.1.8]: https://example.invalid/asi-hopper/compare/v0.1.7...v0.1.8
[0.1.7]: https://example.invalid/asi-hopper/compare/v0.1.6...v0.1.7
[0.1.6]: https://example.invalid/asi-hopper/compare/v0.1.5...v0.1.6
[0.1.5]: https://example.invalid/asi-hopper/compare/v0.1.4...v0.1.5
[0.1.4]: https://example.invalid/asi-hopper/compare/v0.1.3...v0.1.4
[0.1.3]: https://example.invalid/asi-hopper/compare/v0.1.2...v0.1.3
[0.1.2]: https://example.invalid/asi-hopper/compare/v0.1.1...v0.1.2
[0.1.1]: https://example.invalid/asi-hopper/compare/v0.1.0...v0.1.1
[0.1.0]: https://example.invalid/asi-hopper/compare/v0.0.0...v0.1.0
[0.0.0]: https://example.invalid/asi-hopper/releases/tag/v0.0.0
