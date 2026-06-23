# danvas Backlog

Sprint plans in `docs/sprint-1.md` through `docs/sprint-3.md` schedule items from this backlog; delivered items are annotated below.

## Course Project Sync And Diff

Status: largely delivered in sprint 1 by `danvas status` (read-only classification report) and `danvas refresh --diff`; a write-capable sync command remains open.

Add a read-only `danvas sync` or `danvas diff` command that compares local course
sources against `.danvas/course.json`.

Desired behavior:

- Report Canvas items missing local source files.
- Report local source files not represented in the Canvas snapshot.
- Compare matching items by stable metadata: title, group, points, due/unlock/lock dates, published state, submission type, and wrapper/body text where available.
- Clearly label unsupported comparisons, such as quiz question bodies when the snapshot only contains the quiz assignment shell.
- Warn when `.danvas/course.json` is stale enough that the report should be refreshed first.

Likely inputs:

- `.danvas/config.toml`
- `.danvas/course.json`
- local source conventions such as `content/announcements/`, `content/discussions/`,
  `content/quizzes/`, `content/cases/`, or project-configured `[sources]`
  patterns in `.danvas/config.toml`.

## Expanded Course Snapshot

Status: delivered in sprint 1 (`schema_version` 2 snapshots).

Expand `danvas refresh` so `.danvas/course.json` can support stronger local-vs-Canvas
audits.

Desired additions:

- Canvas Files metadata: file ID, display name, filename, folder, size, updated time, and content type.
- Discussion topics: topic ID, title, URL, assignment ID when graded, published/locked state, and normalized message text.
- Announcements separately from ordinary discussions.
- Quiz shells: quiz ID, assignment ID, title, description, points, due dates, and published state.
- Group categories: category ID, name, self-signup settings where available, group
  count, and member counts. Do not include roster/member lists in the general
  snapshot; keep detailed membership verification behind explicit group commands.

Keep the snapshot non-secret and suitable for local comparison. Do not store file download verifier URLs or submission/student data.

## Assignment Update Or Upsert

Add conservative update support for Markdown-backed assignments.

Desired behavior:

- Support `danvas assignments update SOURCE.md --dry-run`.
- Match by Canvas ID when present; allow title matching only with an explicit flag.
- Show a field-by-field before/after diff before writes.
- Update supported assignment fields without deleting unrelated Canvas state.
- Avoid duplicate assignment creation when the local source represents an existing Canvas assignment.

## Assignment And Announcement Readback Verification

Add explicit verification commands for Canvas objects that were created or updated
from local Markdown.

Observed context:

- Agents already dry-run assignment and announcement creation, but after the live
  write they still need to prove that Canvas has the expected title, URL,
  publication state, due date, assignment group, group category, points, submission
  type, and relevant grading settings.
- Today this requires either manual Canvas API calls or interpreting a refreshed
  `.danvas/course.json` snapshot.

Likely command shapes:

```bash
danvas assignments verify content/cases/case-1-emerging-tech.md
danvas assignments verify --assignment-id 19862404
danvas announcements verify content/announcements/04-case-1-open.md
danvas announcements latest --course-id 1742719 --format markdown
```

Desired behavior:

- Resolve the Canvas object by explicit ID from front matter, sidecar metadata, or
  CLI option. Matching by title should require an explicit flag and should refuse
  ambiguous matches.
- Report stable Canvas readback fields and compare them to the local source where
  possible.
- For grouped assignments, verify `group_category_id`,
  `grade_group_students_individually`, and related peer-review settings.
- For announcements, support a simple "latest announcement" export for checking
  instructor-authored Canvas announcements before posting a follow-up.
- Emit human-readable output by default, with optional JSON for handoff or tests.

## Canvas Group Categories And Memberships

Add first-class support for Canvas group categories, group creation, CSV import,
import-progress polling, and membership verification.

Observed context:

- A grouped case assignment required a Canvas group category before publishing.
- `danvas` could export the roster and create the assignment, but the workflow had
  to fall back to raw Canvas API calls to rename a placeholder group category,
  import the Canvas group CSV, poll the import progress, and verify that all groups
  and memberships were present.
- This is a high-risk operational step because assignment publication depends on
  the correct `group_category_id` and students need correct group membership before
  work begins.

Likely command shapes:

```bash
danvas groups categories --course-id 1742719
danvas groups categories rename --course-id 1742719 154244 "Case 1 Groups" --dry-run
danvas groups import --course-id 1742719 --category-id 154244 content/cases/case-1-groups.csv --dry-run
danvas groups verify --course-id 1742719 --category-id 154244 --expected content/cases/case-1-groups.csv
```

Desired behavior:

- List group categories with IDs, names, self-signup settings, group counts, and
  membership counts.
- Create or rename a group category only with an explicit mutating command and
  `--dry-run` support where possible.
- Import a Canvas-compatible group CSV into a chosen group category.
- Poll Canvas progress objects until the import finishes or fails, then report the
  progress ID, status, created/updated group count, user count, and any errors.
- Verify actual Canvas group names and memberships against an expected CSV.
- Refuse to continue when a roster/login in the CSV cannot be resolved to exactly
  one Canvas user.
- Keep roster and membership outputs course-private and avoid writing student data
  outside an explicitly requested output path.

## Group Planning From Roster

Add optional group-planning helpers that produce Canvas group-import CSVs from a
course roster and balancing constraints.

Observed context:

- A 16-student course needed four-person case groups with a mix of campus and
  distance students.
- Three case groupings were needed up front, with the same broad mix but no repeated
  student pairings across cases when feasible.
- The planning logic was useful but ad hoc, and it had to be validated separately.

Likely command shape:

```bash
danvas groups plan \
  --roster .danvas/roster.csv \
  --group-size 4 \
  --balance-by Section \
  --rounds 3 \
  --output-dir content/cases \
  --name-pattern "case-{round}-groups.csv"
```

Desired behavior:

- Read a `danvas roster` export or a Canvas group import template.
- Support constraints such as group size, number of rounds/cases, balancing by
  section or other roster column, and minimizing repeated pairings.
- Emit Canvas import-compatible CSV files plus a validation summary.
- Report repeated pairings, unassigned students, unresolved roster rows, and
  section-balance exceptions.
- Treat the planner as local-only; it should not create Canvas groups unless paired
  with an explicit `danvas groups import` command.

## Canvas File Upload Helper

Status: basic v1 delivered by `danvas files upload`. Markdown asset rewriting and
folder creation remain future work.

Add a file upload command that returns Canvas file metadata needed by local Markdown
sources.

Likely command shape:

```bash
danvas files upload content/cases/case1-prompt.docx --folder "Case Studies"
```

Desired behavior:

- Upload one or more local files to an existing named Canvas Files folder or folder
  ID.
- Print and optionally write file ID, display name, folder, size, content type, and
  URL presence without storing verifier/download URLs.
- Support `--dry-run` with a meaningful preview.
- Support `--on-duplicate overwrite|rename`.
- Do not create folders in v1.
- Later, integrate with Markdown-backed assignments, announcements, and discussions so local asset links can be uploaded and rewritten before posting.

## Single Canvas File Download And Compare

Add a single-file download path for targeted local-vs-Canvas asset checks without
downloading every course file.

Suggested command shape:

```bash
danvas files download-one --course-id 1742719 --file-id 284879389 --output /private/tmp/02a-EmergingTech.canvas.pptx
```

Also useful:

```bash
danvas files download-one --course-id 1742719 --canvas-path "course files/slides/02a-EmergingTech.pptx" --output /private/tmp/
```

Desired behavior:

- Download exactly one Canvas file by file ID, or by an unambiguous Canvas folder path.
- Write to a user-specified output file or directory.
- Refuse ambiguous path matches unless the user supplies a file ID.
- Print Canvas file ID, Canvas path, size, content type, updated time, local output path, and checksum.
- Do not overwrite an existing local file unless `--overwrite` is passed.

Add a companion compare command once the download path is stable.

Suggested command shape:

```bash
danvas files compare --course-id 1742719 --file-id 284879389 --local content/slides/02a-EmergingTech.pptx
```

Minimum desired behavior:

- Compare Canvas metadata against the local file by filename, size, and checksum.
- For Office files such as PPTX/DOCX/XLSX, optionally compare internal ZIP entries and report added, missing, and changed package parts.
- Keep the default comparison non-destructive and avoid storing secret download verifier URLs in `.danvas/course.json`.

## Local Source Discovery

Status: delivered in sprint 1 (`danvas.sources`) and expanded after sprint 1 with
project-configured source patterns in `.danvas/config.toml`.

Add a shared source scanner that understands project conventions and can power
future sync/update commands.

Initial conventions:

- `content/announcements/*.md`
- `content/discussions/*.md`
- `content/quizzes/chap*.md`
- `content/cases/*-assignment.md`

Course repos can override these with `[sources.<kind>]` tables in
`.danvas/config.toml`, for example `[sources.assignments] include =
["content/assignments/*.md"]`. Custom assignment globs require assignment
metadata by default so ordinary support notes are skipped.

The scanner should classify source type, title, comparable metadata, and generated artifacts such as QTI zips when applicable.

## Quiz Shell Awareness

Status: delivered in sprint 1 via `danvas status`.

Add lightweight quiz awareness without turning `danvas` into the quiz authoring
tool.

Desired behavior:

- Compare local quiz Markdown title/description/points to Canvas quiz shells.
- Report whether a local QTI zip exists for the source.
- Report Canvas quiz shells with no local Markdown source.
- Explicitly state that question-body comparison is unavailable unless a future snapshot includes quiz item data.

## Rubric Support

Add rubric creation/audit support after assignment update and sync behavior are stable.

Desired behavior:

- Parse a local rubric source.
- Compare local criteria and point totals against Canvas rubric metadata.
- Support dry-run creation or attachment to an assignment.
- Treat destructive rubric replacement as out of scope unless explicitly requested.

## Graded And Seeded Discussion Creation From Markdown

Add first-class support for creating Canvas discussion topics from Markdown, including ordinary graded discussions and seeded discussions whose source contains both the root discussion body and instructor-created prompt replies.

Current workaround:

- Create the graded discussion body from one Markdown file.
- Keep the prompt replies in a second Markdown file.
- Use a local helper script to call CanvasAPI `post_entry` after the discussion is created.

Desired behavior:

- Accept a single Markdown source with normal assignment/discussion front matter for the root topic.
- Let the body define the root discussion instructions and one or more top-level instructor replies.
- Create the graded discussion topic and post the replies in one command.
- Support `--dry-run` output showing the root discussion payload and each reply payload before any Canvas write.
- Preserve Canvas assignment metadata such as `points_possible`, `due_at`, `published`, and `assignment_group_id`.
- Return and optionally save the created discussion topic ID, assignment ID, URL, and seeded entry IDs.

Possible source format:

```markdown
---
title: Emerging Technology Product Judgment Discussion
points_possible: 10
grading_type: points
submission_types:
- discussion_topic
published: true
due_at: 2026-06-08T04:59:59Z
assignment_group_id: 3444282
---

# Root discussion instructions

Students should reply under the instructor-created prompt threads.

--- reply ---

## Prompt 1

Prompt body...

--- reply ---

## Prompt 2

Prompt body...
```

Likely command shape:

```bash
danvas discussions create --course-id 1742719 discussion.md --seed-replies --dry-run
```

Implementation notes:

- Reuse the existing assignment Markdown front matter parser where practical.
- Convert root and reply Markdown sections to HTML with the same Markdown extensions used elsewhere.
- Use `course.create_discussion_topic(...)` for the root discussion and `topic.post_entry(message=...)` for each seeded top-level reply.
- Keep the operation idempotence-aware if possible, or clearly document that creation is not idempotent and should always be dry-run first.

## Session-Derived Recommendations From INSY 6600 June 2026

These recommendations come from a live INSY 6600 course-prep session that used
`danvas` to synchronize local course state, pull Panopto captions, compare Canvas
Files, and prepare a late Chapter 7 quiz release. They overlap with several backlog
items above, but the priorities and context below reflect the friction observed in
that workflow.

### P0: QTI Import, Publish, And Verification Workflow

Status: delivered in sprint 1 as `danvas quiz import-qti`; verified live 2026-06-12 (Chapter 8, INSY 6600). Note: imports land in the Canvas "Imported Assignments" group unless `--assignment-group-id` is passed; resolving the group by name from `.danvas/config.toml` is a future ergonomic.

Observed context:

- Local quiz authoring used Markdown plus `make-qti` to produce a Canvas QTI zip.
- `danvas quiz` can analyze Classic Quiz student-analysis CSV exports, but it does
  not currently import a QTI package or verify the resulting Canvas quiz settings.
- The Chapter 7 quiz had to be posted manually after the source was updated, and
  the due date was extended because the release was later than planned.

Recommended behavior:

- Add a `danvas quiz import-qti` or similar command that uploads/imports a QTI zip
  into a course.
- Support setting or updating the quiz assignment shell: title, assignment group,
  due/unlock/lock dates, points, published state, time limit, attempt settings, and
  core quiz options where Canvas exposes them.
- Include `--dry-run` and a post-import verification pass that reports the Canvas
  quiz ID, assignment ID, URL, published state, due dates, points, and any settings
  that could not be verified.
- Prefer matching by explicit quiz/assignment ID when updating. If matching by
  title, require an explicit flag and refuse ambiguous matches.

Why priority P0:

- Quiz release is a recurring, time-sensitive teaching task.
- Manual QTI import is the largest current gap between local quiz sources and the
  Canvas-facing workflow.
- A verification report would prevent agents from claiming a quiz is posted or
  correctly configured without evidence.

### P0: Read-Only Course Status Report

Status: delivered in sprint 1 as `danvas status`.

Observed context:

- The user explicitly requested synchronization without overwriting anything outside
  `.danvas`.
- The useful result was a human summary: which assignments existed in Canvas, which
  local quiz sources were missing Canvas shells, and which Canvas files matched,
  differed, or were Canvas-only.
- Producing that report required several separate commands plus manual interpretation.

Recommended behavior:

- Add `danvas status` or `danvas diff` as a read-only default command for course
  workspaces.
- Summarize Canvas/local state across assignments, quiz shells, announcements,
  discussions, files, and group-category summaries using `.danvas/config.toml`,
  `.danvas/course.json`, and local source conventions.
- Clearly classify results as `exact`, `metadata mismatch`, `local-only`,
  `Canvas-only`, `filename-only match`, `unsupported comparison`, or `snapshot stale`.
- Write machine-readable JSON plus a Markdown report suitable for handoff notes.
- Default all writes to `.danvas/`; do not download Canvas files or mutate Canvas
  unless the user passes a specific option.

Why priority P0:

- This is the safest and most reusable way for agents to answer "what differs?"
  without making course changes.
- It provides the right default when a user says "sync" but also says "report only"
  or "do not overwrite."
- It turns the current multi-command audit into a single repeatable workflow.

### Test 1 Reconciliation Workflow Improvements

1. Add `danvas submissions export`
Current `danvas submissions media` downloads files, but there is no metadata-only export. A command like this would have avoided the direct Canvas API script:

```bash
danvas submissions export --assignment-id 19901542 --output .danvas/proctoru-submissions.json
```

It should include `user_id`, name, workflow state, `submitted_at`, score, attempt, attachment count/names, late/missing flags, and optionally submission history.

2. Add assignment override member export
`assignments export --full` showed "12 students" / "4 students" overrides, but not the actual student IDs. A command like this would be useful:

```bash
danvas assignments overrides --assignment-id 19901488
```

or include `student_ids` directly in `assignments export --full`.

3. Include sections in `danvas roster`
The roster export gave Canvas ID/name/login/SIS ID, but not section. For hybrid courses, section is operationally important. Add fields like:

```text
SectionID, SectionName, EnrollmentState, LastActivityAt
```

This would have answered the Quinton Beyer `001` vs `DL1` question without an extra API lookup.

4. Add a reconciliation command for multi-version exams
This session's workflow was common enough to deserve a first-class command:

```bash
danvas exams reconcile \
  --roster .danvas/roster.csv \
  --variant in_class:assignment_override:19901488 \
  --variant zoom:override_or_submission:19901485 \
  --variant proctoru:submission:19901542 \
  --upload-assignment 19901660 \
  --upload-window-minutes 15
```

Output: `.md`, `.csv`, `.json` with accounted/unaccounted, overlaps, upload compliance, and late/missing uploads.

5. Add `danvas auth doctor`
The auth behavior was confusing: `op whoami` reported not signed in, but `danvas` could still resolve the 1Password secret after the desktop prompt. A diagnostic command should say exactly which auth path works:

```bash
danvas auth doctor
```

Expected output: provider available, token resolved yes/no, Canvas ping yes/no, without exposing the token.

6. Add sections to `.danvas/course.json`
The snapshot tracks assignments/quizzes/files/etc., but not sections/enrollment mappings. Including sections would make status reports and roster investigations more self-contained.

7. Avoid writing raw submission payloads by default
For privacy, reconciliation commands should default to sanitized outputs and require something explicit like `--save-raw` for raw Canvas payloads.

### P1: File Inventory And Comparison Report Improvements

Observed context:

- The file inventory/download workflow was useful, but the human-facing conclusion
  required manual classification.
- In the INSY 6600 session, there were 32 Canvas files, 30 exact local matches, one
  filename-only match, and one Canvas-only screenshot. The user then deleted the
  downloaded mirror because it had served its purpose.

Recommended behavior:

- Extend `danvas files inventory` to emit a clearer Markdown comparison report with
  counts and examples for exact matches, filename-only matches, Canvas-only files,
  local-only candidates, hash/size mismatches, and ignored paths.
- Add ignore rules or config for generated/cache/archive paths such as `.danvas/`,
  `_archive/`, rendered artifacts, and local scratch outputs.
- Support a comparison mode that does not require downloading all Canvas Files when
  Canvas metadata is sufficient, and a targeted single-file compare when content
  verification is needed.

Why priority P1:

- The current command already provides much of the raw data.
- Better classification would reduce manual interpretation and make handoff-quality
  reports easier.
- It pairs naturally with the single-file download/compare backlog item above.

### P1: Transcript Filing Helper

Observed context:

- `danvas recordings panopto-captions` successfully found and downloaded the June 4
  Panopto caption export.
- Filing it into the course's transcript structure still required manual naming and
  copying to `transcripts/raw/2026-06-04-lecture-06.panopto.transcript.txt`.

Recommended behavior:

- Add options to suggest or perform a course-local filing step after caption download.
- Possible command shape:

```bash
danvas recordings panopto-captions \
  --output-dir .danvas/panopto-captions \
  --session-id SESSION_GUID \
  --file-to transcripts/raw \
  --name-pattern "{date}-lecture-{number}.panopto.transcript.txt"
```

- If automatic lecture numbering is too project-specific, emit a suggested target
  filename based on session date/title and let the caller copy manually.
- Preserve the manifest and original downloaded caption in `.danvas/` while writing
  the filed transcript only when explicitly requested.

Why priority P1:

- Captions are important course-planning inputs, and the Panopto discovery/download
  path already works.
- A filing helper would prevent inconsistent transcript names and reduce friction
  before transcript-review work.

### P1: Refresh-With-Diff Summary

Status: delivered in sprint 1 as `danvas refresh --diff`.

Observed context:

- Canvas state changed outside `danvas` when the quiz was posted manually.
- A future agent needs to refresh `.danvas/course.json`, but also needs to know what
  changed since the prior snapshot.

Recommended behavior:

- Add `danvas refresh --summary` or `danvas refresh --diff` that compares the old and
  new snapshot before replacing or after saving a backup.
- Report added/removed/changed assignments, assignment groups, group categories,
  quiz shells, files, announcements, and discussions as far as the snapshot
  supports them.
- Include timestamps and a stale-snapshot warning when local data predates known
  Canvas changes.

Why priority P1:

- Manual Canvas edits are common in active teaching.
- A refresh summary helps keep `.danvas/` useful without requiring manual JSON
  comparisons.

### P2: Universal Mutation Guardrails

Status: mutation banner delivered in sprint 1; multi-step progress reporting lands with groups import in sprint 2.

Observed context:

- Existing commands such as assignment creation, announcement creation, grade post,
  feedback upload, and discussion scoring already have useful dry-run behavior in
  several places.
- Agents need an obvious distinction between "reporting" and "writing to Canvas."

Recommended behavior:

- Ensure every Canvas-mutating command has `--dry-run` or a clear preview mode.
- Print a consistent mutation banner before live writes, including course ID, target
  object IDs/titles, row counts, and whether comments/files/grades will be posted.
- For multi-step Canvas operations such as group CSV imports, print the Canvas
  progress ID and run or recommend a verification pass before the workflow is
  considered complete.
- Consider a global `--yes` or confirmation-bypass pattern only for non-interactive
  contexts where the user has explicitly asked for live writes.

Why priority P2:

- This is partly already implemented, so the remaining work is consistency.
- It reduces the chance of accidental Canvas writes during agent-assisted workflows.

### P2: Human-Readable Operation Reports

Status: partially delivered in sprint 1 (`danvas status --report-md`); other workflows remain.

Observed context:

- JSON and CSV outputs were useful for inspection, but the final value to the
  instructor was a concise explanation of what changed, what differed, and what was
  not checked.

Recommended behavior:

- For audit/status/download workflows, provide an optional `--report-md PATH`.
- Include sections for inputs, commands implied, summary counts, differences,
  unsupported checks, stale snapshot warnings, verification/readback status, and
  recommended next actions.
- Keep reports free of secrets, verifier URLs, and student-sensitive data.

Why priority P2:

- This is less urgent than QTI import or status/diff, but it improves handoffs and
  makes CLI output easier for agents and humans to review.

### P2: Generated Report Run Directories

Add a common generated-report convention so first-class audit, verification,
reconciliation, and comparison commands leave durable evidence without wrapper
scripts or per-course naming decisions.

Observed context:

- Course workspaces already keep local Canvas state in `.danvas/`.
- Existing commands use several output styles:
  - `danvas status` prints a summary and can optionally write `--output` JSON and
    `--report-md` Markdown.
  - `danvas files inventory` already writes a bundle directory containing
    `files-inventory.json`, `files-inventory.csv`, and
    `files-missing-report.md`.
  - `assignments audit`, `gradebook check`, `gradebook audit`, `quiz analysis`,
    `quiz import-qti`, and `files upload` can write explicit JSON/CSV report
    files with `--output`.
  - Downloads such as `files download`, `submissions media`, and
    `recordings panopto-captions` write operational artifacts or media bundles,
    not just reports.
- Agents need collision-safe, dated report paths without having to decide whether a
  generated report belongs in authored course source.
- Ad hoc shell wrappers can enforce naming, but the policy belongs in `danvas` so
  every report-producing command behaves consistently.
- `danvas init` currently ignores `.danvas/course.json` in git repos, but it does
  not ignore all future generated report output.

Scope:

- A report run is for generated operational evidence: audit, verification,
  reconciliation, status/comparison, dry-run/readback summaries, or other outputs
  whose primary value is a durable human- and machine-readable record.
- Raw exports, rosters, submissions, grades, downloaded Canvas Files, caption
  downloads, and other source/data artifacts should keep their existing explicit
  output paths or output directories. They may include a manifest, but they are
  not report runs by default.
- Existing explicit `--output`, `--report-md`, and `--output-dir` behavior should
  continue to work. The report-run helper should reduce future inconsistency, not
  break scripts that already pass concrete paths.

Command classification:

| Category | Commands | Default behavior |
|---|---|---|
| Default report run | `files inventory`, `assignments audit`, future `exams reconcile`, future verify/readback report commands | Write a report run unless `--no-report` is passed. |
| Compatibility-sensitive | `status` | Keep stdout-first behavior unless `--report-root` or `--report-dir` is passed. Preserve existing `--output` and `--report-md`. |
| Not report runs by default | `courses`, `roster`, raw exports, `files download`, `submissions media`, `recordings panopto-captions`, grade data downloads/uploads | Keep explicit output files/directories and manifests in their current locations. |

Recommended behavior:

- Add a shared report-run helper used by report-producing commands. Put it in a
  shared module such as `danvas.reports` or `danvas.utils` rather than duplicating
  path logic in each command.
- Commands whose primary purpose is a report should save a report run by default.
  Do not require a universal `--save-report` flag.
- Quick inspection commands may keep stdout-only behavior if their existing
  contract is mainly terminal feedback. When a command grows into a durable
  audit/reconciliation workflow, make the saved report run the default.
- Default report root: `.danvas/reports/` under the resolved course project root.
  For commands that do not currently resolve a project root, add an explicit
  `--project-root` or `--report-root`; do not silently choose a surprising
  directory when no `.danvas` project can be found.
- Use a run directory per report invocation:

  ```text
  .danvas/reports/YYYY-MM-DD-NNN-command-slug/
  ```

- Examples:

  ```text
  .danvas/reports/2026-06-23-001-status/
    manifest.json
    status.json
    status.md
  .danvas/reports/2026-06-23-002-files-inventory/
    manifest.json
    files-inventory.json
    files-inventory.csv
    files-missing-report.md
  .danvas/reports/2026-06-23-003-assignment-audit/
    manifest.json
    assignment-audit.json
    assignment-audit.md
  .danvas/reports/2026-06-23-004-exams-reconcile/
    manifest.json
    exams-reconcile.json
    exams-reconcile.csv
    exams-reconcile.md
  ```

- Use the course/project timezone from `.danvas/config.toml` when available to
  choose the ISO date prefix. If no project timezone is available, use the system
  local date. Choose the next unused three-digit sequence globally for that date,
  not per slug. This preserves chronological order in directory listings.
- Create the run directory with no overwrite behavior. Use an atomic
  `mkdir(exist_ok=False)`-style flow after choosing the candidate path; if a race
  creates the same path, choose the next sequence and retry.
- Print `Report directory: PATH` at the end of the command after all report files
  have been written.
- Include `manifest.json` in every report run directory. At minimum, include:
  command name, `argv`, `generated_at`, report date, report slug, run directory,
  `danvas` version, course ID when known, project root when known, input paths,
  snapshot timestamp when relevant, report file list, `status`, and a boolean or
  classification indicating whether the report may contain private/student data.
- Keep raw snapshots, exports, rosters, submissions, grades, downloaded files, and
  transcript downloads in their existing `.danvas/` locations.
- Keep report outputs free of secrets, verifier URLs, and student-sensitive data
  unless a command is explicitly private and the output path makes that clear.
- `danvas init` should add `.danvas/reports/` to `.gitignore` in git repos, and
  the report helper should create the directory under `.danvas/` so generated
  evidence does not mix with authored course content.

Common options:

```text
--no-report               Suppress the default report run for commands that save
                          one by default.
--report-root DIR         Override the root while still creating a dated run
                          directory below it.
--report-dir DIR          Write the report bundle exactly in DIR. Refuse if DIR
                          exists unless the command explicitly supports overwrite.
--report-slug SLUG        Override the command-derived slug.
```

Option semantics:

- Do not add `--overwrite` as a common report-run option initially. Most reports
  are evidence and should be append-only. If an individual command truly needs
  replacement semantics, keep that opt-in command-specific.
- If both `--report-root` and `--report-dir` are provided, fail with a clear
  conflict message.
- If legacy explicit outputs are provided and no report options are provided, write
  only the explicit outputs. If `--report-root` or `--report-dir` is also provided,
  write the explicit outputs and the report run, unless the command documents a
  narrower rule. Print every path written.
- For new commands with no legacy output contract, report-run output should be the
  default and `--no-report` should mean stdout-only or terminal-summary-only.
- If a command creates a report directory and later fails, keep the directory when
  possible. Write or update `manifest.json` with `status: "failed"`, an error
  summary safe for logs, and the files successfully written before failure. Failed
  audits are often useful operational evidence.

Likely command shapes after migration:

```bash
danvas files inventory --course-id 1742717 --local-root .
# writes .danvas/reports/YYYY-MM-DD-NNN-files-inventory/

danvas assignments audit .danvas/assignments.json --course-yaml syllabus/course.yaml
# writes .danvas/reports/YYYY-MM-DD-NNN-assignment-audit/

danvas exams reconcile --roster .danvas/roster.csv ...
# writes .danvas/reports/YYYY-MM-DD-NNN-exams-reconcile/

danvas status
# may remain stdout-only for compatibility

danvas status --report-root .danvas/reports
# writes a dated status report run

danvas status --output status.json --report-md status.md
# preserves the existing explicit-path behavior
```

Implementation notes:

- Prefer command-specific filenames inside each run directory, such as `status.md`,
  `status.json`, `files-inventory.csv`, or `assignment-audit.md`.
- Directory-per-run generalizes better than sibling `.md`/`.json` files because
  some commands naturally produce bundles.
- The helper should expose a small object or return value with at least `path`,
  `slug`, `created_at`, `manifest`, `record_file(...)`, and `finish(...)`, plus
  convenience methods or helpers for writing JSON, CSV, and Markdown through the
  existing `write_json` and `write_rows` conventions.
- Reuse the existing `slugify` helper for slugs, with a command-specific fallback.
- Add tests for sequence selection, no-overwrite creation, `--report-root` versus
  `--report-dir`, explicit-output compatibility, failed-run manifests, timezone
  date prefixes, and `.gitignore` maintenance.
- Good first adopters are `files inventory` and `assignments audit` because they
  already produce report-like output. Treat `status` as a compatibility-sensitive
  migration because existing tests and docs show stdout plus optional
  `--output`/`--report-md`.

Implementation phases:

1. Foundation and first adopters.
   - Add the shared report-run helper, dated directory creation, manifest writing,
     timezone-aware date prefixes, no-overwrite behavior, and failed-run manifest
     support.
   - Update `danvas init` / gitignore handling for `.danvas/reports/`.
   - Migrate `files inventory` and `assignments audit` to default report-run output
     while preserving explicit legacy output paths.
   - Add focused tests for helper behavior, gitignore updates, first adopters,
     explicit-output compatibility, failed manifests, and timezone date prefixes.

2. Compatibility-sensitive `status` migration.
   - Keep plain `danvas status` stdout-first.
   - Add `--report-root`, `--report-dir`, and `--report-slug` to `status`.
   - When a report option is passed, write `manifest.json`, `status.json`, and
     `status.md` in a report run.
   - Preserve existing `--output` and `--report-md` behavior exactly; if explicit
     paths and report options are both passed, write both.
   - Include snapshot timestamp/path and stale-snapshot status in the manifest.

3. Extend to existing verification/report commands.
   - Evaluate `gradebook check`, `gradebook audit`, `quiz analysis`,
     `quiz import-qti`, `files upload`, and discussion scoring for report-run
     adoption.
   - Migrate only commands whose primary output is an audit, verification, dry-run,
     readback, or comparison report.
   - Keep raw exports, rosters, grade data, downloads, submissions, and caption
     artifacts on explicit paths/directories by default.

4. Future command integration.
   - Make new reconciliation and verify/readback commands report-run-first from
     their initial implementation.
   - Use command-specific Markdown/CSV/JSON filenames and record all produced files
     in `manifest.json`.
   - Add command-specific manifest fields when they materially improve handoffs,
     such as involved assignment IDs, upload windows, snapshot timestamps, source
     export timestamps, and private/student-data classification.

Why priority P2:

- This reduces workflow friction and prevents accidental report overwrites.
- It makes generated operational evidence easy to cite in handoffs.
- It keeps report-storage policy inside `danvas` instead of duplicating it in agent
  skills or per-course shell scripts.

### P1: Case Submission Grading Workflow Improvements

Yes. A few practical `danvas` improvements came up.

1. Add a read-only grade/comment pull command

Something like:

```bash
danvas submissions grades --assignment-id 19838584 \
  --output grading/.../case1-graded-comments.csv \
  --json grading/.../case1-graded-comments.json
```

It should fetch `score`, `grade`, `graded_at`, `grader_id`, `submission_comments`, and optionally filter to graded submissions. We had to write a local script for this.

2. Add attachment integrity checks during `submissions media`

The Crawford workbook downloaded without error but was malformed. `danvas` could detect this cheaply for `.xlsx`, `.docx`, `.pptx`, and `.zip` by running a zip integrity check after download and writing a warning such as:

```text
WARNING: downloaded file is not a valid OOXML zip: Crawford...xlsx
```

It could also store that status in the `.info.json`.

3. Add a repair/provenance-friendly replacement workflow

A small helper could support:

```bash
danvas submissions replace-local-file \
  --original Crawford...xlsx \
  --replacement ~/Downloads/CaseStudy1.xlsx \
  --backup-suffix .corrupt-original
```

This is not a Canvas operation, just local filing hygiene. It would prevent overwriting evidence without keeping the original.

4. Add a submission manifest

After downloading submissions, `danvas` should write a top-level manifest like:

```text
Case_Study_1/submissions-manifest.csv
```

with student, Canvas user ID, submission ID, attempt, submitted_at, attachment filenames, local paths, content type, file size, download status, and integrity status. The sidecar `.info.json` files are useful, but a manifest would make grading workflows much easier.

5. Add `--only-graded` / `--include-grades` options to media download

For workflows like this one, it would be useful to download all submissions but also annotate which ones are graded, or download just graded submissions for audit:

```bash
danvas submissions media --assignment-id ... --include-grades
danvas submissions media --assignment-id ... --only-graded
```

6. Preserve comments separately from media

`submissions media` downloads attachments and media comments, but text comments are not emitted as a readable report. A companion `submission-comments.csv/json` would be useful even when not pulling grades.

The highest-value changes are the grade/comment pull command and OOXML integrity checks. Those would have eliminated most of the custom scripting and caught Crawford’s bad workbook immediately.
