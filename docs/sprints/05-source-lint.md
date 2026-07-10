# Sprint 5: Canvas-Facing Source Linting

Status: implemented and verified on 2026-07-10.

## Objective

Catch common Canvas-source mistakes before create or update commands reach a
dry-run or live mutation.

## Command Surface

```bash
danvas sources lint content/**/*.md
danvas sources lint --kind discussion --project-root .
danvas sources lint content/pages/resources.html --format json --output lint.json
```

The command is local-only and stdout-first. JSON output is explicit and no
network or Canvas authentication is used.

## Checks

Common checks:

- missing or unsupported front matter
- duplicate source title and body H1
- invalid, missing, or suspicious due/unlock/lock dates and timezone offsets
- broken local links, missing relative assets, and unsafe URL schemes
- duplicate headings or IDs
- metadata point totals that conflict with recognizable prose totals
- missing or conflicting local source-map provenance

Kind-specific checks:

- assignments: required assignment fields and contradictory submission settings
- announcements: unsupported assignment-only metadata
- discussions: repeated/excessive prompt headings and malformed seeded sections
- pages: unsafe HTML, document wrappers, scripts/stylesheets, missing or invalid
  `canvas_css` sidecars, compatibility-profile violations, publication/front-page
  contradictions, and fields outside the current Page contract

Heuristic findings such as prose point totals are warnings unless a rule can
establish a definite contradiction. Each finding includes rule ID, severity,
source path, line when available, and a concise remediation.

## Integration

- Exit 0 when no errors are found and 1 when errors exist; warnings alone do not
  fail by default.
- Support `--fail-on warning` for CI or stricter course workflows.
- Reuse the same validators inside source-backed create/update dry-runs where
  practical, but keep the standalone linter free of Canvas calls.
- Permit narrow rule suppression in source front matter with rule IDs and a
  reason; do not support broad global disablement in V1.

## Acceptance Criteria

- The linter accepts valid assignment, announcement, discussion, and Page
  fixtures and reports stable machine-readable rule IDs.
- It catches duplicate H1, missing asset, timezone, point-total, unsafe HTML, and
  Page publication contradictions.
- Glob expansion, mixed source kinds, warnings-only runs, strict mode, and
  suppressions are tested.
- Lint output never includes source-map private data or secret-bearing URLs.

## Deferred

- External HTTP link checking.
- General accessibility certification or prose/style grading.
- Automatic rewriting or fixing of authored source files.
