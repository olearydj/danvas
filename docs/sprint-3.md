# Sprint 3: Safe Updates and Round-Trip Verification

Status: provisional. Drafted 2026-06-12; refine after sprint 2.

## Theme

Move from create-only to maintain: update existing Canvas objects from local sources without creating duplicates, and prove after every write that Canvas holds what the source says. The diff and classification machinery from sprint 1 (`status`, `refresh --diff`) is the foundation this builds on.

## Candidate goals

1. Update/upsert for write commands (backlog "Assignment Update Or Upsert" and HANDOFF item): `assignments update SOURCE.md --dry-run` and equivalents, keyed by Canvas ID when present, title matching only behind an explicit flag, with a field-by-field before/after diff in dry-run.
2. Readback verification (backlog "Assignment And Announcement Readback Verification"): `assignments verify`, `announcements verify`, and `announcements latest`, resolving objects by explicit ID and comparing stable Canvas fields to the local source. Grouped assignments verify `group_category_id` and peer-review settings.
3. Round-trip metadata (backlog/HANDOFF sidecar item): a sidecar manifest for posted objects recording assignment IDs, discussion topic IDs, file IDs, and URLs, keeping reusable Markdown clean. This is what upsert and verify key off, so its format is the first design decision of the sprint.
4. Markdown asset rewriting (completes sprint 2's `files upload`): scan Markdown-backed sources for local image/file references, upload them to Canvas Files, and rewrite links to Canvas URLs before posting.
5. Single-file download and compare (backlog "Single Canvas File Download And Compare"): `files download-one` by file ID or unambiguous Canvas path, plus `files compare` by filename/size/checksum with optional Office package-part comparison.
6. File inventory report improvements (backlog P1, remainder): clearer classification counts and ignore-rule configuration beyond what sprint 1's `status` already delivers.

## Stretch

- Human-readable operation reports (backlog P2): `--report-md PATH` across audit/status/download workflows with consistent sections.

## Beyond sprint 3 (unscheduled)

- Rubric support; the backlog gates it on update and sync behavior being stable, which this sprint delivers.
- Comprehensive activity logging (HANDOFF) without becoming the archival ledger tool.
- Live Canvas gradebook export/download (HANDOFF).
- Remaining `gradebook.py` complexity cleanup (HANDOFF chore; take opportunistically).

## Definition of done

Carry over sprint 1's definition of done, plus: update the Codex skill at `/Users/djo/.codex/skills/teaching-danvas/` (`SKILL.md` and `references/danvas-commands.md`) for any command surface changes. Sprint 3's upsert work specifically invalidates the skill's "import always creates a new quiz; no update-in-place" caveat. Bump the version in `pyproject.toml` (minor for the sprint's features) and tag `vX.Y.Z` at sprint close-out.

## Open questions for planning

- Where do Canvas IDs live: sidecar manifest only, optional front matter, or both with sidecar as the default? The backlog leans sidecar-first to keep reusable Markdown clean.
- Does upsert need three-way comparison (local source, sidecar's last-posted state, live Canvas) to detect manual Canvas edits, or is the two-way before/after diff enough for a first release?
