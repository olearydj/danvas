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
- `src/danvas/sources.py`: local course source discovery.
- `src/danvas/source_lint.py`: local Canvas-facing Markdown/HTML validation.
- `src/danvas/status.py`: read-only Canvas-vs-local status report.
- `src/danvas/assignments.py`, `announcements.py`, `discussions.py`: course
  object operations.
- `src/danvas/overrides.py`: redacted assignment override summaries and explicit
  private membership exports.
- `src/danvas/pages.py`: Page listing/export/sync, rendering, restricted CSS,
  create/update, readback, status normalization, and verification workflows.
- `src/danvas/files.py`: Canvas Files inventory, targeted metadata compare,
  download, and upload.
- `src/danvas/quiz_import.py`, `quiz.py`: QTI import and quiz analysis.
- `src/danvas/gradebook.py`, `assignment_audit.py`, `grades.py`,
  `submissions.py`: grading and audit workflows.
- `src/danvas/panopto.py`: Panopto caption discovery/download through Canvas LTI.
- `tests/`: pytest coverage and CLI command-surface checks.

## Release And Verification

`pyproject.toml` is the version source. `danvas --version` and
`danvas.__version__` read installed package metadata. Bump the minor version for
feature sprints or new commands, and the patch version for fixes.

Current tagged release: 0.7.2. The annotated `v0.7.2` tag marks the verified
Page-comparison regression patch on top of the Sprint 8/9 audit-remediation
release. The 0.7.1 baseline implements private report
permissions, Canvas Files download containment, diagnostic sanitization, Page
diff/identity/update correctness, malformed-source isolation, and assignment
audit edge-case fixes. A final audit-cleanup pass adds Panopto timestamp
resilience, closes documentation drift, and replaces brittle/implicit tests.
The 0.7.2 patch normalizes Page `publish_at` comparisons, preserves duplicate
local-only Page classification when Canvas has no candidate, and prevents
invalid identity conflicts from reserving Canvas rows during status matching.
Ruff, ty, and all 320 tests pass locally and in CI. The global CLI is installed
from the tagged release.

Recommended local checks:

```bash
uv run ruff check .
uv run ty check
uv run pytest
```

CI runs the same checks on push and pull request. Tag releases only after the
pushed commit is green in CI. When command behavior changes, update the repo docs
and the external Codex teaching skill docs:

- `/Users/djo/.codex/skills/teaching-danvas/SKILL.md`
- `/Users/djo/.codex/skills/teaching-danvas/references/danvas-commands.md`

## Durable Decisions

- Keep generated snapshots, reports, and manifests free of secrets, Canvas file
  verifier URLs, and student-sensitive data unless a command explicitly produces
  private output.
- Keep assignment snapshots and normal status output redacted and count-first.
  Full override membership, submission evidence, grades, and comments are
  explicit private outputs.
- `danvas status` stays read-only and stdout-first by default; saved report runs
  are opt-in for that command.
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
- Keep `grading/` for private grading workflow artifacts. Do not silently move
  grading evidence into `.danvas/reports/` unless the command is explicitly a
  private report/audit workflow.
- Use local-file-first gradebook and quiz audit behavior. Add live Canvas
  gradebook export only when a concrete workflow justifies the extra API and
  privacy surface.
- `danvas quiz analysis` analyzes Canvas student-analysis CSV exports. Source
  Markdown quiz analysis remains separate tooling unless explicitly consolidated.
- Keep the initial Canvas Pages workflow deliberately bounded: Markdown or native
  HTML rendering, restricted inline CSS, draft creation, body/publication update,
  and readback verification. Snapshot/status integration and one-way local source
  creation are delivered by Sprints 6 and 7; asset upload/rewriting, rename,
  deletion, and general upsert remain future designs.
- Page snapshot/sync work canonicalizes stable Canvas links and blocks
  unresolved volatile or signed URLs before hashing or writing authored sources.
  Absolute links are Canvas-relative only when scheme, host, and port match the
  configured Canvas origin. The current Page hash profile is `pages-html-v4`;
  status requires a matching snapshot normalizer and otherwise requests refresh.
  Title-only Page matches are provisional collision evidence, never provenance,
  and must be unique among both local sources and Canvas Pages. Occupied sync
  targets with provenance for another Page are conflicts.
- Broad Canvas Files downloads treat Canvas path metadata as untrusted and
  enforce final resolved-path containment inside the selected output directory;
  overwrite permission never weakens containment.

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
`--report-dir`, and a command-specific slug. They should write `manifest.json`, a
command-specific JSON file, and a Markdown file when human review matters.

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

- Typer/Rich `--help` output wraps differently in headless CI. Do not assert
  option flags against rendered help text; use the Click/Typer introspection
  helpers in `tests/test_cli.py`.
- Course repos can override local source discovery with `[sources.<kind>]` tables
  in `.danvas/config.toml`. Broad assignment globs require assignment metadata by
  default so support notes are not reported as local-only assignments.
- Folder-ID uploads must validate course ownership before uploading.
- Upload and report errors should sanitize Canvas payloads and exception text
  because either may include verifier-like or URL-bearing data.
