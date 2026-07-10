# Sprint 4.5: Canvas Pages V2 - Styled Update Workflow

Status: implemented and verified, including the explicitly approved live INSY
7970 draft creation, visual review, publication update, and final verification,
on 2026-07-10.

## Objective

Extend Pages V1 into a bounded general workflow: render Markdown deterministically,
inline a restricted CSS sidecar, create and read back a draft, update an existing
Page's body/publication state, and verify the result.

This command family is general-purpose. The INSY 7970 Additional Resources Page
is the first field-validation fixture, not part of the product contract. No
command, renderer, compatibility rule, or CSS behavior may depend on its title,
content, lecture index, paths, CSS classes, or course ID.

## Command Surface

```bash
danvas pages css-check content/pages/example-page.canvas.css \
  --source content/pages/example-page.md
danvas pages render content/pages/example-page.md --output -
danvas pages create content/pages/example-page.md --dry-run
danvas pages update content/pages/example-page.md --page-id 123 --dry-run
danvas pages verify content/pages/example-page.md --page-id 123
```

`pages update` in this sprint is deliberately narrow: it may change only the
rendered body and `published` state. It must refuse title/slug changes, front-page
changes, deletion, or resolution that would create a new Page.

## Markdown Rendering

- Render an HTML fragment suitable for `wiki_page[body]`, never a full document.
- Pin a renderer/profile version and include it in render, dry-run, and readback
  evidence.
- Preserve explicit heading IDs and generate deterministic IDs for ordinary
  headings. Duplicate headings receive stable suffixes.
- Preserve same-page links such as `#installation` and verify that every local
  fragment target survives rendering and Canvas readback.
- If the first body H1 matches the normalized front-matter title, omit that H1
  from the Canvas-bound fragment without changing the Markdown source. Report the
  action in render output. A nonmatching H1 is preserved but warned about.

## Restricted `canvas_css`

The Page source may declare:

```yaml
canvas_css: example-page.canvas.css
css_policy: strict
```

- Resolve the sidecar relative to the Page source.
- Parse CSS with a real CSS parser and apply selectors to the rendered fragment
  with a selector engine; do not use regular-expression parsing.
- Inline accepted declarations deterministically, then remove classes used only
  as authoring hooks when doing so cannot change links or semantics.
- Reject `@import`, `@font-face`, scripts, JavaScript URLs, external asset URLs,
  unsupported at-rules, custom properties, pseudo-elements, and selectors or
  values that cannot be safely inlined.
- Report parse errors, unsupported declarations, unmatched selectors, conflicts,
  and declarations lost during inlining.
- A Canvas stylesheet must remain usable without media queries. The CSS engine
  validates and inlines the supported layout supplied by the author; it does not
  choose, rewrite, or special-case a Page's presentation.

`pages css-check` validates the stylesheet against the compatibility profile. With
`--source`, it also renders the Page and reports selector matches and the final
inline-style plan. It performs no Canvas calls or source edits.

## Canvas Compatibility Profile V1

Add a small, versioned allowlist defining a conservative general baseline for
ordinary Canvas Pages. The profile must:

- allow common prose, heading, list, link, code, and table markup
- preserve `id`, same-page `href`, accessibility attributes, and safe table
  attributes
- allow only a documented, conservative set of inline presentation properties
- reject document wrappers, `style`/`script` elements, event handlers, and unsafe
  URLs
- identify itself in every render, plan, update, and verification report

Compatibility means "accepted by profile V1," not a guarantee that Canvas will
preserve the markup. Live readback remains authoritative.

## Create, Update, And Verify

- Re-exercise V1 draft creation using a styled source, including
  mutation banner, readback, report evidence, and source-map write after success.
- `pages update` resolves only by explicit Page ID, front matter ID, or source-map
  ID. It shows normalized body and publication changes in dry-run.
- Default `notify_of_update` to false. Publication changes must be explicit in
  front matter and visible in the plan.
- Live update reads the Page back and compares normalized body, accepted inline
  styles, anchors, and published state. Compare styles per element as normalized
  property/value maps, not raw `style` strings, so declaration reordering and
  equivalent Canvas value normalization do not create false mismatches. Removed
  or meaningfully changed properties remain mismatches. A mismatch exits nonzero
  and preserves failed report evidence.
- `pages verify` always checks `published` when it is declared in the source; it
  must not treat a body match as success when publication state differs.

## First Field Validation: INSY 7970

This section defines a non-normative integration fixture. It validates the general
implementation against real course content but does not add product behavior.

Before the field dry-run, add Page front matter to the actual student-facing
course source at `content/pages/additional-resources.md`. Do not modify the
internal planning document at `docs/additional-resources.md`. At minimum, the
student-facing source must declare `title`, `published`, `canvas_css`, and
`css_policy`.

Keep `content/pages/additional-resources-preview.css` unchanged as preview-only
styling. It uses document selectors, a media query, and responsive grid behavior
that are outside compatibility profile V1. Create a separate
`content/pages/additional-resources.canvas.css` that preserves the visual intent
with supported selectors and inlineable declarations. Because media queries are
unsupported, that course-owned sidecar should choose a single-column lecture
index that remains usable at narrow widths. This is an authoring decision in the
fixture, not renderer behavior. Do not create a separate tracked rendered HTML
file.

After successful live readback, keep stable Canvas identity in the existing
source-map sidecar. Add a front-matter Page ID only if the course intentionally
wants that ID embedded in its authored source.

## Acceptance Criteria

- Markdown rendering produces a deterministic fragment with matching-H1 handling.
- CSS checks use structured parsing, enforce profile V1, and produce deterministic
  inline styles.
- Same-page links and generated/explicit heading IDs survive render and readback.
- Generic Markdown, HTML, CSS, heading, anchor, and publication fixtures establish
  reusable behavior independently of any course repository.
- The INSY 7970 source has valid front matter and passes render plus css-check as
  an end-to-end integration fixture.
- A styled draft can be created, read back, and verified.
- An existing Page can update body and publication state without changing title,
  slug, front-page state, module membership, or unrelated fields.
- Published-state and body/style mismatches fail verification.
- Production code and tests contain no branch keyed to a course ID, Page title,
  filename, content phrase, CSS class, or fixture-specific layout.

Required non-normative INSY 7970 field test:

1. Set `published: false`, create the Page, and verify the draft readback.
2. Change the source to `published: true`.
3. Dry-run the existing-Page update and review the publication transition.
4. Perform the explicitly approved live update.
5. Read the Page back and verify `published: true` together with body, styles,
   and anchors.

## Deferred

- Canvas-to-local sync and snapshot/status integration.
- Asset upload or relative-link rewriting.
- Delete, rename, front-page, module, and general upsert workflows.
- Broad CSS compatibility, media queries, pseudo-classes/elements, custom
  properties, remote assets, or institution theme CSS.
