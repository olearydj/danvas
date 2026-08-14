# Authentication

Canvas-backed commands require both an explicit Canvas instance and a token
accepted by that instance. Danvas has no institutional host, token, password
manager, or secret provider built in.

Create and revoke tokens through your Canvas account according to local policy.
Canvas administrators may restrict token creation, API endpoints, enrollment
visibility, or write permissions; danvas cannot bypass those controls.

## The Boundary Danvas Owns

Danvas consumes one credential through one of two provider-neutral transports:

- a selected process environment variable; or
- a selected absolute path to a single-purpose credential file.

Danvas does not choose, authenticate to, invoke, or diagnose the system that
stores the token. An individual or organization can use a shell, CI secret,
container mount, SecretSpec, 1Password, Vault, or another broker without adding
that provider to the danvas dependency or configuration surface.

User profiles store a locator, never the token:

```toml
[profiles.example-university]
api_url = "https://canvas.example.edu/"
api_key_env = "CANVAS_EXAMPLE_API_KEY"
```

The equivalent file-backed profile is:

```toml
[profiles.example-university]
api_url = "https://canvas.example.edu/"
api_key_file = "/run/secrets/canvas_api_key"
```

Raw `api_key`, `token`, `access_token`, and `credential` values are rejected in
user configuration. Course-project configuration may not select a credential
locator at all.

## Environment Transport

For a globally exported variable:

```bash
read -rs CANVAS_EXAMPLE_API_KEY
export CANVAS_EXAMPLE_API_KEY
danvas auth doctor --profile example-university --check-canvas
unset CANVAS_EXAMPLE_API_KEY
```

`read -rs` avoids putting the token in the command line or shell history. A
global export can still persist for the shell session and reach unrelated child
processes.

Danvas reads only the selected name. It rejects a missing, empty, NUL-containing,
or multiline value, removes the selected variable from its own process
environment before Canvas construction, and never tries a fallback after a
selected input fails. This limits ordinary child-process inheritance; it is not
memory zeroization and does not protect against same-user inspection,
administrators, debuggers, or crash dumps.

Danvas does not load shell startup files or dotenv files. A repository-local
`.env` has no effect on either the Canvas URL or credential.

## Credential-File Transport

A credential file contains exactly one token with an optional terminal LF or
CRLF. It is not a dotenv file or general configuration file.

```bash
CANVAS_API_KEY_FILE=/run/secrets/canvas_api_key \
  danvas auth doctor --profile example-university --check-canvas
```

The selected path must be absolute and resolve to a regular file. Danvas reads
it once through one opened descriptor, accepts at most 16 KiB, and rejects an
empty, NUL-containing, multiline, non-UTF-8, or project-contained value. A
projected-volume symlink is supported when its opened target passes those checks.

Danvas never creates, edits, chmods, rotates, renames, or deletes the source
file. On POSIX, a broad-permission file owned by the current user produces a
path-free warning; a root-owned read-only platform mount is not rejected merely
for mode `0444`. Filesystem mode is one part of the deployment boundary, not a
universal proof of safety.

## Input Selection Precedence

Credential selection is independent of Canvas URL selection:

1. `--api-key-env` or `--api-key-file`;
2. the selected profile's `api_key_env` or `api_key_file`;
3. `CANVAS_API_KEY_ENV` or `CANVAS_API_KEY_FILE`; and
4. the default environment variable `CANVAS_API_KEY`.

Defining both transports at one layer is an error. A higher layer replaces a
lower layer, but once one locator wins, a missing or invalid value is final.

The CLI and process selector values are locators, not tokens. Never pass a token
itself as an option value.

## Canvas Origin Binding

Danvas validates where a token may be sent before reading it. The effective API
URL must be bound by one of:

- a selected user profile with the same normalized HTTPS origin;
- an invocation-level `--api-url`; or
- a matching nonempty `CANVAS_API_URL`.

A project-only `[canvas].api_url` is insufficient because a cloned course
repository is not trusted to authorize a credential destination. A profile URL
that disagrees with the effective URL is a hard error, regardless of how the
profile was selected. There is no bypass flag.

For an existing project, the durable fix is a matching user profile plus the
profile name in the project:

```toml
[canvas]
course_id = 101
api_url = "https://canvas.example.edu/"
profile = "example-university"
```

See the [0.19.0 migration guide](migrations/0.19.0.md) for the expected
first-run failure and shell-session alternatives.

## Optional External Runners

These examples illustrate provider choice outside danvas. They are not danvas
dependencies or endorsements, and each external tool retains its own trust,
authentication, audit, and exposure model.

### SecretSpec

If a separately maintained SecretSpec manifest defines `CANVAS_API_KEY` and a
`danvas` scope, run:

```bash
secretspec run --scope danvas -- \
  danvas auth doctor --profile example-university --check-canvas
```

SecretSpec documents the command in its official
[CLI reference](https://secretspec.dev/reference/cli/#run) and explains scoped
child environments in its [scope guide](https://secretspec.dev/concepts/scopes/).
Danvas does not ship or discover a SecretSpec manifest.

### 1Password

Map an environment variable to a 1Password reference, then let `op run` launch
danvas:

```bash
export CANVAS_API_KEY='op://Example/Canvas/credential'
op run -- danvas auth doctor \
  --profile example-university --check-canvas
```

The exported value is a reference rather than the Canvas token. The official
[1Password `op run` reference](https://www.1password.dev/cli/reference/commands/run)
also documents reference-only environment files through `--env-file`. Keep any
such file outside course repositories and remember that 1Password, not danvas,
owns its parsing and resolution.

## Diagnose Without Printing Tokens

Run the doctor offline first:

```bash
danvas auth doctor
danvas auth doctor --profile example-university
```

Without a configured URL, doctor reports an unconfigured origin and does not
read the selected credential. With a safely bound origin, it checks whether the
selected environment or file input is present and structurally readable. It
never prints a token or absolute credential-file path.

Add `--check-canvas` only when you want the bounded authenticated current-user
request:

```bash
danvas auth doctor --profile example-university --check-canvas
```

JSON output uses the explicit `danvas-auth-doctor-v1` schema with `origin`,
`credential`, `canvas`, and `issues` objects. A successful current-user request
does not prove that the token has permission for every course operation.

## Multiple Canvas Instances

Use one named profile per Canvas instance and a different locator for each:

```toml
default_profile = "example-university"

[profiles.example-university]
api_url = "https://canvas.example.edu/"
api_key_env = "CANVAS_EXAMPLE_API_KEY"

[profiles.other-university]
api_url = "https://canvas.other.example/"
api_key_file = "/run/secrets/canvas_other_api_key"
```

Pin each course project to the intended profile and URL. An origin mismatch
fails before danvas reads either input.

## Incident Response

If a token may have appeared in output, a tracked file, shell history, public
report, or retained process environment:

1. revoke or rotate it in Canvas immediately;
2. stop sharing the affected artifact;
3. determine what courses and permissions it exposed;
4. follow institutional incident-reporting policy; and
5. report a danvas vulnerability through the private route in
   [SECURITY.md](../SECURITY.md) when tool behavior contributed.

Rewriting Git history does not revoke a leaked token.
