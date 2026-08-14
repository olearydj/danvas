# Classic Quiz Workflows

Danvas supports two deliberately separate Classic Quiz workflows:

- `quiz import-qti` plans or applies a QTI import; and
- `quiz export-analysis` acquires Canvas's official student-analysis CSV for
  local inspection by `quiz analysis`.

These commands target Classic Quizzes. They do not claim New Quizzes report or
package compatibility.

## Export Then Analyze

Plan the official report request first:

```bash
danvas quiz export-analysis --course-id 101 --quiz-id 202
```

The plan may list matching report metadata using stable numeric IDs. It does
not request a report, poll progress, or download a file. Review the course ID,
quiz ID, version scope, private destination, and any existing matching reports.

Creating or reusing the report uses a Canvas `POST`. It is therefore a Canvas
mutation even though it changes no questions, grades, or course visibility.
Apply only after authorization:

```bash
danvas quiz export-analysis --course-id 101 --quiz-id 202 --apply
```

In an initialized project, the verified CSV defaults to:

```text
.danvas/private/quizzes/quiz-202/student-analysis.csv
```

The data file is committed with a SHA-256 integrity sidecar. Both are private,
no-clobber artifacts. Use `--overwrite` only after deliberately reviewing the
existing pair. Outside a project, provide an explicit `--output` before danvas
will authenticate.

Analyze the acquired CSV locally:

```bash
danvas quiz analysis \
  .danvas/private/quizzes/quiz-202/student-analysis.csv
```

Narrow an answer count to question text terms when useful:

```bash
danvas quiz analysis \
  .danvas/private/quizzes/quiz-202/student-analysis.csv \
  --answer-term "case deadline"
```

`quiz analysis` is local-only. It does not authenticate or mutate Canvas.
Browser-downloaded Classic Quiz student-analysis CSVs remain valid inputs.

## Version Scope

The default report covers Canvas's current quiz version. Request all versions
only when the analysis requires it:

```bash
danvas quiz export-analysis \
  --course-id 101 \
  --quiz-id 202 \
  --includes-all-versions
```

The all-versions setting is part of report identity. A report for one scope is
never treated as a match for the other.

## Supported And Excluded Quiz Types

Acquisition supports Classic Quizzes and identified Surveys whose report CSV
contains the stable `id` and `submitted` columns. Anonymous Surveys are refused
before report creation because their export can omit that identity signature.
An anonymously downloaded CSV may still be inspected locally when the
permissive `quiz analysis` parser can understand it.

New Quizzes use a different Canvas service and report shape. They are not
supported by `quiz export-analysis` or `quiz import-qti`.

## Progress, Evidence, And Safe Retry

Applied report generation is asynchronous. Danvas defaults to polling every two
seconds for at most 120 seconds. `--poll-seconds` and `--timeout-seconds` may
change those positive bounded values.

Danvas attempts report creation once, then reconciles Canvas report state. A
`409 Conflict` continues only when exactly one report matches the requested
course, quiz, type, and version scope. A transport exception after possible
acceptance is not treated as failure or permission to retry.

Successful completion is `applied_verified`: stable report/progress/file IDs
were reconciled, the CSV passed structural validation, and the private pair was
committed. `accepted_unverified`, `conflict`, timeout, failed progress, invalid
CSV, download failure, or output collision exits nonzero with a bounded safe
next action.

Never blindly repeat `--apply` after an uncertain outcome. Inspect the retained
private evidence and verify existing reports first. Protected progress URLs,
signed file URLs, raw Canvas payloads, student rows, answers, scores, and
question text are not retained in command evidence or printed to the terminal.

## Interface Boundary

Missing danvas coverage does not authorize a direct Canvas API call, browser
automation, or provider-specific fallback. Classify the proposed endpoint
effect and ask the operator before leaving the supported interface. See
[Mutation Safety](mutation-safety.md) and
[Privacy And Retained Artifacts](privacy.md) for the standing contracts.
