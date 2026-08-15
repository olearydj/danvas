# Danvas Workflow Patterns

## Course State

Use `danvas refresh --diff` when the saved snapshot may be stale, then use
`danvas status` for local comparison. A partial collection limits conclusions;
it does not prove deletion or absence.

## Authored Content

For assignments, Pages, announcements, and discussions:

1. lint or render locally where available;
2. run the create/update command without `--apply`;
3. review stable identity, scope, expected state, assets, visibility, and report;
4. add `--apply` only for an authorized mutation; and
5. run the family verification command or inspect authoritative result evidence.

Update/verify flows normally use explicit IDs, source front matter, or project
provenance. Do not invent a title fallback.

## Local Sync

Pages, announcements, and discussion prompt sync use `--dry-run` to preview
missing local sources. Run without `--dry-run` to create missing files. These
commands do not overwrite authored files and never accept `--apply`.

## Classic Quiz Analysis

Run `danvas quiz export-analysis --quiz-id ID` to plan the official Canvas
student-analysis report request. Review the stable IDs and private destination,
then add `--apply` only after authorization. Report creation is a Canvas
mutation even though it changes no quiz content or grades. After the verified
private CSV exists, inspect it locally with `danvas quiz analysis PATH`.

Anonymous Surveys and New Quizzes are not supported by the acquisition command.
Do not replace missing coverage with an unapproved direct API or browser path.

## Grades And Feedback

Run grade post/clear or submission feedback without `--apply` first. Applied
grade workflows retain private rollback/results/readback evidence and stop after
uncertain outcomes. Discussion scoring writes a private grade-plan CSV; review
it, then pass it to `grades post` rather than posting directly.

## Files

Inventory, download, compare, and upload are separate operations. Upload plans
show duplicate behavior; add `--apply` only after reviewing `error`, `overwrite`,
or `rename`. A renamed race or unverifiable returned identity is a conflict, not
success.

## Reports

Use `danvas reports list` and `danvas reports latest [SLUG]` to discover retained
evidence across course-internal and private roots. Do not guess the newest
directory by filename alone.
