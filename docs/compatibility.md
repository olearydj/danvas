# Compatibility And Support

The signed `v0.18.0` release is the planned public beta, not a 1.0 stability
promise. A source tree before the tag completes its release gates remains a
candidate. This project is unofficial and is not affiliated with or endorsed
by Instructure.

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

The following transition is active in `0.18.0`:

- `roster --schema legacy-v1` remains available, warns, and is removed in
  `0.19.0`; use the default `LoginID` schema now.

These due aliases were removed in `0.18.0` and fail as unknown options:

- `assignments overrides-sync --live`; use `--apply --confirm apply`.
- `discussions score --upload`; create the plan, then use `grades post`.

Migration guides describe operator-visible changes release by release:

- [0.15.0 instance profiles](migrations/0.15.0.md)
- [0.16.0 private artifacts](migrations/0.16.0.md)
- [0.17.0 plan/apply and evidence](migrations/0.17.0.md)
- [0.18.0 public beta](migrations/0.18.0.md)

## Reporting Problems

Use the repository issue tracker for non-sensitive defects and feature
requests. Do not put tokens, private course data, student information, or
protected URLs in an issue. Follow [SECURITY.md](../SECURITY.md) for a suspected
vulnerability.
