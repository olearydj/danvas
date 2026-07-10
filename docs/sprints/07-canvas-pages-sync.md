# Sprint 7: Canvas Pages Source Sync And Conversion

Status: planned; depends on Sprint 6.

## Objective

Create missing local Page sources from current Canvas Pages without overwriting
authored files or weakening the existing Page renderer. Support conservative,
auditable HTML-to-Markdown conversion while retaining native HTML as the fidelity
fallback.

## Command Surface

```bash
danvas pages sync --output-dir content/pages --format markdown --dry-run
danvas pages sync --output-dir content/pages --format html --dry-run
danvas pages sync --output-dir content/pages --page-id 123 --dry-run

danvas pages export --page-id 123 --format markdown --output /tmp/page.md
danvas pages export --url example-page --format html --output /tmp/page.html
```

`pages sync` is report-run-first and reads live Canvas state. Its live mode writes
local source files and source-map provenance but does not mutate Canvas. Markdown
is the default sync format. `--page-id` and `--url` are mutually exclusive
optional filters; without either, plan all Canvas Pages that do not already have
local sources.

Preserve the existing all-Pages JSON export behavior. `pages export --format
html|markdown` requires exactly one Page selected by `--page-id` or `--url` and
remains an explicit-output command.

## Planning And Collision Rules

Use Sprint 6 discovery and identity matching across all configured Page sources,
not only files already inside `--output-dir`. Plan one of these statuses per
Canvas Page:

- `would_create`
- `created`
- `skipped_known_local`
- `skipped_exists`
- `conflict`
- `conversion_blocked`
- `error`

Derive filenames from the stable Canvas Page slug, sanitize path separators and
reserved names, and use `.md` or `.html` according to the selected format. A
matching front-matter/source-map identity anywhere in the project is
`skipped_known_local`. An occupied target without that identity is never
overwritten: report `skipped_exists` when it is unbound and `conflict` when it
belongs to a different Page.

Do not add `--overwrite` or update existing Page sources in this sprint. Recheck
the target immediately before every write so a file created after planning is
still protected.

## Generated Source Contract

Generated Markdown and HTML use the existing Page front matter:

```yaml
---
title: Example Page
page_id: 123
published: false
front_page: false
editing_roles: teachers
publish_at: null
---
```

Include only values Canvas actually supplies. Do not add `canvas_css`; any safe
inline presentation already present in Canvas remains part of the converted body.
Do not emit `notify_of_update`, volatile URLs, module state, or full Canvas API
payloads.

After a source is written successfully, add a `page` source-map entry containing
the stable Page ID, slug, title, sync command, normalized body hash, and safe
metadata. Dry-runs, skipped actions, conflicts, and blocked conversions do not
write provenance.

## HTML And Markdown Conversion

Native HTML output must be an HTML fragment with Page front matter, never a full
document. Remove only documented nonsemantic Canvas/Rich Content Editor metadata,
then validate the result with the existing Canvas Page compatibility profile.
Unsafe or unsupported elements, attributes, styles, or URLs block conversion
rather than being silently dropped.

The Markdown converter must be deterministic and cover the conservative Page
baseline:

- paragraphs and line breaks
- headings with stable IDs
- emphasis and strong text
- ordered and unordered lists
- links, including same-page anchors
- blockquotes and horizontal rules
- inline and fenced code
- tables supported by the existing Markdown renderer
- safe raw-HTML islands only when required to preserve profile-V1 structure or
  inline presentation

Do not claim Markdown conversion is lossless. Record warnings for normalized
nonsemantic markup. If meaningful structure cannot be represented within the
existing source/compatibility contract, report `conversion_blocked` and recommend
`--format html`.

Before writing either format, load the proposed source through the existing Page
loader and compare its rendered normalized body with the normalized Canvas body.
Write the file only when hashes and same-page anchor targets match. A failed
round trip is `conversion_blocked`; never leave a partial source behind.

## Reports And Safety

Dry-run and live sync reports write `pages-sync.json`, `pages-sync.md`, and
`manifest.json`. Reports include Page identity, title, target path, format,
status, hashes, warnings, and reasons, but exclude full Page bodies and unsafe or
volatile URLs.

Sync does not print a Canvas mutation banner because it performs no Canvas write.
It must clearly say that local files will be created in live mode. A failed
action must not prevent independent safe actions from being reported, while the
command exits nonzero when any conflict, conversion block, or error remains.

Single-Page HTML/Markdown export follows the same converter and round-trip checks,
requires an explicit output path, and refuses replacement unless `--overwrite`
is supplied. Export does not update source-map provenance.

## Acceptance Criteria

- Broad and targeted dry-runs are deterministic and make no local source or
  source-map changes.
- Live sync creates only planned missing sources and never overwrites an existing
  path or known source.
- Repeating sync after success reports `skipped_known_local` and creates no
  duplicate Page source.
- Markdown fixtures round-trip ordinary prose, lists, links, anchors, code, and
  tables through the existing renderer.
- Safe inline styles and structures either survive through Markdown/raw-HTML
  islands or produce a clear HTML-fallback recommendation.
- Unsupported or lossy conversions are blocked before a file is written.
- Generated HTML is a validated fragment source, not a preview or standalone
  document.
- Live source creation writes stable provenance only after successful local
  readback and hash comparison.
- Reports contain no full bodies, signed URLs, tokens, or student data.
- Existing JSON export behavior remains compatible; targeted HTML/Markdown
  exports are covered separately.
- Generic fixtures plus one non-normative real-course field case establish
  reusable behavior without course-specific branches.
- README, backlog, and external teaching-danvas docs describe sync, conversion
  limitations, and overwrite guarantees.

## Deferred

- Updating or overwriting an existing local Page source from Canvas.
- Two-way or automatic synchronization.
- Asset download/upload and relative-link rewriting.
- Page upsert, rename, scheduling/front-page mutation, deletion, and module-link
  maintenance.
- Broader HTML/CSS compatibility and Pandoc-flavored Markdown.
