# Mutation Safety

Danvas separates reading and planning from authorization to change Canvas.
The default is deliberately safe: omitting both mode flags never authorizes a
Canvas mutation.

## Plan Then Apply

Run a mutating command without `--apply` to plan:

```bash
danvas assignments update content/assignments/week-01.md
```

Review the target course, object identity, field changes, publication state,
notification behavior, asset actions, and retained plan. Then authorize the
same intended operation explicitly:

```bash
danvas assignments update content/assignments/week-01.md --apply
```

`--dry-run` is the explicit compatibility spelling for plan mode. Combining
`--dry-run` and `--apply` is an error before project resolution,
authentication, or output creation.

No user or project configuration can restore mutation-on-omission.

## Commands Requiring Apply

The `0.18.0` Canvas-mutation surface is:

- `assignments overrides-sync`
- `assignments create`
- `assignments update`
- `assignments upsert`
- `quiz import-qti`
- `submissions feedback`
- `grades post`
- `grades clear`
- `discussions create`
- `discussions update`
- `pages create`
- `pages update`
- `announcements create`
- `announcements update`
- `files upload`

Immediately before each reviewed write primitive, a common assertion verifies
that normalized mode is `apply`. The source-level architecture inventory forces
review when mutation call sites or assertion sites change.

Some commands add a semantic confirmation:

```bash
danvas assignments overrides-sync assignment.md --apply --confirm apply
danvas assignments upsert assignment.md --apply --confirm create
danvas assignments upsert assignment.md --apply --confirm update
```

These guards are additive. `--confirm` without `--apply` does not authorize a
write.

## Local Writes Are Different

The following commands may create missing local sources but never mutate
Canvas:

- `pages sync`
- `announcements sync`
- `discussions sync-prompts`
- `recordings panopto-captions`

Their `--dry-run` controls local download or source creation. They do not use
`--apply` merely to write local files, and their no-clobber rules remain in
force.

## Preflight And Expected State

Plans may read Canvas. Apply paths re-read relevant state where the command
supports reconciliation. Grade plans may carry `ExpectedCurrentGrade` and
`ExpectedComment`; assignment and authored-content workflows retain stable
identity and bounded expected fields.

Treat preconditions as one-shot guards. After verified success, refresh or
remove stale expectations before an intentional retry. Do not weaken a guard
just to make an apply proceed.

File upload defaults to duplicate policy `error`. Explicit overwrite or rename
does not convert a race into success: if a concurrent file appears or Canvas
returns an unverifiable name, the result is a conflict or unverifiable outcome.

## Evidence States

Consequential workflows separate transport response from authoritative
readback. Common result meanings include:

`already_applied`
: Readback showed the intended state before a new write.

`applied_verified`
: Canvas accepted the write and authoritative readback matched.

`unchanged_failure`
: The write failed and readback established that the prior state remained.

`partially_applied`
: Some intended effects are visible and others are not.

`applied_unverified` or `accepted_unverified`
: Canvas may have accepted the write, but the final state could not be proven.

`indeterminate`
: The available evidence cannot bound the final state safely.

`skipped_after_stop`
: A prior unsafe outcome stopped later rows before they were attempted.

Exact vocabularies vary by transaction family, but the retry rule is stable:
never describe an uncertain acceptance as failure and never retry it blindly.

## Stop And Recovery Rules

After a partial, unverified, or indeterminate result:

1. stop new writes;
2. retain the complete private result and rollback/recovery evidence;
3. inspect Canvas directly or run the relevant read-only verify command;
4. reconcile stable IDs, comments, attachments, and current values; and
5. retry only the rows whose state is known and whose guards are current.

Feedback results retain attachment IDs and exact comment evidence. A comment
write that may have been accepted remains `accepted_unverified` unless readback
matches both the exact text and attachment identity. This prevents blind
duplicate comments or attachments.

Grade actions retain rollback material before writing and halt on unsafe
settlement states. Rollback is an explicit recovery workflow, not an automatic
claim that every remote state can be restored.

## Notifications And Visibility

Publication, availability, notifications, comments, seeded replies, and grade
visibility can affect students even when a numeric grade does not change.
Review these fields in plan output. Confirm publication state in Canvas after
high-consequence changes.

## Automation

Bare invocation of commands that once mutated now plans and exits successfully.
This fails safe, but old automation may mistake a plan for completed work.
Automation should:

- add `--apply` only after reviewing the command's migration guide;
- preserve required `--confirm` values;
- inspect structured result/evidence status rather than only exit code; and
- treat nonzero, partial, unverified, or indeterminate results as requiring
  reconciliation.

See the [0.17.0 migration guide](migrations/0.17.0.md) for the full behavioral
transition and the [Privacy guide](privacy.md) for evidence storage.
