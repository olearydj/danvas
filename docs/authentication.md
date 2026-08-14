# Authentication

Canvas-backed commands require both an explicit Canvas instance and an API
token accepted by that instance. Danvas has no institutional host or token
built in.

Create and revoke tokens through your Canvas account according to local policy.
Canvas administrators may restrict token creation, API endpoints, enrollment
visibility, or write permissions; danvas cannot bypass those controls.

## Keep Tokens Out Of Configuration

User profiles and `.danvas/config.toml` store only non-secret references. Raw
`api_key`, `token`, `access_token`, and `credential` keys are rejected in user
configuration.

Danvas resolves named credentials through `secretpath`. Supported provider
choices are:

- `auto`: let `secretpath` resolve the configured references;
- `1password`: resolve the configured 1Password reference; and
- `env`: read the configured environment variable.

A minimal environment-backed profile is:

```toml
[profiles.example-university]
api_url = "https://canvas.example.edu/"
secret_provider = "env"
api_key_env = "CANVAS_EXAMPLE_API_KEY"
```

```bash
export CANVAS_EXAMPLE_API_KEY="your-canvas-token"
danvas auth doctor --profile example-university --check-canvas
```

Do not commit shell files, `.env` files, password-manager output, or copied
diagnostic transcripts containing credentials.

## Credential Reference Precedence

Credential references resolve independently from the Canvas URL:

1. explicit command options;
2. the selected profile;
3. compatibility environment settings; and
4. safe defaults.

The defaults are secret name `canvas`, provider `auto`, and environment
variable `CANVAS_API_KEY`. Compatibility variables include:

- `CANVAS_SECRET_PROVIDER`
- `CANVAS_API_KEY_OP_REFERENCE`
- `CANVAS_API_KEY_ENV`
- `CANVAS_API_KEY`

Common command overrides are:

```text
--secret-name
--secret-provider auto|1password|env
--op-reference
--api-key-env
```

The Canvas URL must resolve before danvas attempts secret resolution. See
[Configuration](configuration.md) for instance and profile precedence.

## Diagnose Without Printing Tokens

Run the doctor without a network check first:

```bash
danvas auth doctor
danvas auth doctor --profile example-university
```

The offline doctor remains useful when no API URL is configured. It reports the
URL as unconfigured, checks provider availability and reference resolution, and
does not print the secret value.

Add `--check-canvas` only when you want a bounded authenticated request:

```bash
danvas auth doctor --profile example-university --check-canvas
```

The command reports whether Canvas was reachable and identifies the current
user with bounded fields. Errors are sanitized. A successful secret-resolution
check does not prove that the token has permission for every course operation.

## Multiple Canvas Instances

Use one named profile per Canvas instance and give each a distinct secret name
or environment variable. Pin a course project to its intended profile and URL.

```toml
default_profile = "example-university"

[profiles.example-university]
api_url = "https://canvas.example.edu/"
secret_name = "canvas-example"
secret_provider = "env"
api_key_env = "CANVAS_EXAMPLE_API_KEY"

[profiles.other-university]
api_url = "https://canvas.other.example/"
secret_name = "canvas-other"
secret_provider = "env"
api_key_env = "CANVAS_OTHER_API_KEY"
```

If an explicitly selected profile disagrees with a project's pinned URL,
danvas warns and keeps the project URL. Stop and verify the credential rather
than assuming the token is interchangeable.

## Incident Response

If a token may have appeared in output, a tracked file, a shell history, or a
public report:

1. revoke or rotate it in Canvas immediately;
2. stop sharing the affected artifact;
3. determine what courses and permissions it exposed;
4. follow institutional incident-reporting policy; and
5. report a danvas vulnerability through the private route in
   [SECURITY.md](../SECURITY.md) when tool behavior contributed.

Rewriting Git history does not revoke a leaked token.
