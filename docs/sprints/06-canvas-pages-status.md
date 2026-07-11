# Sprint 6: Canvas Pages Discovery, Snapshot, And Status

Status: implemented and verified.

## Objective

Make authored and Canvas-only Pages visible in the normal `refresh` and `status`
workflow without storing full Page bodies in `.danvas/course.json`. Establish the
identity and comparison foundation required by Page sync in Sprint 7.

## Command And Configuration Surface

No new top-level command is required:

```bash
danvas refresh --diff
danvas status
```

Add Page source discovery with conservative defaults and normal overrides:

```toml
[sources.pages]
include = ["content/pages/*.md", "content/pages/*.html"]
exclude = ["content/pages/*-preview.html"]
```

The default includes are the two `content/pages` patterns above, with a default
exclude for `content/pages/*-preview.html`. Existing `[sources]` validation rules
continue to reject absolute paths and `..` escapes. CSS sidecars and generated
preview documents are not Page sources.

## Snapshot Contract

Bump `.danvas/course.json` from schema version 3 to version 4 and add a `pages`
array. Each row contains only stable, non-student Page state:

- `page_id`
- `url` (the Canvas Page slug)
- `html_url`, when Canvas supplies a stable course URL
- `title`
- `published` and `front_page`
- `publish_at`, `editing_roles`, and editor type when available
- `updated_at`
- `body_sha256`, calculated from the canonical normalized Canvas HTML fragment,
  or `null` when volatile URLs cannot be resolved safely
- `body_hash_status`: `available` or `blocked_volatile_url`
- `volatile_url_count`, with no URL values
- `body_normalizer`, identifying the comparison profile used for the hash

Fetch Page detail when list results do not contain a body. Store the normalized
hash, never the body itself. Sort rows deterministically by normalized title and
stable identity. Snapshot and diff output must not contain signed URLs, access
tokens, module data, or student information.

For a schema-3 snapshot, `danvas status` renders all existing non-Page sections,
prints a prominent warning and refresh next action, and reports the Pages section
as unavailable. This compatibility path exits normally and records
`pages_available: false` in saved status output; it must not silently claim that
there are no Pages. Snapshots older than schema 3 retain the existing hard
nonzero failure. `refresh --diff` reports the schema transition through its
existing schema-changed behavior.

## Shared Page URL Canonicalization

Sprint 6 introduces one inbound Page-URL canonicalizer used by snapshot hashing,
status, Sprint 7 conversion, and future Page readback. URL handling occurs before
body hashing or serialization into authored sources.

- Preserve same-page fragments such as `#installation`.
- Convert absolute links on the configured Canvas origin to stable root-relative
  Canvas paths when their course/object identity is known.
- Never infer trust from a Canvas-shaped path alone. An absolute URL is eligible
  for Canvas-relative rewriting only when its normalized scheme, host, and port
  match the configured Canvas origin. Preserve foreign origins, and block body
  hashing when such a URL contains volatile credentials or expiry parameters.
- Canonicalize Canvas file links to stable course/file-ID paths while preserving
  only documented non-secret behavior such as preview versus download.
- Sort ordinary, non-secret query parameters deterministically.
- Treat user-info credentials and secret/expiry parameters as volatile. At
  minimum this includes `verifier`, `access_token`, credential-like `token`
  fields, `signature`, `expires`, `X-Amz-*`, `X-Goog-*`, `Policy`, and
  `Key-Pair-Id`, matched case-insensitively.
- Never include a volatile value in a hash input, snapshot, report, diagnostic,
  generated source, or source-map entry.
- Remove only non-authorable account decorators that Canvas injects as direct
  outer-edge children of Page readback: leading/trailing stylesheet `link`
  elements and empty external `script` elements. Apply this before hashing so
  account theme injection cannot create false drift. Authored sources continue
  to reject both elements, and unsupported elements inside Page content are not
  silently removed.

If a volatile Canvas or external URL can be reduced to a stable Canvas-relative
identity, hash the rewritten form. Otherwise do not hash the body: set
`body_sha256: null`, `body_hash_status: blocked_volatile_url`, and retain only a
count plus a sanitized reason. Status may still compare safe metadata, but body
comparison is `unsupported comparison` until the URL is resolved. Do not strip
unknown external query parameters merely to force a match; they may be
semantically meaningful.

## Local Source Discovery

Add `page` to the supported source kinds and `pages` to the source configuration
keys. A discovered Page source must:

- be Markdown or native HTML with valid Page front matter
- be loaded through the existing Page source loader and compatibility profile
- expose its rendered `body_sha256`, title, publication/front-page state, and
  explicitly declared optional metadata
- retain parse, CSS, anchor, unsafe-markup, and unresolved-asset diagnostics for
  status output rather than crashing the whole course report

Use the current renderer and restricted `canvas_css` behavior; do not introduce a
second status-only renderer.

## Identity And Comparison

Resolve a local Page to a snapshot row in this order:

1. `page_id` or `canvas_id` in front matter.
2. Stable Page ID or slug from `.danvas/source-map.json` for that source path.
3. A unique normalized title candidate for reporting only.

Conflicting front-matter and source-map identities are an unsupported comparison,
not a title fallback. A title-only candidate is `probable match, unbound`, never
`exact`, and never becomes provenance implicitly. Duplicate Canvas titles are
unsupported unless a stable identity resolves the source. Status displays the
candidate Page ID and slug so the user can bind it deliberately.

Report these classifications:

- `exact`
- `metadata mismatch`
- `body mismatch`
- `metadata and body mismatch`
- `local-only`
- `Canvas-only`
- `probable match, unbound`
- `unsupported comparison`

Compare rendered body hashes, title, `published`, and `front_page`. Compare
`publish_at` and `editing_roles` only when the local source declares them.
Treat `updated_at`, editor type, and stable URLs as diagnostics rather than
authoritative authored fields.

Compare a local body hash only when the snapshot row's `body_normalizer` equals
the running `BODY_NORMALIZER_VERSION`. A missing or older normalizer makes body
comparison unsupported even within schema 4; status recommends `danvas refresh`
instead of reporting exactness or drift across incompatible hash profiles. The
configured-origin safety change advances the profile to `pages-html-v4`.

Useful next actions should point to:

- `pages create SOURCE --dry-run` for local-only sources
- `pages verify SOURCE --page-id CANDIDATE` for an unbound title candidate,
  followed by deliberately adding `page_id` or other stable provenance
- `pages verify SOURCE` or `pages update SOURCE --dry-run` for stably bound drift
- `pages sync --output-dir content/pages --dry-run` for Canvas-only Pages after
  Sprint 7 is available

`danvas status` remains read-only and snapshot-backed. It must not fetch Page
bodies, write source-map entries, or modify local sources.

## Acceptance Criteria

- Refresh produces a deterministic schema-v4 `pages` array with no full bodies.
- Snapshot hashes use the same normalized-fragment and URL-canonicalization
  semantics as Page verification and Sprint 7 conversion.
- Signed/verifier URLs either become stable Canvas-relative links or block body
  hashing without leaking their values.
- Default and configured Page source discovery handle Markdown and HTML while
  excluding CSS and preview artifacts.
- Stable ID/source-map matching survives title changes and duplicate titles;
  unique title candidates remain visibly unbound.
- Status distinguishes exact, metadata drift, body drift, local-only,
  Canvas-only, probable-unbound, and unsupported comparisons with actionable
  details.
- Page errors affect that Page's classification without hiding unrelated status
  sections.
- Schema-3 status renders non-Page sections, marks Pages unavailable, recommends
  refresh, and does not fail the whole report.
- Status and report-run outputs contain hashes and concise differences, not full
  Page bodies.
- Generic fixtures cover every classification and schema migration; no behavior
  depends on a course ID, title, path, or CSS class.
- README, backlog, and external teaching-danvas docs describe the new snapshot
  schema and status behavior.

## Deferred

- Canvas-to-local file creation, specified in Sprint 7.
- Asset upload or relative-link rewriting.
- Title/slug rename, scheduling/front-page mutation, general upsert, or deletion.
- Module membership and link maintenance.
- Broader HTML/CSS profiles and Pandoc-flavored Markdown.
