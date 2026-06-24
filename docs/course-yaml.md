# Course YAML

`danvas` audit commands can use a small `course.yaml` file as the intended course policy.

The file is optional, but it makes audits reproducible because it records the expected gradebook weights, rows to exclude, and any final-score reconstruction rules that Canvas does not make obvious from the gradebook export alone.

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
: Preferred Canvas final score column. Common values are `Unposted Final Score`, `Final Score`, `Unposted Current Score`, and `Current Score`.

`exclude_students`
: Regular expressions matched against the Canvas `Student` column. Use this for test students or known non-course rows.

`weights`
: Expected assignment group weights as percentages. Group names should match Canvas assignment group names.

`assignment_groups`
: Alias for `weights`. It may be a mapping of group name to weight or a list of
  objects with `name` and `weight` fields. Prefer `weights` for new files unless
  an existing course config already uses `assignment_groups`.

`final_score_reconstruction`
: Optional rules for courses where the posted final score is a base score plus adjustment assignments.

## Reconstruction Example

```yaml
final_score_column: Unposted Final Score
weights:
  Homework: 25
  Tests: 30
  Project: 20
  Final Exam: 25
final_score_reconstruction:
  base_assignment: Raw Average (14875304)
  adjustment_assignments:
    - Final Exam Adjust (14875406)
    - Attendance Deductions (14702073)
    - Bonus Assignment (14702074)
```

When `base_assignment` is present, `danvas gradebook audit` compares:

```text
base_assignment + adjustment_assignments == final_score_column
```

When `base_assignment` is absent, it compares the weighted Canvas group scores to the final score column.
