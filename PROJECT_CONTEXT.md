# Project Context

## Purpose

`danvas` is an operational Canvas CLI for day-to-day course work: rosters,
assignments, submissions, grading, discussions, announcements, Canvas Pages,
files, recording captions, status reports, source linting, and local audit
workflows.

Keep `danvas` separate from archival/history tooling such as Canvas ledger
databases. It should produce useful operational evidence through reports,
manifests, and explicit outputs without becoming the long-term course-history
system.

## Documentation Map

- `README.md`: user-facing command overview, installation, examples, and safety
  notes.
- `docs/backlog.md`: current planning source, delivered baseline, sprint
  candidates, deferred items, and not-recommended directions.
- `docs/course-yaml.md`: narrow reference for the optional course policy YAML
  used by audit commands.
- `docs/sprints/`: lightweight implemented and planned feature contracts with
  explicit status and acceptance boundaries. Completed 0.6.0 specs remain useful
  implementation records; planned specs define only their named slices.
- `.ho/`: transient session handoffs. Read the latest relevant note for restart
  state, but do not treat handoffs as durable project documentation.

Older pre-0.6 sprint notes, the old upload spec, `design.md`, and `HANDOFF.md`
were removed after their useful content was consolidated. Use git history for
their full text.

## Source Map

- `src/danvas/cli.py`: Typer command surface.
- `src/danvas/auth.py`: Canvas API auth/client creation.
- `src/danvas/config.py`: `.danvas` config, course snapshots, and snapshot diffs.
- `src/danvas/reports.py`: report-run directories, manifests, and report
  discovery helpers.
- `src/danvas/authored_content.py`: shared field-policy, scalar, sequence, and
  timezone-aware datetime comparison primitives for authored Canvas content.
- `src/danvas/sanitize.py`: dependency-free sensitive-key, error-text, and
  retained-evidence sanitization shared across command families.
- `src/danvas/sources.py`: local course source discovery.
- `src/danvas/source_lint.py`: local Canvas-facing Markdown/HTML validation.
- `src/danvas/status.py`: read-only Canvas-vs-local status report.
- `src/danvas/assignments.py`, `announcements.py`, `discussion_sources.py`,
  `discussions.py`: course object operations and authored-source workflows.
- `src/danvas/snapshot_collections.py`: authority-aware Canvas snapshot
  collectors and collection-level availability metadata.
- `src/danvas/overrides.py`: redacted assignment override summaries and explicit
  private membership exports.
- `src/danvas/override_sync.py`: dry-run-first private assignment override
  reconciliation with guarded writes and readback verification.
- `src/danvas/pages.py`: Page listing/export/sync, rendering, restricted CSS,
  create/update, readback, status normalization, and verification workflows.
- `src/danvas/files.py`: Canvas Files inventory, targeted metadata compare,
  download, and upload.
- `src/danvas/quiz_import.py`, `quiz.py`: QTI import and quiz analysis.
- `src/danvas/gradebook.py`, `assignment_audit.py`, `grades.py`,
  `submissions.py`: grading and audit workflows.
- `src/danvas/grade_evidence.py`: private grade mutation receipts, outcome
  classification, recovery artifacts, and release-state evidence.
- `src/danvas/panopto.py`: Panopto caption discovery/download through Canvas LTI.
- `tests/`: pytest coverage and CLI command-surface checks.

## Release And Verification

`pyproject.toml` is the version source. `danvas --version` and
`danvas.__version__` read installed package metadata. Bump the minor version for
feature sprints or new commands, and the patch version for fixes.

Current tagged release: 0.12.0. Sprint 15 consolidates authored-content
comparison and datetime primitives, unifies sanitization, treats
`InvalidAccessToken` as credential-wide failure, and adds opt-in
`--require-complete` exit-3 signaling for partial snapshots. Repeated review
passes restored compatibility contracts and replaced example-fitted sanitizer
coverage with generated credential/prose matrices. Ruff, ty, `uv lock --check`,
529 tests, sprint-document Markdown lint, and isolated editable and wheel smoke
for 0.12.0 pass. A bounded sandbox acceptance confirmed section-inclusive
announcement readback.

The prior `v0.11.0` release delivered authored discussion create, verify, and
safe update after bounded disposable-topic Canvas acceptance. The preceding
0.10.x line delivered truthful grade mutation evidence, assignment release
verification, authorization-resilient snapshots, installed-artifact release
smoke, and the 0.10.2 assignment-alias/evidence hotfix. Versions 0.8.0, 0.9.0,
and 0.10.1 were development identifiers rather than tagged releases. The
user-level CLI remains on `danvas 0.11.0` until the verified 0.12.0 exact tag is
installed during release closeout.

Recommended local checks:

```bash
uv lock --check
.venv/bin/ruff check .
.venv/bin/ty check
.venv/bin/pytest
scripts/release-smoke.sh --expected-version X.Y.Z
```

Use one synchronized/frozen environment and run its executables directly; do not
launch concurrent syncing `uv run` commands against the shared `.venv`. CI runs
the lint, type, and test checks on push and pull request. Tag only the exact
release commit after its pushed CI is green, then verify tag CI and reinstall the
global CLI from that tag. When command behavior changes, update the repo docs and
the external Codex teaching skill docs:

- `/Users/djo/.codex/skills/teaching-danvas/SKILL.md`
- `/Users/djo/.codex/skills/teaching-danvas/references/danvas-commands.md`

## Durable Decisions

- Keep generated snapshots, reports, and manifests free of secrets, Canvas file
  verifier URLs, and student-sensitive data unless a command explicitly produces
  private output.
- Treat truthful evidence as a product invariant: every mutation attempt must
  appear exactly once with the intent that drove it, mutation status must remain
  distinct from evidence status, and indeterminate outcomes must instruct the
  operator to verify Canvas before retrying.
- Keep comparison behavior field-specific. Free-text titles and bodies must not
  receive numeric coercion; booleans use a closed vocabulary; datetimes compare
  semantically only through explicit policies. Every supported authored field
  needs structural policy coverage and round-trip characterization tests.
- Require `Z` or an explicit UTC offset for authored `*_at` timestamps. Assignment
  date aliases expand through the configured course timezone; Page
  `publish_at` may be date-only; graded discussion dates remain explicit-offset
  only because Canvas silently ignores date-only values.
- Use the shared sanitizer for public errors and retained evidence. Preserve
  compound credential-name detection and signed-cloud vocabulary, but keep
  colon-form `policy`/`expires` out of whole-grade-comment hashing because they
  collide with ordinary scheduling prose; the error sanitizer still redacts
  those forms. Alpha-only ambiguous colon/bare-Bearer payloads are an accepted
  grade-evidence detector limitation.
- Keep assignment snapshots and normal status output redacted and count-first.
  Full override membership, submission evidence, grades, and comments are
  explicit private outputs.
- `danvas status` stays read-only and stdout-first by default; saved report runs
  are opt-in for that command.
- Snapshot collection authority must remain explicit. `available` empty
  collections are authoritative; `unavailable`, `failed`, or `partial`
  collections cannot prove absence and must suppress deletion/drift claims.
  Default partial snapshots remain usable with warnings; `--require-complete`
  exits 3 according to each command's documented write timing. An
  `InvalidAccessToken` is fatal and must not replace prior state.
- Raw exports, rosters, submissions, grades, file downloads, and caption downloads
  should keep explicit output paths by default instead of becoming report runs.
- Report runs are operational evidence and should be collision-safe and
  append-only by default.
- Report runs classified as containing private student data must create their
  run directory and every artifact without group or other permissions, including
  interrupted runs and manifests.
- Keep `.danvas/` as generated operational state and evidence, not canonical
  authored course content. Snapshots, reports, manifests, reportable dry-runs,
  downloaded comparison caches, and explicit generated outputs may live there.
- Keep `content/` as authored instructional source. Source-sync commands may
  create missing files there only when explicitly pointed at a content output
  directory; they must not overwrite existing files by default.
- Use `.danvas/source-map.json` as the preferred future round-trip provenance
  sidecar for local source files. It may store stable Canvas IDs, stable Canvas
  URLs or paths, timestamps, command provenance, hashes, and safe comparable
  metadata, but not Canvas verifier/download URLs, tokens, roster data,
  submissions, grades, private comments, or full student content. Optional front
  matter IDs remain supported for course-specific sources.
- For creates, record returned Canvas identity before dependent writes or
  readback so a partial failure cannot produce an unbound orphan and duplicate
  on retry. Finalize provenance only after the documented verification boundary.
- Keep `grading/` for private grading workflow artifacts. Do not silently move
  grading evidence into `.danvas/reports/` unless the command is explicitly a
  private report/audit workflow.
- Use local-file-first gradebook and quiz audit behavior. Add live Canvas
  gradebook export only when a concrete workflow justifies the extra API and
  privacy surface.
- `danvas quiz analysis` analyzes Canvas student-analysis CSV exports. Source
  Markdown quiz analysis remains separate tooling unless explicitly consolidated.
- Keep the initial Canvas Pages workflow deliberately bounded: Markdown or native
  HTML rendering, restricted inline CSS, draft creation, bounded
  body/publication/declared-roles/scheduling update, and readback verification.
  Snapshot/status integration and one-way local source creation are delivered by
  Sprints 6 and 7; asset upload/rewriting, rename, deletion, front-page mutation,
  and general upsert remain future designs.
- Page snapshot/sync work canonicalizes stable Canvas links and blocks
  unresolved volatile or signed URLs before hashing or writing authored sources.
  Absolute links are Canvas-relative only when scheme, host, and port match the
  configured Canvas origin. The current Page hash profile is `pages-html-v4`;
  status requires a matching snapshot normalizer and otherwise requests refresh.
  The Markdown renderer is `pages-markdown-v2`: it adds explicit column scope
  only to simple tables generated from Markdown and leaves native HTML and raw
  HTML embedded in Markdown unchanged, preserving author intent and
  Canvas-to-local round-trip fidelity.
  Title-only Page matches are provisional collision evidence, never provenance,
  and must be unique among both local sources and Canvas Pages. Occupied sync
  targets with provenance for another Page are conflicts.
- Broad Canvas Files downloads treat Canvas path metadata as untrusted and
  enforce final resolved-path containment inside the selected output directory;
  overwrite permission never weakens containment.
- The PyPI distribution name `danvas` is occupied by an unrelated project. Any
  future PyPI publication needs a distinct distribution name; the Python import
  package and installed `danvas` command may keep their existing names.

## Report Output Contract

Classify every new command before implementation:

- `report-run-first`: audits, verification, reconciliation, comparisons, and
  dry-run/readback evidence. These commands should save a report run by default
  when a course project is discoverable.
- `explicit-output`: raw exports, rosters, submissions, grades, downloads, and
  captions. These should keep explicit output files or directories by default.
- `stdout-first`: quick inspection commands. Preserve existing terminal behavior
  and add report output only through explicit report options.

Report-run-first commands should normally support `--no-report`, `--report-root`,
`--report-dir`, and a command-specific slug. They should write `manifest.json`,
a command-specific JSON file, and a Markdown file when human review matters.

Compatibility-sensitive commands, such as `status` and `refresh --diff`, should
preserve default behavior and write report runs only when explicit report options
are passed.

Tests for report-producing commands should cover CLI option presence, default or
explicit report output behavior, legacy output compatibility, report option
conflicts, failed manifests when practical, and the absence of verifier URLs or
unmarked private student data.

Docs for command-surface changes should update `README.md`, relevant backlog
status, and the external teaching-danvas command reference. Update the main
teaching-danvas skill only when behavior changes agent defaults.

## Recurring Pitfalls

- Do not run multiple syncing `uv run` commands concurrently against the same
  project `.venv`; a session doing parallel Ruff/ty/pytest runs coincided with a
  partially installed `secretpath` package. Run one controlled `uv sync --locked`,
  then run verification sequentially, preferably with `uv run --no-sync` or the
  `.venv/bin/` executables.
- Typer/Rich `--help` output wraps differently in headless CI. Do not assert
  option flags against rendered help text; use the Click/Typer introspection
  helpers in `tests/test_cli.py`.
- Course repos can override local source discovery with `[sources.<kind>]` tables
  in `.danvas/config.toml`. Broad assignment globs require assignment metadata by
  default so support notes are not reported as local-only assignments.
- Folder-ID uploads must validate course ownership before uploading.
- Upload and report errors should sanitize Canvas payloads and exception text
  because either may include verifier-like or URL-bearing data.
- Shared-helper extraction is compatibility work, not a clean-slate rewrite.
  Pin surrounding legacy behavior before consolidating and use generated
  cross-product tests for vocabularies/policies where fixes can shift failures
  between under-redaction and over-redaction.
- Canvas discussion/announcement APIs use write-side `specific_sections`, but
  readback needs `include=["sections"]` and canonicalized section IDs. Do not
  compare the write parameter against a default-empty ordinary topic response.
