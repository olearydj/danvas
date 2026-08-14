# Configuration

Danvas has two non-secret configuration layers:

- a user configuration for reusable Canvas instance profiles; and
- `.danvas/config.toml` inside a course project.

Tokens do not belong in either file. See [Authentication](authentication.md)
for credential references and diagnostics.

## User Profiles

The user configuration file is `danvas/config.toml` beneath the
platform-standard configuration directory:

- macOS: `~/Library/Application Support/danvas/config.toml`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/danvas/config.toml`

```toml
default_profile = "example-university"

[profiles.example-university]
api_url = "https://canvas.example.edu/"
timezone = "America/New_York"
secret_name = "canvas-example-university"
secret_provider = "env"
api_key_env = "CANVAS_EXAMPLE_API_KEY"
```

A profile may contain `api_url`, `timezone`, `secret_name`,
`secret_provider`, `op_reference`, and `api_key_env`. Unknown keys, unknown
providers, and raw secret values are rejected.

Profile selection resolves in this order:

1. `--profile`
2. project `[canvas].profile`
3. `DANVAS_PROFILE`
4. user `default_profile`

The Canvas API URL resolves separately:

1. `--api-url`
2. project `[canvas].api_url`
3. selected profile `api_url`
4. `CANVAS_API_URL`

An initialized project therefore cannot be redirected by a generic shell
`CANVAS_API_URL`. If an explicitly selected profile names a different host than
the project, danvas keeps the project URL and prints a warning so the operator
can verify that the credential belongs to that instance.

## Course Projects

Initialize a new course project with a Canvas course ID:

```bash
danvas init 101 --profile example-university
```

The command writes `.danvas/config.toml` and a generated
`.danvas/course.json` snapshot. A typical project configuration begins with:

```toml
[canvas]
course_id = 101
api_url = "https://canvas.example.edu/"
profile = "example-university"
timezone = "America/New_York"
```

The project file contains stable operational configuration, not credentials.
It may still disclose course IDs, schedules, source conventions, and deployment
history. Review it before publishing a course repository.

Init also records current assignment-group name-to-ID mappings:

```toml
[assignment_groups]
Practice = 202
Projects = 303
```

Authored assignments may use `assignment_group_name` instead of repeating the
numeric ID. Supplying both `assignment_group_name` and `assignment_group_id` is
an error.

An explicit `init --timezone` must be an IANA timezone and is validated before
credentials or Canvas are accessed. Without it, init tries recognized Canvas
course metadata and then the selected profile. Unknown timezone metadata is not
guessed.

## Source Layouts

New projects default to `standard-v1`. Init materializes the complete effective
source configuration so discovery does not depend on hidden defaults:

```toml
[sources]
layout = "standard-v1"

[sources.announcements]
include = ["content/announcements/*.md"]
output_dir = "content/announcements"

[sources.discussions]
include = ["content/discussions/*.md"]
output_dir = "content/discussions"

[sources.quizzes]
include = ["content/quizzes/*.md"]

[sources.assignments]
include = ["content/assignments/*.md"]
require_assignment_metadata = true

[sources.pages]
include = ["content/pages/*.md", "content/pages/*.html"]
exclude = ["content/pages/*-preview.html"]
output_dir = "content/pages"
```

Choose the older layout explicitly for a new project when needed:

```bash
danvas init 101 --source-layout legacy-v1
```

Existing initialized projects without a `[sources]` table continue to resolve
as `legacy-v1`. `init --force` preserves the existing effective layout unless
`--source-layout` is explicit. Danvas never infers a layout from filenames and
does not move or generate authored content during init.

Every source path must be project-relative and may not contain parent
traversal. `include`/`includes` and `exclude`/`excludes` are compatibility
spellings, as are singular and plural source-kind table names. Configuring both
the singular and plural table for one kind is an error.

Announcements, discussions, and Pages require an `output_dir` when custom
include patterns do not have one unambiguous static parent. Status and sync
commands use the same resolved directory.

See [Authored Sources](authored-sources.md) for the format boundary and
migration behavior.

## File Inventory Policy

File inventory always excludes danvas and Git machinery plus the active output
directory. Conventional convenience ignores can be extended or replaced:

```toml
[files.inventory]
use_default_ignores = true
ignore = ["scratch/**", "build/**"]
```

Set `use_default_ignores = false` to remove conventions such as `grading/`,
`_archive/`, `_inventory/`, `.obsidian/`, and `node_modules/`. Mandatory
`.git/`, `.danvas/`, and active-output exclusions remain. Inventory reports
record the effective policy.

Ignore patterns must be relative to the course root and may not use parent
traversal.

## Panopto Integration

Panopto support is experimental and deployment-dependent. Configure only
non-secret selectors:

```toml
[integrations.panopto]
caption_language = "English_USA"
tool_name = "Panopto Video"
# tool_id = 202
# base_url = "https://media.example.edu/"
```

Configure either `tool_name` or `tool_id`, not both. A name is an exact
case-insensitive navigation-label match; an ID is preferable when labels
collide. `base_url` must be an HTTPS origin without credentials, path, query,
or fragment.

CLI selectors override project settings. Project settings override the
experimental built-in discovery and `English_USA` language fallback. Unknown
keys and unsafe values fail before secret resolution or LTI launch.

## Course Policy YAML

Assignment and gradebook audits may also read `course.yaml`. It carries policy,
not connection settings. See [Course YAML](course-yaml.md) for weights,
exclusions, final-score reconstruction, and gradebook heading aliases.
