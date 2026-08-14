# danvas

`danvas` is a safety-focused command-line tool for day-to-day Canvas course
operations. It helps instructors inspect courses, manage authored content,
download submissions, reconcile grades, and retain evidence for consequential
changes.

Status: the signed `v0.18.0` release is the planned public beta, not a 1.0
stability promise. Before that tag passes the release gates, this tree is a
candidate and must not be represented as released. This is an unofficial
project and is not affiliated with or endorsed by Instructure.

## What It Does

- initializes course projects and snapshots Canvas metadata;
- audits assignments, Pages, files, and gradebook exports;
- creates and updates assignments, announcements, discussions, and Pages from
  local sources;
- downloads rosters, submissions, feedback material, and course files;
- plans and verifies grade, comment, feedback, quiz-import, and file-upload
  transactions;
- scores discussions into a private `grades post`-compatible plan; and
- experimentally downloads Panopto captions through a Canvas LTI launch.

It intentionally does not manage archival ledger or history databases.

## Requirements

- Linux or macOS;
- Python 3.12, 3.13, or 3.14; and
- [`uv`](https://docs.astral.sh/uv/) for the supported installation path.

Windows is unsupported because danvas cannot enforce its POSIX private-file
permission contract there.

## Install

Install the exact `0.18.0` tag anonymously over HTTPS:

```bash
uv tool install \
  "danvas-cli @ git+https://github.com/olearydj/danvas.git@v0.18.0"
```

The Python distribution is named `danvas-cli`; the installed command and import
package remain `danvas`. Users upgrading from `0.17.x` must remove the old
distribution first. Follow the
[0.18.0 migration guide](docs/migrations/0.18.0.md) rather than forcing one
distribution over the other.

Verify the installation outside a source checkout:

```bash
uv tool list
danvas --version
danvas --help
danvas auth doctor
```

## Five-Minute Setup

Create a user profile containing non-secret instance and credential references.
The configuration file is `danvas/config.toml` beneath your platform-standard
user configuration directory.

```toml
default_profile = "example-university"

[profiles.example-university]
api_url = "https://canvas.example.edu/"
timezone = "America/New_York"
secret_provider = "env"
api_key_env = "CANVAS_EXAMPLE_API_KEY"
```

Set the referenced token without writing it into either configuration file:

```bash
export CANVAS_EXAMPLE_API_KEY="your-canvas-token"
danvas auth doctor --profile example-university --check-canvas
```

Initialize a course project. New projects materialize the `standard-v1` source
layout in `.danvas/config.toml`; they do not move or create authored files.

```bash
mkdir example-course
cd example-course
danvas init 101 --profile example-university
danvas status
```

Course IDs, permissions, and available endpoints come from your Canvas
deployment. Danvas cannot bypass institutional policy or Canvas authorization.

## Safety Model

Canvas-changing commands plan by default. Omitting both flags never authorizes
a Canvas mutation:

```bash
danvas assignments update content/assignments/week-01.md
danvas assignments update content/assignments/week-01.md --apply
```

`--dry-run` is the explicit spelling for the same plan mode. Some higher-risk
commands also require a command-specific `--confirm` value. Local-writing sync
commands keep their own `--dry-run` behavior and never gain `--apply` merely for
writing local sources.

Review generated evidence before applying and after any uncertain outcome. Do
not blindly retry a request reported as accepted but unverified.

Private artifacts default beneath `.danvas/private/` in initialized projects.
On supported POSIX systems, danvas creates private directories as `0700` and
files as `0600`, including temporary files. It does not overwrite private
artifacts by default. Outside a project, private-output commands require an
explicit destination before authentication begins.

Operators remain responsible for institutional data-handling, sharing, and
retention requirements.

## Common Workflows

```bash
# Refresh the local course snapshot without changing Canvas.
danvas refresh --diff

# Validate authored sources without Canvas access.
danvas sources lint

# Plan and then apply one assignment update.
danvas assignments update content/assignments/week-01.md
danvas assignments update content/assignments/week-01.md --apply

# Create a private discussion-grade plan, review it, then use the grade engine.
danvas discussions score \
  https://canvas.example.edu/courses/101/discussion_topics/202 2 1 1 5
danvas grades post .danvas/private/discussions/topic-202/grade-plan.csv
danvas grades post \
  .danvas/private/discussions/topic-202/grade-plan.csv --apply

# Inspect retained report runs.
danvas reports list
danvas reports latest
```

Use `danvas --help`, group help such as `danvas assignments --help`, and leaf
command help for the current option surface.

## Documentation

- [Configuration](docs/configuration.md)
- [Authentication](docs/authentication.md)
- [Privacy and retained artifacts](docs/privacy.md)
- [Compatibility and support](docs/compatibility.md)
- [Authored sources](docs/authored-sources.md)
- [Mutation safety](docs/mutation-safety.md)
- [Course policy YAML](docs/course-yaml.md)
- [0.18.0 migration guide](docs/migrations/0.18.0.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

Sprint notes and the backlog record design history; they are not required user
instructions.

## Development

From a trusted checkout:

```bash
uv sync --frozen
uv run ruff check .
uv run ty check
uv run pytest --cov=danvas --cov-branch --cov-fail-under=82
uv run python scripts/check-docs.py
scripts/release-smoke.sh --expected-version 0.18.0
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete local gate, safe fixture
rules, and the no-live-Canvas default.

## License

MIT. See [LICENSE](LICENSE).
