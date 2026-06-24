# danvas Backlog

Last consolidated: 2026-06-24.

This document is the planning backlog for `danvas`. It reflects the state after
the report-run work landed. The old sprint notes were merged into this file and
removed; use git history for the full old text.

## Delivered Baseline

These features are considered delivered enough that they should not remain as
open sprint goals. Future work can extend them, but the core backlog item is
closed.

| Area | Delivered by | Remaining follow-up, if any |
|---|---|---|
| Expanded course snapshot | `danvas refresh`, schema version 2 | Add sections/enrollments if roster workflows need them. |
| Read-only Canvas/local status | `danvas status` | Add source-sync helpers that create local Markdown from Canvas-only items. |
| Refresh diff | `danvas refresh --diff` | Make diff output report-run aware. |
| Local source discovery | `danvas.sources` plus `[sources.<kind>]` config | Reuse in update, verify, and sync commands. |
| Quiz shell awareness | `danvas status` | Do not compare quiz question bodies unless snapshots later include item data. |
| QTI import, publish, verify | `danvas quiz import-qti` | Resolve assignment groups by configured name, if useful. |
| Canvas Files upload v1 | `danvas files upload` | Markdown asset rewriting and optional folder creation remain separate future work. |
| Generated report runs | `danvas.reports`; adopted by report-producing commands | Add report discovery commands and make new verify/reconcile commands report-first. |
| Report polish | status next actions, file diagnostics, assignment-audit notes | Continue improving command-specific reports as field use reveals friction. |
| Mutation banners | shared guardrail pattern | Apply consistently to future mutating commands. |

Current command families include:

- `init`, `refresh`, `status`, `courses`, `roster`
- `assignments export/create/audit`
- `gradebook check/audit`
- `quiz analysis/import-qti`
- `submissions media/feedback`
- `grades post/verify`
- `discussions export/score`
- `announcements create/export`
- `files inventory/download/upload`
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
| Sprint 2: seeded discussion creation | Not started | Sprint Candidate E, only if still needed for grouped-case workflow. |
| Sprint 2: basic `files upload` | Done | Delivered Baseline; future work is Markdown asset rewriting and optional explicit folder creation. |
| Sprint 2: due-date ergonomics | Not started | Smaller Backlog Items. |
| Sprint 2 stretch: transcript filing helper | Not started | Smaller Backlog Items. |
| Sprint 3: assignment update/upsert | Not started | Sprint Candidate D. |
| Sprint 3: announcement/discussion update pattern | Not started | Sprint Candidate D, after assignment update proves out. |
| Sprint 3: readback verification | Not started | Sprint Candidate C. |
| Sprint 3: round-trip metadata | Not started | Sprint Candidate C, before broad update/upsert work. |
| Sprint 3: Markdown asset rewriting | Not started | Sprint Candidate D, building on delivered `files upload`. |
| Sprint 3: single-file download and compare | Not started | Sprint Candidate B. |
| Sprint 3: file inventory report improvements | Partial | Candidate B; report-run foundation and filename diagnostics are delivered, ignore rules and targeted compare remain. |
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

- File inventory/report improvements are partial: report-run output and some
  diagnostics are delivered; targeted single-file compare, richer ignore rules,
  and Office package-part comparison remain open in Candidate B.
- Human-readable operation reports are partial: several report-producing commands
  now emit Markdown/JSON report runs; future verify, reconcile, compare, and
  readback commands should start with report-run output.
- Sprint 2's grouped-case workflow is partial only because prerequisites landed:
  snapshots include group-category summaries, mutation banners exist, and QTI
  import progress polling can inform future group-import polling. The actual
  `groups` command family has not started.

## Sprint Candidate A: Release And Documentation Cleanup

Theme: make the local release state durable, pushed, and documented before
starting a larger new feature.

Why this should come first:

- `PROJECT_CONTEXT.md` and this backlog now describe the local planning state, but
  the pushed repo and CI still need to catch up.
- External skill docs need explicit checking after command-surface or behavior
  changes because they live outside this repo.

Scope:

- Push local commits when ready and confirm GitHub Actions.
- Decide whether the current version should be tagged after CI passes.
- Keep `PROJECT_CONTEXT.md` and `docs/backlog.md` current if release status
  changes during sprint close-out.
- Confirm the external Codex teaching skill docs still match the current command
  surface:
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

   Desired behavior:

   - Preserve current plain `danvas refresh --diff` terminal behavior.
   - When report options are passed, write `manifest.json`, `refresh-diff.json`,
     and `refresh-diff.md`.
   - Include old/new snapshot timestamps, changed sections, and schema-version
     compatibility status.
   - Keep `.danvas/course.json` as the snapshot source of truth; reports are
     evidence, not replacement snapshots.

3. Continue report output consistency for future commands.

   Desired behavior:

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

   Desired behavior:

   - Download exactly one Canvas file by file ID or by an unambiguous Canvas folder
     path.
   - Refuse ambiguous path matches unless a file ID is supplied.
   - Compare Canvas metadata against a local file by filename, size, checksum, and
     updated time where available.
   - For Office files, optionally compare internal ZIP entries and report added,
     missing, and changed package parts.
   - Improve `files inventory` ignore rules for generated/cache/archive paths such
     as `.danvas/`, `_archive/`, rendered artifacts, and local scratch outputs.

Definition of done:

- Report discovery works against real and fixture `.danvas/reports/` directories.
- `refresh --diff` can write a report run without changing its default behavior.
- README and external skill docs document the new report and compare commands.

## Sprint Candidate C: Local Source Sync And Readback

Theme: close the gap between status reports and maintainable local sources.

Recommended goals:

1. Add Canvas-to-local source sync helpers for Canvas-only instructional content.

   ```bash
   danvas announcements sync --output-dir content/announcements --dry-run
   danvas discussions sync-prompts --output-dir content/discussions --dry-run
   ```

   Desired behavior:

   - Create missing Markdown files with front matter from Canvas announcements or
     instructor-authored discussion prompts.
   - Include stable Canvas IDs, URLs, titles, publish/lock state, and dates where
     available.
   - Generate safe numbered filenames and refuse to overwrite existing files.
   - Skip student replies and ordinary discussion participation by default.
   - Use report runs for dry-run/readback evidence.

2. Add assignment and announcement verification commands.

   ```bash
   danvas assignments verify content/cases/case-1.md
   danvas assignments verify --assignment-id 19862404
   danvas announcements verify content/announcements/04-case-open.md
   danvas announcements latest --course-id 1742719 --format markdown
   ```

   Desired behavior:

   - Resolve Canvas objects by explicit ID from sidecar metadata, front matter, or
     CLI option.
   - Allow title matching only with an explicit flag and refuse ambiguous matches.
   - Compare stable fields: title, URL, published state, due/unlock/lock dates,
     points, assignment group, submission type, group category, and relevant
     grading settings.
   - For announcements, support a safe latest-announcement export before posting a
     follow-up.

3. Design round-trip metadata before broad update/upsert work.

   Recommended direction:

   - Prefer a sidecar manifest for Canvas IDs and URLs so reusable Markdown stays
     mostly clean.
   - Allow optional front matter IDs for course-specific sources when useful.
   - Record assignment IDs, discussion topic IDs, announcement IDs, file IDs, URLs,
     last-posted timestamps, and a safe subset of last-posted comparable fields.

Definition of done:

- `status` next-action hints point to implemented sync/verify commands where
  applicable.
- Sync and verify outputs produce report runs.
- Round-trip metadata format is documented before update/upsert writes are added.

## Sprint Candidate D: Safe Update And Upsert

Theme: move from create-only workflows to controlled maintenance without
duplicating Canvas objects.

Recommended goals:

1. Add conservative assignment update.

   ```bash
   danvas assignments update SOURCE.md --dry-run
   ```

   Desired behavior:

   - Match by Canvas ID from sidecar/front matter or `--assignment-id`.
   - Permit title matching only behind an explicit flag.
   - Show a field-by-field before/after diff before live writes.
   - Update supported fields without deleting unrelated Canvas state.
   - Refuse ambiguous matches and missing IDs unless the user explicitly opts into
     title lookup.

2. Extend the pattern to announcements and discussions after assignment update is
   stable.

3. Add Markdown asset rewriting on top of `files upload`.

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

3. Add graded and seeded discussion creation from Markdown if it remains part of
   the grouped-case workflow.

   ```bash
   danvas discussions create --course-id 1742719 discussion.md --seed-replies --dry-run
   ```

   Desired behavior:

   - Accept one Markdown source with front matter for the root topic and
     `--- reply ---` sections for instructor-seeded prompt replies.
   - Create the discussion topic and top-level instructor replies in one command.
   - Preserve graded discussion assignment metadata.
   - Return topic ID, assignment ID, URL, and seeded entry IDs.

Definition of done:

- A grouped case assignment can be planned, imported, verified, and connected to
  the correct `group_category_id` without raw Canvas API scripts.
- Multi-step writes print mutation banners, progress IDs, and verification
  recommendations.
- Skill docs are updated because the command surface changes materially.

## Sprint Candidate F: Submission Grading Workflow Improvements

Theme: reduce custom scripting and catch bad local submission artifacts earlier.

Recommended goals:

1. Add read-only grade/comment pull.

   ```bash
   danvas submissions grades --assignment-id 19838584 \
     --output grading/case1-graded-comments.csv \
     --json grading/case1-graded-comments.json
   ```

   Desired behavior:

   - Fetch `score`, `grade`, `graded_at`, `grader_id`, text comments, attempt,
     workflow state, late/missing flags, and attachment counts/names.
   - Default to sanitized output and require an explicit option for raw Canvas
     payloads.
   - Support `--only-graded` or equivalent filtering.

2. Add attachment integrity checks to `submissions media`.

   Desired behavior:

   - Validate `.zip`, `.xlsx`, `.docx`, and `.pptx` downloads as ZIP/OOXML
     containers.
   - Write integrity status and warning details into sidecar `.info.json`.
   - Emit clear terminal warnings for malformed downloads.

3. Add a submission manifest.

   Desired behavior:

   - Write a top-level `submissions-manifest.csv` or JSON file after media
     downloads.
   - Include student, Canvas user ID, submission ID, attempt, submitted time,
     attachment filenames, local paths, content type, file size, download status,
     and integrity status.

4. Preserve text comments separately from media.

   Desired behavior:

   - Emit `submission-comments.csv` and/or JSON when downloading media or pulling
     grades.
   - Keep student data clearly marked as private.

5. Add a provenance-friendly local replacement helper only if malformed-download
   recovery keeps recurring.

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

Definition of done:

- Case grading workflows no longer need a local script just to pull graded
  comments and grades.
- Bad Office/ZIP downloads are detected immediately.
- Download manifests make grading folders auditable without reading each sidecar.

## Sprint Candidate G: Exam Reconciliation And Roster/Override Support

Theme: support multi-version exam reconciliation with explicit, private reports.

Recommended goals:

1. Add metadata-only submissions export.

   ```bash
   danvas submissions export --assignment-id 19901542 --output .danvas/proctoru-submissions.json
   ```

   Desired behavior:

   - Include user ID, name, workflow state, submitted time, score, attempt,
     attachment count/names, late/missing flags, and optional submission history.
   - Default to sanitized private output and require `--save-raw` for raw payloads.

2. Add assignment override member export.

   ```bash
   danvas assignments overrides --assignment-id 19901488
   ```

   Desired behavior:

   - Export override IDs, titles, due/unlock/lock dates, and member Canvas IDs.
   - Keep student membership private and explicit.

3. Include sections in roster and optionally `.danvas/course.json`.

   Desired roster fields:

   ```text
   SectionID, SectionName, EnrollmentState, LastActivityAt
   ```

4. Add a report-first reconciliation command.

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

## Smaller Backlog Items

These are useful but should generally wait until they support one of the sprint
candidates above.

### Auth Doctor

Command shape:

```bash
danvas auth doctor
```

Desired behavior:

- Report which auth providers are available.
- Report whether a token can be resolved.
- Ping Canvas with the resolved token.
- Never print the token or verifier-bearing URLs.

This is worthwhile if auth confusion recurs, but it is not currently a core
sprint by itself.

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
