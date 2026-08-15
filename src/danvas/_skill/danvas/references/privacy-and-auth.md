# Danvas Privacy And Authentication

## Artifact Classes

- `shareable`: designed for its documented public or generic use.
- `course_internal`: operational course material, not automatically publishable.
- `private`: may contain student identity, grades, submissions, comments,
  discussion participation, feedback, or protected recording content.

Private project defaults live beneath `.danvas/private/`. Danvas creates
protected directories/files on supported POSIX platforms, stages writes, rejects
unsafe symlinks, and uses integrity sidecars or manifest-last commit markers where
the artifact contract requires them.

Explicit destinations remain the operator's responsibility. Do not weaken the
classification because a path was requested explicitly.

## Credential Boundary

Danvas selects exactly one neutral credential transport:

- `--api-key-env NAME` or profile/process/default environment selection; or
- `--api-key-file /absolute/path` or profile/process selection.

The Canvas origin must be bound before the credential is read. Credential files
are bounded, single-purpose, and rejected from inside a course project. Selected
credential environment variables are removed before Canvas client construction.

External tools may inject the environment value or project a file, but their
provider/account/session policy is outside danvas. Never put token values in
project config, command arguments, logs, guides, or retained artifacts.
