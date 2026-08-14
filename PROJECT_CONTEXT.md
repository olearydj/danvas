# Project Context

## Purpose

`danvas` is a safety-focused operational Canvas CLI for day-to-day course work:
rosters, assignments, submissions, grading, discussions, announcements, Canvas
Pages, files, recording captions, status reports, source linting, and local audit
workflows. It is an unofficial public-beta project and is not affiliated with or
endorsed by Instructure.

Keep `danvas` separate from archival/history tooling such as Canvas ledger
databases. It should produce useful operational evidence through reports,
manifests, and explicit outputs without becoming the long-term course-history
system.

## Documentation Map

- `README.md`: public quickstart, installation, major workflows, and safety
  posture.
- `CHANGELOG.md`: released operator-visible changes.
- `docs/configuration.md`, `authentication.md`, `privacy.md`,
  `compatibility.md`, `authored-sources.md`, and `mutation-safety.md`: public
  contracts for configuration, credentials, retained data, supported platforms,
  source layouts, and Canvas writes.
- `docs/migrations/`: version-specific compatibility and upgrade instructions.
- `docs/course-yaml.md`: narrow reference for optional audit policy and exact
  gradebook heading aliases.
- `docs/backlog.md`: only work that remains to be done or reconsidered. Completed
  and rejected work belongs in sprint records, migrations, the changelog, and git
  history rather than this file.
- `docs/sprints/`: accepted design and implementation records. These explain why
  current contracts exist but are not the active task list.
- `.github/workflows/ci.yml`: supported-platform verification authority.
- `.github/workflows/publish-pypi.yml`: manually dispatched, protected Trusted
  Publishing path for already-built GitHub Release distributions.
- `.ho/`: transient session handoffs. Read the latest relevant note for restart
  state, but do not treat handoffs as durable project documentation.

## Source Map

- `src/danvas/cli.py`: Typer command tree and option adapters.
- `src/danvas/access.py`: exact typed Canvas/local/mutation policy for every leaf
  command.
- `src/danvas/artifacts.py`: exact retained-output classification and the central
  private-artifact filesystem boundary.
- `src/danvas/mutation.py`: shared plan/apply mode and fail-closed pre-write
  assertion.
- `src/danvas/command_guides.py`, `help_rendering.py`, `offline_guides.py`, and
  `command_description.py`: semantic command guidance, progressive help, offline
  guides, and deterministic `danvas-command-guide-v1` JSON.
- `src/danvas/_skill/`, `skill_resources.py`, and `skill_installer.py`: canonical
  packaged Agent Skill, resource identity, and bounded no-clobber installation.
- `src/danvas/auth.py`: resolved-credential Canvas client creation and offline
  authentication diagnostics.
- `src/danvas/credentials.py`: provider-neutral environment/file credential
  selection, origin binding, descriptor-safe file reads, and redacted results.
- `src/danvas/profiles.py`: user profile loading plus profile, instance,
  timezone, and credential-locator precedence.
- `src/danvas/timezones.py`: bounded Canvas/Rails-to-IANA timezone mapping.
- `src/danvas/config.py`, `project_config.py`, and `source_layouts.py`: project
  initialization, `.danvas` configuration, versioned source layouts, and course
  snapshots.
- `src/danvas/sources.py`, `source_map.py`, and `source_lint.py`: authored-source
  discovery, project-contained provenance, and local Canvas-facing validation.
- `src/danvas/reports.py`: report-run directories, manifest v2, and dual-root
  report discovery.
- `src/danvas/sanitize.py`: dependency-free sensitive-key, error-text, and
  retained-evidence sanitization shared across command families.
- `src/danvas/authored_content.py`: shared field-policy, scalar, sequence, and
  timezone-aware datetime comparison primitives.
- `src/danvas/authored_assets.py`, `asset_state.py`, and `canvas_links.py`:
  assignment asset planning/deployment, stable state, safe upload/reuse, and
  Canvas link normalization.
- `src/danvas/assignment_sources.py`, `page_sources.py`,
  `discussion_sources.py`, and `frontmatter.py`: typed authored-source parsing
  and rendering.
- `src/danvas/assignments.py`, `announcements.py`, `discussions.py`, and
  `pages.py`: Canvas object operations and readback verification.
- `src/danvas/status.py` and `snapshot_collections.py`: read-only local-vs-Canvas
  status and authority-aware collection snapshots.
- `src/danvas/overrides.py` and `override_sync.py`: redacted override summaries,
  explicit private membership, and guarded reconciliation.
- `src/danvas/courses.py`, `gradebook.py`, `assignment_audit.py`, `grades.py`,
  `submissions.py`, and `grade_evidence.py`: private roster/grading workflows,
  typed transaction evidence, reconciliation, and recovery.
- `src/danvas/files.py`: Canvas Files inventory, targeted comparison, contained
  downloads, and non-destructive-by-default upload.
- `src/danvas/quiz_import.py` and `quiz.py`: QTI import and local quiz analysis.
- `src/danvas/panopto.py`: experimental Panopto caption discovery/download
  through Canvas LTI with private interrupted-bundle reconciliation.
- `tests/`: command-tree architecture checks and behavioral coverage.
- `scripts/`: documentation, distribution, release-smoke, quickstart, coverage,
  and current-tree/history secret-scan gates.

## Release And Verification

`pyproject.toml` is the version source. The Python distribution is
`danvas-cli`; the installed command and import package remain `danvas`.
`danvas --version` and `danvas.__version__` read installed distribution
metadata.

Current public beta: `0.20.0`. Signed tag `v0.20.0` resolves to
`83c6a43520a3ddf36b8aff32f578f439c8ecaafe`. The global CLI reports
`danvas 0.20.0` outside the checkout. The GitHub prerelease carries one wheel,
one source distribution, and `SHA256SUMS`; the same distributions are published
as [`danvas-cli 0.20.0`](https://pypi.org/project/danvas-cli/0.20.0/) through
PyPI Trusted Publishing with repository-linked attestations.

The public-readiness sequence is complete:

- `0.15.x`: institution-independent instance profiles, explicit URL/timezone
  resolution, and removal of runtime institutional defaults;
- `0.16.0`: central private-artifact boundary, retained-output classification,
  private manifest v2, and project-contained source maps;
- `0.17.0`: plan-on-omission mutation safety, shared pre-write assertions,
  reconciliation evidence, non-destructive upload conflicts, and feedback
  readback;
- `0.18.0`: public-beta packaging/generalization, versioned source layouts,
  replaceable inventory convenience ignores, supported Python/OS declarations,
  public documentation, macOS CI, and history/current-tree secret scans;
- `0.19.0`: provider-neutral credential delivery, hard origin binding, removal
  of SecretPath/dotenv/provider-specific options, and `LoginID`-only rosters;
  and
- `0.20.0`: progressive help, offline guides, deterministic description JSON,
  a portable generic Agent Skill, and bounded skill installation/diagnostics.

Supported runtime is Python `>=3.12,<3.15` on Linux and macOS. Windows is
unsupported because danvas cannot promise its POSIX private-file and atomic
installer contracts there.

CI runs Ruff, ty, dependency audit, branch coverage, Python 3.12/3.13/3.14,
macOS privacy/recovery and isolated-install gates, release smoke, and Gitleaks
against the current tree and all reachable history. Actions and downloaded
scanner artifacts are pinned. Keep `permissions` read-only by default and grant
OIDC only to the protected PyPI publish job.

Recommended local checks:

```bash
uv lock --check
.venv/bin/ruff check .
.venv/bin/ty check
.venv/bin/pytest
.venv/bin/python scripts/check-docs.py
scripts/release-smoke.sh --expected-version X.Y.Z
```

Use one synchronized/frozen environment and run its executables directly; do not
launch concurrent syncing `uv run` commands against the shared `.venv`. For a
release, push the exact candidate, require green branch CI, create the signed
tag, require tag CI, verify exact-tag installation, and only then advance the
global CLI and release records. GitHub Release creation and PyPI publication are
separately authorized actions.

PyPI publication is manual and artifact-first: the protected workflow downloads
the already-reviewed GitHub Release distributions, verifies tag/version/file
identity and checksums, then publishes only those files through OIDC. The
`pypi` environment normally admits `v*` tags only and requires maintainer review.
Do not add a long-lived PyPI token.

## Durable Decisions

- Keep the project unofficial, institution-neutral, and pre-1.0. No host,
  course, timezone, credential provider, or institutional identity is built in.
- Keep the public identity split stable: distribution `danvas-cli`, command and
  import package `danvas`. The unrelated PyPI project named `danvas` must never
  be overwritten or presented as this tool.
- Treat the Click tree, `ACCESS_POLICIES`, `ARTIFACT_POLICIES`, and command-guide
  registry as one reviewed interface. Exact-equality architecture tests must
  force review when a leaf, effect, or retained-output contract changes. Do not
  create a parallel effect/privacy vocabulary.
- Keep the installed CLI authoritative for humans and agents. Progressive help,
  offline guides, deterministic description JSON, and the packaged generic
  Agent Skill must agree and must remain constructible without project,
  credential, or network resolution.
- Keep the packaged skill institution- and provider-neutral. A personal or
  organizational skill may layer workspace triggers and policy on top, but must
  not become the public command authority.
- Canvas-changing commands plan on omission. Only `--apply` authorizes a Canvas
  write; `--dry-run` remains an explicit plan spelling. Local-write sync commands
  retain their separate dry-run/no-clobber contract and never gain `--apply`.
- Require the shared mutation assertion immediately before every Canvas write,
  including nested upload helpers. Architecture inventories must fail closed on
  new mutation call sites.
- Treat truthful evidence as a product invariant: every mutation attempt appears
  exactly once with the intent that drove it; mutation status remains distinct
  from evidence status; and indeterminate outcomes instruct the operator to
  verify before retrying.
- Danvas consumes one credential through one provider-neutral environment
  variable or one externally managed single-purpose file. It does not contact,
  configure, or diagnose secret providers and does not load dotenv files.
- User profiles may select a credential locator; project repositories may not.
  The effective HTTPS Canvas origin must be bound by a matching user profile,
  explicit `--api-url`, or matching `CANVAS_API_URL` before the credential is
  read. There is no origin-binding bypass.
- Once a credential locator wins precedence, an empty, missing, invalid, or
  unsafe value is final; never fall through to another source. Remove a selected
  environment entry before Canvas construction. File reads remain bounded,
  descriptor-based, project-external, and path-redacted.
- Keep generated snapshots, public reports, manifests, diagnostics, help, and
  description output free of tokens, credential-file paths, verifier-bearing
  URLs, and unmarked student-sensitive data.
- Classify retained outputs as `shareable`, `course_internal`, or `private`.
  Payloads inherit the most sensitive applicable class. Private outputs use the
  central artifact boundary, aggregate-only terminal behavior, no-clobber
  defaults, symlink rejection, and creation-time `0700`/`0600` permissions.
- Commit paired private data before its integrity sidecar, and treat a missing or
  mismatched sidecar as invalid rather than successful. A crash or handled
  failure may leave a detectably invalid pair; do not overclaim rollback.
- Keep `.danvas/` as generated operational state and evidence, not canonical
  authored course content. New generated private grading/export artifacts live
  beneath `.danvas/private/`; private report runs use
  `.danvas/private/reports/`. Legacy `.danvas/reports/` remains discoverable.
- Keep `content/` as authored instructional source. Source-sync commands may
  create missing files only when explicitly directed and must not overwrite by
  default.
- Source layouts are versioned contracts. New projects materialize
  `standard-v1`; existing projects without explicit source configuration retain
  `legacy-v1`. Never infer or silently migrate a layout from repository
  contents.
- Use `.danvas/source-map.json` for project-contained stable Canvas identity,
  safe provenance, timestamps, hashes, and comparable metadata. Reject absolute
  or out-of-project entries; never store tokens, verifier URLs, roster data,
  submissions, grades, private comments, or full student content there.
- For creates, retain returned Canvas identity before dependent writes or
  readback so a partial failure cannot create an unbound orphan and duplicate on
  retry. Finalize provenance only after the documented verification boundary.
- Keep comparison behavior field-specific. Free-text titles and bodies do not
  receive numeric coercion; booleans use a closed vocabulary; datetimes compare
  semantically only through explicit policies. Every supported authored field
  needs structural policy coverage and round-trip characterization tests.
- Require `Z` or an explicit UTC offset for authored `*_at` timestamps.
  Assignment date aliases expand through the configured course timezone; Page
  `publish_at` may be date-only; graded discussion dates remain explicit-offset
  only because Canvas silently ignores date-only values.
- Use the shared sanitizer for public errors and retained evidence. Preserve
  compound credential-name and signed-cloud detection while avoiding broad
  patterns that erase ordinary course prose.
- Snapshot collection authority remains explicit. An `available` empty
  collection is authoritative; `unavailable`, `failed`, or `partial` cannot
  prove absence. `InvalidAccessToken` is fatal and must not replace prior state.
- `danvas status` stays read-only and stdout-first by default. Saved report runs
  are opt-in for that command.
- Existing user-maintained `grading/` inputs remain supported. Keep local-file-
  first gradebook and quiz audit behavior; add live exports only for a concrete
  workflow and privacy contract.
- Gradebook heading configuration is exact, Unicode-preserving aliasing, not
  locale inference. Reject ambiguous role matches and keep diagnostics bounded
  to roles, aliases, and observed headings rather than rows.
- The current Page workflow remains bounded: safe Markdown/native HTML,
  restricted CSS, stable-ID create/update/readback, and one-way local source
  creation. Asset rewriting, lifecycle controls, front-page changes, and broad
  upsert remain separate designs. Accepted Sprint 23 now precedes the Page
  adapter because repeated field use exposed a missing supported path for
  acquiring Classic Quiz student-analysis CSVs. The Page-specific adapter over
  the existing assignment asset transaction remains the next major candidate.
- Page snapshot/sync canonicalizes stable Canvas links and blocks unresolved
  volatile or signed URLs before hashing or writing authored sources. The
  current profiles are `pages-html-v4` and `pages-markdown-v2`.
- Broad Canvas Files downloads treat Canvas path metadata as untrusted and
  enforce final resolved-path containment. Upload defaults to conflict rather
  than overwrite; unverifiable or race-renamed results are never reported as
  success.
- Panopto caption support remains experimental, private, and deployment-
  dependent. `artifact-manifest.json` is the final bundle commit marker;
  interrupted pairs are reconciled by session identity and hash without
  deleting or suffixing around unexpected content.

## Report Output Contract

Classify every new command before implementation:

- `report-run-first`: audits, verification, reconciliation, comparisons, and
  dry-run/readback evidence. These commands should save a report run by default
  when a course project is discoverable.
- `explicit-output`: raw exports, rosters, submissions, grades, downloads, and
  captions. These keep explicit output files or directories by default, except
  that the private subset may resolve safely beneath `.danvas/private/` when a
  project is discoverable.
- `stdout-first`: quick inspection commands. Preserve existing terminal behavior
  and add report output only through explicit report options.

Artifact sensitivity is orthogonal: `shareable`, `course_internal`, or
`private`. Private output uses the central boundary for no-clobber behavior,
classification metadata, bounded terminal output, and creation-time
permissions. Without a discoverable project, private explicit-output commands
require an explicit destination before Canvas access.

Report-run-first commands should normally support `--no-report`,
`--report-root`, `--report-dir`, and a command-specific slug. They should write
`manifest.json`, a command-specific JSON file, and Markdown when human review
matters. Report manifest v2 omits raw argv and absolute project/input/run paths.

Compatibility-sensitive commands such as `status` and `refresh --diff` preserve
default terminal behavior and write report runs only when explicit report
options are passed.

Tests for retained output should cover classification, destination resolution
before auth, option conflicts, no-clobber behavior, interrupted paths, failed
manifests when practical, and the absence of verifier URLs or unmarked private
student data.

## Recurring Pitfalls

- Do not run multiple syncing `uv run` commands concurrently against the same
  `.venv`. Perform one controlled `uv sync --locked` or `--frozen`, then use
  `.venv/bin/` executables sequentially.
- Typer/Rich output wraps and styles differently across terminals and CI. Test
  command structure through Click introspection; when output text itself is the
  contract, strip ANSI/Rich styling with `click.unstyle()` before comparison and
  pin bounded-width fixtures deliberately.
- macOS Unix-domain socket paths are short. Tests creating real sockets or FIFOs
  must use a short temporary root such as `/tmp`, not a long pytest path.
- A workstation-wide uv `exclude-newer` policy can reject a just-published PyPI
  release. For release verification, use an isolated no-cache tool directory and
  a package-scoped cutoff override rather than weakening global policy.
- PyPI files and long descriptions are immutable for a version. Finalize the
  public README before building/tagging; later repository documentation changes
  cannot alter the already-published project description without a new version.
- Course projects can override source discovery with `[sources.<kind>]` tables.
  Broad assignment globs require assignment metadata by default so support notes
  are not misclassified as assignments.
- Folder-ID uploads must validate course ownership before uploading. Upload and
  report errors must sanitize Canvas payloads and exception text because either
  can contain verifier-bearing or signed URLs.
- Canvas discussion/announcement APIs use write-side `specific_sections`, but
  readback needs `include=["sections"]` and canonicalized section IDs. Do not
  compare the write parameter against a default-empty topic response.
- Shared-helper extraction is compatibility work, not a clean-slate rewrite.
  Characterize surrounding behavior first and use generated cross-product tests
  when changes can shift between under-redaction and over-redaction.
- Keep tokens, credential values and paths, student data, private artifacts, and
  verifier-bearing URLs out of public documentation, source maps, durable
  context, and handoff notes.
