# Sprint 16: Verified Markdown Asset Deployment

Status: released in 0.13.0 after local, isolated, and bounded live verification.

## Outcome

Let an instructor keep an assignment and its supporting files together in a
local course project, then publish the assignment without manually uploading
every file or replacing every relative link.

For example, this source remains ordinary, portable Markdown:

```markdown
Read the [case packet](../assets/case-packet.pdf).

![Decision tree](../assets/decision-tree.png)
```

On a guarded live create or update, danvas uploads or safely reuses both files,
rewrites only the in-memory HTML sent to Canvas, and verifies that Canvas saved
references to the expected course-file IDs. The Markdown file is never edited.

This is not a whole-tree file synchronizer. It is a bounded deployment stage
inside existing authored-content writes.

## User Story

As an instructor maintaining course content in Git, I want local document and
image links to work after I publish the Markdown to Canvas, without copying
temporary Canvas URLs by hand, so the repository stays readable and portable
while Canvas receives working, verifiable links.

The operator should be able to:

1. write normal relative links beside the authored source;
2. review exactly which files would be reused, uploaded, renamed, or blocked;
3. run the existing create or update command with an explicit Canvas Files
   destination when an upload is needed;
4. retry safely after a partial failure without creating duplicate files; and
5. verify later that the content still references the intended Canvas file
   identities.

## Scope

Sprint 16 integrates asset planning and deployment with Markdown-backed
assignment create, update, upsert, and verify. The shared boundary is designed
for later adoption by Pages, announcements, and discussion root topics, but
those integrations are not part of 0.13.0.

The first version handles links rendered as:

- `<a href="...">` for downloadable files; and
- `<img src="...">` for images.

Repeated references to the same resolved local file are one asset with multiple
occurrences. Fragments such as `diagram.svg#step-3` are retained after rewrite.
Local query strings are rejected because their meaning cannot be preserved
reliably after a Canvas upload.

The following are deliberately outside this sprint:

- Page, announcement, and discussion integration;
- discussion seed-reply assets;
- native-HTML Page local-asset rewriting;
- CSS `url(...)`, scripts, media elements, `srcset`, iframes, and linked
  stylesheets;
- remote HTTP checking, downloading, mirroring, or rewriting;
- implicit Canvas folder creation;
- upload overwrite, file deletion, rollback deletion, or whole-tree sync;
- automatic publication or any broader authored-content mutation; and
- rewriting the Markdown source or creating a tracked rendered-HTML sibling.

If an otherwise supported write contains a local reference in an unsupported
element or attribute, the command fails before Canvas mutation. It never leaves
the link untouched and reports success.

## Command Contract

Assignment create, update, and upsert gain the same three options:

```text
--asset-folder TEXT
--asset-folder-id INTEGER
--asset-on-duplicate error|rename
```

`--asset-folder` and `--asset-folder-id` are mutually exclusive and use the
existing `files upload` destination resolution and course-ownership checks.
`--asset-on-duplicate` defaults to `error`.

Example:

```bash
danvas assignments update content/assignments/case-resources.md \
  --course-id 1576638 \
  --asset-folder "course files/case-resources" \
  --dry-run

danvas assignments update content/assignments/case-resources.md \
  --course-id 1576638 \
  --asset-folder "course files/case-resources"
```

Asset detection is automatic. The destination is required only when at least
one local asset needs an upload. A later run may omit it when every asset has a
valid reusable source-map identity. Passing asset options when the source has no
local assets is an error, which catches command-line mistakes rather than
pretending the options had an effect.

Integrated asset deployment requires an initialized `.danvas` course project.
That gives path containment, course identity, reports, and interrupted-run
provenance one unambiguous durable root. Existing authored commands remain usable
outside a project when their assignment sources contain no local assets.

The configured project course must equal the command's target course before any
asset lookup or upload. Asset deployment never retargets the top-level
source-map course as a side effect of running against another course.

The first version does not accept `overwrite`. A Canvas file may be referenced
by other course content, so replacing its bytes has a broader mutation boundary
than updating the authored object. An operator who intentionally wants that
behavior can use the standalone `danvas files upload --on-duplicate overwrite`
workflow and then re-plan the authored write.

The internal upload planner gains an `error` duplicate policy so one name match
is classified as `conflict`, not `would_overwrite`. The standalone `files
upload` CLI retains its existing public `overwrite|rename` type and never passes
the new internal policy. This keeps one duplicate classifier without changing
the standalone command contract.

There is no `--allow-unresolved-assets`. Missing, ambiguous, unsafe, or
unsupported references block both dry-run acceptance and live mutation.

Existing assignment sources without local assets retain their current offline
dry-run behavior. A dry-run that needs to resolve an upload destination or
destination-name conflict performs read-only Canvas calls, but never uploads a
file or changes authored content.

`verify` never uploads. It reads the content source, source-map provenance, and
Canvas state and reports a missing or stale asset binding as a mismatch.

## Architecture

### New `authored_assets.py` module

A new `src/danvas/authored_assets.py` module is warranted. It owns the asset
deployment transaction used by assignments in 0.13.0 and exposes a narrow seam
for later authored-content integrations:

- local-reference classification;
- safe path resolution, hashing, and de-duplication;
- source-map file identity lookup;
- upload/reuse planning;
- in-memory HTML rewriting;
- readback file-reference verification; and
- safe report projection.

It does not own command parsing, Markdown rendering, content mutation, or
feature-specific source maps. `assignments.py` remains responsible for those
boundaries and calls the shared asset planner after Markdown rendering and before
mutation payload construction.

`authored_content.py` remains a pure comparison and datetime module. Upload I/O
does not belong there.

The new module reuses `files.py` primitives for file validation, destination
resolution, duplicate planning, result classification, and safe upload errors.
It must not copy those implementations. Dependency direction is one-way:
`authored_assets` may call the file pipeline, while `files` does not import an
authored command.

`canvas_links.py` remains the owner of stable Canvas URL construction, sensitive
query names, structural local-reference detection, and file identity extraction.
It gains link-profile helpers needed to render and recognize the two supported
assignment forms. The suffix-gated `relative_asset_url` contract is replaced for
assignment extraction. The independent Page suffix vocabulary and
`unresolved_local_assets` behavior remain unchanged until the Page adapter is
designed; Sprint 16 does not widen Page write, render, sync, or status gates.

### Integration seam

The assignment command supplies:

- the source path and project root;
- the rendered Canvas-bound HTML;
- the content kind and body field;
- the course ID and validated Canvas origin;
- optional destination options; and
- existing source-map provenance.

The asset layer returns a complete deployment plan and, after live upload, a
rewritten HTML fragment plus asset evidence. `assignments.py` inserts that
fragment into its existing payload and readback-verification flow.

Later Page integration must preserve its renderer, CSS inlining, compatibility
validation, and canonical body comparison. Later discussion integration is
limited to the root topic until seed bodies have an equally truthful readback
contract. Native-HTML Page rewriting remains a separate design problem. None of
those future adapters may silently inherit assignment behavior merely because
the shared planner exists.

## Local Reference Contract

### Classification

The scanner parses rendered HTML and structurally classifies every URL-bearing
attribute before consulting a filename suffix or MIME type. A relative path such
as `notes.txt` must be visible to the planner even when no legacy suffix allowlist
contains it. Classifications are:

- `local_asset`: a supported relative file reference;
- `canvas_file`: an existing same-course Canvas file reference;
- `external`: an absolute HTTP or HTTPS link;
- `non_file`: a same-page fragment, `mailto`, or `tel` link;
- `blocked_root_relative`: an unknown root-relative path such as
  `/assets/case.pdf` that is neither a recognized Canvas object path nor a local
  project-relative reference;
- `unsafe`: credentials, volatile signed parameters, an unsafe scheme, or a
  path outside the allowed root;
- `missing`: a local path that does not resolve to a readable regular file; or
- `unsupported`: a local reference in an element or attribute outside the first
  version's allowlist.

External, same-page, mail, telephone, and already-stable same-course references
remain unchanged. Cross-course Canvas file identities, signed/verifier URLs,
Canvas-looking file paths on another origin, and unknown root-relative paths
fail closed. Classification checks recognized Canvas paths before applying the
root-relative block.

### Filesystem boundary

The allowed local root is the configured course project root. Relative paths may
use `..` only when the resolved target remains inside that root.

Resolution is performed on the real path. A symlink that escapes the root is
rejected. Targets must exist, be readable regular files, and not live under
`.git`, `.danvas`, generated report directories, grading/recovery directories,
or another existing danvas inventory-ignore boundary. Directories and device
files are rejected.

Markdown, HTML, CSS, and JavaScript targets are rejected as assets. They are
authored content or executable presentation resources, not opaque Canvas Files.
All other readable file types are accepted through the current upload content-
type resolver; image elements additionally require an image MIME type from a
small documented raster/SVG allowlist. Type policy is applied after structural
detection and never determines whether a relative URL is noticed.

Durable reports use project-relative paths. Absolute paths exist only in memory
for local I/O and are never written into public report evidence.

### Identity and de-duplication

An asset is identified locally by:

- project-relative resolved path;
- SHA-256 of its current bytes;
- byte size; and
- detected content type.

The same resolved path referenced multiple times is uploaded once. Two different
paths with equal bytes remain distinct assets because their authored identity
and destination names may differ.

## Planning Contract

Planning occurs before any upload or authored-content mutation:

1. parse and render the source with the existing feature rules;
2. classify every URL-bearing reference;
3. resolve, validate, hash, and de-duplicate local assets;
4. load file and authored-object source-map provenance;
5. validate any required destination and list it once;
6. produce a complete asset plan;
7. block on any unsafe, missing, unsupported, ambiguous, or conflicting row;
8. compute the planned deployed HTML using stable planned identities where
   available; and
9. present the authored-object diff and asset plan together.

Dry-run statuses are:

- `would_reuse`: the mapped Canvas file identity is valid and the local hash is
  unchanged;
- `would_upload`: no current binding exists and the destination name is free;
- `would_rename`: an upload is required, the destination name exists, and the
  operator explicitly selected `rename`;
- `conflict`: identity, hash, folder, or destination-name evidence disagrees;
- `blocked`: the local reference is unsafe, missing, or unsupported.

A mapped file is reusable only when:

- the initialized project course, file entry's `canvas.course_id`, and target
  course all match;
- its local path and SHA-256 match the current asset;
- the Canvas file still exists;
- Canvas reports it in the current course; and
- its recorded folder remains compatible with an explicitly supplied
destination.

The top-level source-map course is project metadata, not sufficient per-file
evidence. A hand-edited or malformed file entry without `canvas.course_id` is
not reused automatically.

A changed local hash never silently reuses or overwrites the old Canvas file.
The default is `conflict`. With `--asset-on-duplicate rename`, it becomes a new
upload and a new stable file identity. This leaves the old file untouched for
other course content.

If a mapped Canvas file was deleted, the plan may return `would_upload` only
when the destination can be resolved and its name is unambiguous. Otherwise it
returns `conflict`.

## Live Transaction And Retry Safety

The live pipeline is ordered to keep every mutation attributable:

1. repeat local validation and Canvas destination planning;
2. print one aggregate Canvas mutation banner with the authored object, asset
   count, and destination before the first upload;
3. reuse valid mapped files and upload every required file;
4. immediately write one `kind: file` source-map entry after each successful
   upload, before the next upload or content mutation;
5. stop before content mutation if any upload or provenance write is failed or
   indeterminate;
6. rewrite only the in-memory Canvas-bound HTML;
7. call the existing authored-object create or update path;
8. read back the saved object and verify metadata, deployed body, and file IDs;
9. finalize the authored-object source-map entry with its asset associations;
   and
10. finalize the report run.

Immediate file provenance is essential. If the object write or readback fails,
a retry can reuse the already-uploaded file instead of creating a duplicate.

The existing assignment helpers currently print their banner immediately before
the assignment create or edit call. Asset-enabled paths must hoist or
parameterize that call so the aggregate banner appears exactly once before the
first file mutation, not only after uploads have already occurred.

The asset layer never deletes an uploaded file as rollback. A file may already
be referenced elsewhere by the time a recovery attempt runs, and deletion would
be a broader destructive action than the requested authored-content write.

Live asset statuses are:

- `reused`;
- `uploaded`;
- `renamed`;
- `failed`; and
- `indeterminate`.

Mutation and evidence status are separate. If Canvas reports a successful
upload but no trustworthy file ID can be recovered, mutation is `indeterminate`
and the command stops with explicit "verify before retrying" instructions. If a
file ID is known but durable source-map evidence cannot be written, the command
also stops before the content write and prints the safe file identity.

An upload failure after earlier successes leaves those successful identities in
the source map. A content-write failure leaves all uploaded identities recorded
and the authored-object entry unchanged or pending according to its existing
feature contract. The report states exactly which stage changed Canvas.

## Canvas-Bound Link Profiles

Download links and embedded images do not use the same URL shape.

For `<a href>`, danvas emits the existing stable course-file view URL:

```text
https://CANVAS_ORIGIN/courses/COURSE_ID/files/FILE_ID?wrap=1
```

The `href` is sufficient for navigation and identity extraction. Sprint 16 does
not require Rich Content Editor metadata attributes.

For `<img src>`, danvas initially emits a same-course Canvas preview path only:

```html
<img src="/courses/COURSE_ID/files/FILE_ID/preview" ...>
```

`data-api-endpoint`, `data-api-returntype`, `data-canvas-previewable`, and other
Canvas RCE attributes are optional readback metadata, not authored payload or
verification requirements. Existing Page canonicalization already strips them
before hashing, so Canvas adding them does not create Page body drift.

The pre-implementation Canvas profile probe must show that the `src`-only shape
renders and reads back with the same file identity for an assignment. It also
records Page behavior before a later Page adapter is designed. If `src` alone is
insufficient, implementation pauses and this contract is revised; Sprint 16 does
not speculate by injecting attributes after Page canonicalization or widening
the Page allowlist.

The Files API's ordinary `url` and public inline-preview response may contain
user-specific, expiring signed URLs. They are never used as durable links,
written to source maps, or retained in reports. The design follows Canvas's
[Files API](https://developerdocs.instructure.com/services/canvas/file.all_resources/files)
and [API endpoint attribute](https://developerdocs.instructure.com/services/canvas/basics/file.endpoint_attributes)
contracts, with live readback as the final compatibility check.

### Deferred Page canonicalization

`pages.canonicalize_page_url` already normalizes more than file links, so it is
not removed wholesale. Sprint 16 leaves it and Page
`unresolved_local_assets` unchanged. The later Page adapter must delegate
recognized Canvas file paths and sensitive-query classification to
`canvas_links`, remove the Page-specific suffix gate under an explicit Page
migration contract, and retain Page-specific normalization for other course
URLs.

An absolute stable anchor URL from file provenance is intentionally serialized
as a course-relative URL in a future Page payload and Page body hash. The safe
`wrap=1` query remains. Source-map URL form and Page canonical-body form may
therefore differ while resolving to the same course/file identity.

## Verification Contract

Verification is identity-based rather than string-only. For every local asset it
checks:

- the authored Markdown is byte-for-byte unchanged by the command;
- the current local SHA-256 matches recorded deployment provenance;
- the Canvas file exists in the target course;
- the Canvas file belongs to the recorded folder when folder evidence exists;
- readback HTML contains the expected file ID in the expected element/attribute
  class and occurrence count;
- no expected local reference remains unresolved in Canvas-bound HTML; and
- no signed, verifier, foreign-origin, or cross-course URL was retained.

The shared extractor canonicalizes `href`, `src`, `data-api-endpoint`, and
`data-download-url` to course/file identity before comparison. The assignment
payload requires only `href` or `src`; Canvas may add safe Rich Content Editor
metadata without changing the extracted identity.

The verifier does not claim that Canvas file bytes still equal the local bytes
when the file was replaced out of band. Canvas exposes stable identity and
metadata, but this workflow does not download every file during verify. Reports
say `identity_verified` and `local_provenance_match`, not `remote_bytes_match`.

For assignment bodies whose local rendering necessarily differs from deployed
HTML, provenance records two hashes:

- `source_body_sha256`: rendered body before asset URL substitution; and
- `deployed_body_sha256`: canonical body after stable Canvas substitution.

For 0.13 asset deployments, `last_posted.body_sha256` is the deployed
comparable-body hash. `source_body_sha256` records the rendering before asset URL
substitution, and an explicit `deployed_body_sha256` may be repeated in bounded
asset evidence for clarity. A pre-0.13.0 entry lacking `source_body_sha256` does
not constitute drift by itself. Current source-map readers do not consume
`last_posted.body_sha256`; this contract makes its future meaning explicit
without requiring a schema migration or rewriting legacy entries.

## Source Map

The existing schema remains version 1 because entries are extensible and no
reader contract changes. Each successfully uploaded asset receives a normal
entry such as:

```json
{
  "kind": "file",
  "path": "content/assets/case-packet.pdf",
  "canvas": {
    "course_id": 1576638,
    "id": 12345,
    "folder_id": 678,
    "path": "course files/case-resources/case-packet.pdf",
    "url": "https://canvas.example/courses/1576638/files/12345?wrap=1"
  },
  "last_posted": {
    "command": "assignments update",
    "fields": {
      "sha256": "...",
      "size": 42138,
      "content_type": "application/pdf",
      "upload_name": "case-packet.pdf"
    }
  }
}
```

The authored-object entry adds a bounded `assets` list containing project-
relative path, local SHA-256, Canvas file ID, link profile, and occurrence count.
It does not contain full HTML, raw upload responses, signed URLs, authorization
parameters, or absolute filesystem paths.

Conflicting file entries for the same path and course are fatal. An authored
object cannot claim an asset identity that disagrees with the file entry.

## Reports And Exit Semantics

Integrated reports add an `assets` object with evidence schema
`authored-assets-v1` and include:

- source and target course identity;
- destination folder ID and safe full name when used;
- local project-relative path, SHA-256, size, and content type;
- occurrence tags/attributes without surrounding authored prose;
- planned and live status;
- Canvas file ID, folder ID, path, and stable URL;
- mutation, evidence, and verification status; and
- bounded recovery guidance after a partial transaction.

Live asset deployment requires a durable report run. `--no-report` is rejected
when an upload is planned because a multi-step Canvas mutation needs durable
evidence. It remains valid for ordinary writes and for verification-only runs
that do not upload.

Exit behavior is conservative:

- `0`: all planned mutations and evidence completed, or read-only verification
  matched;
- `1`: blocked plan, upload failure, content failure, readback mismatch,
  provenance failure, or verification mismatch;
- `2`: existing command-line usage failure.

An indeterminate upload exits `1` but is not labeled failed. The report and
terminal output explicitly warn against blind retry.

## Compatibility And Migration

Assignment file verification currently treats a relative asset reference as
`partial`. Sprint 16 deliberately strengthens that behavior:

- assignment create, update, and upsert block when a local asset has neither a
  reusable mapping nor an explicit upload destination;
- assignment verify reports an unresolved, stale, or mismatched local asset as
  a mismatch rather than a partial success;
- an unchanged mapped asset is reusable without repeating the destination
  option; and
- assignments with no local references retain their existing payload, report,
  hash, offline dry-run, and verification behavior.

The shared assignment extractor also feeds read-only assignment list and export
projections. Structural detection means those outputs may gain explicit rows for
relative or unknown root-relative URLs that were previously invisible because
their suffix was not allowlisted. This is evidence enrichment only: list/export
does not mutate Canvas, and the new rows must not turn a successful read-only
projection into a command failure.

The error explains how to pass `--asset-folder` or `--asset-folder-id`, or how to
replace the relative reference with an intentional stable Canvas or external
URL. There is no compatibility switch that republishes a known broken relative
link.

## Pre-Implementation Canvas Profile Probe

Before production code is written, run one bounded, explicitly approved sandbox
probe. This is a mutating probe, not a read-only check: it creates disposable
objects and files, reads them back, inspects rendering, and removes them through
separately guarded cleanup.

Using one small image and one stable download link, create an unpublished
assignment and an unpublished Page with hand-built variants:

- `src="/courses/N/files/M/preview"` only;
- the same `src` plus Canvas RCE endpoint/return-type attributes; and
- an anchor using the absolute stable `?wrap=1` course-file URL.

The Page variant cannot use the existing `pages create` source path because its
validator and canonicalizer intentionally remove those RCE attributes. The probe
uses the project's authenticated Canvas client or a disposable test harness to
send the controlled HTML directly; it does not change production code merely to
make the experiment possible.

The harness lives only in scratch space and is never added to `scripts/` or the
package. Before its first write it prints the target course, disposable object
names, file IDs, and cleanup scope explicitly. Its retained field note is
sanitized and contains stable identities only; no token, raw response, signed
URL, or reusable uncontrolled mutation path is committed.

Record exactly which `src`, `href`, and data attributes Canvas preserves for
each family and confirm the image renders in the browser. Independently verify
that both disposable objects and files are absent after cleanup.

The probe determines the shared image profile before implementation. Sprint 16
proceeds with `src`-only assignment payloads only if that form renders and
round-trips to the same file ID. Page results are design evidence for a later
adapter, not Page implementation acceptance for 0.13.0. Signed preview URLs are
never an acceptable fallback.

## Implementation Sequence

0. Complete the approved Canvas profile probe and update the stable link-profile
   contract if observed behavior differs. Completed: Canvas normalized the
   `src`-only assignment and Page variants to the same stable file identity and
   added its own RCE metadata; all preview fetches returned the expected SVG.
1. Add characterization tests for assignment writes and verification with no
   local assets; their payloads, reports, hashes, and offline dry-runs must not
   change.
2. Replace suffix-gated assignment extraction with pure structural URL
   classification, path containment, hashing, de-duplication, and plan models in
   `authored_assets.py`. Unknown root-relative paths are explicitly blocked;
   Page detection remains unchanged.
3. Consolidate assignment-side Canvas file parsing and sensitive-query
   vocabulary in `canvas_links.py`. Record the existing Page canonicalizer and
   suffix detector as explicit Page-adapter work rather than changing them in
   this release.
4. Extend the internal `files.py` duplicate planner with `error`, reuse its
   validation/folder/result/error primitives, and leave the standalone CLI type
   and behavior unchanged.
5. Add immediate `kind: file` provenance and asset association helpers to the
   source-map layer. File entries require `canvas.course_id`; asset deployment
   rejects project/target course mismatch and interrupted-run tests prove safe
   reuse.
6. Integrate assignment create, update, upsert, and verify because their current
   verifier already extracts exact linked file IDs. Hoist or parameterize the
   current create/update banners so one aggregate banner precedes the first
   upload.
7. Add report rendering, failure-stage summaries, CLI options, migration notes,
   README examples, backlog close-out, and external teaching-danvas
   skill/reference updates.
8. Bump to 0.13.0 only after automated and bounded live assignment acceptance
   pass.

No announcement, discussion, or Page mutation adapter is added in this release.
Those future adapters must use the shared plan and verification rows rather than
introducing independent URL rewriting or upload classifiers.

## Automated Acceptance

### Source and path safety

- relative links resolve from the source file and may traverse only within the
  allowed project root;
- missing files, directories, unreadable files, symlink escapes, ignored private
  paths, authored source types, unsafe schemes, and local query strings fail
  before Canvas initialization;
- every assignment URL is detected structurally regardless of suffix, while an
  unknown root-relative URL is explicitly blocked;
- external links, fragments, mail, telephone, and existing stable same-course
  file links remain unchanged;
- foreign-origin, cross-course, signed, and verifier-bearing file links fail;
- source Markdown bytes and mtime remain unchanged after dry-run, success, and
  every injected failure.

### Planning and upload

- repeated references upload once and preserve occurrence counts;
- mapped unchanged assets plan `would_reuse` without requiring a destination;
- reuse requires matching project, target, and per-entry Canvas course IDs;
- new assets require an existing, course-owned destination;
- duplicate destination names, including same-basename files from different
  local directories, default to `conflict`; explicit `rename` plans and records
  each returned name and identity;
- changed local bytes never reuse or overwrite the old file;
- no folder is created implicitly;
- ordinary assignment writes without local assets retain their existing offline
  plan and payload behavior;
- the internal duplicate `error` policy returns conflict for every existing
  destination-name match, while standalone `files upload` retains its current
  overwrite/rename behavior.

### Rewrite and verification

- PDF/download links use stable course file IDs without signed parameters;
- image links use the accepted `src`-only Canvas preview profile and preserve
  alt text, title, and classes;
- fragments survive link rewriting;
- source and deployed assignment hashes are distinct and deterministic;
- dry-run evidence labels a not-yet-rewritable body as
  `pending_canvas_file_ids` rather than presenting local URLs as the deployed
  form;
- safe Canvas Rich Content Editor additions do not change extracted file
  identity;
- retained volatile or verifier query parameters fail readback even when the
  underlying file ID is otherwise valid;
- wrong, missing, cross-course, or duplicate unexpected file IDs fail readback;
- verification reports identity/local-provenance limits without claiming remote
  byte equality.

### Partial failures and evidence

- each successful upload writes file provenance before the next mutation;
- a later upload failure leaves earlier file identities reusable;
- a content-write or readback failure leaves file identities reusable and does
  not delete uploaded files;
- a successful upload without a trustworthy ID is `indeterminate` and warns
  against retry;
- a source-map write failure stops before content mutation and reports the known
  safe file identity;
- public evidence contains no signed URLs, credential parameters, upload
  responses, authored bodies, student data, or unsafe absolute paths;
- every asset mutation attempt appears exactly once with the intent that drove
  it.

### Assignment and shared-boundary coverage

- assignment create, update, upsert, and verify integrations pass;
- assignment upsert preserves its explicit create/update confirmation boundary;
- assignment sources without local assets retain existing create/update/verify
  behavior;
- current-course root-relative content links remain outside asset extraction,
  while unknown and cross-course root-relative links remain visible;
- existing relative-asset verification changes from `partial` to the documented
  blocked/mismatch migration contract;
- Page render, sync, create, update, status, and unresolved-asset behavior remain
  unchanged in 0.13.0;
- assignment list/export projections surface newly detected local and
  root-relative references without becoming mutating or failing read-only
  commands;
- the aggregate mutation banner is emitted exactly once before the first asset
  upload on both create and update paths;
- structural tests prove every supported assignment write uses the shared asset
  planner and no additional local-link classifier is introduced.

The standard frozen pytest suite, Ruff, ty, lock check, Markdown lint, and
editable/wheel release smoke must pass for 0.13.0.

Implementation coverage includes structural detection regardless of suffix,
root/project containment, ignored/private paths, duplicate planning, mapped
reuse, source and asset revalidation immediately before mutation, stable link
profiles, folder-aware readback, source-map interruption, content failure, and
all four assignment command integrations. The clean isolated frozen suite passes
all 565 tests. Ruff, ty, lock validation, sprint-document Markdown lint, and
isolated editable/wheel smoke also pass for 0.13.0.

## Bounded Canvas Acceptance

Use the configured disposable sandbox course only after explicit approval. The
test uses one temporary, already-existing Canvas Files folder, one small PDF,
one small image, and one unpublished assignment. It contains no student data and
sends no notifications. This is the final implementation acceptance, separate
from the earlier link-profile probe.

The live sequence is:

1. prove the source and asset fixtures are disposable and record their local
   hashes;
2. dry-run a new download link and image, confirming the exact folder and
   upload plan;
3. create or update the unpublished assignment and read it back;
4. inspect the assignment in Canvas to confirm the download works and the image
   renders;
5. verify exact file IDs, link profiles, occurrence counts, source immutability,
   and absence of volatile URLs;
6. rerun to prove both assets are reused and the authored object is no-change;
7. change one disposable local asset, prove default conflict, then explicitly
   rename and verify the new identity without replacing the old file;
8. inject or exercise a post-upload/pre-content failure and prove retry reuses
   the recorded file rather than uploading a duplicate; and
9. remove the disposable assignment and all test files through separately
   guarded cleanup, then independently verify they are absent.

If the accepted `src`-only image shape does not survive assignment readback or
render in the browser, 0.13.0 is blocked. The implementation must revisit the
profile and repeat acceptance; it must not fall back to a signed preview URL.

## Definition Of Done

- An instructor can publish Markdown with one local document and one local image
  through assignment create, update, or upsert without manually constructing a
  Canvas URL.
- Dry-run fully describes upload/reuse/conflict behavior before mutation.
- The local Markdown remains unchanged.
- Every upload has immediate durable identity and safe retry behavior.
- Readback proves the expected Canvas file IDs in the final content.
- Reports distinguish file mutation, content mutation, evidence completeness,
  and verification truthfully.
- Unsupported or unresolved assets fail closed.
- No implicit folder creation, overwrite, publication, deletion, remote fetch,
  or whole-tree synchronization is introduced.
- README, backlog, sprint index, and the external teaching-danvas skill and
  command reference describe the shipped command contract.
- The pre-implementation assignment/Page link-profile probe, automated
  acceptance, and disposable assignment field case pass before the 0.13.0
  version bump and tag.

## Implementation And Live Acceptance Result

Implementation completed on 2026-08-12. The bounded sandbox run used course
1576638, existing folder `course files`, one unpublished assignment, one small
document, and one SVG image. Dry-run planned both uploads; live create recorded
each file before the assignment write; readback matched both file IDs, element
classes, occurrence counts, and folder IDs; and verify returned `matches`.

A destination-free rerun reused both identities and planned `no_change`.
Changing one local file failed closed by default; explicit `rename` created a
new file identity without replacing the old file and readback matched. A second
disposable case deliberately caused Canvas to reject the assignment after its
file upload. The retained `kind: file` entry let the corrected retry reuse the
same file without another upload. Source bytes remained unchanged throughout.

Canvas added verifier-bearing preview metadata on readback, as observed in the
step-0 probe, but identity extraction retained only stable course/file IDs and
safe query-name evidence. Browser automation was unavailable in this session;
the approved probe independently fetched every returned preview URL with HTTP
200 and the expected SVG media type. Both disposable assignments and all four
implementation-acceptance files were deleted and independently confirmed
absent.
