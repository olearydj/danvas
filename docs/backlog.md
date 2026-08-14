# danvas Backlog

Last consolidated: 2026-08-12.

This document is the planning backlog for `danvas`. It distinguishes the shipped
0.7.0 surface from genuine follow-on work. The lightweight implementation specs
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

## 0.7.0 Pages Follow-On Implementation Record

The current branch implements the two Pages follow-on sprints planned after the
0.6.0 release:

| Slice | Specification | Commit |
|---|---|---|
| Canvas Pages discovery, schema-v4 snapshot, and status | `docs/sprints/06-canvas-pages-status.md` | `a45d3d1` |
| Canvas-to-local Page sync and conversion | `docs/sprints/07-canvas-pages-sync.md` | `7517c0c` |
| Account-decorator readback normalization found during field testing | Sprints 6 and 7 | `f4252d7` |

Ruff, ty, and all 283 tests passed. A non-normative sandbox field case in course
1576638 passed draft API readback and browser inspection, schema-v4 refresh and
status, Markdown export, targeted and broad sync path agreement, no-clobber local
creation, repeat-sync idempotence, and interrupted-provenance recovery. The test
Page was unpublished and removed after acceptance. The implementation was
published and tagged as `v0.7.0` at `5988c93`.

Follow-up safety review tightened the same implementation before release:
foreign origins with Canvas-shaped paths are never rewritten as local Canvas
links, title-only sync candidates must be unique on both sides, occupied targets
must have matching provenance, and status refuses body-hash comparison across
normalizer versions.

## 0.7.1 Audit Remediation Implementation Record

The post-0.7.0 audit findings were triaged into behavioral defects, targeted test
gaps, documentation drift, and complexity-only debt. The patch-release work is
implemented in two bounded specifications:

| Slice | Specification | Status |
|---|---|---|
| Privacy and filesystem safety hardening | `docs/sprints/08-privacy-filesystem-safety.md` | Implemented and locally verified |
| Correctness and resilience remediation | `docs/sprints/09-correctness-resilience.md` | Implemented and locally verified |

The candidate hardens private report-run permissions, confines broad Canvas
Files downloads to their selected output directory, sanitizes public diagnostic
paths, restores Page-aware snapshot diffs, enforces both-sides Page-title
uniqueness, covers declared Page roles/scheduling fields, isolates malformed
front matter during source scans, and fixes assignment-audit snapshot and
zero-weight edge cases. A final patch-level cleanup adds Panopto out-of-range
timestamp tolerance, corrects the remaining command/example documentation drift,
adds direct front-matter tests, and removes brittle help-prose assertions. Ruff,
ty, and all 312 tests pass locally.

The six complexity-only refactors remain deferred. The combined implementation
is published on `origin/main`, passes CI, and is released as `v0.7.1`; the global
CLI is installed from the tagged release.

## 0.7.2 Page Comparison Regression Patch

A post-release adversarial audit found three regressions introduced by the 0.7.1
Page correctness remediation. The 0.7.2 patch:

- compares date-only and timezone-equivalent `publish_at` values semantically in
  both Page planning and verification
- keeps duplicate unbound local Pages classified as `local-only` when Canvas has
  no title candidate, while retaining ambiguity protection when a candidate exists
- uses the same conflict-aware Page identity resolution in status pre-scan and
  main comparison so a rejected binding cannot orphan an eligible Canvas row

The patch is published on `origin/main`, passes CI with all 320 tests, and is
released as `v0.7.2`; the global CLI is installed from the tagged release.
Complexity-only refactors remain deferred.

## 0.7.3 Documentation And CLI Help Reconciliation

The documentation-only 0.7.3 patch aligns the current bounded Page update scope
across CLI help, durable repo documentation, and the external teaching-danvas
skill/reference. It also records Page sync/create/update/verify in the report-run
inventory and documents semantic comparison of date-only and timezone-equivalent
`publish_at` values. The patch is published on `origin/main`, passes CI, and is
released as `v0.7.3`; the global CLI is installed from the tagged release.

## 0.10.0 Consolidated Evidence And Snapshot Release

The public 0.10.0 release consolidates the previously untagged 0.8.0 grade-
evidence and 0.9.0 assignment-release development lines with Sprint 12's
authorization-resilient snapshots. Sprints 10, 11, and 12 all passed their
bounded field gates. Ruff, ty, and all 395 tests passed locally and in GitHub
Actions for commit `92dc888`, which is published on `origin/main` and tagged
`v0.10.0`. The global CLI is installed from that tag and independently reports
`danvas 0.10.0`; `danvas --help` and the local `auth doctor` diagnostic also
pass outside the repository environment.

## 0.10.2 Assignment Release Maintenance

The public Sprint 13 commit consumed version 0.10.1 without creating a tag, so
the reviewed maintenance release advances to 0.10.2. It retains the installed-
CLI health work and repairs evidence-integrity defects found after the 0.10.0
release:

- `assignments update` and update-mode `assignments upsert` now preserve and
  compare declared `assignment_group`/`assignment_group_name` aliases and
  `canvas_url`/`html_url` values through no-change planning and live readback
- assignment mutation projections use the configured Canvas origin, keeping
  same-origin file-link classifications consistent with the local comparison
- successful file uploads remain classified as successful when Canvas returns
  a file ID but local stable-URL construction is incomplete; mutation and
  evidence statuses are recorded separately with an explicit do-not-retry
  warning
- release smoke rejects an explicitly empty expected version before build or
  installation begins

Focused regression tests cover alias no-change behavior, successful update
readback and provenance, same-origin report projection, partial upload evidence,
and indeterminate upload identity. The full frozen suite, Ruff, ty, isolated
editable/wheel smoke, and exact-tag CI passed for published tag `v0.10.2`; its
pending global replacement check was superseded by the explicitly authorized
exact-tag `v0.11.0` installation. No new Canvas command or live field mutation
is needed. The field install also showed that uv's `--force` alone can exit 0
while retaining an older same-package tool environment; exact-tag replacement
guidance now includes `--upgrade --reinstall` and requires a post-install version
check.

## 0.11.0 Authored Discussion Release

Sprint 14 is implemented in
`docs/sprints/14-discussion-source-workflows.md`. It adds authored discussion
create, verify, and safe update commands; graded-assignment preservation;
explicit seeded-reply confirmation; reverse posting with source-order entry
provenance; complete topic/assignment/seed readback; and a body-only update
scope that never mutates entries. The implementation uses the new
`danvas.discussion_sources` module and ships in 0.11.0. Ruff, ty, all 439 tests,
and isolated editable/wheel smoke pass. Bounded live acceptance passed in
sandbox course 1576638 on 2026-08-12: clean create/readback, stable assignment
and seed-entry provenance, full verify, local duplicate guard, body-only update,
seed preservation, and guarded topic/assignment cleanup all passed. Field
acceptance also established that discussion `*_at` fields need `Z` or an
explicit UTC offset because Canvas silently ignores date-only graded-discussion
dates; source loading and lint now fail before Canvas access for ambiguous
values. The same review pass hardens grade evidence preflight: nonblank
malformed rows and duplicate normalized Canvas IDs now fail before Canvas
access, so verification and recovery cannot silently omit or mispair intent.

## 0.12.0 Structural Foundations Release

Sprint 15 shipped in 0.12.0 and is documented in
`docs/sprints/15-authored-content-foundations.md`. It consolidates assignment,
announcement, discussion, and Page comparison/datetime primitives; moves
divergent redaction vocabularies into one dependency-free sanitizer; makes
`InvalidAccessToken` a fatal credential-wide snapshot failure; and adds opt-in
`--require-complete` process-level signaling while preserving default
partial-snapshot usability. Initial implementation verification passed Ruff, ty,
and all 482 tests in a clean frozen environment. No Canvas mutation or new
command family is included.

Post-review correction passes add characterization coverage for the surrounding
contracts that the initial consolidation did not pin. Field-specific Page,
announcement, and status text/boolean policies avoid both over-coercion and
over-literal comparison. Announcement verification checks the legacy fixed set
plus declared supported fields while retaining optional title and datetime
validation. Section-specific reads adapt IDs from Canvas section-inclusive
responses. Upload failures retain conservative compound-key suppression, while
grade recovery detects colon-delimited, quoted, and bare-Bearer credentials
without treating benign policy/expires/token/signature/bearer prose as secret.
Colon-form `token`/`signature` and bare `Bearer` markers require a
credential-shaped payload, while explicit equals assignments remain sensitive.
Colon-form `policy`/`expires` is reserved for error sanitizing so scheduling
prose such as `your extension expires: 2026-09-01` keeps its recovery row.
Generated matrices cover 2,496 credential name/prefix/separator/value
combinations, 192 colon-reserved combinations, 60 ambiguous prose combinations,
and 16 scheduling-prose combinations. Compound credential names and
`aws_secret_access_key` remain sensitive across both grade-evidence and
error-sanitization paths. Alpha-only
ambiguous colon and bare-Bearer payloads remain an accepted detector limitation:
preserving ordinary prose takes priority when no digit or token marker is
present. YAML calendar errors are centralized and mixed-timezone ordering lint
is conservative. Ruff, ty, and all 529 tests pass after the corrections.
Isolated editable/wheel release smoke also passes. A disposable
section-specific announcement in
sandbox course 1576638 read back the requested section ID and was confirmed
absent after cleanup.

## 0.13.0 Verified Markdown Asset Deployment

Sprint 16 is implemented in
`docs/sprints/16-verified-markdown-assets.md`. It integrates local asset
planning, safe upload/reuse, Canvas-bound HTML rewriting, stable file-ID
readback, and interrupted-run provenance with the existing Markdown-backed
assignment write workflows. A new `danvas.authored_assets` module is warranted
because the multi-file transaction and retry boundary is distinct from both the
assignment feature module and the pure comparison layer.

The authored Markdown remains unchanged. The implementation rejects unresolved,
ambiguous, unsafe, cross-course, and unsupported local references before content
mutation. It excludes implicit folder creation, overwrite, deletion, remote
fetching, whole-tree sync, and Page/announcement/discussion integration. The
approved assignment/Page probe established the `src`-only image profile.
Bounded assignment acceptance then passed upload, destination-free reuse,
explicit rename without overwrite, stable file-ID/folder readback, a rejected
content write followed by source-map-based retry, source immutability, and
independently verified cleanup. The implementation is released as 0.13.0. The
clean isolated frozen suite passes
all 565 tests; Ruff, ty, lock validation, sprint-document Markdown lint, and
isolated editable/wheel smoke also pass.

## 0.13.1 Dependency Maintenance

Released as `v0.13.1`, this patch upgrades frozen `idna` and `soupsieve` to
versions that clear the current dependency audit and adds `pip-audit` to the
development lock and CI checks. It changes no application code or Canvas
behavior. The frozen audit reports no known vulnerabilities; all 565 tests,
Ruff, ty, and lock validation pass. Isolated editable/wheel smoke also passes
for the exact release.

## 0.14.0 Structural Quality Release

Sprint 17 is released as `v0.14.0` and recorded in
`docs/sprints/17-transaction-state-quality.md`. It introduces typed asset
transaction and runtime state, decomposes the highest-risk planning and
execution paths, removes the configuration/Page/source/assignment import cycle,
and adds branch-coverage, complexity, dependency-audit, and supported-Python
ratchets. It deliberately changes no Canvas command, mutation, evidence schema,
or operator workflow.

The frozen Python 3.12 and 3.14 lanes each pass all 602 tests, Ruff, ty, and the
dependency audit. Combined branch-aware coverage is 83.75 percent and
`authored_assets` coverage is 88.84 percent; the enforced floors are 82 percent.
Lock validation, isolated editable/wheel smoke for 0.14.0, local Markdown-link
validation, and sprint-document lint also pass. Independent review found one
blocking transition defect; the corrected candidate passed the complete gate
before release.

Four pre-existing complexity hotspots are the only allowed `C901` suppressions:

- `authored_content.comparable_value`;
- `page_sources.check_css` (moved intact from `pages`);
- `pages.build_pages_sync_plan`; and
- `status.compare_pages`.

They remain named refactor debt. The architecture test fails if another
suppression is added or one of these exceptions moves without updating the
durable decision.

## 0.15.0 Instance Independence Release

Sprint 18 is released as `v0.15.0`. It removes the Auburn host and Central Time
runtime fallbacks, adds platform-native non-secret Canvas profiles, separates
profile/instance/credential precedence, preserves initialized-project and
environment compatibility, maps a bounded set of Rails timezone labels, and
keeps offline `auth doctor` useful without an instance.

Python 3.12 and 3.14 CI passed Ruff, ty, the dependency audit, branch coverage,
all tests, and isolated editable/wheel smoke. The independent implementation
review was initially deferred because the reviewer service was unavailable.
The later batched review accepted the `v0.15.1` release line as released on
2026-08-13, closing that obligation.

Patch release `v0.15.1` forwards the selected profile's `secret_name` through
the Panopto caption command's direct authentication path. No other command or
privacy behavior changes.

## 0.16.0 Private Artifact Release

Sprint 19 is released as `v0.16.0`. It introduces the typed private-artifact
boundary, secure-at-creation filesystem behavior, private defaults beneath
`.danvas/private/`, manifest v2, bounded terminal output, and migration support
for roster and source-map compatibility. Independent implementation review
returned accept-with-fixes; the corrected `aa66f57` commit passed branch and
signed-tag CI on Python 3.12 and 3.14, dependency audit, coverage, and isolated
installation smoke. The global CLI is installed from the verified tag.

Independent review found that the initial self-derived transition tests could
not detect a missing `would_reuse -> failed` edge. The candidate now carries an
independently declared state contract plus real execution cases for upload
success, rejection and uncertainty, destination drift, provenance failure,
partial stable evidence, successful reuse, and stale reuse. Stale all-reuse
execution again returns bounded failure evidence without mutation.

## 0.17.0 Mutation And Evidence Release

Sprint 20 is released as `v0.17.0`. Its exact
55-command access inventory and pre-write architecture gate make all remaining
Canvas-writing commands plan on omission and require `--apply`. Direct
discussion-grade upload is replaced with a private `grades post` CSV; feedback
apply now checkpoints and reads back every attempted row; and file upload
defaults to non-destructive conflict handling with explicit race outcomes.

Independent design and implementation review accepted the candidate through
`ed68108`. The separately authorized disposable-course probes passed on
2026-08-13 with exact cleanup. The first feedback probe exposed CanvasAPI's
attachment-only `upload_comment()` behavior; `b3893aa` now uses the documented
file-upload plus comment-edit sequence, and the corrected probe verified exact
comment/attachment readback. Supplemental review accepted the corrected exact
commit without findings. Branch and signed-tag CI passed on
`f34d32fe6da3a92255f614e68ab3f73ee5aae8cd`, including Python 3.12, Python
3.14, dependency audit, coverage, and isolated installation smoke. The global
CLI is installed from the verified tag and reports `danvas 0.17.0`.

## 0.18.0 Generalization And Public Beta Release

Sprint 21 is the accepted final design slice of the public-readiness program:

- [Generalization, Packaging, And Public Beta](sprints/21-generalization-packaging.md)

The design absorbs source layouts, gradebook heading aliases, replaceable file
inventory defaults, Panopto interrupted-bundle recovery, deprecations due in
0.18.0, packaging metadata, anonymous installation, the public documentation
suite, POSIX/macOS and Python support, workflow hardening, secret scanning, and
the cross-release beta audit. Independent review selected `danvas-cli` as the
distribution while preserving the `danvas` import package and executable. The
Sprint 22 design review and Sprint 21 Group 0 characterization are complete.
Groups 1 through 4 have passed focused review and exact-commit Group 4 CI is
green at `c95cae8`. Group 5 has assembled the clean-machine and cross-release
[public-beta audit](sprints/21-public-beta-audit.md), and independent review
returned `ACCEPT PUBLIC BETA`. Corrected release commit `c12baef` passed exact
branch and signed-tag CI plus anonymous SHA/tag installations. The verified tag
is installed globally as `danvas-cli 0.18.0`; no GitHub Release or PyPI
publication was performed.

## Accepted 0.20.0 Agent Interface Follow-On Design

Sprint 22 is the accepted post-beta interface design:

- [Agent-Facing Help And Portable Skill](sprints/22-agent-interface.md)

It extends the shipped access and artifact registries with workflow guidance,
adds bounded help, offline guides, versioned JSON description, and packages one
generic skill source inside the `danvas-cli` distribution. Sprint 21.5 now owns
the due roster `--schema legacy-v1` removal and provider-neutral authentication
surface; Sprint 22 consumes that released `0.19.0` interface without otherwise
changing its accepted scope. The design authorizes no early skill installation
or external agent invocation. Group 3 commit `75ca92a` refreshes the accepted
design against the neutral `0.19.0` candidate and removes the completed roster
migration work item; implementation still waits for the exact release gates.

## Accepted 0.19.0 Provider-Neutral Credential Boundary

Sprint 21.5 is the accepted post-beta prerequisite:

- [Provider-Neutral Credential Boundary](sprints/21-5-credential-boundary.md)

The design removes provider choice, direct SecretPath integration, and implicit
dotenv loading from danvas while retaining explicit environment-variable and
single-purpose credential-file delivery. It also binds credential use to a
user-controlled Canvas origin and makes external SecretSpec, 1Password, CI, or
platform injection an individual/organization decision. The design targets
`0.19.0`, absorbs the roster legacy-schema removal already promised for that
release, and moves the remaining accepted Sprint 22 agent-interface work to
`0.20.0`. Independent review accepted the threat model, release sequence, and
design on 2026-08-13 after the required contract edits. Group 0 characterization
is complete at `1145791` with no production behavior change. Group 1's neutral
resolver and origin trust gate at `c50d170` was accepted after focused review
with no findings. Group 2's provider-specific option, profile, dotenv,
dependency, doctor-schema, and roster-compatibility removals at `8efbfa5` are
accepted after focused review with no findings. Group 3's public migration
matrix, neutral guide rewrite, candidate version, and Sprint 22 refresh are
complete at `75ca92a` and accepted after focused review with no findings. Group
4 final security review and exact candidate release gates remain.

Named post-beta maintenance: when Python 3.15 is released, revisit the
`<3.15` upper bound. Expand support only with an explicit compatibility review
and a green Python 3.15 CI lane; do not let the upper bound become an unexamined
long-term support policy.

## Delivered Baseline

These features are considered delivered enough that they should not remain as
open sprint goals. Future work can extend them, but the core backlog item is
closed.

| Area | Delivered by | Remaining follow-up, if any |
|---|---|---|
| Expanded course snapshot | `danvas refresh`, schema version 5 | Authority-aware optional collections, partial snapshots, safe section-level diff/status behavior, and atomic replacement are implemented in Sprint 12; add sections/enrollments only if roster workflows need them. |
| Override-aware assignment status | schema-v3 snapshot, `danvas assignments overrides` | Snapshots remain redacted; membership exports are explicit private artifacts. |
| Submission evidence exports | `danvas submissions export/grades/media` | Local replacement provenance remains optional future work. |
| Transaction-safe grade patches | `danvas grades post/clear/comments/verify` | Truthful row outcomes, private receipts/recovery, and targeted release evidence passed bounded live acceptance and shipped in `v0.10.0`. |
| Assignment release evidence | `danvas assignments create/update/upsert/verify`, `danvas files upload`, `danvas.authored_assets` | Integrated Markdown document/image deployment, immediate file provenance, retry-safe reuse, explicit rename, and exact file-ID/folder verification passed bounded live acceptance in Sprint 16; Page/announcement/discussion adapters remain follow-ons. |
| Canvas Pages bounded workflow | `danvas pages list/export/sync/render/css-check/create/update/verify`, schema-v4 status | The Sprint 16 probe established Page image-link behavior, but Page asset deployment remains a follow-on alongside rename/delete, broad upsert, and broader compatibility profiles. |
| Canvas-facing source lint | `danvas sources lint` | External HTTP checking and automatic rewriting remain deferred. |
| Authored discussion workflow | `danvas discussions create/verify/update` | Sprint 14 passed bounded disposable-topic Canvas acceptance and shipped in `v0.11.0`. |
| Read-only Canvas/local status | `danvas status` | Continue refining next-action hints as new source workflows land. |
| Refresh diff | `danvas refresh --diff` | Plain diff remains terminal-first; report output is available through explicit report options. |
| Local source discovery | `danvas.sources` plus `[sources.<kind>]` config | Continue reusing in future source-aware commands. |
| Quiz shell awareness | `danvas status` | Do not compare quiz question bodies unless snapshots later include item data. |
| QTI import, publish, verify | `danvas quiz import-qti` | Resolve assignment groups by configured name, if useful. |
| Canvas Files upload v1 | `danvas files upload`, Sprint 16 assignment integration | Integrated assignment asset deployment is implemented and live-verified; other authored adapters and optional explicit folder creation remain separate future work. |
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
- `discussions create/verify/export/update/sync-prompts/score`
- `announcements create/export/latest/sync/update/verify`
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
| Sprint 2: seeded discussion creation | Done | Sprint 14 generalizes creation beyond grouped cases with dry-run, graded metadata, readback, seed IDs, provenance, and bounded live acceptance. |
| Sprint 2: basic `files upload` | Done | Delivered Baseline; future work is Markdown asset rewriting and optional explicit folder creation. |
| Sprint 2: due-date ergonomics | Done | Smaller Backlog Items; date-only assignment fields are delivered. |
| Sprint 2 stretch: transcript filing helper | Not started | Smaller Backlog Items. |
| Sprint 3: assignment update/upsert | Done | Candidate D; assignment create writes source-map provenance, update is live with readback verification, and upsert plans then requires `--confirm create` or `--confirm update` for live mutation. |
| Sprint 3: announcement/discussion update pattern | Done | Announcement update and Sprint 14 discussion update/verify are delivered with stable identity and readback. |
| Sprint 3: readback verification | Partial | Delivered for assignment create/update/upsert, announcement and discussion update, grade mutation verification, and bounded Page create/update; not yet broad across every write workflow. |
| Sprint 3: round-trip metadata | Done | Sprint Candidate C; `.danvas/source-map.json` design and helpers are delivered for current update workflows. |
| Sprint 3: Markdown asset rewriting | Done for assignments | Sprint 16 covers assignments on delivered `files upload`; Page/announcement/discussion adapters remain follow-ons. |
| Sprint 3: single-file download and compare | Done | Candidate B; `files download-one`, `files compare` metadata, and optional checksum against a supplied downloaded Canvas file are delivered. |
| Sprint 3: file inventory report improvements | Done | Candidate B; report-run foundation, filename diagnostics, targeted metadata compare, downloaded-file checksum compare, and configurable local ignore rules are delivered. |
| Sprint 3 stretch: human-readable operation reports | Partial | Delivered for several report-run commands; Candidate B keeps report consistency work alive for new commands. |
| Sprint 3 beyond: rubric support | Deferred | Smaller Backlog Items; wait until update/upsert behavior is stable. |
| Sprint 3 beyond: activity logging | Not recommended as a sprint | Not Recommended Or No Longer Relevant. |
| Sprint 3 beyond: live Canvas gradebook export/download | Deferred pending a supported Canvas API | Recent Field-Observed Workflow Gaps, item 7; manual native export remains simple and reliable. |
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
- Recheck any maintainer-owned external teaching overlay after a future
  command-surface change, without making that private overlay part of the
  public documentation authority chain.

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
   danvas files download-one --course-id 101 --file-id 303 --output /private/tmp/example.canvas.pptx
   danvas files compare --course-id 101 --file-id 303 --local content/slides/example.pptx
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
   danvas assignments verify --assignment-id 202
   danvas announcements verify content/announcements/04-case-open.md
   danvas announcements latest --course-id 101 --format markdown
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
     "course_id": 101,
     "generated_at": "2026-06-24T12:00:00-05:00",
     "sources": [
       {
         "kind": "assignment",
         "path": "content/cases/case-1.md",
         "canvas": {
           "id": 202,
           "url": "https://canvas.example.edu/courses/101/assignments/202"
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

   Status: implemented and bounded-live-verified as Sprint 16 in
   `docs/sprints/16-verified-markdown-assets.md` and released in 0.13.0.

   Desired behavior:

   - Scan Markdown-backed assignments for local asset links in Sprint 16.
   - Upload or safely reuse local files in an explicitly selected Canvas Files
     folder without implicit folder creation or overwrite.
   - Rewrite only in-memory Canvas-bound HTML; never mutate authored Markdown.
   - Record file identity immediately so interrupted runs retry without duplicate
     upload.
   - Verify final links by stable Canvas course/file identity and never retain
     signed verifier/download URLs.
   - Reuse the shared transaction in later Page, announcement, and discussion
     adapters only after each feature's rendering/readback boundary is designed.

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
   danvas groups categories --course-id 101
   danvas groups categories rename --course-id 101 202 "Case 1 Groups" --dry-run
   danvas groups import --course-id 101 --category-id 202 content/cases/case-1-groups.csv --dry-run
   danvas groups verify --course-id 101 --category-id 202 --expected content/cases/case-1-groups.csv
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
   danvas discussions create --course-id 101 discussion.md --seed-replies --dry-run
   ```

   Desired behavior:

   - Accept one Markdown source with front matter for the root topic and
     `--- reply ---` sections for instructor-seeded prompt replies. Sprint 14
     deliberately uses one reviewable source contract; a separate
     `create-seeded --replies` surface is not needed unless field use reveals a
     real split-source workflow.
   - Create the discussion topic and top-level instructor replies in one command.
   - Preserve graded discussion assignment metadata.
   - Post seed replies in the intended Canvas display order, accounting for the
     observed reverse-order display behavior when needed.
   - Return topic ID, assignment ID, URL, and seeded entry IDs.
   - Record topic identity immediately after creation so a partial failure
     cannot duplicate the topic on retry; replace it with complete topic/seed
     provenance after successful readback.
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
   danvas submissions grades --assignment-id 201 \
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
   danvas submissions export --assignment-id 203 --output .danvas/proctoru-submissions.json
   ```

   Desired behavior:

   - Include user ID, name, workflow state, submitted time, score, attempt,
     attachment count/names, late/missing flags, and optional submission history.
   - Default to sanitized private output and require `--save-raw` for raw payloads.

2. Add assignment override member export.

   Status: delivered for explicit private export and conservative private-file
   synchronization. `assignments overrides-sync` is dry-run by default, creates
   or updates referenced rows, requires `--apply --confirm apply` for writes, and
   preserves Canvas-only overrides rather than deleting them.

   ```bash
   danvas assignments overrides --assignment-id 202
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
     assignment_id: 201
     source: content/cases/case1-assignment.md

     base:
       due_at: 2026-06-15T04:59:00Z
       lock_at: 2026-06-15T04:59:59Z

     overrides:
       - canvas_override_id: 303
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
   - The dry-run-first sync/update workflow accepts the exported YAML/JSON
     structure through `availability_overrides_ref`. Live writes require explicit
     confirmation, and deletion remains intentionally unsupported.

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
     --variant in_class:assignment_override:202 \
     --variant zoom:override_or_submission:204 \
     --variant proctoru:submission:203 \
     --upload-assignment 205 \
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

Implementation status (2026-08-12): Sprints 4 through 7 deliver list/export,
rendering, restricted CSS, draft create/readback, bounded
body/publication/declared-roles/scheduling update, verification, local source
linting, schema-v4 discovery/status, targeted HTML/Markdown export, and
non-overwriting Canvas-to-local source sync. Sprint 16 probed Page image-link
behavior, but Page asset upload/rewriting remains a follow-on. Deletion, rename,
front-page mutation, general upsert, and broader compatibility profiles remain
deferred.

Implementation status: source discovery/snapshot/status is delivered by Sprint
6; safe Canvas-to-local source sync and targeted HTML/Markdown conversion are
delivered by Sprint 7. Page asset handling and broader lifecycle/profile work
remain follow-ons after Sprint 16 establishes the shared assignment boundary.

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
danvas pages list --course-id 101
danvas pages export --course-id 101 --output .danvas/pages.json
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
   page_id: 202
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
     Direct outer-edge account stylesheet/script decorators injected around API
     readback are ignored for hashing and conversion, but are never persisted
     into authored sources or treated as allowed Page markup.
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

   Status: create/readback/verify and bounded
   body/publication/declared-roles/scheduling update are delivered. Title/slug
   rename, front-page mutation, general upsert, and delete remain deliberately
   unsupported.

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
     report and accepts body, publication state, and explicitly declared
     `editing_roles` and `publish_at` changes. Date-only and timezone-equivalent
     scheduled publication values compare semantically on readback.
   - Live update changes only those supported fields, reads the Page back, and
     does not alter title/slug, front-page state, module membership, or links
     elsewhere in the course.
   - A future `pages upsert` would need explicit create/update confirmation and
     separately designed rename behavior.
   - Do not add a broad delete command in the first implementation. Unpublishing
     is safer than deletion and can be handled as an explicit update.

5. Handle links and local assets deliberately.

   Status: same-page anchors are covered by the delivered renderer and tests.
   Sprint 16 includes a Page link-profile probe, but local Page asset upload and
   Canvas-bound rewriting remain a follow-on to its assignment implementation
   and the Sprint 17 structural quality work.

   Desired behavior:

   - Preserve ordinary external links and same-page anchors through Markdown
     conversion and Canvas readback.
   - Detect local relative asset links before a write and fail on every
     unresolved, ambiguous, unsafe, or unsupported reference. Sprint 16 does not
     add `--allow-unresolved-assets`.
   - Reuse the Sprint 16 asset transaction on top of `danvas files upload`, with
     a Page-specific adapter that respects validation and canonical body hashing,
     rewriting only Canvas-bound HTML and leaving authored Markdown unchanged.
   - As part of that adapter, delegate Canvas file parsing and sensitive-query
     names to `canvas_links`, retire the Page-specific suffix gate and duplicate
     file regex, and document the resulting Page detection change in its own
     migration contract.
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

### Accessibility Follow-On: Semantic Rendering And WCAG-Oriented Linting

A July 2026 audit of representative course Pages found that the current
renderer preserves the essential Markdown structure and can produce an
accessible color palette, but it also exposed general opportunities to improve
both the Canvas-bound HTML and the diagnostics authors receive. Treat this as a
course-agnostic Pages feature, based on the final rendered fragment rather than
on Markdown heuristics alone.

1. Strengthen generated HTML semantics without inventing author intent.

   Status: explicit column scope for simple Markdown-generated tables is
   delivered by renderer `pages-markdown-v2`. Native HTML and raw HTML embedded
   in Markdown remain unchanged. Caption support and broader rendered-fragment
   diagnostics remain follow-on work.

   - Preserve the existing heading, list, link, code, and table structure.
   - Add `scope="col"` to generated column-header cells in simple Markdown
     tables. Delivered. Add row-header scope only when the authored structure
     identifies a row header; do not infer it merely from the first cell in each
     row.
   - Preserve authored table captions and accessible names when the selected
     Markdown profile supports them. Do not manufacture captions from nearby
     prose.
   - Keep matching-title H1 removal deterministic so a Canvas Page has one
     effective page title while the remaining heading hierarchy starts at the
     correct level.

2. Give preformatted content and tables a defined narrow-viewport behavior.

   - Test representative Page fragments at 320 CSS pixels and at 400% zoom.
     Avoid full-page horizontal scrolling caused by code blocks, tables, or
     long unbroken tokens.
   - Establish a Canvas-compatible policy for local scrolling or wrapping of
     preformatted blocks. Candidates include allowing a verified
     `overflow-x: auto` declaration, emitting a safe scrolling wrapper, or
     using documented `white-space: pre-wrap` behavior where that does not
     alter the meaning of the content.
   - Verify the chosen markup and inline styles after Canvas readback rather
     than assuming the editor preserves them.

3. Extend `pages css-check` with reliable WCAG-oriented color diagnostics.

   - Compute contrast when foreground and background colors are both
     determinable, including inherited colors and nested combinations such as
     linked inline code.
   - Apply the WCAG 2.2 AA thresholds appropriate to ordinary text, large text,
     and meaningful non-text graphics or boundaries. Do not treat decorative
     borders as required contrast.
   - Report inherited Canvas-shell colors, images, gradients, transparency, or
     other unresolved combinations as indeterminate/manual review rather than
     as automatic passes or failures.
   - Keep CSS compatibility findings distinct from accessibility findings. CSS
     validation is not a complete accessibility audit.

4. Extend `sources lint` to inspect final Page HTML as well as source text.

   - Check heading order, duplicate source-title H1s, table header
     associations, preserved captions, and preformatted-content overflow risk.
   - Warn about vague link labels when a label is difficult to understand even
     in its programmatic context, but do not turn context-dependent labels into
     unconditional errors.
   - Flag missing document language only for standalone HTML documents. Canvas
     Page fragments inherit language from the surrounding Canvas document.
   - Surface which checks require live Canvas testing, including keyboard focus
     visibility, focus not obscured, zoom/reflow in the Canvas shell, and other
     behavior that a static fragment cannot establish.

5. Add generic fixtures and preserve deterministic output.

   - Cover Markdown and native-HTML tables, code blocks, long tokens,
     matching-title H1s, contextual and non-contextual link labels, color
     inheritance, and determinate versus indeterminate contrast pairs.
   - Add Canvas readback fixtures for any new table attributes, wrappers, or
     inline styles.
   - Treat accessibility-affecting HTML normalization changes like other
     renderer changes: make dry-run body diffs explicit and bump the relevant
     renderer or compatibility-profile version when required.

Definition of done:

- `pages render` emits stronger table semantics and reflow-safe output for the
  representative fixtures, and Canvas readback preserves the result.
- `pages css-check` and `sources lint` report actionable, reproducible findings
  without claiming that a passing static check establishes WCAG conformance.
- Command help and Pages documentation explain the automated checks, their
  limits, and the remaining manual Canvas checks.

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

These items came from field use after the 2026-06-24 backlog consolidation.
Items 3 and 4 shipped in 0.6.0, and item 5 is now reflected in the external
skill docs. A CASS transcript review covering the preceding 100 days on
2026-08-09 confirmed the relevance of items 1, 2, and 6 through 9, and added
items 10 and 11 below. Items 6, 8, 9, 10, and 11 are implemented and have passed
their bounded live or read-only field cases. Items 1 and 2 shipped together in
v0.11.0 after bounded live acceptance; item 11 shipped in v0.10.2 and its
exact-install acceptance is superseded by the verified v0.11.0 installation.
Item 7 is explicitly deferred because Canvas does not expose a supported API for
initiating its native instructor gradebook CSV export.

### Current Priority Order

Sprint 16 shipped in 0.13.0, dependency maintenance shipped in 0.13.1, Sprint 17
shipped in 0.14.0, Sprint 18 in 0.15.0, Sprint 19 in 0.16.0, and Sprint 20 in
0.17.0. The accepted public-readiness program temporarily supersedes the prior
feature order:

1. Implement the accepted Sprint 21
   [generalization, packaging, and public-beta gate](sprints/21-generalization-packaging.md)
   for 0.18.0.
2. Revisit the Page asset adapter and grouped-case setup after the readiness
   program, based on concrete workflow demand.

Named post-Sprint 20 maintenance: resolve interrupted Panopto caption-bundle
restart behavior. Sprint 19 deliberately retained unique-name recovery after
an interrupted run; Sprint 20 kept it out of scope. The accepted Sprint 21
design owns deterministic pair reconciliation and refusal of ambiguous
artifacts.

Sprint 10 was selected because items 6 and 10 are two halves of the
same operational guarantee: a grade-posting run must state exactly what Canvas
accepted and whether the targeted students can see the resulting grades. The
sprint applies the same partial-write contract to `grades clear`, adds private
durable receipts that the previous terminal-only commands lacked, and does not
broaden into grade-posting-policy mutation or gradebook export. It is now
implemented and locally verified with Ruff, ty, and all 360 tests. Its bounded
live Canvas field case passed on 2026-08-11 after explicit authorization of the
sandbox enrollment. The production replacement fallback, exact verification,
release conclusion, idempotent stable-ID rerun, restoration, and cleanup all
passed. An initial unpublished-assignment update was authoritatively unchanged
and correctly classified before the guarded assignment was temporarily
published with notifications disabled.

Sprint 11 is implemented in `docs/sprints/11-safe-assignment-release.md` on the
0.9.0 development line. It adds stable upload URLs, duplicate-action preflight,
`allowed_extensions` and exact file-target verification, explicit
partial/indeterminate conclusions, and safe assignment output projections.
Existing `unlock_at` and `group_category_id` comparisons were preserved rather
than reimplemented. Ruff, ty, and all 381 tests pass locally. The bounded live
Canvas field case passed on 2026-08-11 and its disposable assignment/files were
removed. Sprint 10's field gate is complete, and the combined implementation
shipped in `v0.10.0`.

Office package-part comparison, transcript filing, and other smaller workflow
enhancements remain deferred unless a concrete course workflow changes this
ordering.

1. Generalize seeded discussion creation beyond grouped cases.

   Status: shipped in v0.11.0 after bounded disposable-topic acceptance.

   Existing related item: Sprint Candidate E.3. The new evidence is that seeded
   prompts are useful for ordinary course discussions, not just grouped-case
   setup. The command should replace course-specific posting scripts, support
   dry-run/readback, preserve graded-discussion assignment metadata, write source
   map provenance, and return topic, assignment, URL, and entry IDs.

2. Add safe discussion source update and verification.

   Status: shipped in v0.11.0 through Sprint 14. `--body-only` sends only the
   root topic message, and neither update scope mutates discussion entries.

   ```bash
   danvas discussions verify content/discussions/unit-4.md --discussion-id 202
   danvas discussions update content/discussions/unit-4.md --discussion-id 202 --body-only --dry-run
   ```

   Desired behavior:

   - Compare local discussion Markdown/front matter to Canvas topic state and
     the associated graded assignment: title, body, due date, points, published
     state, assignment linkage, and Canvas URL.
   - Compare seeded prompt count and headings when entry IDs or prompt source
     metadata are available, and surface `not_available` when they are not.
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
   danvas grades clear --assignment-id 202 \
     --grades-csv grades-to-clear.csv --dry-run
   ```

   Exact comment cleanup is selected per CSV row with the `CommentID` and
   `Comment` columns; there is no separate `--comments` option.

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

6. Fix exact grade-comment replacement and partial-write reporting.

   Implemented on the 0.8.0 development line through
   `docs/sprints/10-truthful-grade-posting.md` together with item 10 and the
   equivalent multi-step failure boundary in `grades clear`. Local automated
   verification passes, and bounded live Canvas acceptance passed on
   2026-08-11 using an explicitly authorized sandbox enrollment. Exact
   replacement, authoritative verification, stable-ID idempotence, restoration,
   and disposable-assignment cleanup all succeeded.

   Field evidence from a live one-row grade correction on 2026-07-19:

   - A guarded `danvas grades post --dry-run` correctly planned a grade change
     and `CommentAction=replace_exact` against an instructor-owned comment.
   - The live command changed the grade, then failed while replacing the comment
     with `AttributeError: 'dict' object has no attribute 'extend'`.
   - `edit_submission_comment()` passes a dictionary as CanvasAPI request
     `_kwargs`, but CanvasAPI's requester expects a list of parameter tuples and
     calls `.extend()` on it.
   - The current test double defines `edit_comment()`, which the production
     CanvasAPI `Submission` object does not provide, so the broken requester
     fallback is not exercised by the existing replacement test.
   - The command reported `Posted: 0, Failed: 1` even though the grade write had
     succeeded, leaving a partial grade/comment state that required immediate
     readback and a two-step exact-delete-plus-append recovery.

   Required fixes:

   - Encode the comment-edit request with CanvasAPI's `combine_kwargs()` or an
     equivalent list of `(key, value)` tuples rather than a dictionary.
   - Add a regression test that exercises the production requester fallback on
     an object without `edit_comment()`; do not rely only on the convenience
     method supplied by `FakeSubmission`.
   - After any per-row mutation exception, read the submission back and report
     whether the grade, comment, both, or neither changed. Do not summarize a
     partially applied row as though no write occurred.
   - Add compensating rollback or a clearly bounded recovery artifact for
     multi-step grade-plus-comment mutations. The command must either restore
     the captured pre-write state or explicitly stop with exact partial-state
     evidence and a safe next command.
   - Cover grade-success/comment-failure and comment-success/grade-failure cases
     with tests, including rollback evidence and final verification behavior.

   Definition of done:

   - `replace_exact` passes a live-equivalent requester test and a bounded Canvas
     field acceptance check.
   - A combined grade/comment failure cannot be reported as an all-or-nothing
     failure when Canvas has already accepted one part of the mutation.
   - Recovery preserves instructor-comment ownership checks, exact matching,
     expected-current-grade guards, rollback evidence, and readback verification.

7. Add an explicit live Canvas gradebook export/download command.

   Status: deferred on 2026-08-11 after source and API investigation. Continue
   using Canvas's native Gradebook export UI, then pass the downloaded CSV
   unchanged to `danvas gradebook check` or `danvas gradebook audit`. Do not add
   a stub `gradebook export` command: a discoverable command that only explains
   why it cannot run would misrepresent the supported CLI surface.

   Canvas's native export is initiated by the UI-only
   `POST /courses/:course_id/gradebook_csv` route. The route returns progress and
   attachment IDs, after which the documented Progress and Files APIs can be
   used, but Canvas's bearer-token authentication is normally limited to
   `/api/` requests. The existing danvas API token therefore cannot reliably
   initiate the native export. Reconstructing a lookalike CSV from Assignments,
   Submissions, and Enrollments APIs was rejected because it would not preserve
   Canvas's authoritative weighted-group, drop-rule, unposted-grade,
   differentiated-assignment, and enrollment-filter semantics. Browser-session
   cookie/CSRF automation is disproportionate to the easy manual export and
   would create a fragile credential boundary.

   Revisit only if Canvas publishes a supported native gradebook-export API or
   repeated field use demonstrates that the manual download is a material
   operational burden.

   Investigation references:

   - [Canvas Gradebook CSV controller](https://github.com/instructure/canvas-lms/blob/master/app/controllers/gradebook_csvs_controller.rb)
   - [Canvas bearer-token authentication](https://github.com/instructure/canvas-lms/blob/master/lib/authentication_methods.rb)
   - [Canvas Progress API](https://developerdocs.instructure.com/services/canvas/resources/progress)
   - [Canvas Files API](https://developerdocs.instructure.com/services/canvas/resources/files)

   Field evidence from the INSY 6600 Test 1 posting workflow on 2026-07-19:

   - `danvas grades post` and assignment-submission readback could verify a
     targeted score column, but they could not verify the final course-facing
     gradebook layout and weighted-group behavior.
   - The existing `danvas gradebook check` and `gradebook audit` commands require
     a manually exported Canvas gradebook CSV.
   - After moving preserved quiz submissions into a 0%-weighted group and
     posting consolidated scores to a new weighted assignment, the remaining
     verification step required leaving danvas to download the gradebook.

   Original proposed command shape:

   ```bash
   danvas gradebook export --output grading/current-gradebook.csv
   danvas gradebook check grading/current-gradebook.csv
   ```

   Original desired behavior:

   - Download the same instructor gradebook CSV represented by Canvas's Gradebook
     export, using an authenticated supported Canvas endpoint rather than browser
     automation when one is available.
   - Require an explicit output path, refuse overwrite unless `--overwrite` is
     supplied, and mark the file private (`0600`).
   - Keep the command read-only and explicit-output; do not create a report run
     by default.
   - Preserve the raw Canvas export so it can be passed directly to `gradebook
     check` or `gradebook audit` without schema conversion.
   - Report the course ID, output path, file size, and SHA-256 after download,
     while never persisting access tokens, verifier URLs, or temporary signed
     download URLs.
   - Define and test how active, inactive, concluded, and test-student enrollments
     appear so audits can distinguish a missing grade from a roster-state filter.
   - If Canvas requires asynchronous export generation, poll with a bounded
     timeout and leave clear failure evidence without a partial file.

   Original definition of done:

   - A live field test produces a CSV accepted unchanged by both existing
     gradebook commands.
   - Private permissions, no-clobber behavior, timeout handling, and secret/URL
     redaction have automated coverage.
   - README and the external teaching-danvas command reference document the new
     explicit-output workflow.

8. Harden assignment release, file-link verification, and report sanitization.

   Status: implemented on the previously untagged 0.9.0 development line through
   `docs/sprints/11-safe-assignment-release.md`. Ruff, ty, and all 381 tests pass
   locally, and bounded live Canvas acceptance passed on 2026-08-11 with cleanup
   verified. A 2026-08-11 source audit confirmed that `unlock_at` and
   `group_category_id` verification already existed and did not find the
   previously observed generic numeric date enrichment. Those behaviors now
   have regression coverage alongside the new upload-link, declared-field,
   file-identity, status, and output-safety work.

   Field evidence from the INSY 6600 Case Study 3 release on 2026-07-23:

   - `danvas files upload --dry-run` and the live upload both succeeded, but the
     structured upload output exposed only `canvas_id` and `url_present: true`,
     not a reusable stable Canvas course-file URL. The assignment wrapper had to
     construct `https://.../courses/{course_id}/files/{file_id}?wrap=1`
     manually.
   - The upload dry-run reported only `status: dry-run`; it did not distinguish
     whether each target would be created, overwritten, or renamed under the
     selected duplicate policy.
   - `danvas assignments verify` reported `matches`, but its comparison covered
     only title, points, due/lock dates, published state, assignment-group name,
     submission types, grading type, and normalized body text. It did not check
     `unlock_at`, `allowed_extensions`, `group_category_id`, or the actual link
     targets and Canvas file IDs embedded in the live HTML.
   - Exact file-link and extension verification therefore required a full
     assignment export and manual inspection, even though the normal verification
     result appeared complete.
   - The routine assignment-verification JSON report retained the raw Canvas
     assignment description with verifier-bearing file URLs and a
     `secure_params` value. This conflicts with the durable report contract that
     ordinary reports remain free of verifier URLs and secure parameters.
   - Generic date enrichment also produced nonsensical derived fields for numeric
     data, including `assignment_group_id_date`, `enrollment_term_id_date`, and
     `storage_quota_mb_date`. Only known timestamp fields should receive parsed
     date companions.

   Required fixes:

   - Sanitize assignment verification and export report payloads before writing
     them. Ordinary reports must omit raw `secure_params`, remove verifier and
     signed URL parameters, and retain only stable Canvas URLs or extracted file
     IDs. If an explicit raw mode is ever added, classify it as private output,
     require an intentional opt-in, and use private permissions.
   - Restrict date enrichment to an allowlist or reliably typed timestamp fields
     such as `due_at`, `unlock_at`, `lock_at`, `created_at`, and `updated_at`.
     Add regression tests proving IDs, counts, quotas, and other numeric fields
     never gain synthetic `_date` values.
   - Expand assignment verification to compare every supported stable field that
     is declared locally, including `unlock_at`, `allowed_extensions`, and
     `group_category_id`. Report `checked fields match` or an explicit partial
     status when some fields are unsupported rather than implying a complete
     match.
   - Canonicalize local and live assignment links by removing volatile query
     parameters, extract stable Canvas course/file IDs, and verify that every
     required link targets an existing file in the current course. Link text
     equality is not sufficient.
   - Return a safe stable `canvas_url` for every successful file upload, alongside
     the file ID and Canvas path, without retaining the raw verifier/download
     URL. The output should be directly usable in assignment Markdown.
   - Make upload dry-runs resolve duplicate behavior and report `would_create`,
     `would_overwrite`, `would_rename`, or a bounded conflict with the existing
     target ID when available.

   Lower-priority follow-ons:

   - Implement the Sprint 16 verified Markdown asset design on these hardened
     primitives so an assignment can declare local release files, upload or
     reuse them, rewrite only Canvas-bound HTML, and verify the final targets
     without mutating authored source unexpectedly. Page, announcement, and
     discussion adapters remain separately bounded follow-ons.
   - Decide whether `danvas status` should report local-only files for configured
     release-source directories, or provide a narrower release-asset audit that
     does so without turning status into whole-tree file synchronization.
   - Reconcile the source-lint duplicate-title/H1 warning with established Canvas
     assignment-wrapper conventions. Prefer source-kind-aware guidance or an
     explicit suppression mechanism over weakening the rule globally.
   - Consider minute-semantic assignment date comparison only for date-only
     authored fields; preserve exact timestamp comparison for explicitly authored
     datetimes.

   Definition of done:

   - The Case Study 3 release workflow can upload two files, obtain safe stable
     links, create the assignment, and verify all declared metadata and exact file
     IDs without constructing URLs manually or reading a raw full export.
   - A successful verification cannot report a complete match while declared
     supported fields or Canvas file targets remain unchecked.
   - Verification/report fixtures prove that verifier parameters,
     `secure_params`, access tokens, and signed URLs are absent from ordinary
     JSON, Markdown, manifests, stdout, diagnostics, and source-map data.
   - Date-normalization tests prove that only genuine timestamp fields receive
     parsed date companions.
   - Upload dry-run and live output have stable, documented action statuses and
     safe URL fields, with README and external teaching-danvas command-reference
     updates when the command surface changes.

9. Make course snapshots resilient to endpoint-specific authorization gaps.

   Status: released in `v0.10.0` through
   `docs/sprints/12-authorization-resilient-snapshots.md`. Ruff, ty, and all 395
   tests pass locally, CI passed for the release commit, and bounded read-only
   field acceptance passed on 2026-08-11. The field case reproduced
   `Forbidden` for group-category enumeration in historical course 1685356
   while the same credentials returned an available, empty collection in
   sandbox course 1576638. This confirms the practical course/endpoint-specific
   gap without implying a token-wide failure.

   Field evidence from archiving the concluded Fall 2025 INSY 6500 course on
   2026-07-27:

   - `danvas init 1665637` successfully reached the course and ordinary course
     metadata, but Canvas returned `403 Forbidden` while enumerating
     `/api/v1/courses/1665637/group_categories`. Because snapshot collection
     calls that endpoint unconditionally, the command did not create the normal
     schema-v4 `.danvas/course.json`.
   - Group-category collection was added to the expanded snapshot in commit
     `4020c45` on 2026-06-12. Successful initialization before that commit did
     not exercise this endpoint. Post-change snapshots for active courses have
     succeeded, including a course with populated group categories, which argues
     against a token-wide or general Canvas authorization failure.
   - The available evidence cannot distinguish whether Canvas access changed
     when course 1665637 concluded or whether this endpoint was always
     inaccessible for that course. Treat this as a newly exposed,
     course/endpoint-specific permission edge case rather than a confirmed
     general permissions change.

   Investigation and proposed behavior:

   - Reproduce the exact read-only group-categories request against concluded
     and active courses with the same instructor credentials. Record sanitized
     HTTP status and relevant course/enrollment state without persisting tokens,
     signed URLs, or student data.
   - Determine which snapshot collections are required for a usable course
     snapshot and which are optional enrichments. A 401/403 on an optional
     collection should produce an explicit warning and availability marker
     while allowing `init` or `refresh` to complete; it must not silently become
     an empty list.
   - Preserve the distinction between `available and empty`, `unavailable due
     to authorization`, and `collection failed`. Ensure `refresh --diff` and
     `status` do not report removals merely because a section was unavailable
     during the latest refresh.
   - Add regression coverage for a group-categories 403, including any nested
     per-category group lookup, while preserving current active-course snapshot
     behavior. Consider whether the same policy should apply to other optional
     snapshot endpoints only after their required/optional status is explicit.

   Definition of done:

   - `danvas init` and `danvas refresh` can produce an explicitly partial but
     structurally valid snapshot for a historical course when an optional
     endpoint is forbidden.
   - The CLI reports the inaccessible section and HTTP status clearly, without
     misrepresenting it as empty or exposing sensitive response data.
   - Snapshot diff/status behavior and automated tests distinguish unavailable
     metadata from actual Canvas-side deletion.

10. Record assignment release state with grade-posting verification.

   Implemented on the 0.8.0 development line through
   `docs/sprints/10-truthful-grade-posting.md` together with item 6. The sprint
   uses targeted submission `posted_at` and `assignment_visible` evidence, while
   treating assignment publication, availability dates, and manual-posting
   policy as context rather than proof of student visibility. Local automated
   verification passes, and bounded live Canvas acceptance passed on
   2026-08-11 using an explicitly authorized sandbox enrollment. The accepted
   receipt reported `verified_visible`; exact state restoration and disposable
   assignment cleanup were independently confirmed.

   Field evidence from a 16-student INSY 7750 posting workflow on 2026-08-07:

   - `danvas grades post` successfully verified every score and exact comment,
     but the operator separately captured assignment state to establish whether
     the grades remained hidden or had become visible to students.
   - Exact score/comment readback is therefore necessary but not sufficient as
     end-to-end posting evidence when release timing matters.

   Desired behavior:

   - Include a sanitized assignment release-state summary in `grades post` and
     `grades verify` evidence whenever Canvas exposes the relevant fields:
     publication state, availability dates, and grade-posting/visibility state.
   - Clearly distinguish `verified hidden`, `verified visible`, and `student
     visibility not determined`; do not infer visibility from assignment
     publication alone.
   - Preserve the existing private grade/comment evidence boundary: the summary
     must not expose student data, access tokens, or verifier-bearing URLs.
   - Capture the state in the normal post/write report so operators do not need
     an ad hoc, separate assignment snapshot for a grading close-out.

   Definition of done:

   - A grade-post report states both row-level score/comment verification and
     the supported assignment release-state conclusion.
   - Tests cover hidden, visible, unavailable/unsupported, and date-limited
     state representations without overstating what Canvas reports.

11. Add installed-CLI health coverage to the release workflow.

   Status: shipped in v0.10.2 on 2026-08-11. Main and exact-tag CI passed,
   including both isolated install lanes. An exact tagged v0.11.0 global
   installation was subsequently validated on 2026-08-12. See
   `docs/sprints/13-installed-cli-release-health.md` for the bounded script,
   CI, version-matching, documentation, and acceptance contract.

   Field evidence from a course status workflow on 2026-06-25:

   - The globally installed editable `danvas` launcher failed before command
     parsing because its isolated environment held an incompatible `secretpath`
     version.
   - A normal reinstall was initially blocked by a global uv `exclude-newer`
     policy, despite the project environment working correctly. The operational
     workflow required a project-environment workaround until the tool install
     could be repaired.
   - The 2026-08-11 `v0.10.0` close-out successfully built wheel/sdist artifacts,
     installed the wheel in an isolated temporary tool directory, and installed
     the global CLI from the exact Git tag. Version, help, and local auth-doctor
     checks passed outside the repository environment. This is a usable manual
     template but is not yet encoded in CI or durable installation guidance.
   - The same close-out exposed two maintenance warnings worth handling in this
     release-engineering slice: local uv 0.12.1 is newer than the declared
     `uv-build>=0.11.0,<0.12.0` backend range, and GitHub Actions reports that
     `actions/checkout@v4` and `astral-sh/setup-uv@v5` still target deprecated
     Node.js 20 while the runner forces Node.js 24.

   Desired behavior:

   - Define the supported installation modes (editable development checkout and
     tagged release) and smoke-test each in its isolated tool environment.
   - After installation, verify `danvas --version` and a minimal import/auth
     diagnostic before treating the installation as usable.
   - Document how dependency freshness constraints such as uv's
     `exclude-newer` affect a local editable reinstall, including a scoped
     recovery path that does not weaken the user's global policy.
   - Keep this as release engineering and documentation work unless a future
     import-boundary design can make `danvas auth doctor` available when optional
     authentication dependencies are broken.

   Definition of done:

   - Release close-out and editable-install guidance include a reproducible
     isolated-environment smoke test.
   - A dependency mismatch fails with an actionable diagnostic rather than a
     raw import traceback where practical.
   - CI or release verification exercises the documented install path without
     relying on the repository virtual environment.

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
- Do not treat `gradebook.py` cleanup as a product feature. It can be done
  opportunistically when changing gradebook behavior, but it should not drive
  sprint planning by itself.
- Do not keep the original Sprint 2/Sprint 3 order as binding. The report-run
  work changed the planning surface; use the current sprint candidates instead.
- Do not turn `danvas` into archival/history tooling. It remains an operational
  Canvas CLI; durable archival ledgers and course-history databases stay separate.
