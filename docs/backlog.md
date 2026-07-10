# danvas Backlog

Last consolidated: 2026-07-10.

This document is the planning backlog for `danvas`. It distinguishes the shipped
0.6.0 surface from genuine follow-on work. The lightweight implementation specs
in `docs/sprints/` are the durable record for the July 2026 feature sequence;
older pre-0.6 planning notes remain available in git history.

## 0.6.0 Implementation Record

The following feature slices were implemented and locally verified in order on
2026-07-10:

| Slice | Specification | Commit |
|---|---|---|
| Transaction-safe grade patching and cleanup | `docs/sprints/01-transaction-safe-grades.md` | `3db0c71` |
| Override-aware assignment snapshots and status | `docs/sprints/02-override-aware-assignments.md` | `6906957` |
| Submission evidence and metadata exports | `docs/sprints/03-submission-evidence.md` | `c9a6f11` |
| Canvas Pages V1 and V2 | `docs/sprints/04-canvas-pages-v1.md`, `docs/sprints/04-5-canvas-pages-v2.md` | `d49af90` |
| Canvas-facing source linting | `docs/sprints/05-source-lint.md` | `ea00d20` |
| Sprint documentation | `docs/sprints/` | `c5fe6fa` |

Ruff, ty, and the full pytest suite passed for the combined implementation. The
INSY 7970 Page fixture passed local rendering/restricted-CSS checks and the
explicitly approved live draft-to-published acceptance sequence.
The implementation is published on `origin/main` and tagged `v0.6.0` at
`05201fa`. GitHub Actions passed for that exact commit, and the global CLI was
reinstalled non-editably from the tag and smoke-tested locally.

## Delivered Baseline

These features are considered delivered enough that they should not remain as
open sprint goals. Future work can extend them, but the core backlog item is
closed.

| Area | Delivered by | Remaining follow-up, if any |
|---|---|---|
| Expanded course snapshot | `danvas refresh`, schema version 4 | Add sections/enrollments if roster workflows need them. |
| Override-aware assignment status | schema-v3 snapshot, `danvas assignments overrides` | Snapshots remain redacted; membership exports are explicit private artifacts. |
| Submission evidence exports | `danvas submissions export/grades/media` | Local replacement provenance remains optional future work. |
| Transaction-safe grade patches | `danvas grades post/clear/comments/verify` | Continue field-testing exact comment replacement and rollback use. |
| Canvas Pages bounded workflow | `danvas pages list/export/sync/render/css-check/create/update/verify`, schema-v4 status | Assets, rename/delete, broad upsert, and broader compatibility profiles remain deferred. |
| Canvas-facing source lint | `danvas sources lint` | External HTTP checking and automatic rewriting remain deferred. |
| Read-only Canvas/local status | `danvas status` | Continue refining next-action hints as new source workflows land. |
| Refresh diff | `danvas refresh --diff` | Plain diff remains terminal-first; report output is available through explicit report options. |
| Local source discovery | `danvas.sources` plus `[sources.<kind>]` config | Continue reusing in future source-aware commands. |
| Quiz shell awareness | `danvas status` | Do not compare quiz question bodies unless snapshots later include item data. |
| QTI import, publish, verify | `danvas quiz import-qti` | Resolve assignment groups by configured name, if useful. |
| Canvas Files upload v1 | `danvas files upload` | Markdown asset rewriting and optional folder creation remain separate future work. |
| Targeted file download/compare | `danvas files download-one`, `danvas files compare` | One-file explicit download, metadata compare, and SHA-256 compare against a supplied downloaded Canvas file are delivered; Office package-part comparison is deferred. |
| File inventory ignore rules | `danvas files inventory`; `[files.inventory] ignore` | Configurable local-scan ignores are delivered; keep future inventory filtering scoped to local generated/cache noise. |
| Generated report runs | `danvas.reports`; adopted by report-producing commands | Keep future verify/reconcile/compare/readback commands report-first unless they are raw exports or downloads. |
| Report polish | status next actions, file diagnostics, assignment-audit notes | Continue improving command-specific reports as field use reveals friction. |
| Mutation banners | shared guardrail pattern | Apply consistently to future mutating commands. |

Current command families include:

- `init`, `refresh`, `status`, `courses`, `roster`
- `auth doctor`
- `assignments export/overrides/create/verify/update/upsert/audit`
- `gradebook check/audit`
- `quiz analysis/import-qti`
- `submissions export/grades/media/feedback`
- `grades post/clear/comments/verify`
- `discussions export/sync-prompts/score`
- `announcements create/export/latest/sync/verify/update`
- `pages list/export/sync/render/css-check/create/update/verify`
- `sources lint`
- `files inventory/download/download-one/compare/upload`
- `reports list/latest`
- `recordings panopto-captions`

## Merged Sprint 2 And 3 Status

The original sprint 2 and sprint 3 plans are now merged into this backlog. Use the
candidate sections below for new sprint planning rather than treating the old
sprint sequence as canonical.

| Original plan item | Current status | Backlog location |
|---|---|---|
| Sprint 2 overall: grouped case assignment workflow | Partial | Core work is Sprint Candidate E; `files upload` is delivered; due-date ergonomics and transcript filing are smaller backlog items. |
| Sprint 3 overall: safe updates and round-trip verification | Partial | Core update/readback work is split across Sprint Candidates C and D; report foundations are delivered; file compare/report follow-ons are Candidate B. |
| Sprint 2: groups categories/import/verify | Not started | Sprint Candidate E. |
| Sprint 2: group planning from roster | Not started | Sprint Candidate E. |
| Sprint 2: seeded discussion creation | Not started | Sprint Candidate E plus Recent Field-Observed Workflow Gaps; now useful beyond the grouped-case workflow. |
| Sprint 2: basic `files upload` | Done | Delivered Baseline; future work is Markdown asset rewriting and optional explicit folder creation. |
| Sprint 2: due-date ergonomics | Done | Smaller Backlog Items; date-only assignment fields are delivered. |
| Sprint 2 stretch: transcript filing helper | Not started | Smaller Backlog Items. |
| Sprint 3: assignment update/upsert | Done | Candidate D; assignment create writes source-map provenance, update is live with readback verification, and upsert plans then requires `--confirm create` or `--confirm update` for live mutation. |
| Sprint 3: announcement/discussion update pattern | Partial | Sprint Candidate D; announcement update is delivered, discussion update remains deferred until needed. |
| Sprint 3: readback verification | Partial | Delivered for assignment create/update/upsert, announcement update, grade mutation verification, and bounded Page create/update; not yet broad across every write workflow. |
| Sprint 3: round-trip metadata | Done | Sprint Candidate C; `.danvas/source-map.json` design and helpers are delivered for current update workflows. |
| Sprint 3: Markdown asset rewriting | Not started | Sprint Candidate D, building on delivered `files upload`. |
| Sprint 3: single-file download and compare | Done | Candidate B; `files download-one`, `files compare` metadata, and optional checksum against a supplied downloaded Canvas file are delivered. |
| Sprint 3: file inventory report improvements | Done | Candidate B; report-run foundation, filename diagnostics, targeted metadata compare, downloaded-file checksum compare, and configurable local ignore rules are delivered. |
| Sprint 3 stretch: human-readable operation reports | Partial | Delivered for several report-run commands; Candidate B keeps report consistency work alive for new commands. |
| Sprint 3 beyond: rubric support | Deferred | Smaller Backlog Items; wait until update/upsert behavior is stable. |
| Sprint 3 beyond: activity logging | Not recommended as a sprint | Not Recommended Or No Longer Relevant. |
| Sprint 3 beyond: live Canvas gradebook export/download | Not recommended for current planning | Not Recommended Or No Longer Relevant. |
| Sprint 3 beyond: `gradebook.py` cleanup | Not a product backlog feature | Treat as opportunistic maintenance, not sprint scope. |

### Done From Sprint 2/3

- `danvas files upload` is delivered as the Sprint 2 file-upload goal.
- Report-run infrastructure and human-readable reports are substantially
  delivered beyond what Sprint 3 originally listed as stretch scope.
- File inventory has improved diagnostics for filename-only matches, including
  local size and mtime data.

### Partially Delivered From Sprint 2/3

- File inventory/report improvements are delivered for the current Candidate B
  scope: report-run output, targeted metadata compare, optional checksum against
  a supplied downloaded Canvas file, configurable local ignore rules, and file
  diagnostics are in place. Office package-part comparison is deferred out of the
  current Candidate B scope.
- Human-readable operation reports are partial: several report-producing commands
  now emit Markdown/JSON report runs; future verify, reconcile, compare, and
  readback commands should start with report-run output.
- Sprint 2's grouped-case workflow is partial only because prerequisites landed:
  snapshots include group-category summaries, mutation banners exist, and QTI
  import progress polling can inform future group-import polling. The actual
  `groups` command family has not started.

## Delivered: 0.6.0 Release And Documentation Cleanup

Theme: make the local release state durable, pushed, and documented before
starting a larger new feature.

Why this should come first:

- `PROJECT_CONTEXT.md` and this backlog now describe the local planning state, but
  the pushed repo and CI still need to catch up.
- External skill docs need explicit checking after command-surface or behavior
  changes because they live outside this repo.

Status (2026-07-10): done. The sprint-aligned commits are on `origin/main`, CI
passed at `05201fa`, the annotated `v0.6.0` tag points to that commit, the global
CLI was reinstalled non-editably from the tag, and repo/external skill docs were
reconciled.

Completed scope:

- Push local commits and confirm GitHub Actions.
- Tag the green revision as `v0.6.0`.
- Keep `PROJECT_CONTEXT.md` and `docs/backlog.md` current when release status
  changes during close-out.
- Recheck the updated external Codex teaching skill docs after any future
  command-surface change:
  - `/Users/djo/.codex/skills/teaching-danvas/SKILL.md`
  - `/Users/djo/.codex/skills/teaching-danvas/references/danvas-commands.md`

Definition of done:

- `origin/main` contains the intended release commits.
- CI is green.
- Durable docs reflect the final release/tag state.
- External skill docs are either confirmed current or updated.

## Sprint Candidate B: Report Workflow Follow-Ons

Theme: make generated reports easier to find, cite, and use as operational
evidence.

Recommended goals:

1. Add report discovery commands.

   ```bash
   danvas reports list
   danvas reports latest
   danvas reports latest status
   danvas reports latest files-inventory
   ```

   Status: delivered.

   Desired behavior:

   - List report directories under `.danvas/reports/`.
   - Read `manifest.json` when present and summarize command, generated time,
     status, private-data classification, course ID, and produced files.
   - Refuse to infer too much from malformed report directories; label them
     clearly as missing or invalid manifests.
   - Support JSON output for handoffs and tests.

2. Make `refresh --diff` reportable.

   ```bash
   danvas refresh --diff --report-root .danvas/reports
   ```

   Status: delivered.

   Desired behavior:

   - Preserve current plain `danvas refresh --diff` terminal behavior.
   - When report options are passed, write `manifest.json`, `refresh-diff.json`,
     and `refresh-diff.md`.
   - Include old/new snapshot timestamps, changed sections, and schema-version
     compatibility status.
   - Keep `.danvas/course.json` as the snapshot source of truth; reports are
     evidence, not replacement snapshots.

3. Continue report output consistency for future commands.

   Status: delivered as a standing engineering rule in `PROJECT_CONTEXT.md`
   under "Report Output Contract".

   Desired behavior:

   - Classify new commands as report-run-first, explicit-output, or stdout-first
     before implementation.
   - New verification, reconciliation, compare, and dry-run/readback commands
     should be report-run-first unless they are raw exports or downloads.
   - Raw rosters, gradebook exports, submission downloads, files downloads, and
     captions should keep explicit output paths by default.
   - Do not add a common report `--overwrite`; report directories should remain
     append-only evidence.

4. Add targeted file comparison improvements.

   ```bash
   danvas files download-one --course-id 1742719 --file-id 284879389 --output /private/tmp/example.canvas.pptx
   danvas files compare --course-id 1742719 --file-id 284879389 --local content/slides/example.pptx
   ```

   Status: delivered for current scope. The only item not implemented is Office
   ZIP package-part comparison, which is intentionally deferred as a future
   optional deep-inspection feature.

   Delivered in B.3a: `danvas files compare` resolves a Canvas file by
   `--file-id` or exact `--canvas-path`, compares Canvas metadata against one
   local file, prints a terminal summary, and writes `files-compare.json`,
   `files-compare.md`, and `manifest.json` as a report run when enabled.

   Delivered in B.3b: `danvas files download-one` writes exactly one Canvas file
   to an explicit output path, and `--downloaded-canvas PATH` adds SHA-256
   comparison against a supplied downloaded Canvas file without downloading
   anything implicitly.

   Delivered in B.3c: `danvas files inventory` excludes generated/cache/archive
   paths by default and supports `[files.inventory] ignore` for project-specific
   local-scan noise.

   Desired behavior:

   - Download exactly one Canvas file by file ID or by an unambiguous Canvas
     folder path. Delivered.
   - Keep `files download-one` explicit-output, not report-run-first: require an
     output path, refuse overwrite unless `--overwrite`, and print metadata that
     can be reused with `files compare`. Delivered.
   - Refuse ambiguous path matches unless a file ID is supplied. Delivered for
     `files compare` and `files download-one`.
   - Compare Canvas metadata against a local file by filename, size, content type,
     and updated time diagnostics. Delivered.
   - Compare file contents by SHA-256 only when a downloaded Canvas-side file is
     supplied with `--downloaded-canvas`. Delivered.
   - For Office files, optionally compare internal ZIP entries and report added,
     missing, and changed package parts. Not implemented; intentionally deferred
     as an explicit future option such as `--office-parts` only if basic compare
     workflows need it.
   - Improve `files inventory` ignore rules for generated/cache/archive paths such
     as `.danvas/`, `_archive/`, rendered artifacts, and local scratch outputs.
     Delivered in B.3c with `[files.inventory] ignore` plus built-in generated
     path defaults.

Definition of done:

- Report discovery works against real and fixture `.danvas/reports/` directories.
- `refresh --diff` can write a report run without changing its default behavior.
- README and external skill docs document the new report and compare commands.

## Sprint Candidate C: Local Source Sync And Readback

Theme: close the gap between status reports and maintainable local sources.

Storage boundary for this sprint:

- `.danvas/` is generated operational state and evidence: snapshots, report runs,
  manifests, dry-run/readback reports, and explicit generated outputs.
- `content/` is authored instructional source. Sync commands may create missing
  Markdown files there only when explicitly pointed at a content output
  directory.
- `grading/` is private grading workflow material and should not become a default
  report-run destination.
- Do not use `.danvas/` as a staging area for files that later become authored
  course sources. If Canvas content should become local source, write it directly
  to the requested `content/...` destination with overwrite guards.

Recommended goals:

1. Add Canvas-to-local source sync helpers for Canvas-only instructional content.

   ```bash
   danvas announcements sync --output-dir content/announcements --dry-run
   danvas discussions sync-prompts --output-dir content/discussions --dry-run
   ```

   Status: delivered. `danvas announcements sync` and `danvas discussions
   sync-prompts` create report-first plans for Canvas-only instructional content
   and can create missing local Markdown files without overwriting existing
   authored sources.

   Desired behavior:

   - Create missing Markdown files with front matter from Canvas announcements or
     instructor-authored discussion prompts.
   - Include stable Canvas IDs, URLs, titles, publish/lock state, and dates where
     available.
   - Generate safe numbered filenames and refuse to overwrite existing files.
   - Do not provide broad `--overwrite` for source sync in the first
     implementation. Existing targets should be reported, not modified.
   - Live sync should write only new files whose target path does not exist.
   - If a generated source target already exists, mark it as `skipped_exists`;
     if an existing file appears to match the Canvas ID, mark it as
     `skipped_known_local`; if a title/path collision appears unrelated, mark it
     as `conflict` and require a user-chosen path or later update workflow.
   - Skip student replies and ordinary discussion participation by default.
   - Use report runs for dry-run/readback evidence.

   Expected plan statuses:

   - `would_create`
   - `created`
   - `skipped_exists`
   - `skipped_known_local`
   - `conflict`
   - `error`

2. Add assignment and announcement verification commands.

   ```bash
   danvas assignments verify content/cases/case-1.md
   danvas assignments verify --assignment-id 19862404
   danvas announcements verify content/announcements/04-case-open.md
   danvas announcements latest --course-id 1742719 --format markdown
   ```

   Status: done. Delivered: `danvas announcements verify SOURCE` verifies one
   local announcement source against Canvas by `canvas_id` front matter or
   `--announcement-id`, and `danvas assignments verify SOURCE` verifies one
   local assignment source against Canvas by `assignment_id`/`canvas_id`/`id`
   front matter or `--assignment-id`. Both commands write report evidence.
   `danvas announcements latest` exports the latest Canvas announcement as
   Markdown or JSON without mutating Canvas.

   Desired behavior:

   - Resolve Canvas objects by explicit ID from sidecar metadata, front matter, or
     CLI option. Delivered for announcements and assignments.
   - Allow title matching only with an explicit flag and refuse ambiguous matches.
   - Compare stable fields: title, URL, published state, due/unlock/lock dates,
     points, assignment group, submission type, group category, and relevant
     grading settings.
   - For announcements, support a safe latest-announcement export before posting a
     follow-up.

3. Design round-trip metadata before broad update/upsert work.

   Status: done. Round-trip metadata should use a project-level sidecar source
   map as the preferred durable provenance store, while continuing to support
   optional front matter IDs for course-specific sources and existing synced
   files.

   Proposed source map:

   - Path: `.danvas/source-map.json`.
   - Ownership: generated operational state, not authored course content.
   - Key: source kind plus project-relative source path.
   - Schema: versioned JSON with `schema_version`, `course_id`,
     `generated_at`, and a `sources` list.
   - Source entry fields:
     - `kind`: `assignment`, `announcement`, `discussion`, or `file`.
     - `path`: project-relative local source path.
     - `canvas`: stable Canvas ID, stable HTML URL or Canvas path, and safe
       object timestamps where available.
     - `last_posted`: command name, timestamp, danvas version, comparable field
       snapshot, and body/file hashes when useful.
   - Exclusions: no Canvas verifier/download URLs, access tokens, roster data,
     submissions, grades, private comments, or full student content.

   ID resolution order for future update/upsert commands:

   1. Explicit CLI option, such as `--assignment-id`.
   2. Front matter ID, such as `assignment_id` or `canvas_id`.
   3. `.danvas/source-map.json` entry for the source path.

   Safety rules:

   - If front matter and source-map IDs conflict, fail unless an explicit CLI ID
     resolves the conflict.
   - Dry-runs and read-only verification commands may read the source map but
     must not update it.
   - Live create/update/sync commands should update the source map only after
     the Canvas write succeeds and readback confirms the object.
   - Source-sync commands may still write front matter IDs for newly created
     course-specific Markdown, but reusable authoring templates should prefer
     the sidecar map.
   - Do not store full Markdown/HTML bodies in the source map. Store hashes and
     the small comparable metadata subset needed to detect likely drift.

   Minimal example:

   ```json
   {
     "schema_version": 1,
     "course_id": 1742719,
     "generated_at": "2026-06-24T12:00:00-05:00",
     "sources": [
       {
         "kind": "assignment",
         "path": "content/cases/case-1.md",
         "canvas": {
           "id": 19862404,
           "url": "https://auburn.instructure.com/courses/1742719/assignments/19862404"
         },
         "last_posted": {
           "command": "assignments update",
           "posted_at": "2026-06-24T12:00:00-05:00",
           "danvas_version": "0.3.0",
           "fields": {
             "title": "Case 1",
             "points_possible": 100,
             "published": true
           },
           "body_sha256": "..."
         }
       }
     ]
   }
   ```

Definition of done:

- `status` next-action hints point to implemented sync/verify commands where
  applicable.
- Sync and verify outputs produce report runs.
- Round-trip metadata format is documented before update/upsert writes are added.
  Delivered as the `.danvas/source-map.json` design above.

## Sprint Candidate D: Safe Update And Upsert

Theme: move from create-only workflows to controlled maintenance without
duplicating Canvas objects.

Recommended goals:

0. Implement source-map helpers for safe update workflows.

   Status: done. `.danvas/source-map.json` is now backed by reusable helpers for
   load, write, project-relative source keys, ID resolution, and
   front-matter/source-map conflict detection. Dry-runs and read-only commands
   can read the map; live assignment create and update write it only after
   Canvas readback succeeds.

1. Add conservative assignment update.

   ```bash
   danvas assignments update SOURCE.md --dry-run
   ```

   Status: done for existing assignments. `danvas assignments update SOURCE.md`
   resolves by explicit `--assignment-id`, assignment ID front matter, or
   `.danvas/source-map.json`; `--match-title` enables exact-title lookup only
   when no ID is available. Dry-run writes a field-by-field report without
   Canvas mutation. Live mode updates supported assignment fields, reads Canvas
   back, writes report evidence, and updates the source map after verified
   readback. `danvas assignments upsert SOURCE.md --dry-run` plans whether an
   upsert would update an ID/source-map/title match or create a new assignment;
   live upsert requires `--confirm create` or `--confirm update` matching the
   planned action.

   Desired behavior:

   - Match by Canvas ID from sidecar/front matter or `--assignment-id`.
   - Permit title matching only behind an explicit flag.
   - Show a field-by-field before/after diff before live writes.
   - Update supported fields without deleting unrelated Canvas state.
   - Refuse ambiguous matches and missing IDs unless the user explicitly opts into
     title lookup.

2. Extend the pattern to announcements and discussions after assignment update is
   stable.

   Status: partial. `danvas announcements update SOURCE.md` is delivered for
   existing announcements. It resolves by explicit `--announcement-id`,
   `canvas_id` front matter, or `.danvas/source-map.json`; it does not match by
   title and does not create missing announcements. Dry-run writes a
   field-by-field report without Canvas mutation. Live mode updates only the
   supplied announcement fields and body, reads Canvas back, writes report
   evidence, and updates the source map after verified readback. Discussion
   update remains deferred until a concrete course workflow needs it.

3. Add Markdown asset rewriting on top of `files upload`.

   Status: not started.

   Desired behavior:

   - Scan Markdown-backed assignments, announcements, and discussions for local
     asset links.
   - Upload local files to configured Canvas Files folders.
   - Rewrite links in the Canvas-bound HTML or generated Markdown output without
     mutating source files unless explicitly requested.
   - Preserve verifier/download URL secrecy.

Definition of done:

- Dry-run diffs are clear enough to review before mutation.
- Live updates have readback verification.
- Report runs capture update/readback evidence.

## Sprint Candidate E: Groups And Grouped Case Assignment Workflow

Theme: make grouped case assignment setup operationally safe from roster to
Canvas verification.

Recommended goals:

1. Add Canvas group category and membership commands.

   ```bash
   danvas groups categories --course-id 1742719
   danvas groups categories rename --course-id 1742719 154244 "Case 1 Groups" --dry-run
   danvas groups import --course-id 1742719 --category-id 154244 content/cases/case-1-groups.csv --dry-run
   danvas groups verify --course-id 1742719 --category-id 154244 --expected content/cases/case-1-groups.csv
   ```

   Desired behavior:

   - List group categories with IDs, names, self-signup settings, group counts, and
     membership counts.
   - Create or rename categories only through explicit mutating commands.
   - Import Canvas-compatible group CSVs into a chosen category.
   - Poll Canvas progress objects and report status, progress ID, created/updated
     counts, user counts, and errors.
   - Verify actual group names and memberships against an expected CSV.
   - Treat roster and membership outputs as course-private.

2. Add local group planning.

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

   - Read a `danvas roster` export or a Canvas group-import template.
   - Support group size, number of rounds, balancing by section or another roster
     column, and minimizing repeated pairings.
   - Emit Canvas import-compatible CSVs plus validation summaries.
   - Report repeated pairings, unassigned students, unresolved rows, and balance
     exceptions.
   - Stay local-only; never create Canvas groups from the planner alone.

3. Add graded and seeded discussion creation from Markdown as a general
   discussion workflow.

   ```bash
   danvas discussions create --course-id 1742719 discussion.md --seed-replies --dry-run
   danvas discussions create-seeded --course-id 1742719 topic.md --replies replies.md --dry-run
   ```

   Desired behavior:

   - Accept one Markdown source with front matter for the root topic and
     `--- reply ---` sections for instructor-seeded prompt replies, or accept a
     root topic source plus a separate seeded-replies source.
   - Create the discussion topic and top-level instructor replies in one command.
   - Preserve graded discussion assignment metadata.
   - Post seed replies in the intended Canvas display order, accounting for the
     observed reverse-order display behavior when needed.
   - Return topic ID, assignment ID, URL, and seeded entry IDs.
   - Write `.danvas/source-map.json` provenance for the topic and seeded entries
     after successful readback.
   - Verify the created topic and prompt replies after posting.

Definition of done:

- A grouped case assignment can be planned, imported, verified, and connected to
  the correct `group_category_id` without raw Canvas API scripts.
- Multi-step writes print mutation banners, progress IDs, and verification
  recommendations.
- Skill docs are updated because the command surface changes materially.

## Delivered In 0.6.0: Submission And Grade Safety

Implementation status (2026-07-10): goals 1-4 and 6 are delivered. This section
retains the field rationale behind the shipped behavior. The optional local
replacement helper in goal 5 is the only remaining product follow-up.

Theme: reduce custom scripting and catch bad local submission artifacts earlier.

Recommended goals:

1. Add read-only grade/comment pull.

   ```bash
   danvas submissions grades --assignment-id 19838584 \
     --output grading/case1-graded-comments.csv
   ```

   Status: delivered. Choose a `.csv` or `.json` output path; one invocation
   writes one explicit private export.

   Desired behavior:

   - Fetch `score`, `grade`, `graded_at`, `grader_id`, text comments, attempt,
     workflow state, late/missing flags, and attachment counts/names.
   - Default to sanitized output and require an explicit option for raw Canvas
     payloads.
   - Support `--only-graded` or equivalent filtering.

2. Add attachment integrity checks to `submissions media`.

   Status: delivered.

   Desired behavior:

   - Validate `.zip`, `.xlsx`, `.docx`, and `.pptx` downloads as ZIP/OOXML
     containers.
   - Write integrity status and warning details into sidecar `.info.json`.
   - Emit clear terminal warnings for malformed downloads.

3. Add a submission manifest.

   Status: delivered.

   Desired behavior:

   - Write a top-level `submissions-manifest.csv` or JSON file after media
     downloads.
   - Include student, Canvas user ID, submission ID, attempt, submitted time,
     attachment filenames, local paths, content type, file size, download status,
     and integrity status.

4. Preserve text comments separately from media.

   Status: delivered.

   Desired behavior:

   - Emit `submission-comments.csv` and/or JSON when downloading media or pulling
     grades.
   - Keep student data clearly marked as private.

5. Add a provenance-friendly local replacement helper only if malformed-download
   recovery keeps recurring.

   Status: deferred pending repeated field need.

   ```bash
   danvas submissions replace-local-file \
     --original Crawford.xlsx \
     --replacement ~/Downloads/CaseStudy1.xlsx \
     --backup-suffix .corrupt-original
   ```

   Desired behavior:

   - Treat this as local filing hygiene, not a Canvas operation.
   - Preserve the original file with a clear suffix before copying the replacement.
   - Update or write local provenance metadata so grading evidence is not silently
     overwritten.

6. Add grade-patch safety and comment-management improvements from the Case Study
   1 cross-check workflow.

   Status: delivered through online baseline preflight, rollback artifacts,
   targeted clearing, exact-match or explicit-ID instructor-comment cleanup,
   stable submission manifests, and live readback verification.

   Session note:

   - Grade comments should support replace/delete for instructor-owned comments.
     The Case Study 1 workflow required manually deleting bad comments in Canvas.
     `danvas grades post` can add comments, but there should be a safe way to list
     and delete or replace comments authored by the current user, ideally scoped by
     assignment/submission/comment IDs.
   - Grade patch preflight should compare against a baseline. Before posting,
     danvas could validate original grade, proposed grade, numeric delta, and any
     "additional deduction" language in the comment. That would have caught the
     Royster/Reeves mismatch where the grade reflected `-9/-5` but the comment
     still said `14/10`.
   - `grades post` should create an automatic rollback CSV. Before live posting,
     it should save the exact current grades/comments for targeted rows as a
     rollback artifact.
   - Submission downloads should avoid nested duplicate folders. The
     `Case_Study_1/Case_Study_1` duplication was easy to miss. `danvas
     submissions media` should either flatten into the specified output directory
     or warn when the output path already looks like the assignment folder.
   - Sidecar metadata should avoid volatile resolved URLs. The `.info.json` files
     differed mostly because Canvas CDN tokens changed. Storing the stable Canvas
     file ID/download URL is useful; storing expiring signed URLs makes duplicate
     detection noisy.
   - A generated submission archive manifest would help. A `manifest.csv/json`
     with student, submission ID, filenames, hashes, download time, and source
     (`canvas` vs `manual_off_canvas_copy`) would make later review cleaner and
     reduce the need for ad hoc hash checks.

Delivered outcome:

- Case grading workflows no longer need a local script just to pull graded
  comments and grades.
- Bad Office/ZIP downloads are detected immediately.
- Download manifests make grading folders auditable without reading each sidecar.
- Grade patches are preflighted against current Canvas state, automatically
  rollbackable, and support safe cleanup of instructor-owned comments.

## Sprint Candidate G: Exam Reconciliation And Roster Sections

Implementation status (2026-07-10): metadata-only submission export,
override-aware redacted snapshots/status, and explicit private override
membership export are prerequisites already delivered in 0.6.0. The remaining
candidate is section-aware roster data plus report-first exam reconciliation.
Override mutation should be considered only after a concrete field workflow
justifies its additional privacy and write surface.

Theme: support multi-version exam reconciliation with explicit, private reports.

Recommended goals:

1. Add metadata-only submissions export.

   Status: delivered by `danvas submissions export`.

   ```bash
   danvas submissions export --assignment-id 19901542 --output .danvas/proctoru-submissions.json
   ```

   Desired behavior:

   - Include user ID, name, workflow state, submitted time, score, attempt,
     attachment count/names, late/missing flags, and optional submission history.
   - Default to sanitized private output and require `--save-raw` for raw payloads.

2. Add assignment override member export.

   Status: delivered for explicit private export. The example local override
   file and dry-run sync/update workflow below remain possible future extensions,
   not current command behavior.

   ```bash
   danvas assignments overrides --assignment-id 19901488
   ```

   Desired behavior:

   - Export override IDs, titles, due/unlock/lock dates, and member Canvas IDs.
   - Keep student membership private and explicit.
   - Support a local private override file referenced from the authored
     assignment source, for example:

     ```yaml
     # content/cases/case1-assignment.md
     availability_overrides_ref: grading/25-26.Su/assignment-overrides/case-study-1.yaml
     ```

     The referenced file should preserve the Canvas base window plus
     differentiated student windows:

     ```yaml
     assignment_id: 19838584
     source: content/cases/case1-assignment.md

     base:
       due_at: 2026-06-15T04:59:00Z
       lock_at: 2026-06-15T04:59:59Z

     overrides:
       - canvas_override_id: 900773
         title: "extension group 1"
         due_at: 2026-06-17T04:59:59Z
         lock_at: null
         assignees:
           canvas_user_ids: [123, 456]
     ```

   - Prefer `grading/<term>/assignment-overrides/` over `content/` for these
     records because override membership is student material.
   - Avoid student names in the override file by default; use Canvas user IDs
     or SIS IDs, and keep reports count-first unless member detail is explicitly
     requested.
   - Add a dry-run-first sync/update workflow for assignment overrides. Live
     writes should require explicit confirmation, especially for deleting
     Canvas overrides or changing assignee membership.

3. Make assignment status comparisons override-aware.

   Status: delivered for redacted schema-v3 snapshots, base-window comparison,
   and untracked-override reporting. Local override-file reconciliation remains
   future scope.

   Current problem:

   - `danvas refresh` and `danvas assignments export --full` request
     `include=["all_dates", "overrides"]`, but the simplified
     `.danvas/course.json` assignment rows drop `all_dates`.
   - `danvas status` compares local assignment front matter to Canvas top-level
     `due_at`/`unlock_at`/`lock_at`, which can be misleading when Canvas reports
     an override-derived top-level due date.
   - Example observed in INSY 6600 Case Study 1: the local source matched the
     Canvas `all_dates` base / "Everyone else" window, while Canvas top-level
     `due_at` reflected a later differentiated student window.

   Desired behavior:

   - Preserve a redacted override summary in `.danvas/course.json`, including
     `has_overrides`, `all_dates` window metadata, override IDs/titles, and
     assignee counts, but not student names by default.
   - When `all_dates` includes a base row, compare local assignment front matter
     against that base row rather than Canvas top-level date fields.
   - If Canvas has override windows but no local `availability_overrides_ref`,
     report "Canvas has untracked assignment overrides" separately from base
     assignment metadata mismatches.
   - If a local override reference exists, classify each override as exact,
     local-only, Canvas-only, or metadata/member mismatch.
   - Keep full override membership in the referenced private grading file or in
     explicit private reports, not in normal status output.

4. Include sections in roster and optionally `.danvas/course.json`.

   Status: not started; this is the first active goal in this candidate.

   Desired roster fields:

   ```text
   SectionID, SectionName, EnrollmentState, LastActivityAt
   ```

5. Add a report-first reconciliation command.

   Status: not started; build it after section-aware roster data.

   ```bash
   danvas exams reconcile \
     --roster .danvas/roster.csv \
     --variant in_class:assignment_override:19901488 \
     --variant zoom:override_or_submission:19901485 \
     --variant proctoru:submission:19901542 \
     --upload-assignment 19901660 \
     --upload-window-minutes 15
   ```

   Desired output:

   - `.md`, `.csv`, and `.json` report files in a report run.
   - Accounted/unaccounted students, overlaps, upload compliance, and late/missing
     upload status.
   - Private-data classification in `manifest.json`.

Definition of done:

- The observed Test 1 reconciliation workflow can be reproduced without direct
  Canvas API scripts.
- Student-identifying outputs are explicit and marked private.

## Sprint Candidate H: Canvas Pages Follow-Ons

Implementation status (2026-07-10): Sprints 4 through 7 deliver list/export,
rendering, restricted CSS, draft create/readback, body/publication-only update,
verification, local source linting, schema-v4 discovery/status, targeted
HTML/Markdown export, and non-overwriting Canvas-to-local source sync. Asset
upload/rewriting, deletion, rename, general upsert, and broader compatibility
profiles remain deferred.

Implementation status: source discovery/snapshot/status is delivered by Sprint 6;
safe Canvas-to-local source sync and targeted HTML/Markdown conversion are
delivered by Sprint 7. Asset handling and broader Page lifecycle/profile work
remain unscheduled.

Theme: manage student-facing Canvas Pages from durable local sources with the
same dry-run, verification, readback, and provenance safeguards used for
assignments and announcements.

The Additional Resources paths and names below are illustrative examples only.
The command family, renderer, compatibility rules, and tests must remain general
and must not branch on a course ID, Page title, filename, content phrase, CSS
class, or example-specific layout.

Why this belongs in its own command family:

- Canvas Pages are durable instructional content, not files or assignments.
- The Canvas API stores a Page body as HTML, while Markdown is the more useful
  local authoring format for most course repositories.
- Page titles determine Canvas URL slugs, so renames require stable ID-based
  resolution and explicit readback rather than title-only matching.
- Pages can be drafts, scheduled for publication, designated as a course front
  page, and linked from modules or other rich content. Those states should not
  be hidden inside a generic raw API command.

Delivered command set:

```bash
danvas pages list --course-id 1742812
danvas pages export --course-id 1742812 --output .danvas/pages.json
danvas pages render content/pages/example-page.md --output /tmp/example-page.html
danvas pages css-check content/pages/example-page.canvas.css
danvas pages create content/pages/example-page.md --dry-run
danvas pages verify content/pages/example-page.md
danvas pages update content/pages/example-page.md --dry-run
```

Current sync and future lifecycle command:

```bash
danvas pages sync --output-dir content/pages --format markdown --dry-run
danvas pages upsert content/pages/example-page.md --dry-run
```

Recommended goals:

1. Add read-only listing and export.

   Status: broad all-Pages JSON plus targeted single-Page HTML/Markdown export
   are delivered.

   Desired behavior:

   - `pages list` prints a compact table with page ID, title, Canvas URL/slug,
     published state, front-page state, scheduled publication, editing roles,
     editor type, and updated time.
   - `pages export` writes JSON for all Pages or one Page selected by `--page-id`
     or `--url`.
   - Page bodies should be omitted from broad list output unless explicitly
     requested with `--full`.
   - Preserve Canvas HTML in HTML exports. Treat HTML-to-Markdown conversion as
     a convenience representation that may be lossy, especially for embedded
     Canvas files, media, tables, and Rich Content Editor attributes.

2. Add Canvas-to-local source sync.

   Status: delivered in Sprint 7 with inventory-wide target planning,
   no-clobber writes, round-trip validation, and provenance recovery.

   ```bash
   danvas pages sync --output-dir content/pages --format markdown --dry-run
   danvas pages sync --output-dir content/pages --format html --dry-run
   ```

   Desired behavior:

   - Follow the announcement/discussion sync model: report first, create only
     missing local sources, and never overwrite an authored source.
   - Support `--format markdown|html`. Markdown should be the default for
     ordinary prose pages; HTML should be available when exact Rich Content
     Editor structure matters.
   - Use safe filenames derived from the Canvas page URL, with collision and
     existing-source statuses matching other sync commands:
     `would_create`, `created`, `skipped_exists`, `skipped_known_local`,
     `conflict`, and `error`.
   - Write stable page metadata in front matter where useful and source-map
     provenance after live source creation. Do not place volatile Canvas URLs,
     verifier URLs, or full bodies in `.danvas/source-map.json`.

3. Define the local Page source contract.

   Status: the conservative Markdown/native-HTML source contract, fragment
   renderer, matching-H1 handling, stable anchors, compatibility profile V1,
   and restricted `canvas_css` sidecar are delivered. Preview-document styling,
   scheduled publication, front-page mutation, and broader profiles remain
   deferred.

   Markdown example:

   ```yaml
   ---
   title: "Additional Resources"
   page_id: 1234567
   published: false
   front_page: false
   editing_roles:
     - teachers
   publish_at: null
   ---
   ```

   Desired behavior:

   - Treat Markdown as the normal authored source. Always render it to semantic
     HTML internally before sending `wiki_page[body]`, but do not require or
     create a tracked sibling `.html` artifact during create/update/upsert.
   - Add `pages render SOURCE` as a local-only inspection command that emits the
     exact Canvas-bound HTML fragment on request. `--output -` should print it;
     an explicit output path should write it. The default should not write into
     `content/` or update source-map provenance.
   - Accept `.html` as an optional native source for pages whose required
     structure cannot be represented cleanly in Markdown. Send an HTML source
     body without Markdown conversion, but still validate and normalize it
     before planning a Canvas write.
   - Use Canvas-safe, predictable Markdown conversion for headings, links,
     lists, tables, code blocks, and explicit heading IDs. Do not inject a full
     HTML document, stylesheet, scripts, or unsupported page-level metadata into
     the Canvas body.
   - Treat `title` as required. Support `page_id`/`canvas_id`, `published`,
     `front_page`, `editing_roles`, and `publish_at`. Default new pages to
     unpublished unless the source explicitly requests publication.
   - Keep `notify_of_update` an explicit CLI/source option defaulting to false;
     a routine content correction should not unexpectedly notify the class.
   - Reject `front_page: true` with `published: false`, or plan the required
     publication transition explicitly if Canvas permits it.

   HTML rendering and comparison rules:

   - The renderer should produce an HTML fragment suitable for
     `wiki_page[body]`, not a standalone document with `html`, `head`, or `body`
     wrappers.
   - Dry-run and verify reports should expose the rendered body hash and a
     readable normalized-body diff. An explicit `--save-rendered-html PATH` may
     preserve the planned/readback fragments for debugging, but report runs and
     normal source directories should not accumulate rendered copies by default.
   - Normalize insignificant differences introduced by Canvas, such as safe
     attribute ordering or Rich Content Editor metadata, without hiding removed
     elements, changed links, missing IDs, or meaningful text differences.
   - Pin or document the Markdown rendering profile so a danvas upgrade does not
     silently rewrite every Page. Renderer-version changes should be visible in
     dry-run reports.

   CSS policy:

   - Do not treat a linked stylesheet as part of an ordinary Canvas Page source.
     Canvas Pages are stored as HTML fragments inside the Canvas application,
     and account/theme CSS is outside the Page API and instructor-level course
     ownership.
   - Distinguish two stylesheet roles. Preview-only CSS belongs to the author's
     local preview workflow and is never sent to Canvas. `canvas_css` is a
     restricted sidecar declared in Page front matter; danvas validates it and
     compiles allowlisted declarations into inline `style` attributes in the
     Canvas-bound fragment.
   - Allow the source front matter to declare the restricted stylesheet and
     validation mode:

     ```yaml
     canvas_css: additional-resources.canvas.css
     css_policy: strict
     ```

   - Add a local validation command and integrate the same checks into render and
     write plans:

     ```bash
     danvas pages css-check content/pages/additional-resources.canvas.css
     danvas pages render content/pages/additional-resources.md --output -
     ```

   - Parse CSS with a structured CSS parser rather than regular expressions.
     Apply supported selectors to the rendered HTML with a real selector engine,
     then serialize the resulting inline declarations deterministically.
   - Maintain a versioned Canvas compatibility profile for supported elements,
     attributes, CSS properties, and value constraints. Record the selected
     profile version in dry-run/render reports so rule changes do not silently
     restyle existing Pages.
   - In strict mode, reject unsupported or unsafe constructs before a Canvas
     write. At minimum reject `@import`, `@font-face`, scripts, JavaScript URLs,
     external stylesheet links, unsupported at-rules, and selectors or values
     that cannot survive safe inlining. Warn or fail on pseudo-elements,
     pseudo-classes, media queries, CSS custom properties, and external asset
     URLs according to the documented profile.
   - Report unsupported properties and values, unused or unmatched selectors,
     conflicting declarations, selector-specificity surprises, and rules lost
     during inlining. Include basic accessibility diagnostics where they can be
     stated reliably, but do not present CSS validation as a complete
     accessibility audit.
   - Prefer semantic HTML that inherits Canvas typography and responsive styles.
     Restricted CSS is an escape hatch for useful presentation, not the default
     authoring model.
   - Run native `.html` source inline styles through the same compatibility
     validator. Reject `style` blocks, external stylesheet links, scripts, and
     JavaScript in the default source profile unless a future explicit mode has
     a justified Canvas-safe implementation.
   - Treat saved-page readback as the definitive compatibility check. After a
     live create or update, compare planned inline declarations with returned
     Canvas HTML and report every element, attribute, or style Canvas removed or
     changed. A static check should say "compatible with Canvas profile X," not
     claim that Canvas is guaranteed to preserve it.
   - Institution-wide Theme Editor CSS/JS is a separate administrative workflow
     and out of scope for `danvas pages`.

4. Add conservative create, verify, update, and upsert workflows.

   Status: create/readback/verify and body/publication-only update are delivered.
   Title/slug rename, front-page mutation, general upsert, and delete remain
   deliberately unsupported.

   Desired behavior:

   - `pages create SOURCE --dry-run` shows title, converted-body summary/hash,
     publish state, front-page state, editing roles, and scheduled publication.
   - Live create prints the Canvas mutation banner, creates the Page, reads it
     back, verifies stable fields and normalized body content, writes report
     evidence, and records `.danvas/source-map.json` provenance only after
     successful readback.
   - Resolve existing Pages by explicit `--page-id`, then front matter ID, then
     source-map ID. Update and verify do not title-match and never create a
     missing Page.
   - `pages verify SOURCE` compares title, normalized HTML body, publication
     state, stable slug/URL, and supported compatibility fields. Canvas-normalized
     attributes and inline styles are compared semantically.
   - `pages update SOURCE --dry-run` produces a field-by-field before/after
     report and accepts only body and publication-state changes.
   - Live update changes only those supported fields, reads the Page back, and
     does not alter title/slug, front-page state, module membership, or links
     elsewhere in the course.
   - A future `pages upsert` would need explicit create/update confirmation and
     separately designed rename behavior.
   - Do not add a broad delete command in the first implementation. Unpublishing
     is safer than deletion and can be handled as an explicit update.

5. Handle links and local assets deliberately.

   Status: same-page anchors are covered by the delivered renderer and tests.
   Local asset upload and Canvas-bound link rewriting remain deferred.

   Desired behavior:

   - Preserve ordinary external links and same-page anchors through Markdown
     conversion and Canvas readback.
   - Detect local relative asset links before a write. In the first
     implementation, fail with a clear message or require an explicit
     `--allow-unresolved-assets`; do not silently publish broken links.
   - Later integrate with the planned Markdown asset-rewriting workflow on top
     of `danvas files upload`, rewriting only the Canvas-bound HTML and leaving
     the authored Markdown unchanged.
   - Report course-relative Canvas links and embedded file/media references in
     verification output without persisting signed or verifier URLs.

6. Integrate Pages with snapshots, source discovery, and status.

   Status: delivered in Sprint 6 through schema-v4 snapshots, Page source
   discovery, provisional title candidates, body-hash comparison, and status
   next actions.

   Desired behavior:

   - Add Page summaries to `.danvas/course.json` without including full bodies by
     default. Preserve page ID, title, URL/slug, published/front-page state,
     publish time, editing roles, editor type, updated time, and an optional
     normalized body hash.
   - Add `[sources.pages]` configuration with a default such as
     `content/pages/*.{md,html}`.
   - Extend `danvas status` with Pages classifications and next actions:
     exact, metadata mismatch, body mismatch, local-only, and Canvas-only.
   - Keep Pages out of assignment/discussion comparisons even when a Page is
     linked from a module.

### Future V3: Pandoc-Flavored Markdown Authoring Profile

- Add an explicit extended Markdown profile for authors who need structural
  features beyond the conservative default Markdown renderer:

  ```yaml
  markdown_profile: pandoc
  canvas_css: resources.canvas.css
  ```

- Keep `.md` as the source format. This is Pandoc-flavored Markdown support, not
  a Quarto `.qmd` workflow and not an executable-document feature.
- Define and pin the exact Pandoc extensions in a versioned renderer profile.
  Candidate extensions include fenced divs, bracketed spans, header attributes,
  link attributes, definition lists, pipe or grid tables, and explicit raw HTML
  blocks where the Canvas compatibility profile allows them.
- Use fenced divs, spans, classes, and IDs as general authoring hooks that can be
  consumed by restricted `canvas_css` and then safely inlined. Do not introduce
  Page-specific syntax for layouts, callouts, resource indexes, or other content
  patterns that Pandoc can already express structurally.
- Continue producing an HTML fragment rather than a standalone document. Run the
  result through the same Canvas element/attribute/style validator, asset checks,
  CSS inliner, dry-run reports, and live readback verification as ordinary
  Markdown and native HTML sources.
- Treat raw HTML as input to validation, not an escape hatch around it. Reject or
  report elements and attributes outside the selected Canvas compatibility
  profile.
- Detect Pandoc availability and version explicitly. Record the Pandoc version,
  enabled extension set, and danvas renderer-profile version in render and
  readback evidence so upgrades cannot silently rewrite every Page.
- Add generic fixtures for fenced divs, spans, explicit and duplicate heading
  IDs, same-page links, definition lists, tables, raw HTML, and CSS selectors
  targeting author-supplied classes. Do not key behavior to a course ID, source
  path, Page title, or one field-validation Page.
- Keep Quarto, Jupyter/Knitr execution, shortcodes, Bootstrap themes, JavaScript
  widgets, tabsets, citations requiring browser dependencies, generated resource
  directories, and full-document template extraction out of scope. Reconsider a
  Quarto adapter only if a concrete Canvas workflow later requires computational
  document rendering rather than ordinary Page authoring.

Report and safety requirements:

- Dry-run, sync, verify, update, upsert, and live readback should use report
  runs with Markdown and JSON evidence.
- Body comparisons should store hashes and concise normalized diffs rather than
  duplicate full student-facing content in source-map metadata.
- All live writes print the standard Canvas mutation banner.
- No command publishes, schedules, renames, or changes the course front page
  unless that state is explicit in the reviewed plan/source.
- Skill documentation must be updated when this command family ships.

Definition of done for the remaining candidate:

- The already-delivered bounded Page workflow remains backward compatible and
  course-agnostic.
- Canvas-only Pages can be inventoried and safely synced to missing local
  Markdown or HTML sources without overwriting authored files.
- Any later rename, front-page, upsert, or asset behavior is introduced through
  explicit plans and readback rather than silently widening `pages update`.
- `danvas refresh` and `danvas status` can identify local-only, Canvas-only, and
  drifted Page sources.

## Recent Field-Observed Workflow Gaps

These items came from the INSY 7750 Unit 4 discussion workflow after the
2026-06-24 backlog consolidation. Items 3 and 4 shipped in 0.6.0, and item 5 is
now reflected in the external skill docs. Items 1 and 2 remain product work.

1. Generalize seeded discussion creation beyond grouped cases.

   Existing related item: Sprint Candidate E.3. The new evidence is that seeded
   prompts are useful for ordinary course discussions, not just grouped-case
   setup. The command should replace course-specific posting scripts, support
   dry-run/readback, preserve graded-discussion assignment metadata, write source
   map provenance, and return topic, assignment, URL, and entry IDs.

2. Add safe discussion source update and verification.

   ```bash
   danvas discussions verify content/discussions/unit-4.md --discussion-id 10819092
   danvas discussions update content/discussions/unit-4.md --discussion-id 10819092 --body-only --dry-run
   ```

   Desired behavior:

   - Compare local discussion Markdown/front matter to Canvas topic state and
     the associated graded assignment: title, body, due date, points, published
     state, assignment linkage, and Canvas URL.
   - Compare seeded prompt count and headings when entry IDs or prompt source
     metadata are available.
   - Support scoped updates such as `--body-only` that do not delete, reorder,
     or repost existing prompt replies or student responses.
   - Resolve IDs through explicit CLI options, front matter, or
     `.danvas/source-map.json`, following the assignment/announcement update
     safety model.
   - Write report-run evidence for dry-runs, mismatches, live readback, and
     verification.

3. Add a general Canvas-facing source linter.

   Status: delivered by `danvas sources lint` in 0.6.0. External HTTP checking
   and automatic rewriting remain out of scope.

   ```bash
   danvas sources lint content/discussions/*.md
   danvas sources lint --kind discussion --project-root .
   ```

   Desired behavior:

   - Check authored Markdown before Canvas posting or update, not only after a
     mismatch is discovered in Canvas.
   - Flag source issues that commonly cause Canvas-facing friction: duplicate
     native title/body H1, broken links, missing or suspicious due dates,
     timezone-offset mistakes, prose point totals that do not match front matter,
     excessive or repeated prompt headings, and missing source-map provenance for
     previously posted items.
   - Keep checks general across Canvas-facing source kinds where practical, with
     discussion-specific checks only where the content model requires them.

4. Add targeted grade clearing with exact-match comment cleanup.

   Status: delivered by `danvas grades clear` in 0.6.0, including online
   preflight, rollback evidence, instructor-owned exact-match/explicit-ID comment
   cleanup, and readback verification.

   ```bash
   danvas grades clear --assignment-id 19952228 \
     --grades-csv grades-to-clear.csv --comments exact-match --dry-run
   ```

   Desired behavior:

   - Clear mistaken grades for targeted students without requiring ad hoc Canvas
     API scripts.
   - Preflight current Canvas grade/comment state and produce rollback evidence
     before live mutation.
   - Optionally delete only instructor-owned comments that match exact supplied
     text or explicit comment IDs; do not bulk-delete comments by loose matching.
   - Verify the cleared grades and remaining comments after live mutation.
   - Treat this as a concrete refinement of Sprint Candidate F.6 rather than a
     replacement for broader grade-patch safety work.

5. Update external teaching-danvas skill timeout guidance.

   Status: done in the external teaching-danvas skill and command reference on
   2026-07-10.

   Desired behavior:

   - In the Codex teaching-danvas skill, document that 1Password or other secret
     provider timeouts should be treated as likely user-interaction timeouts
     first.
   - On timeout, retry with clear messaging that an authentication popup may be
     waiting for user action before treating the behavior as a danvas defect.
   - Keep this in external skill docs, not as a `danvas` command feature, unless
     repeated evidence shows the CLI itself needs better timeout messaging.

## Smaller Backlog Items

These are useful but should generally wait until they support one of the sprint
candidates above.

### Auth Doctor

Command shape:

```bash
danvas auth doctor
```

Status: done. `danvas auth doctor` reports secretpath provider/config
diagnostics, checks whether the shared `canvas` secret resolves, and can ping
Canvas current-user with `--check-canvas`. It never prints the resolved token.

Desired behavior:

- Report which auth providers are available.
- Report whether a token can be resolved.
- Ping Canvas with the resolved token.
- Never print the token or verifier-bearing URLs.

### Transcript Filing Helper

Command shape:

```bash
danvas recordings panopto-captions \
  --output-dir .danvas/panopto-captions \
  --session-id SESSION_GUID \
  --file-to transcripts/raw \
  --name-pattern "{date}-lecture-{number}.panopto.transcript.txt"
```

Desired behavior:

- Suggest or perform a course-local filing step after caption download.
- Preserve original downloaded captions and manifests in `.danvas/`.
- Only write into course transcript folders when explicitly requested.

This is useful for teaching repos with transcript workflows, but it is less
central than source sync, verification, groups, or grading.

### Rubric Support

Desired behavior:

- Parse a local rubric source.
- Compare local criteria and point totals against Canvas rubric metadata.
- Support dry-run creation or attachment to an assignment.
- Treat destructive rubric replacement as out of scope unless explicitly
  requested.

Do this after update/upsert behavior is stable.

### Due-Date Ergonomics

Status: done. Assignment Markdown now accepts date-only `due_date`,
`unlock_date`, and `lock_date` fields. They expand to Canvas `due_at`,
`unlock_at`, and `lock_at` datetimes using `[canvas].timezone` from
`.danvas/config.toml`; `due_date` and `lock_date` use 23:59 and `unlock_date`
uses 00:00.

Desired behavior:

- Support date-only front matter such as `due_date: 2026-05-29`.
- Resolve date-only values using the course timezone from `.danvas/config.toml`.
- Apply an explicit end-of-day default for due dates.

This is useful across write commands, but it is smaller than the readback/update
work and should be taken when touching front matter or write-command parsing.

### Canvas File Folder Creation

Possible future behavior:

- Add an explicit `--create-folder` or `files folders create` command.
- Never create folders implicitly from upload or asset rewriting.
- Resolve path rules and parent folder ambiguity before implementation.

## Not Recommended Or No Longer Relevant

These ideas should not be pursued as stated unless new evidence changes the
design direction.

- Do not add a separate read-only `danvas sync` or `danvas diff` command for the
  existing status use case. `danvas status` and `danvas refresh --diff` cover the
  read-only comparison direction. Future "sync" work should mean concrete
  Canvas-to-local source creation or verified update workflows, not another name
  for status.
- Do not make `danvas status` write report runs by default. It is intentionally
  stdout-first for compatibility and quick inspection; report output should remain
  opt-in through `--report-root`, `--report-dir`, `--output`, or `--report-md`.
- Do not put `discussions score` into `.danvas/reports/` by default. Its normal
  output is grading workflow data, not durable course-status evidence.
- Do not make raw exports, rosters, submissions, grades, file downloads, or
  caption downloads default report runs. These are source/data artifacts or media
  bundles and should keep explicit output paths or directories.
- Do not add a common report-run `--overwrite` option. Report runs are operational
  evidence and should remain collision-safe and append-only by default.
- Do not store Canvas file verifier/download URLs in `.danvas/course.json`,
  report manifests, or upload reports. Keep URL presence or stable HTML URLs only
  where safe.
- Do not compare quiz question bodies in `danvas status` until snapshots include
  quiz item data. Current quiz shell awareness is intentionally lightweight.
- Do not build a whole-tree Canvas Files sync as a near-term feature. `files
  upload`, targeted download/compare, and Markdown asset rewriting are the safer
  direction.
- Do not create Canvas Files folders implicitly during upload. Folder creation
  should be explicit because path ambiguity can be destructive or confusing.
- Do not make group planning mutate Canvas. Planning should emit local CSVs and
  validation; only `groups import` should write groups.
- Do not implement destructive rubric replacement as part of first rubric support.
  Creation, audit, and attachment are safer starting points.
- Do not schedule comprehensive activity logging as a near-term sprint. If durable
  operational evidence is needed, prefer report runs, manifests, and explicit
  command outputs that solve a concrete workflow.
- Do not prioritize live Canvas gradebook export/download as current sprint work.
  The existing gradebook commands are local-file-first; add live export only when
  a course workflow needs it enough to justify the Canvas API and privacy surface.
- Do not treat `gradebook.py` cleanup as a product feature. It can be done
  opportunistically when changing gradebook behavior, but it should not drive
  sprint planning by itself.
- Do not keep the original Sprint 2/Sprint 3 order as binding. The report-run
  work changed the planning surface; use the current sprint candidates instead.
- Do not turn `danvas` into archival/history tooling. It remains an operational
  Canvas CLI; durable archival ledgers and course-history databases stay separate.
