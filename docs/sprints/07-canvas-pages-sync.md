# Sprint 7: Canvas Pages Source Sync And Conversion

Status: implemented and verified; built on Sprint 6. The non-normative field
case passed in Auburn sandbox course 1576638 on 2026-07-10, including API
readback, browser inspection, snapshot/status, targeted export, targeted and
broad sync planning, idempotent live local sync, and provenance recovery.

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
not only files already inside `--output-dir`. After inventory-wide target
planning, assign one of these statuses to each Page selected for action:

- `would_create`
- `created`
- `skipped_known_local`
- `skipped_exists`
- `conflict`
- `conversion_blocked`
- `recovered_provenance`
- `would_recover_provenance`
- `source_created_provenance_failed`
- `error`

Always load the complete current course Page inventory and derive canonical
targets for the entire inventory before applying `--page-id` or `--url`. Filters
limit which actions appear and may execute; they must not change filename
normalization, collision sets, Page-ID suffixing, or the chosen target for any
Page. If the complete inventory cannot be obtained, even a targeted sync fails
safely rather than deriving a potentially different path from partial data.

Derive filenames from the stable Canvas Page slug and use `.md` or `.html`
according to the selected format. Apply one strict cross-platform filename
profile on every operating system:

- normalize Unicode to NFC and compare target keys with Unicode case-folding
- replace path separators, NUL/control characters, and filesystem-forbidden
  punctuation
- remove trailing periods and spaces from each filename component
- reject Windows device basenames such as `CON`, `PRN`, `AUX`, `NUL`, `COM1`
  through `COM9`, and `LPT1` through `LPT9`, case-insensitively and even when an
  extension is present
- calculate every proposed target before writing and detect collisions by the
  normalized case-folded key

When a slug is reserved/empty or multiple Page slugs produce the same target
key, use the deterministic form `{sanitized-slug}--page-{page_id}.{ext}` for all
affected Pages, substituting `page` when sanitization leaves an empty basename.
If those fallback keys still collide, report `conflict`; never choose a winner
based on API or filesystem iteration order. Dry-run output shows the original
slug, chosen target, and collision reason.

A matching front-matter/source-map identity anywhere in the project is
`skipped_known_local`. A unique title-only candidate from Sprint 6 also blocks
duplicate creation and is reported as `skipped_known_local` with identity
`title_candidate`, the candidate ID/slug, and an instruction to bind it
deliberately; sync never writes provenance from a title-only match. An occupied
target without either relationship is never overwritten: report
`skipped_exists` when it is unbound and `conflict` when it belongs to a different
Page.

Do not add `--overwrite` or update existing Page sources in this sprint. Recheck
the target immediately before every write, then install with the no-clobber
primitive defined below so a file created after that check is still protected.

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

## Transaction And Recovery Contract

Build and validate the complete source in memory, write it to an exclusive
temporary file in the target directory, and flush it before installation. Install
the completed temporary file with an operating-system no-replace primitive such
as `renameat2(RENAME_NOREPLACE)`, `renamex_np(RENAME_EXCL)`, or an atomic
same-filesystem hard link followed by temporary-file removal. Destination
existence must be tested by the installation primitive itself, not only by an
earlier path check.

If the destination appears before installation, classify the action as
`skipped_exists` or `conflict` after safe identity inspection and remove only the
temporary file. Never replace, truncate, open for ordinary writing, or unlink the
destination. `os.replace()` and any rename API with replace-on-existence
semantics are prohibited. If the platform/filesystem offers no proven
no-clobber primitive, fail the action safely rather than weakening the guarantee.
Source-map updates likewise use temporary-file replacement and must not expose
partially written JSON; replacing the danvas-owned source-map file does not grant
permission to replace authored Page sources.

The generated source's `page_id` and normalized body hash are the recovery
record if interruption occurs between source creation and provenance update. If
the source-map write fails, keep the valid new source, report
`source_created_provenance_failed`, and exit nonzero. On the next sync:

- re-read the Canvas Page and the local source
- require matching `page_id`, title/slug relationship, normalized body hash, and
  anchors
- plan provenance-only repair in dry-run
- write only the missing source-map entry in live mode and report
  `recovered_provenance`

If any recovery check differs, report `conflict` and make no changes. This same
path handles process interruption when no prior failure report exists. Never
delete or overwrite an occupied source merely because provenance is absent.

## HTML And Markdown Conversion

Native HTML output must be an HTML fragment with Page front matter, never a full
document. Remove only documented nonsemantic Canvas/Rich Content Editor metadata,
then validate the result with the existing Canvas Page compatibility profile.
Unsafe or unsupported elements, attributes, styles, or URLs block conversion
rather than being silently dropped.

Canvas account customizations may prepend or append non-authorable stylesheet
`link` and empty external `script` elements to API readback. The shared Page
normalizer removes those elements only when they are direct outer-edge children
of the returned fragment. Sync and export never persist them; authored sources
still reject `link` and `script`, and the normalizer does not remove unsupported
elements embedded within meaningful Page content.

Apply Sprint 6's shared Page URL canonicalizer before conversion. Stable Canvas
course/file links are written in their canonical root-relative form. Verifier
parameters, signed query values, embedded credentials, and expiring URLs are
never written to Markdown, HTML, reports, or provenance. If a volatile URL cannot
be resolved to stable Canvas identity, report `conversion_blocked` with sanitized
diagnostics and write no source. Round-trip comparison uses canonicalized bodies
on both sides so token rotation cannot create false drift.

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

Emit explicit Markdown heading IDs with Python-Markdown attribute syntax, for
example `## Installation {#installation}`. The existing `extra` renderer profile
includes `attr_list` and must be regression-tested to produce
`<h2 id="installation">`. The converter must not invent a second ID convention.

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
- A destination created after the final path check but before installation is
  preserved byte-for-byte and classified without using replace-on-existence
  rename behavior.
- Repeating sync after success reports `skipped_known_local` and creates no
  duplicate Page source.
- Broad and targeted sync compute targets from the same complete Page inventory;
  a fixture with colliding slugs receives the same Page-ID-suffixed path in both
  plans.
- Markdown fixtures round-trip ordinary prose, lists, links, anchors, code, and
  tables through the existing renderer.
- Safe inline styles and structures either survive through Markdown/raw-HTML
  islands or produce a clear HTML-fallback recommendation.
- Unsupported or lossy conversions are blocked before a file is written.
- Volatile URLs are canonicalized to stable Canvas-relative forms or block the
  action; authored sources and reports never contain verifier/signed values.
- Generated HTML is a validated fragment source, not a preview or standalone
  document.
- Live source creation writes stable provenance only after successful local
  readback and hash comparison.
- Interrupted or failed provenance writes are recovered on a later run only
  after exact Page-ID, body-hash, and anchor verification.
- Case, Unicode, reserved-name, trailing-character, and sanitized-slug filename
  collisions are classified deterministically before any write.
- Markdown emits `{#stable-id}` heading attributes that round-trip through the
  current renderer.
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
