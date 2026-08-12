# danvas

`danvas` is a command-line tool for day-to-day Canvas course operations: rosters, assignments, submissions, grading, announcements, discussions, and Pages.

Status: early/internal tool. It is useful for real Canvas workflows, but command behavior may still change as course planning and audit workflows mature.

It is intentionally separate from archival/history tooling such as Canvas ledger databases.

## Functionality

- report course status
  - compares the `.danvas` course snapshot and local course sources in one read-only command
  - covers assignments, announcements, discussions, Pages, quiz shells, and files
  - classifies Pages by stable identity and normalized body hash; title-only candidates remain visibly unbound
  - classifies each item as exact, metadata/body mismatch, local-only, Canvas-only, filename-only match, probable unbound match, or unsupported comparison
  - warns when the snapshot is stale
  - optional JSON output and Markdown report

- discover courses and rosters
  - list active Canvas courses visible to the authenticated user
  - export course rosters by course
  - roster format includes `CanvasID`, name, Canvas login ID in the `Email` column, and SIS ID

- export assignments from Canvas by course
  - JSON, CSV, Markdown directory formats
  - concise or extended sanitized (`--full`) projections; raw Canvas payloads are never retained
  - includes assignment groups, points, dates, publication state, submission types, stable URLs, visible description text, and safe file-link evidence
  - exports private assignment-override membership separately while snapshots retain only redacted override summaries

- audit Canvas assignment setup
  - compare Canvas assignment group weights to `course.yaml`
  - summarize assignments by group
  - identify unpublished assignments and missing due dates
  - writes a dated report run by default in course projects

- create assignments in Canvas
  - Markdown body with YAML (`---`) or TOML (`+++`) front matter
  - supports Canvas assignment metadata fields
  - dry-run mode to inspect payload before creating
  - verify every declared supported field, exact embedded Canvas file IDs, and current-course file existence
  - distinguish complete matches from mismatches, partial coverage, and indeterminate reads

- download submissions
  - assignment attachments
  - attached media
  - media comments
  - per-file metadata sidecars
  - sanitized metadata/grade exports, stable manifests, SHA-256 hashes, and Office/ZIP integrity checks

- upload feedback
  - upload per-student feedback files as Canvas submission comments
  - match files to students by embedded Canvas user ID
  - dry-run mode to preview matched and unmatched files

- grade submissions
  - post grades from CSV
  - optional text comments from CSV
  - online baseline preflight, expected-current-grade checks, comment/delta checks, and automatic rollback artifacts
  - append or replace exact instructor-owned comments and safely clear targeted grades/comments
  - classify every live row from authoritative readback as verified, unchanged failure, partial, unverified, indeterminate, or not attempted
  - stop new writes after unsafe outcomes and emit guarded private recovery evidence when the final state is known
  - verify Canvas grades/comments against CSV and report targeted grade visibility from Canvas `posted_at` and assignment-visibility evidence
  - write private plan/result/verify report runs by default in course projects

- manage Canvas Pages
  - deterministic Markdown or native-HTML fragment rendering with stable heading anchors
  - accessible column-header semantics for simple Markdown-generated tables while preserving authored HTML tables unchanged
  - restricted `.canvas.css` validation and deterministic style inlining under a versioned compatibility profile
  - list/export, draft creation, bounded body/publication/roles/scheduling update, source-map provenance, and readback verification
  - schema-v5 authority-aware snapshot summaries and local-source status comparison without storing full Page bodies
  - canonicalizes stable links only on the configured Canvas origin and blocks unresolved signed/verifier URLs before hashing
  - safely syncs missing Canvas Pages to Markdown or native HTML without overwriting authored sources
  - targeted HTML/Markdown export with normalized-body and anchor round-trip checks

- lint Canvas-facing local sources
  - assignment, announcement, discussion, and Page validation without Canvas access
  - rejects ambiguous offset-free authored timestamps before Canvas access
  - stable rule IDs, narrow documented suppressions, JSON output, and warning-strict CI mode

- check and audit gradebook exports
  - parse Canvas gradebook CSVs with `Points Possible` rows
  - identify final score variants and assignment groups
  - summarize missing, `N/A`, and nonnumeric cells
  - reconstruct weighted totals from course policy and Canvas group scores

- grade discussions
  - export discussion posts by discussion URL
  - sync missing Canvas discussion prompts into local Markdown sources without overwriting
  - score discussions by original post count and response count
  - configurable points and caps
  - optional CSV output of scored rows
  - optional upload to graded discussion assignment

- export announcements
  - create announcements from Markdown with front matter
  - dry-run mode to inspect the Canvas discussion-topic payload before creating
  - export the latest Canvas announcement as Markdown or JSON
  - sync missing Canvas announcements into local Markdown sources without overwriting
  - verify one local announcement source against Canvas by stable ID
  - update one existing Canvas announcement from Markdown after a dry-run diff
  - course-level announcement bodies
  - optional JSON, CSV, or Markdown output
  - filters replies to the authenticated user by default, so student replies are excluded

- inventory, compare, upload, and download course files
  - exports Canvas Files metadata to JSON and CSV without download URLs
  - optionally compares Canvas filenames and sizes to a local course root (`--local-root`)
  - writes a dated report run with JSON, CSV, manifest, and Markdown missing-file report by default
  - compares one Canvas file's metadata to one local file by file ID or exact Canvas path
  - can compare SHA-256 checksums against a supplied downloaded Canvas file
  - downloads exactly one Canvas file to an explicit output path
  - upload dry-runs classify `would_create`, `would_overwrite`, `would_rename`, or conflict from one destination listing
  - live uploads return the final Canvas ID/path and a generated stable course-file URL without retaining download/verifier URLs
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

## Command Tree

```text
danvas
├── init
├── refresh
├── status
├── courses
├── roster
├── auth
│   └── doctor
├── assignments
│   ├── export
│   ├── overrides
│   ├── overrides-sync
│   ├── create
│   ├── verify
│   ├── update
│   ├── upsert
│   └── audit
├── gradebook
│   ├── check
│   └── audit
├── quiz
│   ├── analysis
│   └── import-qti
├── submissions
│   ├── export
│   ├── grades
│   ├── media
│   └── feedback
├── grades
│   ├── post
│   ├── clear
│   ├── comments
│   └── verify
├── discussions
│   ├── export
│   ├── create
│   ├── verify
│   ├── update
│   ├── sync-prompts
│   └── score
├── announcements
│   ├── create
│   ├── export
│   ├── latest
│   ├── sync
│   ├── update
│   └── verify
├── pages
│   ├── list
│   ├── export
│   ├── sync
│   ├── render
│   ├── css-check
│   ├── create
│   ├── update
│   └── verify
├── sources
│   └── lint
├── files
│   ├── inventory
│   ├── download
│   ├── download-one
│   ├── compare
│   └── upload
├── reports
│   ├── list
│   └── latest
└── recordings
    └── panopto-captions
```

## Installation

For editable development from a trusted checkout:

```bash
uv tool install --force --editable .
```

For repository-local development without changing the installed tool:

```bash
uv run danvas --help
```

Before a release, build and verify separate editable and wheel installations in
temporary uv tool directories:

```bash
scripts/release-smoke.sh
scripts/release-smoke.sh --expected-version 0.12.0
```

The smoke script honors normal uv configuration and freshness rules, never
contacts Canvas, and never changes the global danvas installation.

Install the latest exact tagged release:

```bash
uv tool install --force --upgrade --reinstall \
  "danvas @ git+ssh://git@github.com/olearydj/danvas.git@v0.11.0"
```

Verify the installed environment outside the checkout:

```bash
uv tool list
danvas --version
danvas --help
danvas auth doctor
```

If danvas fails before command parsing, `auth doctor` cannot start either. Use
`uv tool list` to inspect the installed version/source, then upgrade/reinstall
from the exact tag and repeat all startup checks. `--force` alone may exit 0
while retaining the older same-package tool environment. If a machine-wide uv
`exclude-newer` cutoff predates a required release artifact, keep the global
policy unchanged and use an explicitly audited cutoff for this install command
only:

```bash
uv tool install --force --upgrade --reinstall \
  --exclude-newer YYYY-MM-DDTHH:MM:SSZ \
  "danvas @ git+ssh://git@github.com/olearydj/danvas.git@v0.11.0"
```

Do not remove or loosen the global cutoff merely to make resolution succeed.
Confirm that the selected cutoff includes the tagged release and its required
dependencies.

## Authentication

`danvas` uses the shared `secretpath` name `canvas`. On this machine the normal
path is declared in `~/.config/secretpath/config.toml`; `.env` and command-line
overrides are still supported.

```bash
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

Inspect authentication setup without printing tokens:

```bash
danvas auth doctor
danvas auth doctor --check-canvas
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
group-category summaries, plus Page metadata and normalized body hashes. Snapshot
schema version 5 records whether each collection is authoritative, unavailable,
failed, or partial. Optional endpoint failures leave an explicitly partial but
usable snapshot; `refresh --diff` and `status` do not claim removals or
local/Canvas drift from non-authoritative collections. Required assignment and
assignment-group reads still fail without replacing the previous snapshot. An
`InvalidAccessToken` from any top-level or nested collection stops collection,
exits nonzero, and does not write or replace snapshot state.
Snapshots never store Page bodies, download verifier URLs, raw Canvas error
responses, or student data. Page hashing also ignores non-authorable account stylesheet/script
decorators that Canvas injects around API readback while continuing to reject
those elements in authored Page sources. Absolute links become Canvas-relative
only when their origin matches the configured Canvas origin. Status requests a
refresh instead of comparing Page hashes produced by an older normalizer. If the
project is a git repo, `danvas init` adds `.danvas/course.json` to `.gitignore`.

Refresh the generated snapshot without changing Canvas; `--diff` summarizes what
changed since the previous snapshot:

```bash
danvas refresh
danvas refresh --diff
danvas refresh --diff --report-root .danvas/reports
danvas refresh --require-complete
```

Optional collection gaps still exit zero by default and print bounded warnings
to stderr. Automation can pass `--require-complete` to `init`, `refresh`, or
`status`. Strict init/refresh exits `3` before writing project or snapshot state;
strict status writes requested evidence and then exits `3`. Report manifests
derived from partial evidence use status `partial`.

The first refresh from schema 4 to schema 5 reports a schema change instead of
making cross-schema change claims. Later schema-v5 diffs compare authoritative
sections independently and label unavailable or newly restored sections without
inventing additions or removals.

After initialization, Canvas-backed commands can omit `--course-id`; an explicit
`--course-id` still wins over the project config. Assignment Markdown can also
use an assignment group name:

```yaml
---
title: Case Study 1
assignment_group_name: Case Studies
points_possible: 100
due_date: 2026-05-29
---
```

Use `assignment_group_id` when you want to bypass project-local name resolution.
Date-only assignment fields `due_date`, `unlock_date`, and `lock_date` expand to
Canvas `*_at` datetimes using the course timezone in `.danvas/config.toml`.
`due_date` and `lock_date` use 23:59; `unlock_date` uses 00:00. Use explicit
`due_at`, `unlock_at`, or `lock_at` with `Z` or an explicit UTC offset when a
different time is needed. Offset-free timestamps are rejected before Canvas
access. Announcement and discussion scheduling fields use the same aware-time
requirement; Page `publish_at` additionally accepts a date-only value.

`danvas status` has default local-source conventions:

- `content/announcements/*.md`
- `content/discussions/*.md`
- `content/quizzes/chap*.md`
- `content/cases/*-assignment.md`
- `content/pages/*.md` and `content/pages/*.html` (excluding `*-preview.html`)

Override them per course in `.danvas/config.toml` when a teaching repo uses a
different layout:

```toml
[sources.assignments]
include = ["content/assignments/*.md", "content/cases/*-assignment.md"]
exclude = [
  "content/assignments/*-draft-notes.md",
  "content/assignments/*-starter-spec.md",
]

[sources.pages]
include = ["content/pages/*.md", "content/pages/*.html"]
exclude = ["content/pages/*-preview.html"]
```

When custom assignment include patterns are configured, `danvas status` only
treats Markdown files with assignment metadata beyond `title`/`name` as
assignment sources. This keeps broad folders such as `content/assignments/` from
turning support notes into noisy local-only or unsupported status rows. Set
`require_assignment_metadata = false` in `[sources.assignments]` for a narrow
glob where every matched file should be reported, even when front matter is
missing.

`danvas files inventory --local-root .` excludes generated/cache paths such as
`.danvas/`, `_archive/`, `_inventory/`, hidden files, and common generated report
filenames by default. Add project-specific local-scan ignores in
`.danvas/config.toml` when a course repo has additional scratch or rendered
outputs:

```toml
[files.inventory]
ignore = [
  "scratch/**",
  "rendered/**",
  "content/slides/*.html",
]
```

`danvas status` warns when the snapshot is older than 24 hours. Override the
threshold per project with a `[status]` table in `config.toml`:

```toml
[status]
max_snapshot_age_hours = 72
```

## Source Map

Live assignment create/update, announcement update, discussion update, and Page
create/update workflows write generated provenance to `.danvas/source-map.json`
after Canvas readback succeeds. Discussion create records the returned topic ID
immediately, before seeded replies or readback, so a partial failure cannot be
retried as a duplicate; complete provenance replaces that recovery identity
after successful readback. Page sync writes
provenance after verified local source creation and can recover a missing entry
after an interrupted provenance write.
The source map links project-relative authored source paths to Canvas object IDs
and stores safe comparable metadata plus body hashes. It does not store Canvas
API tokens, verifier/download URLs, roster data, submissions, grades, private
comments, or full student content. Dry-runs and read-only verification commands
may read the source map but do not update it.

## Authored Discussions

Discussion Markdown uses front matter for topic and optional graded-assignment
metadata. Put each instructor seed reply after a `--- reply ---` line:

```markdown
---
title: Unit 4 Discussion
published: false
points_possible: 10
assignment_group_name: Discussions
due_at: 2026-09-01T04:59:00Z
---

Discuss the unit.

--- reply ---

## Prompt One

Start with evidence.
```

Dry-run creation first. A source containing reply sections requires the explicit
`--seed-replies` confirmation. Create refuses sources already bound by front
matter or the source map. Live creation records the returned topic ID before
seed posting, then reads the topic, linked assignment, and returned seed-entry
IDs back before completing source-map provenance. Verify and update resolve only
by `--discussion-id`, `canvas_id` front matter, or the source map; they never
title-match. Discussion timestamps require `Z` or an explicit UTC offset;
timezone-equivalent values compare semantically. If stable seed entry IDs are
unavailable, verification prints and records that seed headings/count were not
checked. `discussions
update --body-only` updates only the root topic message and never deletes,
reorders, edits, or reposts instructor or student entries.

## Report Runs

Report-first commands such as assignment audits, file inventories, file
comparisons, gradebook checks/audits, grade post/clear/verify, quiz analyses,
source sync, verification, and update dry-run/readback workflows write dated run directories under
`.danvas/reports/` by default when a course project is available:

```text
.danvas/reports/YYYY-MM-DD-NNN-command-slug/
  manifest.json
  command-output.json
  command-output.md
```

The date prefix uses the course timezone from `.danvas/config.toml` when present,
then falls back to the system local date. `danvas init` adds `.danvas/reports/` to
`.gitignore` in git repositories.

Report runs classified with `may_contain_private_student_data: true`, including
grade post/clear/verify, gradebook checks/audits, and quiz analyses, create their
run directory and every artifact without group or other permissions. This
protection applies to default and explicitly selected report directories.

Use `--output`, `--report-md`, or `--output-dir` when you need a specific legacy
path. Use `--report-root` to choose a different root while keeping the dated run
directory, `--report-dir` to create one exact report directory, and `--no-report`
to suppress default report output where the command supports it.

Inspect saved report runs locally:

```bash
danvas reports list
danvas reports latest
danvas reports latest status
danvas reports latest files-inventory
```

`reports list` includes report directories with missing or invalid manifests and
labels them. `reports latest` returns the newest valid manifest, optionally
filtered by report slug. Both commands support `--report-root` for a nonstandard
reports directory and `--output` for JSON output.

## Examples

```bash
# Course status (read-only, from the .danvas snapshot)
danvas status
danvas refresh --diff --report-root .danvas/reports
danvas status --report-root .danvas/reports
danvas status --output status.json --report-md status.md

# Courses and rosters
danvas courses --output courses.csv
danvas roster --course-id 1706414 --output roster.csv

# Assignments
danvas assignments export --course-id 1706414 --output assignments.json
danvas assignments export --course-id 1706414 --output assignments-full.json --full
danvas assignments export --course-id 1706414 --output assignments.csv
danvas assignments export --course-id 1706414 --output assignments-md --format markdown
danvas assignments create --course-id 1706414 assignments/hw1.md --dry-run
danvas assignments verify --course-id 1706414 assignments/hw1.md
danvas assignments update --course-id 1706414 assignments/hw1.md --dry-run
danvas assignments upsert --course-id 1706414 assignments/hw1.md --dry-run
danvas assignments upsert --course-id 1706414 assignments/hw1.md --confirm update
danvas assignments audit assignments-full.json --course-yaml course.yaml
danvas assignments overrides --course-id 1706414 --assignment-id 19413569 \
  --output .danvas/private/assignment-overrides.yaml
danvas assignments overrides-sync --course-id 1706414 assignments/hw1.md
danvas assignments overrides-sync --course-id 1706414 assignments/hw1.md \
  --live --confirm apply

# Submissions and feedback
danvas submissions export --course-id 1706414 --assignment-id 19413569 \
  --output .danvas/private/submissions.json
danvas submissions grades --course-id 1706414 --assignment-id 19413569 \
  --output .danvas/private/grades.csv
danvas submissions media --course-id 1706414 --assignment-id 19413569 --output-dir downloads
danvas submissions feedback --course-id 1706414 --assignment-id 19413569 \
  --roster roster.csv --feedback-dir feedback --pattern "*-feedback.pdf" --dry-run

# Grades
danvas grades post --course-id 1706414 --assignment-id 19413569 --grades-csv grades.csv --dry-run
danvas grades comments --course-id 1706414 --assignment-id 19413569 --canvas-id 4024825
danvas grades clear --course-id 1706414 --assignment-id 19413569 --grades-csv rollback.csv --dry-run
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
danvas discussions sync-prompts --course-id 1655780 --output-dir content/discussions --dry-run
danvas discussions create --course-id 1655780 content/discussions/unit-4.md \
  --seed-replies --dry-run
danvas discussions verify --course-id 1655780 content/discussions/unit-4.md
danvas discussions update --course-id 1655780 content/discussions/unit-4.md \
  --body-only --dry-run
danvas discussions score https://auburn.instructure.com/courses/1655780/discussion_topics/9772349 \
  2 2 3 2 --output discussion-scores.csv

# Announcements
danvas announcements create --course-id 1706414 announcements/welcome.md --dry-run
danvas announcements export --course-id 1655780 --output announcements.md
danvas announcements latest --course-id 1655780 --format markdown
danvas announcements sync --course-id 1655780 --output-dir content/announcements --dry-run
danvas announcements verify --course-id 1655780 content/announcements/001-update.md
danvas announcements update --course-id 1655780 content/announcements/001-update.md --dry-run

# Pages
danvas pages sync --course-id 1706414 --output-dir content/pages --dry-run
danvas pages sync --course-id 1706414 --output-dir content/pages --page-id 123 --dry-run
danvas pages export --course-id 1706414 --page-id 123 --format markdown --output /tmp/page.md
danvas pages render content/pages/resources.md --output -
danvas pages css-check content/pages/resources.canvas.css --source content/pages/resources.md
danvas pages create --course-id 1706414 content/pages/resources.md --dry-run
danvas pages update --course-id 1706414 content/pages/resources.md --page-id resources --dry-run
danvas pages verify --course-id 1706414 content/pages/resources.md --page-id resources

# Local source lint (no Canvas authentication)
danvas sources lint --project-root .
danvas sources lint content/pages/*.md --format json --output .danvas/source-lint.json

# Files
danvas files inventory --course-id 1742717 --local-root .
danvas files inventory --course-id 1742717 --output-dir .danvas/files-inventory --local-root .
danvas files upload --course-id 1742717 --folder "course files/slides" \
  --dry-run content/slides/example.pptx
danvas files upload --course-id 1742717 --folder-id 15968602 \
  --on-duplicate overwrite --output .danvas/uploaded-files.json content/slides/example.pptx
danvas files compare --course-id 1742717 --file-id 284879389 \
  --local content/slides/example.pptx
danvas files compare --course-id 1742717 \
  --canvas-path "course files/slides/example.pptx" \
  --local content/slides/example.pptx
danvas files compare --course-id 1742717 --file-id 284879389 \
  --local content/slides/example.pptx \
  --downloaded-canvas .danvas/canvas-files/slides/example.pptx
danvas files download-one --course-id 1742717 --file-id 284879389 \
  --output .danvas/canvas-files/slides/example.pptx
danvas files download --course-id 1742717 --output-dir .danvas/canvas-files

# Reports
danvas reports list
danvas reports latest status
danvas reports latest files-inventory --output .danvas/latest-files-report.json

# Recordings
danvas recordings panopto-captions --course-id 1742717 \
  --folder-id b4e2a2bc-0b9f-439e-9095-b44e00f269c4 --dry-run
danvas recordings panopto-captions --course-id 1742717 \
  --folder-id b4e2a2bc-0b9f-439e-9095-b44e00f269c4 --output-dir panopto-captions
```

`assignments export --full` is an extended safe projection, not a raw Canvas
object dump. Assignment create/update/upsert/verify evidence omits raw
description HTML and unsafe nested Canvas payloads; stable link identity is
recorded as Canvas course/file IDs and generated course-file URLs.

`assignments verify` returns success only for `matches`. It returns nonzero for
`mismatch`, `partial`, or `indeterminate`, and its report states declared-field
coverage plus the local/live Canvas file-ID counts and course-scoped file reads.
`allowed_extensions` comparisons are case-insensitive and ignore a leading dot.
Relative local assets remain partial until a later asset-upload/rewriting
workflow resolves them.

`files upload --dry-run` reads the resolved folder and records whether each file
would be created, overwritten, or renamed. This is point-in-time evidence;
Canvas's live result remains authoritative. Live rows record separate
`mutation_status` and `evidence_status` values. A successful row always retains
its `canvas_id` and `canvas_path`; when the configured Canvas origin is valid it
also provides a reusable `canvas_url` such as
`https://canvas.example/courses/101/files/44?wrap=1`. If URL construction is
incomplete, the row remains truthfully uploaded and warns not to retry it.

## CSV Formats

Roster exports include:

```text
CanvasID,Name,Email,SIS_ID
```

The `Email` column is populated from Canvas `login_id`; in many courses that is
an email address, but it should be treated as the Canvas login identifier.

Grade uploads require `CanvasID` and `Grade`; `Name` and `Comment` are optional:

```text
CanvasID,Name,Grade,Comment
4024825,"Lawson, Jack",90,"Good work."
```

Fully blank CSV rows are ignored. Any nonblank row missing `CanvasID` or
`Grade`, any invalid/nonpositive Canvas ID, and duplicate IDs (including forms
such as `1` and `001`) fail before Canvas access. Verify therefore cannot report
success after silently omitting malformed input intent.

## Safety

Use `--dry-run` before commands that write to Canvas:

```bash
danvas assignments create ... --dry-run
danvas assignments update ... --dry-run
danvas assignments upsert ... --dry-run
danvas announcements update ... --dry-run
danvas pages create ... --dry-run
danvas pages update ... --dry-run
danvas submissions feedback ... --dry-run
danvas grades post ... --dry-run
danvas discussions score ... --dry-run
danvas quiz import-qti ... --dry-run
danvas files upload ... --dry-run
```

`grades post --dry-run` reads the current Canvas state and validates the full
patch without writing. Use `--offline-preview` only when authentication is
intentionally unavailable. Post, clear, and verify write private report runs by
default when a course project is discoverable; use `--project-root` for explicit
project discovery and `--no-report`, `--report-root`, `--report-dir`, or
`--report-slug` to control the report. Live post/clear writes private
rollback JSON/CSV before the first mutation, reads every attempted row back, and
stops new writes after a partial, unverified, or indeterminate result. When the
observed state supports safe preconditions, danvas also writes a guarded forward
recovery CSV; otherwise it leaves private JSON/Markdown guidance and requires a
fresh readback. Grade release conclusions are `verified_visible`,
`verified_hidden`, `mixed`, or `not_determined`; publication and manual-posting
policy are context rather than proof that students can see a grade.

Auburn Canvas may reject grade/comment updates on an unpublished assignment as
unauthorized even when the enrollment is gradeable and the caller has
`manage_grades`; confirm publication state before diagnosing a token failure,
but do not publish without explicit authorization. `ExpectedCurrentGrade` and
`ExpectedComment` are one-shot pre-mutation guards. After verified success, an
idempotent `replace_exact` retry should retain the exact owned `CommentID` while
refreshing or omitting stale preconditions; the retry then reports
`already_applied` without writing.

`pages sync --dry-run` reads Canvas and plans local source creation. Live sync
writes only missing local files with no-clobber installation and recoverable
source-map provenance; it does not mutate Canvas and has no overwrite mode.

`files download` treats Canvas folder and file names as untrusted input and
confines every broad-download target to `--output-dir`; `--overwrite` never
weakens that boundary.

`recordings panopto-captions --dry-run` previews a local caption-download
workflow and writes manifests without caption files. Live mode downloads
captions locally; neither mode mutates Canvas.

Live Canvas writes print a `== Canvas write: ... ==` banner showing the course, target, and write counts before any change is made.

## Development

```bash
uv run ruff check .
uv run ty check
uv run pytest
uv run danvas --help
```

CI runs the same three checks on push and pull request.
