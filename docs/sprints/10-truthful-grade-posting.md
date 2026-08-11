# Sprint 10: Truthful Grade Posting And Release Evidence

Status: implemented, locally verified, accepted in a bounded live Canvas field
case on 2026-08-11, and released in consolidated `v0.10.0`.

## Objective

Make every targeted grade mutation leave truthful, private, and actionable
evidence. A run must distinguish a fully verified change from a partial write,
an unchanged failure, and an indeterminate state, then report whether the
targeted grades are posted to students without inferring visibility from
assignment publication alone.

This sprint combines field-observed backlog items 6 and 10. It also applies the
same failure semantics to `grades clear`, whose grade-plus-comment workflow has
the same multi-step risk as `grades post`.

## Why This Is Next

The current grade workflow already has strong preflight, baseline, ownership,
rollback-capture, and successful-readback behavior. Its remaining gap is more
fundamental than a new command family:

- exact comment replacement uses the wrong low-level CanvasAPI request shape in
  the production fallback
- a grade can be accepted before a later comment operation fails, while the
  terminal summary reports only a failed row
- post/clear/verify results are terminal-only rather than durable private
  receipts
- score and comment readback does not establish whether the resulting grade is
  posted to the student

Until those gaps close, broader gradebook export, assignment-release
automation, and discussion work should not take priority over truthful mutation
evidence.

## Command Surface

Preserve the existing commands and CSV formats:

```bash
danvas grades post --assignment-id 123 --grades-csv patch.csv --dry-run
danvas grades post --assignment-id 123 --grades-csv patch.csv
danvas grades clear --assignment-id 123 --grades-csv clear.csv --dry-run
danvas grades clear --assignment-id 123 --grades-csv clear.csv
danvas grades verify --assignment-id 123 --grades-csv patch.csv
```

Add the standard report controls to `post`, `clear`, and `verify`:

```text
--project-root PATH
--no-report
--report-root PATH
--report-dir PATH
--report-slug TEXT
```

These commands become private report-run-first workflows when a course project
is discoverable. Preserve their concise terminal plans and summaries, and keep
the existing pre-write rollback CSV/JSON location and `--rollback-dir`
compatibility.

Do not add grade-posting-policy mutations, bulk post/hide actions, or a new
gradebook export command in this sprint.

## Mutation And Readback Contract

Represent each row as an explicit sequence of intended effects rather than one
success/failure boolean:

1. Capture the pre-write grade, score, relevant instructor-owned comments, and
   visibility fields.
2. Apply only the planned grade and comment effects.
3. Read the submission back after the planned effects.
4. If any request or verification step raises, attempt a fresh readback before
   classifying the row.
5. Stop processing new rows after the first `partially_applied`,
   `applied_unverified`, or `indeterminate` result. Mark untouched rows
   `not_attempted`.

Use stable machine-readable row outcomes:

- `verified_applied`: every intended effect is present on readback
- `already_applied`: no mutation was needed and the desired state was verified
- `unchanged_failure`: an operation failed and readback proves no intended
  effect was applied
- `partially_applied`: readback proves some, but not all, intended effects were
  applied; record `grade_only`, `comment_only`, or the exact bounded equivalent
- `applied_unverified`: the request returned successfully but readback does not
  confirm the intended state
- `indeterminate`: authoritative readback failed, so the final Canvas state is
  unknown
- `not_attempted`: execution stopped before reaching the row

The command exits nonzero for every outcome except `verified_applied` and
`already_applied`. Terminal totals must report these outcome classes rather
than collapsing them into `Posted` and `Failed`.

Fix exact comment replacement through the documented submission-comment
endpoint using CanvasAPI's supported request encoding, such as
`combine_kwargs()` or a list of `(key, value)` tuples. Tests must exercise the
real requester fallback shape on an object without the convenience
`edit_comment()` method.

## Recovery Contract

Keep pre-write rollback capture mandatory before the first live mutation. Do
not automatically issue compensating Canvas writes after a partial result:
automatic rollback adds another fallible multi-step mutation and can obscure
the state that needs recovery.

Instead, a partial or indeterminate run must produce collision-safe private
recovery evidence containing:

- pre-write, intended, and observed grade/comment state for the affected row
- the phase and sanitized exception that triggered recovery
- whether the observation is authoritative or incomplete
- the exact remaining or reversal preconditions, including expected current
  grade and exact instructor-owned comment ID/text requirements
- a safe next action for completing the intended patch, restoring the captured
  state, or performing manual readback when state is indeterminate

Generate a candidate recovery CSV only when all required guards can be encoded
without weakening exact comment ownership/matching. Otherwise provide JSON and
Markdown guidance, not a partially safe executable file.

## Private Receipt Contract

Dry-run, live post, live clear, and verify reports may contain student grade
evidence and must therefore use private report-run permissions from directory
creation onward. Each report run contains:

- `manifest.json`
- `grades-plan.json` and `grades-plan.md` for dry-runs
- `grades-result.json` and `grades-result.md` for live mutation receipts
- `grades-verify.json` and `grades-verify.md` for explicit verification
- recovery artifacts when required

Receipts record course and assignment IDs, assignment title, command/version,
rollback artifact paths, counts by row outcome, release-state summary, and the
minimum per-row evidence needed to support the conclusion. Normal receipts may
store comment IDs, action, ownership result, exact-match result, and text hashes;
full comment text belongs only in the already-private rollback or recovery
artifact when needed for restoration.

No receipt, manifest, terminal output, diagnostic, or recovery artifact may
contain access tokens, verifier-bearing URLs, temporary signed URLs, or raw
Canvas exception payloads.

## Release-State Evidence

Read targeted submissions with Canvas's visibility association and capture the
documented submission `posted_at` and `assignment_visible` values. Record
assignment-level context separately: `published`, `unlock_at`, `due_at`,
`lock_at`, and `post_manually` when Canvas exposes them.

Use conservative conclusions over the targeted rows:

- `verified_visible`: every desired grade/comment state matches, every target
  has non-null `posted_at`, and every target reports `assignment_visible=true`
- `verified_hidden`: every desired grade/comment state matches and every target
  has null `posted_at`
- `mixed`: targeted rows have a mixture of posted/hidden states or a mixture of
  `assignment_visible` values; include count-first detail
- `not_determined`: required fields are absent, unsupported, unauthorized,
  could not be read reliably, or all grades are posted while one or more target
  assignments are not visible to their owners

Publication, availability dates, and `post_manually` are context, not substitutes
for submission evidence. A published assignment is not sufficient to claim that
grades are visible, and this sprint never posts or hides grades as a side effect
of verification.

## Implementation Boundaries

- Centralize post and clear row execution/classification in one internal helper
  so both commands share the same failure and readback semantics.
- Keep planning, mutation, verification, receipt rendering, and recovery-data
  construction separately testable. Extract a new module only if this cannot be
  done clearly inside `grades.py`.
- Preserve existing CSV compatibility, comment ownership rules, deduction
  consistency checks, assignment-title guards, offline preview, mutation
  banners, and configurable inter-row delay.
- Preserve report-run append-only behavior and existing explicit rollback paths.
- Do not add automatic release-state mutations, gradebook export, rubric writes,
  or broad course-grade reconciliation.

Implementation result: the evidence, sanitization, recovery, and release-state
logic warranted extraction into `src/danvas/grade_evidence.py`. Keeping that
policy-heavy artifact logic separate leaves `grades.py` responsible for Canvas
planning and mutation orchestration and lets both layers be tested directly.

## Automated Acceptance

Tests must cover:

- the production requester fallback for exact comment edit, including its
  parameter encoding and endpoint
- grade success followed by comment failure
- comment success followed by grade failure through the shared classifier
- request failure with authoritative unchanged readback
- successful request with mismatching readback
- failed or unavailable recovery readback
- halt-on-partial behavior and `not_attempted` remaining rows
- idempotent reruns after full success and after a safely recoverable partial
  result
- recovery CSV generation only when all ownership and expected-state guards are
  representable
- private permissions for report directories, manifests, receipts, rollback
  artifacts, and recovery artifacts, including failed runs
- report option conflicts and `--no-report` compatibility
- release conclusions for all visible, all hidden, mixed, assignment-invisible,
  missing fields, and readback failure
- absence of tokens, verifier/signed URLs, and raw unsafe exception text from all
  outputs

Ruff, ty, and the full pytest suite must pass sequentially after one controlled
environment sync.

Local verification on 2026-08-11: Ruff and ty passed, and all 360 tests passed.

## Field Acceptance

After automated verification, run an explicitly authorized, bounded Canvas
field case using instructor-owned comments and a disposable or otherwise safe
target:

1. Dry-run a one-row grade plus `replace_exact` change and retain the private
   plan receipt.
2. Apply it and confirm exact grade/comment readback and the expected release
   conclusion.
3. Verify the production comment-edit fallback is exercised or separately test
   that endpoint against a safe comment.
4. Re-run the patch to prove idempotence.
5. Restore the original state using the captured rollback evidence and verify
   restoration.

Do not induce a live partial failure merely to test recovery; automated
live-equivalent requester and state-machine tests own that case.

### Field Acceptance Result

On 2026-08-11, the user explicitly authorized the sandbox's student enrollment
for this bounded case. The test used a disposable assignment, exact assignment
title/ID guards, one targeted enrollment, private report and rollback
directories, and instructor-owned acceptance comments. No participant identity
is retained in this durable record.

Canvas rejected the first grade/comment seed while the assignment was
unpublished. Danvas read the submission back, correctly classified the row as
`unchanged_failure`, and reported `not_determined`; no target state had changed.
After the exact disposable assignment was temporarily published with update
notifications disabled, the same grade-only seed succeeded. This establishes
an operational constraint for this Canvas instance: an enrollment may be
gradeable and the caller may hold `manage_grades`, yet an unpublished assignment
can still reject the submission update as unauthorized.

The accepted path then passed all required checks:

- a private one-row dry-run planned the guarded grade plus `replace_exact`
  change
- the live command exercised the production requester fallback and returned
  `verified_applied`
- explicit `grades verify` confirmed the exact grade/comment state and reported
  `verified_visible`
- a stable-comment-ID rerun without stale one-shot expected-state guards
  returned `already_applied` and made no mutation
- `grades clear` restored the original empty grade and removed the exact owned
  acceptance comment; an independent readback confirmed both fields were empty
- the disposable assignment was deleted by guarded exact ID/title, and a final
  assignment inventory confirmed cleanup

The deliberately guarded original patch correctly refused a literal rerun once
its `ExpectedCurrentGrade` and `ExpectedComment` preconditions became stale.
For idempotent retry after a verified success, retain the exact owned comment ID
but refresh or omit one-shot preconditions that describe the pre-mutation state.
The bounded live field gate is complete.

## Definition Of Done

- Exact comment replacement works through the production CanvasAPI request path.
- No grade or comment mutation is summarized as wholly failed when readback
  proves that Canvas accepted part of it.
- A partial, unverified, or indeterminate row stops further writes and leaves
  private, actionable recovery evidence.
- Post, clear, and verify leave durable private receipts by default in a course
  project while preserving terminal and rollback compatibility.
- Every post/verify receipt gives a conservative targeted-row release conclusion
  or explicitly says it cannot be determined.
- README, backlog status, CLI help, and the external teaching-danvas command
  reference describe the shipped behavior and safety boundary.
