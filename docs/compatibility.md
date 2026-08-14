# Compatibility And Support

The signed `v0.19.0` release is the latest public beta, not a 1.0 stability
promise. The `0.20.0` agent-interface source remains a candidate until its tag
completes the release gates. This project is unofficial and is not affiliated
with or endorsed by Instructure.

Version `0.19.0` carries a deliberate authentication-boundary break. Signed
`v0.18.0` remains the documented rollback point for that transition.

## Supported Runtime

Danvas supports:

- Python 3.12, 3.13, and 3.14;
- Linux on POSIX filesystems; and
- macOS.

Python 3.15 and later are outside the declared range until explicitly tested.
Windows is unsupported because the private-artifact boundary depends on POSIX
directory and file modes plus symlink semantics.

CI is the authority for the exact tested matrix. A platform may satisfy Python
requirements while differing in filesystem, shell, keychain, browser, or
network behavior.

## Agent Hosts

The portable `danvas` skill follows the open Agent Skills layout. Installer
target paths and packaged-resource loading are structurally tested for the
`shared`, Codex, Claude Code, Gemini, and GitHub Copilot targets.

For `0.20.0`, bounded no-network behavior acceptance covered ten fixture
workflows on Codex and Claude Code. Codex was tested with native project-skill
discovery. Claude Code was tested after the harness surfaced the skill; its
vendor target path and loader shape are covered structurally. Both evaluations
passed skill use, command discovery, effect and privacy classification,
plan-before-apply behavior, local-sync handling, apply authorization, bounded
output, and safe recovery criteria. No evaluation contacted or mutated Canvas.

Gemini, GitHub Copilot, and the portable `shared` target have structural
installation and path coverage only in this release. Danvas does not claim that
their model behavior was evaluated. Agent-host support also does not grant shell
permissions, alter trust settings, or make model behavior deterministic.

## Canvas Deployments

Danvas uses the public Canvas API through `canvasapi`. It has no institutional
host, course, timezone, or credential built in. Canvas cloud and self-hosted
deployments can differ in enabled endpoints, permissions, feature flags,
account policy, and response shape.

Administrators may prevent token creation or restrict operations. A successful
`auth doctor --check-canvas` proves only its bounded current-user request; it
does not prove that every command is authorized.

Unknown, missing, partial, or authorization-limited reads are reported rather
than treated as authoritative absence where the workflow supports partial
evidence.

## Gradebook CSVs

The built-in gradebook profile is tested against English Canvas headings such
as `Student`, `ID`, `Points Possible`, and the current/final score and grade
variants. Exact aliases may be configured in `course.yaml` for a known export:

```yaml
gradebook_heading_aliases:
  student: [Étudiant]
  id: [Identifiant]
  points_possible: [Points possibles]
  unposted_final_score: [Note finale non publiée]
```

Aliases extend the English profile; they are not automatic locale detection or
a general translation layer. Matching trims surrounding whitespace but remains
exact and Unicode-preserving. Ambiguous role matches are rejected with bounded
heading diagnostics and no student rows.

See [Course YAML](course-yaml.md) for all supported roles.

## Authored Content

Authored Markdown and HTML support is intentionally bounded. Canvas may rewrite
HTML, inject account decorators, normalize links, or reject fields according to
deployment policy. Danvas verifies the fields and body representations it
claims and reports unsupported comparisons.

Source layouts are versioned. `standard-v1` is the new-project default;
existing projects without explicit source configuration retain `legacy-v1`.
See [Authored Sources](authored-sources.md).

## QTI

`quiz import-qti` targets Classic Quiz imports through Canvas content migration.
It does not claim New Quizzes package compatibility. Plan mode inspects the
package and intended shell settings; `--apply` imports and verifies the bounded
quiz settings that danvas owns.

Package acceptance and imported question behavior can vary by Canvas release.
Inspect the resulting quiz before student use.

## Panopto

Panopto caption support is experimental and deployment-dependent. It assumes a
Panopto LTI navigation tool visible through Canvas and protected media endpoints
compatible with the tested fixtures. Configure an exact tool name or ID when
automatic discovery is ambiguous.

Danvas does not provide a generic recording-provider plugin boundary and does
not use independent Panopto API credentials. Caption output is private. A
successful run on one institution does not establish support for another
Panopto deployment.

## Compatibility Lifetimes

Version `0.19.0` removes the provider-specific authentication interface
and the deprecated alternate roster schema. Authentication now accepts only
provider-neutral environment or credential-file locators, and roster export is
`LoginID`-only. Stale automation fails loudly rather than silently choosing a
different credential source.

The release also requires a user-controlled binding between the selected
credential and effective Canvas origin. Many existing projects with only a
project URL will fail their first authenticated command until a matching
profile, invocation URL, or environment URL establishes that intent. Follow the
[0.19.0 migration guide](migrations/0.19.0.md) before upgrading.

These due aliases were removed in `0.18.0` and fail as unknown options:

- `assignments overrides-sync --live`; use `--apply --confirm apply`.
- `discussions score --upload`; create the plan, then use `grades post`.

Migration guides describe operator-visible changes release by release:

- [0.15.0 instance profiles](migrations/0.15.0.md)
- [0.16.0 private artifacts](migrations/0.16.0.md)
- [0.17.0 plan/apply and evidence](migrations/0.17.0.md)
- [0.18.0 public beta](migrations/0.18.0.md)
- [0.19.0 provider-neutral credentials](migrations/0.19.0.md)
- [0.20.0 agent interface](migrations/0.20.0.md)

## Reporting Problems

Use the repository issue tracker for non-sensitive defects and feature
requests. Do not put tokens, private course data, student information, or
protected URLs in an issue. Follow [SECURITY.md](../SECURITY.md) for a suspected
vulnerability.
