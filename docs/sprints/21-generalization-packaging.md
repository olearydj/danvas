# Sprint 21: Generalization, Packaging, And Public Beta

Status: design accepted on 2026-08-13 after independent review. Sprints 18
through 20 are released as `v0.15.x`, `v0.16.0`, and `v0.17.0`. This sprint is
the final generalization and packaging slice of the accepted public-readiness
program and targets `0.18.0`. Group 0 characterization is complete at
`ded6b2e`; Groups 1 through 3 have passed focused review; and Group 4 CI and
security hardening has passed focused review and awaits exact-commit remote CI.
The sprint does not authorize external publication, tagging, global
installation, or live Canvas use. A separately authorized repository-setting
change enabled GitHub private vulnerability reporting on 2026-08-13.

The reviewed Python distribution name is `danvas-cli`. The Python import
package and installed command remain `danvas`.

## Outcome

Make the repository defensible as a public beta for instructors using ordinary
Canvas deployments on supported POSIX systems.

The release will remove the remaining maintainer-specific workflow defaults,
make new projects self-describing, complete package metadata and public
documentation, provide anonymous installation, test the declared Linux/macOS
and Python support, and add repository security gates appropriate to a public
project.

This is a boundary-hardening release, not a feature expansion. The Canvas
instance, private-artifact, and plan/apply contracts delivered in Sprints 18
through 20 remain authoritative.

## Program Context

The public-readiness program reserves the beta label for this release. Its
cross-release threshold requires:

1. no institutional or timezone fallback;
2. one enforced private-artifact boundary;
3. no implicit Canvas mutation;
4. bounded, truthful mutation evidence;
5. installation and onboarding without maintainer credentials or paths;
6. declared platform/Python support matching CI; and
7. public documentation that stands without the internal backlog.

Items 1 through 4 shipped in `0.15.x` through `0.17.0`. Sprint 21 owns items 5
through 7 and the remaining workflow-generalization work. It may claim public
beta only after an independent audit verifies the complete threshold against
the released tree.

Sprint 22 is a separate, accepted `0.19.0` agent-interface design. Its review is
complete and assigned roster compatibility removal to 0.19.0 without requiring
another Sprint 21 interface amendment. That review does not authorize Sprint 22
implementation or widen Sprint 21 into agent packaging.

## Verified Baseline

The `0.17.0` tree has the following remaining public-boundary assumptions:

- source discovery defaults to `content/cases/*-assignment.md` and
  `content/quizzes/chap*.md`; per-kind overrides exist, but `init` does not
  materialize an explicit layout;
- status next actions still print fixed `content/announcements`,
  `content/discussions`, and `content/pages` paths;
- file inventory always extends built-in exclusions, while maintainer
  conventions such as `grading`, `_archive`, and `_inventory` are also enforced
  outside the configurable pattern list;
- gradebook parsing assumes English structural headings including `Student`,
  `Points Possible`, and the four score/grade variants;
- Panopto discovery assumes a tool label or URL containing `panopto`, the
  caption language defaults in the CLI, and an interrupted bundle can silently
  create duplicate uniquely suffixed captions on retry;
- `assignments overrides-sync --live` and `discussions score --upload` remain
  deprecated compatibility spellings scheduled for removal in `0.18.0`;
- roster `--schema legacy-v1` remains available under the Sprint 19 promise
  that it will not be removed before `0.19.0`;
- an explicit invalid `init --timezone` is validated only after Canvas access;
- one executable test fixture still uses an Auburn host and real-looking IDs
  remain in reusable examples and fixtures;
- `pyproject.toml` is named `danvas`, declares only Python `>=3.12`, and omits
  license, maintainership, classifiers, keywords, and project URLs;
- the README's exact-tag installation uses GitHub SSH rather than anonymous
  HTTPS;
- the public guide set lacks dedicated configuration, authentication, privacy,
  compatibility, contribution, security, and changelog documents;
- CI runs Python 3.12 and 3.14 only on Ubuntu, grants no explicit token
  permissions, and references third-party actions by movable version tags; and
- no dedicated current-tree and reachable-history secret scan is a release
  gate.

The repository has a tracked MIT `LICENSE`. The gap is package metadata and
public documentation, not absence of a license grant.

## Accepted Review Decisions

### Distribution name

The distribution name is `danvas-cli`. On 2026-08-13, independent review
queried PyPI's JSON API and observed HTTP 200 for the unrelated `danvas`
distribution and HTTP 404 for both `danvas-cli` and `danvas-tool`. The review
selected `danvas-cli` because it:

- was observed available on the intended registry at review time;
- is not confusingly official or likely to imply Instructure endorsement;
- remains recognizable as the distribution that installs the `danvas` CLI;
- follows normalized Python distribution naming rules; and
- has a direct migration from the currently installed distribution named
  `danvas`.

Availability is point-in-time evidence, not a reservation. Implementation must
recheck it before any separately authorized reservation or publication. The
Python import package remains `danvas`, and the installed console command
remains `danvas`. Selecting the name does not authorize PyPI publication or
reservation.

### Source-layout transition

Independent review accepted the following transition:

- a brand-new `danvas init` defaults to `standard-v1` and writes the complete
  effective source configuration;
- an existing initialized project without explicit source configuration keeps
  the exact `legacy-v1` discovery behavior;
- `init --force` preserves an existing effective layout unless the operator
  passes `--source-layout`; and
- no command infers a layout from files already present in the repository.

This is the compatibility-preserving answer to the program's remaining layout
question: new projects receive the public convention, while existing projects
do not silently stop discovering their sources.

## 1. Source Layout Contract

### Named layouts

Add two versioned layout names:

- `standard-v1`:
  - announcements: `content/announcements/*.md`;
  - discussions: `content/discussions/*.md`;
  - quizzes: `content/quizzes/*.md`;
  - assignments: `content/assignments/*.md`;
  - Pages: `content/pages/*.md` and `content/pages/*.html`;
  - Page exclusion: `content/pages/*-preview.html`; and
  - assignment metadata required for broad assignment discovery.
- `legacy-v1`:
  - announcements: `content/announcements/*.md`;
  - discussions: `content/discussions/*.md`;
  - quizzes: `content/quizzes/chap*.md`;
  - assignments: `content/cases/*-assignment.md`;
  - Pages and Page exclusions identical to the current defaults; and
  - current assignment marker behavior preserved.

Layout names are compatibility identifiers, not mutable aliases. A future
change to the standard patterns requires `standard-v2` or explicit project
overrides.

### Materialized configuration

New initialization writes the selected layout and its effective per-kind
values, rather than relying on package defaults:

```toml
[sources]
layout = "standard-v1"

[sources.assignments]
include = ["content/assignments/*.md"]
require_assignment_metadata = true

[sources.announcements]
include = ["content/announcements/*.md"]
output_dir = "content/announcements"

[sources.discussions]
include = ["content/discussions/*.md"]
output_dir = "content/discussions"

[sources.quizzes]
include = ["content/quizzes/*.md"]

[sources.pages]
include = ["content/pages/*.md", "content/pages/*.html"]
exclude = ["content/pages/*-preview.html"]
output_dir = "content/pages"
```

Every path is relative to the project root. Absolute paths, parent traversal,
and output directories containing glob syntax fail configuration validation.
Initialization does not create, move, or rename authored source files.

Per-kind values override the named layout. An omitted per-kind key inherits
from the selected layout. The effective configuration renderer used by tests
and diagnostics must therefore be able to show the resolved layout without
consulting maintainer knowledge.

The currently supported singular kind names and `includes`/`excludes` spellings
remain readable in `0.18.0`; init writes only canonical plural tables with
`include`/`exclude`. After accounting for those compatibility spellings,
unknown keys in the touched source tables fail with the full configuration key
so a typo cannot silently restore a package default.

### Existing projects and force behavior

An existing project with no `[sources]` table resolves as `legacy-v1`. An
existing project with per-kind source tables but no layout also uses
`legacy-v1` for unspecified kinds, preserving current mixed custom/default
behavior.

`danvas init` gains:

```text
--source-layout standard-v1|legacy-v1
```

For a new project, omission selects `standard-v1`. For `init --force` against an
existing config, omission preserves and materializes the existing effective
source configuration. Passing `--source-layout` deliberately replaces the
source layout, while unrelated supported configuration tables remain intact.
The command never guesses from current directory names.

The `0.18.0` migration guide must show how an existing project opts in to the
standard layout without moving files, and separately how to move files after
updating configuration.

### Configuration-derived next actions

Status next actions use `[sources.<kind>].output_dir` for announcement,
discussion, and Page sync suggestions. For a legacy/custom config without that
key, danvas may derive a directory only when all relevant include patterns have
one unambiguous static parent. Otherwise the next action names the missing
configuration key instead of inventing a path.

The corresponding sync commands use the same resolver: explicit `--output-dir`
wins, then configured `output_dir`, then an unambiguous layout-derived
directory. Their local-write/no-clobber contract remains unchanged. Output
resolution happens before Canvas context or authentication.

Assignment, quiz, and other suggestions must not print maintainer paths. A
placeholder such as `SOURCE` is acceptable when the operator must choose a new
file.

## 2. Replaceable File-Inventory Ignores

Split exclusions into two typed groups:

- mandatory safety exclusions, which cannot be disabled; and
- default convenience exclusions, which projects may extend or replace.

Mandatory exclusions are limited to danvas/repository machinery that cannot be
meaningfully compared as course content:

- `.git/**`;
- `.danvas/**`;
- the active inventory report/output artifacts; and
- transient files created by the current inventory operation.

Default convenience exclusions include current local conventions such as
`_archive/**`, `_inventory/**`, `grading/**`, `.obsidian/**`,
`node_modules/**`, `__pycache__/**`, hidden files, `.DS_Store`, and known
generated inventory filenames. Their exact reviewed list is centralized in one
constant and exposed in documentation and test fixtures.

Configuration becomes:

```toml
[files.inventory]
use_default_ignores = true
ignore = ["scratch/**", "rendered/**"]
```

When `use_default_ignores = true`, custom patterns extend the convenience
defaults. When false, only mandatory exclusions plus custom patterns apply.
Existing projects omit the key and retain `true`, so current behavior is
unchanged. Invalid booleans and unsafe patterns fail before traversal.

Only `use_default_ignores` and `ignore` are valid keys in the touched table.
Unknown keys fail with `[files.inventory].<key>` rather than being ignored.

Reports state whether defaults were used and record the effective bounded
pattern list. Fixed prose about `grading` or `_archive` must derive from that
effective policy rather than claim an exclusion that the project disabled.

## 3. Configurable Gradebook Headings

### Bounded alias model

Keep English Canvas gradebook CSV headings as the tested built-in profile. Add
exact aliases through the existing optional course policy YAML:

```yaml
gradebook_heading_aliases:
  student: [Étudiant]
  id: [Identifiant]
  points_possible: [Points possibles]
  unposted_final_score: [Note finale non publiée]
  final_score: [Note finale]
  unposted_current_score: [Note actuelle non publiée]
  current_score: [Note actuelle]
  unposted_final_grade: [Évaluation finale non publiée]
  final_grade: [Évaluation finale]
  unposted_current_grade: [Évaluation actuelle non publiée]
  current_grade: [Évaluation actuelle]
```

The same score-role aliases apply to group-total suffix detection. Metadata
roles may also define aliases for SIS user ID, SIS login ID, section, email, and
root account so they are not mistaken for assignments.

Aliases extend the English defaults. They do not claim that danvas supports a
locale; the project supports only the fixtures and explicit aliases it tests.
Header comparison trims surrounding whitespace but otherwise remains exact and
Unicode-preserving.

### Ambiguity and diagnostics

Configuration fails when one alias maps to multiple canonical roles. Parsing
fails when multiple observed headers satisfy a required single role, when the
points row cannot be found, or when no configured final-score variant is
present.

The diagnostic names the missing or ambiguous canonical role, the configured
aliases considered, and a bounded list of observed headings. It never prints
student rows, login IDs, scores, or cell values. Private gradebook output and
report behavior remain governed by Sprint 19.

Existing `final_score_column` continues to accept an exact observed header and
wins after alias resolution. Existing English exports and policy files remain
unchanged.

## 4. Optional Panopto Integration And Restart Recovery

### Configuration boundary

Panopto remains bundled but explicitly experimental in `0.18.0`. It uses
dependencies already required by the core CLI, so an optional dependency group
would not create a meaningful installation boundary. A provider plugin is
deferred until another recording provider or an incompatible Panopto deployment
creates a real interface requirement.

Add non-secret project configuration:

```toml
[integrations.panopto]
caption_language = "English_USA"
tool_name = "Panopto Video"
# tool_id = 123
# base_url = "https://media.example.edu/"
```

`tool_name` is an exact case-insensitive label match. `tool_id` is the
deterministic choice when labels collide. Defining both is an error. Without
either, the current bounded `panopto` discovery remains the experimental
fallback.

Explicit CLI values win over project configuration, which wins over the current
built-in caption-language/discovery fallback. Add explicit tool-name/tool-ID
CLI overrides so every configurable selector remains available for one-off
use. A configured base URL must be an HTTPS origin without credentials, query,
or fragment; it is not a place for signed launch URLs or tokens.

Unknown `[integrations.panopto]` keys and type mismatches fail before secret
resolution or LTI launch. An explicit selector replaces the configured
selector; defining both name and ID at the same precedence layer remains an
error.

The private manifest records the effective non-authorizing integration
settings, but continues to omit viewer, launch, session, verifier, and signed
URLs.

### Interrupted-bundle policy

Replace unique-name recovery with deterministic reconciliation:

1. `artifact-manifest.json` remains the bundle commit marker and is written
   last.
2. When the marker is absent, danvas inventories existing caption/data-sidecar
   pairs before network access.
3. A valid pair whose sidecar hash matches and whose `session_id` matches one
   requested session is reused as `reused_after_interruption`.
4. Missing sidecars, hash mismatches, duplicate session identities, unexpected
   extra artifacts, or a filename collision belonging to another session are
   blockers. Danvas neither deletes nor renames around them.
5. New captions use no `-2`, `-3`, or similar implicit collision suffix.
6. The final manifest includes both reused and newly downloaded rows and commits
   only after every declared pair is valid.

If a completed bundle already has a manifest, no-clobber remains the default.
`--overwrite` retains its explicit meaning, but replacement must not weaken
pair validation or silently keep stale rows. A crash at any point leaves either
a previously valid completed bundle or an incomplete bundle that the next run
can reconcile or reject safely.

No live Panopto acceptance is required by default. Fixtures must model complete,
interrupted, tampered, ambiguous, and collision cases. Any real protected-media
check requires separate authorization and private evidence handling.

## 5. Compatibility Removals And Small Correctness Work

### Options due for removal

Remove these options from the `0.18.0` Click surface:

- `assignments overrides-sync --live`; use `--apply --confirm apply`;
- `discussions score --upload`; the command remains plan-only and the generated
  CSV is applied with `grades post`.

They must fail as unknown options during parsing, before project resolution,
authentication, output creation, or Canvas access. The migration guide includes
before/after commands and notes the deliberate nonzero behavior of the old
spelling.

### Roster legacy schema

Keep `roster --schema legacy-v1` throughout `0.18.0`, satisfying the Sprint 19
compatibility promise. Update its warning and public documentation to say it is
removed in `0.19.0`. The accepted Sprint 22 interface design absorbs that
removal and requires its help/guides to expose only `LoginID`.

No new compatibility alias replaces `legacy-v1`. Internal readers continue to
accept both headers during `0.18.0` so operators can consume retained artifacts
created by earlier releases.

### Init timezone ordering

Validate an explicit `danvas init --timezone` as an IANA zone before resolving
Canvas context, loading credentials, or making a network call. Canvas/profile
fallback values retain their existing ordering and validation behavior.

An invalid explicit value must leave `.danvas/` and `.gitignore` untouched and
must be testable with authentication and network entry points set to fail if
called.

### Placeholder and path cleanup

Adopt one public fixture convention:

- Canvas hosts use `https://canvas.example.edu/`;
- course, assignment, file, and user IDs use small internally consistent
  placeholders such as `101`, `202`, and `303`;
- public paths use project-relative examples or neutral POSIX examples; and
- reusable examples never use a maintainer home, mount, course repository, or
  external skill path.

Replace the remaining `auburn.instructure.com` test fixture and real-looking
IDs in executable fixtures where the magnitude has no test purpose. Current
README, configuration, migration, backlog examples, and machine-consumed docs
receive the same review.

Historical sprint acceptance records may name Auburn or a sandbox course when
that fact is necessary to explain field evidence. They must not reproduce
student data, access URLs, or unnecessary object IDs. This is a current-tree
cleanup only; it does not rewrite Git history.

`PROJECT_CONTEXT.md` remains current maintainer documentation, but the public
authority chain ends inside the repository. It must not require a personal
filesystem path or external Codex skill for installation, use, contribution,
or release verification.

## 6. Distribution And Package Metadata

### Distribution identity

Change `[project].name` from `danvas` to the reviewed `danvas-cli` before the
beta candidate is built. Preserve:

```toml
[project.scripts]
danvas = "danvas.cli:main"

[tool.uv.build-backend]
module-name = "danvas"
```

Build metadata and installed-package tests must prove that the selected
distribution imports `danvas`, installs exactly one `danvas` executable, and
reports version `0.18.0` through package metadata.

Because this changes distribution identity, the migration guide must give exact
`uv tool list`, uninstall-old-distribution, install-new-distribution, and
verification commands. The process must not rely on `--force` replacing a tool
owned by a differently named distribution.

### Metadata

Complete `pyproject.toml` with:

- `requires-python = ">=3.12,<3.15"`;
- SPDX license expression `MIT` and `LICENSE` inclusion;
- reviewed author/maintainer metadata;
- repository, issues, documentation, and changelog URLs;
- keywords and topic classifiers;
- Python 3.12, 3.13, and 3.14 classifiers;
- POSIX, Linux, and macOS classifiers; and
- the existing `danvas` import and command declarations.

Do not add the deprecated license classifier when using the SPDX license
expression. Wheel and source-distribution inspection must verify the rendered
metadata and included license.

### Anonymous installation

The primary public installation uses an exact Git tag over anonymous HTTPS:

```bash
uv tool install \
  "danvas-cli @ git+https://github.com/olearydj/danvas.git@v0.18.0"
```

Candidate smoke uses an exact full commit SHA. SSH remains an optional
contributor workflow, not the user quickstart. No branch, floating tag, local
checkout, editable install, maintainer cache, or external skill may be required.

PyPI publication, GitHub Release creation, tag creation, and global tool
replacement remain separately authorized release actions. Sprint completion
does not require publishing the distribution to PyPI.

## 7. Public Documentation Suite

### Entry points

Reshape the documentation surface to:

- `README.md`: concise status, capabilities, anonymous installation,
  five-minute setup, plan/apply warning, privacy warning, support matrix, and
  links;
- `docs/configuration.md`: profiles, project config, source layouts, inventory
  policy, Panopto settings, and precedence;
- `docs/authentication.md`: token references, `secretpath`, environment
  fallbacks, profiles, and offline doctor behavior;
- `docs/privacy.md`: artifact classes, private roots, permissions, terminal
  limits, tracking guidance, and retention responsibility;
- `docs/compatibility.md`: Python/OS/Canvas scope, gradebook heading profile,
  QTI/Panopto limits, and deprecations;
- `docs/authored-sources.md`: supported source formats, standard/legacy layouts,
  configuration, provenance, and source linting;
- `docs/mutation-safety.md`: plan/apply, confirmation guards, notification
  review, evidence states, uncertainty, and safe retry behavior;
- `CHANGELOG.md`: release-oriented changes beginning with the public-readiness
  program and links to detailed migrations;
- `CONTRIBUTING.md`: environment setup, tests, architecture gates, safe fixture
  rules, and no-live-Canvas default; and
- `SECURITY.md`: supported release policy and a verified private vulnerability
  reporting path.

`docs/course-yaml.md` remains the detailed course-policy reference and gains the
gradebook alias schema. Sprint and backlog documents remain design/history, not
required user instructions.

### Public claims

Public docs must state:

- `0.18.0` is a beta, not 1.0 stability;
- the project is unofficial and is not affiliated with or endorsed by
  Instructure;
- only Linux and macOS on Python 3.12 through 3.14 are supported;
- Windows is unsupported because the private-artifact contract is POSIX-only;
- Panopto is experimental and deployment-dependent;
- English Canvas gradebook headings are tested and other headings require
  explicit aliases;
- Canvas administrators may impose permissions or policies danvas cannot
  bypass; and
- operators remain responsible for institutional data handling and retention.

README examples use one coherent placeholder course and never depend on the
backlog, historical sprint notes, personal files, or an agent skill.

### Documentation checks

Add a repository-local Markdown/link check with one documented invocation. It
must validate relative links and anchors across README and the public guide set
without requiring network access. External links receive a bounded release-time
review rather than making ordinary CI depend on the availability of third-party
sites.

The installed wheel must include any documentation referenced by installed
help. Repository-only contribution/history docs need not ship in the wheel.

## 8. Platform, CI, And Repository Security

### Supported matrix

Linux CI runs the full gate on Python 3.12, 3.13, and 3.14. Ruff retains
`target-version = "py312"` because that is the minimum syntax target.

A `macos-latest` Python 3.13 lane runs:

- the full test suite;
- explicit private-artifact, report, source-map, download containment, and
  Panopto interruption tests;
- wheel build and isolated installed-CLI smoke; and
- permission assertions proving private directories/files are `0700`/`0600`
  from creation under restrictive and permissive umasks.

The release does not claim Windows support and adds no Windows runner.
Unsupported platforms must fail clearly before promising POSIX permissions.

### Workflow hardening

Set workflow-level permissions to:

```yaml
permissions:
  contents: read
```

No current job needs a write scope. Any future exception is granted on the
smallest individual job and requires review.

Every external `uses:` reference is pinned to a full-length commit SHA with a
comment naming the reviewed upstream release. Implementation resolves the SHA
from the action's authoritative repository and verifies it belongs to that
repository; it does not copy a SHA from an untrusted example. Dependabot may be
configured for GitHub Actions updates, but an update still requires review.

Keep `pull_request`, `push`, and signed-tag gates unprivileged. Do not introduce
`pull_request_target`, repository secrets, self-hosted runners, or publish
permissions for this sprint.

### Secret scanning

Use a pinned Gitleaks CLI release through one repository script and CI job. The
script runs two explicit modes:

- `gitleaks dir` for the current working tree; and
- `gitleaks git` with all reachable refs for history.

CI fetches full history only for this job. Findings are redacted and are not
uploaded as public artifacts. A `.gitleaks.toml` may extend default rules, but
allowlisting must be fingerprint-, line-, or narrowly path-specific with an
adjacent rationale. Broad allowlists for tests, docs, URLs, or the Auburn name
are forbidden.

Before beta release, every finding is adjudicated as:

- actual secret: stop, rotate/revoke, assess exposure, and separately decide
  whether history coordination is warranted;
- protected/private data: stop and obtain the required privacy review; or
- false positive: add the smallest reviewed allowlist with no secret value in
  the explanation.

A zero-finding scan does not prove that no secret ever existed, but it is a
repeatable release gate. The existing decision against rewriting history for
ordinary identity or institutional breadcrumbs remains unchanged.

## 9. Beta Threshold Audit

Create a release checklist that maps every public-beta threshold item to code,
tests, documentation, and exact release evidence. The audit must cover Sprints
18 through 21 rather than reviewing only this diff.

Required independent checks are:

1. a command/config/output inventory confirming no instance, privacy, or
   mutation boundary regressed;
2. a clean-machine anonymous HTTPS install from the exact candidate commit;
3. version, root help, offline `auth doctor`, and representative local-only help
   outside the checkout;
4. a new-project standard-layout quickstart using only placeholders and no
   Canvas mutation;
5. an existing-project legacy-layout migration fixture;
6. Linux and macOS private-artifact evidence;
7. package metadata and wheel-content inspection;
8. local public-document link validation;
9. current-tree and reachable-history secret scans with adjudication; and
10. an independent public-boundary review that explicitly approves or rejects
    the beta claim.

No live Canvas mutation is required. If implementation uncovers a changed
Canvas-observable behavior that fixtures cannot establish, it must be proposed
as a separately authorized bounded probe before release.

## Compatibility And Migration

Publish `docs/migrations/0.18.0.md` with exact before/after examples for:

- new `standard-v1` initialization;
- unchanged implicit `legacy-v1` behavior in existing projects;
- explicit layout selection and `init --force` preservation;
- configuration-derived status output directories;
- extending versus replacing file-inventory convenience ignores;
- gradebook heading aliases and unknown-heading diagnostics;
- Panopto configuration and interrupted-bundle reconciliation;
- removal of override-sync `--live`;
- removal of discussion-score `--upload`;
- retention of roster `legacy-v1` through `0.18.0` and removal in `0.19.0`;
- distribution-name migration for existing uv tool installations;
- anonymous HTTPS installation;
- the Python `<3.15` upper bound and POSIX-only support; and
- public documentation replacements for maintainer-oriented README sections.

The migration guide must not tell operators to delete an incomplete Panopto
bundle, move source files before changing configuration, or uninstall the old
distribution until the replacement command and rollback path are explicit.
It must also explain that skipping `uv tool uninstall danvas` can leave two
different distributions claiming the same `danvas` executable; uv may refuse
the install or leave command ownership/shadowing that must not be treated as a
successful migration. Verification must inspect `uv tool list`, the executable
path, and `danvas --version` after installing `danvas-cli`.

Existing project config, relative source maps, v1/v2 reports, private artifacts,
and English gradebook policy files remain readable. No schema is silently
rewritten merely to claim beta readiness.

## Implementation Sequence

### Group 0: review decisions and characterization

1. [x] Record the reviewed `danvas-cli` distribution name and dated PyPI
   evidence in this document.
2. [x] Accept the proposed source-layout transition.
3. [x] Review Sprint 22's design against the chosen distribution, source, help,
   and roster-deprecation surface; feed back only necessary Sprint 21 interface
   amendments.
4. [x] Freeze source, inventory, gradebook, Panopto interruption,
   deprecated-option, package, documentation, CI, and current-tree breadcrumb
   baselines.

Group 0 is complete. Commit `ded6b2e` adds an explicit public-boundary baseline
and the missing executable Panopto interruption counterexample without changing
runtime behavior. The exact gate passed 776 tests at 84.70% branch coverage,
the authored-assets module floor, Ruff, ty, frozen-lock validation, and the
dependency audit. Independent review accepted Group 1 on 2026-08-13.

### Group 1: project generalization

1. [x] Add named source layouts, init selection/materialization, force-preservation,
   and configuration-derived next actions.
2. [x] Split mandatory and convenience inventory exclusions and add replacement
   mode.
3. [x] Validate explicit init timezones before context/network access.
4. [x] Replace maintainer fixture URLs, IDs, paths, and reusable examples according
   to the placeholder policy.

Group 1 is implementation-complete in three reviewed-scope commits:

- `f2a94bc` adds immutable source layouts, init materialization and preservation,
  canonical source validation, and shared status/sync output resolution;
- `7f23193` separates mandatory inventory machinery from replaceable convenience
  ignores and records the effective policy in report output; and
- `c826e88` validates explicit init timezones before Canvas context and replaces
  reusable institutional hosts, maintainer paths, and real-looking fixture IDs.

The exact local gate passed 797 tests at 84.90% branch coverage, the
authored-assets module floor at 88.87%, Ruff, ty, frozen-lock validation, and
the dependency audit. Independent review accepted Group 1 on 2026-08-13 and
cleared Group 2 to proceed.

### Group 2: parser and integration boundaries

1. [x] Add gradebook heading aliases, ambiguity checks, and bounded diagnostics.
2. [x] Add Panopto configuration precedence and deterministic interrupted-bundle
   reconciliation.
3. [x] Remove `--live` and `--upload`; update the roster legacy warning to the
   fixed `0.19.0` removal.

Group 2 is implementation-complete in three reviewed-scope commits:

- `e95fa9b` adds canonical gradebook heading roles, project-configured aliases,
  ambiguity rejection, and bounded diagnostics; it also rejects simultaneous
  singular and plural source-kind tables explicitly;
- `c7eec56` adds validated Panopto project settings and CLI precedence, exact
  tool selection, and deterministic hash-checked interrupted-bundle
  reconciliation without duplicate downloads; and
- `cc18fd8` removes the due `--live` and `--upload` compatibility spellings and
  pins the roster `legacy-v1` warning to its `0.19.0` removal.

The exact local gate passed 815 tests at 84.99% branch-aware coverage, the
authored-assets module floor at 88.87%, Ruff, ty, frozen-lock validation, and
the dependency audit. Independent review accepted Group 2 on 2026-08-13 and
cleared Group 3 to proceed.

### Group 3: package and public docs

1. [x] Adopt the reviewed distribution name and complete package metadata.
2. [x] Add anonymous candidate/tag install smoke and distribution migration
   tests.
3. [x] Build the public guide suite, shorten README, add the changelog and
   contribution/security policies, and remove external maintainer paths from
   the authority chain.
4. [x] Publish the `0.18.0` migration guide and local documentation checker.

Group 3 is implementation-complete in six reviewed-scope commits:

- `701acc0` adopts the `danvas-cli` distribution identity, `0.18.0` candidate
  metadata, Python upper bound, SPDX license declaration, archive inspection,
  and renamed editable/wheel release smoke;
- `8ef1e4e` adds the isolated exact-SHA/exact-tag anonymous HTTPS installation
  smoke and distribution-shadowing guard;
- `61b9d2b` closes the accepted Group 1 import tidy-up without introducing a
  module cycle;
- `0a41757` and `d360727` harden exact-version validation and keep the invalid
  ref fixture within the public placeholder policy; and
- `7dc5681` publishes the public guide suite, concise README, changelog,
  contribution and security policies, `0.18.0` migration guide, and offline
  local-link/anchor checker.

On 2026-08-13, the repository API first reported private vulnerability
reporting disabled. After separate operator authorization, the setting was
enabled and a second API read returned `{"enabled": true}`. `SECURITY.md`
therefore points to a verified repository security-advisory route rather than
inventing or publishing a personal security contact. External availability is
reviewed at release time; the ordinary documentation gate remains offline.

The exact local gate passed 827 tests at 84.99% branch-aware coverage, the
authored-assets module floor at 88.87%, Ruff, ty, frozen-lock validation, the
dependency audit, all 12 public-document Markdown/link checks, distribution
archive inspection, and isolated editable/wheel installation smoke. The
anonymous installer is structurally tested against exact SHA/tag and legacy
shadowing cases; the real exact-candidate and tag runs remain Group 5 release
gates after those refs exist remotely. Independent review accepted Group 3 on
2026-08-13 and cleared Group 4 to proceed.

### Group 4: CI and security

1. [x] Add Python 3.13 and the macOS lane.
2. [x] Set minimal workflow permissions and pin every action to a verified full
   SHA.
3. [x] Add the pinned current-tree/history secret-scan script and CI job.
4. [x] Run all existing quality, build, audit, and installation gates.

Group 4 is implementation-complete in `6b92ddd`. The workflow now runs the
frozen full gate on Linux Python 3.12, 3.13, and 3.14; runs the full suite,
focused POSIX privacy/recovery checks, dependency audit, build, and isolated
installation smoke on macOS Python 3.13; and makes both platform families
prerequisites of the final install-smoke job. Workflow permissions are
explicitly `contents: read`, pull-request CI uses no repository secret or
privileged event, and all external actions use reviewed immutable references:
`actions/checkout` `v7.0.1` at
`3d3c42e5aac5ba805825da76410c181273ba90b1` and `astral-sh/setup-uv` `v9.0.0`
at `c771a70e6277c0a99b617c7a806ffedaca235ff9`.

The repository-owned secret-scan script downloads Gitleaks `8.30.1` from its
official release, verifies the platform archive against the reviewed published
SHA-256, emits fully redacted terminal output, retains no report, and scans
both the working tree and all reachable history through `--log-opts=--all`.
The real pinned tool found no leak in either scope on 2026-08-13. The local
quality gate passed 831 tests at 84.99% branch-aware coverage, the
authored-assets module floor at 88.87%, Ruff, ty, frozen-lock validation, the
dependency audit, the 12-document offline checker, the focused 95-test POSIX
privacy/recovery matrix, and isolated sdist/wheel installation smoke. Focused
review accepted Group 4 on 2026-08-13 after independently resolving both action
SHAs and all four Gitleaks archive checksums against their authoritative
upstreams. Exact-commit remote CI remains open before Group 5 may begin.

### Group 5: beta audit and release

1. Run the clean-machine quickstart and cross-release beta matrix.
2. Obtain an independent public-boundary review and close every finding.
3. Push the exact candidate and require branch CI on that SHA.
4. Tag `v0.18.0` only after review and branch gates pass.
5. Require signed-tag CI and anonymous exact-tag install before the global CLI
   advances or public docs call the release complete.

Each group lands in logical commits. Groups 1 through 3 receive focused review
before CI/security hardening and the beta-claim audit build on their contracts.

## Automated Acceptance

### Source layouts and status

- New init without `--source-layout` writes a complete `standard-v1` config.
- New init can explicitly materialize `legacy-v1`.
- Existing source-less config resolves exactly as the `0.17.0` legacy defaults.
- Existing mixed custom config inherits unspecified kinds from `legacy-v1`.
- `init --force` without a layout preserves the effective source config and
  unrelated supported tables.
- No source layout is inferred from existing directories or filenames.
- Standard fixtures discover ordinary assignment, announcement, discussion,
  quiz, and Page sources without case/chapter naming.
- Status sync suggestions use configured output directories or name the missing
  key; no fixed maintainer output path remains.
- Sync commands without an explicit output use the same configured directory
  and resolve it before Canvas context or authentication.
- All configured paths reject absolute values and parent traversal.
- Touched source tables reject unknown keys after honoring existing
  compatibility spellings.

### Inventory

- Existing config omission retains the current convenience exclusions.
- `use_default_ignores = false` includes a fixture beneath `grading/` and
  `_archive/` while still excluding `.git/`, `.danvas/`, and active outputs.
- Custom ignores work in both extend and replace modes.
- Reports record the effective policy and do not claim disabled exclusions.
- Invalid modes, unknown keys, and unsafe patterns fail before filesystem
  traversal.

### Gradebook

- Existing English fixtures remain bit-for-bit compatible.
- Configured aliases cover metadata, points, final score, final grade, and group
  total roles.
- One alias cannot satisfy multiple canonical roles.
- Duplicate observed role matches fail with bounded diagnostics.
- Unknown-heading failures show roles/aliases/headings but no student row data.
- Existing `final_score_column`, exclusion, weights, and reconstruction policies
  remain compatible.

### Panopto

- Explicit CLI selectors outrank project config, which outranks experimental
  defaults.
- Ambiguous/unknown tool configuration and unsafe base URLs fail before secret
  resolution or LTI launch.
- An interrupted valid pair is reused by session ID without a second download.
- Missing/tampered/duplicate sidecars and cross-session filename collisions are
  blockers and create no suffixed duplicate.
- The manifest commits last and distinguishes reused and downloaded rows.
- Private permissions and URL-redaction tests from Sprint 19 remain green.

### Deprecations and ordering

- `--live` and `--upload` are absent from help and rejected before context,
  output, auth, or network calls.
- Replacement `--apply --confirm apply` and `grades post` workflows remain
  covered.
- Roster `legacy-v1` remains functional, warns about `0.19.0` removal, and does
  not relabel the value in the default schema.
- Invalid explicit init timezones fail before authentication/network and write
  no project state.
- Executable fixtures and current public examples use only the placeholder
  host/ID/path convention.

### Packaging and docs

- The reviewed distribution builds an sdist and wheel containing `LICENSE` and
  valid static metadata.
- The wheel imports `danvas`, installs exactly one `danvas` command, and reports
  `0.18.0`.
- `Requires-Python` is `>=3.12,<3.15`; classifiers match tested platforms and
  versions.
- Anonymous HTTPS candidate/tag installation passes outside the checkout.
- README and every public guide use internal relative links that pass the local
  checker.
- Public docs state beta, unofficial status, privacy/mutation boundaries,
  compatibility limits, experimental Panopto, and security reporting.
- No public authority document requires a maintainer path, SSH credentials,
  course repository, or external agent skill.

### CI and security

- Linux Python 3.12, 3.13, and 3.14 pass the frozen full gate.
- macOS Python 3.13 passes the full suite, private-artifact checks, build, and
  isolated install smoke.
- Workflow permissions are explicitly read-only.
- Every external action reference is a full SHA with a reviewed version comment.
- Current-tree and all-reachable-history secret scans run with one pinned tool
  version and zero unadjudicated findings.
- Pull-request CI needs no repository secrets and uses no privileged event or
  self-hosted runner.

### Regression and beta release

- The 55-command access registry remains exact unless an independently reviewed
  interface change updates it.
- No private-output or mutation assertion site is lost.
- Ruff, ty, lock validation, dependency audit, branch coverage, complexity,
  import-cycle, build, editable/wheel, and exact-install gates remain green.
- The cross-release threshold has one evidence link per requirement.
- Independent review explicitly accepts the public-beta claim on the exact
  release commit.

## Bounded Acceptance

The normal Sprint 21 acceptance path is entirely local, CI-based, or read-only.
It uses isolated temporary homes/config roots and no maintainer credentials.

The clean-machine case must prove:

1. anonymous installation from the exact candidate;
2. `danvas --version`, `danvas --help`, and offline `danvas auth doctor`;
3. a local new-project configuration render for `standard-v1` using fixtures;
4. no discovery of personal config, SSH keys, course paths, or installed agent
   skills; and
5. clean uninstallation/reinstallation across the distribution-name migration.

No live Canvas or Panopto operation is authorized by this design. Any proposed
live case must identify the single changed remote semantic, the disposable
target, retained private evidence, cleanup boundary, and why fixtures are
insufficient.

## Non-Goals

- PyPI publication, GitHub Release creation, package-name reservation, tagging,
  or global CLI replacement without separate release authorization;
- Windows support or emulating POSIX private permissions on Windows;
- broad internationalization or shipping translated gradebook profiles without
  fixtures;
- moving, renaming, or generating authored course files during init;
- a Panopto plugin system, another recording provider, or changes to protected
  media access behavior;
- automatic deletion of incomplete Panopto artifacts;
- removing roster `legacy-v1` before `0.19.0`;
- Sprint 22 help, guide registry, machine description, skill packaging, or skill
  installation implementation;
- Page assets, grouped-case setup, gradebook export, or another Canvas feature;
- rewriting Git history for maintainer identity or public institutional context;
  or
- a broad CLI rewrite unrelated to the public-beta boundary.

## Resolved Design Decisions

- New projects use a materialized `standard-v1`; existing projects retain
  legacy behavior unless they opt in.
- Layouts are versioned and never inferred from repository contents.
- File-inventory safety exclusions remain mandatory; maintainer convenience
  exclusions become replaceable.
- Gradebook aliases extend one tested English profile through course policy
  YAML and do not imply general locale support.
- Panopto remains bundled but experimental and gains deterministic interrupted
  recovery instead of unique-name duplication.
- Override `--live` and discussion-score `--upload` are removed in `0.18.0`.
- Roster `legacy-v1` remains for `0.18.0` and is removed in `0.19.0`.
- The beta supports Linux and macOS on Python 3.12 through 3.14; Windows and
  Python 3.15 are unsupported.
- CI uses least-privilege read access and immutable action SHAs.
- Gitleaks runs separate current-tree and all-reachable-history scans.
- Historical identity breadcrumbs do not trigger a history rewrite.
- Sprint 22 design review followed Sprint 21 design acceptance and is complete
  before Sprint 21 implementation.
- The Python distribution is `danvas-cli`; the import package and executable
  remain `danvas`.

Independent review also accepted the source transition, narrow mandatory
inventory exclusions, bounded alias schema, Panopto refusal-first recovery,
complete macOS lane, two-mode Gitleaks gate, and public guide set. The completed
Sprint 22 review owns the roster removal and current-interface refresh together.

One release-time audit question intentionally remains: after all exact-commit
evidence is assembled, does `0.18.0` satisfy the seven-part public-beta
threshold without qualification beyond the documented beta limits?

## Definition Of Done

Sprint 21 is complete only when:

- the `danvas-cli` distribution decision and current availability are rechecked;
- workflow conventions are explicit, versioned, and compatibility-tested;
- public installation needs no maintainer credential or path;
- package identity and metadata are internally consistent;
- public docs form a self-contained user/contributor/security surface;
- Linux/macOS and Python support exactly match CI;
- workflow permissions/actions and secret scanning meet the reviewed security
  contract;
- all Sprint 18 through 21 beta-threshold evidence is current;
- independent review accepts the implementation and beta claim; and
- exact branch, signed-tag, anonymous install, and global replacement gates pass
  in that order.

## Release Contract

The target is `0.18.0`, the first release permitted to use the public-beta
label. The release commit must pass the full local gate, independent review,
clean-machine quickstart, platform matrix, documentation check, package
inspection, and secret scans before tagging.

After the exact candidate is pushed and branch CI is green, create a signed
`v0.18.0` tag. Require tag CI and anonymous exact-tag installation before
replacing the global CLI or recording the release complete. Any PyPI
publication or GitHub Release remains a separately authorized action.

## Reference Basis

- [PyPA `pyproject.toml` metadata specification][pyproject-spec]
- [GitHub Actions secure-use guidance][github-actions-security]
- [Gitleaks scanning modes and configuration](https://github.com/gitleaks/gitleaks)
- [Existing PyPI project named `danvas`](https://pypi.org/project/danvas/)

[pyproject-spec]: https://packaging.python.org/en/latest/specifications/pyproject-toml/
[github-actions-security]: https://docs.github.com/en/actions/reference/security/secure-use
