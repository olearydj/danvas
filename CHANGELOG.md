# Changelog

This file records operator-visible release changes. Detailed transition steps
live in the linked migration guides.

## 0.18.0 - Public Beta Candidate

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
