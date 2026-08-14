# Sprint 21 Public Beta Audit

Status: independent public-boundary review accepted the public-beta claim for
exact candidate `fcc83bb` on 2026-08-13. Its only requested pre-tag correction
was a non-behavioral `0.19.0` credential-migration notice, now present in the
public authentication and compatibility guides. No `v0.18.0` tag, global CLI
replacement, GitHub Release, or PyPI publication has been authorized or
performed.

## Audit Question

Does the exact candidate satisfy the seven-part public-beta threshold from
[Sprint 18](18-public-readiness.md#public-beta-threshold), with no qualification
beyond the beta, platform, authentication, and experimental-integration limits
stated in the public documentation?

This audit covers the released `0.15.x`, `0.16.0`, and `0.17.0` boundaries plus
the complete `0.18.0` candidate. It does not treat a green Sprint 21 diff as a
substitute for checking the cross-release product.

## Cross-Release Threshold Matrix

### 1. Instance and timezone independence

- Runtime: [profile and URL precedence](../../src/danvas/profiles.py),
  [timezone normalization](../../src/danvas/timezones.py), and
  [pre-context init validation](../../src/danvas/config.py) contain no
  institutional URL or implicit local timezone fallback.
- Enforcement: [profile tests](../../tests/test_profiles.py),
  [configuration tests](../../tests/test_config.py), and the
  [Sprint 21 characterization guard](../../tests/test_sprint21_characterization.py)
  cover independent precedence, missing configuration, Rails-to-IANA mapping,
  and failure before Canvas context.
- Public contract: [authentication](../authentication.md),
  [configuration](../configuration.md), and the
  [0.15.0 migration guide](../migrations/0.15.0.md) require explicit instance
  intent and explain the remaining timezone resolution sources.
- Release evidence: Sprint 18 shipped at `v0.15.1` commit
  `9b1ba8863ce2b2d7f6bb05b6e6b9e90dcc89647e`; its
  [signed-tag CI](https://github.com/olearydj/danvas/actions/runs/31714116836)
  passed, and the deferred implementation review is recorded in the
  [Sprint 19 status](19-private-artifacts.md).
- Assessment: met.

### 2. One private-artifact boundary

- Runtime: [artifact policy](../../src/danvas/artifacts.py) centrally classifies
  33 course-internal and 18 private retained-output commands. Private creation,
  staging, sidecars, symlink refusal, permissions, and pair validation share
  that module.
- Enforcement: [artifact tests](../../tests/test_artifacts.py),
  [report tests](../../tests/test_reports.py), and the bidirectional
  [CLI registry audit](../../tests/test_cli.py) cover the real command tree,
  `0700` directories, `0600` files, no-clobber, umask `000`, and torn pairs.
- Public contract: [privacy](../privacy.md) and the
  [0.16.0 migration guide](../migrations/0.16.0.md) define default roots,
  explicit-output behavior, aggregate terminals, and operator obligations.
- Release evidence: Sprint 19 shipped at `v0.16.0` commit
  `aa66f57520ecd68e689776fcd84ea04fa1e75793`; its
  [signed-tag CI](https://github.com/olearydj/danvas/actions/runs/31736147017)
  passed, and independent review is recorded in the
  [Sprint 19 status](19-private-artifacts.md).
- Assessment: met.

### 3. No implicit Canvas mutation

- Runtime: the exact 55-command [access registry](../../src/danvas/access.py)
  declares 15 mutation-capable commands and zero bare mutators. Shared
  [mutation-mode resolution](../../src/danvas/mutation.py) fails closed and
  reserves `--apply` for Canvas writes.
- Enforcement: [access tests](../../tests/test_access.py),
  [mutation tests](../../tests/test_mutation.py), and the
  [architecture inventory](../../tests/test_architecture.py) require exact
  command, write-call, and pre-write-assertion sets.
- Public contract: [mutation safety](../mutation-safety.md) and the
  [0.17.0 migration guide](../migrations/0.17.0.md) teach plan-by-default,
  command-specific confirmations, local-write separation, and automation risk.
- Release evidence: Sprint 20 shipped at `v0.17.0` commit
  `f34d32fe6da3a92255f614e68ab3f73ee5aae8cd`; its
  [signed-tag CI](https://github.com/olearydj/danvas/actions/runs/31749638335)
  passed, and the exact review/probe record is in
  [Sprint 20](20-mutation-reconciliation.md).
- Assessment: met.

### 4. Bounded mutation evidence and safe retry

- Runtime: [grade evidence](../../src/danvas/grade_evidence.py),
  [grade transactions](../../src/danvas/grades.py),
  [feedback settlement](../../src/danvas/submissions.py), and
  [file-upload reconciliation](../../src/danvas/files.py) distinguish verified,
  conflicting, failed, skipped, and accepted-but-unverified outcomes without
  preserving tokens, protected URLs, or raw payloads.
- Enforcement: [grade-evidence tests](../../tests/test_grade_evidence.py),
  [grade tests](../../tests/test_grades.py),
  [submission tests](../../tests/test_submissions.py), and
  [file tests](../../tests/test_files.py) cover authoritative readback, stop
  policy, uncertain settlement, conflict-safe reruns, and aggregate terminals.
- Public contract: [mutation safety](../mutation-safety.md) tells operators not
  to retry accepted-but-unverified writes blindly and identifies the retained
  private evidence needed for reconciliation.
- Release evidence: the separately authorized upload and feedback probes,
  correction, exact readback, cleanup, and supplemental acceptance are recorded
  in [Sprint 20](20-mutation-reconciliation.md#bounded-live-acceptance).
- Assessment: met.

### 5. Generic installation and quickstart

- Runtime and packaging: the distribution is `danvas-cli` while the import and
  executable remain `danvas`; [source layouts](../../src/danvas/source_layouts.py)
  materialize `standard-v1` for new projects and preserve `legacy-v1` for
  existing source-less projects.
- Enforcement: the [anonymous install smoke](../../scripts/anonymous-install-smoke.sh)
  accepts only an exact SHA or matching tag, installs over anonymous HTTPS,
  runs outside the checkout under `env -i`, and invokes the installed-package
  [quickstart fixture](../../scripts/check-public-beta-quickstart.py).
  [Install tests](../../tests/test_anonymous_install_smoke.py) and
  [quickstart tests](../../tests/test_public_beta_quickstart.py) pin the
  distribution migration, standard render, legacy preservation, no authored
  file creation, and failure-preserving cleanup.
- Public contract: the [README](../../README.md),
  [configuration guide](../configuration.md), and
  [0.18.0 migration guide](../migrations/0.18.0.md) use only anonymous HTTPS,
  placeholder institutions/IDs, and public paths.
- Candidate evidence: exact public commit `c95cae8` passed the real anonymous
  install, version, root help, local-only help, offline doctor, standard-layout,
  and legacy-layout fixture under an isolated home/config root. A real isolated
  `v0.17.0` `danvas` uninstall followed by exact-candidate `danvas-cli` install
  also produced one `danvas 0.18.0` executable and no legacy distribution.
- Assessment: met provisionally; repeat against the final pushed candidate and
  exact tag remains mandatory.

### 6. Declared platform and Python support matches CI

- Metadata: [project metadata](../../pyproject.toml) declares Python
  `>=3.12,<3.15`, Linux/POSIX, and macOS, with no Windows classifier.
- Enforcement: [CI](../../.github/workflows/ci.yml) runs the frozen full gate on
  Linux 3.12, 3.13, and 3.14 and the full suite, privacy/recovery matrix, build,
  and isolated install smoke on macOS 3.13.
- Public contract: [compatibility](../compatibility.md) names that exact support
  range and explains why Windows is outside the private-file contract.
- Candidate evidence: exact commit `c95cae87f35d2a502f290cabf844b37710813c75`
  passed every job in
  [CI run 31760904461](https://github.com/olearydj/danvas/actions/runs/31760904461),
  including the pinned current-tree/history secret scan and final install smoke.
- Assessment: met; repeat on the final review candidate remains mandatory.

### 7. Self-contained public documentation

- Surface: README plus configuration, authentication, privacy, compatibility,
  authored-sources, mutation-safety, course-policy, migration, changelog,
  contribution, and security documents form the public authority chain.
- Enforcement: the offline [documentation checker](../../scripts/check-docs.py)
  and [documentation tests](../../tests/test_docs.py) validate all 12 Markdown
  files, relative links, anchors, required topics, and absence of maintainer
  paths, SSH installation, and external agent-skill dependencies.
- Security route: [SECURITY.md](../../SECURITY.md) names GitHub private
  vulnerability reporting as primary. The repository setting was re-read on
  2026-08-13 and returned `{"enabled": true}`.
- Forward compatibility: the [authentication](../authentication.md) and
  [compatibility](../compatibility.md) guides state that the provider-specific
  `0.18.0` credential surface has an accepted post-beta replacement design and
  requires migration in `0.19.0`.
- Distribution identity: PyPI's JSON API returned HTTP 200 for occupied
  `danvas` and HTTP 404 for `danvas-cli` on 2026-08-13. This is point-in-time
  naming evidence, not a claim that a package has been reserved or published.
- Assessment: met.

## Required Independent Checks

1. Command/config/output inventory: passed. The exact registries report 55
   commands, 15 mutation-capable commands, zero bare mutators, 33
   course-internal artifact policies, and 18 private policies. Architecture and
   bidirectional CLI tests pass.
2. Anonymous exact-candidate install: passed provisionally at `c95cae8`; final
   candidate and tag repetitions remain open.
3. Version/help/offline checks outside checkout: passed under an empty
   environment and isolated home for `danvas --version`, root help,
   `sources lint --help`, and offline `auth doctor`.
4. New-project standard-layout fixture: passed through the exact installed
   package, with complete materialization and no authored-file creation.
5. Existing-project legacy fixture: passed through the exact installed package;
   a source-less project retained the assignment case pattern and quiz chapter
   pattern.
6. Linux/macOS private-artifact evidence: passed in exact
   [CI run 31760904461](https://github.com/olearydj/danvas/actions/runs/31760904461).
7. Package and wheel inspection: passed for sdist and wheel metadata, `LICENSE`,
   import package, single executable, editable install, and wheel install.
8. Public-document validation: 12 files passed the offline checker; changed
   sprint documents pass Markdown lint.
9. Secret scans: pinned Gitleaks 8.30.1 reported no finding in the current tree
   or all 186 reachable commits. No allowlist exists and no report was retained.
10. Independent public-boundary review: passed. On 2026-08-13, review of exact
    candidate `fcc83bb` returned `ACCEPT PUBLIC BETA`, re-executed all 834 tests,
    independently enumerated the command and artifact registries, and accepted
    all seven threshold assessments. Its sole pre-tag finding was the
    non-behavioral credential-migration notice now recorded in the public docs.

## Audit-Driven Corrections

The audit found and closed three gate defects without changing Canvas runtime
behavior:

1. Initial Group 4 CI at `9d96fdc` exposed two tests that inspected ANSI-styled
   Rich output without the existing normalization helper. `c95cae8` corrected
   the assertions; exact CI then passed on every supported lane.
2. The anonymous and wheel smokes used isolated environments but originally
   invoked checks from the repository working directory. `5f5f8dc` moves every
   runtime check to a temporary cwd with isolated `HOME`, `XDG_CONFIG_HOME`,
   empty `PYTHONPATH`, and `env -i`, then exercises both source-layout fixtures
   through the installed interpreter.
3. A successful EXIT trap could mask an earlier shell failure on macOS.
   `5f5f8dc` preserves the incoming status while deleting only the validated
   temporary root in all three release/security scripts. A forced failure now
   exits nonzero and still leaves no temporary directory.

## Current Gate Record

- Local candidate gate: 834 tests passed at 84.99% branch-aware coverage;
  `authored_assets.py` passed its 82% module floor at 88.87%; Ruff, ty,
  ShellCheck, frozen-lock validation, and dependency audit passed.
- Package gate: sdist/wheel metadata and contents, editable install, wheel
  install, root help, and offline doctor passed outside the checkout.
- Documentation gate: all 12 public files passed the offline link/anchor check.
- Security gate: current-tree and all-history scans passed with zero finding;
  private vulnerability reporting is enabled.
- Remote platform gate: `c95cae8` passed exact
  [CI run 31760904461](https://github.com/olearydj/danvas/actions/runs/31760904461).
- Historical release gates: signed-tag CI passed for
  [`v0.15.1`](https://github.com/olearydj/danvas/actions/runs/31714116836),
  [`v0.16.0`](https://github.com/olearydj/danvas/actions/runs/31736147017), and
  [`v0.17.0`](https://github.com/olearydj/danvas/actions/runs/31749638335).

## Gates Still Open

The candidate is not yet a release. These steps remain ordered:

1. the resulting exact candidate is pushed and passes the complete remote CI
   matrix;
2. anonymous exact-candidate installation is repeated from that SHA;
3. an authorized signed `v0.18.0` tag is created only then;
4. tag CI and anonymous exact-tag installation pass; and
5. only afterward may the global CLI and release records advance.

No live Canvas or Panopto operation is required or authorized for this audit.
