# Sprint 2: Publish a Grouped Case Assignment End-to-End

Status: provisional. Drafted 2026-06-12; refine at sprint planning after sprint 1 lands.

## Theme

The highest-friction workflow observed in live course prep that sprint 1 does not touch: standing up a grouped case assignment. Today that means falling back to raw Canvas API calls for group categories, CSV imports, and membership verification, and using a side script to seed discussion prompts. This sprint makes `danvas` cover the whole path: plan groups locally, create the Canvas group structure, verify membership, upload the case prompt file, and create the graded or seeded discussion.

## Candidate goals

1. Groups suite (backlog "Canvas Group Categories And Memberships"): `groups categories` list/rename/create, `groups import` from a Canvas-compatible CSV with progress polling, and `groups verify` against an expected CSV. Mutations are explicit commands with `--dry-run`; ambiguous roster matches refuse to continue. This is the highest-risk operational step in the workflow (publication depends on `group_category_id`), so it leads the sprint.
2. Group planning (backlog "Group Planning From Roster"): local-only `groups plan` that turns a roster export plus constraints (group size, rounds, balance-by column, minimized repeat pairings) into Canvas import CSVs and a validation summary. Never writes to Canvas.
3. Seeded discussion creation (backlog "Graded And Seeded Discussion Creation From Markdown"): `discussions create` from a single Markdown source with front matter for the root topic and `--- reply ---` sections for instructor prompt replies, with full dry-run of every payload. Reuses the shared `frontmatter` module.
4. Basic `files upload` (backlog "Canvas File Upload Helper"): delivered as a v1 command for uploading one or more local files to an existing named Canvas Files folder or folder ID, with dry-run, duplicate policy, safe JSON report output, and no folder creation. Markdown asset rewriting stays in sprint 3.
5. Due-date ergonomics (HANDOFF item): date-only `due_date:` front matter, course-local timezone from `.danvas/config.toml`, end-of-day defaults. Small, and it serves every write command in this sprint.

## Stretch

- Transcript filing helper (backlog P1): `--file-to`/`--name-pattern` options or a suggested-filename output after Panopto caption download.

## Dependencies on sprint 1

- The expanded snapshot's group-category section feeds `groups verify` and `status`.
- The mutation banner from sprint 1 Goal 5 applies to every new write command here.
- QTI import's progress-polling code should be shared with `groups import` (both poll Canvas progress objects); extract a common helper when the second consumer appears.

## Definition of done

Carry over sprint 1's definition of done, plus: update the Codex skill at `/Users/djo/.codex/skills/teaching-danvas/` (`SKILL.md` and `references/danvas-commands.md`) for any command surface changes; it lives outside this repo and is missed by repo-wide searches. Bump the version in `pyproject.toml` (minor for the sprint's features) and tag `vX.Y.Z` at sprint close-out.

## Open questions for planning

- Does `groups plan` need a real constraint solver, or is the observed greedy/retry approach from the ad hoc session good enough to ship first?
- Should seeded-reply creation be idempotence-aware, or documented as create-once with mandatory dry-run (the backlog allows either)?
