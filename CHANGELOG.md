# Changelog

This file records operator-visible release changes. Detailed transition steps
live in the linked migration guides.

## 0.21.0 - Classic Quiz Analysis Export

Sprint 23 closes the supported acquisition gap for Classic Quiz analysis:

- adds plan-by-default `quiz export-analysis` for Canvas's official identified
  `student_analysis` report;
- treats the report `POST` as a Canvas mutation requiring `--apply`, even though
  it changes no quiz content or grades;
- reconciles create-or-reuse, `409`, asynchronous progress, readback, and
  uncertain transport outcomes without blind retries;
- validates and commits the downloaded CSV as a private SHA-bearing artifact
  pair for the existing local `quiz analysis` consumer;
- excludes anonymous Surveys and New Quizzes from acquisition with explicit
  diagnostics; and
- teaches the human and agent interfaces that missing command coverage does not
  authorize direct API, browser, or provider-specific fallback.

Existing QTI import and local analysis behavior are unchanged. Bounded Canvas
field acceptance passed after correcting the report attachment lookup to use
Canvas's global file endpoint. Release remains gated on bounded agent
acceptance, independent exact-candidate review, and the established branch/tag
installation gates.

See [Migrating to 0.21.0](docs/migrations/0.21.0.md).

## 0.20.0 - Agent Interface

Sprint 22 makes the installed CLI the authoritative human and agent interface:

- adds progressive root, family, and leaf help derived from typed command
  semantics and the existing access/privacy registries;
- adds packaged offline task guides and deterministic
  `danvas-command-guide-v1` JSON discovery;
- packages one portable, provider-neutral `danvas` Agent Skill in editable,
  sdist, and wheel installations;
- adds explicit dry-run/install/doctor workflows for documented Codex, Claude
  Code, Gemini, Copilot, and shared skill locations; and
- protects skill installation with allowlisted paths, provenance and content
  hashes, no-clobber classification, and atomic whole-directory commits.

Canvas payloads, credentials, mutation behavior, and retained evidence schemas
are unchanged.

Released as signed tag `v0.20.0` after independent command-truth and installer
review, bounded Codex and Claude Code behavior acceptance, branch/tag platform
CI, anonymous exact-ref installation, and global CLI verification. The verified
release wheel and source distribution are also published as
[`danvas-cli 0.20.0`](https://pypi.org/project/danvas-cli/0.20.0/) through PyPI
Trusted Publishing with repository-linked attestations.

See [Migrating to 0.20.0](docs/migrations/0.20.0.md).

## 0.19.0 - Provider-Neutral Credentials

Sprint 21.5 moves provider choice outside danvas:

- replaces provider-specific authentication with selected environment-variable
  or single-purpose credential-file delivery;
- requires user-controlled binding between the effective Canvas origin and the
  credential before reading it;
- removes implicit dotenv loading and the SecretPath/python-dotenv dependencies;
- introduces the provider-neutral `danvas-auth-doctor-v1` diagnostic schema;
- removes the due alternate roster schema and retains `LoginID`-only exports;
  and
- documents optional external SecretSpec, 1Password, CI, and platform-mount
  patterns without making any provider a danvas dependency.

Released as signed tag `v0.19.0` after independent security review and exact
branch/tag, anonymous-install, and live read-only authentication gates.

See [Migrating to 0.19.0](docs/migrations/0.19.0.md).

## 0.18.0 - Public Beta

Sprint 21 completes the public-readiness program:

- changes the Python distribution name to `danvas-cli` while preserving the
  `danvas` command and import package;
- declares Python 3.12 through 3.14 and Linux/macOS support;
- adds versioned `standard-v1` and `legacy-v1` authored-source layouts;
- materializes new-project source configuration and derives status/sync paths
  from it;
- makes file-inventory convenience ignores replaceable while retaining
  mandatory machinery exclusions;
- adds exact gradebook heading aliases with ambiguity rejection;
- adds configurable experimental Panopto selection and deterministic
  interrupted-bundle reconciliation;
- removes the due `--live` and `--upload` compatibility options;
- completes package metadata, anonymous HTTPS installation, public guides,
  macOS/Python CI coverage, and repository security gates; and
- audits the cross-release privacy, mutation, installation, and support
  threshold before applying the public-beta label.

See [Migrating to 0.18.0](docs/migrations/0.18.0.md).

## 0.17.0 - Plan And Reconciliation

Sprint 20 made omission safe across the Canvas-writing surface. Fifteen
mutation-capable commands plan by default and require `--apply`; transaction
families retain bounded evidence and stop after unsafe outcomes. Discussion
scoring now emits a private grade plan consumed by `grades post`.

See [Migrating to 0.17.0](docs/migrations/0.17.0.md).

## 0.16.0 - Private Artifacts

Sprint 19 established the private-artifact boundary: protected defaults beneath
`.danvas/private/`, creation-time POSIX permissions, no-clobber behavior,
integrity sidecars, sanitized manifest v2, aggregate terminal output, and
project-contained source-map provenance.

See [Migrating to 0.16.0](docs/migrations/0.16.0.md).

## 0.15.1 - Instance Profiles

Sprint 18 removed the institutional host and timezone fallbacks, added
user-level instance profiles, pinned URL/profile/credential precedence, mapped
recognized Rails-style timezone names, and retained an offline authentication
doctor. `0.15.1` corrected Panopto credential-reference propagation.

See [Migrating to 0.15.0](docs/migrations/0.15.0.md).

## Earlier Releases

Earlier alpha releases developed transactional grading, assignment overrides,
submission evidence, Canvas Pages, source linting, snapshot resilience,
discussion workflows, authored content, asset verification, and release-health
gates. The detailed record remains in the
[sprint index](docs/sprints/README.md) and [backlog](docs/backlog.md); those are
design history rather than required user documentation.
