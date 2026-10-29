# Integrating asi_hopper (read only) into asi_dewey and asi_kletz

**Status:** Plan 0.2, 2026-10-29 (0.1 of 2026-10-27 plus the Confluence surface of Hopper 0.1.7 and 0.1.8)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md), the charter: the ontology's
gateway tier, the edges table, and the plans index, where this plan is listed.
**Scope:** read only. Nothing here writes to Jira or Confluence. Each sibling only writes to its own SQLite.

## 0. What Hopper already provides (0.1.0; Confluence since 0.1.7)

```python
from asi_hopper import Hopper
from asi_hopper.errors import AuthRequired, HopperError

with Hopper(interactive=False) as hopper:          # reads ./hopper.toml or $ASI_HOPPER_CONFIG
    issues = hopper.search("project = HWL AND assignee = currentUser()")   # list[IssueRecord]
    issue = hopper.get("HWL-2572")                                          # IssueRecord
    row = issue.to_row()        # flat: key, type, summary, status, status_category, priority,
                                # assignee, reporter, labels, parent, created, updated, due, url
```

`AuthRequired` means the engineer has not run `asi-hopper auth login` yet; surface it as a
`Result` error with that instruction, nothing else. Everything else is `HopperError`.

Hopper is offline-testable: `Hopper(gateway="replay", fixtures="<asi_hopper>/tests/fixtures")`
returns the recorded HWL data, so each sibling's tests can cover its `jira` verbs without a
session or a network.

Confluence, read only, since 0.1.7 (the same `Hopper`, the same session):

```python
refs = hopper.cql("title ~ 'STPA'", space="STPA")            # list[PageRef]: id, title, url, excerpt
page = hopper.page("399343803")                               # PageRecord: markdown body, version, updated
hopper.execute("confluence", action="comments", target="399343803")
manifest = hopper.evidence.snapshot_pages(                    # 0.1.8: a dated, hashed page bundle
    PageSource.parse("399343803", depth=1), out_dir, comments=True
)
```

`PageSource` is `asi_hopper.services.evidence.PageSource`. The replay fixtures cover the STPA space,
page 399343803 with its two children and their comments.

## 1. Dependency

In each sibling:

```powershell
uv add --editable ..\asi_hopper
```

`pyproject.toml` then carries `asi_hopper` as a path source (same pattern as asi_gutenberg).
The sibling's `hopper.toml` is not needed: pass `config_path` or rely on
`ASI_HOPPER_CONFIG`; recommended is one `hopper.toml` in the asi_hopper folder and
`ASI_HOPPER_CONFIG` pointing at it so every tool shares the same session and site.

## 2. asi_dewey

### 2.1 Schema change (`jira_ticket`)

Today: `order`, `name`, `status` (lookup `jira_status`: open / in progress / blocked / done),
`url`. Add, all optional so existing rows and the workbook import keep working:

| Field | Type | From `IssueRecord` |
|---|---|---|
| `key` | TEXT, unique when set | `key` |
| `issue_type` | TEXT | `issue_type` |
| `priority` | TEXT | `priority` |
| `assignee` | TEXT | `assignee` |
| `parent_key` | TEXT | `parent.key` |
| `labels` | TEXT | `";".join(labels)` |
| `updated` | DATE/TEXT | `updated` |
| `synced_at` | TEXT | time of the sync |

`name` receives the Jira summary; `url` receives `url`; `status` is mapped from
`status_category`: `new → open`, `indeterminate → in progress`, `done → done`; `blocked` only
when the Jira status name contains "Blocked" (HWL has `Blocked` and `Development - Blocked`).

### 2.2 Verbs (registered in `asi_dewey/commands/jira.py`)

- `jira sync [--jql "<jql>"] [--dry-run]`: default JQL from `dewey.toml`
  (`jira_jql = "project = HWL AND (assignee = currentUser() OR watcher = currentUser())"`).
  For each record: upsert by `key` through the existing `EntityService` (so validation and the
  audit log apply, actor `hopper`); rows with a `key` not in the result keep their data and get
  a warning in the `Result`, never a delete. Returns counts: created, updated, unchanged,
  missing.
- `jira status`: last sync time, row counts by status, whether a session exists
  (`Hopper.status()["session"]["logged_in"]`).
- `jira get <key>`: pass-through to `hopper.execute("get", ...)` for the GUI's detail pane.

### 2.3 GUI

- Dashboard tile "Open Jira tickets" reads the synced rows (no live call on refresh).
- A `Sync Jira` button on the Jira Ticket screen calls `jira sync` and refreshes via the event
  bus; `AuthRequired` is shown in the status bar with the login instruction.

### 2.4 Tests

- `tests/test_jira.py` builds the dewey `Brain` on a temp database and a Hopper on the replay
  fixtures, runs `jira sync`, asserts the mapped rows, re-runs and asserts `unchanged`.

## 3. asi_kletz

### 3.1 Schema change (`safety_plan_row`)

Add `jira_key` (TEXT, optional) so a deliverable can name the Jira issue that tracks it, and
`jira_status` (TEXT, optional, read-only mirror).

### 3.2 Verbs

- `jira reconcile [--apply]`: for each row with a `jira_key`, `hopper.get(key)`; report
  `plan_status` vs Jira `status_category` mismatches using the mapping
  `Pending → new`, `Ongoing → indeterminate`, `Done → done` (`Blocked`, `Alternative`,
  `Out-of-Scope` are never auto-mapped). Without `--apply` nothing changes; with it, only
  `jira_status` is written (the mirror), never `plan_status`. The engineer decides the plan.
- `jira link <row-id> <key>`: sets `jira_key` after verifying the issue exists.

### 3.3 Matrix screen

- A column "Jira" showing `jira_status` with a tooltip of the Jira summary; the cell opens the
  issue URL.

### 3.4 Confluence (after 3.1 to 3.3; decided 2026-10-29; superseded the same day)

> Superseded by [confluence-integration-plan.md](confluence-integration-plan.md), sections 4 and 5: no new
> columns, the row's `urls` list (Kletz 0.20.0) is the association; `confluence link`, `confluence evidence`
> and `confluence check` are specified there. Kept for the record.

- `safety_plan_row` gains `confluence_page_id` (TEXT, optional) and `confluence_url` (TEXT, optional):
  the page that backs a deliverable, found once with `hopper.cql(...)` and kept on the row.
- `confluence link <row-id> <page-id>` sets them after `hopper.page(id)` confirms the page is visible.
- `confluence evidence [--rows ...]` calls `hopper.evidence.snapshot_pages(PageSource(ids=...),
  <kletz evidence dir>, comments=True)` for the linked pages and records the manifest's folder and
  `taken_at` on each row; a later `asi-hopper diff <bundle>` shows what changed since the review.
- No list refresh calls `hopper.page()`: every page carries its body. The matrix shows the stored
  `confluence_url` only.

## 4. Shared conventions

- Both siblings call Hopper with `interactive=False` and `actor="hopper"` when writing to their
  own database.
- Both read `ASI_HOPPER_CONFIG` first; neither ships a `hopper.toml` of its own.
- Both can call `hopper.evidence.snapshot(jql, out_dir, title=...)` (Jira) or
  `hopper.evidence.snapshot_pages(source, out_dir, ...)` (Confluence, 0.1.8) to attach a dated bundle
  to a review; the bundle lives under the sibling's evidence folder, and `asi-hopper verify` checks it.
- Neither sibling imports anything from `asi_hopper.gateway`; the surface is `Hopper`,
  `IssueRecord`, `Result`, and the two error classes.

## 5. Order of work

1. asi_dewey schema change and `jira sync` with tests on the replay fixtures (half a day).
2. asi_dewey GUI tile and button (an hour).
3. asi_kletz `jira_key`, `jira link`, `jira reconcile` with tests (half a day).
4. One live run of each against `HWL` after `asi-hopper auth login`; record the result in each
   CHANGELOG.
5. asi_kletz Confluence columns, `confluence link` and `confluence evidence` (section 3.4) with
   tests on the replay fixtures (half a day), then one live run against the STPA space.
