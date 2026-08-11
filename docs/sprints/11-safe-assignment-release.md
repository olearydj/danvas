# Sprint 11: Safe Assignment Release Evidence

Status: implemented, locally verified, and accepted in a bounded live Canvas
field case on 2026-08-11; release close-out remains pending. Target release:
0.9.0.

## Objective

Make the existing file-upload-to-assignment workflow produce safe, reusable
Canvas file links and a verification result that proves every declared stable
assignment field and Canvas file target that danvas claims to check.

A successful assignment verification must never retain a credential-bearing
URL, report a complete match while a declared field was skipped, or require an
operator to inspect a raw Canvas assignment export to confirm file identity.

This sprint refines field-observed backlog item 8. It does not implement
Markdown asset rewriting, automatic assignment publication, or broad file
synchronization.

## Release Gate

Sprint 10 is implemented on the unreleased 0.8.0 line and passed its explicitly
authorized live Canvas acceptance case on 2026-08-11. Keep Sprint 11 as a
separate 0.9.0 feature slice because it changes
file-upload evidence, assignment-verification semantics, and multiple
ordinary-output safety boundaries. Its earlier external gate is now complete;
the development-line release states still need consolidated close-out.

## Current-State Audit

The 2026-08-11 source and test audit found that the original backlog report is
partly stale:

- `assignments verify` already compares `unlock_at` and `group_category_id`
- local assignment parsing already accepts `allowed_extensions`, but verify does
  not retain or compare it
- no generic numeric-to-`*_date` enrichment exists in the current source tree;
  retain this as a regression invariant rather than adding corrective code
- file upload failures already sanitize common URL/error leakage, but successful
  output exposes only `canvas_id` and `url_present`, not a safe reusable link
- upload dry-run resolves the folder but labels every row only `dry-run`
- assignment verify/update/upsert reports embed a Canvas record containing the
  raw assignment payload; verify and full export can therefore retain raw HTML,
  `secure_params`, or verifier/signed URLs
- assignment verification compares normalized visible body text, so two bodies
  can match even when their file link targets differ

The implementation should remove the residual gaps without reimplementing
already-delivered field comparisons.

## Canvas API Constraints

The design relies on these documented Canvas behaviors:

- file upload `on_duplicate` supports `overwrite` and `rename`; the completed
  upload returns a Canvas File representation
- a File representation includes stable identity fields such as `id`,
  `folder_id`, `display_name`, and `filename`, but its returned `url` is a
  download URL and is not a durable report value
- `GET /api/v1/courses/:course_id/files/:id` provides a course-scoped existence
  and membership check
- Canvas rich-content HTML may add `data-api-endpoint` and
  `data-api-returntype="File"`, which are useful identity evidence but must
  agree with any file ID in `href` or `src`
- Assignment objects document `allowed_extensions`, `unlock_at`, and
  `group_category_id` as stable fields available for comparison when present

Do not depend on upload-token parameter names, temporary upload URLs, verifier
values, signed storage URLs, or Canvas's exact server-side rename suffix.

## Command Surface

Preserve the existing commands and required options:

```bash
danvas files upload --folder 'course files/cases' FILE... --dry-run
danvas files upload --folder 'course files/cases' FILE...
danvas assignments verify content/assignments/case.md
danvas assignments export --output assignments.json
danvas assignments export --full --output assignments-full.json
```

No new command or required flag is needed. Existing JSON/report fields gain
stronger documented semantics.

`assignments export --full` means an extended sanitized projection, not a raw
Canvas payload. Do not add a raw-output mode in this sprint. If one is ever
justified, it must be an explicit opt-in, classified private from creation, and
designed separately.

## Shared Canvas Link Module

Add `src/danvas/canvas_links.py` as a pure, separately tested module. It owns:

- normalization and same-origin comparison for the configured Canvas origin
- construction of the stable course-file view URL
  `{origin}/courses/{course_id}/files/{file_id}?wrap=1`
- parsing file identity from course-relative and same-origin absolute URLs,
  including view, download, preview, and documented API endpoint forms
- extraction of Canvas file references from rich-content HTML attributes such
  as `href`, `src`, `data-api-endpoint`, and `data-download-url`
- detection of conflicting IDs or course contexts on the same element
- removal or rejection of verifier, token, signature, expiry, `secure_params`,
  `x-amz-*`, and `x-goog-*` values
- safe link-evidence projections that never retain a raw signed/download URL

Move only generic origin helpers out of `pages.py` if parity tests prove the
existing Page canonicalization result is unchanged. Keep Page-specific HTML
normalization and hashing in `pages.py`; do not broaden this sprint into a Page
refactor.

Keep upload orchestration and duplicate planning in `files.py`. Keep assignment
loading, Canvas reads, comparison aggregation, and report rendering in
`assignments.py`. A second new module is not warranted unless implementation
shows a genuinely independent policy boundary.

## Stable File Upload Evidence

### Dry-run planning

After resolving and validating the destination folder, list its current files
once and compare each local basename to Canvas `display_name`. Produce one of:

- `would_create`: no exact current name exists
- `would_overwrite`: one exact name exists and `on_duplicate=overwrite`; include
  its Canvas file ID
- `would_rename`: at least one exact name exists and `on_duplicate=rename`;
  include conflicting IDs but do not predict Canvas's final name
- `conflict`: the current state is ambiguous or cannot support a truthful plan

Dry-run is an online point-in-time plan, not a lock. Its report must say that
the live result remains authoritative if Canvas changes before upload.

Deduplicate the folder listing and preserve the current local preflight that
rejects missing files and unsafe duplicate local basenames before Canvas
mutation.

### Live results

For every successful upload, report only stable/safe fields:

- `status: uploaded`
- `canvas_id`
- `folder_id`
- final `display_name` and `filename` from Canvas
- final `canvas_path`
- generated stable `canvas_url`
- size and content type when present

Construct `canvas_url` from the configured trusted Canvas origin, course ID,
and returned file ID. Never copy or trim the response's raw `url`,
`download_url`, upload URL, or preview URL into durable output. Remove
`url_present` after documenting the replacement; `canvas_url` is the supported
field.

Keep the existing nonzero partial-failure behavior. Successful rows remain
usable when another row fails, while all failure text continues through the
sanitized error boundary.

## Assignment Evidence Projection

Build reports from explicit safe projections rather than recursively serializing
CanvasAPI objects and deleting a few known keys afterward.

The ordinary safe assignment projection may include:

- stable IDs, title, points, grading/submission configuration, publication,
  availability dates, and supported group/assignment-group identity
- `allowed_extensions`
- normalized visible body text or body hash
- safe extracted Canvas file-link evidence
- redacted override counts already supported elsewhere
- stable same-origin Canvas object URLs without volatile query values

It must not include raw assignment `description` HTML, `secure_params`, raw
CanvasAPI payloads, verifier/download/preview URLs, signed storage URLs,
authorization headers, tokens, or unredacted override membership.

Apply this output boundary to:

- `assignments verify` JSON and Markdown reports
- assignment update/upsert plans and readback reports
- assignment create/update dry-run terminal payloads when they echo authored
  link-bearing HTML
- normal and `--full` assignment exports in JSON, CSV, and Markdown
- report manifests, diagnostics, stdout summaries, and source-map values derived
  from assignment results

Mutation payloads may retain the authored HTML in memory for the Canvas request;
the safe projection requirement applies before any terminal or durable output.

Sanitize exception text with the shared report error boundary before retaining
it. Do not write `str(exc)` directly into assignment reports.

## Declared-Field Verification

Track which front-matter fields were explicitly declared rather than inferring
coverage from nonblank normalized values. Always verify the required title and
body; verify every supported stable field declared locally.

The supported comparison set for this sprint is:

- title
- points possible
- due, unlock, and lock timestamps
- published state
- assignment-group ID or resolved assignment-group name
- submission types
- grading type
- group-category ID
- allowed extensions
- normalized visible body text
- Canvas file identities embedded in the rendered body

Normalize `submission_types` and `allowed_extensions` as order-independent
sets. Extension comparison is case-insensitive and ignores a leading dot, but
the mutation payload remains unchanged. Preserve the current timestamp
semantics; minute-semantic comparison remains deferred.

Do not claim coverage for accepted-but-unverified metadata. If a locally
declared field is outside the supported comparison set, report it as
unsupported and make the overall result partial rather than silently omitting
it.

## Canvas File-Link Verification

Extract file references independently from the locally rendered HTML and the
live Canvas HTML. Compare a multiset of current-course Canvas file IDs so that
Canvas-added decorators and volatile query strings do not create false drift,
while missing, changed, or duplicated targets remain visible.

For every unique expected file ID:

1. reject an explicitly different course ID without contacting that course
2. call the course-scoped file endpoint to prove the target exists in the
   current course
3. record only the file ID, stable generated URL, safe Canvas path/name, and
   bounded status
4. treat a disagreement between `href`/`src` and `data-api-endpoint` on one
   element as a mismatch

External web links are outside this sprint's reachability scope. Do not retain
their raw query strings in evidence. Relative local asset links remain
unresolved and produce partial verification; automatic upload/rewriting is a
later sprint.

Deduplicate course-scoped file reads by ID. A 404 is an authoritative mismatch.
Authorization, throttling, or transient read failures are indeterminate, not
proof that the file is absent.

## Verification Status Contract

Use these top-level `assignments verify` statuses:

- `matches`: every required and explicitly declared supported field matches,
  file-ID multisets match, every expected Canvas file exists in the current
  course, and no required check is unavailable
- `mismatch`: at least one authoritative field or link check differs, a target
  belongs to another course, or a required file is authoritatively not found
- `partial`: no authoritative mismatch exists, but at least one declared field,
  relative asset, or required comparison is unsupported or unavailable while
  other checks remain trustworthy
- `indeterminate`: the assignment read or another foundational read failed, so
  no trustworthy overall comparison can be made

Return zero only for `matches`. Reports and manifests for all other statuses are
failed evidence runs. Preserve machine-readable per-check status and reason
values; retain the existing `matches` boolean on ordinary field checks where it
is unambiguous for compatibility.

An assignment 404 becomes `mismatch` with reason `assignment_not_found`, rather
than a separate top-level status. Sanitized diagnostics may distinguish 404,
unauthorized, and transient failures without retaining raw response content.

Terminal output is count-first and names only fields/statuses. Raw local or
Canvas HTML and unsafe URL values never appear in the terminal table.

## Output Safety Contract

Before any normal artifact or terminal payload is emitted, tests must be able to
serialize it and prove the absence of:

- access/API tokens and authorization headers
- `verifier` and `secure_params`
- raw Canvas download, preview, or upload URLs
- `signature`, `policy`, expiry, `x-amz-*`, and `x-goog-*` values
- unsafe raw exception payloads
- private assignment-override membership

Unknown nested Canvas keys are not trusted merely because their current fixture
value looks harmless. Prefer allowlisted projections. The generated stable
`?wrap=1` course-file view URL is the only query-bearing file URL emitted by
this workflow.

No command in this sprint becomes a private report merely to make unsafe output
acceptable. The goal is safe ordinary operational evidence.

## Date Regression Boundary

The current tree does not contain the field-observed generic date-enrichment
behavior. Add fixtures proving assignment reports/exports do not synthesize
`assignment_group_id_date`, `enrollment_term_id_date`, `storage_quota_mb_date`,
or any other `*_date` companion from numeric/non-temporal fields.

Only fields explicitly returned or authored as real assignment timestamps are
retained. Do not add a generic date-enrichment helper as part of this sprint.

## Implementation Sequence

1. Add pure link parsing, stable URL construction, safe projection, and
   adversarial tests in `canvas_links.py`.
2. Add upload duplicate planning and stable live result fields in `files.py`.
3. Replace raw assignment report/export payloads with safe projections.
4. Add declared-field coverage and `allowed_extensions` verification.
5. Add HTML file-ID extraction, course-scoped existence checks, and aggregate
   verification statuses.
6. Sweep JSON, CSV, Markdown, manifest, stdout, diagnostic, and source-map
   boundaries with sentinel-secret tests.
7. Update README, CLI help, backlog status, and both external
   `teaching-danvas` skill files when behavior ships.
8. Run Ruff, ty, and the full pytest suite before any live Canvas acceptance.

## Automated Acceptance

Tests must cover:

- same-origin absolute and course-relative file links
- view, download, preview, API-endpoint, `href`, `src`, and
  `data-api-endpoint` variants
- mismatched attribute IDs, cross-course IDs, missing IDs, malformed URLs,
  fragments, encoded paths, credentials in authority, and unexpected ports
- removal/rejection of verifier, token, signature, expiry, `secure_params`,
  `x-amz-*`, and `x-goog-*` values
- stable upload URL construction from configured origin/course/file identity
- dry-run create, overwrite, rename, ambiguous conflict, and concurrent-state
  limitation reporting
- live successful, renamed, overwritten, partial-failure, and unsafe-error
  upload responses
- explicit empty and populated `allowed_extensions`
- already-delivered `unlock_at` and `group_category_id` comparisons
- exact declared-field coverage and unsupported-field partial status
- identical body text with changed file ID
- duplicate links to one file and deduplicated course-scoped file reads
- file exists, file 404, cross-course link, unauthorized read, throttled read,
  and transient failure
- `matches`, `mismatch`, `partial`, and `indeterminate` aggregation and exit codes
- sanitized verify/update/upsert/create/export JSON, CSV, Markdown, manifests,
  stdout, diagnostics, and source-map data
- `--full` export remaining an extended safe projection
- absence of synthetic numeric `*_date` fields
- no behavioral change in existing Page URL canonicalization if shared origin
  helpers move

Local verification on 2026-08-11: Ruff and ty passed, and all 381 tests passed.

## Field Acceptance

After automated verification, use an explicitly authorized sandbox or otherwise
safe course:

1. Prepare two small non-sensitive files, with one destination name absent and
   one already present.
2. Run upload dry-runs for both duplicate policies and retain the plan report.
3. Upload the files, confirming final IDs, Canvas paths, and generated stable
   links without retaining raw download URLs.
4. Create or update a disposable draft assignment source that declares
   `allowed_extensions` and links to both exact file IDs.
5. Verify the assignment and confirm `matches`, complete field coverage, and
   successful current-course file reads.
6. Change one local expected file ID to a nonexistent or cross-course ID and
   confirm a non-mutating `mismatch`; do not create an unsafe live target merely
   for testing.
7. Scan every retained artifact for the sentinel verifier/token/signature values
   used in fixtures and confirm none are present.
8. Restore or remove temporary draft content and uploaded files under the same
   explicit authorization, then record cleanup evidence.

### Field Acceptance Result

Passed on 2026-08-11 in sandbox course 1576638:

- upload dry-runs distinguished `would_create`, `would_overwrite`, and
  `would_rename` without predicting Canvas's renamed filename
- live overwrite and create uploads returned stable course-file URLs and safe
  identity/path evidence
- a disposable unpublished assignment declared `allowed_extensions` and linked
  to both exact uploaded file IDs
- positive verification returned `matches` with all seven declared fields and
  both course-scoped file reads confirmed
- changing one expected file ID to a nonexistent ID produced a non-mutating
  `mismatch` and `not_found` file evidence
- retained acceptance artifacts contained no verifier, `secure_params`, access
  token, or signed-storage query values
- the disposable assignment and uploaded files were removed by exact ID, and a
  final inventory confirmed the sandbox had returned to its original three
  assignments and zero files

This completes the bounded live field gate. Sprint 10's field gate also passed
on 2026-08-11, so only consolidated release close-out remains.

## Exclusions

- automatic Markdown asset upload or Canvas-bound HTML rewriting
- assignment publish/unpublish or module release orchestration
- broad local-vs-Canvas file synchronization
- external HTTP link checking
- raw assignment export mode
- grade posting or grade release-state changes
- minute-semantic assignment date comparison
- source-lint duplicate-title/H1 policy changes
- installed-CLI release health work from backlog item 11

## Definition Of Done

- Upload dry-run states the expected duplicate action for every file without
  predicting an unknowable renamed filename.
- Every successful live upload returns a stable reusable `canvas_url`, Canvas
  file ID, and Canvas path without retaining the raw API file URL.
- Assignment verification checks `allowed_extensions`, every other explicitly
  declared supported field, exact Canvas file-ID multisets, and current-course
  file existence.
- `matches` is impossible when a required declared field or file target was
  skipped, unsupported, unauthorized, or indeterminate.
- Ordinary assignment reports/exports and all related output boundaries are
  free of secret-bearing URLs, `secure_params`, tokens, raw unsafe exceptions,
  and private override membership.
- The Case Study 3 workflow can upload two files, use returned stable links, and
  verify the complete declared assignment/file identity without constructing a
  URL manually or inspecting a raw export.
- README, CLI help, backlog status, sprint index, and the external
  `teaching-danvas` skill/reference describe the shipped behavior.

## Primary References

- [Canvas File Uploads](https://developerdocs.instructure.com/services/canvas/basics/file.file_uploads)
- [Canvas Files API](https://developerdocs.instructure.com/services/canvas/file.all_resources/files)
- [Canvas Assignments API](https://developerdocs.instructure.com/services/canvas/resources/assignments)
- [Canvas API Endpoint Attributes](https://developerdocs.instructure.com/services/canvas/basics/file.endpoint_attributes)
