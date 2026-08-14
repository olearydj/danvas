# Changelog

This file records operator-visible release changes. Detailed transition steps
live in the linked migration guides.

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

This source tree remains a release candidate until the independent security
review and exact branch/tag gates complete.

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
