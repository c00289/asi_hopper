# Confluence sandbox, read only (2026-10-29)

**Owner's words:** "sandbox a test of what we can do with confluence just like we did with jira ... what can
we retrieve ... no writes at all for now but plan for them in the adapter".

**Scope:** every Confluence *read* tool of Atlassian's Remote MCP Server (`https://mcp.atlassian.com/v1/mcp`),
exercised through Hopper's own MCP client (`McpGateway`, OAuth 2.1 session of the owner's account, gateway
forced non-interactive so no browser could open) against `asirobots.atlassian.net`, with small, user-scoped
queries, every call under the gateway's own timeout. **No write tool was called**, not once, not with a test
page, not with a comment. The write side exists as a contract only (section 6).

**Auth state:** a session was stored in Windows Credential Manager from the owner's `asi-hopper auth login`
earlier the same day; the server honoured it for every call (no `AuthRequired`, no re-login). The stored
token's `scope` field is empty; the server still served Confluence, so the scopes are granted at consent
time and not echoed back.

**Calls made:** 1 tool inventory, 8 distinct Confluence read tools, plus `fetch`, `search` (Rovo) and
`getContentFormatGuide` once each to see what they return; two deliberate error cases (bad CQL, missing
page). Recordings were made with `asi-hopper --record` and curated into `tests/fixtures` (bodies
truncated, see the `note` of each `index.json` entry).

## 1. The server's inventory

`asi-hopper tools` (new in 0.1.7; `tools --product confluence --schema` for the schemas) lists 32 tools.
Confluence has 13: 8 reads the adapter uses, 1 read it does not need (the HTML authoring guide), 4 writes.
Two more reads touch Confluence without being Confluence tools: `fetch` (any Jira issue or Confluence
page by ARI) and `search` (Rovo, cross-product). The teamwork-graph tools that `getConfluencePage`'s own
description mentions (`getTeamworkGraphContext`, `getTeamworkGraphObject`) are **not** exposed to this
client at all, so "linked comments, child pages, shared users, page owners" through the graph is not
available from Hopper; child pages and comments come from the dedicated tools below.

Every tool takes `cloudId`; the site host (`asirobots.atlassian.net`) is accepted in place of the UUID, as
on the Jira side. The server does not annotate tools as read-only or destructive (no `annotations`), so
Hopper classifies them by name (`commands/confluence.py::classify_tool`).

## 2. What each read tool retrieves

| Tool | Arguments (required in bold) | Returns | Pagination | Body format | Verb |
|---|---|---|---|---|---|
| `getConfluenceSpaces` | **cloudId**, keys[], ids[], type (global/personal), status (current/archived), labels, favourite, start, limit (default 25, max 250), expand | `results[]` of `{id, key, name, type, status, homepageId, spaceOwnerId, authorId, createdAt, description, icon, _links.webui, currentActiveAlias}` + `_links.base` | `_links.next` carries a `cursor`, but the tool has no `cursor` argument and **`start` is ignored** (`limit=3` and `limit=3,start=3` return the same three spaces): one page of at most 250 spaces is the reach | none | `confluence spaces [KEY,KEY]` |
| `getPagesInConfluenceSpace` | **cloudId, spaceId** (numeric id, not the key), contentType (page/blog), limit (1-250), cursor, status, title, sort (`-modified-date` etc.), contentFormat (markdown/adf) | `results[]` of `{id, status, title, spaceId, parentId, parentType, authorId, ownerId, createdAt, version{number, message, authorId, createdAt}, body}` | `_links.next` with `cursor`; the adapter follows it with `--all` | every page comes **with its body** (markdown by default here); there is no "no body" option, so a page of 5 STPA pages was 22 KB | `confluence pages SPACE` |
| `getConfluencePage` | **cloudId, pageId** (id or tiny-link id), contentType, contentFormat (html/markdown/adf) | `{id, type, status, title, spaceId, parentId, parentType, authorId, ownerId, lastOwnerId, createdAt, version{...}, body}` | n/a | **markdown** (48 KB for the sample page, links kept, tables rendered), **adf** (a JSON `doc`, 214 KB, node types seen: heading, paragraph, table, panel, layoutSection, mediaSingle, extension, rule), **html** (96 KB, Confluence HTML+ with `data-type` layout nodes); omitted = markdown | `confluence page ID [--format]` |
| `getConfluencePageDescendants` | **cloudId, pageId**, limit (max 250), depth (max 10), cursor | `results[]` of `{id, status, title, parentId, depth, childPosition, type, lastModified}` | `_links.next` with `cursor` | no bodies | `confluence children ID [--depth]` |
| `searchConfluenceUsingCql` | **cloudId, cql**, cqlcontext, cursor, expand, limit (default 25, max 250), prev, next | `results[]` of `{content{id, type, status, title, ari, history{createdBy, createdDate}, extensions, _links}, title, excerpt, url, resultGlobalContainer{title, displayUrl}, breadcrumbs, entityType, lastModified, friendlyLastModified, score}` + `start, limit, size, totalSize, cqlQuery, searchDuration, archivedResultCount` | `_links.next` with `cursor` (`_t_...`); `totalSize` is the full count | excerpt only (first ~400 characters of text) | `confluence search [CQL] [--space KEY]` |
| `getConfluencePageFooterComments` | **cloudId, pageId**, contentType, limit, cursor, status, sort, contentFormat (markdown/adf), includeReplies, repliesPerComment (1-25) | `results[]` of `{id, status, title, authorId, createdAt, body}` (+ `replies[]` when asked) | `_links.next` with `cursor` | markdown or adf | `confluence comments ID [--kind footer]` |
| `getConfluencePageInlineComments` | as above plus resolutionStatus (open default / resolved / dangling / reopened) | as above plus `resolutionStatus` and `properties{inlineOriginalSelection, inlineMarkerRef}` (the page text the comment hangs on) | `_links.next` with `cursor` | markdown or adf | `confluence comments ID [--kind inline]` |
| `getConfluenceCommentChildren` | **cloudId, commentId, commentType** (footer/inline), limit, cursor, sort, contentFormat | `{cloudId, commentType, results[], _links}`; results shaped like the comment lists | `_links.next` with `cursor` | markdown or adf | `confluence replies ID --kind` |
| `fetch` | **id** (ARI `ari:cloud:confluence:{cloudId}:page/{id}`) | `{id, title, text, url, type: "confluence-page", metadata{cloudId, spaceId, authorId, createdAt, status, version}}` | n/a | one plain-text rendering (smart links as `<custom data-type="smartlink">`) | not used: `getConfluencePage` gives more |
| `search` (Rovo) | **query** | `results[]` of `{id (ARI), title, text, url, type, metadata{cloudId, searchScope}}`; 20 hits for "functional safety STPA" across STPA, FST and SE spaces | none seen | text snippet | not used: "may consume up to 10 Rovo Credits" a call and not user-scoped; see section 7 |
| `getContentFormatGuide` | **toolName** (createConfluencePage / updateConfluencePage), reference | `{toolName, source: "@atlassian/atlassian-html-format:html-format.md", body}` (23 KB of HTML authoring rules) | n/a | markdown text | not used: it exists for the write tools |

### Errors seen

- Bad CQL: `tool error: {"error":true,"message":"Search failed: 400 Bad Request ... Could not parse cql",
  "statusCode":400}`. The gateway raises `GatewayError`; the verb answers `ok: false` with that text.
- Missing page (`pageId = 1`): `... 404 Not Found ... Cannot find a page with id [1]`, the same way.
- No auth error occurred. Had the session been rejected the gateway would have raised `AuthRequired`
  ("no Atlassian session for this account; run `asi-hopper auth login` once"); a sibling surfaces that
  text and never opens a browser.

### Limits observed

- Timing: the first call of a process took 3-5 s (connection and token refresh), every later call 0.3-1.5 s.
- Sizes: a page body in ADF (214 KB) is the largest single answer; it fits the transport's default
  `max_event_mb = 16`. A list of 250 pages *with bodies* could not; the adapter's `pages` default is 25.
- `limit` caps at 250 on every list; the server's own default is 25 and the adapter uses the same.
- Rate: no 429 in ~30 calls at the gateway's 5 requests/second.

## 3. Examples (recorded; identifiers are the site's, people are not named)

`confluence spaces --limit 5`

```json
{"id": "16810795", "key": "VSP", "name": "Vehicle Software Platform", "type": "global", "status": "current",
 "homepage_id": "16810905", "url": "https://asirobots.atlassian.net/wiki/spaces/VSP"}
```

`confluence pages STPA --limit 5` (the key is resolved to id `5791547559` with one `getConfluenceSpaces` call)

```json
{"id": "262996144", "title": "V2X to VCU STPA (Old Format)", "status": "current", "type": "page",
 "space_id": "5791547559", "space_key": null, "parent_id": "5852037127", "depth": null,
 "last_modified": "2026-10-13T16:29:06.066Z", "excerpt": null,
 "url": "https://asirobots.atlassian.net/wiki/pages/viewpage.action?pageId=262996144"}
```

`confluence page 399343803` (markdown; `--format adf` returns the ADF document as `body`)

```json
{"id": "399343803", "title": "Locator Safety Function STPA", "status": "current", "type": "page",
 "space_id": "5791547559", "parent_id": "6051201086", "parent_type": "page",
 "author_id": "<account id>", "owner_id": "<account id>", "created": "2020-04-09T18:51:49.935Z",
 "updated": "2021-10-20T20:49:25.061Z", "version": 45, "version_message": null,
 "version_author_id": "<account id>", "body_format": "markdown",
 "body": "Related Links:\n\n[Top-level STPA](https://example.invalid/wiki/spaces/STPA/pages/100000001/Top-level+STPA) ..." (synthetic; the real body is ASI-internal),
 "url": "https://asirobots.atlassian.net/wiki/pages/viewpage.action?pageId=399343803"}
```

`confluence children 399343803`

```json
[{"id": "5763236170", "title": "Low-precision GPS loss scenario details", "depth": 1, "parent_id": "399343803", ...},
 {"id": "5779062840", "title": "Proximity Monitor Risk Scenarios", "depth": 1, "parent_id": "399343803", ...}]
```

`confluence search` with no CQL runs the user-scoped default `contributor = currentUser() AND type = page
ORDER BY lastmodified DESC` and says so in `warnings`; for the owner's account it finds **0** pages
(`totalSize: 0`): the account has not edited a Confluence page. `confluence search "type = page ORDER BY
lastmodified DESC" --space STPA --limit 3` finds 3 of `totalSize: 97`, with `space_key: "STPA"` and an
excerpt each. `lastmodified >= now("-30d")` site-wide found pages in MOBIUS, VTT and TD1.

`confluence comments 399343803` returns no footer comment and three open inline comments, each with the
sentence it is anchored on (`selection`), its `resolution` and a markdown `body`; `confluence replies
5351964709 --kind inline` returns none.

## 4. What the adapter offers (read only)

| Verb | Service | Records |
|---|---|---|
| `confluence spaces [KEYS]` | `ConfluenceService.spaces(keys, limit)` | `Space` |
| `confluence pages SPACE [--all] [--max N]` | `pages(space, ...)` (key or id) | `PageRef` |
| `confluence page ID [--format markdown/adf/html] [--raw]` | `page(id, content_format)` | `PageRecord` (`to_dict`, `to_row`) |
| `confluence children ID [--depth 1-10] [--all]` | `children(id, depth, ...)` | `PageRef` |
| `confluence search [CQL] [--space KEY] [--all] [--max N]` | `search(cql, space, ...)` | `PageRef` |
| `confluence comments ID [--kind footer/inline/all] [--replies]` | `comments(id, kind, replies)` | `PageComment` |
| `confluence replies ID --kind footer/inline` | `replies(id, kind)` | `PageComment` |
| `confluence snapshot IDS \| ID --depth N \| CQL [--space] [--comments] [--out] [--name] [--title]` (0.1.8) | `EvidenceService.snapshot_pages(PageSource, out_dir)` | a bundle: `pages.json`, `pages/<id>.md`, `pages.csv`, `pages.md`, `manifest.json` |
| `tools [--product] [--schema]` | gateway `LIST_TOOLS` | the inventory, classified |

Python: `hopper.page(id)`, `hopper.cql(cql, space=...)`, `hopper.confluence.<method>`; every verb answers a
`Result` (`ok, verb, data, errors, warnings`) exactly like the Jira verbs, so asi_kletz can consume it the
way it consumes `search` and `get`. Conventions carried over from JIRA Live Data: nothing connects until
the first call, a window calls these off its UI thread, the default query is scoped to the signed-in user,
every list is one page unless `--all`, and `--all` stops at 40 pages.

Recorded fixtures (`tests/fixtures`, `index.json` entries dated 2026-10-29): the inventory, spaces (first
page and by key), the STPA space's newest 5 pages, the sample page in all three formats (bodies cut), its
children, the default CQL (empty) and a space-scoped CQL, footer and inline comments, one comment's replies.
`tests/test_confluence.py` runs all of it offline.

## 5. Recommended read-only surface for the siblings

1. **asi_kletz**: `hopper.cql("title ~ '<deliverable>'", space="STPA")` to find the Confluence page that
   backs a Safety Plan deliverable; keep `PageRef.id` and `PageRef.url` on the row; `hopper.page(id)` only
   on demand (a detail pane), never in a list refresh, because every page carries its body.
2. **Evidence**: a `PageRecord` with `body_format = "markdown"` plus `version` and `updated` is a dated,
   hashable statement of what a page said. `confluence snapshot` (0.1.8) writes such bundles: pages by id,
   a page tree, or a CQL, with the Markdown bodies byte for byte and a manifest with every hash.
3. **Do not** use `search` (Rovo) from a tool: it spends credits per call and is not scoped to the user.
4. **Do not** rely on `getConfluenceSpaces` beyond 250 spaces: name the keys instead (`confluence spaces
   STPA,FST`), which is also what the key-to-id resolver does.

## 6. The write side: contract only

`gateway/api.py::ConfluenceWriteSide` is an abstract class with four documented signatures, one per write
tool: `create_page`, `update_page`, `create_footer_comment`, `create_inline_comment`. The only
implementation, `ClosedConfluenceWriteSide`, is what `ConfluenceApi.writes` holds; each method raises
`WriteSideClosed` ("... the Confluence write side is closed by owner decision (2026-10-29): Hopper reads
Confluence and never writes it") before inspecting an argument or touching the gateway.
`test_the_write_side_refuses_without_touching_the_gateway` asserts all four refuse, that the gateway's
call count does not move, that the contract cannot be instantiated, and that no verb is marked `writes`.
What a future write adapter would need, learned from the schemas: `createConfluencePage` wants
`spaceId` and a `body` in HTML (then `getContentFormatGuide` first) or markdown; `createConfluenceInlineComment`
wants the exact selected text, which occurrence, and the total count of occurrences on the page.

## 7. For the owner to decide

- ~~Whether Rovo `search` should be reachable at all.~~ Decided 2026-10-29: it stays in the inventory and out of the adapter.
- ~~Whether the proposal's decision 6 ("Confluence: out of scope, permanently for this tool", 2026-10-27)
  is superseded by this read-only surface living in Hopper.~~ Superseded by the owner on 2026-10-29:
  Confluence is in play, read only, inside Hopper (proposal decision 6, revised).
- ~~Whether a Confluence evidence bundle (section 5, item 2) is wanted.~~ Wanted; shipped as `confluence snapshot` in 0.1.8.
