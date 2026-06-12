# Sprint 1: Close the Local-to-Canvas Loop

Status: implemented 2026-06-12, pending live verification: Goal 1's refresh against a real course, and Goal 4's QTI import against a sandbox course. The `v0.1.0` tag from Goal 5 waits on that verification. Drafted 2026-06-12 from `docs/backlog.md` and `HANDOFF.md`.

## Theme

An instructor or agent working in a course workspace can answer "what differs between my local sources and Canvas?" with one read-only command, and can release a quiz end-to-end without leaving `danvas`. Everything else in this sprint exists to support those two outcomes.

## Why now

The session-derived recommendations in `docs/backlog.md` come from a live INSY 6600 session this month and name two P0 items: a QTI import/publish/verify workflow and a read-only course status report. The course is running now, quiz releases are recurring and time-sensitive, and the status report is the safest default behavior for agent-assisted course work. Both P0s depend on a richer course snapshot, which is why the snapshot work goes first.

## Goal 1: Expanded course snapshot (foundation)

Extend `danvas init`/`danvas refresh` so `.danvas/course.json` captures what the comparison features need, per the "Expanded Course Snapshot" backlog item.

Scope:

- Canvas Files metadata: file ID, display name, filename, folder, size, updated time, content type.
- Discussion topics: topic ID, title, URL, assignment ID when graded, published/locked state, normalized message text.
- Announcements, captured separately from ordinary discussions.
- Quiz shells: quiz ID, assignment ID, title, description, points, due/unlock/lock dates, published state.
- Group categories: category ID, name, self-signup settings, group count, member counts. No rosters or member lists in the general snapshot.
- Add a `schema_version` field so `refresh --diff` (Goal 3) and future consumers can detect old snapshots.

Constraints:

- The snapshot stays non-secret: no download verifier URLs, no student-identifying data.
- Snapshot growth should not change existing consumers; current keys (`course`, `assignment_groups`, `assignments`, `folders`, `generated_at`) keep their shape.

Acceptance criteria:

- `danvas refresh` against a real course produces all new sections.
- Tests build the snapshot from an extended `FakeCourse` and assert section contents.
- A test asserts no `verifier` strings and no member lists appear in the snapshot, mirroring the existing files-inventory secrecy tests.

Size: M. No open design questions; the backlog item specifies the field list.

## Goal 2: `danvas status` read-only course report (session P0)

One command that replaces the multi-command audit from the June session.

Scope:

- A local source scanner module implementing the documented conventions: `content/announcements/*.md`, `content/discussions/*.md`, `content/quizzes/chap*.md`, `content/cases/*-assignment.md`. It classifies source type, title, comparable metadata, and generated artifacts such as QTI zips.
- `danvas status`: compare the snapshot against local sources and report each item as `exact`, `metadata mismatch`, `local-only`, `Canvas-only`, `filename-only match`, `unsupported comparison`, or `snapshot stale`.
- Coverage across assignments, quiz shells, announcements, discussions, and files. Group categories appear as summary counts only.
- Human-readable output by default, JSON via `--output`, optional Markdown report via `--report-md`.
- Quiz shell awareness per the backlog item: compare local quiz Markdown title/points to Canvas quiz shells, report missing QTI zips and Canvas-only shells, and state explicitly that question-body comparison is unavailable.

Constraints:

- Read-only. No Canvas mutations, no file downloads. Writes only to explicitly requested output paths.
- Works from the snapshot plus local files; it must not require live Canvas calls (a stale-snapshot warning covers the gap).

Acceptance criteria:

- Running `danvas status` in a fixture course workspace produces the classification report with at least one example of each classification covered by tests.
- A stale-snapshot warning fires when `generated_at` is older than a configurable threshold.
- JSON and Markdown outputs round-trip the same data; reports contain no secrets.

Size: L. This is the largest item; the scanner and the comparison logic are separable commits.

## Goal 3: `danvas refresh --diff` (session P1)

When refresh replaces the snapshot, report what changed since the previous one.

Scope:

- Keep the prior snapshot (backup file or in-memory comparison before overwrite).
- Report added/removed/changed assignments, assignment groups, files, quiz shells, announcements, and discussions, as far as the snapshot supports.
- Include timestamps for both snapshots in the summary.

Acceptance criteria:

- Tests compare two fixture snapshots and assert the diff report content.
- A snapshot with an older `schema_version` produces a clear "diff unavailable, snapshot format changed" message instead of a wrong diff.

Size: S-M. Pure JSON-to-JSON comparison once Goal 1 lands.

## Goal 4: QTI import, publish, and verify (session P0)

`danvas quiz import-qti`: upload a QTI zip into a course, poll to completion, configure the quiz shell, and verify the result.

Scope:

- Upload/import via the Canvas content-migration API and poll the progress object until the migration finishes or fails, reporting progress ID, status, and errors.
- Update the quiz assignment shell: title, assignment group, due/unlock/lock dates, points, published state, time limit, attempt settings.
- Post-import verification readback reporting quiz ID, assignment ID, URL, published state, dates, points, and any settings that could not be verified.
- `--dry-run` for the shell-settings half; the import itself is documented as non-previewable if Canvas offers no meaningful dry-run.
- Match by explicit quiz/assignment ID when updating. Title matching only behind an explicit flag that refuses ambiguous matches.

Plan of attack:

- Start with a half-day spike against a sandbox course before committing to the command surface. Classic Quiz migration behavior through `canvasapi` is the least-charted territory in this sprint.
- Must-have core: import plus the verification report. First cut if the API fights back: the shell-settings update (the verify report still tells the user what to fix manually).

Acceptance criteria:

- A QTI zip imports into a sandbox course and the verification report matches the Canvas UI state.
- Failure paths (bad zip, failed migration, ambiguous title match) exit nonzero with actionable messages and are covered by tests against fakes.

Size: L, including the spike. Highest technical risk in the sprint.

## Goal 5: Guardrail consistency, CI, and tag (small)

Scope:

- Mutation banner: a consistent preamble before any live Canvas write showing course ID, target object IDs/titles, row counts, and what will be posted. Dry-run already exists everywhere; this is presentation consistency (backlog P2).
- GitHub Actions workflow running `ruff check`, `ty check`, and `pytest` on push and pull request (HANDOFF item).
- If the sprint ends green, tag `v0.1.0`. HANDOFF already flags tagging once the CLI stabilizes; shipping `status` plus quiz release is a defensible "stable enough."

Acceptance criteria:

- Every mutating command prints the banner before live writes; a shared helper keeps wording consistent.
- CI passes on the sprint branch.

Size: S.

## Sequencing

Goal 1 first; Goals 2 and 3 in either order after it; Goal 4's spike can start in parallel with Goal 2; Goal 5 closes the sprint. Each goal lands as a commit series with the suite green at every commit, regression tests included, and README/`docs/course-yaml.md`/HANDOFF updated as behavior changes.

## Cut line

Between Goal 3 and Goal 4. Goals 1-3 deliver the complete read-only story at low risk. Goal 4 is high-value but carries the API risk, and it degrades gracefully to "import + verify" without the settings update.

## Out of scope for this sprint

The groups suite (categories, CSV import with progress polling, `groups plan`), seeded discussion creation, `files upload` and Markdown asset rewriting, assignment upsert/update, single-file download/compare, transcript filing, rubrics, activity logging, and live gradebook export. See `docs/sprint-2.md` and `docs/sprint-3.md`.

## Definition of done

- `uv run ruff check .`, `uv run ty check`, and `uv run pytest` clean at every commit.
- New behavior covered by tests against fakes; no test requires live Canvas.
- README and HANDOFF reflect the new commands; backlog items delivered here are removed or annotated.
- No snapshot, report, or manifest contains secrets, verifier URLs, or student-sensitive data.
