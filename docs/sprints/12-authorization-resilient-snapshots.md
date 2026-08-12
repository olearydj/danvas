# Sprint 12: Authorization-Resilient Partial Snapshots

Status: implemented, locally verified, accepted in a bounded read-only Canvas
field case on 2026-08-11, and released as `v0.10.0`.

## Objective

Allow `danvas init`, `danvas refresh`, `danvas refresh --diff`, and `danvas
status` to remain truthful and useful when Canvas permits the core course reads
but denies or fails an optional snapshot endpoint.

An inaccessible optional collection must never abort the whole snapshot,
silently become an authoritative empty list, or create false removal/local-only
claims. A failure in a required collection must still prevent replacement of a
previously trustworthy snapshot.

This sprint implements field-observed backlog item 9. It does not add retry
orchestration, expand the command surface, or turn snapshots into a general
archive format.

## Field Evidence

A bounded read-only check on 2026-08-11 used the same installed danvas 0.9.0
credentials against two courses:

- group-category enumeration for historical course 1685356 raised CanvasAPI
  `Forbidden`
- group-category enumeration for sandbox course 1576638 succeeded and returned
  an empty collection

This is sufficient to reproduce the operational problem and distinguish it
from a general authentication failure. It does not establish why the historical
course denies that endpoint, and the design must not encode a cause that Canvas
did not report.

The pre-sprint schema-v4 builder called every collection sequentially and
aborted on the first exception. Its lists alone could not distinguish
unavailable from empty, and both diff and status treated missing/falsy sections
as `[]`. A schema change was therefore warranted.

## Schema V5 Contract

Preserve the existing top-level collection arrays for straightforward consumers
and add explicit authority metadata:

```json
{
  "schema_version": 5,
  "snapshot_status": "partial",
  "group_categories": [],
  "collections": {
    "group_categories": {
      "status": "unavailable",
      "authoritative": false,
      "reason": "forbidden",
      "error_type": "Forbidden",
      "item_count": 0
    }
  }
}
```

Every declared snapshot collection receives exactly one state:

- `available`: the read completed and its list is authoritative; an empty list
  means Canvas authoritatively returned no items
- `unavailable`: Canvas denied access, initially CanvasAPI `Unauthorized` or
  `Forbidden`; its placeholder list is not authoritative
- `failed`: an operational read failed, including throttling, network/response
  failures, or another safely classified CanvasAPI failure; its placeholder
  list is not authoritative
- `partial`: a parent collection was read but one or more required nested reads
  failed; retained rows are useful but the section is not authoritative

`snapshot_status` is `complete` only when every collection is `available`; it is
`partial` otherwise. Collection metadata contains only allowlisted status,
reason, exception-class name, authority, and count fields. Never persist raw
exception text, response bodies, request URLs, headers, tokens, or signed URL
parameters.

Because Canvas documents rate limiting as a 429 response described as
`Forbidden`, exception classification must check CanvasAPI's
`RateLimitExceeded` before its `Forbidden` superclass. Throttling is `failed`,
not proof that the caller lacks permission.

## Required And Optional Collections

The first implementation uses an explicit registry rather than inferring
importance from call order.

Required foundation:

- course identity and ordinary course metadata
- assignment groups
- assignments, including assignment-group name resolution

Failure in a required read aborts `init` or `refresh`. If a prior snapshot
exists, its bytes remain unchanged.

Optional enrichments:

- folders and files, collected as one dependency-aware unit because trustworthy
  file paths depend on the folder inventory
- discussions
- announcements
- quizzes
- pages
- group categories and their nested groups

An optional gap produces a schema-v5 partial snapshot, a concise warning, and a
successful command exit because the core snapshot remains usable. The warning
names the collection, status, and bounded reason without raw server detail.

Sprint 15 preserves that default and adds `--require-complete` to `init`,
`refresh`, and `status`. Strict init/refresh exits `3` before writing or
replacing state; strict status writes requested evidence and then exits `3`.
Partial warnings are written to stderr, and report manifests derived from
partial evidence use status `partial`.

Sprint 15 also distinguishes `InvalidAccessToken` from endpoint-local
`Unauthorized`: an invalid token aborts collection at required, optional, and
nested boundaries, calls no later collectors, and cannot write or replace a
snapshot. `Forbidden` and endpoint-local `Unauthorized` retain the partial
snapshot behavior documented here.

Folders and files retain their two existing top-level arrays. If folder
enumeration is unavailable or failed, neither array is authoritative and file
collection is not attempted. If folders succeed but file enumeration fails,
folders may remain `available` while files receive the failure state.

## Nested Group-Category Semantics

Group-category listing and per-category group enumeration have distinct
authority:

- if the category list is denied, the section is `unavailable` with
  `group_categories: []`
- if the category list succeeds but any `category.get_groups()` call is denied
  or fails, retain the category rows and mark the section `partial`
- a row whose groups are unavailable uses `groups_status: unavailable` (or
  `failed`), `groups: []`, `group_count: null`, and `member_count: null`
- a successfully read category with no groups uses `groups_status: available`
  and zero counts

Unknown counts must be `null`, never zero. Per-category metadata follows the
same bounded reason/error policy as top-level collection metadata.

## Module Boundary

A new `src/danvas/snapshot_collections.py` module is warranted. The policy now
includes a collector registry, required/optional classification, dependency
handling, safe exception classification, nested partial results, and authority
metadata shared by build, diff, and status paths. Keeping that logic in
`config.py` would mix Canvas collection policy with CLI/config-file
orchestration.

The new module should own:

- immutable `CollectionSpec` and `CollectionResult` models
- the collection registry and dependencies
- CanvasAPI exception-to-bounded-reason classification
- collection execution and schema-v5 metadata construction
- specialized group-category nested-read handling

`config.py` remains responsible for command orchestration, composing the full
snapshot, atomic snapshot writes, and diff report rendering. `status.py`
consumes authority metadata rather than independently guessing availability.
Existing domain-specific normalization may remain in its current module when it
does not encode collection authority policy.

Catch and classify expected CanvasAPI/request failures at the optional
collection boundary. Do not catch `BaseException`, and do not convert local
programming or data-contract defects into a misleading authorization marker.

## Init And Refresh Behavior

`init` and `refresh` follow the same collection policy:

1. read the course and required collections
2. stop without writing if any required read fails
3. attempt each optional collection independently, respecting dependencies
4. compose one complete or explicitly partial schema-v5 snapshot
5. print a count-first summary and bounded warnings for non-available sections
6. write atomically only after composition succeeds

The existing atomic writer preserves the prior snapshot on a required failure.
Optional failures do not copy stale collection data forward: the new snapshot
contains a non-authoritative placeholder plus metadata, making freshness and
authority explicit.

## Diff Semantics

Schema-v5 diff is section-aware. For each section:

| Old state | New state | Comparison |
|---|---|---|
| `available` | `available` | Compare normally. |
| `available` | non-authoritative | `unavailable`; emit no added/removed/changed claims. |
| non-authoritative | `available` | `restored`; establish a new baseline without historical change claims. |
| non-authoritative | non-authoritative | `unavailable`; emit no change claims. |

`partial` is non-authoritative for whole-section diffing. Do not compare its
retained subset, because absent rows may simply be unreadable.

The diff payload records a per-section `comparison_status` plus old/new
collection status and bounded reason. Its top-level status is `success` only
when all selected sections are comparable and `partial` when any section is
skipped or restored. A partial diff can still contain trustworthy changes from
available/available sections.

The first schema-v4-to-v5 refresh retains the existing schema-mismatch behavior:
no cross-schema content diff is claimed. The newly written v5 snapshot becomes
the baseline for later section-aware diffs.

## Status Semantics

`danvas status` checks collection authority before comparing Canvas snapshot
rows with local sources:

- `available` sections preserve current comparison behavior
- `unavailable`, `failed`, and `partial` sections render an explicit unavailable
  summary with the bounded reason
- non-authoritative sections produce no Canvas-only, local-only, missing, or
  removed classifications
- group categories display `Unavailable (forbidden)` rather than `None` when
  the endpoint was denied

Machine-readable status output includes the snapshot's overall status and the
collection metadata needed to interpret skipped comparisons. Existing
schema-v3 Pages compatibility remains, but schema-v5 authority metadata takes
precedence whenever present.

Consumers that require a section for mutation planning must reject a
non-authoritative section with a clear next action rather than proceed from its
placeholder list. Read-only consumers may continue with independent available
sections.

## Output Safety

All snapshot, diff, status, terminal, and report outputs must exclude:

- access tokens and authorization headers
- raw request/response bodies
- raw exception strings
- verifier, signature, expiry, and signed-storage query values
- student/member identities introduced by nested group reads

Persist exception class names only from an allowlist and stable reason codes
such as `unauthorized`, `forbidden`, `rate_limited`, `network_error`,
`invalid_response`, or `collection_error`. Do not preserve Canvas's response
message merely because it accompanied a 401/403.

## Implementation Sequence

1. Add schema-v5 result models, safe exception classification, and collector
   registry in `snapshot_collections.py`.
2. Move snapshot collection behind required/optional execution boundaries while
   preserving successful schema-v4 field shapes in the v5 arrays.
3. Implement nested group-category partial results and null unknown counts.
4. Make init/refresh warnings and atomic-write behavior reflect authority.
5. Add section-aware diff comparison states and reports.
6. Make status and snapshot-dependent planners consume collection authority.
7. Update README, backlog, sprint index, CLI help where applicable, and the
   external teaching-danvas reference when behavior ships.
8. Run Ruff, ty, and the full pytest suite before bounded read-only field
   acceptance.

## Automated Acceptance

Tests must cover:

- group-category list `Forbidden` producing an otherwise usable partial snapshot
- nested `get_groups()` `Forbidden` retaining a category with null unknown
  counts and partial authority
- a successful empty group-category response remaining authoritative and empty
- `RateLimitExceeded` classified as `failed/rate_limited`, not `unavailable`
- required collection denial aborting without changing an existing snapshot
- independent optional failures not preventing other optional collections
- folder/file dependency behavior
- complete and partial init/refresh summaries and exit behavior
- the full diff-state table, including no false removals and restoration without
  historical change claims
- status suppressing local-only/Canvas-only conclusions for non-authoritative
  sections
- schema-v4-to-v5 first-refresh behavior
- active-course complete snapshots remaining behaviorally unchanged
- JSON, Markdown, terminal, manifest, and diagnostic output free of unsafe
  exception/URL/token data

Local verification on 2026-08-11: Ruff and ty passed, and all 395 tests passed.

Implementation added `src/danvas/snapshot_collections.py` for the collector
registry, required/optional policy, dependency handling, bounded exception
classification, and nested partial results. Snapshot writes now use the shared
atomic JSON writer so a required-read or local construction failure cannot
truncate or replace the previous snapshot.

## Field Acceptance

Use read-only operations only:

1. Initialize or refresh a temporary project for historical course 1685356 and
   confirm a structurally valid partial snapshot with group categories marked
   `unavailable/forbidden`.
2. Run status and confirm the section is unavailable rather than empty and no
   local-only/removal claim is emitted from it.
3. Run `refresh --diff` from an authoritative fixture or prior v5 baseline and
   confirm endpoint denial produces no removal claims.
4. Repeat against sandbox course 1576638 and confirm an available empty
   group-category collection and otherwise complete behavior.
5. Scan retained snapshots/reports for raw exception bodies, tokens, verifier
   values, signed URLs, and student/member identities.

No Canvas mutation is required or authorized by this field case.

### Field Acceptance Result

Passed on 2026-08-11 using the project development CLI and the same credentials
for both courses:

- `init` for historical course 1685356 completed with schema version 5,
  `snapshot_status: partial`, and only `group_categories` marked
  `unavailable/forbidden`
- `status` rendered `Group categories: unavailable (forbidden)` while continuing
  to compare authoritative sections
- a repeated live `refresh --diff` classified group categories as unavailable on
  both sides and explicitly emitted `no change claims`; no removal was reported
- `init` for sandbox course 1576638 completed with `snapshot_status: complete`
  and an authoritative empty group-category collection
- sandbox status rendered `Group categories: none`, preserving the distinction
  from endpoint denial
- retained snapshots, status outputs, and the refresh-diff report contained no
  access tokens, authorization headers, verifier/signed URL values, secure
  parameters, or student/member identity fields

All field operations were read-only against Canvas. The only writes were the
explicit temporary project snapshots and reports under `/private/tmp`.

## Exclusions

- retry/backoff orchestration or rate-limit scheduling
- token refresh or alternative authorization flows
- stale-data carry-forward or snapshot caching
- broad conversion of all danvas commands to partial-result semantics
- a new course-archive format or export command
- treating 404 as equivalent to authorization denial
- redesigning unrelated status output
- changing snapshot collection concurrency

## Definition Of Done

- `init` and `refresh` complete with an explicitly partial schema-v5 snapshot
  when an optional endpoint is forbidden.
- Required collection failure cannot overwrite the previous snapshot.
- Available empty, unavailable, failed, and nested-partial collections remain
  distinguishable in snapshot, diff, status, terminal, and report outputs.
- Diff and status make no deletion or local-only claim from a non-authoritative
  collection.
- Active-course snapshots preserve their current data shape and comparisons.
- Automated and bounded read-only field acceptance pass without retaining
  sensitive response or membership data.
- README, backlog, sprint index, CLI help where applicable, and the external
  teaching-danvas reference describe the shipped behavior when implementation
  lands.

## Primary References

- [Canvas Group Categories API](https://developerdocs.instructure.com/services/canvas/resources/group_categories)
- [Canvas Groups API](https://developerdocs.instructure.com/services/canvas/resources/groups)
- [Canvas API Throttling](https://developerdocs.instructure.com/services/canvas/basics/file.throttling)
