# Sprint 1: Transaction-Safe Grade Patching And Cleanup

Status: implemented and verified on 2026-07-10.

## Objective

Make targeted grade changes reviewable, baseline-aware, reversible, and safely
correctable. Preserve the existing CSV workflow while eliminating blind dry-runs
and manual Canvas comment cleanup.

## Command Surface

```bash
danvas grades post --assignment-id 123 --grades-csv patch.csv --dry-run
danvas grades clear --assignment-id 123 --grades-csv clear.csv --dry-run
danvas grades comments --assignment-id 123 --canvas-id 456 --output comments.json
```

`grades post --dry-run` becomes an online preflight: it reads the assignment and
targeted submissions but performs no mutation. Add `--offline-preview` only to
preserve the current no-auth CSV display behavior.

## Input And Plan

- Continue requiring `CanvasID` and `Grade` for `grades post`.
- Continue accepting `Name` and `Comment`.
- Add optional `ExpectedCurrentGrade`. A mismatch blocks that row and the live
  operation.
- The plan must show course, assignment ID and title, student identifier, current
  grade, proposed grade, numeric delta when available, and the comment action.
- If a comment states a recognizable numeric deduction that conflicts with the
  grade delta, fail preflight unless the user explicitly removes or corrects it.
- Existing comment behavior remains append-if-exact-text-is-absent.

`grades clear` targets only listed students. Comment deletion is allowed only by
explicit comment ID or exact supplied text, and only for comments authored by the
authenticated instructor. Loose text matching and bulk comment deletion are out
of scope.

## Safety And Evidence

- Before the first live write, save a collision-safe rollback CSV and JSON beside
  the input CSV by default; allow an explicit `--rollback-dir` override.
- The rollback artifact records the assignment, targeted Canvas IDs, original
  grades, original comment IDs/text needed for recovery, and capture time. Mark it
  private and never overwrite it.
- Refuse live mutation if any targeted row fails baseline or ownership checks.
- Print the normal mutation banner, perform readback verification, and record
  partial failures without hiding successful rows.
- Never place private grade/comment evidence in `.danvas/source-map.json`.

## Acceptance Criteria

- Dry-run catches a wrong assignment target, baseline mismatch, and grade/comment
  deduction mismatch without writing to Canvas.
- Legacy grade CSVs remain valid.
- A live patch creates rollback evidence before mutation and verifies every row.
- Rerunning an already-applied patch remains idempotent.
- Exact instructor-owned comments can be listed, deleted, or replaced; other
  instructors' comments and student comments are never deleted.
- Tests cover mixed success, rollback write failure, sanitized exceptions, and
  readback mismatch.

## Deferred

- Rubric-based grading and rubric replacement.
- Broad gradebook export or long-term grade history.
- Fuzzy or semantic interpretation of arbitrary comment prose.
