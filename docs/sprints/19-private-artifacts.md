# Private Artifact Boundary

Status: accepted implementation specification for Sprint 19 / `0.16.0` after
independent design review on 2026-08-13. The same review retrospectively
accepted the Sprint 18 implementation and `v0.15.1` correction as released,
subject to the durable-context correction landed with this acceptance. This
document authorizes implementation but no live Canvas mutation.

## Outcome

Make every danvas output containing student, grade, submission, discussion,
override-membership, or protected-recording data safe by default. One typed
artifact boundary will resolve private paths, create directories and files with
restrictive permissions from their first byte, refuse accidental overwrites,
classify retained evidence, and keep sensitive row data out of routine terminal
output.

This is the bounded second release in the accepted public-readiness program:

| Sprint | Release | Outcome | Public status |
| --- | --- | --- | --- |
| 18 | 0.15.x | Instance profiles | Alpha, released |
| 19 | 0.16.0 | Private artifacts | Alpha, this specification |
| 20 | 0.17.0 | Mutation and evidence | Alpha, design-only |
| 21 | 0.18.0 | Generalization and packaging | Beta candidate |

Sprint 19 does not claim a public beta. It makes no Canvas mutation-policy
change, does not generalize maintainer source layouts, and does not add the
agent-facing interface proposed for Sprint 22.

## Context

Sprint 18 removed the Auburn API fallback, added user-level instance profiles,
made project configuration outrank generic environment fallback, removed the
built-in Central Time default, and shipped as `v0.15.0`. A focused follow-up
fixed profile-specific Panopto secret selection and shipped as `v0.15.1`.

The current tree already recognizes some private data, but enforcement is
distributed and incomplete:

- private report runs pass `private_data=True`, while explicit output paths
  often bypass the report writer;
- `write_json()` and `write_rows()` create ordinary files and several callers
  invoke `mark_private()` only after the complete payload has been written;
- private report directories are created with a restrictive requested mode,
  but nested files are still written first and tightened later;
- roster, discussion, and Panopto defaults write into the working directory;
- report manifests retain `sys.argv`, absolute run directories, project roots,
  and input paths;
- source-map paths fall back to absolute paths when a source is outside the
  project;
- discussion scoring and feedback planning print student names, identifiers,
  filenames, and scores to routine terminal output;
- caption manifests retain reusable Panopto `viewer_url` values; and
- `danvas init` ignores the course snapshot and report directory, but not a
  private-artifact root.

The existing `mark_private()` helper remains useful for auditing legacy files,
but it cannot satisfy the new creation-time guarantee. A private file must not
exist with permissive mode bits during a successful, interrupted, or failed
write.

## Durable Contract Amendment

This sprint deliberately amends the existing Report Output Contract for
sensitive commands.

Non-sensitive raw exports continue to require or honor their explicit output
paths. Sensitive exports and downloads may instead select a documented default
beneath `.danvas/private/` when a course project is available. Without a course
project, a command that will retain private data must require an explicit
output path before Canvas access.

The implementation must update the durable project context through the
project's approved context-maintenance workflow so it states the same rule.
This sprint document is not a substitute for that update.

## Artifact Classification

Every command that writes retained output must declare one of three content
classes in a central registry:

- `shareable`: sanitized operational evidence intentionally safe to share.
  May be committed to a repository after normal review.
- `course_internal`: course/account configuration or authored content without
  student-private data. Not automatically safe to publish; existing storage
  behavior may remain.
- `private`: student data, grades, submissions, identities, protected
  media/access data, or raw payloads that may contain them. Must use the
  complete private-artifact contract.

`course_internal` is not a euphemism for shareable. It allows the inventory to
state that a course list, authored Page, or file inventory may expose course
names, schedules, content, and object IDs without expanding this sprint into a
general course-content storage redesign. Sprint 21 owns broader documentation
and configuration cleanup.

Classification follows content rather than command family. A raw Canvas payload
inherits the most sensitive class it may contain. A report run inherits the
maximum class of its payloads. A future file-producing command must add a
registry entry and pass an inventory test before it can ship.

The existing `may_contain_private_student_data` and `private_student_data`
booleans remain readable compatibility fields. New manifests use
`artifact_class` as the authoritative classification. For `private` artifacts,
the legacy boolean remains `true` where it is already part of a public schema.

## Command And Output Inventory

The implementation starts from the following reviewed inventory. It is a
required baseline rather than an exhaustive allowlist: the inventory test must
also catch output-producing commands added or missed during implementation.

### Private outputs

Each entry names the private content, then the Sprint 19 behavior:

- `roster`: names, Canvas IDs, login IDs, SIS IDs. Safe project default;
  explicit path required without a project; schema correction.
- `assignments overrides`: differentiated assignment membership. Safe project
  default; explicit path remains supported.
- `assignments overrides-sync`: membership plans and results. Private report
  root and secure writes.
- `gradebook check`, `gradebook audit`: student rows, scores, and grade
  diagnostics. Explicit output and report-run forms use the same boundary.
- `quiz analysis`: student analysis and answer-linked rows. Explicit output
  and report-run forms use the same boundary.
- `submissions export`, `submissions grades`: submission metadata, grades,
  comments, attachments, optional raw payloads. Safe project defaults; secure
  JSON/CSV/raw output.
- `submissions media`: student-named files, attachments, media, sidecars, and
  manifests. Safe project directory; secure partial and final files.
- `submissions feedback`: roster-to-feedback mapping and per-student results.
  Private plan/result evidence; aggregate terminal output.
- `grades post`, `grades clear`, `grades comments`, `grades verify`: grades,
  comments, release state, rollback and recovery evidence. Private reports,
  explicit outputs, and rollback material.
- `discussions export`: names, IDs, and full post bodies. Safe project
  default; secure output.
- `discussions score`: identities, participation counts, scores, and grade
  plan. Private plan/results; aggregate terminal output.
- `announcements export`: selected reply-user identity and reply bodies.
  Private because `--reply-user-id` can select any participant.
- `recordings panopto-captions`: protected sessions, captions, and access
  metadata. Safe project directory; sanitized private manifests.

Any raw-output option attached to these commands is also `private`, regardless
of its filename or serialization format.

### Course-internal outputs

The course snapshot, project configuration, source map, course list,
assignment/Page/announcement/discussion authored-content evidence, QTI import
evidence, Canvas file inventory/downloads, status output, and refresh reports
are `course_internal` unless their actual payload includes a private class from
the preceding table. Assignment override references and announcement exports
are the named exceptions.

`courses` is deliberately classified `course_internal`: it exposes the
authenticated account's active-course visibility, names, codes, and dates, but
does not ordinarily contain enrollment rows or protected student data. Its
existing `courses.csv` default is retained in Sprint 19. Help must state that
the file is course-internal and is not automatically safe to publish.

`announcements latest` is deliberately `course_internal`: it retains an
announcement body and author metadata but requests no participant replies.
`announcements export` remains conservatively `private` even in its common
authenticated-instructor case because the same output contract permits an
arbitrary `--reply-user-id`; classification must not vary silently with one
option value.

Canvas file downloads may contain licensed or otherwise restricted course
material. They remain `course_internal`, not `shareable`, and retain their
existing destination behavior. Canvas does not provide enough information to
prove that an arbitrary downloaded file lacks student data, so command help and
the migration guide must tell operators to choose a private destination when
the file content is sensitive. This sprint does not attempt to inspect payload
content or infer copyright or institutional sharing rights from a Canvas file.

### Shareable outputs

Only bounded, sanitized operational evidence may declare `shareable`. The
initial registry should be conservative. Public report manifests become
shareable after the manifest migration below, but a manifest's referenced
payload keeps its own class. Aggregate lint results and release/installation
health output may also be shareable when they contain no source body, personal
path, raw error, or course-private field.

## Private Path Resolution

### Project default

The protected root is fixed at `.danvas/private/` for this release. It is not
profile configuration and must not be redirected by a user-level profile. An
explicit output option may select another location.

Default paths are deterministic and intentionally refuse to overwrite an
existing artifact:

| Command | Default relative to `.danvas/private/` |
| --- | --- |
| `roster` | `roster.csv` |
| `assignments overrides` | `overrides/assignment-<id>.yaml` |
| `submissions export` | `submissions/assignment-<id>/submissions.json` |
| `submissions grades` | `submissions/assignment-<id>/grades.csv` |
| `submissions media` | `submissions/assignment-<id>/media/` |
| `submissions feedback` | `submissions/assignment-<id>/feedback-plan.json` |
| `grades comments` | `grades/assignment-<id>/user-<id>/comments.json` |
| `discussions export` | `discussions/topic-<id>/posts.json` |
| `discussions score` | `discussions/topic-<id>/grade-plan.csv` |
| `announcements export` | `announcements/announcements.json` |
| `recordings panopto-captions` | `recordings/panopto-captions/` |
| private report runs | `reports/YYYY-MM-DD-NNN-<slug>/` |

The command may preserve an explicitly requested format by changing the suffix
of its safe default. Danvas-chosen default bundle roots and top-level artifact
names may contain validated numeric Canvas object or user IDs and bounded
non-personal slugs. They never derive components from user names, login IDs,
titles, or free text.

That rule does not prohibit student-derived leaf filenames inside an already
private bundle when those names are operationally necessary, as in
`submissions media`. Such leaves remain beneath a validated bundle root, use
the secure writer, may appear only in private bundle metadata, and are never
printed in routine terminal output. Numeric user IDs used to distinguish
private per-user artifacts are likewise permitted below the command's bundle
root.

Grade rollback and recovery material belongs under the private grade/report
tree rather than beside an input CSV by default. An explicit `--rollback-dir`
continues to work through the same secure boundary.

### Project discovery and explicit output

A command resolves the project using the same explicit `--project-root` and
ancestor `.danvas` discovery rules as configuration. Private commands missing a
project-facing option gain the shared option without changing authentication
precedence.

Resolution occurs before Canvas authentication or network access:

1. an explicit output path wins;
2. otherwise a discovered course project selects the command's default under
   `.danvas/private/`;
3. otherwise the command exits with an actionable `--output`, `--output-dir`,
   `--report-root`, or `--report-dir` example.

An explicit destination outside `.danvas/private/` is supported because users
may need an encrypted volume or controlled institutional directory. The CLI
still creates the artifact with restrictive file mode and prints a concise
warning that the destination is outside the project-private root. It does not
silently relocate the requested path.

Default-root containment is resolved and checked before creation. Existing or
new symlink components beneath `.danvas/private/` are rejected. Path traversal,
absolute default fragments, and a file where a directory is expected are hard
errors. Explicit user destinations do not authorize danvas to chmod unrelated
ancestor directories.

### No-clobber

No-clobber is the default for private single files, report directories,
download directories, caption files, manifests, sidecars, rollback evidence,
and temporary/partial files. Existing command-specific `--overwrite` options
remain explicit compatibility paths and are routed through atomic replacement.

An interrupted prior run must not be mistaken for a valid artifact. Danvas may
delete only a temporary file that it created during the current process. It
must not recursively clean an existing output directory or guess that a prior
partial directory is disposable.

## Creation-Time Filesystem Contract

Add a dependency-light `danvas.artifacts` module. It owns typed policy and
filesystem mechanics; command modules supply only their classification,
project context, explicit destination, default relative path, and payload.

The boundary must provide secure equivalents for JSON, CSV, text, bytes,
streamed downloads, atomic replacement, and report bundles. Generic
`write_json()` and `write_rows()` remain available for non-private artifacts,
but private code paths may not call them and then invoke `mark_private()`.

On supported POSIX systems:

- every danvas-owned private directory is created with mode `0700`;
- every private file, including a `.part` or atomic temporary file, is opened
  with mode `0600` at creation;
- the implementation uses low-level exclusive creation where needed rather
  than relying on the process umask;
- an overwrite writes a new `0600` temporary file in the destination directory,
  flushes it, and atomically replaces the destination;
- every final path is verified as a regular file or directory with no
  group/other mode bits;
- a symlink is never followed as a danvas-managed private artifact; and
- a failed or interrupted write leaves no permissive content-bearing file.

The helper may tighten an existing danvas-owned `.danvas/private/` directory
before use. It must not loosen permissions and must not chmod an arbitrary
explicit parent directory. Existing explicit output files are never modified
unless the user supplied that command's documented overwrite option.

No process-wide umask mutation is permitted. Tests run with umask `000` to
prove that correctness comes from the writer rather than ambient configuration.

Sprint 19 supports POSIX permission enforcement only. On a platform where this
contract cannot be enforced, a private-output command fails before Canvas or
filesystem mutation with an explicit unsupported-platform diagnostic. Sprint
21 owns the final operating-system support statement and macOS CI lane.

## Artifact Identification

Every private bundle includes classification metadata:

```json
{
  "artifact_schema_version": 1,
  "artifact_class": "private",
  "command": "submissions export",
  "created_at": "2026-08-13T10:15:00-05:00",
  "danvas_version": "0.16.0",
  "files": ["submissions.json"]
}
```

The reusable classification envelope contains no absolute path, arguments,
student identifier, student name, source body, token, signed URL, or raw
exception. Bundle metadata is `artifact-manifest.json`. A private bundle
manifest may additionally list relative student-derived filenames or stable IDs
needed to verify its contained files; that semantic metadata remains private
and must never be projected into a public report manifest. A private file
already covered by the bundle manifest does not receive a redundant generic
artifact sidecar. A standalone JSON artifact may embed the same classification
fields. A standalone CSV, text, or binary output receives a same-directory
`<filename>.artifact.json` sidecar because changing data rows or adding comment
lines would break consumer schemas.

`submissions media` retains exactly one semantic `<filename>.info.json`
sidecar per downloaded file. That existing sidecar becomes the authoritative
per-file artifact metadata and absorbs the classification fields; no second
`<filename>.artifact.json` is created. The bundle manifest records both the
media file and its `.info.json` sidecar.

Every standalone or semantic sidecar records the exact data file's SHA-256
digest and is committed after the data file. Missing metadata or a digest
mismatch makes the artifact detectably invalid. If either no-clobber target
already exists, the write stops before changing either one. A handled failure
removes incomplete outputs when that is safely possible; otherwise it leaves a
detectably invalid pair and reports the recovery action. It does not promise to
restore the prior pair during an explicit overwrite. A process crash between
the two commits may likewise leave a detectably invalid pair, but never an
apparently valid sidecar for different content. Multi-file bundles use a
private staging directory and commit the bundle manifest last under the same
validity rule.

CLI option help for every private raw output begins with `Private` and states
the project default or explicit-path requirement. Completion messages identify
the artifact as private and print its bounded root path, not individual
student-derived filenames. The bounded root is the command-level directory
above any per-user or student-derived leaf, such as
`.danvas/private/grades/assignment-<id>/` or
`.danvas/private/submissions/assignment-<id>/media/`; it therefore never prints
the `user-<id>` component of the comments artifact.

## Terminal And Diagnostic Contract

Routine terminal output for a private command contains aggregate counts,
classification, the bounded artifact path, and safe next actions. It does not
print student names, login IDs, SIS IDs, Canvas user IDs, grades, comments,
post bodies, feedback filenames tied to students, caption text, viewer URLs, or
raw Canvas errors.

This changes these known paths:

- `discussions score` prints aggregate scored/unmatched/failed counts and the
  private grade-plan path, not one name/score line per participant;
- `submissions feedback` prints aggregate matched/unmatched counts and the
  private plan/result path, not roster labels, Canvas IDs, or feedback
  filenames; and
- `submissions media` and Panopto caption downloads print aggregate completion
  and their private bundle root, not student/session-derived filenames or
  viewer URLs.

Detailed rows belong in the private artifact, not behind an easy-to-miss verbose
terminal flag. Sprint 19 adds no `--show-private` escape hatch. A future
interactive display would need a separate design that addresses shell history,
CI logs, agent transcripts, and redirection.

All retained and displayed errors use the shared sanitizer. Artifact metadata
stores a stable error class and bounded safe message, never `repr()` of a raw
Canvas/request exception. A command may name an explicit user-supplied path in
an actionable error; it may not echo a secret-bearing URL or private payload.

## Report Manifest Migration

Report manifest schema version 2 removes machine- and maintainer-specific
provenance while retaining enough information for discovery and audit.

The v2 manifest:

- adds `manifest_schema_version: 2` and `artifact_class`;
- retains command name, timestamp/date, bounded slug, danvas version, course ID
  when needed, snapshot timestamp, status, safe error, and relative file list;
- removes `argv`, absolute `run_directory`, and absolute `project_root`;
- replaces `input_paths` with project-relative path references or a bounded
  `{"scope": "external"}` placeholder;
- rejects recorded files outside the report bundle instead of falling back to
  an absolute path; and
- never retains tokens, signed/verifier URLs, raw exceptions, or private row
  content in the manifest.

Private report runs move from `.danvas/reports/` to
`.danvas/private/reports/`. `reports list` and `reports latest` must continue to
discover existing v1 runs in `.danvas/reports/` as well as v2 public and private
runs. Readers treat a missing version as v1 and retain the existing legacy
privacy boolean. They do not rewrite old evidence in place.

Discovery identifies a run by `(storage_scope, relative_run_directory)`, where
`storage_scope` distinguishes the ordinary and private report roots. Two roots
may independently contain the same `YYYY-MM-DD-NNN-<slug>` directory name; list
and JSON output retain both without collision. Latest selection orders by the
manifest timestamp and then that stable scoped identity rather than silently
deduplicating equal directory names.

Persisted report-discovery JSON uses paths relative to the selected reports
root. Existing terminal discovery may resolve a local path for operator use,
but a file written with `--output` must not embed an absolute project or report
root unless the user later opts into a separately designed local-debug format.

## Source Map And Trackable Project State

Source maps are intended to be trackable deployment provenance, and
`.danvas/config.toml` is intended to be trackable non-secret project
configuration. Neither is `shareable` by default: both are `course_internal`
and may reveal course names, course/object IDs, assignment-group IDs, schedules,
and deployment history. Public repositories should use generic configuration
or ignore those files locally when that metadata should remain private.

Tokens never belong in either file.

`source_path_key()` must stop returning an absolute fallback. A source-map path
must be relative to the resolved project root. A source outside that root is
rejected during preflight, before Canvas mutation, whenever the command would
read or write source-map provenance. Dry-run and live resolution use the same
containment rule so a plan cannot promise a live transaction that will later
fail only while writing provenance.

The stable diagnostic is: `Source is outside the danvas project root; move it
into the project or pass the correct --project-root.` The migration guide must
reproduce that exact text so existing external-source workflows can recognize
and remediate the compatibility break.

This release does not introduce opaque hashes for external paths because they
would make provenance non-resolvable and disguise a project-layout error. Users
must copy or move authored sources into the project, or select the correct
`--project-root`.

## Git Ignore Contract

`danvas init` writes this idempotent generated-artifact block when the target is
a Git worktree:

```gitignore
.danvas/course.json
.danvas/reports/
.danvas/private/
```

The first two entries already exist in current initialization behavior; only
`.danvas/private/` is new. Repeated initialization must not duplicate or reorder
unrelated user rules.

The migration guide must explain that adding an ignore rule does not untrack an
already committed artifact. It provides commands for inspecting and removing a
specific known file from the Git index, but danvas does not automatically run
`git rm`, rewrite history, delete existing exports, or claim that a public
artifact has been retracted. Suspected credentials require rotation; student
data in published history requires institutional/privacy review.

## Roster Schema Correction

The default roster schema becomes:

```text
CanvasID,Name,LoginID,SIS_ID
```

`LoginID` is accurate for Canvas `login_id`; danvas must not continue to label
it as email. `--schema legacy-v1` emits the existing
`CanvasID,Name,Email,SIS_ID` header for bounded compatibility and prints a
deprecation warning. The value is not transformed in either schema.

The legacy schema remains throughout the public-readiness program and is not
removed before `0.19.0`. Documentation and tests must not describe `login_id`
as a verified email address.

Consumers inside this repository must accept both headers during the migration.
Ambiguous input containing both `LoginID` and `Email` is rejected unless their
normalized values are identical for every row.

## Protected Recording Corrections

Panopto caption, session, and folder artifacts are private. Their destination
directory, download temporary files, caption text, JSON/CSV manifests, and any
session sidecars all use the secure boundary.

Default manifests remove `viewer_url` and any signed, verifier, launch, or
session URL capable of granting or replaying access. Stable, non-authorizing
session IDs may remain when required to select or reconcile captions. The CLI
must not print reusable access URLs. A request for a full raw Panopto payload is
not added in this sprint.

## Compatibility And Migration

`0.16.0` is intentionally a behavior-changing alpha release. The migration
guide must enumerate each affected command rather than describing the change as
generic privacy hardening.

Existing behavior changes as follows:

- Private defaults that wrote into the current directory now resolve beneath
  `.danvas/private/` when a course project is available.
- A private command without a project no longer uses a generic default; it
  requires an explicit destination before Canvas access.
- Private files are no longer chmodded after writing; they are mode `0600`
  from creation.
- New private report runs live under `.danvas/private/reports/` instead of
  `.danvas/reports/`; old runs remain discoverable.
- Roster stops labeling `login_id` as `Email`; the default header is `LoginID`
  and `--schema legacy-v1` preserves the old header.
- Discussion, feedback, and media paths stop printing student-level details;
  terminal output is aggregate and details are retained privately.
- Panopto manifests no longer include `viewer_url`; reusable access URLs are
  omitted.
- Report manifests stop retaining absolute paths and full argv; v2 manifests
  contain bounded relative provenance.
- Out-of-project sources no longer become absolute source-map keys; they fail
  preflight with project-root guidance.

Explicit private output paths remain supported and become securely created.
Existing v1 reports, existing source maps with relative paths, and the legacy
roster schema remain readable. Existing absolute source-map entries are
reported with migration guidance; they are not silently rewritten because an
automatic guess could bind provenance to the wrong source.

No command may infer that an existing ordinary file should be moved, chmodded,
deleted, or untracked. Migration examples operate on explicit paths selected by
the user.

## Implementation Sequence

The sprint is implemented and reviewed in these bounded groups:

1. **Characterization and registry.** Freeze the command/output inventory,
   legacy schemas, default paths, report discovery, current permissions, and
   terminal leakage with tests. Add the typed classification registry and make
   unclassified output-producing commands fail the inventory test.
2. **Secure artifact primitive.** Add creation-time directory/file modes,
   exclusive/no-clobber behavior, atomic overwrite, secure streaming, bundle
   metadata, containment, symlink rejection, and unsupported-platform checks.
3. **Reports and provenance.** Add manifest v2, split public/private report
   roots, dual-root discovery, relative persisted paths, and source-map
   containment preflight.
4. **Private command migration.** Route roster, overrides, gradebook, quiz,
   submission, grades, discussion, announcement-export, and Panopto paths
   through the primitive. Remove post-write chmod as the enforcement path.
5. **Output correction.** Apply `LoginID`, aggregate private terminal output,
   Panopto URL removal, secure sidecars, and raw-output help text.
6. **Initialization and migration docs.** Add the private ignore, the
   command-by-command migration table, tracking guidance, examples, and
   durable-context amendment.
7. **Release gate.** Run the complete frozen suite and isolated install smoke,
   then obtain the deferred independent review before tagging `0.16.0`.

Each group should be a logical commit. Review findings may add focused tests and
repairs, but must not pull Sprint 20 mutation-mode work into this release.

## Test Matrix

### Artifact primitive

- Directory and file modes are exactly private with process umask `000`.
- JSON, CSV, text, bytes, streamed downloads, sidecars, and report files are
  private from creation.
- A forced exception after first-byte write never exposes a permissive file.
- No-clobber rejects an existing target or sidecar without changing either.
- A pre-existing `.part`, staging, or temporary target is refused and never
  unlinked as though the current process created it.
- Explicit overwrite uses a private temporary file and atomic replacement.
- An injected crash between data and sidecar commit leaves a missing or
  SHA-256-mismatched sidecar and is detected as invalid on the next read.
- Default-root traversal and existing/new symlinks are rejected.
- An explicit external destination does not chmod unrelated ancestors.
- Unsupported platforms fail before network access or filesystem mutation.

### Resolution and initialization

- Project discovery chooses `.danvas/private/` from a nested working directory.
- Explicit destinations win without changing profile/auth precedence.
- No-project omission fails before auth with the correct explicit option.
- Default filenames contain bounded IDs/slugs and no user names or free text.
- Init adds `.danvas/private/` once and preserves unrelated `.gitignore` rules.

### Reports and provenance

- V2 public manifests contain no absolute roots, argv, token-shaped values, raw
  errors, student content, or signed URLs.
- Private manifests and every referenced file are mode `0600` under a `0700`
  run tree.
- Files outside a report bundle cannot be recorded as an absolute fallback.
- V1 public/private and v2 public/private runs remain discoverable in date/slug
  order across both roots.
- Equal run-directory names in the ordinary and private roots remain distinct
  through their scoped identities and deterministic latest ordering.
- Persisted discovery output uses relative paths.
- Out-of-project source paths fail before a mocked Canvas write; project-
  relative paths remain stable across two checkout locations.

### Command migration

- Every command in the private inventory uses the shared boundary for default,
  explicit, raw, report, rollback, manifest, sidecar, partial, and failure
  outputs.
- Registry coverage includes `announcements latest` and every other inspection
  command exposing an explicit or implicit retained-output option.
- Explicit gradebook and quiz-analysis paths match report-run protections.
- Roster default and legacy schemas are exact and internal readers accept both.
- Discussion scoring and submission feedback stdout contain no fixture student
  name, Canvas user ID, login ID, score, comment, or matched filename.
- Submission media and Panopto failure paths leave no permissive partial file.
- Panopto manifests contain no viewer, signed, verifier, launch, or session URL.
- A raw private export is classified in data/sidecar metadata and CLI help.

### Regression and release

- Existing no-clobber behavior remains default.
- Existing explicit outputs remain usable on supported POSIX systems.
- Existing v1 reports and relative source maps remain readable.
- Auth/profile precedence and offline `auth doctor` behavior remain unchanged.
- Ruff, ty, frozen supported-Python tests, coverage/complexity ratchets,
  dependency audit, Markdown lint/link checks, build, editable/wheel smoke, and
  exact-tag smoke all pass on the release commit.

## Acceptance Criteria

Sprint 19 is complete only when all of the following are true:

- [ ] Every file-producing command has a reviewed artifact-class declaration.
- [ ] Every private output named in the inventory routes through the central
  artifact boundary, including raw, explicit, report, rollback, sidecar,
  download, partial, and error paths.
- [ ] With umask `000`, private directories/files exist as `0700`/`0600` from
  creation and remain protected during injected failures.
- [ ] Private defaults resolve beneath `.danvas/private/` in a project and fail
  before Canvas access without a project or explicit destination.
- [ ] Private artifacts no-clobber by default and explicit overwrite is atomic.
- [ ] Routine terminal output contains no private row-level fixture data.
- [ ] Roster uses `LoginID` by default and offers the documented legacy schema.
- [ ] Panopto artifacts contain no reusable viewer or signed access URL.
- [ ] Report manifest v2 contains only bounded provenance and dual-root
  discovery preserves existing evidence.
- [ ] Source maps cannot persist an absolute source path, and live commands
  validate containment before mutation.
- [ ] Init ignores `.danvas/private/` idempotently and migration docs explain
  already-tracked/history limitations.
- [ ] `.danvas/config.toml` and `.danvas/source-map.json` tracking guidance is
  explicit and consistent.
- [ ] The durable Report Output Contract is amended through the approved
  project-context workflow.
- [ ] No Sprint 20 mutation-mode behavior or direct discussion-grade upload
  rewrite is included.
- [ ] The complete local and CI release gates pass on one exact commit.
- [ ] Deferred independent review covers Sprint 18 implementation, the 0.15.1
  correction, and this Sprint 19 design/implementation before the 0.16.0 tag.

## Non-Goals

- Rewriting Git history or automatically untracking/deleting legacy artifacts;
- inferring whether arbitrary course content is legally or institutionally
  shareable;
- encrypting artifacts, managing retention, or replacing institutional storage
  policy;
- supporting non-POSIX permission semantics before a separately tested design;
- changing Canvas mutation defaults, `--apply`, `--upload`, grade transaction
  readback, or feedback stop policy owned by Sprint 20;
- generalizing course layouts, gradebook locale aliases, file-ignore defaults,
  packaging, or public-beta claims owned by Sprint 21;
- displaying private rows in the terminal through a new convenience flag;
- installing agent skills or implementing Sprint 22; or
- live Canvas field acceptance unless separately proposed and explicitly
  authorized.

## Review Focus

The deferred review should concentrate on five adversarial questions:

1. Can any successful, failed, or interrupted private write expose content with
   permissive mode bits, including temporary and partial download files?
2. Does any private command path bypass the boundary through explicit output,
   raw output, rollback, report, sidecar, or exception handling?
3. Can a persisted public manifest/source map retain an absolute personal path,
   sensitive argument, raw exception, student field, or reusable access URL?
4. Does any no-project command reach authentication or Canvas before rejecting
   an omitted private destination?
5. Can compatibility behavior silently overwrite, relocate, chmod, delete, or
   untrack an existing user artifact?

Review should also challenge the `course_internal` versus `private`
classification table. Reclassification toward `private` is allowed within the
sprint; weakening a named private output requires revising the accepted
public-readiness program rather than an implementation shortcut.
