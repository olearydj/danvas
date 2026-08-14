# Course YAML

`danvas` audit commands can use a small `course.yaml` file as the intended
course policy.

The file is optional, but it makes audits reproducible because it records the
expected gradebook weights, rows to exclude, and any final-score reconstruction
rules that Canvas does not make obvious from the gradebook export alone.

## Minimal Example

```yaml
final_score_column: Unposted Final Score
exclude_students:
  - "^Student, Test$"
weights:
  Homework: 25
  Tests: 30
  Project: 20
  Final Exam: 25
```

Use it with:

```bash
danvas assignments audit assignments-full.json --course-yaml course.yaml
danvas gradebook check final-canvas-gradebook.csv --course-yaml course.yaml
danvas gradebook audit final-canvas-gradebook.csv --course-yaml course.yaml
```

## Fields

`final_score_column`
: Preferred Canvas final score column. Common values are
  `Unposted Final Score`, `Final Score`, `Unposted Current Score`, and
  `Current Score`.

`exclude_students`
: Regular expressions matched against the Canvas `Student` column. Use this for
  test students or known non-course rows.

`weights`
: Expected assignment group weights as percentages. Group names should match
  Canvas assignment group names.

`assignment_groups`
: Alias for `weights`. It may be a mapping of group name to weight or a list of
  objects with `name` and `weight` fields. Prefer `weights` for new files unless
  an existing course config already uses `assignment_groups`.

`final_score_reconstruction`
: Optional rules for courses where the posted final score is a base score plus
  adjustment assignments.

`gradebook_heading_aliases`
: Exact heading aliases for a known Canvas gradebook export. Aliases extend the
  built-in English headings; they are not general locale detection. Supported
  roles include `student`, `id`, `sis_user_id`, `sis_login_id`, `section`,
  `email`, `root_account`, `points_possible`, and the four score and grade roles.

```yaml
gradebook_heading_aliases:
  student: [Étudiant]
  id: [Identifiant]
  points_possible: [Points possibles]
  unposted_final_score: [Note finale non publiée]
  final_score: [Note finale]
  unposted_final_grade: [Évaluation finale non publiée]
```

Matching trims surrounding heading whitespace but is otherwise exact and
Unicode-preserving. The same score aliases identify assignment-group total
suffixes. A configured alias may belong to only one canonical role, and an
export containing multiple headings for one role is rejected as ambiguous.

## Reconstruction Example

```yaml
final_score_column: Unposted Final Score
weights:
  Homework: 25
  Tests: 30
  Project: 20
  Final Exam: 25
final_score_reconstruction:
  base_assignment: Raw Average (201)
  adjustment_assignments:
    - Final Exam Adjust (202)
    - Attendance Deductions (203)
    - Bonus Assignment (204)
```

When `base_assignment` is present, `danvas gradebook audit` compares:

```text
base_assignment + adjustment_assignments == final_score_column
```

When `base_assignment` is absent, it compares the weighted Canvas group scores
to the final score column.
