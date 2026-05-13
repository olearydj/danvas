# danvas

Unified operational Canvas CLI for course usage tasks: rosters, assignments, submissions, grades, and discussions.

This repo intentionally excludes archival ledger/history tooling. Keep durable course-history databases in `canvas-ledger` and CV import scripts; use `danvas` for day-to-day Canvas operations.

## Install

```bash
uv tool install -e .
```

## Authentication

The CLI loads `.env`, then resolves a Canvas token from 1Password or an environment variable.

```bash
export CANVAS_API_KEY_OP_REFERENCE="op://Dev/Canvas/credential"
export CANVAS_API_KEY="fallback-token"
export CANVAS_API_URL="https://auburn.instructure.com/"
```

Shared options are available on every command:

```bash
danvas <command> --api-url https://auburn.instructure.com/ --course-id 1706414
```

## Unified Interface

```bash
# Courses and rosters
danvas courses --output courses.csv
danvas roster --course-id 1706414 --output roster.csv

# Assignments
danvas assignments export --course-id 1706414 --output assignments.json
danvas assignments export --course-id 1706414 --output assignments-md --format markdown
danvas assignments create --course-id 1706414 assignments/hw1.md --dry-run

# Submissions and feedback
danvas submissions media --course-id 1706414 --assignment-id 19413569 --output-dir downloads
danvas submissions feedback --course-id 1706414 --assignment-id 19413569 --roster roster.csv --feedback-dir feedback --pattern "*-feedback.pdf" --dry-run

# Grades
danvas grades post --course-id 1706414 --assignment-id 19413569 --grades-csv grades.csv --dry-run
danvas grades verify --course-id 1706414 --assignment-id 19413569 --grades-csv grades.csv

# Discussions
danvas discussions export https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 --output discussion.json
danvas discussions score https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 2 2 3 2 --upload --dry-run
```

`grades.csv` accepts `CanvasID`, `Grade`, optional `Name`, and optional `Comment`. When `Comment` is present, `grades post` posts it as a submission comment and `grades verify` checks it.

## Source Inventory

Operational functionality found and consolidated:

| Source | Functionality | Consolidation |
| --- | --- | --- |
| `/casa/dev/canvas-upload` | Auth, roster export, feedback uploads, grade posting, assignment create/export | Directly folded into `danvas roster`, `danvas submissions feedback`, `danvas grades post`, `danvas assignments *` |
| `/casa/dev/canvas_api/get_assignment_media.py` | Download assignment submission attachments and media comments | Folded into `danvas submissions media` |
| `/casa/dev/canvas_api/get_discussions.py` | Export discussion posts, score participation, optionally post discussion grades/comments | Folded into `danvas discussions export` and `danvas discussions score` |
| `/casa/dev/canvas-commander/cc.py` | Interactive term/course/assignment browser | Replaced by non-interactive `danvas courses` and `danvas assignments export` |
| `/casa/au/teaching/INSY7740-PD2/.../post_project_grades_comments.py` | Course-local grades plus comments with verification | Generalized through optional `Comment` column in `danvas grades post/verify` |

Excluded archival/history functionality:

| Source | Reason |
| --- | --- |
| `/casa/dev/canvas-ledger` | Purpose-built local SQLite history ledger with annotations and drift tracking |
| `/casa/pub/cv/scripts/import_canvas_history.py` | CV/teaching-history import from ledger-style exports |
| `/casa/pub/cv/data/*canvas-history*` | Generated archival data, not operational Canvas interaction |

## Consolidation Proposal

Use `danvas` as the only operational Canvas command surface:

| Domain | Commands | Notes |
| --- | --- | --- |
| Discovery | `courses`, `roster` | Replaces interactive browsing and one-off roster scripts |
| Assignment setup/audit | `assignments create/export` | Keeps Markdown/TOML authoring and structured course export |
| Submission IO | `submissions media/feedback` | Separates downloads from feedback uploads |
| Gradebook updates | `grades post/verify` | Handles grades with optional text comments idempotently |
| Discussions | `discussions export/score` | Keeps discussion analytics operational, with optional grade upload |

Migration path:

1. Install `danvas` from this repo.
2. Stop adding new features to `canvas-upload` and ad-hoc `/casa/dev/canvas_api` scripts.
3. Move course-local grade/comment CSV workflows to `danvas grades post` using `Comment` columns.
4. Leave `canvas-ledger` and CV history scripts independent.
