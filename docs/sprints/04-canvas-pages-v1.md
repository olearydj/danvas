# Sprint 4: Canvas Pages V1

Status: implemented and verified on 2026-07-10.

## Objective

Support the immediate workflow of authoring a Canvas Page locally, inspecting the
exact Canvas-bound HTML, creating it safely as a draft, and verifying readback.

## Command Surface

```bash
danvas pages list --course-id 123
danvas pages export --course-id 123 --output pages.json
danvas pages render content/pages/resources.md --output -
danvas pages create content/pages/resources.md --dry-run
danvas pages verify content/pages/resources.md
```

`pages list` is stdout-first, `pages export` and `pages render` are
explicit-output, and create dry-run/readback plus verify are report-run-first.

## Source Contract

Accept Markdown as the normal source and native HTML when exact structure is
needed. Front matter requires `title` and may include `page_id`/`canvas_id`,
`published`, `front_page`, `editing_roles`, `publish_at`, and
`notify_of_update`.

- New Pages default to `published: false`, `front_page: false`, and no update
  notification.
- Markdown renders to a semantic HTML fragment, never a full HTML document.
- Native HTML rejects scripts, external stylesheet links, JavaScript URLs, and
  document-level wrappers. Allowlisted inline markup/styles may pass through for
  Canvas readback verification.
- Local relative assets are detected before a write. V1 fails clearly rather
  than silently publishing broken references.
- `pages render` is local-only and does not update provenance.

## Create And Verify

- Dry-run shows title, publication state, scheduled time, editing roles, rendered
  body hash, unresolved assets, and the exact planned action.
- Live create prints the mutation banner, creates the Page, reads it back, and
  compares stable metadata plus normalized body content.
- Write a `page` entry to `.danvas/source-map.json` only after successful
  readback. Store stable ID/slug, comparable fields, renderer version, and body
  hash, not the full body.
- `pages verify` resolves by explicit ID, front matter, then source map; title-only
  matching is not part of V1.
- Normalization may ignore insignificant Canvas attribute ordering but must not
  hide changed text, links, IDs, elements, or styles.

## Acceptance Criteria

- Markdown and native HTML fixtures render deterministically.
- A Page can be dry-run, created unpublished, read back, recorded in the source
  map, and verified.
- Failed readback leaves no provenance entry and produces failed report evidence.
- Publication, front-page, unresolved-asset, unsafe-HTML, and notification guards
  are covered by tests.
- Reports and source maps contain no verifier URLs or unnecessary full bodies.

## Deferred

- Canvas-to-local Page sync.
- General Page update, upsert, rename, front-page changes, or deletion.
  Body/publication-only update is specified separately in Sprint 4.5.
- Snapshot/status integration and module-link maintenance.
- Local asset upload/rewriting.
- Broad CSS compatibility and advanced stylesheet behavior. Restricted parsing,
  inlining, profile V1, and `pages css-check` are specified in Sprint 4.5; local
  preview CSS is never sent to Canvas.
