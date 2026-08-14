# danvas Backlog

Last consolidated: 2026-08-14.

This document contains only work that remains to be done or reconsidered.
Released behavior belongs in `CHANGELOG.md`, migration guides, and the accepted
sprint records under `docs/sprints/`. Rejected directions and completed work are
kept in those records and in git history rather than repeated here.

There is no accepted Sprint 23 design. Feature priority should follow concrete
course-workflow demand.

## Current Priority Order

1. Add the Page asset adapter on top of the verified assignment asset
   transaction.
2. Add group-category, membership-import, verification, and local group-planning
   workflows for grouped cases.
3. Add section-aware roster data and report-first exam reconciliation.
4. Pull a smaller candidate forward only when field use justifies it.

The Page and grouped-case candidates were the named post-readiness priorities.
Their relative order may change when an actual course deadline makes one more
valuable.

## Candidate: Page Asset Deployment

### Page Asset Goal

Extend the existing Markdown-backed Page workflow so Pages can reference local
documents and images without ad hoc upload scripts or unstable Canvas URLs.

### Proposed Scope

- Reuse the Sprint 16 asset transaction rather than creating another upload,
  provenance, or retry engine.
- Add a Page-specific adapter to `pages create`, `pages update`, and
  `pages verify`.
- Detect local relative references before Canvas mutation and reject unresolved,
  ambiguous, unsafe, cross-course, or unsupported targets.
- Upload or safely reuse files only in an explicitly selected existing Canvas
  folder.
- Rewrite only the Canvas-bound HTML fragment; never modify authored Markdown.
- Record stable course/file identity immediately enough to make retries safe.
- Verify the final Page body by stable Canvas file IDs and course-relative links,
  without retaining signed or verifier-bearing URLs.
- Replace Page-specific link parsing with the shared `canvas_links` authority as
  part of the same reviewed change.

### Safety Boundary

- Omission plans; `--apply` authorizes Canvas mutation.
- No implicit folder creation, overwrite, deletion, remote fetching, or broad
  file synchronization.
- A file write that succeeds before Page mutation fails must leave exact
  evidence and a safe reuse path rather than encouraging blind retry.
- Page body readback remains the authoritative compatibility check.

### Page Asset Acceptance

- Generic document and image fixtures cover planning, upload, reuse, rewrite,
  readback, retry, and source immutability.
- A bounded disposable-course case verifies one Page with one document and one
  image, followed by exact-ID cleanup.
- Migration notes name any change in supported Page link detection.

### Later Asset Adapters

Announcement and discussion adapters may reuse the same transaction only after
the Page adapter establishes the shared integration boundary. Each adapter still
needs its own rendering and readback contract; they should not be bundled into
the first Page slice.

## Candidate: Groups And Grouped Cases

### Group Workflow Goal

Make grouped assignment setup reproducible from roster planning through Canvas
membership verification.

### Canvas Group Commands

Potential surface:

```bash
danvas groups categories --course-id 101
danvas groups categories rename --course-id 101 202 "Case 1 Groups"
danvas groups import --course-id 101 --category-id 202 groups.csv
danvas groups verify --course-id 101 --category-id 202 --expected groups.csv
```

Required behavior:

- List category IDs, names, self-signup settings, group counts, and membership
  counts.
- Create or rename categories only through explicit plan/`--apply` commands.
- Import Canvas-compatible membership CSVs into an explicit category.
- Poll Canvas progress objects with bounded timeouts and retained evidence.
- Verify group names and membership against the expected private CSV.
- Treat roster and membership artifacts as private by default and keep terminal
  output aggregate-only.

### Local Group Planner

Potential surface:

```bash
danvas groups plan \
  --roster .danvas/private/roster.csv \
  --group-size 4 \
  --balance-by Section \
  --rounds 3 \
  --output-dir .danvas/private/group-plans
```

The planner should remain local-only. It should support section-aware balancing,
minimize repeated pairings across rounds, emit Canvas-import-compatible CSVs,
and report unresolved rows, repeated pairings, and balance exceptions. Planning
must never mutate Canvas.

### Group Workflow Acceptance

- A disposable category can be planned, imported, read back, verified, and
  removed without direct Canvas API scripts.
- Progress failures and partial imports produce exact recovery evidence.
- The workflow can supply a verified `group_category_id` to an authored graded
  assignment without exposing membership in ordinary status output.

## Candidate: Section-Aware Exam Reconciliation

### Exam Reconciliation Goal

Reproduce multi-version exam accounting without direct Canvas scripts or manual
student-by-student spreadsheets.

### Roster And Override Foundations

- Add `SectionID`, `SectionName`, `EnrollmentState`, and `LastActivityAt` to the
  explicit private roster schema.
- Add section/enrollment snapshot data only if the reconciliation workflow
  needs it; preserve unavailable-versus-empty semantics.
- Extend local override-reference reconciliation so status can distinguish
  exact, local-only, Canvas-only, metadata mismatch, and membership mismatch
  without putting member identities in normal snapshots or stdout.

### Reconciliation Command

Potential surface:

```bash
danvas exams reconcile \
  --roster .danvas/private/roster.csv \
  --variant in_class:assignment_override:202 \
  --variant zoom:override_or_submission:204 \
  --variant proctoru:submission:203 \
  --upload-assignment 205 \
  --upload-window-minutes 15
```

The command should be read-only and report-first. Private Markdown, CSV, and JSON
evidence should identify accounted and unaccounted students, overlaps, variant
assignment, upload compliance, and late/missing uploads. It must preserve the
distinction between missing evidence, inaccessible Canvas data, and a confirmed
absence.

### Exam Reconciliation Acceptance

- A representative multi-version fixture reproduces the reconciliation result
  without Canvas mutation.
- A bounded read-only course case confirms section, override, submission, and
  roster shapes.
- Student-identifying outputs remain explicit private artifacts; stdout stays
  aggregate-only.

## Additional Page Work

These items are not part of the first asset-adapter slice. Pull them forward
individually when a concrete Page workflow needs them.

### Lifecycle Controls

- Design Page upsert only after stable-ID create/update behavior shows a field
  need.
- Treat title/slug rename as a separate explicit operation with link-impact
  diagnostics and stable-ID readback.
- Treat front-page mutation as its own guarded operation rather than silently
  widening `pages update`.
- Add broader Canvas compatibility profiles only when fixtures demonstrate a
  real institutional difference.

### Accessibility And Reflow

- Preserve authored table captions and accessible names when the selected
  Markdown profile supports them.
- Define and live-verify narrow-viewport behavior for tables, code blocks, and
  long unbroken tokens.
- Add determinate WCAG-oriented foreground/background contrast diagnostics to
  `pages css-check`, reporting unresolved Canvas-shell cases as manual review.
- Extend Page linting against rendered HTML for heading order, table-header
  associations, captions, link-label context, and overflow risk.
- Keep compatibility, accessibility diagnostics, and claims of full WCAG
  conformance explicitly separate.

### Optional Pandoc Profile

Consider a versioned Pandoc-flavored Markdown profile only if authors need
structural features unavailable in the conservative renderer. Any design must
pin Pandoc extensions and versions, produce Canvas-safe fragments, pass the same
element/attribute/style and asset validators, and record renderer provenance.
Quarto execution, JavaScript widgets, and full-document themes are not implied
by this candidate.

## Smaller Workflow Candidates

These should normally wait until repeated field use or one of the major
candidates provides a natural implementation boundary.

### External Link Checking

Add opt-in external HTTP checking to `sources lint` if broken remote links become
a recurring release problem. It needs bounded concurrency, timeouts, redirects,
offline behavior, and diagnostics that distinguish unavailable from invalid.
Automatic source rewriting is not part of this candidate.

### Source-Lint Title Policy

If the duplicate front-matter-title/body-H1 warning keeps producing false
positives, make it source-kind-aware or add a narrow explicit suppression. Do
not weaken the check globally: Page rendering already handles a matching title
H1 differently from other authored source kinds.

### Date-Only Comparison Semantics

Consider minute-semantic assignment date comparison only for date-only authored
fields if Canvas normalization continues producing harmless mismatches. Preserve
exact timestamp comparison for explicitly authored datetimes.

### QTI Assignment-Group Resolution

Allow `quiz import-qti` to resolve an assignment group by configured exact name
when a course workflow needs it. Planning must show the resolved stable ID and
reject missing or ambiguous matches before import.

### Explicit Canvas Folder Creation

Consider `files folders create` or an equally explicit operation. It must resolve
parent identity, path ambiguity, and readback before mutation. Upload and asset
commands must continue refusing to create folders implicitly.

### Office Package-Part Comparison

Optionally extend `files compare` with an explicit deep-inspection mode for
Office ZIP containers. Report added, missing, and changed package parts without
claiming semantic document equivalence.

### Release-Asset Status

If operators need whole-course release checks, add a narrowly configured audit
for local-only files in declared release-source directories. Do not turn
`status` into whole-tree file synchronization.

### Transcript Filing

Add an explicit local filing step after Panopto caption download if course
transcript workflows keep requiring manual moves. Preserve the original private
bundle and manifest; never write into authored transcript folders by default.

### Submission Replacement Provenance

Add a local-only helper if recovery from malformed Canvas downloads keeps
recurring. It should preserve the original file, copy an operator-selected
replacement, and update private provenance rather than silently replacing
grading evidence.

### Rubric Support

Consider a local rubric source plus read-only comparison first. Creation or
attachment would require plan/`--apply`, exact assignment identity, and
readback. Destructive rubric replacement is outside the initial candidate.

## Maintenance Triggers

### Python 3.15

The distribution currently declares `>=3.12,<3.15`. When Python 3.15 is
released, run an explicit compatibility review and add a green 3.15 CI lane
before changing the upper bound.

### Named Complexity Debt

Four functions remain the only allowed `C901` suppressions:

- `authored_content.comparable_value`;
- `page_sources.check_css`;
- `pages.build_pages_sync_plan`; and
- `status.compare_pages`.

Refactor them opportunistically when modifying the same behavior. Do not create
a complexity-only release, and do not add another suppression without a reviewed
architecture/test update.

## Backlog Hygiene

- Add an item only when it describes an unresolved user workflow, maintenance
  trigger, or decision that could plausibly lead to implementation.
- Include the evidence or trigger that would move a deferred item into active
  design.
- Move accepted implementation detail into a sprint design before coding.
- Remove an item once it ships or is rejected; rely on sprint records,
  migrations, the changelog, and git history for the durable account.
- Reorder the priority list after every completed sprint rather than preserving
  historical numbering.
