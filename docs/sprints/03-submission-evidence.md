# Sprint 3: Submission Evidence And Metadata Exports

Status: implemented and verified on 2026-07-10.

## Objective

Make submission review and download folders auditable without raw Canvas scripts,
volatile signed URLs, duplicate directory layouts, or ad hoc hash checks.

## Command Surface

```bash
danvas submissions export --assignment-id 123 --output submissions.json
danvas submissions grades --assignment-id 123 --output graded-comments.csv
danvas submissions media --assignment-id 123 --output-dir grading/case1 \
  --layout flat
```

`submissions export` and `submissions grades` are explicit-output, private-data
commands. JSON and CSV are supported; raw Canvas payloads require `--save-raw` and
an explicit path.

## Export Contract

The metadata export includes Canvas user ID, optional name, submission ID,
attempt, workflow state, submitted/graded times, score/grade, grader ID,
late/missing/excused flags, attachment IDs/names/types/sizes, and comment counts.
Optional history and full text comments must be explicit because they increase
privacy and output size.

`submissions grades` emits a review-friendly flat file containing current grade,
attempt, grader, flags, and text comments. It does not download attachments.

## Media Evidence

- Preserve the current assignment-subdirectory layout as the compatibility
  default; add `--layout flat|assignment-subdir`.
- Warn when the requested output already ends with the assignment directory name
  and would create duplicate nesting.
- Write a top-level collision-safe CSV or JSON manifest by default.
- Record stable Canvas file/attachment IDs, local paths, SHA-256, byte size,
  content type, download time, source, and download/integrity status.
- Validate ZIP, DOCX, XLSX, and PPTX containers and surface failures prominently.
- Sidecars and manifests must omit verifier URLs and resolved signed CDN URLs.
- Existing files are not overwritten unless explicitly requested; skipped files
  remain represented in the manifest.

## Acceptance Criteria

- Metadata-only export works without downloading media.
- Grade/comment export supports `--only-graded` and preserves comment ownership
  metadata compatible with Sprint 1's comment-cleanup model.
- Flat layout does not create an extra assignment directory; compatibility layout
  remains unchanged.
- Office corruption, HTTP failure, duplicate filename, and existing-file cases
  are reflected in the manifest.
- Generated evidence is explicitly marked private and contains no token,
  verifier, or signed URL.

## Deferred

- Automatic local replacement of malformed submissions.
- Long-term archival or submission history databases.
- Exam reconciliation reports; this sprint supplies their reusable inputs.
