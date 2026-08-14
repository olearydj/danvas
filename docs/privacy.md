# Privacy And Retained Artifacts

Danvas handles course configuration, instructor-authored material, grades,
submissions, comments, rosters, discussion responses, and protected recordings.
The operator remains responsible for institutional data-handling, disclosure,
and retention requirements.

## Artifact Classes

Danvas uses three classifications:

`shareable`
: Output intentionally designed for public sharing. A classification is not a
  substitute for reviewing the actual content.

`course_internal`
: Course metadata, authored sources, snapshots, reports, and downloaded course
  files that may disclose schedules, titles, Canvas object IDs, deployment
  history, or restricted instructor material.

`private`
: Student-identifying or protected data, including rosters, submissions,
  grades, comments, discussion responses, feedback plans/results, assignment
  override membership, gradebook exports, and protected captions.

Payloads inherit the most sensitive applicable class. Canvas course files are
classified as course-internal by default, but Canvas cannot prove that an
instructor-uploaded file contains no student or restricted data. Choose a
private destination when the content requires one.

## Private Root And Permissions

Inside an initialized project, omitted private-output paths resolve beneath:

```text
.danvas/private/
```

Outside a project, commands producing private output require an explicit
`--output`, `--output-dir`, or `--rollback-dir` before Canvas authentication.

On supported POSIX systems, danvas creates private directories with mode
`0700` and files with mode `0600` from creation, including temporary files. It
rejects symlinks at protected boundaries and does not overwrite private
artifacts by default. Explicit overwrite uses staged atomic replacement and
detectable data/sidecar consistency; a crash may leave a pair detectably
invalid rather than pretending it committed.

Windows is unsupported because this permission contract cannot be promised
there.

## Credential Transport

Danvas does not store a Canvas token or contact a secret provider. It reads one
selected environment variable or one externally managed credential file. The
selected environment entry is removed before Canvas construction to limit
ordinary child-process inheritance, but this is not memory zeroization. A file
is read once and never created, modified, chmodded, renamed, or deleted by
danvas.

Credential values are excluded from terminal output, reports, snapshots,
sidecars, and diagnostic JSON. Auth doctor may name an environment-variable
locator because it is actionable non-secret metadata; a credential-file locator
is reported only as a redacted classification, never as an absolute path.

Environment injection and file delivery have different exposure boundaries.
Global exports can reach unrelated children. Per-command external runners bound
the value to their process tree subject to their own guarantees. File safety
depends on the filesystem, mount, user, and host policy. Danvas validates its
input but does not claim any transport is universally safer.

## Integrity Sidecars And Manifests

Standalone private CSV, text, and binary files normally receive a companion
artifact sidecar containing classification, command identity, and SHA-256.
Media downloads retain one authoritative `.info.json` sidecar. Private JSON
may embed its own artifact metadata.

A sidecar is committed after its data file. Missing or mismatched sidecars mean
the artifact is incomplete or tampered with and must not be treated as valid.

Report manifest version 2 records project-relative or bundle-relative inputs.
It omits raw command lines and absolute project, input, and run paths. Inputs
outside the project or bundle are represented as external rather than exposing
the path.

Panopto caption bundles use `artifact-manifest.json` as the final commit marker.
An interrupted bundle without that marker is reconciled read-only by session
identity and sidecar hash. Unexpected, duplicate, missing, or tampered pairs are
blockers; danvas does not delete them or create a suffixed duplicate.

## Terminal Output

Private workflows print aggregate counts and bounded artifact roots rather than
student rows. Routine output does not repeat student names, login IDs, Canvas
user IDs, grades, comments, feedback filenames, or protected recording URLs.

Errors may identify an explicit operator-supplied path when that path is needed
for remediation. Treat transcripts as potentially sensitive anyway: shell
prompts, paths, and surrounding tools can add information outside danvas's
control.

## Tracking And Sharing

`danvas init` adds generated snapshots, reports, and private artifacts to
`.gitignore` when the project is a Git repository. Verify that the following
remain ignored:

```text
.danvas/course.json
.danvas/reports/
.danvas/private/
```

`.danvas/config.toml` and `.danvas/source-map.json` contain no credentials, but
they can expose course IDs, source paths, schedules, and deployment provenance.
They may be reasonable in a private course repository and inappropriate in a
public one.

Never commit Canvas tokens, `.env` files, raw API responses, private artifact
bundles, unreviewed downloaded files, or copied grading evidence.

## Retention And Disposal

Danvas does not impose an institutional retention schedule. Before deleting an
artifact, consider whether it is the only evidence supporting a grade or other
consequential action. Before retaining it, consider whether policy still permits
storage on that device and in that location.

Prefer encrypted storage and bounded access for retained private artifacts.
Use the operating system's approved secure-removal or device-management process
when policy requires disposal; deleting a Git-tracked file does not remove it
from history.

## Related Guides

- [Authentication](authentication.md)
- [Mutation Safety](mutation-safety.md)
- [Compatibility](compatibility.md)
- [0.16.0 private-artifact migration](migrations/0.16.0.md)
