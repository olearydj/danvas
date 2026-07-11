# Sprint 8: Privacy And Filesystem Safety Hardening

Status: implemented and locally verified for 0.7.1. This sprint remediates the privacy, secret-handling,
and download-containment defects confirmed by the post-0.7.0 codebase audit at
commit `5988c93`.

## Objective

Make the repository's existing privacy and leakage-prevention rules enforceable
at every relevant output boundary. Private report runs must be private by
construction, untrusted Canvas file metadata must never escape the selected
download directory, and public diagnostics must not persist student identifiers,
signed URLs, access tokens, or raw Canvas upload payloads.

This is a patch-release hardening sprint. It does not add command surface or
broaden Canvas mutation behavior.

## Private Report-Run Contract

`create_report_run(private_data=True)` must carry that classification into the
returned `ReportRun`. Private runs include current gradebook check/audit and quiz
analysis reports and any future report explicitly classified as containing
private student data.

For a private run:

- create the run directory without group or other permissions
- remove group and other permissions from every JSON, CSV, Markdown, and other
  file written through `ReportRun`
- harden `manifest.json` even though it normally contains metadata rather than
  student rows
- apply permissions immediately after each completed write rather than waiting
  only for `finish()`, so an interrupted run does not leave readable artifacts
- retain the manifest field `may_contain_private_student_data: true`
- preserve normal user-owner permissions subject to the operating system and
  filesystem; the contract is that `mode & 0o077 == 0`

Private behavior must apply equally to sequenced default report directories and
explicit `--report-root` or `--report-dir` destinations. Public report runs keep
their existing umask-governed behavior.

`mark_private()` remains the shared file-hardening primitive. It must be safe to
call after a file has been written and must not add permissions that were absent.
Directory hardening may use a separate helper if that makes the distinction
clearer.

## Download Path Containment

Treat Canvas folder names and file display names as untrusted path input in
`danvas files download`.

- A sanitized path component that is empty, `.` or `..` becomes a safe
  placeholder and never retains traversal semantics.
- Continue removing separators, control characters, and platform-forbidden
  filename punctuation under the existing download naming profile.
- Before creating a directory or downloading a file, resolve the candidate
  target against the resolved `--output-dir` and require it to remain inside
  that directory.
- Perform the containment check at the final write boundary even when component
  sanitization has already succeeded.
- `--overwrite` permits replacement only of a contained target. It never weakens
  containment.
- A rejected target produces a sanitized, actionable error and no directory or
  file outside the output root.

Apply the same final-boundary rule to any shared helper used by targeted and
broad file downloads. Do not rely on Canvas UI or API validation to establish
local filesystem safety.

## Public Diagnostic Sanitization

Non-private status, Page, feedback-upload, and report artifacts must not include
raw secret-bearing or student-bearing exception/body text.

### Assignment override diagnostics

An invalid local override reference may report the path and a generic parse or
validation category. It must not embed the raw YAML parser exception because
parser diagnostics can reproduce the offending line from a private override
export, including Canvas user IDs.

Status reports remain classified as non-private and must not acquire private
override membership merely because a referenced file is malformed.

### Page update plans and reports

Never place a raw Canvas Page body into `changes.body.before`, stdout, or a
non-private report. Canonicalize the current Canvas body with the same configured
Canvas-origin and volatile-URL rules used for Page hashing and verification.

If the current body cannot be reduced to a safe canonical form, record a
redacted/blocked diagnostic rather than its content. A Page update may still be
blocked or described without persisting the unsafe body.

### Feedback upload errors

`danvas submissions feedback` must pass upload exception text through the shared
sanitizer before printing it. Student labels may retain the command's existing
explicit private-console behavior, but signed upload URLs, verifier values,
tokens, and raw Canvas response URLs must not appear.

### Shared report sanitizer

Align `reports.safe_error` with the repository's authentication and upload
sanitizers. At minimum, redact case-insensitive `token`, `access_token`,
`verifier`, `secret`, authorization/bearer credentials, signed URL parameters,
and complete URL-shaped values where the current report contract calls for URL
redaction. Key matching must not fail merely because `token` is preceded by an
underscore.

Prefer shared, narrowly named sanitization helpers over independent regular
expressions with silently different coverage. Preserve useful exception type and
non-sensitive context.

## Tests

Add focused tests that demonstrate the boundary rather than merely exercising a
helper:

- `mark_private()` removes all group/other bits from a deliberately permissive
  file and does not add owner permissions
- every file and the directory produced by a representative private report run
  satisfy `mode & 0o077 == 0`, including before and after `finish()`
- a representative public report run retains its existing behavior
- `.` and `..` Canvas path components cannot escape a temporary output directory
- a nested traversal attempt with `--overwrite` cannot replace a sentinel file
  outside the output directory
- normal nested Canvas paths still download to the expected relative target
- malformed override YAML containing a recognizable student ID does not place
  that ID in status JSON or Markdown
- Page plan/report fixtures containing verifier, `access_token`, and signed
  external URLs contain neither the values nor the raw URLs
- feedback-upload exceptions containing upload URLs and credentials are
  sanitized in captured output
- shared sanitizer tests cover URL and bare-key forms, case variants, and benign
  nearby text

Do not mark real security/error branches `pragma: no cover` merely because the
exact CanvasAPI exception class varies. Use a fake object that raises a stable
generic exception and assert the observable sanitized result.

## Acceptance Criteria

- All private report-run directories and files deny group/other permissions,
  including interrupted runs and manifests.
- Public report behavior and existing report discovery remain compatible.
- No Canvas-controlled folder or filename can cause broad or targeted downloads
  to create or overwrite a path outside the selected output root.
- `--overwrite` does not bypass containment.
- Public status and Page reports do not contain raw private override lines, full
  Canvas Page bodies, verifier URLs, signed URLs, tokens, or bearer credentials.
- Feedback upload failures retain useful sanitized diagnostics without exposing
  Canvas upload payloads.
- Permission and sanitization guarantees are verified at the produced-artifact
  boundary, not only through unit tests of internal regular expressions.
- Ruff, ty, and the complete pytest suite pass.
- README, backlog, project context, and external teaching-danvas guidance are
  updated only where operator-visible behavior or safety expectations change.

## Deferred

- Encryption at rest and protection from privileged system administrators or
  backup services.
- A general secret-scanning framework for arbitrary user-authored outputs.
- Reclassifying all console output as private; command-specific explicit private
  workflows retain their documented behavior.
- Complexity-only refactors in `files.py`, `pages.py`, `status.py`, and
  `overrides.py` unless a small extraction is necessary to implement or test the
  safety boundary clearly.
- Unrelated documentation ordering and general coverage expansion.
