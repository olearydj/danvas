# danvas

`danvas` is a command-line tool for day-to-day Canvas course operations: rosters, assignments, submissions, grading, announcements, and discussions.

Status: early/internal tool. It is useful for real Canvas workflows, but command behavior may still change as course planning and audit workflows mature.

It is intentionally separate from archival/history tooling such as Canvas ledger databases.

## Functionality

- report course status
  - compares the `.danvas` course snapshot and local course sources in one read-only command
  - covers assignments, announcements, discussions, quiz shells, and files
  - classifies each item as exact, metadata mismatch, local-only, Canvas-only, filename-only match, or unsupported comparison
  - warns when the snapshot is stale
  - optional JSON output and Markdown report

- discover courses and rosters
  - list active Canvas courses visible to the authenticated user
  - export course rosters by course
  - roster format includes `CanvasID`, name, email, and SIS ID

- export assignments from Canvas by course
  - JSON, CSV, Markdown directory formats
  - full or concise payloads
  - includes assignment groups, points, dates, publication state, submission types, URLs, and descriptions

- audit Canvas assignment setup
  - compare Canvas assignment group weights to `course.yaml`
  - summarize assignments by group
  - identify unpublished assignments and missing due dates

- create assignments in Canvas
  - Markdown body with YAML (`---`) or TOML (`+++`) front matter
  - supports Canvas assignment metadata fields
  - dry-run mode to inspect payload before creating

- download submissions
  - assignment attachments
  - attached media
  - media comments
  - per-file metadata sidecars

- upload feedback
  - upload per-student feedback files as Canvas submission comments
  - match files to students by embedded Canvas user ID
  - dry-run mode to preview matched and unmatched files

- grade submissions
  - post grades from CSV
  - optional text comments from CSV
  - idempotent checks for existing grades/comments
  - verify Canvas grades/comments against CSV

- check and audit gradebook exports
  - parse Canvas gradebook CSVs with `Points Possible` rows
  - identify final score variants and assignment groups
  - summarize missing, `N/A`, and nonnumeric cells
  - reconstruct weighted totals from course policy and Canvas group scores

- grade discussions
  - export discussion posts by discussion URL
  - score discussions by original post count and response count
  - configurable points and caps
  - optional CSV output of scored rows
  - optional upload to graded discussion assignment

- export announcements
  - create announcements from Markdown with front matter
  - dry-run mode to inspect the Canvas discussion-topic payload before creating
  - course-level announcement bodies
  - optional JSON, CSV, or Markdown output
  - filters replies to the authenticated user by default, so student replies are excluded

- inventory course files
  - exports Canvas Files metadata to JSON and CSV without download URLs
  - optionally compares Canvas filenames and sizes to a local course root (`--local-root`)
  - writes a Markdown missing-file report for archive checks
  - downloads Canvas Files into a local folder tree with a manifest

- download Panopto captions
  - launches Panopto through the Canvas course navigation LTI tool
  - lists visible recording sessions and writes JSON/CSV manifests
  - downloads caption text exports when captions are available

- upload grades
  - assignment grades from CSV
  - discussion scores to the associated graded discussion assignment
  - optional submission comments
  - dry-run mode before live Canvas writes

- analyze Canvas quiz/survey exports
  - parse Classic Quiz / Survey student-analysis CSV files
  - discover question/score column pairs
  - summarize scores and selected answer counts

- import QTI quiz packages
  - imports a text2qti/QTI zip as a Classic Quiz via the Canvas content-migration API
  - polls the migration to completion and reports failures
  - applies quiz shell settings: dates, publish state, time limit, attempts, assignment group
  - verifies the resulting Canvas quiz settings and exits nonzero on mismatch
  - dry-run mode shows the package and settings before any Canvas write

## Installation

```bash
uv tool install -e .
```

For development inside the repository:

```bash
uv run danvas --help
```

Check the installed version:

```bash
danvas --version
```

## Authentication

`danvas` loads `.env` and can read a Canvas API token from either 1Password or an environment variable.

```bash
export CANVAS_API_KEY_OP_REFERENCE="op://Dev/Canvas/credential"
export CANVAS_API_KEY="fallback-token"
export CANVAS_API_URL="https://auburn.instructure.com/"
```

Common options are available on Canvas-backed commands:

```bash
--api-url
--secret-provider auto|1password|env
--op-reference
--api-key-env
```

`recordings panopto-captions` uses the Canvas token to launch the course Panopto
LTI tool; it does not require separate Panopto API client credentials.

## Project Configuration

Initialize a teaching project once to avoid repeating the Canvas course ID and
assignment group IDs:

```bash
danvas init 1742717
```

This writes:

```text
.danvas/config.toml
.danvas/course.json
```

`config.toml` is the human-readable project configuration. It stores stable,
non-secret defaults such as the Canvas base URL, course ID, course timezone, and
assignment group name-to-ID mappings. `course.json` is a generated Canvas
metadata snapshot for local lookup and comparison; it covers assignments,
assignment groups, files, announcements, discussions, quiz shells, and
group-category summaries, and it never stores download verifier URLs or student
data. If the project is a git repo, `danvas init` adds `.danvas/course.json` to
`.gitignore`.

Refresh the generated snapshot without changing Canvas; `--diff` summarizes what
changed since the previous snapshot:

```bash
danvas refresh
danvas refresh --diff
```

After initialization, Canvas-backed commands can omit `--course-id`; an explicit
`--course-id` still wins over the project config. Assignment Markdown can also
use an assignment group name:

```yaml
---
title: Case Study 1
assignment_group_name: Case Studies
points_possible: 100
---
```

Use `assignment_group_id` when you want to bypass project-local name resolution.

`danvas status` has default local-source conventions:

- `content/announcements/*.md`
- `content/discussions/*.md`
- `content/quizzes/chap*.md`
- `content/cases/*-assignment.md`

Override them per course in `.danvas/config.toml` when a teaching repo uses a
different layout:

```toml
[sources.assignments]
include = ["content/assignments/*.md", "content/cases/*-assignment.md"]
exclude = [
  "content/assignments/*-draft-notes.md",
  "content/assignments/*-starter-spec.md",
]
```

When custom assignment include patterns are configured, `danvas status` only
treats Markdown files with assignment metadata beyond `title`/`name` as
assignment sources. This keeps broad folders such as `content/assignments/` from
turning support notes into noisy local-only or unsupported status rows. Set
`require_assignment_metadata = false` in `[sources.assignments]` for a narrow
glob where every matched file should be reported, even when front matter is
missing.

`danvas status` warns when the snapshot is older than 24 hours. Override the
threshold per project with a `[status]` table in `config.toml`:

```toml
[status]
max_snapshot_age_hours = 72
```

## Examples

```bash
# Course status (read-only, from the .danvas snapshot)
danvas status
danvas status --output status.json --report-md status.md

# Courses and rosters
danvas courses --output courses.csv
danvas roster --course-id 1706414 --output roster.csv

# Assignments
danvas assignments export --course-id 1706414 --output assignments.json
danvas assignments export --course-id 1706414 --output assignments.csv
danvas assignments export --course-id 1706414 --output assignments-md --format markdown
danvas assignments create --course-id 1706414 assignments/hw1.md --dry-run
danvas assignments audit assignments-full.json --course-yaml course.yaml --output assignment-audit.json

# Submissions and feedback
danvas submissions media --course-id 1706414 --assignment-id 19413569 --output-dir downloads
danvas submissions feedback --course-id 1706414 --assignment-id 19413569 \
  --roster roster.csv --feedback-dir feedback --pattern "*-feedback.pdf" --dry-run

# Grades
danvas grades post --course-id 1706414 --assignment-id 19413569 --grades-csv grades.csv --dry-run
danvas grades verify --course-id 1706414 --assignment-id 19413569 --grades-csv grades.csv
danvas gradebook check final-canvas-gradebook.csv --course-yaml course.yaml
danvas gradebook audit final-canvas-gradebook.csv --course-yaml course.yaml \
  --assignments assignments-full.json --output gradebook-audit.json

# Quiz/survey exports
danvas quiz analysis student-analysis.csv --answer-term "which version" --answer-term comp \
  --output quiz-analysis.json

# Quiz import (Classic Quizzes via QTI)
danvas quiz import-qti chap07.zip --course-id 1742717 \
  --due-at 2026-06-20T04:59:00Z --publish --dry-run
danvas quiz import-qti chap07.zip --course-id 1742717 \
  --due-at 2026-06-20T04:59:00Z --publish --output quiz-import-report.json

# Discussions
danvas discussions export https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 \
  --output discussion.json
danvas discussions score https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 \
  2 2 3 2 --output discussion-scores.csv

# Announcements
danvas announcements create --course-id 1706414 announcements/welcome.md --dry-run
danvas announcements export --course-id 1655780 --output announcements.md

# Recordings
danvas recordings panopto-captions --course-id 1742717 \
  --folder-id b4e2a2bc-0b9f-439e-9095-b44e00f269c4 --dry-run
danvas recordings panopto-captions --course-id 1742717 \
  --folder-id b4e2a2bc-0b9f-439e-9095-b44e00f269c4 --output-dir panopto-captions
```

## CSV Formats

Roster exports include:

```text
CanvasID,Name,Email,SIS_ID
```

Grade uploads require `CanvasID` and `Grade`; `Name` and `Comment` are optional:

```text
CanvasID,Name,Grade,Comment
4024825,"Lawson, Jack",90,"Good work."
```

## Safety

Use `--dry-run` before commands that write to Canvas:

```bash
danvas assignments create ... --dry-run
danvas submissions feedback ... --dry-run
danvas grades post ... --dry-run
danvas discussions score ... --dry-run
danvas quiz import-qti ... --dry-run
danvas recordings panopto-captions ... --dry-run
```

`grades post` and comment posting check for already-present grades/comments before writing when possible.

Live Canvas writes print a `== Canvas write: ... ==` banner showing the course, target, and write counts before any change is made.

## Development

```bash
uv run ruff check .
uv run ty check
uv run pytest
uv run danvas --help
```

CI runs the same three checks on push and pull request.
