# Sprint 24: Post-Program Hygiene

Status: released as signed tag `v0.21.1` on 2026-08-14 from `dd30019`, and
published to PyPI. Accepted for `0.21.1` by independent design review, which
re-verified all eight findings against the tree and required the Release
Contract section plus the committed Panopto fix choice recorded below.
Independent exact-candidate review accepted `dd30019`. Branch CI
`31857479652`, tag CI `31857776914`, anonymous exact-tag and exact-SHA
installs, and global verification as `danvas 0.21.1` all passed. PyPI Trusted
Publishing run `31858000548` published the reviewed GitHub Release artifacts as
[`danvas-cli 0.21.1`](https://pypi.org/project/danvas-cli/0.21.1/); the dated
check on 2026-08-14 America/Chicago (2026-08-15 UTC) verified matching
SHA-256 digests, repository-linked Integrity provenance, both cryptographic
attestations, and an isolated PyPI installation.

This sprint remediates the eight verified findings from the first
whole-system deep review after the public-readiness program, run on
2026-08-14 against `85955b4`
(`v0.21.0` plus the landing-page commit). The review covered whole-file views
of `src/danvas` in three cloud ultra reviews, scaffolded as do-not-merge pull
requests 2 through 4 over the `review-baseline` branch: legacy internals and
C901 hotspots, security and boundary modules, and the CLI/agent interface.

Review outcome for the record: all eight findings are low severity. The
adversarial second opinion on `credentials.py`, `skill_installer.py`, and
`artifacts.py` returned only one defense-in-depth completeness item in the
shared sanitizer. `quiz_reports.py`, `cli.py` structure, and the internals of
the four documented C901 suppressions produced no correctness findings. Nothing
found touches mutation safety, evidence truthfulness, or the
credential/origin-binding contracts. Each finding was independently verified
against the tree before acceptance; the two mechanically checkable claims (the
CSS regex and the naive timestamp) were reproduced, and the rest were confirmed
by path tracing.

## Objective

Land all eight fixes as one bounded maintenance pass with a regression test per
change. Existing commands become stricter about explicit configuration, more
deterministic in retained evidence and comparison normalization, and consistent
in agent-facing guidance. No new command, option, or Canvas mutation is
introduced, and no C901 refactor is attempted.

The sprint has three named themes. The first theme exists because the review
found the same defect shape independently in three legacy modules, which argues
for recording the principle durably, not just patching the instances.

## Theme 1: Explicit-Selector Strictness

Principle: explicit operator configuration is honored or produces a bounded
error. It never silently falls through to a heuristic, a default, or a
differently-configured filter.

### Gradebook final-score column (`gradebook.py:164-178`)

`CanvasGradebook.choose_final_score_column` handles one and many matches for an
explicit `--final-score-column` request but has no zero-match branch, so a
requested heading that matches nothing falls through to the `SCORE_ROLES`
observed-defaults loop and the audit silently runs against a different column.

- Add a zero-match branch that raises `ValueError`, quoting the requested
  heading and `bounded_observed_headings(self.headers)`, mirroring the two
  sibling branches in the same method.
- Regression test: requested heading absent from headers raises; the message
  names the request and stays bounded to headings, not rows.

### Panopto tool selector (`panopto.py:265-275`)

`discover_panopto_tool` raises on an ambiguous configured `tool_name`/`tool_id`
and returns on a unique match, but on zero matches in
`visible_course_nav_tools` it falls through to the substring heuristic, which
returns the first tool containing "panopto" and discards the operator's
explicit selector. The tabs branch at `panopto.py:294-295` already implements
the correct discipline.

- When a selector is configured and the tools listing yields zero matches, do
  not enter either substring heuristic. Proceed directly to the tabs-matching
  path, which already raises with the selector and course id on zero matches.
  Review committed to this option over raising immediately at the nav-tools
  branch because it preserves the legitimate configuration where the selected
  tool is absent from course navigation but present in tabs.
- Regression tests: two Panopto-adjacent nav tools plus a configured name
  matching neither raises rather than returning the first substring hit; a
  configured selector that matches only in tabs still resolves.

### Status file comparison ignore policy (`status.py:625-626`)

`compare_files` calls `local_files(root)` with no ignore patterns, so it always
uses `default_inventory_ignore_patterns()` and never reads the project's
`[files.inventory]` configuration. `danvas status` and `danvas files inventory`
therefore disagree about which local files exist whenever `use_default_ignores`
or `custom_patterns` is set.

- Thread the project root through `compare_files` and resolve
  `files_inventory_ignore_policy` the same way `command_files_inventory` does,
  then pass the effective patterns to `local_files`.
- Regression tests: a project with `use_default_ignores = false` and a custom
  pattern produces the same local-file universe from `status` and `files
  inventory`; default behavior without inventory configuration is characterized
  as unchanged.

### Durable decision

Add one line to the Durable Decisions section of `PROJECT_CONTEXT.md` on
acceptance, worded approximately: explicit operator selectors and configured
filters are honored or fail with a bounded error naming the request and the
observed candidates; they never silently fall through to heuristics or
defaults.

## Theme 2: Evidence And Normalization Correctness

Principle: retained evidence and comparison normalization are deterministic and
unambiguous across operators, timezones, and serialization variants.

### CSS zero-unit collapse for `%` (`page_sources.py:486`)

The zero-unit collapse regex in `normalize_css_value` terminates with `\b`,
which never matches after `%` because `%` is a non-word character. `margin: 0%`
survives normalization while every other zero-unit form collapses to `0`, so
semantically identical CSS can produce spurious `compare_page` body
differences.

- Replace the trailing `\b` with `(?![\w.-])`, the mirror of the existing
  lookbehind.
- Regression tests: `0%`, `0.0%`, and `0%;` collapse to `0`; nonzero forms such
  as `10%` are untouched; existing unit cases keep their behavior.

### Panopto date rendering (`panopto.py:614`)

`parse_panopto_date` calls `datetime.fromtimestamp(timestamp_ms / 1000)`
without `tz`, rendering Panopto's UTC millisecond epoch as operator-local wall
time with no offset marker. The value persists in `artifact-manifest.json` and
`manifest.csv` `created_date` fields and in caption filename prefixes, so
bundles differ per operator timezone for the same session. Interrupted-bundle
reconciliation is unaffected because it keys on `session_id`.

- Pass `UTC` (already imported) so the rendered instant carries an explicit
  offset, consistent with the project's explicit-offset timestamp doctrine.
- Regression test: a `/Date(ms)/` input renders identically regardless of
  process timezone and carries `+00:00`.

### Sanitizer AWS credential symmetry (`sanitize.py:8-28,44,55`)

`SENSITIVE_NAMES` covers `aws_secret_access_key` (env-var form of the secret)
and `awsaccesskeyid` (signed-URL form of the ID) but not `aws_access_key_id`,
and the two credential-name regexes are literal-only for the ID. A mapping
containing both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` sanitizes only
the secret. `sanitize_public` has production callers in `files.py` and
`assignments.py`, so the asymmetry is reachable; no active leak path is known,
making this defense-in-depth completeness.

- Add `aws_access_key_id` to `SENSITIVE_NAMES` and widen `awsaccesskeyid` to
  `aws[_-]?access[_-]?key[_-]?id` in both `SENSITIVE_NAME_PATTERN` and
  `UNAMBIGUOUS_CREDENTIAL_RE`.
- Regression tests: paired env-var-form AWS credentials are both dropped by
  `sanitize_public` and both redacted by `sanitize_error`; ordinary prose
  containing "access key" survives, preserving the existing
  anti-over-redaction posture.

## Theme 3: Interface Consistency

Principle: agent-facing guidance and internal idioms follow the conventions the
codebase has already established.

### Upload folder resolution walks pagination twice (`files.py:955,962`)

`resolve_upload_folder` iterates the paginated `course.get_folders()` once for
exact matches and a second time to build the nearby-folder suggestions,
doubling Canvas round trips exactly on the misspelled-`--folder` path and
risking a different snapshot between walks. `build_file_inventory` already
materializes the listing once.

- Materialize `list(course.get_folders())` once and reuse it for the match
  filter and the suggestion sort.
- Regression test: a fake paginated source counts one iteration for the
  not-found path.

### Overrides-sync guide example (`command_guides.py:573`)

The `_BASE_EXAMPLES` entry for `assignments overrides-sync` shows
`OVERRIDES.csv`, but the command's argument is assignment Markdown with
`availability_overrides_ref` front matter (`cli.py:983-986`); a CSV fails
preflight. Every sibling authored-source command uses the `SOURCE` placeholder.
The wrong example fans out to `danvas describe`, progressive help, offline
guides, and the packaged Agent Skill.

- Change the placeholder to `SOURCE` and regenerate whatever derived guide
  surfaces the build produces.
- Regression test or characterization update: the rendered example for
  `assignments overrides-sync` uses `SOURCE`, consistent with siblings.

## Acceptance Criteria

- All eight changes land with the regression tests named above; each test fails
  against the pre-sprint tree.
- Behavior changes are limited to the described paths: three silent fallbacks
  become bounded errors or honor configuration, normalization and evidence
  rendering become deterministic, one guide example changes, and one sad-path
  pagination walk is halved.
- The strictness changes are honest about compatibility: an operator whose
  configuration silently mismatched before will now receive an error where they
  previously received wrong-but-quiet behavior. The changelog entry states this
  plainly for `--final-score-column`, the Panopto selector, and `status` ignore
  handling.
- `PROJECT_CONTEXT.md` gains the explicit-selector durable decision line.
- The full local gate passes: pytest, Ruff, ty, docs checks, packaging smoke,
  and secret scans, per the standard release sequence.
- No Canvas credential or live-course access is required; all acceptance is
  local and test-based.

## Release Contract

The sprint targets patch release `0.21.1`. Under the project's version
convention this is a patch, not a minor: eight defect fixes with no new
command, option, or mutation surface. Turning silently-wrong behavior into a
bounded error is a defect fix even though it is operator-visible; the
changelog-honesty requirement in the acceptance criteria covers that
visibility.

Closeout follows the standard sequence: full local gate, exact-candidate
independent review, push, green branch CI, signed tag `v0.21.1`, tag CI,
exact-tag installation verification, global CLI advance, and release records.
GitHub Release creation and PyPI publication remain separately authorized
post-tag actions per the established contract.

## Non-Goals

- No refactor of the four C901 suppressions; the review found no internal
  correctness defect in them, and the suppressions remain standing named debt.
- No `cli.py` structural decomposition.
- No new command families, options, or mutation surfaces.
- No timezone rework beyond the single Panopto rendering site; `local_files`
  mtime rendering already carries an offset via `astimezone()` and is out of
  scope.
- Review scaffolding cleanup (closing PRs #2-#4 and deleting `review-baseline`
  and the `review-src-*` branches) is repository housekeeping alongside this
  sprint, not sprint work.

## Implementation Record

Implemented on 2026-08-14 in theme order against `b1c799d`. Every listed
regression test was confirmed to fail against the pre-sprint source before the
corresponding fix was accepted, using a stashed-source run per theme.

- Theme 1: `gradebook.py` gained the zero-match raise; `panopto.py` now guards
  both substring heuristics behind an unconfigured-selector branch and lets the
  tabs path report unmatched selectors; `status.compare_files` accepts an
  optional `ignore_patterns` override and otherwise resolves
  `files_inventory_ignore_policy` from the project root.
- Theme 2: the `page_sources.py` collapse regex now terminates with
  `(?![\w.-])`; `parse_panopto_date` renders through `UTC`; `sanitize.py` adds
  `aws_access_key_id` and `awssecretaccesskey` to `SENSITIVE_NAMES` and widens
  both credential-name regexes to separator-insensitive AWS ID forms.
- Theme 3: `resolve_upload_folder` materializes the folder listing once;
  the `assignments overrides-sync` example placeholder is now `SOURCE`.
- Version pins moved to `0.21.1` in `pyproject.toml`, `uv.lock`, `README.md`,
  the packaged `SKILL.md`, and the installation, distribution, skill-resource,
  and public-beta characterization tests. The public-fixture numeric guard now
  records the Unix millisecond epoch used by the new timezone test, with the
  reason stated inline.

## Reference Basis

- Review target: whole-file views of `src/danvas` at `85955b4`, tag `v0.21.0`
  at `0953757`.
- Findings verified 2026-08-14 against the working tree; reviewer line-number
  drift was corrected during verification (`compare_files` is at
  `status.py:625`, not the reported 455), and the reviewer's claim that
  `sanitize_public` has no production callers was corrected (`files.py:1180`,
  `assignments.py:1532`).
