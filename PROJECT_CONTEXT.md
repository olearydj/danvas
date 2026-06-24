# Project Context

## Purpose

`danvas` is an operational Canvas CLI for day-to-day course work: rosters,
assignments, submissions, grading, discussions, announcements, files, recording
captions, status reports, and local audit workflows.

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
- `.ho/`: transient session handoffs. Read the latest relevant note for restart
  state, but do not treat handoffs as durable project documentation.

Historical sprint notes, the old upload spec, `design.md`, and `HANDOFF.md` were
removed after their useful content was consolidated into this file and
`docs/backlog.md`. Use git history for the full old text.

## Source Map

- `src/danvas/cli.py`: Typer command surface.
- `src/danvas/auth.py`: Canvas API auth/client creation.
- `src/danvas/config.py`: `.danvas` config, course snapshots, and snapshot diffs.
- `src/danvas/reports.py`: report-run directories and manifests.
- `src/danvas/sources.py`: local course source discovery.
- `src/danvas/status.py`: read-only Canvas-vs-local status report.
- `src/danvas/assignments.py`, `announcements.py`, `discussions.py`: course
  object operations.
- `src/danvas/files.py`: Canvas Files inventory, download, and upload.
- `src/danvas/quiz_import.py`, `quiz.py`: QTI import and quiz analysis.
- `src/danvas/gradebook.py`, `assignment_audit.py`, `grades.py`,
  `submissions.py`: grading and audit workflows.
- `src/danvas/panopto.py`: Panopto caption discovery/download through Canvas LTI.
- `tests/`: pytest coverage and CLI command-surface checks.

## Release And Verification

`pyproject.toml` is the version source. `danvas --version` and
`danvas.__version__` read installed package metadata. Bump the minor version for
feature sprints or new commands, and the patch version for fixes.

Recommended local checks:

```bash
./.venv/bin/ruff check .
./.venv/bin/ty check
./.venv/bin/python -m pytest
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
- `danvas status` stays read-only and stdout-first by default; saved report runs
  are opt-in for that command.
- Raw exports, rosters, submissions, grades, file downloads, and caption downloads
  should keep explicit output paths by default instead of becoming report runs.
- Report runs are operational evidence and should be collision-safe and
  append-only by default.
- Use local-file-first gradebook and quiz audit behavior. Add live Canvas
  gradebook export only when a concrete workflow justifies the extra API and
  privacy surface.
- `danvas quiz analysis` analyzes Canvas student-analysis CSV exports. Source
  Markdown quiz analysis remains separate tooling unless explicitly consolidated.

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
