# Confluence into the family: work product links in Kletz, STPA objects in Dewey, one door in Hopper

**Status:** Proposed (written 2026-10-29, the day Hopper 0.1.8 shipped page evidence bundles)
**Owner:** FuSa engineer
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md): the ontology (gateways hand plain
records up, primary tools decide what to keep), the policy "Confluence: reads only", the identity rule (`uid`),
the plans index where this plan is listed.
**Supersedes:** section 3.4 of [integration-plan.md](integration-plan.md) (the `confluence_page_id` columns it
proposed are not needed: the plan row's `urls` list already is the association).
**Target versions:** asi_kletz 0.22.0 and 0.23.0, asi_hopper 0.1.9, asi_dewey 0.10.0, in that order (the plan
was written against Kletz 0.20.0 and Dewey 0.8.4; the same day shipped Kletz 0.21.0 and Dewey 0.9.0 on other
work, so every number moved up one).
**Scope:** read only. Nothing here writes to Confluence or Jira. Each tool writes its own SQLite only.

---

## 1. The ask

The owner, 2026-10-29: "let us plan a big project, cross repo... when we add confluence read only into kletz we
should be able to associate objects with jama urls; obviously the next candidate is replacing the google.com
placeholder with a real url once known; but more importantly there may be a way to tie in individual stpa
objects to confluence." And right after: "i said jama but meant confluence."

Read as three asks, in rising order of size:

1. **Kletz associates its objects with Confluence URLs.** Kletz 0.20.0 already stores an ordered list of URLs per
   deliverable; what is missing is that the tool knows *what* a URL is (a Confluence page, a Jira issue, the
   placeholder), can find a Confluence page without leaving the window, and can prove what the page said.
2. **The placeholder gives way to real Confluence URLs once they are known.** The placeholder is the Microsoft
   homepage, not google.com (`plan urls --placeholder`, 0.20.0, the owner's own wording "use microsoft homepage as
   placeholder url for all"); the replacement must be one audited bulk operation, not 63 hand edits.
3. **Individual STPA objects tie to Confluence.** The STPA pages carry losses, hazards, unsafe control actions,
   loss scenarios and constraints with stable local identifiers (H2, UCA14, CSTR28). Today no tool holds any of
   them. Dewey gets them as entities, each one citing the page, the version and the section it came from, and the
   family can trace a hazard to a UCA to a scenario to a constraint to a Jira ticket to a plan deliverable.

That third one is the point of the whole programme's tooling. It is also the one where the design has to be right
the first time, so this plan spends most of its words there.

## 2. What exists today (facts, 2026-10-29)

**Hopper 0.1.8.** One `confluence` verb (`spaces`, `pages`, `page`, `children`, `search`, `comments`, `replies`,
`snapshot`), `Hopper.page(id)` and `Hopper.cql(cql, space=)`, frozen `PageRef` / `PageRecord` / `PageComment`,
`EvidenceService.snapshot_pages(PageSource, out_dir)` writing a hashed bundle (`pages.json`, `pages/<id>.md` byte
for byte, `pages.csv`, `pages.md`, `manifest.json`), `verify` and `diff` for both bundle kinds. The write side is a
closed contract. Rovo `search` is out of the adapter by owner decision. The first bundle is
`evidence/locator-safety-function-stpa-2026-10-29/`.

**Kletz 0.20.0 (schema 10).** `safety_plan_row.urls`: an ordered JSON list of absolute http(s) URLs, the first the
link; `schema/urls.py` (`parse_urls`, `first_url`, `url_host`...); `WorkProductService` guards every write;
`plan urls --placeholder <url> [--check]`; the export's **Work product** hyperlink column shows the host; the form's
`UrlsWidget` with Open; `row_N_url` / `row_N_urls` for the standards. Location flags `loc_jama`, `loc_dms`,
`loc_sharepoint` exist as check marks independent of the URLs. The `jira_key` field has a picker fed by the last
JIRA Live Data fetch (0.15.0). Pickers are a `FieldSpec.picker` string dispatched in `gui/widgets.py` and
`gui/entity_screen.py`: `jira`, `people`, `urls`.

**Dewey 0.8.4 (schema 3).** STPA control structures (`control_structure`, `cs_controller`, `cs_algorithm`,
`cs_process_model_entry`, `cs_edge`, `cs_signal`, `cs_note`), a `ControlStructureFactory` with registered builders
(`blank`, `template:wheel_loader_master`, `from_drawio`, `from_datasets`, `clone`), a `cs` verb, exports through
Escher. No entity for a loss, a hazard, a UCA, a scenario or a constraint. `docs/control-structure-plan.md`
section 2 already says the ids are stable slugs "so the later STPA steps (unsafe control actions, loss scenarios)
can point at a signal by CA-13 and a controller by vak_controller": this plan is those later steps.

**The Confluence STPA pages** (from the bundle; page 399343803 "Locator Safety Function STPA", version 45, with
two children). One page is one analysis, in four sections under `##` headings:

| Section | What it holds | How objects are written |
|---|---|---|
| Losses and Hazards | a HAZARD FOCUS list | one line each: `H2 - <hazard text>`, `H4.3 - <hazard text>` (dotted codes are sub-hazards of H4) |
| Control Structure | prose and the picture | the picture is an attachment, not in the Markdown; the controllers and control actions reappear as the first two columns of the next table |
| Context Table | one row per controller and control action, four UCA columns (not providing / providing / timing or order / stopped too soon or applied too long) | cells hold one or more `**UCA14 **text *[H2, H4.3]*`; strikethrough (`~~UCA3~~`) means retired; `(duplicate of **UCA10**)` is written in words |
| Loss Scenarios | one numbered row per UCA and per its safe counterpart `CAn`, with Type (1 to 4), causal factors, constraints | `**CSTR28 **text`, `**CSTR1 **and **CSTR2**` (a reference without text), beliefs in italics, `(same as UCA5 CF)` cross references |

Three observations that shape the design:

- **Local codes are stable within a page and not unique across pages.** Every STPA page has its own UCA1. The
  only globally unique key is (Confluence page id, local code). Dewey keys objects that way and never by code
  alone.
- **The page version and the body hash are the baseline.** Version 45 of 399343803 is exactly the bytes in
  `pages/399343803.md`, hash `5f6f8272...`. An object that cites "page 399343803, version 45, section Context
  Table, UCA14" is a citation that can be checked for as long as the bundle exists, and `asi-hopper diff` says
  when the live page moved.
- **The Markdown the MCP server renders flattens cell formatting.** Bold runs are glued to their text
  (`**UCA1 **When the vehicle...`), line breaks inside a cell vanish, and strikethrough wraps fragments. The reader
  works on this text as it is; it never asks for ADF to get a cleaner shape (the ADF is there, `--format adf`,
  as a fallback for a cell the Markdown reader cannot split).

The STPA space holds 97 pages (the CQL fixture's total). Child pages carry scenario details and review notes;
page comments (8 inline on the Locator page, with the selected sentence each) are the review history and are
already in the bundle.

## 3. Where each piece belongs

The ontology decides this, not convenience:

| Piece | Repo | Why |
|---|---|---|
| Reading pages, searching, evidence bundles, generic page anatomy (sections, tables, links, heading anchors) | **asi_hopper** | a gateway normalises what the external system says into plain records; the anatomy of a Confluence page is about Confluence, not about STPA |
| URL kinds, the Confluence picker on a deliverable, evidence per deliverable, the placeholder replacement | **asi_kletz** | the Safety Plan and its deliverables; no STPA knowledge |
| Losses, hazards, UCAs, scenarios, constraints; the reader that turns an STPA page into them; the links to control structures | **asi_dewey** | working knowledge; `control-structure-plan.md` already reserved the place |
| Nothing | **asi_standards** | `row_N_url` / `row_N_urls` already carry the links into QF-17 |

Dewey and Kletz still never import each other. Both point at the same Confluence page id, which is the join a
human or an agent makes by reading the two tools; neither tool stores the other's rows.

## 4. Phase A: Kletz 0.22.0, URLs that know what they are

No schema change. `schema/urls.py` gains `url_kind(url) -> str` and `URL_KINDS = ("confluence", "jira",
"sharepoint", "placeholder", "other")`, decided from the host; Confluence is the one that matters:

| Kind | Host rule | Source of the rule |
|---|---|---|
| `confluence` | `asirobots.atlassian.net` with path `/wiki/` | known |
| `jira` | `asirobots.atlassian.net` with path `/browse/` or `/jira/` | known |
| `sharepoint` | `*.sharepoint.com` | known |
| `placeholder` | `www.microsoft.com` (the 0.20.0 placeholder) | known |
| `other` | anything else (a Jama or DMS link today) | an optional `kletz.toml` `[urls] hosts = {jama = "...", dms = "..."}` names more kinds when the owner wants them; not asked for |

What uses it:

- **The export's Work product cell** reads the kind and the host ("Confluence, asirobots.atlassian.net"; a
  placeholder row reads "placeholder"), so a reviewer sees at a glance which deliverables still point nowhere.
- **The form's link lines** carry the kind as a prefix.
- **`plan urls --audit [--rows ...]`** (no write): per row, the kinds present, and the findings: a placeholder
  still present, no `confluence` URL on a deliverable whose work product location names Confluence, a `jira` URL
  that disagrees with the row's `jira_key`. A JSON Result, one line per finding, for an agent to act on.
- **`plan urls --replace <old-url> <new-url> [--check]`**: every row whose list contains `old` gets `new` in the
  same position, one transaction, one audit entry (`urls_replace`, with the ids), the event
  `plan.urls_replaced`; `--check` names the rows and writes nothing. This is how the placeholder gives way to a
  real page URL on every row at once, and how a page that moves is corrected once. Phase B's `confluence link`
  is the per-row way, with the page checked live.
- A per-kind setter is not added: `update safety_plan_row N --set urls=...` already does it, and the window's
  URLs box too.

The owner's "jama" of 2026-10-29 was a slip for Confluence. No Jama door, host or kind is planned; the `other`
kind and the optional host map above are there only so a pasted Jama or DMS link is not mislabelled.

Tests: `test_url_kinds.py` (every kind, the optional host map, the audit's findings on the seeded database, the
replacement in three forms and its dry run, the export cell text). Half a day.

## 5. Phase B: Kletz 0.23.0, Confluence read only, through Hopper

The `asi_hopper` dependency is already there (0.5.0). No schema change: the URL list is the association, as the
owner designed it in 0.20.0.

**Verbs** (`commands/confluence.py`, the `jira` verb's shape; every one a JSON Result; `AuthRequired` surfaces as
the one line "run `asi-hopper auth login`", as the Jira verbs do):

- `confluence search <text> [--space KEY] [--limit n]`: `hopper.cql("title ~ '<text>'", space=...)`, the refs
  as rows (id, title, space, url, last modified). No Rovo.
- `confluence page <id-or-url>`: `hopper.page(id)` without the body by default (title, version, updated, url,
  parent), `--body` for the Markdown. Accepts a page URL and pulls the id from it (`pageId=` or `/pages/<id>/`).
- `confluence link <row> <id-or-url> [--first]`: resolves the page (it must exist and be visible), appends its
  canonical URL (`.../wiki/pages/viewpage.action?pageId=<id>`) to the row's `urls` (first with `--first`), through
  the ordinary update path so the guard, the audit and the event apply. Refuses a URL already on the row.
- `confluence evidence [--rows ...] [--comments] [--out DIR]`: collects every `confluence` URL on the chosen rows
  (default all), calls `hopper.evidence.snapshot_pages(PageSource(kind="pages", ids=...), out, comments=...)`
  with the Kletz evidence folder (`kletz.toml` `evidence_dir`, default `evidence/`), and answers the manifest.
  One audit entry (`confluence_evidence`: the folder, the page ids, the rows). A deliverable's evidence is then
  the Hopper bundle, verifiable with `asi-hopper verify` and comparable with `asi-hopper diff`; Kletz stores no
  page text.
- `confluence check [--rows ...]`: for every `confluence` URL, is the page still there and what version is it
  (`hopper.page`, no body); for rows whose last evidence bundle is known from the audit log, whether the version
  moved since. Read only, a report.

**The window.** The URLs box gets a **Find page** button (greyed when Hopper has no session): a small window in the
People Lookup pattern (`gui/people_lookup.py`): a text entry, a space drop-down (default STPA), Search, the hits
in a list (title, space, last modified), Insert appends the page's URL to the editor. The search runs as a
`BackgroundFetch` of `confluence search`, never on the Tk thread. No page body is shown in Kletz: the link opens
the browser, as the Open button does today.

**Dashboard.** One tile: deliverables with a Confluence link, with a placeholder, with no URL at all.

Tests on Hopper's replay fixtures (`Hopper(gateway="replay", fixtures=<asi_hopper>/tests/fixtures)`, which already
hold the STPA space search, page 399343803 with its children and comments): the verbs in three forms, `link`
through the guard, `evidence` producing a bundle that `asi-hopper verify` accepts, `check` on the fixtures, the
Find page window with the fetch monkeypatched, the dashboard tile. One day.

## 6. Phase C: Hopper 0.1.9, the anatomy of a page

Generic helpers so that a consumer can cite a part of a page without parsing Markdown itself. No STPA knowledge
enters Hopper.

`asi_hopper/model/pagetext.py` (pure functions on the Markdown body):

- `sections(markdown) -> list[Section]`: `Section(level, heading, anchor, start, end, text)`, split on `#`
  headings; `anchor` is the Confluence heading anchor for the page URL (`#Context-Table` for the cloud editor;
  the exact rule is confirmed against the live page and recorded in the fixture).
- `tables(text) -> list[Table]`: GitHub-style pipe tables into `Table(header, rows)` with cells as text, pipes
  inside cells unescaped.
- `links(text) -> list[Link]`: `(label, url, page_id or None)` for every Markdown link, the page id pulled from
  Confluence URLs.
- `strike(text) -> (clean, was_struck)` and `bold_runs(text)`: the two formatting facts a consumer needs to read a
  cell written as `**UCA1 **When the vehicle...`.

Surface: `PageRecord.sections()`, `PageRecord.anchor_url(heading)`; `confluence page <id> --section "Context
Table"` returns that section's text; `pages.json` entries in a bundle gain `sections: [{heading, anchor,
sha256}]` so a citation can name a section hash as well as the body hash (the manifest format is unchanged
otherwise; `record_version` stays 1 because the addition is a new key).

Tests on the recorded page (the four sections, the two tables with their row counts, the links to the
ASIMFS pages, a struck cell), plus a synthetic page for the edge cases. Half a day.

## 7. Phase D: Dewey 0.10.0, the STPA step objects

> **Moved, 2026-10-29, later the same day.** Phase D shipped in asi_dewey 0.10.0 and 0.10.1 as written, and the
> owner then decided that control structures and every STPA object belong in Kletz ("Dewey is more for
> experimental and day to day; all true work products will end up in Kletz once sanitized"). asi_kletz 0.24.0
> holds the entities, the `stpa` verb, the reader through Kletz's own Confluence path, the views and the screen,
> unchanged in dialect; asi_dewey 0.11.0 removes them and keeps a `handover` verb. Read this section as the
> design; the code is in asi_kletz.

### 7.1 Entities (schema 4)

One `stpa_analysis` holds everything from one Confluence page; every child row names its analysis, so many
analyses coexist and the same local code means different things under different analyses.

| Entity | Fields (beyond id, uid, created, updated) | Rules |
|---|---|---|
| `stpa_analysis` | name, slug, system, status (Draft / Reviewed / Baselined), control_structure (slug or empty), source_kind (`confluence` / `hand`), source_page_id, source_url, source_version, source_body_sha256, source_taken_at, source_bundle (folder), note | one analysis per (source_page_id, source_version) at most; `source_*` are readonly after `from_confluence` |
| `stpa_loss` | analysis, order, code (`L1`), text | code unique within the analysis |
| `stpa_hazard` | analysis, order, code (`H2`, `H4.3`), text, parent (hazard code or empty), losses (list of codes), retired (bool), cite | a dotted code's parent is the code before the last dot when that hazard exists |
| `stpa_uca` | analysis, order, code (`UCA14`), controller (text), control_action (text), category (`not_providing` / `providing` / `timing_order` / `duration`), text, hazards (list of codes), retired (bool), duplicate_of (code or empty), cs_controller (key or empty), cs_signal (signal id or empty), cite | code unique within the analysis; every hazard code listed must exist in the analysis (a warning, not a refusal: the pages cite `[H4]` where only H4.3 to H4.5 are listed) |
| `stpa_scenario` | analysis, order, row (the table's number), uca (code), counterpart (`CA14` or empty), types (list of 1 to 4), causal_factors (multiline), beliefs (multiline), constraints (list of CSTR codes), cite | the uca must exist; a row whose UCA cell is empty is kept with `uca` empty and a warning |
| `stpa_constraint` | analysis, order, code (`CSTR28`), text (empty when only referenced), cite | code unique within the analysis; `text` filled from the first row that spells it out |

`cite` is one text field on every object, the citation: `page <id> v<version> § <heading> (<anchor url>)`, built
by the reader, editable, and the one thing a Gutenberg report prints beside the object. Lists are JSON arrays in
text columns, as in the control structures. `cs_controller` and `cs_signal` are filled only when the analysis
names a control structure and the names match (section 7.3).

### 7.2 The factory and the verb

`StpaFactory` beside `ControlStructureFactory`, same `Builder` and `register_builder`:

- `blank` (name, system): the analysis and nothing else, for one written by hand.
- `from_bundle` (path, name): reads `pages/<id>.md` and `manifest.json` from a Hopper bundle folder. **This is
  the primary builder**: offline, hashed, replayable, and what the tests use. The analysis's `source_*` come
  from the manifest.
- `from_confluence` (page id, name, out): `hopper.evidence.snapshot_pages(PageSource(kind="pages", ids=[id]),
  out, comments=True)` into Dewey's evidence folder, then `from_bundle`. Needs a session; the bundle it writes
  is the evidence.
- `clone` (from): a deep copy under a new slug.

The `stpa` verb, the `cs` verb's shape: `stpa list | get <id> | builders | new <builder> [--name --system --from
--page --out] | refresh <id> [--apply] | validate <id> | link <id> --structure <slug> [--apply] | export <id>
--out <dir> [--format xlsx|md|docx|pdf|svg|png] | delete <id> [--cascade]`. The parts are rows of their own
entities, so the generic `create` / `update` / `delete` and the Excel sheets work on them.

- `refresh`: snapshot the page again, read it, and compare to the stored objects by code: new, changed (text,
  hazards, category), retired (now struck or gone). A report; `--apply` applies it, keeps every Dewey-side field
  (`cs_controller`, `cs_signal`, notes, status) and writes one audit entry per object changed. Confluence stays
  the truth for the text; Dewey owns the links.
- `validate`: dangling hazard codes, UCAs without a scenario, constraints only referenced, duplicate texts, UCAs
  that name a controller the attached structure does not have.
- `link --structure`: proposes `cs_controller` and `cs_signal` for every UCA by name (section 7.3); applies with
  `--apply`.

### 7.3 The reader (`asi_dewey/stpa/confluence_reader.py`)

Pure functions over Hopper's `sections` and `tables` (Phase C), standard library only, the way `drawio_reader.py`
is. It never sees raw Atlassian JSON.

- **Hazards**: in the section whose heading contains "Losses and Hazards", every line `^(H\d+(\.\d+)*)\s*-\s*(.+)$`;
  a struck line is retired. Losses the same with `L`. The page under study lists hazards only; losses stay empty
  with a warning.
- **UCAs**: in the first table of the section whose heading contains "Context Table": column 0 is the controller
  (carried down when empty, as the page does), column 1 the control action, columns 2 to 5 the four categories in
  the table's order. Each cell is split on `**UCA\d+\s*\*\*` boundaries; for each piece: the code, the text up to
  the hazard list, the `[H2, H4.3]` codes, retired if the run is struck, `duplicate_of` from `(duplicate of
  **UCAn**)`. A cell that is a link (`[Braking STPA](...)`) becomes a warning naming the linked page, not a UCA.
- **Scenarios and constraints**: in the first table of the section whose heading contains "Loss Scenarios": row
  number, the UCA or CA code at the start of column 1, Types from `Type (\d)`, causal factors (column 3), the
  beliefs (italic runs starting `Belief:`), and in column 4 every `CSTR\d+` with the text that follows it up to
  the next code or `and`; a constraint spelled out once and referenced elsewhere keeps the spelled-out text.
- Every object's `cite` names the page, the version, the section heading and the anchor URL.

The reader returns the plain dataset (`{analysis, losses, hazards, ucas, scenarios, constraints, warnings}`), the
factory loads it through the entity services so validation and the audit apply.

**Linking to a control structure** (`link --structure`): a UCA's `controller` text matched to `cs_controller.name`
and `key` case-insensitively, its `control_action` to `cs_signal.name` among the signals leaving that controller.
Exact matches apply; partial ones are reported with the candidates; nothing fuzzy is written without `--apply`.

### 7.4 Views

- **Excel**: six sheets (one per entity), the workbook's existing exporter.
- **Gutenberg**: an `stpa_report` document in the Generate screen's catalog: hazards; the UCA table by controller
  and category; scenarios with causal factors and constraints; every object with its citation; the review
  comments from the bundle as an appendix, since the bundle holds them.
- **Escher**: an `stpa_trace` diagram: hazards, UCAs, scenarios, constraints as four columns with edges; the
  attached control structure's controllers as swimlanes when linked.
- **The window**: an STPA screen in the control structures' pattern (list of analyses, the parts as tabs); a
  **Refresh from Confluence** button that runs `stpa refresh` and shows the report before `--apply`.

### 7.5 Tests and the public repo

asi_dewey is public and the Locator STPA is ASI-internal (`control-structure-plan.md`, section 1). The tests use a
**synthetic STPA page** in the exact Markdown shape the MCP server renders (the four sections, a context table
with the glued bold runs, struck cells, a duplicate note, a loss-scenario table with CA counterparts and CSTR
references), written by hand with neutral names, and a synthetic Hopper bundle around it. No real page text
enters the repo. One real run on the owner's machine against page 399343803 is recorded in the CHANGELOG as a
count (hazards, UCAs, scenarios, constraints found; warnings), never as content. Two days.

## 8. Phase E: the trace across the family

After D, this trace exists without any tool importing another:

```
Kletz plan row "STPA step 2"  --urls-->  Confluence page 399343803  <--source_page_id--  Dewey stpa_analysis
        |                                          |                                           |
     jira_key  --------------------->  HWL-2572 (STPA Step N work)                        stpa_uca UCA14
                                                                                               |
                                                                            cs_signal CA-07 of the structure
```

Hopper is the only process that reads Confluence; both tools hold page ids and URLs; the evidence bundles under
each tool's evidence folder prove what the page said when each tool looked. An agent asked "which deliverable
covers UCA14, is it on track, and has the page changed since the review" answers it with four read-only calls.

## 9. Risks and open questions for the owner

1. **Public repositories and the real STPA page.** Checked 2026-10-29 with `gh repo view`: asi_hopper, asi_dewey
   and asi_kletz are **public**; asi_standards is private. Hopper's Confluence fixtures (0.1.7: the Locator page
   body, cut, its children, its comments with the reviewers' words) and `evidence/locator-safety-function-stpa-
   2026-10-29/` (0.1.8: the full bodies of three STPA pages and ten comments) sit in the asi_hopper repo. The
   charter's rule ("a controlled document never enters a public repo, not even in history") and the
   control-structure plan's "the compactor STPA ... is ASI-internal" apply to them. Nothing STPA has been pushed:
   the last push was 0.1.5, and the 0.1.6 to 0.1.8 commits are local, so the fix is cheap today and a history
   rewrite on GitHub later. **Done 2026-10-29, before the push, under the charter's rule:** every Confluence
   fixture's page body, comment text, inline selection, search excerpt and other people's account ids were
   replaced by synthetic text of the same shape (ids, titles, versions, timestamps and structure kept; the
   synthetic STPA page has the four sections, the glued bold runs, a struck duplicate and a loss-scenario table,
   so Phases C and D can be tested on it); the real bundle stays on the owner's machine, git-ignored
   (`.gitignore`), with asi_standards as the place for it if the owner wants it versioned; the 0.1.7 and 0.1.8
   commits were rebuilt without the real text before the first push. The Jira fixtures pushed in 0.1.0 (HWL
   ticket summaries and one description) remain a smaller question of the same kind for the owner.
2. **Which pages.** The 0.20.0 placeholder stands on every row today. The STPA deliverables (step 1 outputs,
   steps 2 to 4 results) map to STPA pages the owner can name; the QMS-form deliverables (QF-12, HARA, FSC, TSC)
   may have no Confluence page at all, in which case the placeholder stays and `plan urls --audit` keeps saying
   so. That is a finding for the plan's owner, not a tool problem.
3. **Heading anchors.** The cloud editor's anchor form (`#Context-Table`) is checked against the live page in
   Phase C; if anchors are not stable, the citation falls back to the section hash, which the bundle carries.
4. **The Markdown rendering is the server's, not ours.** If Atlassian changes how tables are rendered, the reader
   breaks loudly (warnings, counts dropping to zero), which `refresh` surfaces before `--apply`. The bundle keeps
   the old text, so nothing is lost.
5. **Scale.** 97 pages in the STPA space; a snapshot is one call per page plus two per page with comments. A
   whole-space bundle is a few minutes and is never done on a timer.
6. **Confluence writes.** None, anywhere, in any phase. A finding that a page is wrong is a Jira comment written by
   a person, or a page comment written by a person.

## 10. Order of work

| Step | Repo and version | Effort | Depends on |
|---|---|---|---|
| A | asi_kletz 0.22.0: URL kinds, audit, replace | half a day | nothing |
| B | asi_kletz 0.23.0: `confluence` verbs, Find page, evidence per deliverable | one day | Hopper 0.1.8 (shipped) |
| C | asi_hopper 0.1.9: page anatomy, `--section`, section hashes in bundles | half a day | nothing |
| D | asi_dewey 0.10.0 (since moved to asi_kletz 0.24.0): STPA entities, factory, reader, `stpa` verb, views, screen | two days | C |
| E | one live run of each: Kletz links the STPA deliverables to their pages and takes evidence; Dewey reads page 399343803; counts in the CHANGELOGs | half a day | B, D |

A and C can run in parallel; B and D after them; E last. Nine working days of agent time at the family's usual
pace is pessimistic; the family lock (one primary tool at a time) makes B and D sequential on one machine for the
live runs only.

## 11. Acceptance

- A: `plan urls --audit` on the owner's database names every row still on the placeholder; `plan urls --replace`
  moves them all to a Confluence URL in one audited step; the export's Work product column reads the kind.
- B: a deliverable gets its STPA page through Find page; `confluence evidence` writes a bundle that
  `asi-hopper verify` accepts; `confluence check` reports the version of every linked page.
- C: `confluence page 399343803 --section "Context Table"` returns the table alone; the bundle entry lists four
  sections with hashes.
- D: `stpa new from_bundle --from evidence/locator-safety-function-stpa-2026-10-29 --name Locator` on the owner's
  machine yields 5 hazards, 28 UCAs (2 retired), 56 scenario rows and the constraints the page spells out, with
  warnings for the link cell and the `[H4]` reference; `stpa refresh` on an unchanged page reports nothing;
  the report and the trace diagram render; the tests pass on the synthetic page only.
- E: the charter's plans index row for this plan reads Implemented, and the trace of section 8 is demonstrated
  once end to end.

## Revision history

- 2026-10-29 Written, the day after Hopper 0.1.7 opened Confluence and the day 0.1.8 added page bundles. Revised
  the same day on the owner's correction "i said jama but meant confluence": Confluence URLs are the
  association; Jama is a footnote.
