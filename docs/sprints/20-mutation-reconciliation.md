# Mutation And Evidence Reconciliation

Status: implemented `0.17.0` release candidate through Group 5. Independent
design and implementation review accepted the candidate through `ed68108` on
2026-08-13. The two separately authorized disposable-course probes passed; the
feedback probe exposed and drove the focused `b3893aa` API correction described
below. Supplemental review of that correction and exact branch/tag release
gates remain open.

## Outcome

Make bare invocation safe across the Canvas-writing CLI. Every command that can
mutate Canvas will plan by default, `--apply` will be the single public
authorization for Canvas writes, and retained evidence will distinguish plans,
attempts, verified results, unsafe uncertainty, and safe next actions.

The release also removes the separate best-effort discussion-grade uploader,
makes ordinary file-upload conflicts non-destructive by default, and gives
submission feedback the stop and evidence semantics expected of a multi-row
Canvas transaction.

Sprint 20 remains an alpha release. It does not claim the public-beta threshold
reserved for Sprint 21 / `0.18.0`.

## Program Context

Sprint 18 / `0.15.x` removed institution-specific runtime defaults and added
explicit instance profiles. Sprint 19 / `0.16.0` established the private
artifact boundary and bounded routine terminal output. Those releases are the
foundation for this sprint:

- instance and credential resolution still fails before Canvas access when it
  is incomplete;
- private destinations still resolve before authentication;
- plans and results containing student or grade data remain private;
- report manifest v2 remains the public provenance boundary; and
- existing grade-posting transactions retain rollback, readback, recovery, and
  release-state evidence.

This sprint changes operator authorization and selected result semantics. It
does not weaken the instance or privacy contracts to preserve compatibility.

## Verified Baseline

The `0.16.0` CLI contains 55 leaf commands. Twenty command functions expose a
`dry_run` parameter. Nineteen default it to `False`; only
`assignments overrides-sync` defaults to planning.

That numeric count is not the mutation inventory:

- 16 commands are capable of mutating Canvas;
- 13 of those mutate Canvas when invoked bare today;
- `assignments overrides-sync` already plans when invoked bare;
- `assignments upsert` requires an action-specific `--confirm` before it
  mutates, although its `dry_run` default is `False`;
- `discussions score` writes Canvas only with `--upload`; and
- four other commands use `--dry-run` only to control local file creation or
  download behavior.

The design must preserve those distinctions in tests and migration guidance.

## Access-Mode Inventory

Sprint 20 introduces a typed access-policy registry covering every Click leaf
command. A policy declares these independent axes:

- Canvas read;
- local retained write;
- Canvas mutation;
- destructive or removal-capable behavior;
- grade-affecting behavior;
- notification or student-visibility behavior; and
- authoritative verification/readback behavior.

The registry is operational metadata, not documentation-only duplication. CLI
architecture tests enumerate the real Click tree and require exact set equality
with the registry. A newly added or stale command therefore fails the gate.

The Sprint 19 output-policy test is strengthened in the same pass: it checks
both directions and detects positional retained-output paths, rather than only
known output option names.

### Local-only commands

These ten commands do not call Canvas. They may read or write local artifacts,
but they never gain `--apply`:

- `status`;
- `reports list` and `reports latest`;
- `assignments audit`;
- `gradebook check` and `gradebook audit`;
- `quiz analysis`;
- `sources lint`; and
- `pages render` and `pages css-check`.

### Canvas-read and retained-output commands

These 25 commands may read Canvas and write local snapshots, exports, reports,
or downloads, but they do not mutate Canvas and never gain `--apply`:

- `init`, `refresh`, `courses`, and `roster`;
- `auth doctor`, whose Canvas read remains conditional on `--check-canvas`;
- `assignments export`, `assignments overrides`, and `assignments verify`;
- `submissions export`, `submissions grades`, and `submissions media`;
- `grades comments` and `grades verify`;
- `discussions export` and `discussions verify`;
- `pages list`, `pages export`, and `pages verify`;
- `announcements export`, `announcements latest`, and
  `announcements verify`;
- `files inventory`, `files download`, `files download-one`, and
  `files compare`.

`init` and `refresh` write project state, and download/export commands write
retained content. Their existing no-clobber, private-output, and explicit
overwrite contracts remain separate from Canvas mutation authorization.

### Local-write `--dry-run` commands

These four commands use `--dry-run` to control local effects, not Canvas
mutation:

- `pages sync`;
- `announcements sync`;
- `discussions sync-prompts`; and
- `recordings panopto-captions`.

The three source-sync commands continue to read Canvas and write no-clobber
local sources when `--dry-run` is omitted. Panopto continues to write manifests
in dry-run mode and downloads private caption files only when dry-run is
omitted. None gains `--apply` in this sprint.

The help text and migration guide must label these as local-write modes so an
operator does not mistake omission for Canvas authorization.

### Canvas-mutation-capable commands

The remaining 16 commands are the complete mutation surface:

<!-- markdownlint-disable MD013 -->

| Command | Current live authorization | New `0.17.0` contract | Special risk/guard |
| --- | --- | --- | --- |
| `assignments overrides-sync` | `--live --confirm apply`; bare plans | bare/`--dry-run` plan; `--apply --confirm apply` writes | creates or updates membership and availability windows |
| `assignments create` | bare writes | bare/`--dry-run` plan; `--apply` writes | may upload assets and publish student-visible content |
| `assignments update` | bare writes | bare/`--dry-run` plan; `--apply` writes | may change visibility, schedule, and notification fields |
| `assignments upsert` | action-specific `--confirm` writes; bare fails | bare/`--dry-run` plan; `--apply` plus matching `--confirm` writes | confirmation must be `create` or `update` |
| `quiz import-qti` | bare imports | bare/`--dry-run` plan; `--apply` writes | creates a migration and may publish the imported quiz |
| `submissions feedback` | bare uploads | bare/`--dry-run` plan; `--apply` writes | student communication; stop/readback contract below |
| `grades post` | bare posts | bare/`--dry-run` preflight; `--apply` writes | grade-affecting; existing rollback/readback retained |
| `grades clear` | bare clears | bare/`--dry-run` preflight; `--apply` writes | destructive and grade-affecting; rollback remains required |
| `discussions create` | bare writes | bare/`--dry-run` plan; `--apply` writes | may create a graded, published topic and seed replies |
| `discussions update` | bare writes | bare/`--dry-run` plan; `--apply` writes | changes existing student-visible content |
| `pages create` | bare writes | bare/`--dry-run` plan; `--apply` writes | may publish a Page |
| `pages update` | bare writes | bare/`--dry-run` plan; `--apply` writes | may publish and notify users |
| `announcements create` | bare writes | bare/`--dry-run` plan; `--apply` writes | notification-bearing and schedule-sensitive |
| `announcements update` | bare writes | bare/`--dry-run` plan; `--apply` writes | edits notification-bearing content |
| `files upload` | bare uploads; duplicate default is overwrite | bare/`--dry-run` plan; `--apply` writes; duplicate default is error | explicit overwrite or rename remains available |
| `discussions score` | bare writes a plan; `--upload` writes grades | always writes only a private `grades post` plan | direct grade mutation is removed |

<!-- markdownlint-enable MD013 -->

No other command may acquire Canvas mutation behavior without adding a registry
entry, `--apply`, plan-by-default tests, migration documentation, and the
evidence fields required below.

## Mutation Authorization Contract

### Public vocabulary

Every Canvas-mutating command except the now-plan-only `discussions score`
uses one contract:

- omission means plan;
- `--dry-run` is an explicit compatibility spelling for plan;
- `--apply` authorizes Canvas writes; and
- `--dry-run --apply` is an error before authentication or retained output.

Plans may perform documented Canvas reads needed to resolve identity, compare
state, or validate a target. Commands that already support an offline plan keep
that property. A plan may write its documented report or private artifact, but
never Canvas state.

`--apply` authorizes only the mutation represented by the plan produced in that
invocation. It does not imply overwrite, deletion, publication, title matching,
or action selection beyond options the operator supplied explicitly.

The mutation banner prints only after all plan blockers and target guards pass
and immediately before the first Canvas write. It is not itself authorization.

### Typed implementation boundary

Introduce a small typed mutation module rather than duplicating Boolean
interpretation in 15 command implementations. It owns:

- a `MutationMode` enum with `plan` and `apply`;
- validation of `--dry-run`, `--apply`, and temporary legacy aliases;
- common help wording;
- a pre-write assertion called immediately before Canvas mutation; and
- policy lookup for architecture and command-surface tests.

The existing implementation functions may continue receiving a normalized
mode or a compatibility `dry_run` Boolean during migration, but raw CLI flags
must be resolved once at the adapter boundary. No function may infer apply mode
from omission.

### Additional guards

Action-specific guards remain additive:

- assignment upsert requires `--apply --confirm create` or
  `--apply --confirm update`, matching the planned action;
- override synchronization requires `--apply --confirm apply`;
- grade clear retains exact row targeting, expected-state checks, and private
  rollback preflight;
- grade post retains expected title/current-grade/comment guards; and
- file overwrite or rename requires an explicit `--on-duplicate` value in
  addition to `--apply`.

Supplying `--confirm` without `--apply` fails with an actionable message rather
than exiting successfully after a plan. This prevents old automation from
mistaking a newly safe run for a completed mutation.

### Legacy option handling

`assignments overrides-sync --live` remains a deprecated alias for `--apply`
through `0.17.x`. It prints a warning to stderr, still requires
`--confirm apply`, and cannot combine with `--apply` or `--dry-run`. It is
removed in `0.18.0` before the beta claim.

All other current mutation commands already expose `--dry-run`; no inverse
`--live` spelling is added to them.

`discussions score --upload` never mutates Canvas in `0.17.0`. It generates the
same private grade plan as omission, then exits nonzero with the replacement
`grades post` command. A nonzero exit is intentional: old automation must not
interpret plan generation as a successful grade upload. The option may be
removed in `0.18.0` after one migration release.

`discussions score --dry-run` remains an explicit, harmless spelling for its
only behavior: generate the private plan without mutating Canvas. It exits `0`
when the plan is ready and does not emit a deprecation warning.
`--sleep-seconds` is removed from this command in `0.17.0`, because pacing
belonged only to the removed direct uploader; retaining an inert option would
make the help surface untruthful. Pacing for the generated plan is supplied to
the subsequent `grades post` command instead.

## Plan Contract

Every plan records enough information to review the proposed action and to
distinguish a valid plan from a blocker. The common envelope contains:

- command and evidence schema version;
- mode `plan`;
- resolved course and stable target identifiers;
- sanitized, project-relative input provenance where applicable;
- intended action count and a stable per-action key;
- relevant before/intended values or an explicit statement that no remote
  before-state is available;
- blockers, warnings, visibility/notification effects, and duplicate policy;
- the private or course-internal artifact classification; and
- the exact next command as an argument array or bounded template without
  tokens or secret values.

Plans that contain student, grade, feedback, or membership data remain under
the Sprint 19 private boundary. Routine stdout remains aggregate and prints at
most the bounded artifact root.

Plan status and exit behavior are:

- `ready`: complete plan with no blockers, exit 0;
- `no_change`: verified no-op, exit 0;
- `blocked`: conflict, ambiguous identity, stale expectation, or unsafe target,
  exit nonzero; and
- `failed`: plan could not be completed reliably, exit nonzero.

The exact numeric nonzero code remains compatible with existing command-family
behavior in `0.17.0`; standardizing all CLI exit codes is a later interface
decision.

## Result And Evidence Contract

An apply run preserves the plan and records each intended mutation exactly
once using a stable action key. The common result vocabulary is:

- `not_attempted`;
- `applied_verified`;
- `already_applied`;
- `rejected`;
- `failed_before_acceptance`;
- `accepted_unverified`; and
- `skipped_after_stop`.

Command families may retain richer typed states already accepted in Sprint 17,
but their public reports must map unambiguously to these meanings.

Evidence distinguishes:

1. intended plan;
2. mutation attempt;
3. Canvas response or exception;
4. authoritative readback when available;
5. final classification; and
6. a safe next action.

An exception after sending a request is not proof that Canvas rejected it.
`accepted_unverified` is unsafe to retry blindly. Dependent writes stop after a
rejected, failed, or uncertain action unless an existing stronger transaction
contract proves continuation safe.

Raw exception text is sanitized before stdout or retained evidence. Private
evidence may retain stable student and object IDs needed for recovery, but not
tokens, signed URLs, or unsanitized transport payloads.

## Notification And Visibility Review

Plans for assignments, quizzes, discussions, Pages, and announcements must
display every supplied field that can change student visibility, schedule, or
notification behavior. At minimum this includes fields such as `published`,
`notify_of_update`, delayed posting, availability windows, and assignment
publication when supported by that source type.

Omitted fields are reported as omitted or preserved rather than silently
projected as false. Apply evidence records the intended value and readback value
when the Canvas API exposes one.

## File Upload Conflict Safety

`files upload --on-duplicate` adds `error` and makes it the default. The plan
lists the destination folder and classifies each file as ready or conflict.
Known conflicts block before the mutation banner.

Explicit `--on-duplicate overwrite` and `--on-duplicate rename` remain
available only with `--apply`. The report records the requested and observed
outcome separately.

Canvas exposes overwrite/rename transport behavior rather than a conditional
create primitive. To keep an `error` policy non-destructive under a race, the
implementation must:

1. re-list and compare the destination immediately before upload;
2. block if the intended name exists;
3. use the non-overwriting rename transport behavior for the final request;
4. verify the returned name and stable file identity; and
5. classify a race-created renamed file as a conflict requiring manual review,
   never as successful application of the requested plan.

This rule may leave a newly uploaded, renamed file in the narrow race case, but
it never overwrites the pre-existing object. Evidence must name that limitation
and must not recommend a blind retry. Deleting the race artifact automatically
is out of scope because deletion would introduce a new destructive operation.

Asset-integrated assignment workflows keep their existing `error`/`rename`
asset policy and verified provenance rules.

## Discussion Scoring Reconciliation

`discussions score` becomes a calculation and plan-generation command only. It
resolves the graded discussion's assignment, reads current submission grades,
and writes a private CSV directly accepted by `grades post`.

The CSV uses the established grade schema:

- `CanvasID`;
- `Name`;
- `Grade`;
- `ExpectedCurrentGrade`;
- `Comment`;
- `CommentAction`, set to `append`; and
- any bounded scoring-count columns retained for human review.

The artifact sidecar records the course, discussion, assignment, assignment
title, scoring parameters, and file digest. It also records argument arrays for
the next steps, equivalent to:

```bash
danvas grades post ASSIGNMENT_ID \
  --grades-csv .danvas/private/discussions/topic-TOPIC_ID/grade-plan.csv \
  --expected-assignment-title "EXPECTED TITLE"

danvas grades post ASSIGNMENT_ID \
  --grades-csv .danvas/private/discussions/topic-TOPIC_ID/grade-plan.csv \
  --expected-assignment-title "EXPECTED TITLE" \
  --apply
```

The first command preflights through the established grade transaction. The
second explicitly applies it. `discussions score` no longer owns grade writes,
sleep/retry behavior, rollback, or readback logic.

## Submission Feedback Transaction

Bare `submissions feedback` and explicit `--dry-run` retain the current local
matching plan and write `feedback-plan.json`. `--apply` writes the distinct
`feedback-results.json` artifact established in the `0.16.0` correction.

Before the first Canvas write, apply mode validates all roster IDs, file
matches, readable files, file hashes, the assignment target, and the private
result destination. The plan records unmatched files as blockers unless the
operator narrows the source pattern so only intended files remain.

For each matched student, apply mode:

1. records an intended action keyed by Canvas user ID and feedback-file digest;
2. uploads the comment and attachment;
3. performs fresh submission-comment readback;
4. classifies the comment/attachment as verified, rejected, failed before
   acceptance, or accepted but unverified; and
5. atomically checkpoints the private result after each row.

The command stops on the first rejected, failed, or uncertain action. Remaining
rows become `skipped_after_stop`. It does not add `--continue-on-error` in this
sprint. Canvas does not provide a sufficiently general rollback for posted
submission comments, so evidence and a safe manual recovery boundary are more
truthful than pretending the batch is atomic.

A rerun never assumes an exception means no comment was created. Existing exact
comments and attachment metadata are reviewed during preflight; ambiguous
remote state blocks with a manual-review instruction.

## Adjacent Hardening Included

Two small findings from the Sprint 18/19 reviews align with the inventory work
and are included without broadening product behavior:

- make `secret_name` required at internal `resolve_api_key` call sites and add
  an architecture test restricting those direct call sites; and
- warn when an explicitly selected profile's API URL disagrees with the
  higher-precedence project URL, while continuing to honor the accepted
  precedence order.

The access/output registry tests also gain the reverse-direction and positional
output checks described above.

## Compatibility And Migration

`0.17.0` is intentionally behavior-changing. The migration guide contains a
command-by-command table matching the 16-command mutation inventory, including:

- old bare behavior;
- new bare plan behavior;
- exact `--apply` spelling;
- any retained `--confirm` guard;
- visibility or notification fields shown in the plan;
- compatibility alias lifetime; and
- result evidence and safe retry guidance.

The guide leads with the thirteen commands whose bare invocation changes from
Canvas mutation to planning. It separately explains override sync, assignment
upsert, discussion scoring, and all four local-write dry-run commands.

The override-sync row must show that `--confirm apply` without `--live` changes
from a successful planning invocation in `0.16.0` to an actionable nonzero
error without `--apply` in `0.17.0`. The upsert row must likewise show that
either `--confirm create` or `--confirm update` without `--apply` exits nonzero.
The feedback row names unmatched files becoming blockers rather than the
`0.16.0` behavior of reporting them and continuing.

Automation migration examples must treat a successful plan as a plan, not a
successful mutation. Scripts that intend writes add `--apply` and verify the
result artifact/status rather than relying only on process exit.

The guide includes an explicit shell-automation example for
`discussions score --upload`: its new nonzero exit means "grade plan generated;
direct upload removed," not plan-generation failure. The replacement workflow
checks the generated artifact, runs `grades post` to preflight it, and invokes
`grades post --apply` only after review.

One residual risk is accepted deliberately: a legacy script that invokes one of
the thirteen flipped commands bare will now plan and exit `0`, so automation
that checks only the exit code sees success without the mutation it intended.
That failure direction is a safe no-op rather than an unauthorized write, and
the migration guide must state it explicitly rather than leave it implied.

No compatibility mode, environment variable, project configuration, or profile
may globally restore mutation-on-omission.

## Implementation Sequence

### Group 1: inventory and characterization

1. Add the typed access-policy registry for all 55 leaf commands.
2. Strengthen access and retained-output architecture tests to exact equality.
3. Add CLI characterization tests for all 20 current `dry_run` commands and all
   16 Canvas mutation entry points before changing defaults.
4. Add an AST/source-scan architecture test that inventories Canvas mutation
   primitives and raw upload POSTs by exact call site. Every site must be an
   allowlisted wrapper or be dominated by the common pre-write assertion; stale
   and newly unclassified call sites fail the gate.
5. Pin the current additional guards, local-write behavior, and legacy options,
   including both upsert confirmation values without apply.

This group is a gate: no default flips until the independent inventory can
detect an omitted command.

### Group 2: shared mode and content commands

1. Add `MutationMode`, common options, conflict validation, and the final
   pre-write assertion.
2. Migrate assignment create/update/upsert and override sync.
3. Migrate discussion, Page, and announcement create/update.
4. Make plan evidence include visibility and notification fields.

### Group 3: grade and import commands

1. Migrate QTI import, grade post, and grade clear to plan-by-default.
2. Preserve existing grade rollback, readback, and recovery semantics.
3. Replace discussion direct upload with the private `grades post` plan.
4. Add migration-safe handling of `--upload`, `--live`, and `--confirm`.

### Group 4: feedback and file conflicts

1. Migrate submission feedback to `--apply`, per-row checkpointing, readback,
   and stop-on-unsafe behavior.
2. Add the file-upload `error` default and race-safe non-overwrite transport.
3. Add the adjacent auth and registry hardening.

### Group 5: documentation and release

1. Publish `docs/migrations/0.17.0.md` with the complete migration table.
2. Update help, README examples, the sprint index, backlog, and durable context.
3. Run the full local release gate and independent operator-safety review.
4. Perform only the bounded live acceptance authorized below.
5. Tag `v0.17.0` only after exact-commit branch and tag CI pass.

Each group lands as a logical commit and keeps the tree reviewable. Review
findings may add focused corrections but must not pull Sprint 21 generalization
or Sprint 22 agent-interface work into this release.

## Test Matrix

### Architecture

- The Click tree and access-policy registry contain exactly the same 55 leaf
  commands.
- The retained-output registry has no missing or stale entries and detects
  positional retained destinations.
- Exactly the 15 remaining Canvas-writing commands expose `--apply` and
  `--dry-run`; no local-only, read-only, sync, download, or scoring command
  exposes `--apply`.
- Every runtime Canvas write passes the common pre-write assertion.
- A source-scan inventory covers CanvasAPI create/edit/upload mutation methods,
  nested asset uploads, and raw upload-URL POSTs; its exact call-site set cannot
  gain or lose an entry silently.
- Direct `resolve_api_key` call sites are bounded and always pass
  `secret_name` explicitly.

### Default safety

- Bare invocation of every mutation-capable command performs zero Canvas
  writes.
- Explicit `--dry-run` performs zero Canvas writes.
- `--apply --dry-run` fails before auth and output.
- `--confirm` without `--apply` never mutates and exits nonzero.
- Upsert tests cover both `--confirm create` and `--confirm update` without
  `--apply`; override sync covers `--confirm apply` without `--apply`.
- The override `--live` alias cannot bypass confirmation or combine with the
  new flags.
- All four local-write dry-run commands retain their `0.16.0` behavior and do
  not expose `--apply`.

### Mutation and evidence

- Each apply test proves exactly one intended write and one stable evidence
  action per target.
- Readback success, rejection, pre-acceptance failure, and acceptance
  uncertainty map to distinct states and next actions.
- An unsafe row stops dependent feedback writes and checkpoints skipped rows.
- Mutation banners never appear during planning and always precede the first
  apply write.
- Retained errors and stdout remain sanitized under token, URL, student, and
  raw-exception fixtures.

### Command-specific behavior

- File upload blocks known duplicates by default and never passes overwrite to
  Canvas for an `error` policy.
- A simulated duplicate race cannot overwrite an existing Canvas file and is
  reported as a renamed conflict requiring review.
- Discussion scoring emits a `grades post`-compatible private CSV with expected
  current grades and never calls a grade mutation method.
- `--upload` creates the plan, exits nonzero, and prints the replacement command
  without private row data.
- Discussion `--dry-run` remains a successful explicit plan spelling, while
  removed `--sleep-seconds` is rejected by command parsing.
- Feedback dry-run then apply uses distinct no-clobber artifacts, reads back
  each attempted row, and stops after the first unsafe outcome.
- Notification-bearing plans show all supplied visibility, schedule, and
  notification fields.

### Regression and release

- Sprint 18 profile/credential precedence and offline doctor behavior remain
  unchanged except for the explicit mismatch warning.
- Sprint 19 private paths, permissions, terminal disclosure, and manifest v2
  remain unchanged.
- Ruff, ty, frozen Python 3.12 and 3.14 tests, coverage and complexity ratchets,
  dependency audit, Markdown checks, build, and editable/wheel smoke pass on
  one exact commit.

## Bounded Live Acceptance

Most Sprint 20 changes are authorization gates around already accepted Canvas
payloads and are covered without live mutation. Before release, a disposable
course probe is required only for changed Canvas-observable semantics that
cannot be established by fixtures:

- upload one disposable file, verify the default conflict blocks, explicitly
  exercise rename, and confirm an existing file is never overwritten; and
- post one disposable feedback comment/attachment to a test submission, verify
  readback classification, then inspect the private result evidence.

The probe requires separate explicit authorization, uses no production student
data, records created object IDs, and cleans up only objects it created when the
API supports safe cleanup. No other live Canvas mutation is implied by design
acceptance or implementation.

The authorized probes passed on 2026-08-13 in sandbox course 1576638. The file
probe confirmed that omission plans, the default `error` policy blocks a known
duplicate, and explicit `rename` creates a distinct Canvas file without changing
the original. Independent inventory readback confirmed both identities and
sizes before exact-ID cleanup; both files were then confirmed absent.

The first feedback attempt correctly stopped as `accepted_unverified`: Canvas
stored the attachment but used its default attachment-only comment text. Field
inspection established that CanvasAPI's `Submission.upload_comment()` ignores
the supplied text during its upload-token request, then creates an
attachment-only comment. The focused `b3893aa` correction now follows Canvas's
documented two-stage contract: upload through the Submission Comments file
endpoint, then attach that returned file ID with `comment[text_comment]` in one
submission edit. Tests model both write boundaries, and the architecture gate
requires a pre-write assertion before each. After exact cleanup of the first
attempt, the corrected probe returned `applied_verified`, with accepted response
and verified readback for the exact comment text, attachment ID, filename, and
size. The exact corrected comment and attachment were then confirmed absent.

## Acceptance Criteria

Sprint 20 is complete only when all of the following are true:

- [x] Every leaf command has a reviewed, exact access-policy declaration.
- [x] Every Canvas-mutating command plans on omission and requires `--apply`.
- [x] Local-write dry-run commands retain their distinct contract and never
  gain `--apply`.
- [x] Legacy aliases cannot bypass the new boundary and have documented removal
  versions.
- [x] Plans expose target, action, blockers, visibility/notification effects,
  and a safe apply command without secret or private terminal leakage.
- [x] Apply evidence distinguishes intention, attempt, response, readback,
  classification, and safe next action.
- [x] File upload defaults to conflict error and cannot overwrite under that
  policy.
- [x] Discussion scoring no longer writes grades and emits an exact
  `grades post` plan.
- [x] Submission feedback checkpoints per-row evidence, reads back outcomes,
  and stops after unsafe or uncertain results.
- [x] Grade post/clear retain their rollback, recovery, and release-state
  guarantees under the new mode.
- [x] Required `secret_name`, URL/profile mismatch warning, and strengthened
  architecture tests are complete.
- [x] The `0.17.0` migration guide enumerates all mutation and local-write mode
  changes command by command.
- [x] The authorized bounded live probes pass without production data.
- [ ] Independent review accepts the implementation and exact-commit local,
  branch, and tag gates pass before release.

## Non-Goals

- Renaming local sync `--dry-run` to `--write-local`;
- adding a global compatibility switch that restores live-on-omission;
- extracting a new shared grade transaction engine for discussion scoring;
- adding automatic feedback rollback or continue-on-error behavior;
- adding Canvas file deletion to clean up a duplicate race;
- resolving interrupted Panopto bundle restart policy, which remains a separate
  private-artifact maintenance decision;
- validating explicit init timezones before network access, owned by Sprint 21;
- generalizing course layouts, gradebook locale aliases, packaging, CI
  platforms, or public-beta documentation owned by Sprint 21;
- implementing the Sprint 22 help and skill installer design;
- rewriting the large CLI module solely for style; or
- performing live Canvas mutation without the bounded acceptance authorization
  above.

## Review Focus

Independent review should challenge these questions before acceptance:

1. Does the 55-command inventory match the actual Click tree without relying on
   a manually mirrored subset?
2. Can any legacy flag, confirmation path, direct helper call, or nested asset
   operation mutate Canvas without `--apply`?
3. Can old automation exit successfully without performing the mutation it
   intended, especially for upsert, override sync, or discussion upload?
4. Does every notification-bearing plan show the exact field values that can
   make content visible or alert students?
5. Is file upload genuinely non-overwriting under known conflicts and races,
   and is the renamed-race limitation stated honestly?
6. Can feedback evidence distinguish rejected from possibly accepted requests
   and prevent a blind duplicate retry?
7. Does discussion scoring produce a grade plan that the existing transaction
   consumes without schema translation or loss of expected-state guards?
8. Do plan/result artifacts continue to satisfy the Sprint 19 privacy boundary
   on success, failure, interruption, and explicit-output paths?
9. Are the two bounded live probes necessary and sufficient for the semantics
   that fixtures cannot prove?
