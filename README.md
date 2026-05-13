# danvas

`danvas` is a command-line tool for day-to-day Canvas course operations: rosters, assignments, submissions, grading, and discussions.

Status: early/internal tool. It is useful for real Canvas workflows, but command behavior may still change as course planning and audit workflows mature.

It is intentionally separate from archival/history tooling such as Canvas ledger databases.

## Functionality

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
  - Markdown body with TOML front matter
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

- upload grades
  - assignment grades from CSV
  - discussion scores to the associated graded discussion assignment
  - optional submission comments
  - dry-run mode before live Canvas writes

- analyze Canvas quiz/survey exports
  - parse Classic Quiz / Survey student-analysis CSV files
  - discover question/score column pairs
  - summarize scores and selected answer counts

## Installation

```bash
uv tool install -e .
```

For development inside the repository:

```bash
uv run danvas --help
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

## Examples

```bash
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

# Discussions
danvas discussions export https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 \
  --output discussion.json
danvas discussions score https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 \
  2 2 3 2 --output discussion-scores.csv
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
```

`grades post` and comment posting check for already-present grades/comments before writing when possible.

## Development

```bash
uv run python -m compileall src
uv run danvas --help
```
