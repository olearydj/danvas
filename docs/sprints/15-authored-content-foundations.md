# Sprint 15: Authored-Content Foundations And Snapshot Signaling

Status: implemented locally on 2026-08-12. Target release: 0.12.0.

## Outcome

Remove the comparison and redaction drift that produced the 0.10.0 assignment
alias defect and the initial Sprint 14 discussion defects before another
authored-content type is added.

This sprint is structural, but its completion criteria are behavioral:

- every authored datetime is either unambiguous or rejected before Canvas access;
- assignment, announcement, discussion, and Page comparisons use one normalization
  and datetime engine;
- public errors and retained evidence use one sensitive-value vocabulary;
- an invalid Canvas token aborts snapshot collection instead of masquerading as
  one optional unavailable collection;
- partial snapshots retain their usable default behavior while automation can
  explicitly require a complete snapshot and receive a distinct exit status.

No new Canvas object type or mutating command is added.

## Why This Sprint Is Next

The authored-source modules currently contain separate implementations of
scalar normalization, comparison checks, Canvas-object value lookup, datetime
handling, and terminal/report projection. The implementations have already
diverged:

- assignments normalize numbers and order-insensitive lists but compare datetime
  strings literally;
- announcements compare normalized strings and omit a standard check status;
- discussions use shared datetime semantics but retain another scalar normalizer;
- Pages use the shared datetime helper only for `publish_at` and expose a
  different comparison shape;
- accepted-field registries and comparison coverage have historically drifted.

Error boundaries also use different regular expressions in `reports.py`,
`auth.py`, `files.py`, `assignments.py`, and `grade_evidence.py`. The vocabularies
disagree about bearer credentials, `secret=`, signed-cloud parameters, and
sensitive payload keys.

Sprint 12 correctly distinguishes authoritative empty collections from partial
snapshots, but `InvalidAccessToken` is currently classified like an optional
endpoint denial. A globally invalid credential is not collection-local and must
stop the snapshot. Partial snapshots themselves remain useful, so their default
exit-zero contract should not be broken merely to give strict automation a
process-level signal.

## Design Decisions

### 1. Expand `authored_content.py`; do not create a second comparison module

`src/danvas/authored_content.py` already owns the shared datetime comparison
primitive. Expand it into the dependency-free authored comparison layer rather
than introducing `authored_compare.py` or a base command class.

The shared layer owns:

- whitespace, boolean, numeric, and sequence normalization;
- timezone-aware and explicitly date-only datetime comparison;
- construction of the standard comparison row:
  `field`, `status`, `matches`, `local`, and `canvas`;
- bounded Canvas object/dictionary value selection used by authored record
  adapters;
- pure datetime validation that both source loaders and `sources lint` consume.

Feature modules continue to own:

- accepted front-matter fields and aliases;
- local and Canvas record construction;
- identity resolution and source-map provenance;
- mutation payloads and command safety boundaries;
- report schemas, Markdown rendering, and command-specific summaries.

This avoids inheritance and prevents a structural sprint from merging distinct
mutation workflows.

### 2. Use field policies, not a universal coercion rule

The shared comparison entry point accepts a small per-field policy. Supported
policies cover:

- normal scalar values;
- timezone-aware datetimes;
- date-only-or-aware datetimes;
- order-insensitive normalized sequences such as `allowed_extensions`.

The default scalar normalizer preserves booleans, treats integral numeric text
and numeric values equivalently, collapses whitespace in text, and does not sort
arbitrary lists unless the field policy says order is irrelevant.

Every authored command must derive comparison rows and aggregate status from the
same shared result. Terminal summaries after a live mutation must render the
fresh readback rows, never the pre-mutation diff.

Each feature retains a structural test proving that every accepted comparable
field has an explicit comparison policy. The existing discussion coverage test
becomes the pattern for assignments and announcements. Page metadata fields are
covered by their bounded Page-policy table.

### 3. Reject ambiguous timestamps at source load

One pure validator returns a structured issue containing the field and reason.
Source loaders turn the issue into an actionable preflight error; `sources lint`
uses the same issue to produce its lint finding. Neither path reimplements ISO
parsing or timezone detection.

Field policy is explicit:

- Assignment `due_at`, `unlock_at`, and `lock_at` require an ISO timestamp with
  `Z` or an explicit UTC offset.
- Assignment `due_date`, `unlock_date`, and `lock_date` aliases accept a date.
  The loader expands it through the configured course timezone before shared
  validation.
- Announcement `delayed_post_at` and `lock_at` require an aware ISO timestamp.
- Discussion `delayed_post_at`, `due_at`, `unlock_at`, and `lock_at` require an
  aware ISO timestamp.
- Page `publish_at` accepts a date or an aware ISO timestamp.

An offset-free timestamp such as `2026-09-01T23:59:00` is rejected everywhere.
Date-only values remain supported only through the documented assignment aliases
and Page `publish_at` contract. Sprint 14 already enforces the discussion row of
this table; Sprint 15 replaces that local validator with the shared policy.

Timezone-equivalent aware timestamps compare by absolute instant. Page
date-only comparison retains its existing calendar-date semantics. No implicit
local timezone is assigned to an offset-free `*_at` value.

### 4. Add a dependency-free `sanitize.py`

A new `src/danvas/sanitize.py` module is warranted. Redaction is a cross-cutting
safety boundary, not report-run orchestration, and importing `reports.py` merely
to sanitize an authentication or upload error creates unnecessary coupling.

The module owns:

- the canonical sensitive-name vocabulary;
- URL and authorization-header removal from exception text;
- case-insensitive sensitive payload-key detection;
- recursive sanitization for retained public evidence;
- detection of sensitive text for workflows that intentionally replace the
  whole value with a hash instead of returning sanitized prose.

The canonical vocabulary is the union of the currently protected forms,
including:

- `token`, `access_token`, `verifier`, `secret`, `api_key`, and
  `secure_params`;
- `Authorization: Bearer ...` and bare `Bearer ...`;
- `signature`, `policy`, `expires`, `key-pair-id`, `awsaccesskeyid`,
  `x-amz-*`, and `x-goog-*`;
- upload/request URL keys such as `upload_url`, `download_url`, `file_url`, and
  `error_url`.

Policy remains domain-aware:

- error text removes whole URLs and redacts credential values;
- public recursive projections drop sensitive keys and sanitize nested strings;
- stable canonical Canvas object URLs are constructed through existing URL
  helpers and are not passed through the error sanitizer;
- private grade recovery comments continue to replace an entire sensitive value
  with a hash marker, but use the shared detector;
- authored bodies are never rewritten by this sanitizer.

`reports.safe_error` may remain as a compatibility re-export during this sprint,
but no independent sensitive regular expression may remain in reports, auth,
files, assignments, or grade evidence after migration.

### 5. Treat `InvalidAccessToken` as a fatal credential failure

`InvalidAccessToken` indicates that the shared credential is unusable, not that
one optional collection lacks permission. Classification must carry a fatal or
credential-wide distinction. The classifier must test this exception before
broader `Unauthorized` or `CanvasException` classes so inheritance cannot make
the fatal branch unreachable.

At both top-level and nested collection boundaries:

- `InvalidAccessToken` aborts `init` or `refresh` with a concise sanitized error;
- no partial snapshot is written;
- an existing snapshot remains byte-for-byte unchanged;
- no later collection is called after the credential failure;
- the command exits nonzero.

`Forbidden` and endpoint-specific `Unauthorized` retain Sprint 12 behavior for
optional collections. `RateLimitExceeded`, request failures, and other Canvas
errors retain their existing failed/unavailable distinctions. This sprint does
not infer global credential failure from every HTTP 401 when canvasapi has not
classified it as `InvalidAccessToken`.

### 6. Add opt-in strict signaling for partial snapshots

Default behavior remains compatible: an optional collection gap writes an
explicitly partial but usable snapshot and exits zero. The snapshot JSON remains
the authoritative machine-readable record.

Add `--require-complete` to `init`, `refresh`, and `status`:

- `init --require-complete` exits `3` before writing config or snapshot files
  when any collection is non-authoritative;
- `refresh --require-complete` exits `3` before replacing the prior snapshot or
  writing a diff report when the candidate snapshot is partial;
- `status --require-complete` still renders and writes requested status evidence,
  then exits `3` when its source snapshot is partial;
- exit `1` remains a fatal operational failure, while Typer's argument/usage
  failures retain exit `2`.

Partial-snapshot warnings move to stderr in both default and strict modes. JSON
and report payloads retain `snapshot_status` and collection metadata. Report
manifests produced from partial evidence use status `partial` rather than
`success`.

This gives wrappers an explicit process contract without turning a usable
partial refresh into a default failure.

## Implementation Sequence

1. Expand `authored_content.py` with pure normalization, field comparison,
   Canvas-value selection, and datetime validation primitives.
2. Migrate discussions first and prove no report/status behavior changes beyond
   using the shared validator.
3. Migrate announcements and assignments, add timezone-equivalence behavior,
   and add accepted-field coverage tests.
4. Migrate Page metadata matching while retaining the Page report shape and
   date-only `publish_at` contract.
5. Add `sanitize.py`, migrate every existing redaction consumer, and remove the
   duplicate regular expressions.
6. Make invalid-token classification fatal at top-level and nested snapshot
   boundaries.
7. Add `--require-complete`, stderr warnings, exit `3`, and partial report
   manifest status.
8. Reconcile README, backlog, CLI help, Sprint 12 documentation, and the
   external teaching-danvas skill/reference; bump the implementation to 0.12.0.

Each migration step must keep the full suite green so any behavioral change can
be attributed to one boundary.

## Automated Acceptance

### Authored comparison and datetime validation

- timezone-equivalent assignment, announcement, discussion, and Page values
  match;
- offset-free `*_at` values fail during source loading before Canvas
  initialization;
- assignment date-only aliases still expand with the course timezone;
- Page date-only `publish_at` remains supported;
- booleans, numeric strings, whitespace, and order-insensitive extension lists
  retain current intended semantics;
- normalized Page/announcement text and exact general status text do not acquire
  numeric coercion from assignment/discussion scalar policies;
- Page and status booleans use a closed `true`/`false` textual vocabulary;
- every accepted comparable field has an explicit policy;
- announcement verify checks its pre-0.12 fixed field scope plus every declared
  supported field and does not require title front matter, while update still
  requires a title;
- section-specific announcement update requests compare against IDs adapted from
  Canvas `include[]=sections` readback;
- a live-update report and terminal summary are derived from the same readback
  checks.

### Sanitization

- one table-driven matrix covers case variants, URL query values, bare key/value
  forms, bearer headers, signed-cloud parameters, sensitive nested keys, and
  benign near-matches;
- reports, auth doctor, file upload failures, assignment projections, and grade
  recovery use the same vocabulary;
- raw exception URLs, tokens, verifier values, and signed request material never
  appear in terminal output, JSON, Markdown, CSV, or manifests;
- stable canonical Canvas object links remain available where explicitly safe;
- upload-failure projections conservatively drop compound keys containing the
  historical token, URL, and verifier markers;
- benign grading-comment prose containing words such as `policy`, `expires`,
  `token`, `signature`, or `bearer` is retained unless it uses a
  credential-shaped marker;
- explicit equals assignments, unambiguous credential names, and authorization
  headers remain sensitive, while prose-capable colon fields and bare `Bearer`
  markers require a credential-shaped payload for whole-value grade recovery
  hashing;
- colon-form `Policy` and `Expires` values remain the error sanitizer's concern,
  rather than making grade-comment recovery discard prose-capable rows.

### Snapshot behavior

- invalid token failure in a required, optional, or nested collection is fatal,
  calls no later collectors, and preserves an existing snapshot;
- optional forbidden endpoints still produce a usable partial snapshot by
  default with exit zero and stderr warnings;
- strict init/refresh exits `3` without replacing state;
- strict status writes requested evidence and exits `3`;
- complete snapshots exit zero in both default and strict modes;
- partial JSON, diff/status reports, and manifests remain mutually consistent.

The full frozen test suite, Ruff, ty, editable smoke, and built-wheel smoke must
pass. This sprint requires no Canvas mutation. A read-only refresh against one
complete sandbox course and one known partial historical course is useful final
confirmation when explicitly authorized, but synthetic invalid-token tests are
the authoritative credential-failure acceptance because live credentials must
not be deliberately invalidated.

## Non-Goals

- another authored-content command family;
- a base command class or generic mutation engine;
- changing source-map schemas or report evidence payload shapes (the manifest
  status vocabulary gains the explicit `partial` value);
- automatic timezone inference for ambiguous timestamps;
- changing which snapshot collections are required versus optional;
- making partial snapshots fail by default;
- storing raw HTTP response bodies or exception payloads;
- broad status, report-rendering, or CLI-framework refactors;
- Canvas writes or deliberately invalidating the user's token.

## Definition Of Done

- No authored feature module owns a second scalar/datetime comparison engine.
- No redaction consumer owns an independent sensitive-value vocabulary.
- All accepted authored datetime forms are explicit, validated before Canvas,
  and documented.
- Invalid Canvas credentials cannot produce or replace a partial snapshot.
- Automation can require a complete snapshot through a documented exit-`3`
  contract without changing default partial-snapshot usability.
- Repository and teaching-danvas documentation describe the implemented
  behavior, and 0.12.0 release checks pass.

## Implementation Result

The implementation expands `danvas.authored_content` with policy-driven scalar,
sequence, datetime, validation, comparison-row, and Canvas-value primitives.
Assignments, announcements, discussions, Pages, source discovery, source lint,
and status comparison consume those shared policies. Structural tests bind every
supported authored comparison field to an explicit policy.

The new dependency-free `danvas.sanitize` module supplies the shared sensitive
vocabulary and recursive public-evidence behavior. Reports, auth diagnostics,
file uploads, assignment projections, and grade recovery now consume that module
without retaining a second redaction vocabulary.

Snapshot collection now treats `InvalidAccessToken` as fatal at top-level and
nested boundaries. `init`, `refresh`, and `status` expose
`--require-complete`; partial strict runs exit `3` according to the write timing
defined above, warnings use stderr, and partial reports use partial manifests.

The post-review compatibility passes preserve domain-specific behavior around
consolidation: normalized Page/announcement text, exact general status text,
closed boolean coercion, coercive assignment/discussion scalars, fixed-plus-
declared announcement verification with optional title handling, conservative
upload-key suppression, bidirectional grade-comment sensitivity, centralized
structured YAML/date errors, and conservative ordering lint after timezone
findings. Announcement `specific_sections` readback requests Canvas section data
and maps returned section objects to stable IDs.

Local verification on 2026-08-12 passes Ruff, ty, and all 540 tests in a clean
frozen environment. The package and lock metadata are synchronized at 0.12.0;
isolated editable and wheel release smoke also passes for that exact version. A
bounded acceptance in sandbox course 1576638 created announcement 10917561 for
section 1703367, read the same section ID back through `include[]=sections`,
reported a matching comparison, and confirmed the disposable announcement no
longer existed after cleanup.
