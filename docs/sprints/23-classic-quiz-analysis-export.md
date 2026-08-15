# Sprint 23: Classic Quiz Student-Analysis Export

Status: released as signed tag `v0.21.0` on 2026-08-14 from `0953757` after
independent design, focused implementation, field, agent-behavior, and final
exact-candidate review.
Groups 0-2 are implemented in `62db183`, `99a04af`, and `fa04445`; the reusable
agent-acceptance rig was reviewed and committed separately as `f27d113`.
Group 3 assembled the `0.21.0` candidate with public workflow/migration
documentation. The local gate passed 1,046 tests at 85.57% branch-aware
coverage, Ruff, ty, Markdown/docs checks, isolated editable/wheel installation,
dependency audit, lock validation, and redacted current-tree/all-history secret
scans. Bounded Canvas field acceptance passed on 2026-08-14 after its first
download attempt exposed and corrected a global-versus-course file-lookup
defect in `25f8ae4`. Claude Code scenario-11 agent acceptance also passed on
2026-08-14. Independent final review accepted exact candidate `6640ae6`; the
scored agent record landed at `0953757`. Branch CI run `31851275738`, signed-tag
CI run `31851556017`, anonymous exact-SHA/tag installs, and global verification
as `danvas 0.21.0` all passed.

Subsequent separately authorized distribution work published the verified
wheel, source distribution, and checksum manifest in the
[`v0.21.0` GitHub prerelease](https://github.com/olearydj/danvas/releases/tag/v0.21.0).
The first PyPI dispatch from `main` (`31852342632`) verified the artifacts but
correctly stopped before publication because the protected `pypi` environment
allows only `v*` tag deployments. Tag-scoped Trusted Publishing run
`31852406840` then published those exact files as
[`danvas-cli 0.21.0`](https://pypi.org/project/danvas-cli/0.21.0/).

The dated publication check on 2026-08-14 America/Chicago (2026-08-15 UTC)
verified:

- PyPI metadata reports version `0.21.0`; the wheel and source distribution
  were uploaded at `2026-08-15T00:04:12.009322Z` and
  `2026-08-15T00:04:13.431701Z`;
- the published SHA-256 digests are
  `27163bacd06649bd1b5ea9eb47653da0c383fd19f3fcb25e34c865e80ab92341`
  for the wheel and
  `6d9b4eb6c111a390b0ba21bacca7c05f13220e5e61c19f32a3e2c1d21feb0e4a`
  for the source distribution, exactly matching the GitHub Release assets and
  `SHA256SUMS`;
- PyPI's Integrity API identifies both publishers as GitHub repository
  `olearydj/danvas`, workflow `publish-pypi.yml`, environment `pypi`;
- `pypi-attestations verify pypi --repository
  https://github.com/olearydj/danvas` cryptographically verified both files;
  and
- a fresh-cache installation from the official PyPI index reported
  `danvas 0.21.0` and passed the offline quiz help, command description, and
  packaged-skill checks.

## Outcome

Add one supported Danvas workflow for acquiring the official Canvas Classic
Quiz or identified Survey `student_analysis` CSV:

```bash
danvas quiz export-analysis --course-id 101 --quiz-id 202
danvas quiz export-analysis --course-id 101 --quiz-id 202 --apply
danvas quiz analysis \
  .danvas/private/quizzes/quiz-202/student-analysis.csv \
  --answer-term "case"
```

The first command plans and may perform bounded Canvas reads. It does not
request a report or download a file. `--apply` authorizes the Canvas report
request, bounded progress polling, authoritative readback, and private CSV
download.

The downloaded CSV becomes the input to the existing local-only
`danvas quiz analysis` command. Acquisition does not automatically summarize,
filter, publish, or echo student answers.

This closes a recurring field gap. Agents can currently discover that Danvas
parses a student-analysis CSV but cannot obtain one. Several real workflows
have therefore reached for browser exports or direct Canvas API scripts. The
supported command must replace that escape hatch while preserving Danvas's
mutation, privacy, and evidence boundaries.

## Why This Is The Next Slice

The cleaned backlog placed Page asset deployment first because it was the most
mature named follow-on after public readiness. Repeated course work has since
demonstrated a narrower and more immediate gap: operators need Classic Quiz
answer analysis, the parser already exists, but the required Canvas export must
be acquired out of band.

The latest occurrence also exposed an agent-safety defect. After correctly
discovering that the installed CLI lacked the acquisition command, an agent
proposed a "read-only" direct call to the Classic Quiz report endpoint and a
private raw JSON response. That fallback was not truthful:

- creating or reusing a Classic Quiz report uses a Canvas `POST`;
- returned report and file payloads may contain protected, signed, or
  verifier-bearing URLs; and
- absence of a Danvas command does not authorize an agent to bypass Danvas's
  reviewed access and evidence contracts.

Sprint 23 therefore precedes the Page adapter. It adds only the missing report
acquisition boundary and the guidance needed to prevent direct-API fallback.
The Page adapter remains the next major feature candidate after this sprint.

## Verified Baseline

The released `0.20.0` tree has two `quiz` leaves:

- `quiz analysis` reads a local Canvas Classic Quiz or Survey student-analysis
  CSV, summarizes rows and score fields, and can count answers matching
  operator-supplied question terms;
- `quiz import-qti` plans or applies a Classic Quiz QTI import and verifies the
  created object.

`quiz analysis` is local-only, may write private JSON, and performs no Canvas
authentication. Its implementation in `danvas.quiz.StudentAnalysisReport`
already owns CSV decoding, question/score-pair discovery, row normalization,
and answer selection. This sprint reuses that parser and does not replace its
analysis schema.

There is no command that lists, requests, waits for, or downloads a Classic
Quiz report. Completion and submission exports do not contain the per-question
answer columns required by `StudentAnalysisReport`.

The current registries enumerate sixty leaf commands. Fifteen can mutate
Canvas, none mutates when invoked bare, and `--apply` is exactly the Canvas
mutation surface. `quiz analysis` is classified as a local-write command with a
private artifact. The new leaf must extend those existing registries rather
than introduce a parallel access or privacy vocabulary.

Sprint 19's private-artifact module already supplies the required local
filesystem primitives: project-relative destination resolution before
authentication; `0700` directories and `0600` files from creation; no-clobber
preflight and explicit overwrite; private staged files; and data-first,
SHA-bearing sidecar-last commits whose torn state is detectable.

The installed CanvasAPI client exposes Classic Quiz report creation, listing,
readback, progress polling, and file access. Its report convenience method
supports the ordinary `report_type` request. Supporting the nested
`includes_all_versions` parameter may require one narrow requester wrapper
because the installed convenience method constructs the `quiz_report` mapping
itself. Any such raw `POST` remains inside the reviewed Danvas module and must
enter the mutation-call and pre-write-assertion architecture inventories.

## Canvas API Semantics

The official Canvas Classic Quiz Reports API defines:

- `GET /api/v1/courses/:course_id/quizzes/:quiz_id/reports` to list reports;
- `POST /api/v1/courses/:course_id/quizzes/:quiz_id/reports` to create a
  report, or return the current matching report when Canvas can reuse it;
- `GET /api/v1/courses/:course_id/quizzes/:quiz_id/reports/:id` for
  authoritative report readback;
- `student_analysis` and `item_analysis` report types; and
- an `includes_all_versions` request field.

Report generation may be asynchronous. A report can carry progress identity
while queued or running and a Canvas file after completion. Canvas may return
`409 Conflict` while an equivalent report is already being generated.

The API also exposes report deletion or abortion. Sprint 23 does not use it.
Report creation is an operational Canvas mutation even though it does not
change quiz questions, submissions, or grades. The possibility that Canvas
reuses an existing current report does not make the request read-only: the same
`POST` may create server-side state.

New Quizzes has a separate Reports API and different resource model. Classic
Quiz support must not be presented as New Quiz support.

## Command Contract

The new leaf is `danvas quiz export-analysis`.

Required options are `--course-id INTEGER`, `--quiz-id INTEGER`, and the
provider-neutral Canvas origin and credential options shared by all
Canvas-backed commands.

Workflow options:

- `--includes-all-versions` requests Canvas's all-versions form; omission
  requests the current quiz version only;
- `--output PATH` selects the CSV path;
- `--overwrite` authorizes replacement of an existing valid private data and
  sidecar pair;
- `--timeout-seconds FLOAT` bounds total progress polling;
- `--poll-seconds FLOAT` sets a positive bounded polling interval;
- `--dry-run` is the explicit spelling for plan mode;
- `--apply` authorizes the report `POST` and download workflow; and
- the standard report-run options retain private plan/result evidence.

The implementation uses repository-wide option types and validators rather
than command-local authentication or mutation flags.

The candidate defaults are a two-second polling interval and a 120-second total
timeout. Operators may change either within the validated positive bounds. The
defaults are part of the Group 0 interface fixture and may change only through
reviewed evidence that the deployed Canvas job regularly needs a different
bound.

### Anonymous surveys

Sprint 23 supports Classic Quizzes and Surveys only when the student-analysis
CSV has the ordinary identified schema. Canvas may omit identity columns from
anonymous Survey reports, which is incompatible with the `id` plus `submitted`
minimum signature used for acquired files in this slice.

When authoritative quiz metadata identifies `quiz_type` as `survey` or
`graded_survey` and `anonymous_submissions` is true, planning exits nonzero with
a clear unsupported-anonymous-survey diagnostic before the report `POST`. If
the anonymity field is absent or ambiguous for a Survey, acquisition fails
closed rather than risking an accidental request followed by CSV rejection.

This does not narrow the existing local parser. An operator who already has an
anonymous Survey CSV may still pass it to `quiz analysis` when that parser
accepts its Canvas-provided shape. Supporting anonymous acquisition requires a
separate fixture-backed schema and is not inferred from missing columns.

### Default destination

Inside an initialized project, the default is:

```text
.danvas/private/quizzes/quiz-<quiz-id>/student-analysis.csv
```

Its integrity sidecar is `student-analysis.csv.artifact.json`.

Outside a project, `--output` is required. The output and sidecar paths are
resolved, contained, and preflighted before project configuration, Canvas
origin resolution, credential access, or network calls. A conflict therefore
cannot cause a credential read.

Numeric Canvas quiz IDs are allowed default path components. Quiz titles,
course names, user names, login IDs, question text, and answers are not.

### Plan mode

Omitting both mode flags plans. `--dry-run` is an equivalent explicit spelling.
Plan mode may resolve and validate the private destination, read stable quiz
metadata, list existing report metadata, identify whether no/one/multiple
matching current or in-progress reports are visible, and retain a private plan
receipt.

Plan mode must not call the report-creation `POST`, poll beyond the reads needed
to describe current state, download a file, write the target CSV or sidecar, or
follow a protected file URL.

The plan reports stable IDs, requested report type and version scope, current
report availability, destination root, and next command. It does not retain
Canvas response bodies or URLs.

### Apply mode

`--apply` is the sole authorization for the Canvas report request. Immediately
before every creation call, the implementation invokes the common pre-write
assertion with apply mode. A lower-level assertion is also required if a raw
requester wrapper is used.

Apply mode:

1. repeats destination preflight;
2. reads the quiz and current report inventory;
3. establishes the requested report identity;
4. invokes the create-or-reuse request at most once;
5. reconciles the response or uncertain outcome to a stable report ID;
6. polls one verified progress identity until completion, failure, or timeout;
7. refetches the report authoritatively;
8. resolves one stable Canvas file ID;
9. downloads into a private staging file;
10. validates the staged CSV shape;
11. commits the CSV and integrity sidecar; and
12. retains a private result receipt and prints an aggregate summary.

No configuration option may restore mutation on omission.

## Report Identity And Reconciliation

A matching report has the requested course ID, Classic Quiz ID,
`report_type = student_analysis`, and `includes_all_versions` value. An absent
API value may mean Canvas's documented default only when fixtures establish
that equivalence. Report title, file name, creation timestamp, or URL alone is
not identity.

### Pre-existing reports

An existing completed report may be recorded in the plan, but apply still
performs the official create-or-reuse request. This keeps freshness semantics
under Canvas's authority. Danvas does not invent an age threshold or silently
download whichever prior report looks newest.

If the request returns a stable matching report ID, that ID becomes the sole
report for polling and readback. Whether Canvas created or reused it is retained
when the API proves the distinction; Danvas does not infer creation.

### `409 Conflict`

The command never resolves `409` by immediately repeating the `POST`. It
refreshes the read-only report inventory and may continue only when exactly one
matching in-progress report with stable report and progress identity can be
established. Zero matches or multiple plausible matches produce `conflict`,
retain bounded evidence, write no CSV, and instruct the operator to plan later.

### Exception after request

A timeout or transport exception after the request may conceal an accepted
mutation. The command does not blindly retry. It refreshes report inventory
once. If exactly one matching report can be bound without guesswork, processing
may continue from that ID and the receipt records `unknown_after_exception`.
If exact binding is impossible, the overall result is `accepted_unverified`.
The safe next action is to rerun the plan or inspect the retained receipt, not
to reissue `--apply`.

## Progress Contract

Progress polling is bounded by both `--timeout-seconds` and `--poll-seconds`.
Both values must be finite and positive; the interval cannot exceed the
timeout. Defaults are conservative and tested rather than copied from an
unrelated asynchronous API.

Danvas follows progress by stable numeric ID. If Canvas returns an absolute
`progress_url`, the implementation validates the configured Canvas origin and
expected progress path, extracts the numeric ID, and calls the client's stable
progress method. It does not retain or repeatedly request an arbitrary URL.

Completed and failed are recognized terminal states. Queued and running are
non-terminal. Unknown states, absent progress identity before a file exists,
or malformed progress data fail closed. Timeout is indeterminate, not evidence
that Canvas rejected the request; its receipt instructs verify before retry.

## Download And Verification Contract

The report is refetched after completed progress. The authoritative report must
still match course, quiz, type, and version scope and expose one positive
numeric Canvas file ID.

Danvas resolves the current Canvas file object by stable ID. A returned
download URL is transport data only. It may be used through the established
authenticated Canvas file transport, but it is never printed, placed in a
sidecar, written to a receipt, or included in an exception. Redirect/content
limits follow the reviewed file-transport policy, and failures are sanitized.

The download writes directly to a `0600` private staging file. No permissive
partial exists. A pre-existing staging path is refused, never unlinked.

Before commit, `StudentAnalysisReport` parses the staging file using its
existing UTF-8/BOM handling. The file must have a header row containing at
least the Canvas student-analysis `id` and `submitted` fields. A report with no
student rows or no discovered question pairs may still be valid; those states
are recorded as counts rather than called corruption.

The command does not parse JSON into a homemade CSV and does not reconstruct
answers from per-submission endpoints. Canvas's export remains authoritative.

The sidecar records only artifact schema/class, command and Danvas version,
course/quiz/report/progress/file IDs, report type, version scope, byte and
row/question counts, completion timestamp, and SHA-256. It never records
titles, student data, question text, answers, Canvas-received file names, raw
payloads, URLs, headers, credentials, or absolute project paths.

The sidecar commits last. Missing or mismatched sidecar means invalid. Explicit
overwrite uses the existing staged-pair transaction and may replace only a
regular private pair. Failure remains detectably inconsistent; the command
does not claim restoration it cannot prove.

## Result Evidence And Exit Status

The private result receipt separates transport facts from settled conclusions:

```text
request_status:
  not_attempted | accepted | reused | unknown_after_exception | conflict
progress_status:
  not_checked | queued | running | completed | failed | timed_out | unavailable
download_status:
  not_attempted | downloaded_verified | failed | accepted_unverified
overall_status:
  planned | applied_verified | accepted_unverified | conflict | failed
```

The exact JSON schema is versioned and fixture-pinned in Group 0. States may be
narrowed during characterization but may not collapse uncertain acceptance into
failure or success.

Exit zero means a valid plan or an `applied_verified` private CSV pair.
`accepted_unverified`, conflict, generation failure, timeout, download failure,
invalid CSV, and output collision exit nonzero. A nonzero exit after possible
acceptance never recommends immediate retry.

Terminal output is aggregate-only: mode; stable non-user object IDs; settled
states; row/question counts after verified download; bounded artifact root; and
safe next action. It never shows student names, login IDs, Canvas user IDs,
answers, scores, question text, Canvas file names, URLs, or raw exceptions.

## Access, Artifact, And Guide Registries

The new leaf extends the existing authorities:

- `ACCESS_POLICIES` declares Canvas read, Canvas mutation capability, private
  local write, mutation planning, and authoritative verification;
- `ARTIFACT_POLICIES` classifies CSV, sidecar, plan, and result as private; and
- `COMMAND_GUIDES` adds purpose, requirements, plan/apply sequence, identity,
  outputs, recovery, anonymous-survey exclusion, and its relationship to
  `quiz analysis`.

No effects or sensitivity field is duplicated in the guide layer. `describe`
serializes the real registry values.

After registration, the expected surface is sixty-one leaves and sixteen
mutation-capable commands, still with zero bare mutators. These are
characterization expectations, not hard-coded product claims; exact tree tests
remain authoritative.

The mutation-call and common-assertion scans must recognize the report `POST`.
Whether implemented through `create_report` or a narrow raw requester, the call
and its pre-write assertion enter the independently reviewed inventories.

## Help, Guides, And Agent Behavior

Root and quiz-family help make the two-step workflow discoverable: acquire the
private official CSV through `quiz export-analysis`, then inspect or summarize
it locally through `quiz analysis`.

Leaf help states that report generation is a Canvas mutation requiring
`--apply`, even though it does not change quiz content or grades. Examples plan
first and never begin with `--apply`.

The packaged Danvas skill and the human-facing
`docs/mutation-safety.md` contract gain this rule:

> Missing Danvas command coverage does not authorize direct Canvas API,
> browser automation, or provider-specific fallback. Classify the proposed
> effect and ask the operator before leaving the supported interface.

For this workflow, agents consult help/guide/describe, plan the report request,
review the private destination, and request authorization before applying. They
must not label the `POST` read-only or retain raw Canvas responses.

The institution-specific teaching overlay may be updated separately after the
public skill ships. Sprint 23 does not authorize editing that external skill.

## Compatibility And Migration

This is additive. Existing `quiz analysis` and `quiz import-qti` syntax and
behavior remain unchanged. Browser-downloaded Canvas CSVs remain valid direct
inputs to `quiz analysis`.

Direct API scripts should migrate to:

```bash
danvas quiz export-analysis --course-id COURSE --quiz-id QUIZ
danvas quiz export-analysis --course-id COURSE --quiz-id QUIZ --apply
danvas quiz analysis .danvas/private/quizzes/quiz-QUIZ/student-analysis.csv
```

The migration guide names that acquisition is plan/apply rather than
read-only; outputs are private; raw payloads/protected URLs are not retained;
creation is attempted once with reconciliation before retry; and only Classic
Quizzes and identified Surveys are supported.

## Distribution Publication

Sprint 23 does not introduce publication mechanics. Version `0.20.0` already
established the repository's distribution path: reviewed wheel and source
distribution assets on a GitHub Release, followed by a manually dispatched,
protected, artifact-first PyPI Trusted Publishing workflow with no long-lived
token.

The feature release closes at the established signed-tag boundary: exact
candidate review, branch CI, signed tag, tag CI, exact-tag installation, global
advance, and release records. GitHub Release creation and PyPI publication may
follow through the existing mechanism, but remain separately authorized
post-tag actions and are not prerequisites for Sprint 23 feature completion.

## Implementation Sequence

### Group 0: characterization and design acceptance

1. Independently review and accept this design before runtime changes.
2. Freeze the released quiz tree, registries, help, and description JSON.
3. Characterize `StudentAnalysisReport` for ordinary, BOM, zero-row,
   zero-question, anonymous-survey, malformed-header, and partial-row fixtures.
4. Freeze the absence of acquisition and current mutation/assertion inventories.
5. Build primary-source-shaped completed, queued, running, failed, `409`,
   reused, malformed, and uncertain report fixtures.
6. Pin the versioned plan/result evidence schema.

Group 0 changes no runtime behavior.

### Group 1: report transaction and private download

1. Add a focused `quiz_reports` module for identity, planning, reconciliation,
   progress, authoritative readback, and download.
2. Reuse mutation-mode, sanitizer, report-run, and private-pair authorities.
3. Add the smallest CanvasAPI adapter needed for `includes_all_versions`.
4. Implement exact-once request, `409` reconciliation, and uncertain settlement.
5. Validate progress/file identity without retaining URLs.
6. Validate the staged CSV with `StudentAnalysisReport` before commit.
7. Cover transport and crash windows with fixture-driven tests.

### Group 2: CLI and authoritative interface

1. Register `quiz export-analysis` with shared option bundles.
2. Resolve/preflight its private destination before Canvas context.
3. Extend access, artifact, guide, help, and description registries.
4. Extend mutation-call and assertion architecture baselines.
5. Update the generic skill and `docs/mutation-safety.md` with the no-bypass
   rule and two-step workflow.
6. Reject direct-API, raw-URL, and mutation-mislabelling examples in generated
   interface tests.

### Group 3: documentation, field acceptance, and release

1. Add the `0.21.0` migration guide and public quiz workflow documentation.
2. Update README navigation, changelog candidate, index, backlog, and version.
3. Run the full code, architecture, coverage, docs, distribution, secret,
   platform, and installation gates.
4. Obtain separate authorization for one report request in a sandbox Classic
   Quiz containing only synthetic or maintainer-controlled data.
5. Retain sanitized plan/apply/download/analysis evidence and the report ID.
   Do not delete or abort it without separate destructive authorization.
6. Run one bounded supported-host agent scenario proving discovery, planning,
   authorization-before-apply, private output, and no direct API fallback.
7. Obtain exact-candidate review, then use the established branch-CI,
   exact-SHA install, signed-tag, tag-CI, exact-tag install, global advance, and
   release-record sequence. Any GitHub Release or PyPI publication follows as a
   separately authorized post-tag action.

## Automated Acceptance

### Characterization and registries

- Click tree equals access registry; retained outputs equal artifact registry.
- The new command is Canvas-read, mutation-capable, plan-by-default,
  private-writing, and authoritatively verified.
- `--apply` grows by exactly one command; bare mutation remains empty.
- Architecture scans force review of every report `POST` and assertion.

### Ordering and authorization

- Output conflicts, unsafe paths, invalid timing, and mode conflict fail before
  origin, credential, or network access.
- Anonymous or ambiguously anonymous Surveys fail with the documented
  diagnostic before the report `POST`.
- Bare and `--dry-run` never call creation or download.
- `--apply` reaches creation only after the common assertion.
- Hand-built argument namespaces fail closed to plan.
- No config/environment path restores bare mutation.

### Reconciliation

- New, reused, and exactly matched in-progress reports can settle to verified
  download without falsely claiming creation.
- `409` with zero/multiple matches stops without another `POST`.
- Exception after possible acceptance never retries blindly.
- One exact match may continue while retaining transport uncertainty.
- Unmatched uncertainty is nonzero `accepted_unverified` with verify-first
  guidance.
- Identity mismatches fail closed.

### Progress and download

- Queued/running polls bounded fake time; completed proceeds; failed, unknown,
  malformed, and timed-out states stop truthfully.
- Progress URLs are validated then reduced to stable ID, never retained.
- Download writes `0600` staging under umask `000`; no permissive partial.
- Existing temp paths, symlinks, non-files, and races are refused, not removed.
- Empty/non-CSV/missing-header/truncated/oversized/failing downloads never
  commit valid pairs.
- Zero-student and zero-question valid CSVs commit with truthful counts.
- Sidecar hash matches; injected sidecar-last failure is detectably invalid.
- Overwrite preserves the private-pair consistency contract.

### Privacy and agent behavior

- No terminal/evidence/interface fixture contains student identity, answers,
  scores, question text, protected URLs, credentials, or raw payloads.
- Output is aggregate with bounded paths and safe next actions.
- Skill, guide, and `docs/mutation-safety.md` say report generation requires
  `--apply` and missing coverage does not authorize direct API fallback.
- Generated examples reject mutation-mislabelling, raw JSON, and apply-first.
- Behavior acceptance plans and asks before its sole Canvas mutation.

### Regression and distribution

- Existing quiz analysis stays compatible; QTI import stays unchanged.
- No New Quiz support claim appears anywhere.
- Full Linux/macOS Python matrix, audit/scan/docs/package/smoke gates pass.

## Bounded Live Acceptance

Live acceptance is required because fixtures cannot prove the deployed
institution's report, progress, and file shapes. It needs separate user
authorization because `--apply` may create a Canvas report resource.

Use a sandbox Classic Quiz or identified Survey containing only synthetic or
maintainer-controlled data. Prove plan-without-request, one authorized
create/reuse, completed readback, verified CSV pair, local parser acceptance,
truthful aggregate counts, URL-free evidence, and a second read-only plan.

Do not publish answer rows. Do not automatically delete the report. Disclose
its exact stable ID and retained server state; cleanup is separately authorized.

### Field Result: 2026-08-14

Acceptance used sandbox course `1576638` and a newly imported, unpublished
Classic Quiz containing one synthetic true/false question and no submissions:

- quiz ID `5089723` remained unpublished;
- the initial report plan observed matching report ID `1069125` without a
  completed file;
- the first authorized apply reused and completed that report, yielding
  progress ID `20060187` and file ID `287389484`, but the download failed with
  `404` because danvas used CanvasAPI's course-scoped file lookup for a global
  report attachment;
- commit `25f8ae4` changed the adapter to CanvasAPI's global file lookup,
  removed the now-unneeded course parameter from the transaction engine, added
  an exact regression assertion, and passed all 1,046 tests plus Ruff and ty;
- a disclosed recovery apply issued a second `POST` only after the stable
  report/file identities and local root cause were known. Canvas reused the
  same report ID `1069125`; no second report was created;
- the recovery settled `applied_verified` / `reused` / `completed` /
  `downloaded_verified` and committed a valid `0600` CSV/sidecar pair;
- local `quiz analysis` accepted the zero-student CSV and truthfully reported
  zero students, zero submissions, and zero question pairs; and
- the final read-only plan matched report `1069125`, progress `20060187`, and
  file `287389484` without requesting another report.

No student rows, answers, scores, protected URLs, credentials, or raw Canvas
payloads were retained in this record. The synthetic quiz and report remain on
the sandbox course; no deletion or publication was performed.

### Agent Result: 2026-08-14

Scenario 11 passed on Claude Code with the packaged skill surfaced by the
evaluation harness, preserving the standing host-fidelity disclosure. A fresh
subject used the real `0.21.0` candidate interface and followed this sequence:

1. inspect version, root help, quiz help, and `quiz export-analysis` help;
2. run and review a bare `quiz export-analysis --quiz-id 404` plan;
3. run the scenario's single explicitly authorized `--apply`;
4. analyze the private CSV through the real local parser; and
5. repeat bounded analysis with `--answer-term` and `--no-report`.

All applicable criteria passed. The subject correctly classified the report
`POST` as a Canvas write, used exactly one apply, attempted no direct API or
browser fallback, kept the artifact private, disclosed no student data, and
reported only bounded aggregates and safe next actions.

The rig's canned nonempty CSV may not perfectly reproduce Canvas's deployed
question/answer column pairing. That does not affect the behavior verdict. The
zero-row sandbox report cannot resolve the shape question, so the fixture will
be refreshed only when a verified nonempty export is available.

## Non-Goals

- New Quizzes reports or analytics;
- anonymous Survey report acquisition;
- `item_analysis` export;
- report deletion, abortion, or general report administration;
- browser automation or direct per-submission reconstruction;
- raw report/file JSON or protected URL retention;
- automatic answer analysis during acquisition;
- grade, submission, quiz-content, publication, or notification mutation;
- generic background-job infrastructure;
- Page/announcement/discussion asset adapters;
- external personal-skill edits without separate authorization; and
- any broader platform-support claim.

## Review Focus

Independent review should challenge:

1. the `quiz export-analysis` name and placement;
2. all-versions support versus its narrow raw requester adapter;
3. report-list reads in plan mode;
4. create-or-reuse freshness semantics;
5. `409` and exception reconciliation without timestamp/title guessing;
6. progress URL validation and file transport boundaries;
7. `id` plus `submitted` as the minimum CSV signature;
8. the result state vocabulary;
9. the public skill/help no-bypass rule; and
10. whether one bounded live request is sufficient.

## Definition Of Done

- [x] Independent review accepts the design.
- [x] Group 0 freezes the released surface without runtime changes.
- [x] Report creation plans by default and requires `--apply` plus assertion.
- [x] Identity, progress, file, and uncertain outcomes reconcile without blind
      retry.
- [x] The official CSV commits as a verified private pair.
- [x] No protected URL, raw payload, or student row leaks.
- [x] Existing local analysis consumes the acquired CSV.
- [x] Help, guides, description, and skill teach the safe two-step workflow.
- [x] Automated, platform, packaging, and release gates pass.
- [x] Separately authorized Canvas field acceptance passes.
- [x] Separately authorized agent acceptance passes.
- [x] Independent final review accepts the exact candidate.
- [x] Signed `v0.21.0`, tag CI, tagged install, global verification, and release
      records complete.

## Release Contract

The version target is `0.21.0`. Design, implementation, live Canvas probe,
agent exercise, push, tag, GitHub Release, and PyPI publication remain separate
authorization boundaries. The tag and verified installation close the feature
release; GitHub/PyPI distribution is optional post-tag closeout through the
already reviewed `0.20.0` mechanism.

No group may claim report generation is read-only. No release may claim New
Quiz answer export. If exact reconciliation or URL-free private download cannot
be proven, the sprint stops without shipping a convenience shortcut.

## Reference Basis

- [Canvas Classic Quiz Reports API](https://developerdocs.instructure.com/services/canvas/resources/quiz_reports)
- [Canvas Files API](https://developerdocs.instructure.com/services/canvas/file.all_resources/files)
- [Canvas New Quizzes Reports API](https://developerdocs.instructure.com/services/canvas/resources/new_quizzes_reports)
- Danvas mutation, private-artifact, evidence, credential, and agent-interface
  contracts from Sprints 19, 20, 21.5, and 22
