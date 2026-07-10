# Sprint 2: Override-Aware Assignment Snapshots And Status

Status: implemented and verified on 2026-07-10.

## Objective

Stop reporting false assignment drift when Canvas exposes an override-derived
top-level date. Represent assignment windows accurately while keeping student
membership out of normal snapshots and status output.

## Snapshot Contract

Bump `.danvas/course.json` from schema version 2 to version 3. Assignment rows
retain their current fields and add:

- `has_overrides`
- a redacted `all_dates` list containing window ID/title, `base`, due/unlock/lock
  times, and assignee count
- override IDs and titles when Canvas supplies them

Do not store student names, SIS IDs, Canvas user IDs, or raw override payloads in
the normal snapshot.

## Status Behavior

- When `all_dates` contains a base or "Everyone else" row, compare local source
  dates to that row instead of top-level assignment dates.
- Report override state separately from base assignment metadata.
- If Canvas has overrides and the source lacks `availability_overrides_ref`, show
  `Canvas has untracked assignment overrides` with counts only.
- If a reference exists, load its private file and classify overrides as exact,
  local-only, Canvas-only, metadata mismatch, or membership mismatch. Normal
  terminal output remains count-first.
- Version 2 snapshots retain the existing clear refusal path: status instructs
  the user to run `danvas refresh`, and refresh-diff reports a schema change.

## Explicit Private Export

```bash
danvas assignments overrides \
  --assignment-id 123 \
  --output grading/25-26.Su/assignment-overrides/case-study-1.yaml
```

This is an explicit-output command. It may include Canvas user IDs or SIS IDs,
but not names by default. It refuses overwrite unless explicitly requested and
labels the output private.

## Acceptance Criteria

- The observed base-date/extension-date case reports matching base metadata and
  a separate override notice rather than a generic due-date mismatch.
- Schema-version migration and refresh-diff behavior are tested.
- Snapshots and normal reports contain no override member identifiers.
- Private export includes stable override IDs, windows, and membership needed for
  later reconciliation.
- Status handles missing, malformed, and wrong-assignment override references
  without exposing private rows.

## Deferred

- Creating, updating, or deleting Canvas assignment overrides.
- Automatic reconciliation of override membership from the roster.
- Exam-specific multi-variant reconciliation.
