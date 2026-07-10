# Sprint 6: Canvas Pages Discovery, Snapshot, And Status

Status: planned.

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
- `body_sha256`, calculated from the normalized Canvas HTML fragment
- `body_normalizer`, identifying the comparison profile used for the hash

Fetch Page detail when list results do not contain a body. Store the normalized
hash, never the body itself. Sort rows deterministically by normalized title and
stable identity. Snapshot and diff output must not contain signed URLs, access
tokens, module data, or student information.

Schema-3 snapshots remain readable by generic tooling, but `danvas status` must
request a refresh before attempting Page comparison against a pre-v4 snapshot.
`refresh --diff` reports the schema transition through its existing
schema-changed behavior.

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
3. A unique normalized title match for an otherwise unbound source.

Conflicting front-matter and source-map identities are an unsupported comparison,
not a title fallback. Duplicate Canvas titles are also unsupported unless a
stable identity resolves the source.

Report these classifications:

- `exact`
- `metadata mismatch`
- `body mismatch`
- `metadata and body mismatch`
- `local-only`
- `Canvas-only`
- `unsupported comparison`

Compare rendered body hashes, title, `published`, and `front_page`. Compare
`publish_at` and `editing_roles` only when the local source declares them.
Treat `updated_at`, editor type, and stable URLs as diagnostics rather than
authoritative authored fields.

Useful next actions should point to:

- `pages create SOURCE --dry-run` for local-only sources
- `pages verify SOURCE` or `pages update SOURCE --dry-run` for drift
- `pages sync --output-dir content/pages --dry-run` for Canvas-only Pages after
  Sprint 7 is available

`danvas status` remains read-only and snapshot-backed. It must not fetch Page
bodies, write source-map entries, or modify local sources.

## Acceptance Criteria

- Refresh produces a deterministic schema-v4 `pages` array with no full bodies.
- Snapshot hashes use the same normalized-fragment comparison semantics as Page
  verification.
- Default and configured Page source discovery handle Markdown and HTML while
  excluding CSS and preview artifacts.
- Stable ID/source-map matching survives title changes and duplicate titles.
- Status distinguishes exact, metadata drift, body drift, local-only,
  Canvas-only, and unsupported comparisons with actionable details.
- Page errors affect that Page's classification without hiding unrelated status
  sections.
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
