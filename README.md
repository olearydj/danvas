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
  - roster format includes `CanvasID`, name, Canvas login ID in the `LoginID` column, and SIS ID
  - private roster output defaults beneath `.danvas/private/`
  - `--schema legacy-v1` retains the old `Email` label through 0.18.x and is
    removed in 0.19.0

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
  - plans by default; `--apply` authorizes the reviewed Canvas change
  - safely plans, uploads or reuses, rewrites, and verifies relative document and image assets
  - leaves authored Markdown unchanged and records immediate file provenance for safe retries
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
  - plan by default, block all unmatched files, and require `--apply`
  - checkpoint every applied row and stop after unsafe or uncertain readback

- grade submissions
  - post grades from CSV
  - optional text comments from CSV
  - plan by default and require `--apply` before changing Canvas
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
  - private `grades post`-compatible CSV plan with expected-current-grade guards
  - aggregate-only terminal output and no direct grade-upload path

- export announcements
  - create announcements from Markdown with front matter
  - plan create/update by default and require `--apply` to write Canvas
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
  - upload plans classify create, overwrite, rename, or conflict from the destination listing
  - duplicate names block by default; overwrite/rename require explicit policy and `--apply`
  - live uploads return the final Canvas ID/path and a generated stable course-file URL without retaining download/verifier URLs
  - downloads Canvas Files into a local folder tree with a manifest

- download Panopto captions
  - launches Panopto through the Canvas course navigation LTI tool
  - lists visible recording sessions and writes sanitized private JSON/CSV manifests
  - downloads caption text exports into a protected bundle when captions are available

- upload grades
  - assignment grades from CSV
  - discussion score plans consumed by the same grade transaction
  - optional submission comments
  - plan by default; `--apply` captures rollback, writes, and reads back

- analyze Canvas quiz/survey exports
  - parse Classic Quiz / Survey student-analysis CSV files
  - discover question/score column pairs
  - summarize scores and selected answer counts

- import QTI quiz packages
  - imports a text2qti/QTI zip as a Classic Quiz via the Canvas content-migration API
  - polls the migration to completion and reports failures
  - applies quiz shell settings: dates, publish state, time limit, attempts, assignment group
  - verifies the resulting Canvas quiz settings and exits nonzero on mismatch
  - plan mode shows the package and settings; `--apply` authorizes import

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
scripts/release-smoke.sh --expected-version X.Y.Z
```

The smoke script honors normal uv configuration and freshness rules, never
contacts Canvas, and never changes the global danvas installation.

Install the latest exact tagged release:

```bash
uv tool install --force --upgrade --reinstall \
  "danvas @ git+ssh://git@github.com/olearydj/danvas.git@v0.17.0"
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
  "danvas @ git+ssh://git@github.com/olearydj/danvas.git@v0.17.0"
```

Do not remove or loosen the global cutoff merely to make resolution succeed.
Confirm that the selected cutoff includes the tagged release and its required
dependencies.

## Authentication

Canvas-backed commands require an explicit Canvas instance. Configure one with
a course project, a user-level profile, `--api-url`, or the compatibility
`CANVAS_API_URL` environment variable. Danvas has no built-in institutional
host.

The user configuration is `danvas/config.toml` beneath the platform-standard
configuration directory (for example, `~/Library/Application Support/danvas/`
on macOS or `${XDG_CONFIG_HOME:-~/.config}/danvas/` on Linux). Profiles contain
stable defaults and secret references, never tokens:

```toml
default_profile = "example-university"

[profiles.example-university]
api_url = "https://canvas.example.edu/"
timezone = "America/New_York"
secret_name = "canvas-example-university"
secret_provider = "auto"
api_key_env = "CANVAS_EXAMPLE_UNIVERSITY_API_KEY"
```

Without a selected profile, the compatibility `secretpath` name remains
`canvas`. Existing `.env`, environment-variable, 1Password-reference, and
command-line workflows remain supported:

```bash
export CANVAS_API_KEY="fallback-token"
export CANVAS_API_URL="https://canvas.example.edu/"
```

Common options are available on Canvas-backed commands:

```bash
--profile
--api-url
--secret-name
--secret-provider auto|1password|env
--op-reference
--api-key-env
```

Inspect authentication setup without printing tokens:

```bash
danvas auth doctor
danvas auth doctor --check-canvas
```

The offline doctor remains useful without an instance: it reports the API URL
as `unconfigured` and continues secret-provider diagnostics. Only
`--check-canvas` requires a resolved API URL.

See the [0.15.0 migration guide](docs/migrations/0.15.0.md) for exact
before/after behavior and precedence.

`recordings panopto-captions` uses the Canvas token to launch the course Panopto
LTI tool; it does not require separate Panopto API client credentials.

## Project Configuration

Initialize a teaching project once to avoid repeating the Canvas course ID and
assignment group IDs:

```bash
danvas init 101 --profile example-university
```

This writes:

```text
.danvas/config.toml
.danvas/course.json
```

`init` resolves the Canvas host from `--api-url`, an existing project setting,
the selected profile, then `CANVAS_API_URL`. Profile selection resolves from
`--profile`, project configuration, `DANVAS_PROFILE`, then `default_profile`.
An initialized project's API URL always outranks the generic environment
fallback.

Pass `--timezone` to pin an IANA timezone. Otherwise init uses recognized Canvas
course metadata (including an explicit bounded mapping for Rails-style names),
then the selected profile timezone. Unknown metadata is never guessed. If no
timezone resolves, init omits the setting and date-only authored fields remain
unavailable until `[canvas].timezone` is configured.

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
project is a git repo, `danvas init` adds `.danvas/course.json`,
`.danvas/reports/`, and `.danvas/private/` to `.gitignore`.

`.danvas/config.toml` and `.danvas/source-map.json` contain stable, non-secret
course configuration and deployment provenance. They are suitable for tracking
in a private course repository, but may expose course names, Canvas object IDs,
schedules, and deployment history. Review them before publishing. Tokens never
belong in either file.

## Private Artifacts

Student-identifying exports, grades, comments, discussion responses, feedback
plans, and protected recording captions are private artifacts. In an
initialized project, their omitted output paths resolve beneath
`.danvas/private/`. Outside a project, the relevant `--output`, `--output-dir`,
or `--rollback-dir` is required before Canvas authentication begins.

On supported POSIX platforms, danvas creates its private directories as `0700`
and files as `0600`, including temporary files. It does not overwrite private
artifacts by default. Standalone CSV, text, and binary artifacts receive an
integrity sidecar; standalone JSON embeds classification metadata. Routine
terminal output is count-first and does not repeat student rows.

See [the 0.16.0 migration guide](docs/migrations/0.16.0.md) for the complete
private-output inventory and compatibility changes. See
[the 0.17.0 migration guide](docs/migrations/0.17.0.md) before upgrading
automation that can change Canvas.

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
source sync, verification, and update dry-run/readback workflows write dated
run directories when a course project is available. Non-private reports use
`.danvas/reports/`; private reports use `.danvas/private/reports/`:

```text
.danvas/reports/YYYY-MM-DD-NNN-command-slug/
  manifest.json
  command-output.json
  command-output.md

.danvas/private/reports/YYYY-MM-DD-NNN-command-slug/
  manifest.json
  command-output.json
  command-output.md
```

The date prefix uses the course timezone from `.danvas/config.toml` when present,
then falls back to the system local date. `danvas init` ignores both report
roots in Git repositories.

Report manifest schema version 2 records bounded relative provenance and omits
full argument vectors and absolute project/run paths. Report discovery reads
both roots, including legacy v1 runs, and identifies equal directory names by
storage scope. Private report runs create their directory and every artifact
without group or other permissions.

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
danvas roster --course-id 101

# Assignments
danvas assignments export --course-id 101 --output assignments.json
danvas assignments export --course-id 101 --output assignments-full.json --full
danvas assignments export --course-id 101 --output assignments.csv
danvas assignments export --course-id 101 --output assignments-md --format markdown
danvas assignments create --course-id 101 assignments/hw1.md
danvas assignments create --course-id 101 assignments/hw1.md --apply
danvas assignments verify --course-id 101 assignments/hw1.md
danvas assignments update --course-id 101 assignments/hw1.md
danvas assignments upsert --course-id 101 assignments/hw1.md
danvas assignments upsert --course-id 101 assignments/hw1.md \
  --apply --confirm update
danvas assignments update --course-id 101 content/assignments/case.md \
  --project-root . --asset-folder "course files/case-resources"
danvas assignments update --course-id 101 content/assignments/case.md \
  --project-root . --asset-folder "course files/case-resources" --apply
danvas assignments audit assignments-full.json --course-yaml course.yaml
danvas assignments overrides --course-id 101 --assignment-id 202
danvas assignments overrides-sync --course-id 101 assignments/hw1.md
danvas assignments overrides-sync --course-id 101 assignments/hw1.md \
  --apply --confirm apply

# Submissions and feedback
danvas submissions export --course-id 101 --assignment-id 202
danvas submissions grades --course-id 101 --assignment-id 202
danvas submissions media --course-id 101 --assignment-id 202
danvas submissions feedback --course-id 101 --assignment-id 202 \
  --roster roster.csv --feedback-dir feedback --pattern "*-feedback.pdf"
danvas submissions feedback --course-id 101 --assignment-id 202 \
  --roster roster.csv --feedback-dir feedback --pattern "*-feedback.pdf" --apply

# Grades
danvas grades post --course-id 101 --assignment-id 202 --grades-csv grades.csv
danvas grades post --course-id 101 --assignment-id 202 --grades-csv grades.csv --apply
danvas grades comments --course-id 101 --assignment-id 202 --canvas-id 303
danvas grades clear --course-id 101 --assignment-id 202 --grades-csv rollback.csv
danvas grades verify --course-id 101 --assignment-id 202 --grades-csv grades.csv
danvas gradebook check final-canvas-gradebook.csv --course-yaml course.yaml
danvas gradebook audit final-canvas-gradebook.csv --course-yaml course.yaml \
  --assignments assignments-full.json --output gradebook-audit.json

# Quiz/survey exports
danvas quiz analysis student-analysis.csv --answer-term "which version" --answer-term comp \
  --output quiz-analysis.json

# Quiz import (Classic Quizzes via QTI)
danvas quiz import-qti chap07.zip --course-id 101 \
  --due-at 2026-06-20T04:59:00Z --publish
danvas quiz import-qti chap07.zip --course-id 101 \
  --due-at 2026-06-20T04:59:00Z --publish --output quiz-import-report.json --apply

# Discussions
danvas discussions export https://canvas.example.edu/courses/101/discussion_topics/404 \
  --output discussion.json
danvas discussions sync-prompts --course-id 101 --output-dir content/discussions --dry-run
danvas discussions create --course-id 101 content/discussions/unit-4.md \
  --seed-replies
danvas discussions create --course-id 101 content/discussions/unit-4.md \
  --seed-replies --apply
danvas discussions verify --course-id 101 content/discussions/unit-4.md
danvas discussions update --course-id 101 content/discussions/unit-4.md \
  --body-only
danvas discussions score https://canvas.example.edu/courses/101/discussion_topics/404 \
  2 2 3 2 --output discussion-scores.csv

# Announcements
danvas announcements create --course-id 101 announcements/welcome.md
danvas announcements create --course-id 101 announcements/welcome.md --apply
danvas announcements export --course-id 101 --output announcements.md
danvas announcements latest --course-id 101 --format markdown
danvas announcements sync --course-id 101 --output-dir content/announcements --dry-run
danvas announcements verify --course-id 101 content/announcements/001-update.md
danvas announcements update --course-id 101 content/announcements/001-update.md

# Pages
danvas pages sync --course-id 101 --output-dir content/pages --dry-run
danvas pages sync --course-id 101 --output-dir content/pages --page-id 123 --dry-run
danvas pages export --course-id 101 --page-id 123 --format markdown --output /tmp/page.md
danvas pages render content/pages/resources.md --output -
danvas pages css-check content/pages/resources.canvas.css --source content/pages/resources.md
danvas pages create --course-id 101 content/pages/resources.md
danvas pages create --course-id 101 content/pages/resources.md --apply
danvas pages update --course-id 101 content/pages/resources.md --page-id resources
danvas pages verify --course-id 101 content/pages/resources.md --page-id resources

# Local source lint (no Canvas authentication)
danvas sources lint --project-root .
danvas sources lint content/pages/*.md --format json --output .danvas/source-lint.json

# Files
danvas files inventory --course-id 101 --local-root .
danvas files inventory --course-id 101 --output-dir .danvas/files-inventory --local-root .
danvas files upload --course-id 101 --folder "course files/slides" \
  content/slides/example.pptx
danvas files upload --course-id 101 --folder-id 505 \
  --on-duplicate overwrite --output .danvas/uploaded-files.json \
  content/slides/example.pptx --apply
danvas files compare --course-id 101 --file-id 606 \
  --local content/slides/example.pptx
danvas files compare --course-id 101 \
  --canvas-path "course files/slides/example.pptx" \
  --local content/slides/example.pptx
danvas files compare --course-id 101 --file-id 606 \
  --local content/slides/example.pptx \
  --downloaded-canvas .danvas/canvas-files/slides/example.pptx
danvas files download-one --course-id 101 --file-id 606 \
  --output .danvas/canvas-files/slides/example.pptx
danvas files download --course-id 101 --output-dir .danvas/canvas-files

# Reports
danvas reports list
danvas reports latest status
danvas reports latest files-inventory --output .danvas/latest-files-report.json

# Recordings
danvas recordings panopto-captions --course-id 101 \
  --folder-id b4e2a2bc-0b9f-439e-9095-b44e00f269c4 --dry-run
danvas recordings panopto-captions --course-id 101 \
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
Relative document and image links in Markdown-backed assignments use the shared
asset transaction. New assets require an existing Canvas Files destination via
`--asset-folder` or `--asset-folder-id`; danvas never creates a folder or
overwrites a file implicitly. Duplicate names and changed local bytes fail by
default. `--asset-on-duplicate rename` explicitly uploads a new identity and
leaves the old Canvas file untouched. A later run reuses unchanged source-map
identities without repeating the destination option. Create, update, upsert,
and verify fail closed for unresolved, unsafe, stale, or cross-course assets,
while the authored Markdown remains unchanged.

`files upload` plan mode reads the resolved folder and records whether each file
would be created, overwritten, renamed, or blocked. Duplicate names block by
default; `--on-duplicate overwrite` and `rename` are explicit policies that
still require `--apply`. Planning is point-in-time evidence; Canvas's applied
result remains authoritative. Apply rows record separate
`mutation_status` and `evidence_status` values. A successful row always retains
its `canvas_id` and `canvas_path`; when the configured Canvas origin is valid it
also provides a reusable `canvas_url` such as
`https://canvas.example/courses/101/files/44?wrap=1`. If URL construction is
incomplete, the row remains truthfully uploaded and warns not to retry it.

## CSV Formats

Roster exports include:

```text
CanvasID,Name,LoginID,SIS_ID
```

The `LoginID` column is populated from Canvas `login_id`; in many courses that
is an email address, but it should be treated as the Canvas login identifier.
`--schema legacy-v1` retains the old `Email` header through 0.18.x and is
removed in 0.19.0.

Grade uploads require `CanvasID` and `Grade`; `Name` and `Comment` are optional:

```text
CanvasID,Name,Grade,Comment
303,"Example, Student",90,"Good work."
```

Fully blank CSV rows are ignored. Any nonblank row missing `CanvasID` or
`Grade`, any invalid/nonpositive Canvas ID, and duplicate IDs (including forms
such as `1` and `001`) fail before Canvas access. Verify therefore cannot report
success after silently omitting malformed input intent.

## Safety

Commands that can change Canvas plan by default. Review the plan, then repeat
the invocation with `--apply` to authorize the write. `--dry-run` is an
explicit compatibility spelling for plan mode; it cannot be combined with
`--apply`.

```bash
danvas assignments update SOURCE
danvas assignments update SOURCE --apply

danvas grades post --assignment-id 202 --grades-csv grades.csv
danvas grades post --assignment-id 202 --grades-csv grades.csv --apply
```

Assignment upsert additionally requires `--confirm create` or
`--confirm update`, matching the plan. Override reconciliation requires
`--confirm apply`. `discussions score` never writes grades; it emits a private
CSV for the `grades post` transaction.

`grades post --dry-run` reads the current Canvas state and validates the full
patch without writing. Use `--offline-preview` only when authentication is
intentionally unavailable. Post, clear, and verify write private report runs by
default when a course project is discoverable; use `--project-root` for explicit
project discovery and `--no-report`, `--report-root`, `--report-dir`, or
`--report-slug` to control the report. Live post/clear writes private rollback
JSON/CSV beneath `.danvas/private/grades/assignment-<id>/rollback/` before the
first mutation, reads every attempted row back, and stops new writes after a
partial, unverified, or indeterminate result. When the
observed state supports safe preconditions, danvas also writes a guarded forward
recovery CSV; otherwise it leaves private JSON/Markdown guidance and requires a
fresh readback. Grade release conclusions are `verified_visible`,
`verified_hidden`, `mixed`, or `not_determined`; publication and manual-posting
policy are context rather than proof that students can see a grade.

Canvas may reject grade/comment updates on an unpublished assignment as
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
weakens that boundary. Canvas cannot prove that arbitrary course files lack
student data or restricted material, so choose a private destination when the
downloaded content is sensitive.

`recordings panopto-captions --dry-run` previews a local caption-download
workflow and writes private manifests without caption files. Live mode
downloads captions beneath `.danvas/private/recordings/` by default; neither
mode mutates Canvas. Retained manifests omit viewer, launch, signed, verifier,
and session URLs.

Live Canvas writes print a `== Canvas write: ... ==` banner showing the course, target, and write counts before any change is made.

## Development

```bash
uv run ruff check .
uv run ty check
uv run pip-audit --skip-editable
uv run pytest --cov=danvas --cov-branch --cov-report=term-missing \
  --cov-report=json:/tmp/danvas-coverage.json --cov-fail-under=82
uv run python scripts/check-module-coverage.py \
  /tmp/danvas-coverage.json src/danvas/authored_assets.py 82
uv run danvas --help
```

CI runs the same frozen lint, type, dependency-audit, and branch-coverage checks
on Python 3.12 and 3.14, then verifies editable and wheel installs once after
both lanes pass.
