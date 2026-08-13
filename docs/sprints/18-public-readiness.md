# Public Readiness Program: Sprints 18-21

Status: accepted after factual and design review. Sprint 18 implementation is
authorized and in progress; Sprints 19-21 remain design-only until separately
reviewed. No live Canvas mutation, publication, release, or history rewrite is
authorized by this design note.

## Outcome

Make the public repository safe and understandable for instructors outside the
maintainer's institution without weakening the evidence and mutation-safety
properties already delivered.

The repository is already suitable to remain public as source code. The core is
unusually mature for an early/internal CLI: release 0.14.0 has typed asset
transaction state, architecture checks, supported-Python CI lanes, dependency
auditing, branch-coverage and complexity ratchets, extensive readback and
recovery behavior, secret sanitization, and careful filesystem containment.

It is not yet suitable to present as a generally reusable public Canvas tool.
The public boundary still contains institution-specific defaults, maintainer
workflow conventions, incomplete private-output handling, inconsistent live
mutation contracts, and maintainer-oriented packaging and documentation.

This program spans four bounded releases. The first three correct instance,
privacy, and mutation boundaries while retaining the internal/alpha label. Only
the fourth release may claim a defensible public beta. It is not a 1.0 claim.

## Context

The repository is already public. The current code, documentation, and local
release state identify 0.14.0 as the latest release. Sprint 16 delivered verified
Markdown asset deployment for assignments, and Sprint 17 stabilized that
transaction with typed state, an acyclic module boundary, and stronger quality
ratchets.

The public-readiness review assessed these areas:

| Area | Assessment |
| --- | --- |
| Core engineering | Strong |
| Canvas mutation safety | Uneven across command families |
| Privacy defaults | Needs work before broad recommendation |
| Institution independence | Several Auburn and maintainer assumptions remain |
| Installation and onboarding | Maintainer-oriented |
| Contributor readiness | Moderate |
| Public release readiness | Not yet |

The main blockers are privacy defaults and inconsistent mutation policy, not
general code quality.

The current backlog names the Page asset adapter as the next feature. Adopting
this program would deliberately pause that work through four bounded releases
because the repository is already public and its public boundary should be
hardened before another adapter extends the current assumptions. Until this
design is accepted, the existing backlog priority remains unchanged.

The review found no tracked course snapshots, CSV exports, `.env` files,
private keys, or obvious credential-shaped values in the current tree. A
targeted pattern scan across all 131 commits then reachable also found no common
API-key or private-key signatures. That was a bounded pattern review, not a
substitute for a dedicated secret scanner or a legal/privacy review.

Reachable history and current documentation do contain personal and
institutional breadcrumbs: maintainer filesystem paths, a personal historical
commit email, Auburn hosts, real-looking course/object IDs, and descriptions of
course-specific field acceptance. Those are not authentication secrets, but
they should be separated from the supported public interface.

## Public Beta Threshold

The project may describe itself as a public beta only when all of the following
are true:

1. A new user cannot accidentally target Auburn or inherit Central Time merely
   by omitting configuration.
2. Every command that emits student, grade, submission, discussion, roster, or
   protected recording data uses the same private-artifact policy.
3. No command mutates Canvas through an implicit or unexpectedly destructive
   default.
4. Every live mutation has bounded, sanitized result evidence appropriate to
   its risk; grade-affecting writes additionally have authoritative readback and
   safe retry guidance.
5. The generic installation and quickstart path works without the maintainer's
   SSH credentials, local directory layout, Codex skills, or course naming
   conventions.
6. The declared operating-system and Python support match tested behavior.
7. Public documentation explains authentication, privacy, compatibility,
   mutation safety, and support status without requiring the internal backlog.

## Release Sequence

The program is committed to this split rather than treating release packaging as
an implementation-time question:

| Sprint | Release | Bounded outcome | Public status |
| --- | --- | --- | --- |
| 18 | 0.15.0 | Instance profiles | Alpha |
| 19 | 0.16.0 | Private artifacts | Alpha |
| 20 | 0.17.0 | Mutation and evidence | Alpha |
| 21 | 0.18.0 | Generalization and packaging | Beta candidate |

Each release needs its own bounded implementation specification and independent
review before coding. This document is the cross-release contract: later slices
may refine implementation details but may not weaken the public beta threshold.

## Program Scope

The program includes six connected public-boundary slices:

1. Canvas-instance profiles and removal of Auburn/timezone runtime defaults;
2. one private-artifact policy applied to every sensitive command;
3. one Canvas-mutation mode and evidence contract, kept distinct from local
   write behavior;
4. configuration of maintainer-specific source, gradebook, file, and integration
   conventions;
5. public installation, packaging metadata, onboarding, and support documents;
   and
6. explicit platform/Python compatibility plus public-repository security
   checks.

Privacy, instance independence, and mutation safety must all ship before the
project is described as a public beta. Documentation-only cleanup must not be
used to claim that threshold while runtime defaults remain.

## 1. Canvas Instance And Authentication Profiles

### Remove institution-specific fallbacks

The runtime currently falls back to `https://auburn.instructure.com/`, CLI help
promises that fallback, and `danvas init` defaults to `America/Chicago`. These
are maintainer defaults rather than safe public defaults.

After Sprint 18:

- the CLI has no built-in Canvas host;
- absence of a resolvable API URL produces an actionable setup error before
  secret resolution or Canvas access;
- `danvas init` has no built-in timezone;
- an explicit timezone wins, otherwise init may use authoritative Canvas course
  or account metadata when available, then the selected user profile;
- if no timezone is available, init omits it and explains that date-only
  authored fields will remain unavailable until it is configured; and
- examples use `https://canvas.example.edu/` and non-live placeholder IDs.

Canvas course and account timezone metadata cannot be assumed to be IANA data.
Canvas may return Rails-style labels such as `Central Time (US & Canada)`.
Automatic adoption therefore requires a small, explicit, tested Rails-to-IANA
mapping. An unmapped value is reported and left unconfigured; it is never
guessed from institution, locale, or system timezone.

### Add user-level instance profiles

Support non-secret user configuration at the platform-appropriate danvas config
path. The design should use the standard operating-system config directory
rather than assuming `~/.config` on every platform.

Illustrative shape:

```toml
default_profile = "institution-a"

[profiles.institution-a]
api_url = "https://canvas.example.edu/"
timezone = "America/New_York"
secret_name = "canvas-institution-a"
secret_provider = "auto"
api_key_env = "CANVAS_INSTITUTION_A_API_KEY"
```

Profiles contain references and stable defaults, never token values. A course
project may select a profile:

```toml
[canvas]
profile = "institution-a"
course_id = 101
api_url = "https://canvas.example.edu/"
timezone = "America/New_York"
```

Profile selection and instance resolution use separate precedence rules.

Profile selection is:

1. explicit `--profile`;
2. `[canvas].profile` in the course project;
3. `DANVAS_PROFILE`; then
4. the user configuration's `default_profile`.

Canvas API URL resolution is:

1. explicit `--api-url`;
2. `[canvas].api_url` in the course project;
3. the selected profile's `api_url`;
4. `CANVAS_API_URL` only when no course project or selected profile establishes
   an instance; then
5. no value and an actionable error.

A generic shell-profile `CANVAS_API_URL` must never silently override an
initialized project's pinned instance. Credential-reference precedence is
separate because token values do not select the Canvas host: explicit secret
options win, then the selected profile's references, then existing environment
fallbacks.

Project configuration must not contain a token. Existing `CANVAS_API_URL`,
`CANVAS_API_KEY`, secret-provider, 1Password-reference, and configurable token
environment-variable workflows remain supported.

The fixed `secretpath` name `canvas` remains a compatibility default only when
no profile selects another name. Multiple Canvas instances and accounts must be
possible without renaming environment variables globally between commands.

### Migration

Existing initialized projects already contain an API URL and timezone, so they
should continue to work. Uninitialized use that previously relied on the Auburn
fallback must stop with migration guidance. No migration may silently infer a
different institution.

### Offline auth diagnostics

`danvas auth doctor` must remain useful outside a project when no profile or API
URL is configured. Its offline form reports the instance as `unconfigured`,
continues provider/configuration diagnostics, and preserves the isolated release
smoke contract. Only `auth doctor --check-canvas` requires a resolved instance
and fails actionably when one is absent.

## 2. Private Artifact Contract

### Central policy

Introduce one private-artifact boundary and route every sensitive output
through it. The helper owns directory creation, file creation, overwrite policy,
permissions, manifest classification, warnings, and downstream ignore rules.

Private data includes at least:

- rosters and course enrollments with user identifiers;
- grades, comments, release evidence, and gradebook exports or analyses;
- submission metadata, bodies, attachments, media, and feedback mappings;
- assignment override membership;
- discussion posts, participant identities, participation scores, and upload
  plans;
- quiz student-analysis rows or answer data tied to learners;
- protected recording/session metadata, caption downloads, and viewer URLs; and
- raw Canvas payloads that may include any of the above.

The classification is about content, not command family. A future command must
declare its output class before implementation.

### Default location and permissions

When a course project is available, default private outputs belong beneath
`.danvas/private/`. Without a course project, a command that produces private
data must require an explicit output location rather than quietly writing to the
current directory.

This deliberately amends the existing Report Output Contract for the sensitive
subset of commands previously classified as `explicit-output`. Raw exports and
downloads still accept explicit paths, but sensitive commands may use a safe
project-local default beneath `.danvas/private/`; without a project they require
an explicit path. Non-sensitive raw exports retain the existing explicit-output
decision. The accepted Sprint 19 specification and `PROJECT_CONTEXT.md` must
state the same revised contract.

`danvas init` must add at least these generated paths to a Git repository's
`.gitignore`:

```gitignore
.danvas/course.json
.danvas/reports/
.danvas/private/
```

Private directories must be created without group/other access before artifacts
are written. Private files must not be created permissively and tightened only
after content is present. Existing no-clobber behavior remains the default.

For the first public beta, it is acceptable to support only platforms where the
declared privacy contract can be enforced and tested. Unsupported platforms
must receive an explicit diagnostic; the CLI must not claim that POSIX mode bits
provide equivalent protection everywhere.

### Existing command corrections

At minimum, reconcile the following paths:

- `roster`: rename the misleading `Email` field to `LoginID`; offer a documented
  legacy schema only when compatibility requires it;
- `courses`: classify account/course visibility metadata deliberately rather
  than inheriting a generic CSV writer;
- `discussions export`: protect names, IDs, and full post bodies;
- `discussions score`: protect student-level plans and results and avoid printing
  names/scores by default in aggregate mode;
- `recordings panopto-captions`: protect caption files and manifests, and omit
  viewer URLs or other reusable access material from the default manifest;
- explicit gradebook and quiz-analysis outputs: apply the same protection as
  their report-run forms; and
- every raw-output option: identify itself as private both in the artifact and
  in CLI guidance.

Run a command/output inventory during implementation. The named cases above are
known findings, not an exhaustive allowlist.

### Shareable operational evidence

Public/non-private manifests should use project-relative paths. They must not
retain:

- absolute project roots;
- absolute input paths;
- full command arguments containing personal paths or sensitive free text;
- tokens, signed/verifier URLs, or raw error payloads; or
- student or private course content.

When provenance cannot express a source path relative to the project, fail or
record a bounded placeholder. Do not fall back to embedding an absolute
maintainer path in a source map intended for reuse.

Document whether `.danvas/config.toml` and `.danvas/source-map.json` are intended
to be tracked. They contain no credentials, but they may expose course names,
course/object IDs, assignment-group IDs, schedules, and deployment history.

## 3. Consistent Mutation And Evidence Contract

### Access-mode inventory

The reviewed CLI has 20 command functions with a `dry_run` option. Nineteen
default it to `False`; only assignment override sync defaults to planning. That
count includes both Canvas mutations and local-write workflows, but it makes the
size of the compatibility break explicit: Sprint 20 reverses the bare-invocation
behavior of nearly the whole Canvas-mutating surface, not merely option names.

Before implementation, classify every command on separate axes:

- Canvas-read-only;
- local-writing without Canvas mutation;
- Canvas-mutating, including commands that also write local evidence;
- private-output; and
- destructive, grade-affecting, notification-producing, or otherwise requiring
  an additional guard.

The Sprint 20 migration guide must enumerate every Canvas-mutating command whose
bare invocation changes, with its old behavior, new plan behavior, explicit
apply command, notification behavior, and compatibility alias.

### Canvas mutation mode

Every Canvas-mutating command uses this public contract:

- omission plans by default and may perform documented read-only Canvas calls;
- `--dry-run` remains an explicit planning spelling and compatibility path;
- `--apply` authorizes the planned Canvas mutation; and
- destructive or grade-affecting operations may require an additional target or
  state guard, but must not invent a different basic live-mode vocabulary.

Plan-by-default provides the same safety as requiring a planning flag while
avoiding ceremony with no additional protection. A bare invocation never
mutates Canvas.

Local-writing commands are a distinct category. `pages sync`, `announcements
sync`, and `discussions sync-prompts` read Canvas but use `--dry-run` to gate
local no-clobber source creation. They do not gain `--apply`, because no live
Canvas state is changed. Their existing local plan/write behavior remains in
this program and must be documented as such; any future `--write-local` rename
requires a separate compatibility design.

For a transaction that mutates Canvas and writes local evidence or provenance,
`--apply` authorizes the Canvas transaction; the documented local evidence is
part of that transaction rather than a second ambiguous mode.

Existing `--live`, `--upload`, and `--confirm` forms need a documented migration
plan. Compatibility aliases may remain temporarily, but no legacy alias may
bypass the new safety boundary.

Notification behavior must be explicit and included in the plan for every
Canvas content mutation. A default should not surprise students.

### Non-destructive duplicate defaults

`files upload` currently defaults duplicate handling to `overwrite`. Change the
public default to `error`. Overwrite and rename remain explicit, separately
reviewable actions. Asset-integrated assignment workflows retain their stricter
existing conflict behavior.

### Evidence invariant

Apply the durable evidence invariant across command families:

- every intended mutation appears exactly once in retained evidence;
- plan, mutation, evidence, and verification states remain distinct;
- an indeterminate result does not invite a blind retry;
- dependent writes stop after unsafe or indeterminate outcomes;
- retained and displayed errors use the shared sanitizer; and
- result evidence states the safe next action.

Content creates/updates, uploads, override synchronization, feedback uploads,
and grade-affecting commands may have different result schemas, but they share
these invariants.

### Discussion-score and feedback reconciliation

`discussions score --upload` must not remain a separate best-effort grade writer
that continues after failures and lacks authoritative readback. Sprint 20 will
remove its direct grade write and emit a private grade plan/CSV consumed by
`danvas grades post`. The output includes the exact review and post command, so
the established grade transaction owns preflight, rollback, mutation, readback,
release evidence, and recovery without a new shared-engine extraction.

The old `--upload` spelling must either fail with that replacement command or
act only as a bounded compatibility alias for generating the plan. It must not
continue to write grades directly. Direct engine integration can follow later
if field use shows that the intermediate review step creates material friction.

`submissions feedback` likewise needs bounded per-row evidence, sanitized
failures, a stop policy for unsafe outcomes, and a documented retry boundary.

## 4. Generalize Workflow Conventions

### Course source layouts

The current defaults encode the maintainer's course layout, especially
`content/cases/*-assignment.md` and `content/quizzes/chap*.md`. Replace implicit
personal conventions with an explicit layout selected during initialization.

Recommended standard layout:

```text
content/assignments/*.md
content/announcements/*.md
content/discussions/*.md
content/quizzes/*.md
content/pages/*.md
content/pages/*.html
```

`danvas init` should write the effective patterns into project configuration so
the project is self-describing. Existing projects without explicit source
configuration retain a documented legacy layout during migration. Status
next-action suggestions must derive output directories from effective project
configuration instead of printing fixed `content/...` paths.

### File inventory exclusions

Current built-in exclusions include maintainer conventions such as `grading` and
`_archive`, and project configuration can only add patterns. Support an explicit
choice between extending and replacing the defaults, for example:

```toml
[files.inventory]
use_default_ignores = true
ignore = ["scratch/**", "rendered/**"]
```

Safety-critical exclusions for `.git`, `.danvas`, and the active output tree may
remain mandatory. Course-layout preferences should not be mandatory.

### Gradebook and roster schemas

Canvas gradebook parsing currently assumes English headings such as `Student`,
`Points Possible`, and `Unposted Final Score`. The public contract should:

- document the tested Canvas export format and locale;
- support configured aliases for metadata, points, final-score, final-grade, and
  group-total headings where feasible;
- fail with a diagnostic that names the unrecognized headers; and
- avoid claiming broad locale support until fixtures and CI cover it.

Roster output must represent Canvas `login_id` truthfully as `LoginID`, since it
is not guaranteed to be an email address.

### Optional integrations

Panopto support is provider-specific and depends on observed LTI and private
service behavior. Present it as an optional/experimental integration. Move the
caption language, tool-name matching, retained manifest fields, and any provider
URL overrides into an `[integrations.panopto]` configuration boundary while
retaining explicit CLI overrides.

QTI import accepts a supported QTI zip. Public help should describe text2qti as
one tested producer rather than requiring the maintainer's `make-qti` wrapper.

## 5. Public Packaging And Documentation

### Installation and distribution

The primary public installation path must not require GitHub SSH credentials.
Use an anonymous HTTPS exact-tag install immediately.

The PyPI distribution name `danvas` is occupied by an unrelated project. Before
PyPI publication, choose a distinct distribution name. The import package and
installed `danvas` command may remain unchanged if the selected packaging name
allows it. Name selection is a review decision and must not be guessed during
implementation.

Add standard package metadata to `pyproject.toml`:

- license declaration;
- project/repository/issues/documentation URLs;
- maintainer or author metadata appropriate for publication;
- Python and operating-system classifiers matching CI;
- topic classifiers and keywords; and
- an explicit supported Python upper bound when support is intentionally
  bounded.

External publication, tag creation, GitHub release creation, and global tool
replacement remain separately authorized release actions.

### Public documentation surface

Replace the maintainer-runbook shape with these public entry points:

- `README.md`: short overview, status, anonymous installation, five-minute
  quickstart, mutation warning, and links to deeper guides;
- `docs/configuration.md`;
- `docs/authentication.md`;
- `docs/privacy.md`;
- `docs/compatibility.md`;
- command-contract references for authored sources and mutation/evidence
  behavior;
- `CHANGELOG.md`;
- `CONTRIBUTING.md`; and
- `SECURITY.md` with a private vulnerability-reporting path.

Add a standard statement that the project is not affiliated with or endorsed by
Instructure. Explain the Canvas trademark relationship without implying that
the tool is an official Canvas product.

The README's examples should use placeholder hosts and internally consistent
placeholder IDs. Public guidance must not refer to `On this machine`, external
Codex skill paths, absolute maintainer filesystem paths, course-specific
repositories, or the maintainer's private release environment.

### Planning and design history

Retain sprint specifications that explain durable technical contracts, but
separate current public guidance from historical field notes. Replace or redact
real-looking sandbox/course IDs and maintainer paths in the current tree where
they add no technical value.

`PROJECT_CONTEXT.md` must either become current, generic project-maintainer
documentation or move out of the public authority chain. It must not advertise
stale release state or require files outside the repository.

Do not rewrite Git history merely to remove ordinary maintainer identity or
already-public institutional breadcrumbs. Rewrite history only after a separate
review finds actual secrets or material protected data and weighs rotation,
coordination, fork invalidation, and clone disruption. Because the repository is
already public, rewriting cannot retract prior exposure.

## 6. Portability, CI, And Repository Security

### Supported platforms and Python versions

The package currently declares Python `>=3.12`, while CI covers 3.12 and 3.14 on
Ubuntu. The public beta target is POSIX-only, supporting Linux and macOS. Sprint
21 should:

- add Python 3.13 to the test matrix;
- declare `>=3.12,<3.15` rather than implying indefinite future-Python
  compatibility;
- retain Ruff's `py312` target because it represents the minimum supported
  syntax version;
- add a `macos-latest` privacy/filesystem lane before claiming macOS support;
- verify the existing Linux lanes against the same private-artifact contract;
  and
- not claim Windows support until private-artifact protection and path behavior
  have a tested Windows contract.

The first public beta deliberately remains POSIX-only. That is preferable to
claiming unsupported cross-platform privacy.

### CI and security hygiene

- Give GitHub Actions explicit minimal permissions.
- Pin third-party actions by immutable commit SHA while retaining readable
  version comments or automated update support.
- Keep frozen dependency auditing, release smoke, type checks, lint, architecture
  checks, and branch coverage.
- Add a dedicated current-tree and reachable-history secret scan before the
  public-beta release. Record the scanner/version and adjudicate findings
  without committing secret-bearing output.
- Add tests that enumerate every CLI command classified as mutating or private;
  a new command must not bypass either registry.

## Architecture Boundary

The profile, private-artifact, and mutation-policy work should establish typed
shared boundaries rather than add more command-local conditionals.

Likely components are:

- a typed resolved command context containing instance, course, timezone, auth
  references, output policy, and project root;
- a dependency-light profile/configuration module;
- a private-artifact writer used by explicit outputs and report runs; and
- mutation-policy metadata or helpers shared by command families.

The implementation should reduce the 45 repeated Canvas-auth option bundles in
`cli.py` where the new context naturally permits it. A full 3,000-line CLI split
is not required for the public-beta boundary and should not become an unrelated
refactor. Extract command-family registration only when necessary to keep the
new contracts testable.

## Compatibility And Migration

This program intentionally changes unsafe defaults across multiple bounded
minor releases.

Required migration behavior:

- existing initialized projects with `api_url` and `timezone` continue to run;
- uninitialized Auburn-fallback use stops with setup instructions;
- existing source-layout behavior remains available through an explicit legacy
  layout or generated configuration;
- `Email` roster consumers receive a documented legacy-schema option for a
  bounded deprecation period;
- `files upload` without `--on-duplicate` becomes conflict-safe;
- bare Canvas-mutating commands plan instead of writing;
- the Sprint 20 migration guide enumerates every flipped command rather than
  describing the change only at the policy level;
- local-writing sync commands retain their separate `--dry-run`/no-clobber
  contract and never use `--apply` to describe a local file write;
- old live-mode flags either map visibly to the new contract for one deprecation
  window or fail with the exact replacement command; and
- existing report/source-map schemas change only through an explicit schema
  version and migration test.

Each release must include its own migration guide with before/after command and
configuration examples. The 0.17.0 guide is additionally required to contain a
complete command-by-command mutation table.

## Program Implementation Sequence

### Sprint 18 / 0.15.0: instance independence

1. Characterize current instance, profile, environment, project, timezone, and
   offline auth-doctor behavior.
2. Introduce instance profiles and a typed resolved command context.
3. Remove the Auburn and Central Time fallbacks with migration diagnostics.
4. Add bounded Rails-to-IANA timezone mapping and unconfigured fallback behavior.
5. Preserve offline auth-doctor and isolated release smoke without a configured
   API URL.
6. Update current durable context and the 0.15.0 migration guide, then complete
   independent review and release gates.

### Sprint 19 / 0.16.0: private artifacts

1. Inventory every command/output by sensitivity, default path, overwrite
   behavior, report behavior, terminal disclosure, and interruption behavior.
2. Characterize current schemas and permission behavior.
3. Introduce the private-artifact boundary, secure-at-creation behavior, private
   default root, and `.gitignore` updates.
4. Migrate every private command and sanitize shareable paths/manifests.
5. Amend the durable Report Output Contract and publish the privacy migration
   guide.
6. Complete an adversarial private-output review and release gates.

### Sprint 20 / 0.17.0: mutation reconciliation

1. Inventory every command by Canvas-read, local-write, Canvas-mutation,
   destructive, grade, notification, and verification behavior.
2. Add characterization tests for all mutation entry points and local-write sync
   behavior.
3. Make Canvas mutations plan by default and reserve `--apply` for Canvas writes.
4. Change file-upload duplicate behavior to conflict-safe.
5. Replace direct discussion-score upload with a private `grades post` plan and
   add transactional feedback evidence.
6. Publish the complete command-by-command migration table, then complete an
   independent operator-safety review and release gates.

### Sprint 21 / 0.18.0: generalized public beta

1. Add explicit source layouts, configuration-derived next actions, replaceable
   inventory ignores, truthful roster fields, gradebook aliases, and optional
   integration configuration.
2. Rebuild the public README and add authentication, configuration, privacy,
   compatibility, contribution, security, and changelog documents.
3. Add package metadata, anonymous installation, POSIX/Python declarations,
   macOS CI, minimal permissions, immutable action pins, and secret scanning.
4. Run a clean-machine quickstart and an independent public-boundary audit.
5. Claim public beta only when the cross-release threshold and all final release
   gates pass.

## Automated Acceptance

### Institution independence

- No source or CLI default contains an Auburn Canvas host.
- No init path silently chooses `America/Chicago` or any other maintainer
  timezone.
- Rails-style Canvas timezone labels are mapped only through the explicit tested
  table; unknown labels remain unconfigured with an actionable diagnostic.
- Missing instance configuration fails before Canvas access with a generic
  actionable message.
- Two named profiles can select different Canvas hosts, secret references,
  token environment variables, and timezones in one test process.
- Existing project-local API URL and timezone configuration remain compatible.
- A generic `CANVAS_API_URL` cannot override an initialized project's API URL.
- Offline `auth doctor` reports an unconfigured instance but still completes
  provider diagnostics and isolated release smoke; `--check-canvas` fails
  actionably without an instance.

### Private artifacts

- Every command in the private-command inventory produces protected output.
- Private directories and files are protected at creation time, including
  interrupted and failed runs.
- `.danvas/private/` is added to downstream `.gitignore` idempotently.
- Explicit private outputs refuse overwrite by default.
- Roster, discussion, gradebook, quiz-analysis, submission, override, and
  recording fixtures cannot escape the private classification.
- Public manifests contain no absolute project paths, student data, tokens,
  signed/verifier URLs, or protected viewer URLs.
- Source-map writes reject or safely normalize sources outside the project.

### Mutation safety

- Every Canvas-mutating command is present in a central test inventory.
- Every local-writing and Canvas-mutating command has a separate access-mode
  classification.
- Omitting `--apply` plans and never mutates Canvas.
- Every Canvas-mutating command supports a reviewable dry-run or plan.
- Local-writing sync commands never interpret `--apply` as local-write
  authorization and retain their tested no-clobber contract.
- `files upload` defaults to a conflict rather than overwrite.
- Notification choices appear in plans and payload characterization tests.
- Discussion-score plan generation and feedback writes retain one outcome per
  intent, sanitize errors, stop according to their documented unsafe-outcome
  policy, and provide safe retry guidance.
- Grade-affecting discussion writes use authoritative readback or emit a grade
  plan for the established grade engine; no best-effort direct upload remains.

### Workflow generalization

- A newly initialized standard-layout fixture discovers ordinary assignment,
  announcement, discussion, quiz, and Page sources without case/chapter naming.
- A legacy-layout fixture retains pre-sprint discovery behavior.
- Status next actions use the effective configured source paths.
- File inventory tests cover extending and replacing non-critical default
  ignores while preserving mandatory safety exclusions.
- Roster output labels Canvas `login_id` as `LoginID`.
- Gradebook fixtures cover the documented default headings, configured aliases,
  and an actionable unknown-header failure.
- Panopto tests cover configured tool matching/language and absence of viewer
  access URLs from default manifests.

### Packaging and public documentation

- An anonymous exact-tag or candidate-commit HTTPS installation passes version,
  help, and offline auth-doctor smoke without the repository environment.
- Package metadata contains license, project URLs, maintainership, classifiers,
  and supported Python bounds.
- The README quickstart uses only placeholder hosts/IDs and no maintainer-local
  paths.
- All documented links resolve locally.
- Public docs state beta status, privacy boundaries, mutation semantics,
  compatibility limits, and the unofficial relationship to Instructure.
- Current-tree and reachable-history secret scans complete with all findings
  adjudicated before release.
- Python 3.12, 3.13, and 3.14 pass the supported lanes, and package metadata
  declares `>=3.12,<3.15`.
- A `macos-latest` lane verifies the private-artifact contract before macOS is
  listed as supported.

### Existing quality gates

- Ruff, ty, lock validation, the dependency audit, and all tests pass under each
  supported Python lane.
- Global and named-module branch-coverage floors remain at least their 0.14.0
  values unless a reviewed design change raises them.
- The import graph remains acyclic and no undocumented `C901` suppression is
  added.
- Editable and wheel smoke pass in isolated environments.

## Bounded Live Acceptance

Most acceptance is local or read-only. Before release, use a disposable sandbox
course only if implementation changes Canvas-observable mutation behavior that
cannot be proven with current fixtures.

Any live case requires separate authorization and must be narrowly limited to:

1. profile-selected authentication against a non-Auburn or generic test
   instance when available;
2. one file upload conflict/default check with separately authorized cleanup;
3. the selected discussion-score integration path against a disposable graded
   discussion, with complete grade readback and restoration; and
4. confirmation that notification settings and retained evidence match the
   plan.

No live roster, student submission, or production-course data should be copied
into the repository or public acceptance record.

## Non-Goals

- Implementing the Page asset adapter or another new Canvas feature family;
- grouped-case workflow expansion;
- general internationalization of all terminal and report prose;
- claiming support for every Canvas deployment, locale, authentication policy,
  or third-party LTI configuration;
- Windows support without a tested private-artifact contract;
- replacing `secretpath` merely because it originated in the maintainer's
  workflow;
- converting `danvas` into a long-term Canvas history ledger;
- automatic publication to PyPI, GitHub Releases, or another package registry;
- automatic tag creation or global CLI replacement;
- rewriting Git history for ordinary maintainer attribution or already-public
  non-secret context; or
- a broad CLI-module rewrite unrelated to the public boundary.

## Resolved Review Decisions

- The work is a four-release program, not one sprint-shaped release.
- Bare Canvas-mutating commands plan; `--apply` authorizes Canvas writes.
- Local-source sync remains a separate local-write/no-clobber contract and does
  not use `--apply`.
- Discussion scoring emits a private grade plan consumed by `grades post` rather
  than extracting or duplicating the transaction engine in Sprint 20.
- The first public beta is POSIX-only; macOS support requires a macOS CI lane.
- Current history is not rewritten for identity breadcrumbs. A rewrite is
  reconsidered only if the dedicated scan finds actual secret or protected data.

## Remaining Review Questions

1. Which platform-config library and exact profile schema should Sprint 18 use?
2. What distinct distribution name should Sprint 21 use for publication?
3. Should existing source discovery default to the legacy layout until each
   project opts in, or should `init` always materialize a selected layout?
4. Which course metadata, if any, should be classified as private even when it
   contains no student records?
5. Should Panopto remain bundled but experimental, become an optional dependency
   group, or move to a provider plugin later?

## Definition Of Done

- Sprints 18-21 ship as separately reviewed releases, and the public beta
  threshold is met without relying on prose-only warnings for unsafe runtime
  behavior.
- Institution, timezone, source-layout, gradebook, inventory, and optional
  integration assumptions are explicit configuration or documented bounded
  compatibility profiles.
- Every private and mutating command is centrally inventoried and enforced by
  tests.
- Public installation and onboarding work without maintainer credentials or
  filesystem context.
- Supported platforms and Python versions are declared, tested, and consistent
  with private-artifact behavior.
- Current public documentation contains no unnecessary maintainer-local paths or
  live course examples.
- Dedicated secret scanning and independent public-boundary review are complete.
- No Page asset, grouped-case, archival-ledger, or unrelated refactor work has
  entered the program.

## Release Contract

The target sequence is:

- Sprint 18: 0.15.0, instance independence;
- Sprint 19: 0.16.0, private artifacts;
- Sprint 20: 0.17.0, mutation reconciliation; and
- Sprint 21: 0.18.0, generalized public beta.

Each release candidate must pass pushed main CI and its slice-specific
independent review before an exact tag is created. Tag CI and anonymous exact-tag
install smoke must pass before the installed global CLI advances to that tag.
The public quickstart and cross-release acceptance matrix are additional 0.18.0
gates. Releases 0.15.0 through 0.17.0 remain internal/alpha and must not claim
the public beta label early.

No push, tag, GitHub Release, package-registry publication, history rewrite,
global installation change, or live Canvas mutation is implied by this design.
