# Sprint 14: Authored Discussion Creation And Safe Updates

Status: implemented and locally verified on 2026-08-11. Target release: 0.11.0.

## Outcome

Replace course-specific discussion posting scripts with one authored-source
workflow that can create graded topics with instructor seed replies, verify the
result, and update an identified root topic without disturbing any discussion
entries.

The implementation lives in `src/danvas/discussion_sources.py`. Shared authored
datetime semantics live in `src/danvas/authored_content.py` and are also used by
Pages. The discussion module is a new
module because the create/update workflow has a different safety boundary from
the existing discussion export and participation-scoring operations: it owns
authored-source parsing, stable identity, mutation planning, readback evidence,
and source-map provenance.

## Source Contract

A source is Markdown with YAML or TOML front matter. The root topic body comes
first. Each instructor seed reply begins with a line containing exactly
`--- reply ---` (surrounding horizontal whitespace is allowed):

```markdown
---
title: Unit 4 Discussion
discussion_type: threaded
published: false
points_possible: 10
assignment_group_name: Discussions
due_at: 2026-09-01T04:59:00Z
---

Discuss the unit using evidence from the reading.

--- reply ---

## Prompt One

Start with the strongest example.

--- reply ---

## Prompt Two

Respond to a peer.
```

The root body and every reply must be nonempty. The first Markdown heading in a
reply is its prompt heading for verification. `seed_entry_ids` may be present as
provenance, but normal creation records entry IDs in `.danvas/source-map.json`
instead of rewriting authored source.

Topic fields include `title`, `discussion_type`, `published`,
`require_initial_post`, `delayed_post_at`, `lock_at`, rating options, and group
category metadata. Grading-related fields include `points_possible`, `due_at`,
`unlock_at`, `grading_type`, and `assignment_group_id` or
`assignment_group_name`. A topic is treated as graded only when grading-related
metadata is declared; ordinary `published` or `lock_at` metadata does not create
an assignment accidentally.

## Commands

```bash
danvas discussions create --course-id COURSE_ID discussion.md \
  --seed-replies --dry-run
danvas discussions create --course-id COURSE_ID discussion.md --seed-replies

danvas discussions verify --course-id COURSE_ID discussion.md
danvas discussions update --course-id COURSE_ID discussion.md --dry-run
danvas discussions update --course-id COURSE_ID discussion.md \
  --body-only --dry-run
```

`create` refuses a source containing reply sections unless `--seed-replies` is
present. This prevents a plausible-looking partial creation that silently omits
the instructor prompts. Dry-run does not initialize Canvas and never writes
source-map provenance.

Live creation:

1. prints a Canvas mutation banner;
2. creates the topic and its assignment metadata in one request;
3. immediately records the returned topic identity as recovery provenance;
4. posts seeded replies in reverse source order because the observed Canvas
   display is newest-first;
5. retains the returned IDs in authored source order;
6. reads the topic, assignment, and returned entries back;
7. verifies declared topic/assignment fields, root body, seed count, and prompt
   headings;
8. replaces recovery provenance with the complete verified source-map entry.

The command prints and records topic ID, assignment ID, stable Canvas URL, and
seed entry IDs.

## Identity And Verification

`verify` and `update` resolve identity in this order:

1. explicit `--discussion-id`;
2. `canvas_id` front matter;
3. the `discussion` entry for the source path in
   `.danvas/source-map.json`.

Front-matter/source-map conflicts fail unless the explicit CLI ID resolves the
conflict. Create refuses any source already bound by front matter or source-map
identity and directs the operator to verify/update instead. These commands never
title-match, and verify/update never create a missing topic. An announcement ID
is rejected by update.

Verification compares only declared values plus the always-declared title and
root body. Supported evidence includes title, stable URL, discussion type,
initial-post requirement, due/unlock/lock dates, points, publication state,
assignment linkage and identity, assignment group, grading type, and group
category, every accepted rating/podcast/pinning/section field, and assignment
override visibility. Date-only values and timezone-equivalent ISO timestamps
compare semantically. Seed count and headings are checked only when stable entry
IDs are available from front matter, source-map provenance, or the current
create run; otherwise terminal and report output explicitly say seed verification
was not available. Student top-level posts are never guessed to be instructor
prompts.

## Update Boundary

Full update sends the root body and only front-matter fields actually declared
by the author. Omitted publication or grading fields retain their Canvas state.
`--body-only` sends exactly one field: the root topic `message`.

Neither update mode calls an entry create, edit, delete, or reorder endpoint.
Reports state `entry_mutation: none`; seed replies and student responses remain
untouched even when the local source contains reply sections.

Live update performs a fresh readback and writes source-map provenance only
when every in-scope field matches. Existing seed entry IDs are carried forward.

## Reports And Provenance

Create, verify, and update write normal report runs when a course project is
available, with `--no-report`, `--report-root`, `--report-dir`, and
`--report-slug` controls. Reports use evidence schema
`discussion-source-v1` and include planned scope, bounded comparisons, returned
IDs, and readback status.

The source map stores stable topic, assignment, URL, update timestamp, seed
entry IDs, comparable metadata, prompt count/headings, and a root-body hash. An
immediate post-create entry contains `topic_created` plus pending/incomplete
verification state and is sufficient to block unsafe create retries. Complete
readback replaces it with normal verified provenance. The source map does not
duplicate the full root body or reply bodies.

## Failure Semantics

- Invalid or empty sources fail before Canvas initialization.
- A seed-bearing create without `--seed-replies` fails before Canvas
  initialization.
- Unbound dry-runs and no-change updates do not mutate Canvas or the source map.
- Topic/assignment/reply readback mismatch exits nonzero while retaining
  recovery identity and any returned seed entry IDs.
- A failure after topic creation may leave a partial Canvas object; the report
  is marked failed, recovery provenance blocks duplicate create, and the printed
  topic/entry IDs remain explicit recovery handles.
- Verification distinguishes not found from an indeterminate lookup failure.

## Acceptance

Automated coverage includes parsing, seed confirmation, offline dry-run,
graded creation payloads, every accepted compare field, timezone/date-only
equivalence, reverse posting, source-order and interrupted-create provenance,
duplicate retry blocking, visible unavailable-seed verification, body-only
update isolation, and declared-field-only full updates.

Ruff, ty, and all 437 tests pass. The 0.11.0 isolated release smoke also passes
for both editable and built-wheel installs, including version, help, and local
auth-doctor checks. Live Canvas acceptance is intentionally separate because it
creates and updates Canvas objects; it requires an explicitly authorized
disposable discussion target and must clean that target up afterward.
