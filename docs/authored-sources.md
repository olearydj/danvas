# Authored Sources

Danvas discovers project-local sources for status, lint, create, update,
verify, export, and sync workflows. Sources remain ordinary files under the
operator's control; init never moves or generates them.

## Standard Layout

New projects use the materialized `standard-v1` layout:

```text
content/
├── announcements/*.md
├── assignments/*.md
├── discussions/*.md
├── pages/*.md
├── pages/*.html
└── quizzes/*.md
```

Page preview files matching `content/pages/*-preview.html` are excluded.
Existing initialized projects without a `[sources]` table keep `legacy-v1`,
whose assignment and quiz patterns are:

```text
content/cases/*-assignment.md
content/quizzes/chap*.md
```

The other legacy directories match the standard layout. Select or override
layouts in `.danvas/config.toml`; see [Configuration](configuration.md).

## Front Matter

Assignment, announcement, discussion, and Markdown Page sources use YAML
front matter delimited by `---` or TOML front matter delimited by `+++`.

```markdown
---
title: Week 1 Practice
points_possible: 10
assignment_group_name: Practice
due_date: 2026-09-04
published: false
---

Complete the practice activity and submit your work in Canvas.
```

Use explicit ISO 8601 timestamps with `Z` or an offset for datetime fields.
Assignments additionally support date-only `due_date`, `unlock_date`, and
`lock_date`; danvas expands those using `[canvas].timezone`. Page `publish_at`
also accepts a date-only value. Offset-free datetime values are rejected before
Canvas access.

Exact supported metadata depends on the source kind and command. Use leaf help
and a plan run before applying.

## Assignments

Assignment sources combine front matter with a Markdown body. They support
bounded assignment fields, publication state, assignment-group IDs or
project-local names, availability dates, submission settings, and relative
document/image assets.

The standard layout requires recognizable assignment metadata so unrelated
Markdown is not discovered accidentally. A custom assignment include pattern
also requires metadata by default. Set
`require_assignment_metadata = false` only when the broader discovery is
deliberate.

Relative assets are planned, uploaded or reused, rewritten, and verified under
the authored-asset contract. Authored Markdown remains unchanged; stable Canvas
identity is retained in `.danvas/source-map.json` and asset state.

## Announcements And Discussions

Announcements and discussions use Markdown bodies plus kind-specific front
matter. Create and update plan by default and require `--apply` to change
Canvas. Verify compares the bounded owned fields and normalized body text.

Discussion sources may include explicit seeded-reply sections. Posting those
requires the additional `--seed-replies` confirmation because each reply is a
separate Canvas write.

Sync commands read Canvas and write only missing local files. Their
`--dry-run` controls local creation, not Canvas mutation. They never overwrite
authored sources.

## Pages

Pages may be Markdown or native HTML fragments. Markdown rendering provides
stable heading anchors and bounded table semantics. Native HTML is preserved
within the supported fragment policy. Optional `.canvas.css` rules are
validated and inlined deterministically.

Create/update/verify use stable source-map identity and normalized body hashes.
Title-only candidates remain visibly unbound. Canvas links are canonicalized
only when they belong to the configured Canvas origin; signed or verifier URLs
are rejected from retained source state.

## Quiz Sources And QTI

Quiz Markdown participates in local discovery and status by providing a title
such as:

```text
Quiz title: Week 1 Check
```

A neighboring `.zip` is recognized as the QTI artifact. Actual import is
performed by `quiz import-qti`, which targets Classic Quizzes. The Markdown file
is not a complete quiz authoring language.

## Lint Before Canvas

Run source lint locally:

```bash
danvas sources lint
danvas sources lint --fail-on warning
```

Lint checks titles, dates, structure, links, point totals, kind-specific
metadata, and source-map provenance. It emits stable rule IDs and supports
narrow, reasoned `lint_suppress` entries in front matter. Lint does not prove
that Canvas will accept or preserve every field.

## Provenance And Containment

`.danvas/source-map.json` binds project-contained sources to stable Canvas
identities. New entries outside the project are rejected; existing absolute
entries must be migrated. Do not copy a source map between unrelated courses.

The map contains no token or raw Canvas payload, but it can disclose course IDs,
object IDs, source paths, and deployment history. Treat it as course-internal
and review it before publication.

## Safe Workflow

1. Configure or confirm the source layout.
2. Run `danvas sources lint`.
3. Run `danvas status` and inspect discovery.
4. Run the create/update command without `--apply`.
5. Review the plan, target course, publication state, dates, and assets.
6. Apply once, then inspect verification evidence before retrying.

See [Mutation Safety](mutation-safety.md) for apply and recovery rules.
