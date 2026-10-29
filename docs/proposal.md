# ASI Hopper — Proposal

**Status:** Proposal 0.3. Approved with constraints on 2026-10-27 (section 13); the read side shipped the same day as 0.1.0 (see `README.md` and `CHANGELOG.md`). **The write side is delayed indefinitely** (owner decision, 2026-10-27): no sandbox project will be requested, and the question is not to be raised again. Sections 5.4 to 5.6 and phase 2 stay in this document as a record of the design only.
**Date:** 2026-10-27
**Owner:** Roy Mendoza (Functional Safety Engineer, Engineering | Safety)
**Programme:** Wheel Loader (Haulage), Jira project `HWL`, site `asirobots.atlassian.net`
**Siblings:** asi_dewey (working knowledge), asi_kletz (safety plan), asi_gutenberg (documents), asi_escher (diagrams)

---

## 1. The idea in one sentence

Jira is where the programme's work is tracked; ASI Hopper is the one audited, replayable,
reversible command path to it, so a human at a keyboard, an AI agent, and asi_dewey all drive
Jira through the same verbs, and nothing is written without a plan, a reason, and a journal entry.

Named after Grace Hopper, who built the first compiler so that people could instruct a machine
in their own words. A hopper is also the bin that feeds material into a machine in measured
doses, which is exactly the posture this tool takes towards Jira: controlled, metered, logged.

## 2. Why this tool, and why now

The FuSa work on the wheel loader lives in Jira as stories, tasks, and bugs (today: the STPA
step triplets `HWL-2572..2575`, the Platform Safety Plan story `HWL-2554`, the Platform
Activity Flow story `HWL-2553`, the control-room E-stop guard bug `HWL-2620`, and the L0 test
dependency task `HWL-2652`). asi_dewey already models `jira_ticket` as an entity, but today
that entity is typed in by hand from the workbook and goes stale the moment Jira moves.

Three things are needed, and none of them exist yet:

1. **A Python door into Jira** that asi_dewey (and later asi_kletz) can call, so that the
   ticket list in the working-knowledge store is pulled from Jira instead of typed.
2. **Puppeting with rails.** The Atlassian connector in Claude is "hot" and is a fine pair of
   hands for ad-hoc work in a chat. It is not a foundation for safety-lifecycle automation:
   it leaves no audit trail in our hands, has no dry run, no undo, no project allowlist, is
   not reproducible (a conversation is not a script), and cannot be called from Python.
3. **Evidence.** Confirmation reviews and the safety case need snapshots of what Jira said on
   a given date, content-hashed, exportable, and feedable to asi_gutenberg.

ASI Hopper provides all three with one code base and one command vocabulary.

### 2.1 How the hot connector still earns its keep

The connector is used *during the build* and *alongside* Hopper, never *inside* it:

- Record real responses now (`/myself`, project list, issue search, create-meta, transitions)
  to seed the replay fixtures that the test suite runs against, so tests never touch live Jira.
- Verify field ids, custom fields, and JQL against the real `HWL` project before coding.
- Once `asi-hopper serve` exists, an agent in Claude Code puppets **Hopper** (with rails)
  rather than raw Jira. The raw connector stays available for throwaway questions.

## 3. Design principles (the same ones as the siblings)

- **One command path.** CLI, Python API, MCP server, and asi_dewey all build the same
  `Command` objects and get the same `Result` (`ok`, `verb`, `data`, `errors`, `warnings`).
  The wire format is byte-compatible with asi_dewey's so an agent learns one dialect.
- **Read by default, and write-locked until there is somewhere safe to write.** Hopper starts
  in `read` mode. Writes need `mode = "write"` in the config or `--write` on the command line,
  and only ever touch allowlisted projects. On top of that, a project must be marked
  `test = true` in the config before Hopper will write to it at all, and writing to a
  non-test project needs a dated `production_writes_approved_by` line. Today no test
  project exists, so no write verb can run anywhere.
- **Plan, then apply.** Any set of writes can be compiled into a reviewable `plan.json`
  without touching Jira, then applied as a unit with a journal entry per step. A plan file is
  the FuSa "review before commit" and doubles as evidence.
- **Nothing is deleted. Ever.** There is no `delete` verb. Jira deletions are unrecoverable and
  a safety record must stay. Undo of a create is a transition to a cancelled state plus a
  label, never a delete; undo of a comment is a retraction comment.
- **Every write is journaled with before and after.** Hopper fetches the current values
  before it writes and stores actor, timestamp, reason, request, response, and prior state in
  a local SQLite journal. `undo <journal-id>` reverses what can be reversed.
- **Deterministic and replayable.** Scripts are `.jsonl`, steps carry idempotency ids, a replay
  of a finished script is a no-op, and the test suite runs against recorded fixtures.
- **Factories and registries.** Gateways, commands, exporters, and policy rules are registered,
  not hard-wired, so the Confluence door or an OAuth gateway is an addition, not a rewrite.
- **No shared code with the siblings.** Like gutenberg and escher, Hopper is a library a
  sibling adds with `uv add --editable ../asi_hopper`. Hopper never imports asi_dewey.

## 4. What Hopper is, and is not

| Hopper is | Hopper is not |
|---|---|
| A Jira Cloud client with a FuSa posture (rails, journal, evidence) | A Jira replacement or a mirror with its own truth |
| A command vocabulary callable from CLI, Python, scripts, and an agent | A GUI (Jira already has one; the JIRA Live Data windows of asi_dewey and asi_kletz are fed by Hopper) |
| The Jira door for asi_dewey and asi_kletz | A Confluence tool (possible later through the same gateway pattern, out of scope for v1) |
| Single-user, runs as the engineer's own Atlassian account | A shared service account or a server |

## 5. Architecture

```
+-------------------------------------------------------------------------+
|  Front ends                                                             |
|   CLI (asi-hopper)   Python API (Hopper)   MCP server   asi_dewey        |
+-------------------------------------------------------------------------+
|  Command layer: CommandFactory -> Command.run(ctx, args) -> Result      |
|   read verbs | write verbs | plan / apply / undo | run | serve | status  |
+-------------------------------------------------------------------------+
|  Policy: mode, project allowlist, protected statuses, write budget      |
|  Journal: audit, before/after, undo, idempotency (SQLite, hopper.db)    |
+-------------------------------------------------------------------------+
|  Services: issues, search, transitions, links, comments, evidence       |
+-------------------------------------------------------------------------+
|  Model: IssueRecord, Transition, Link, Comment, FieldMeta (frozen)       |
|  ADF: Markdown <-> Atlassian Document Format                            |
+-------------------------------------------------------------------------+
|  Gateway protocol: JiraGateway                                          |
|   RestGateway (httpx, API v3) | ReplayGateway (fixtures) | DryRunGateway |
+-------------------------------------------------------------------------+
|  Jira Cloud REST API v3 at https://asirobots.atlassian.net              |
+-------------------------------------------------------------------------+
```

### 5.1 Gateway layer

`JiraGateway` is a small protocol: `get_issue`, `search`, `create_issue`, `edit_issue`,
`transitions`, `transition`, `comment`, `link`, `fields_for`, `myself`, `projects`. Three
implementations:

| Gateway | Use |
|---|---|
| `McpGateway` | Production, phase 0 choice. A Python MCP client to Atlassian's hosted Remote MCP Server (`mcp.atlassian.com`), authenticated by OAuth 2.1 browser login, the same door the Claude connector already uses for this account. No API token involved. Retry with backoff, rate limited, every call logged. |
| `RestGateway` | Production alternative. `httpx` against Jira Cloud REST API v3 with an OAuth 2.0 (3LO) bearer token from an app registered at developer.atlassian.com. Only if the Remote MCP tool surface proves too narrow. |
| `ReplayGateway` | Tests and offline work. Serves JSON recorded from the real site; raises on an unrecorded call so a test can never silently hit the network. |
| `DryRunGateway` | `plan` mode. Reads pass through to the real gateway, writes are recorded as intended calls and returned as a diff. |

A `GatewayFactory` picks one by name (`mcp`, `rest`, `replay`, `dryrun`). Personal API tokens
are not permitted on this org, so Basic auth is not an option and is not implemented. The
Remote MCP Server's Jira tool surface, as seen from this account today, covers get, search
(JQL), create, edit, transition, comment, worklog, issue links, remote links, create-meta,
user lookup, and the Teamwork Graph; watchers, changelog, and attachments are the known
gaps and are where the `rest` gateway would be needed.

### 5.2 Model

Normalised, frozen dataclasses so the rest of the code never sees raw Jira JSON:

- `IssueRecord`: key, id, project, issue_type, summary, status, status_category, priority,
  assignee, reporter, labels, components, created, updated, resolution, url, description
  (Markdown), custom fields by name, and a `raw` escape hatch.
- `Transition`, `Link`, `Comment`, `Worklog`, `FieldMeta` (required, allowed values, schema).
- `Changeset`: the diff between an `IssueRecord` and intended field values; what `plan` prints.

### 5.3 ADF

Descriptions and comments are Atlassian Document Format. Hopper authors **Markdown** and
converts a supported subset both ways: headings, paragraphs, bold, italic, code, links, bullet
and numbered lists, tables, block quotes, and a `panel` for the Hopper footer. Anything outside
the subset round-trips as a warning, never as silent loss.

### 5.4 Policy

Loaded from `hopper.toml`, enforced in the dispatcher before any command runs:

```toml
[policy]
mode = "read"                       # read | plan | write
protected_statuses = ["Done"]       # leaving these needs --force and a reason
max_writes_per_apply = 50           # a plan larger than this is refused
require_reason = true               # every write carries --reason, stored in the journal
footer = true                       # comments and descriptions written by Hopper end with
                                    # "— asi_hopper <actor> <journal-id>" so Jira shows provenance
# production_writes_approved_by = "2026-xx-xx <name>"   # absent: only test projects are writable

[[projects]]                        # the allowlist; writes outside it are refused
key = "HWL"
test = false                        # production: read only until the line above exists

# [[projects]]                      # a test project would go here; none exists and none will be requested (section 13, decision 2)
# key = "FSBX"
# test = true
```

Violations are returned as `Result.errors`, never as exceptions, so an agent sees them.

### 5.5 Journal

SQLite, one row per operation: journal id (ULID), actor (`cli`, `python`, `agent`,
`dewey`), Atlassian account id, timestamp, verb, issue key, reason, request, response, prior
state, status (`applied`, `failed`, `undone`), plan id and step id when part of a plan, and
an idempotency key. `asi-hopper undo <id>` reverses an update (restores prior fields), a
transition (transitions back if the workflow allows, otherwise reports), a comment (posts a
retraction), a link (removes the link), and a create (transitions to the configured cancelled
status and labels `hopper-undone`). The journal is also the evidence that a given change was
made by a given actor for a given reason.

### 5.6 Plan and apply

```
asi-hopper plan steps.jsonl --out plan.json     # resolve names to ids, validate against
                                                # create-meta, check policy, compute diffs,
                                                # write a human-readable plan; touches no issue
asi-hopper apply plan.json                      # execute step by step, journal each one,
                                                # stop on first failure, write apply-report.json
```

The plan contains, per step: the verb, the resolved request, the current state, the diff, the
policy checks passed, and an idempotency key. Re-applying a plan whose steps are already in the
journal is a no-op. The plan file is what a reviewer signs off; the report is what goes into
the evidence folder.

### 5.7 Evidence

`asi-hopper snapshot "<jql>" --out evidence/stpa-2026-10-27.json` writes every matching
issue as `IssueRecord`s with comments and changelog, plus a manifest (JQL, timestamp, account,
count, SHA-256 of the body). `asi-hopper diff a.json b.json` or `diff a.json --live` shows
what changed. asi_gutenberg can render a snapshot into a report; this is the bridge from Jira
to the safety case.

### 5.8 Automation surfaces

| Surface | Who uses it |
|---|---|
| `asi-hopper <verb> ...` | The engineer, shell scripts, agents with a shell |
| `Hopper("hopper.toml").execute("get", key="HWL-2572")` | asi_dewey, asi_kletz, notebooks |
| `asi-hopper run steps.jsonl` | Batch work, recipes, replays |
| `asi-hopper serve --mcp` | Claude Code and other MCP clients puppet Hopper, with rails, instead of raw Jira |
| `asi-hopper serve --http 127.0.0.1:8765` | asi_dewey's window and any local front end (same JSON as `execute_dict`) |

## 6. Command vocabulary (first cut)

Read (allowed in every mode):

```
whoami                                 # account, site, scopes, policy mode
projects [--search <text>]             # visible projects with issue types
fields <project> <issue-type>          # create-meta: required fields, allowed values, custom field ids
get <key> [--comments] [--changelog]
search "<jql>" [--fields ...] [--max N] [--all]
transitions <key>
links <key> | comments <key> | history <key>
snapshot "<jql>" --out <file> | diff <a> <b|--live>
schema [<verb>] | status
```

Write (need `mode = "write"` or `--write`, an allowlisted project, and `--reason`):

```
create <project> <issue-type> --summary ... [--description md] [--set field=value ...] [--parent KEY]
update <key> --set field=value ... | --data '{json}'
transition <key> "<status or transition name>" [--resolution ...] [--force]
comment <key> --text "markdown"
assign <key> <me|email|accountId|unassigned>
link <key> <type> <other-key>          # e.g. link HWL-2574 blocks HWL-2572
label <key> --add x --remove y
worklog <key> --time 1h30m [--started ...]
watch <key> | unwatch <key>
```

Control:

```
plan <steps.jsonl> --out plan.json | apply plan.json | undo <journal-id>
run <steps.jsonl> [--stop-on-error true] | serve [--mcp | --http host:port] | journal [--tail N]
```

Wire format, identical to asi_dewey:

```json
{"verb": "transition", "args": {"key": "HWL-2575", "to": "In Progress", "reason": "Starting STPA step 4"}, "actor": "agent"}
{"ok": true, "verb": "transition", "data": {"key": "HWL-2575", "from": "To Do", "to": "In Progress", "journal_id": "01K8..."}, "errors": [], "warnings": []}
```

### 6.1 A recipe that matters today: the STPA triplet

The HWL board already follows a pattern: one STPA step becomes three stories, `– Work`,
`– Peer Review`, `– Approval` (see `HWL-2574`, `HWL-2572`, `HWL-2573`). As a script:

```jsonl
{"id": "s2-work",     "verb": "create", "args": {"project": "HWL", "type": "Story", "summary": "STPA Step 2 – Control Structure – Work",        "reason": "FuSa sprint planning"}}
{"id": "s2-review",   "verb": "create", "args": {"project": "HWL", "type": "Story", "summary": "STPA Step 2 – Control Structure – Peer Review", "reason": "FuSa sprint planning"}}
{"id": "s2-approval", "verb": "create", "args": {"project": "HWL", "type": "Story", "summary": "STPA Step 2 – Control Structure – Approval",    "reason": "FuSa sprint planning"}}
{"id": "l1", "verb": "link", "args": {"key": "$s2-work",   "type": "Blocks", "other": "$s2-review",   "reason": "review follows work"}}
{"id": "l2", "verb": "link", "args": {"key": "$s2-review", "type": "Blocks", "other": "$s2-approval", "reason": "approval follows review"}}
```

`$s2-work` is resolved by `plan` to the key the create step will produce. Hopper ships this as
a parameterised recipe (`asi-hopper recipe stpa-step --step 2 --title "Control Structure"`)
so it is one command, with the plan still reviewable first.

## 7. asi_dewey integration

- **Direction, v1:** Jira to dewey only. Jira is the truth for tickets; dewey's `jira_ticket`
  rows become a cached view, the way the Excel workbook is a view of dewey's database.
- **Who owns the sync:** asi_dewey. It adds `asi_hopper` as a path dependency and gains a
  `jira sync` verb that calls `Hopper.search(jql)` and upserts through its own
  `Brain.execute_dict(..., actor="hopper")`, so dewey's audit log sees it like any other actor.
  Hopper exposes normalised records and knows nothing about dewey.
- **Schema growth in dewey (proposed, separate change):** `jira_ticket` gains `key`,
  `issue_type`, `priority`, `assignee`, `updated`, `synced_at`; `name` becomes the Jira
  summary; `status` maps from Jira status category to dewey's `jira_status` lookup
  (`new → open`, `indeterminate → in progress`, `done → done`, `blocked` from a label or
  flag). The existing `url` field is filled from the issue key.
- **Later (v2):** dewey tasks of class `deliverable` can be *proposed* as Jira issues through
  a Hopper plan that the engineer reviews before it is applied.
- **asi_kletz:** the Safety Plan row's `status` can be reconciled against the linked Jira
  issue the same way, through the same `Hopper` API.

## 8. Authentication and security

- Hopper runs as the engineer's own Atlassian account (`c00289@contractor.asirobots.com`,
  account id `712020:cc2de3ca-…`). There is no service account; what the engineer may do in the
  browser is what Hopper may do, and the Jira changelog shows the engineer's name.
- **Personal API tokens are not permitted on this org** (decision 1, section 13), so there is
  no Basic auth anywhere in Hopper. Credential: an **OAuth 2.1 session** with Atlassian's
  Remote MCP Server, obtained once by `asi-hopper auth login` (browser consent, the same flow
  the Claude connector used). The refresh token is stored in Windows Credential Manager
  through `keyring` (service `asi_hopper`). Never in `hopper.toml`, never in the journal, never
  in a plan file, never in logs (the gateway redacts bearer headers).
- Hopper adds its own actor on top of the account: the journal distinguishes `cli`, `python`,
  `agent`, and `dewey` even though Jira sees one user. With `footer = true`, Jira itself shows
  provenance on every comment Hopper writes.
- OAuth 2.0 (3LO) against the REST API is the registered fallback gateway; it needs an app
  registered at developer.atlassian.com and may need IT approval to install on the site.
- The journal and snapshots live next to the config, under OneDrive, git-ignored.

## 9. Functional-safety posture

Hopper is a software tool used in the safety lifecycle (ISO 26262-8 clause 11; IEC 61508-3
7.4.4 in spirit). The argument for confidence in it is built into the design rather than
written afterwards:

| Concern | How Hopper answers it |
|---|---|
| A tool error could silently corrupt a safety record | No delete verb; every write journaled with prior state; undo; `plan` previews every diff; protected statuses need `--force` |
| A tool could act outside its remit | Policy allowlist of projects; read mode by default; write budget per apply; every write carries a reason |
| Results must be reproducible | Scripts with idempotency ids; replay is a no-op; plan files are inputs, reports are outputs, both are content-hashed |
| Behaviour must be verified | Test suite runs against recorded fixtures from the real site; a contract test records which endpoint and date each fixture came from; live tests only with `ASI_HOPPER_LIVE=1` |
| Evidence must be exportable | `snapshot` with manifest and SHA-256; `diff`; journal export; asi_gutenberg renders them |
| An AI agent must not be able to do more than the engineer intends | The agent talks to Hopper, Hopper talks to Jira; the rails are in code, not in a prompt |

Hopper does not claim a tool confidence level; it is designed so that one can be argued when
the programme's tool qualification plan asks for it.

## 10. What was learned from the live site (2026-10-27)

- Site `asirobots.atlassian.net`, cloud id `0e0e7883-6f84-469d-a098-706e035c766e`; scopes
  on the current connector are `read:jira-work`, `write:jira-work` plus Confluence read/write.
- 33 projects visible. The FuSa-relevant ones: `HWL` Wheel Loader (Haulage), classic,
  id 12649, issue types Task, Sub-task, Story, Bug, Epic, Initiative; `FSS` Foundation
  Systems & Safety, classic, adds Support, Objective; `FMFS` Fairway Mowing Functional
  Safety, team-managed; `RDRR` R&D Risk Register (discovery); `OSC` Occupational Safety
  Committee.
- `HWL` workflow as seen: `To Do` (10249) → `In Progress` (3) → `Done` (10001). Priorities
  include an `Un-Groomed` value (id 5). Labels in use: `safety`, `e-stop`, `VAT`,
  `test-failure`.
- Classic projects mean custom fields and required fields vary per issue type, so `fields`
  (create-meta discovery) is a read verb in the first release, not a later nicety.

## 11. Phases

| Phase | Deliverable | Exit test |
|---|---|---|
| 0. Access spike (half a day) | Python MCP client completes OAuth 2.1 login to `mcp.atlassian.com` for this account; `whoami`, `HWL` project, create-meta, and a JQL search succeed; responses recorded as fixtures | `whoami` returns the account from Python, no API token anywhere |
| 1. Read, v0.1.0 | Config, gateway protocol, `McpGateway`, `ReplayGateway`, model, `Result`, dispatcher, CLI; verbs `whoami projects fields get search transitions links comments history snapshot schema status` | All read verbs pass against fixtures; one live smoke test; the open-tickets snapshot in `evidence/` reproduces from the CLI |
| 2. Write with rails, v0.2.0 | Policy (including the test-project lock), journal, Markdown↔ADF, verbs `create update transition comment assign link label`, `plan`, `apply`, `undo`, footer. **Built and tested against `ReplayGateway` and `DryRunGateway` only; live write tests are blocked until decision 2 delivers a sandbox project** | Create → update → transition → undo round-trips in the sandbox project, journal shows before/after; until then, the same round-trip passes in replay |
| 3. Automation, v0.3.0 | `run`, `recipe stpa-step`, `serve --mcp`, `serve --http`, `Hopper.search` surface for dewey; dewey `jira sync` lands as a dewey change | Claude Code creates an STPA triplet through Hopper from a plan; dewey's Jira table refreshes from `HWL` |
| 4. Evidence, v0.4.0 | `diff`, snapshot manifests and hashes, journal export, `worklog`, `watch`, OAuth gateway if needed | A dated STPA evidence bundle renders through asi_gutenberg |

Each phase ships with tests, a CHANGELOG entry, and a README update, as the siblings do.

## 12. Layout

```
asi_hopper/
  README.md  CHANGELOG.md  pyproject.toml  uv.lock  .python-version  .gitignore
  hopper.example.toml          copy to hopper.toml (git-ignored)
  docs/proposal.md             this document
  recipes/stpa_step.jsonl      parameterised scripts
  src/asi_hopper/
    hopper.py                  Hopper: wires everything, in-process API, hopper.toml loading
    config.py                  settings, precedence, keyring
    gateway/                   JiraGateway protocol, RestGateway, ReplayGateway, DryRunGateway, GatewayFactory, retry
    model/                     IssueRecord, Transition, Link, Comment, FieldMeta, Changeset
    adf/                       Markdown <-> ADF
    policy/                    Policy, rules, violations
    journal/                   SQLite journal: audit, undo, idempotency
    services/                  issues, search, transitions, links, comments, evidence
    commands/                  Result, Command, CommandFactory, Dispatcher, verbs
    plan/                      Plan, Step, compile, apply, report, reference resolution ($id)
    automation/                CLI, script runner, MCP server, HTTP server
  tests/                       pytest; fixtures/ recorded from the live site with dates
```

Dependencies: `mcp` (client, for `McpGateway`; server, for `serve --mcp`), `keyring`,
`httpx` (only for the fallback `rest` gateway). Python 3.13, `uv`, `ruff`, `pytest`,
`tool.uv.link-mode = "copy"` for OneDrive, like the siblings.

## 13. Decisions (2026-10-27)

Questions 1 and 2 were answered by the owner; 3 to 6 were decided the way the tech lead would
decide them, and stand unless overruled.

1. **API tokens: not permitted.** Decided by the owner. Consequence: no Basic auth in Hopper.
   Phase 0 uses the Atlassian Remote MCP Server over OAuth 2.1, which this account is already
   authorised for (it is what the Claude connector uses). OAuth 2.0 (3LO) against the REST API
   is the fallback and would need an app registration and possibly IT approval. Sections 5.1,
   8, and 11 updated.
2. **Sandbox: none exists, so no writing until a test project exists.** Decided by the owner.
   Consequences: `mode = "read"` is the shipped default, and a second, independent lock means
   write verbs refuse any project not marked `test = true`; production projects additionally
   need a dated `production_writes_approved_by` line. Phase 2 is built and tested in replay
   only. The sandbox this decision contemplated (a project `FSBX` "FuSa Sandbox" sharing
   `HWL`'s workflow and issue type schemes) was withdrawn the same day: the write side is
   delayed indefinitely by owner decision and no project will be requested. Hopper does not
   create issues in `HWL` labelled as sandbox; a safety board is not a test bed.
3. **Cancelled status for undo-of-create:** transition to `Done` with resolution `Won't Do`,
   add label `hopper-undone`, post a retraction comment that names the journal id. If the
   workflow exposes a dedicated `Cancelled` status, prefer it; verify on the sandbox during
   phase 2, never on `HWL`.
4. **Provenance footer: yes, on by default.** One line, no decoration:
   `— asi_hopper · actor=agent · journal=01K8…`. Auditors want provenance where the record
   is, not only in a local database. Configurable per project in case a team objects.
5. **Dewey schema: approved as a separate dewey change.** `key` becomes the natural unique
   key and the upsert target; `name` holds the Jira summary; `order` stays as display
   ordering; add `issue_type`, `priority`, `assignee`, `updated`, `synced_at`. Status maps from
   Jira status category (`new → open`, `indeterminate → in progress`, `done → done`);
   `blocked` only from an explicit Jira flag or label, never inferred. Sync runs in dewey with
   actor `hopper`.
6. **Confluence: out of scope, permanently for this tool.** A Confluence door, if ever
   wanted, is a separate sibling that reuses the gateway pattern, not a Hopper feature.
   *2026-10-29:* the owner asked for a read-only Confluence sandbox "just like we did with jira"; it
   shipped in Hopper 0.1.7 (`confluence` verb, `docs/confluence-sandbox-2026-10-29.md`), reads only,
   write side closed. Whether this decision is formally superseded is the owner's call.

## 14. Status

Design approved with the two constraints above. On 2026-10-27 the owner decided that the write
side is delayed indefinitely and that no sandbox will be requested, so Hopper is a read-only
tool, and the work is integrating its read capabilities into asi_kletz and asi_dewey (see
`docs/integration-plan.md`). Phase 0 and phase 1 were done the same day:
the OAuth login from Python against `mcp.atlassian.com` and the 0.1.0 read verbs with fixtures.

## 15. Integration with the primary tools (read side)

Both siblings add `asi_hopper` as a path dependency and gain a read-only `jira` verb family
that calls ``Hopper(interactive=False)``:

- **asi_dewey** `jira sync [--jql ...]`: upserts `IssueRecord.to_row()` into `jira_ticket`
  keyed by `key`, through `Brain.execute_dict(..., actor="hopper")`; the dashboard's "open
  Jira tickets" tile reads the synced rows. `jira status` reports the last sync time and count.
- **asi_kletz** `jira reconcile`: for every Safety Plan row that names a Jira key, compares the
  row's `status` with the issue's `status_category` and reports mismatches; never changes the
  row without `--apply`, and `--apply` only touches kletz's own database, never Jira.
- Both tools can call `hopper.evidence.snapshot(...)` to attach a dated bundle to a review.

Hopper's side of this is done in 0.1.0: `Hopper.search` / `Hopper.get` return records,
`IssueRecord.to_row()` is the flat shape, `AuthRequired` is the error a sibling surfaces when
the engineer has not run `asi-hopper auth login` yet.

---

## Revision history

- 2026-10-29 Decision 6 carries a dated note: a read-only Confluence surface shipped in Hopper 0.1.7 at
  the owner's request; the write side stays closed. No other design change.
- 2026-10-28 Wording sweep: decision 2, section 14 and this history say what the status line says:
  write side delayed indefinitely by owner decision, no sandbox requested. No design change.
- 2026-10-27 Proposal 0.3: write side delayed indefinitely, no sandbox request; status and section 15
  (read-side integration with asi_dewey and asi_kletz) added; 0.1.0 shipped.
- 2026-10-27 Proposal 0.2: decisions recorded (no API tokens, no sandbox yet, writes locked);
  gateway changed to Remote MCP over OAuth 2.1 with REST/3LO as fallback; test-project lock
  added to policy; phases 0 to 2 adjusted; first evidence snapshot (open tickets) added under
  `evidence/`.
- 2026-10-27 Proposal 0.1: vision, rationale against the raw connector, principles,
  architecture, command vocabulary, STPA triplet recipe, asi_dewey integration, security,
  FuSa posture, live-site findings, phases, layout, open questions.
