# Handoff Note

## Danvas

Workspace: `/Volumes/Casa/dev/danvas`

GitHub repo: <https://github.com/olearydj/danvas>

Remote: `origin git@github.com:olearydj/danvas.git`

Branch: `main`

`danvas` is a unified operational Canvas CLI for course work. It handles rosters, assignments, submissions, grading, discussions, and local export audits. It is intentionally separate from archival/history tooling such as Canvas ledger databases and from report-specific scripts under teaching/report trees.

Important commits:

- `3ec191d Initial danvas CLI`
- `671d134 Clean up project metadata`
- `09365e9 Add Canvas audit commands`
- `23c985a Add audit command tests`
- `44c2d43 Split Canvas operations from CLI`
- `dbe8383 Add license and project status`

Useful verification commands:

```bash
uv run ruff check .
uv run ty check
uv run pytest
```

Latest checks: `ruff` clean, `ty` clean, and `96 passed` in pytest. GitHub Actions (`.github/workflows/ci.yml`) runs the same three checks on push and pull request.

Main files:

- `src/danvas/cli.py`: Typer command surface.
- `src/danvas/auth.py`: Canvas API auth/client creation.
- `src/danvas/config.py`: project-local `.danvas` config, course snapshots, and snapshot diffs.
- `src/danvas/sources.py`: local course source scanner (content/ conventions).
- `src/danvas/status.py`: read-only `danvas status` snapshot-vs-local report.
- `src/danvas/quiz_import.py`: QTI import, migration polling, and quiz verification.
- `src/danvas/courses.py`: courses/roster operations.
- `src/danvas/assignments.py`: assignment export/create operations.
- `src/danvas/announcements.py`: announcement create/export operations.
- `src/danvas/frontmatter.py`: shared Markdown front matter parsing for write commands.
- `src/danvas/submissions.py`: submission download/feedback upload operations.
- `src/danvas/grades.py`: grade post/verify operations.
- `src/danvas/discussions.py`: discussion export/score/upload operations.
- `src/danvas/gradebook.py`: Canvas gradebook CSV parsing/check/audit.
- `src/danvas/quiz.py`: Canvas Classic Quiz/Survey student-analysis CSV parsing.
- `src/danvas/assignment_audit.py`: assignment setup audit helpers.
- `src/danvas/files.py`: Canvas Files inventory/download operations.
- `src/danvas/panopto.py`: Panopto caption downloads via the Canvas LTI launch.
- `docs/course-yaml.md`: supported course policy YAML shape.
- `docs/backlog.md`: planned feature work and design notes.
- `docs/sprint-1.md`, `docs/sprint-2.md`, `docs/sprint-3.md`: sprint plans; sprint 1 is detailed, 2 and 3 are provisional.
- `tests/`: pytest coverage and Typer smoke tests.

Design decisions:

- `danvas` is for operational Canvas workflows.
- Keep Canvas ledger/history/archival tools separate.
- Keep 3010 report scripts standalone unless explicitly requested.
- Use local-file-first gradebook and quiz audit behavior.
- Live Canvas gradebook export/download support is a possible future feature, not implemented.
- `danvas quiz analysis` analyzes Canvas student-analysis CSV exports, not quiz source Markdown.

Optional future `danvas` work:

- Add more examples in `README.md`.
- Add comprehensive `danvas` activity logging so day-to-day Canvas interactions leave a durable operational history, without turning `danvas` into the archival ledger tool.
- Add live Canvas gradebook export/download support.
- Clean up remaining non-urgent `gradebook.py` complexity.
- Add `danvas discussions create` for Markdown-authored discussion topics, including graded discussion settings and the attached Canvas assignment payload. This should cover the workflow where `assignments create` is not enough because the Canvas object is a discussion topic with assignment metadata.
- Resolve assignment groups by name in write commands, for example `assignment_group_name: Introductions`, and fail clearly on missing or ambiguous matches. Creating a new group should require an explicit option rather than happening implicitly.
- Add `danvas files upload` and integrate it with Markdown-backed announcements, discussions, and assignments so local image references can be uploaded to Canvas Files and rewritten to Canvas file URLs before posting.
- Add update/upsert support for Canvas write commands, keyed by Canvas ID when present and by title only with explicit confirmation. Dry-run should show a useful before/after diff to avoid duplicate assignments, discussions, or announcements.
- Add a sidecar manifest or other round-trip metadata output for posted Canvas objects, including assignment IDs, discussion topic IDs, Canvas file IDs, and HTML URLs. Prefer keeping reusable Markdown clean unless course-specific IDs are intentionally stored in front matter.
- Improve due-date ergonomics for course workflows: support local course timezone, end-of-day defaults, and date-only front matter such as `due_date: 2026-05-29` instead of requiring UTC timestamps.
- Tag an initial version once the CLI stabilizes.

## Deprecated Canvas Tools

Old scripts were marked deprecated/noncanonical rather than removed.

Touched old locations:

- `/casa/dev/canvas-upload/README.md`
- `/casa/dev/canvas_api/DEPRECATED.md`
- `/casa/dev/canvas_api/get_assignment_media.py`
- `/casa/dev/canvas_api/get_discussions.py`
- `/casa/dev/canvas-commander/README.md`
- `/casa/dev/canvas-commander/cc.py`
- `/casa/au/teaching/INSY7740-PD2/grading/25-26.Sp/project/upload/post_project_grades_comments.py`

## Analyze-QTI And Make-QTI

This work happened outside the `danvas` repo.

Canonical scripts:

- `/Users/djo/.config/scripts/analyze-qti`
- `/Users/djo/.config/scripts/make-qti`

Executable symlinks:

- `/Users/djo/.local/bin/analyze-qti -> /Users/djo/.config/scripts/analyze-qti`
- `/Users/djo/.local/bin/make-qti -> /Users/djo/.config/scripts/make-qti`

Original course-local script:

- `/Volumes/Casa/au/teaching/INSY3010-PySQL/content/tests/25-26.Fa/analyze_quiz.py`

The course-local `analyze_quiz.py` is now a deprecated wrapper, not a symlink. It prints a deprecation notice and forwards arguments to `analyze-qti`.

`analyze-qti` purpose:

- Summarize text2qti-formatted quiz source Markdown.
- Report randomized `GROUP` structure.
- Report topics, categories, available questions, picked questions, selection rates, points, and optional expected student exposure.

`analyze-qti` implementation details:

- uv script shebang: `#!/usr/bin/env -S uv run --script`
- No external dependencies.
- Reads UTF-8.
- Preserves source topic/category order.
- Parses `Pick:` and `Points per question:` case-insensitively.
- Uses text2qti defaults of `1` for missing group options.
- Warns on `pick > available` and unterminated `GROUP`.
- Supports text output, `--json`, `--csv`, and `--students N`.

Example:

```bash
analyze-qti /Volumes/Casa/au/teaching/INSY3010-PySQL/content/tests/25-26.Fa/test1/test1-mc.md --students 67
```

Verified output reproduced original key totals for test1:

- `156` available
- `30` picked
- `60` points
- `19.2%` overall selection rate

`make-qti` purpose:

- Converts text2qti Markdown quiz source to Canvas QTI zip via `uvx text2qti`.
- Outputs to `~/Downloads` by default.

`make-qti` improvements made:

- Added `--output-dir DIR`.
- Added `--force`.
- Refuses to overwrite existing output unless `--force`.
- Fixed batch-mode counter bug under `set -e`.
- Avoids commenting Markdown headings inside fenced code blocks.
- Avoids `ls | awk` size parsing.
- Directory conversion exits nonzero if any conversion fails.

Verification performed:

```bash
analyze-qti --help
make-qti --help
uvx ruff check /Users/djo/.config/scripts/analyze-qti
bash -n /Users/djo/.config/scripts/make-qti
analyze-qti /Volumes/Casa/au/teaching/INSY3010-PySQL/content/tests/25-26.Fa/test1/test1-mc.md --students 67
analyze-qti /Volumes/Casa/au/teaching/INSY3010-PySQL/content/tests/25-26.Fa/test1/test1-mc.md --csv
make-qti --output-dir /var/folders/d3/2qdml55n4vd1lcrt4q_5dl3w0000gn/T/opencode/qti-test --force /Volumes/Casa/au/teaching/INSY3010-PySQL/content/tests/25-26.Fa/test1/test1-mc.md
```

## Search Notes

Investigated whether the original `analyze_quiz.py` had duplicates.

Findings:

- Only one exact tool was found: `/Volumes/Casa/au/teaching/INSY3010-PySQL/content/tests/25-26.Fa/analyze_quiz.py`.
- Closest related code: `/Volumes/Casa/dev/text2qti/text2qti/quiz.py`, which is parser/model infrastructure, not a stats CLI.
- Related but different: `/Volumes/Casa/dev/danvas/src/danvas/quiz.py`, which analyzes Canvas student-analysis CSV exports.
- Related but report-specific: `/Volumes/Casa/au/teaching/INSY3010-PySQL/reports/comp1220-python-impact/scripts/canvas_quiz_utils.py`.
- Related by domain only: `/Volumes/Casa/dev/utils/sc-grader/*` for Squarecap/in-class quiz grading.
- No relevant quiz/text2qti tooling was found under `/Volumes/Casa/pub`.

Important distinction:

- `analyze-qti` analyzes source Markdown before Canvas import.
- `danvas quiz analysis` analyzes Canvas student-analysis CSV after quiz/survey completion.
- Keep these separate unless explicitly asked to consolidate.
