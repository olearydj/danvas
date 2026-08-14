# Sprint 21.5: Provider-Neutral Credential Boundary

Status: design accepted on 2026-08-13 after independent review and the required
contract edits. Sprint 21 shipped as verified public-beta tag `v0.18.0`; Group 0
characterization is complete at `1145791` with no production change. Group 1's
neutral resolver and trust gate are complete at `c50d170` and accepted after
focused review. Group 2's provider-ownership removal at `8efbfa5` is accepted
after focused review. Group 3's public migration and downstream-interface work
at `75ca92a` is accepted after focused review. Group 4 release review and exact
candidate gates remain. This sprint authorizes no secret migration, external
secret-manager installation, Canvas access, release, or modification outside
this repository.

This design targets `0.19.0` for the credential-boundary release, absorbs the
already scheduled `0.19.0` roster legacy-schema removal, and moves the
remaining Sprint 22 agent-interface release to `0.20.0`.

## Outcome

Make danvas responsible for consuming one Canvas credential without making it
responsible for choosing, authenticating to, or diagnosing the system that
stores that credential.

The installed application will accept a Canvas API token through two narrow,
provider-neutral transports:

- one explicitly selected process environment variable; or
- one explicitly selected, single-purpose credential file.

The operator, organization, CI system, container runtime, or external secret
broker chooses how to populate that transport. SecretSpec, 1Password, Vault,
cloud secret managers, system keyrings, CI secret stores, and platform-mounted
credentials are integrations around danvas rather than dependencies inside it.

The release removes the required `secretpath` dependency, implicit `.env`
loading, 1Password-specific configuration, provider-specific CLI options, and
provider diagnostics from the core application. It does not claim that
environment or file delivery eliminates secret exposure. The token must still
enter danvas memory; the goal is smaller authority, explicit delivery, and
institution-neutral ownership.

This is an authentication-boundary release, not a Canvas feature release. It
does not change mutation authorization, private-artifact placement, evidence
schemas, authored sources, or Canvas payload behavior.

## Why This Sprint Is Separate

Sprint 21 establishes the first public beta from the already reviewed
`secretpath` contract. Expanding its implementation-complete packaging and
documentation group with a new authentication architecture would invalidate a
bounded review and delay the beta for work that is not a demonstrated release
vulnerability.

The accepted Sprint 18 program made
"replacing `secretpath` merely because it originated in the maintainer's
workflow" a [program non-goal](18-public-readiness.md#non-goals). This sprint
preserves that judgment: provider provenance is not a reason to replace a
working boundary. It explicitly supersedes that narrower non-goal because the
public product should consume a provider-neutral credential transport rather
than require one personal provider abstraction, provider-specific options, and
provider diagnostics. Removing that runtime authority also shrinks the public
supply-chain and diagnostic surface. Those are product-boundary reasons, not a
reaction to where the dependency originated.

Sprint 22 will publish richer help, guides, machine-readable command metadata,
and a portable Agent Skill. Those surfaces should not encode forty-five copies
of provider-specific options that are already scheduled for replacement.
Resolving the credential boundary after `0.18.0` but before Sprint 22 therefore
avoids both late Sprint 21 scope growth and immediate Sprint 22 documentation
churn.

The recommended release sequence is:

1. Sprint 21 ships the reviewed `0.18.0` public beta with the current
   authentication behavior documented honestly.
2. Sprint 21.5 ships the provider-neutral boundary and the already promised
   roster `legacy-v1` removal as `0.19.0`, with an exact migration guide.
3. Sprint 22 consumes the released `0.19.0` surface, drops the now-complete
   roster-removal work item, and targets `0.20.0` without otherwise changing
   its agent-interface scope.

Independent review accepted this sequencing. Sprint 22's document mechanics and
released-surface baseline are updated in Group 3 after the neutral `0.19.0`
surface exists; the accepted remaining interface scope is otherwise unchanged.

## Research And Security Position

The design follows four current primary-source observations:

- the [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
  recommends least privilege, lifecycle management, rotation, automation, and
  decoupling applications from secret stores where the deployment model permits;
- [SecretSpec](https://secretspec.dev/concepts/providers/) separates declaration
  of required secrets from provider selection, while its
  [`run` command](https://secretspec.dev/reference/cli/) normally delivers the
  selected values to the child process as environment variables;
- [SecretSpec scopes](https://secretspec.dev/concepts/scopes/) reduce which
  values are delivered but are explicitly not an authorization boundary; and
- [1Password](https://developer.1password.com/docs/cli/secrets-scripts) likewise
  documents external `op run` injection and recommends least-privilege service
  accounts for automated use.

Platform guidance distinguishes durable plaintext configuration from ephemeral
credential mounts. [Docker secrets](https://docs.docker.com/engine/swarm/secrets/)
are exposed to an authorized service as files and motivate the common
`*_FILE` application convention. Environment variables remain useful and
portable, but OWASP warns that they may be inherited by processes or appear in
diagnostics and dumps. A mounted file has different risks: path substitution,
permissions, unintended persistence, backup, and cleanup.

There are therefore three broad models, none of which removes the need for
danvas to hold the Canvas token in memory:

1. an external component injects the value into the process environment;
2. an external component exposes the value through a file, descriptor, mount,
   or equivalent local channel; or
3. danvas authenticates to and retrieves from a secret provider directly.

The third model avoids environment and credential-file exposure but moves
provider authentication, SDK/CLI behavior, caching, network trust, availability,
and provider authority into the danvas process. A compromised directly
integrated application may possess authority to retrieve more than one secret.
An external broker can instead give danvas exactly one Canvas token without
giving it the provider credential used to obtain that token.

For a short-lived CLI that needs one bearer credential and performs no lease
renewal, external least-capability delivery is the better default. Direct
provider integration remains valid for a future workload-identity or dynamic
credential requirement, but it is not justified by the current product.

## Verified `0.18.0` Baseline

The implementation candidate has the following credential behavior:

- `secretpath>=0.3.0` is a required runtime dependency;
- `python-dotenv>=1.0` is required and `main()` calls `load_dotenv()`
  unconditionally before Typer dispatch;
- `secretpath` provider choices are `auto`, `1password`, and `env`;
- `auto` is the default, with 1Password and environment behavior owned by the
  external library;
- the logical name defaults to `canvas`, the environment variable defaults to
  `CANVAS_API_KEY`, and an `op://` reference may be selected;
- forty-five Canvas-backed leaf signatures repeat `--secret-name`,
  `--secret-provider`, `--op-reference`, and `--api-key-env`;
- user profiles admit `secret_name`, `secret_provider`, `op_reference`, and
  `api_key_env`, while rejecting raw secret values;
- compatibility environment settings include `CANVAS_SECRET_PROVIDER`,
  `CANVAS_API_KEY_OP_REFERENCE`, and `CANVAS_API_KEY_ENV`;
- `resolve_api_key()` and `auth doctor` call `secretpath` directly;
- `auth doctor` reports `op`, `direnv`, SecretPath config files, provider
  resolution, and an optional Canvas identity check;
- ordinary Canvas construction prints the provider source;
- Panopto resolves the same Canvas token directly through `resolve_api_key()`;
  and
- a project URL outranks a profile URL, with a mismatch warning only when the
  profile was selected explicitly.

The current system does not store a raw token in a danvas profile or course
configuration, does not write a durable secret cache, and requires the API URL
to resolve before the token. Those safety properties remain.

The unconditional dotenv load is materially different from an intentional
credential mount. Python-dotenv searches upward from the calling module by
default, or from the working directory in its documented interactive, debugger,
frozen, or explicit-use modes. It parses a multi-key plaintext format and
changes the process environment before danvas knows which command or credential
it needs. Public documentation warns users not to commit `.env` files, but the
executable still consumes one implicitly. Sprint 21.5 removes that ambient
channel.

## Threat Model And Trust Boundaries

### Assets

The primary asset is a Canvas bearer token. Related protected state includes:

- any provider credential or authenticated provider session used to obtain it;
- the intended Canvas API origin to which it may be sent;
- the user profile and source locator that select it; and
- diagnostics that could reveal the value, provider-native reference, or
  unnecessary personal filesystem paths.

### Trust zones

This sprint treats the following as separate trust zones:

- the invoking user, their process environment, and their user-level danvas
  profile are trusted to select a credential input;
- a course repository and `.danvas/config.toml` may be shared or cloned and are
  not trusted to select a secret, credential file, environment-variable name,
  provider, or resolver command;
- an external broker or platform injector is trusted to expose only the value
  intended for danvas;
- danvas is trusted to use the selected token for the resolved Canvas origin but
  should receive no continuing authority over the external provider; and
- Canvas is trusted only at the explicitly bound HTTPS origin.

A course project may continue to name a user profile for instance selection.
It cannot name the profile's credential locator, and origin binding prevents a
project from combining that profile's credential with another API origin.

### Failures in scope

The implementation and tests address:

- an ambient `.env` file changing credential or endpoint inputs;
- stale environment variables silently winning after a more specific source
  was selected;
- a course project naming a credential locator;
- a profile credential being used against a conflicting Canvas origin;
- a missing source falling through to a different token;
- environment inheritance by a future subprocess;
- reading a directory, device, socket, unbounded file, empty value, or multiline
  dotenv-style payload as a token;
- path replacement between a file preflight and read;
- provider names, references, tokens, and raw provider errors entering output;
- old automation appearing successful after its provider-specific options stop
  working; and
- a non-Canvas command resolving credentials merely because credential-related
  configuration exists.

Memory disclosure by a compromised process, operating-system administrator,
debugger, or crash dump cannot be eliminated by an application-level transport.
The design does not claim memory zeroization that Python cannot guarantee.

## Design Principles

1. **Danvas declares need, not storage.** The application requires one Canvas
   token; the operator or organization chooses its durable authority.
2. **Delivery is explicit.** No `.env` discovery, provider auto-detection, or
   fallback from a selected missing source to another credential is allowed.
3. **The smallest capability crosses the boundary.** Danvas receives the token,
   not the credentials or session used to query a broader secret store.
4. **Course repositories cannot select secrets.** Credential source metadata is
   accepted only from CLI intent, a user-level profile, or the invoking process.
5. **Transport risks are stated honestly.** Environment and files are supported
   transports, not described as secure storage or perfect isolation.
6. **No raw token appears in argv or TOML.** CLI options select a variable name
   or file path; neither accepts the bearer value.
7. **One source means one source.** Conflicting selectors fail, and an explicitly
   selected but unresolved source never falls through.
8. **Origin and credential are one authorization decision.** A profile-bound
   token is not silently sent to a different project URL.
9. **Resolution is bounded and early.** Destination, configuration, origin, and
   selector validation finish before the selected value is read.
10. **Provider tools remain optional.** SecretSpec and 1Password are documented
    examples, not installed, imported, diagnosed, or required by danvas.

## Scope

Sprint 21.5 includes:

1. a typed provider-neutral Canvas credential-input model;
2. environment-variable and single-purpose credential-file transports;
3. deterministic source selection with no fallback after selection;
4. removal of implicit dotenv loading and the `python-dotenv` dependency;
5. removal of direct SecretPath integration and the required dependency;
6. removal of provider-specific CLI, profile, and compatibility settings;
7. a provider-neutral `auth doctor` report and JSON schema;
8. stronger Canvas-origin binding before credential access;
9. shared resolution for ordinary CanvasAPI and Panopto authentication;
10. architecture tests preventing secret-provider and subprocess drift;
11. external-runner and platform-file documentation without endorsing one
    organizational provider; and
12. the roster `--schema legacy-v1` removal already promised for `0.19.0`; and
13. an exact migration and release transition before Sprint 22 renders the
    final interface.

## 1. Credential Input Model

### Typed source descriptor

Add one small internal credential module whose conceptual records are:

```text
CredentialInput
  kind: environment | file
  locator: environment-variable name | absolute file path
  selection_source: cli | user_profile | process | default

ResolvedCredential
  value: secret string
  source_kind: environment | file
```

Exact Python names may change during implementation, but the ownership does
not: profiles select a non-secret descriptor; the credential module validates
and resolves it; `auth.py` constructs Canvas clients from the resolved value.
No module exposes a provider enum or provider-native reference.

The resolver returns only the value and sanitized transport class. It does not
claim to know whether an environment variable was populated by SecretSpec,
1Password, CI, a shell, or another system.

Any result type that contains the value must implement a redacting `__repr__`
that cannot expose it through dataclass defaults, exceptions, logs, or pytest
assertion introspection. Tests use random credential-shaped sentinels and pin
the assertion-failure representation of `ResolvedCredential`, not only normal
stdout and stderr.

### Selection precedence

Credential input selection is independent of API URL and profile selection:

1. exactly one explicit command selector:
   `--api-key-env NAME` or `--api-key-file PATH`;
2. exactly one selected user-profile key: `api_key_env` or `api_key_file`;
3. exactly one process selector: `CANVAS_API_KEY_ENV` or
   `CANVAS_API_KEY_FILE`; and
4. the default environment variable `CANVAS_API_KEY`.

Defining both selectors at one layer is an error. A higher-precedence selector
replaces lower-precedence selectors. Once a descriptor is selected, failure to
read it is final; danvas does not try another environment variable, file, or
provider.

`CANVAS_API_KEY_ENV` contains the name of an environment variable.
`CANVAS_API_KEY_FILE` contains an absolute path. `CANVAS_API_KEY` contains the
token only when no higher-precedence descriptor was selected.

The course-project `[canvas]` table may not define `api_key_env`,
`api_key_file`, `secret_name`, `secret_provider`, `op_reference`, a resolver
command, or any raw token spelling. A targeted diagnostic names the forbidden
key and directs the operator to their user profile or external injector.

### CLI surface

Every Canvas-backed leaf exposes only these credential selectors:

```text
--api-key-env NAME
--api-key-file PATH
```

The values are locators, never tokens. They are mutually exclusive at parsing
time before project resolution, credential access, output creation, or Canvas
network access. Non-Canvas commands expose neither option.

Do not add `--api-key`, `--token`, `--credential-command`,
`--secret-provider`, or a generic `--from` option.

### User-profile surface

A profile selects at most one transport:

```toml
[profiles.example-university]
api_url = "https://canvas.example.edu/"
api_key_env = "CANVAS_API_KEY"
```

or:

```toml
[profiles.example-university]
api_url = "https://canvas.example.edu/"
api_key_file = "/run/secrets/canvas_api_key"
```

The profile stores no value. `api_key_env` is validated as a portable
environment identifier. `api_key_file` must be absolute so its meaning cannot
change with the command working directory or project location.

## 2. Environment Transport

The environment resolver:

1. validates the selected variable name;
2. reads it exactly once;
3. rejects missing, empty, NUL-containing, or multiline values;
4. copies the value into the bounded credential result;
5. removes that selected variable from `os.environ` before constructing a
   Canvas client or reaching any code permitted to launch a child process; and
6. never prints, persists, hashes, or returns the value in diagnostics.

Removing the mapping prevents ordinary child-process inheritance. It does not
prove that every copy was erased from Python or operating-system memory, and no
documentation may claim otherwise.

The resolver does not enumerate the environment, look for likely token names,
load a shell profile, invoke `direnv`, or parse dotenv files. Only the selected
name is inspected.

`load_dotenv()` is removed from `main()`. The `python-dotenv` dependency is
removed if the implementation inventory confirms it has no remaining use.
Starting danvas inside a directory containing `.env` must not change any
command behavior.

## 3. Credential-File Transport

The credential-file input is a single-purpose value file, not a dotenv file or
general configuration file. Danvas never creates, edits, chmods, rotates,
deletes, or backs it up.

The resolver:

1. accepts only an absolute path selected outside course-project configuration;
2. opens the path once and validates the opened descriptor rather than
   preflighting and reopening it;
3. requires a regular file and rejects directories, devices, FIFOs, and sockets;
4. reads at most 16 KiB plus one sentinel byte and rejects larger content;
5. accepts one terminal LF or CRLF but rejects an empty value, NUL, or any other
   line break;
6. closes the descriptor immediately after the bounded read; and
7. retains no file path in reports or Canvas evidence.

The default implementation does not categorically reject a symlinked path.
Projected secret volumes commonly use symlink-based publication. Opening once
and validating the resulting descriptor avoids a preflight/read race, while
the rule that a course repository cannot select the path prevents the ordinary
repository-symlink attack. Tests must cover both a valid projected symlink and
path replacement around the open.

A credential file contained inside the active course-project root is rejected.
This prevents `.env`, `.danvas/`, or another tracked/local course file from
becoming the supported secret store merely by renaming it. Local workstation
files belong in a user-controlled configuration directory; platform credentials
belong in their runtime mount.

POSIX mode checks are diagnostic, not universal validity rules. A user-owned
local file that is group/world readable produces an actionable warning, but a
root-owned read-only file inside an isolated container is not rejected solely
for mode `0444`. Documentation must not equate a mode bit with the complete
platform security boundary.

## 4. External Provider Integration

Danvas does not depend on, import, shell out to, or probe SecretSpec,
1Password, Vault, a keyring, or a cloud provider.

The authentication guide should show equivalent, clearly labeled patterns:

```console
secretspec run --scope danvas -- danvas auth doctor --check-canvas
```

```console
op run --env-file=PATH -- danvas auth doctor --check-canvas
```

```console
CANVAS_API_KEY_FILE=/run/secrets/canvas_api_key \
  danvas auth doctor --check-canvas
```

The exact SecretSpec and 1Password examples must be reverified against their
primary documentation during implementation. The guide describes them as
optional examples with different trust and exposure properties, not as danvas
support commitments or equivalent provider security guarantees.

Danvas does not ship a `secretspec.toml`, write a provider configuration, ask a
user to select an organization-wide provider, or add SecretSpec's Python SDK.
An individual or organization may own a separate declarative manifest and
scope containing `CANVAS_API_KEY`.

## 5. Canvas Origin Binding

Externalizing provider resolution does not prevent a confused-deputy failure:
a valid token can still be delivered to danvas and then sent to the wrong API
origin. Credential resolution therefore remains behind a stricter origin gate.

Before reading an environment variable or credential file:

1. normalize the effective HTTPS Canvas origin;
2. if a selected user profile declares `api_url`, require it to match the
   effective origin regardless of how the profile was selected;
3. turn the current profile/project mismatch warning into an error before
   credential access;
4. when no selected user profile binds the effective origin, require an exact
   invocation-level `--api-url` or matching nonempty `CANVAS_API_URL`; and
5. refuse a project-only origin that has no user-controlled binding.

This preserves project URL resolution for offline inspection, status, help,
and migration diagnostics. It changes the authorization gate for any command
that would read a token. Existing projects without a selected matching profile
must add one, set a matching user-controlled `CANVAS_API_URL`, or pass
`--api-url` explicitly.

There is no `--allow-origin-mismatch` flag. Operators with legitimate aliases
create a profile for the actual API origin rather than disabling the binding.

The normalized comparison includes scheme, host, and effective port and ignores
only an equivalent trailing slash. It does not infer institutional ownership
from a hostname substring or restrict Canvas to `instructure.com`.

## 6. Provider-Neutral Auth Doctor

`danvas auth doctor` remains useful offline and without a configured URL. Its
new report distinguishes:

- profile selection;
- API URL configuration and origin-binding status;
- credential transport selection;
- whether the selected input is present and structurally readable;
- optional POSIX permission warnings for a local credential file; and
- the existing optional bounded Canvas reachability/current-user check.

It no longer reports:

- `op` or `direnv` availability;
- SecretPath configuration files;
- secret names, provider order, provider-native references, or provider errors;
- whether SecretSpec, 1Password, Vault, or another broker is installed; or
- a provider name inferred from the transport.

The JSON form becomes an explicit `danvas-auth-doctor-v1` schema with
`origin`, `credential`, `canvas`, and `issues` objects. The credential object
may name a configured environment-variable identifier because it is actionable
non-secret metadata. It reports only a redacted file classification rather than
an absolute credential-file path. Neither form emits the value.

Ordinary Canvas commands retain one routine transport notice: `Using Canvas
credential from: environment` or `credential file`. They must not attribute the
value to a provider that danvas did not contact. Sprint 22 may review whether
structured consumers make the line unnecessary; Sprint 21.5 does not remove it.

## 7. Provider-Specific Removal

Remove from the `0.19.0` executable surface:

- `--secret-name`;
- `--secret-provider`;
- `--op-reference`;
- the `auto|1password|env` provider enum; and
- all corresponding argument plumbing.

Remove from accepted user-profile keys:

- `secret_name`;
- `secret_provider`; and
- `op_reference`.

Remove these compatibility environment controls:

- `CANVAS_SECRET_PROVIDER`; and
- `CANVAS_API_KEY_OP_REFERENCE`.

Retain `CANVAS_API_KEY_ENV` as a provider-neutral variable-name selector and
retain `CANVAS_API_KEY` as the default value transport. Add
`CANVAS_API_KEY_FILE` as the file selector.

Presence of a removed provider environment control causes an actionable failure
before credential access rather than being ignored. Removed CLI options fail as
unknown options during parsing. Removed profile keys fail with a targeted
migration message. Old automation must never appear successful after silently
choosing a different credential source.

Remove:

- the `secretpath` runtime dependency and lock entries;
- all imports and exception types from that package;
- SecretPath-specific tests and doctor rendering;
- direct `resolve_named_secret()` calls; and
- any requirement that release smoke import or install SecretPath.

The public distribution continues to include no secret-provider SDK or CLI.

## 8. Process And Dependency Boundary

Danvas presently has no production subprocess requirement. Preserve that
property after credential resolution with an architecture test that fails on
new uses of `subprocess`, `os.system`, shell execution, or process-spawn APIs
unless an independently reviewed call site is allowlisted.

This is not a claim that subprocesses are categorically forbidden forever. It
ensures that a future helper cannot begin inheriting `CANVAS_API_KEY` unnoticed.
Any accepted future subprocess must receive a constructed minimal environment
that omits credential values and selector metadata.

Add a second architecture check that production modules import no known secret
provider package and contain no provider-native `op://` reference. Documentation
examples are allowlisted separately so external integration guidance remains
possible without becoming runtime coupling.

The dependency audit and secret scan remain Sprint 21 release gates. Sprint
21.5 additionally verifies wheel and sdist metadata to prove neither
`secretpath` nor `python-dotenv` remains required.

## Compatibility And Migration

This is a deliberate pre-1.0 authentication-interface break. Canvas command
names, mutation flags, output locations, and payload behavior remain stable,
but existing SecretPath and implicit-dotenv workflows require operator action.

The expected first authenticated command after upgrade will fail for many
existing initialized projects. In particular, the common pre-Sprint-18 setup
has a project `[canvas].api_url`, no selected user profile, and a default
`CANVAS_API_KEY`; the project URL alone is no longer allowed to choose the
origin that receives that token. The one-line durable fix, after defining a
matching user profile, is `profile = "example-university"` beneath the
project's existing `[canvas]` table. The one-line shell-session alternative is
`export CANVAS_API_URL=https://canvas.example.edu/` with the exact matching
origin. Passing the same origin through `--api-url` is the per-invocation
alternative. Each fix establishes user-controlled origin intent; none weakens
the binding or changes the stored project URL.

The migration guide must include:

- provider-specific profile keys to `api_key_env` or `api_key_file`;
- direct 1Password lookup to external `op run` injection;
- SecretPath environment mode to the retained `api_key_env` contract;
- an optional SecretSpec `run --scope danvas` example;
- local/container credential-file examples;
- removal of implicit `.env` loading;
- the new origin-binding failure and exact fixes for an unbound project;
- the auth-doctor JSON replacement;
- replacement of routine provider attribution with transport-only attribution;
- the already scheduled removal of roster `--schema legacy-v1` in favor of the
  existing `LoginID` schema;
- multiple-instance profiles with distinct environment names or external
  provider profiles; and
- rollback to the exact `v0.18.0` tag without rewriting project files.

Configuration is not rewritten automatically. A stale profile fails with a
targeted message that names every removed key and shows a neutral replacement.
This makes rollback possible and prevents code from guessing whether an
`op_reference` should become an environment variable or a file.

The guide must distinguish:

- a globally exported environment variable, which may persist and reach
  unrelated children;
- a per-command external runner, whose environment exposure is bounded to the
  launched process tree;
- a durable plaintext `.env` file, which danvas no longer discovers; and
- a single-purpose ephemeral credential file or platform mount.

It must not describe SecretSpec as mandatory, claim that file delivery is
universally safer, ask users to put a raw token in argv/TOML, or suggest a shell
command that prints the token.

Before the `v0.18.0` tag, Sprint 21 public authentication and compatibility
documentation should receive a small non-behavioral notice that the
provider-specific surface is under accepted post-beta review and may change in
`0.19.0`. That notice is authorized only after this design's release sequence
is accepted; the Sprint 21 runtime and dependency set remain unchanged.

## Implementation Sequence

### Group 0: characterization and accepted sequencing

1. [x] Resolve the release/deprecation and Sprint 22 retargeting questions.
2. [x] Freeze the exact forty-five-command authentication option surface.
3. [x] Characterize SecretPath resolution, provider output, auth-doctor text/JSON,
   Panopto authentication, and missing-URL-before-secret ordering.
4. [x] Add an executable counterexample proving a local `.env` currently changes
   both `CANVAS_API_KEY` and `CANVAS_API_URL` process inputs at startup.
5. [x] Characterize project/profile origin mismatch and project-only authenticated
   operation.
6. [x] Inventory all process-spawn and provider-package call sites with exact
   architecture baselines.

No runtime behavior changes in Group 0.

Implementation record: `1145791` adds an executable transition gate covering
all 45 Canvas-backed leaves and their six current authentication options,
SecretPath wrapper arguments and provider attribution, exact auth-doctor text
and JSON shapes, missing-URL ordering, debugger-mode dotenv population of both
the credential and endpoint, the warning-only profile mismatch, and successful
project-only authentication. The existing Panopto profile-secret regression
remains the exact direct-authentication check. Architecture tests now pin the
two provider-package imports, four direct provider/dotenv calls, two bounded
`resolve_api_key()` entry points, and zero production process-spawn calls. The
full released-tree gate passes 843 tests at 85.05% branch-aware coverage, the
authored-assets module floor at 88.87%, Ruff, ty, frozen-lock validation, and
the dependency audit.

### Group 1: neutral resolver and trust gate

1. [x] Add typed credential descriptors and independent precedence fixtures.
2. [x] Implement bounded environment and credential-file readers.
3. [x] Remove the selected environment value before Canvas construction.
4. [x] Add origin binding and conflict-before-credential ordering.
5. [x] Route CanvasAPI and Panopto through the same neutral resolver.
6. [x] Replace routine provider attribution with truthful transport
   attribution or no routine line.

Group 1 does not yet remove legacy options or dependencies; characterization
keeps the old path available until the new path is independently exercised.

Implementation record: `c50d170` adds a provider-neutral credential module with
typed environment/file descriptors, independent layer-precedence fixtures, and
a redacting resolved-value representation. The environment reader consumes and
removes exactly the selected variable before downstream construction. The file
reader performs one bounded descriptor open, requires a regular file, supports
projected-volume symlinks, rejects active-project containment and path
replacement, preserves the source artifact, and emits only a path/value-free
POSIX permissions warning. User profiles may select the neutral file transport;
course projects may select neither transport nor legacy provider metadata.

The effective HTTPS Canvas origin is now bound before credential access to a
matching selected profile, invocation-level `--api-url`, or matching
`CANVAS_API_URL`; all profile-selection paths enforce conflicts, while custom
domains and trailing-slash/default-port equivalence remain supported. Ordinary
CanvasAPI and Panopto authentication share one reviewed resolver entry point,
and runtime attribution names only an observed environment or credential-file
transport. Group 0's warning-only mismatch and project-only-authentication tests
were deliberately inverted. The transitional 45-command legacy option surface,
SecretPath wrapper, auth-doctor schema, dotenv behavior, and dependencies remain
available for explicit Group 2 removal.

The full Group 1 gate passes 908 tests at 85.20% branch-aware coverage, the new
credential module at 94%, and the authored-assets module floor at 88.87%, plus
Ruff, ty, frozen-lock validation, and the dependency audit. No Canvas, Panopto,
external provider, or out-of-repository operation was performed.

Focused review accepted Group 1 on 2026-08-13 with no findings. The reviewer
confirmed the single-open file boundary, origin binding, strict selector
precedence, environment removal, redacting representations, and shared
Canvas/Panopto path.

### Group 2: remove provider ownership

1. [x] Replace the forty-five repeated auth bundles with the two neutral selectors.
2. [x] Remove provider-specific profile keys and compatibility environment controls.
3. [x] Remove implicit dotenv loading.
4. [x] Remove SecretPath and python-dotenv runtime dependencies and lock entries.
5. [x] Replace auth doctor with the versioned neutral report.
6. [x] Add actionable failures for every retired spelling.
7. [x] Remove roster `--schema legacy-v1` on its already announced `0.19.0`
   schedule and retain only `LoginID`.
8. [x] Flip Group 0 characterization tests deliberately rather than deleting them.

Implementation record: `8efbfa5` replaces all 45 Canvas-backed command bundles
with `--api-key-env` and `--api-key-file`, removes provider-specific runtime and
profile plumbing, rejects retired profile keys and process controls with
migration guidance, and removes implicit dotenv loading. The shared boundary
now returns the redacting neutral result directly. Auth doctor emits the clean
`danvas-auth-doctor-v1` origin/credential/Canvas schema, diagnoses bounded file
and environment failures without provider attribution, redacts file locators,
and never reads a credential when the origin is unconfigured, conflicting, or
unbound. Roster output is `LoginID`-only.

SecretPath and python-dotenv are absent from project metadata, the frozen lock,
the synchronized environment, and isolated editable/wheel installs. The
distribution checker enforces the removal in both wheel and sdist metadata.
Architecture tests pin zero provider imports, zero provider calls, zero process
spawns, and the two reviewed neutral-reader entry points. Every retired CLI
spelling is exercised across all 45 former surfaces as an unknown option. The
full Group 2 gate passes 917 tests at 85.19% branch-aware coverage, the
authored-assets module floor at 88.87%, Ruff, ty, frozen-lock validation, the
dependency audit, and isolated editable/sdist/wheel smoke. No Canvas, Panopto,
external provider, or out-of-repository operation was performed.

Focused review accepted Group 2 on 2026-08-13 with no findings. The reviewer
independently enumerated all 45 Canvas-backed option surfaces, the complete
dependency and provider excision, every retired-spelling failure, the neutral
doctor schema, environment-removal ordering, and the `LoginID`-only roster
surface. A separate full-suite run passed all 917 tests.

### Group 3: public migration and downstream interface

1. [x] Publish `docs/migrations/0.19.0.md` with the required workflow matrix.
2. [x] Rewrite authentication, configuration, privacy, compatibility, README, and
   contribution examples around provider-neutral delivery.
3. [x] Add optional, primary-source-verified SecretSpec and 1Password recipes.
4. [x] Update Sprint 22's accepted baseline to the released neutral option and
   `LoginID`-only roster surface, remove its completed roster-removal work item,
   and retarget it to `0.20.0` without otherwise changing its agent-interface
   scope.
5. [x] Keep the external personal teaching skill behind a separately
   authorized post-tag change; it is not part of this repository sprint and
   must precede replacement of the maintainer's global CLI.

Implementation record: `75ca92a` publishes the complete `0.19.0` migration
matrix, leads with the expected existing-project origin-binding failure and its
three exact fixes, and documents environment, credential-file, SecretSpec,
1Password, multiple-instance, doctor-schema, roster, rollback, and exposure
transitions. Current authentication, configuration, privacy, compatibility,
README, changelog, and contributor guidance now describe only the neutral
credential boundary. Executable documentation guards prevent current guides
from reviving retired provider controls or the removed roster schema.

The candidate version and lock metadata advance to `0.19.0`; the public
documentation checker now covers 13 files. Sprint 22 is refreshed against the
neutral `0.19.0` candidate, removes completed compatibility work, and remains
otherwise unchanged as the accepted `0.20.0` design. The full Group 3 gate
passes 920 tests at 85.19% branch-aware coverage, the authored-assets module
floor at 88.87%, Ruff, ty, frozen-lock validation, Markdown and link checks,
dependency audit, current-tree secret scan, and isolated editable/sdist/wheel
smoke. Primary provider examples were checked against their official command
references. No Canvas, Panopto, external provider, personal-skill, global-tool,
or out-of-repository operation was performed.

Focused review accepted Group 3 on 2026-08-13 with no findings. The reviewer
independently verified every required migration workflow and external-provider
recipe against primary sources, exercised the documentation regression tests,
confirmed the candidate metadata and package gates, and accepted Sprint 22's
coherent `0.20.0` retarget against the neutral released-surface contract.

### Group 4: review and release

1. Run independent security-boundary review of selection, origin binding, file
   reads, diagnostics, and migration behavior.
2. Run the complete supported Python/Linux/macOS gate and exact package smoke.
3. Optionally run a separately authorized, bounded read-only Canvas doctor check
   for both transports; no mutation is required.
4. Push and tag only after exact-commit branch CI is green.
5. After tag CI and anonymous exact-tag installation pass, separately authorize
   and complete the maintainer's `op run`-based injection and external teaching
   skill migration before replacing the maintainer's global CLI.
6. Verify the global tagged installation and release documentation before
   declaring `0.19.0` complete.

## Automated Acceptance

### Selection and ordering

- Every Canvas-backed command exposes exactly `--api-key-env` and
  `--api-key-file`; every non-Canvas command exposes neither.
- Defining both selectors at CLI, profile, or process-selector precedence fails
  before project output, credential access, or network access.
- CLI beats profile, profile beats process selection, and process selection
  beats the `CANVAS_API_KEY` default in independent winner fixtures.
- A selected missing or invalid source fails without trying another source.
- Course configuration cannot select any credential locator or provider.
- Missing or conflicting API-origin binding fails before the selected
  environment variable or file is read.
- Non-Canvas commands succeed without loading user profiles or inspecting
  credential inputs.

### Environment transport

- Only the selected variable is inspected.
- Missing, empty, NUL, and multiline values fail without echoing content.
- A valid one-line value reaches Canvas construction exactly once.
- The selected variable is absent from `os.environ` before any downstream call.
- A child-inheritance fixture cannot observe the selected token.
- Random credential-shaped values never appear in stdout, stderr, exceptions,
  reports, snapshots, or test failure representations; the fixture explicitly
  exercises pytest assertion `repr` of a `ResolvedCredential` result.
- A repository-local `.env` has no effect on any command.

### File transport

- Relative paths, project-contained paths, missing paths, directories, devices,
  FIFOs, sockets, empty values, NUL, multiline values, and values over 16 KiB
  fail before Canvas access.
- One trailing LF or CRLF is removed; no other whitespace is silently changed.
- The resolver reads from one opened descriptor and is safe against path
  replacement after open.
- A valid projected-volume-style symlink resolves to one regular file and is
  read successfully.
- A local broad-permission file produces the reviewed diagnostic without
  printing its contents.
- No credential path appears in retained reports or Canvas evidence.
- Danvas never creates, modifies, chmods, renames, or deletes the source file.

### Origin binding

- Every profile-selection path, not only explicit `--profile`, enforces an exact
  normalized profile/effective-origin match before credential access.
- A project-only API URL cannot receive a token without a matching user profile,
  explicit URL, or matching user-controlled `CANVAS_API_URL`.
- Trailing-slash equivalence passes; scheme, host, and effective-port changes
  fail.
- Custom Canvas domains work without an Instructure hostname assumption.
- No override option disables the check.

### Auth doctor

- Offline doctor works with no API URL or credential configured.
- Text and `danvas-auth-doctor-v1` JSON distinguish unconfigured, conflict,
  missing, unreadable, structurally invalid, origin-unbound, and resolved input.
- `--check-canvas` is the only path that performs the bounded Canvas request.
- Neither form invokes or diagnoses a provider executable.
- Neither form emits a token, provider-native reference, raw provider error, or
  absolute credential-file path.
- The current SecretPath-shaped JSON fails an explicit compatibility fixture so
  the schema break cannot be mistaken for an additive change.

### Removal and architecture

- `--secret-name`, `--secret-provider`, and `--op-reference` are unknown options
  on every former command surface and fail before context.
- Stale profile keys and legacy provider environment controls produce targeted
  nonzero migration errors.
- Production code has no SecretPath, SecretSpec, 1Password, dotenv, keyring,
  Vault, or cloud secret-provider import.
- Production code has no unreviewed process-spawn call site.
- `pyproject.toml`, the frozen lock, sdist metadata, and wheel metadata contain
  neither `secretpath` nor `python-dotenv` as runtime requirements.
- The complete CLI starts, renders help, and runs local-only commands in an
  environment where no provider tool or provider Python package is installed.

### Documentation and quality gates

- Public docs teach environment and file delivery as transports with explicit
  risks, not secure stores.
- Every external provider example is optional, primary-source verified, and
  uses no raw secret literal.
- No current guide or example retains `secret_provider`, `op_reference`,
  `--secret-name`, `--secret-provider`, `--op-reference`, or implicit dotenv
  instructions except the migration guide's clearly labeled before-state.
- Roster `--schema legacy-v1` is absent, the default `LoginID` schema remains,
  and its removal appears in the `0.19.0` migration guide.
- Sprint 22's baseline and examples use only the released neutral and
  `LoginID`-only surface.
- Ruff, ty, frozen lock validation, dependency audit, secret scan, branch
  coverage, all tests, documentation links, Markdown lint, and editable/sdist/
  wheel smoke pass on every supported release lane.

## Risks And Mitigations

### Environment injection is mistaken for secure storage

State explicitly that it is process delivery. Prefer per-command scoped
injection over global export, remove the selected variable before downstream
code, prevent subprocess drift, and document crash-dump/administrator limits.

### Credential files become a renamed `.env` convention

Accept exactly one value, require an absolute external path, reject the active
course root, never parse key/value syntax, and lead platform examples with
ephemeral mounts rather than durable local plaintext.

### Direct provider integration was more convenient

Provide copyable external-runner recipes and actionable doctor diagnostics.
Do not regain convenience through an arbitrary resolver-command hook, automatic
provider probing, or a required SecretSpec dependency.

### Origin binding breaks legitimate aliases

Fail before reading the credential and explain how to create a user profile for
the actual API origin. Do not weaken the check with hostname guessing or a broad
bypass flag. Review alias fixtures from supported custom-domain deployments.

### Removing SecretPath strands existing users

Ship a complete before/after migration guide, preserve `api_key_env`, make stale
configuration fail loudly, announce the planned boundary in the `0.18.0` docs
after design acceptance, and preserve exact-tag rollback.

### External tools change

Keep all provider examples outside runtime behavior, reverify primary docs at
release time, and test only danvas's input contract. A broken SecretSpec or
1Password installation remains that tool's diagnostic responsibility.

### Python cannot prove zeroization

Minimize lifetime and propagation but make no zeroization promise. Security
claims cover source selection, output, persistence, and child inheritance, not
forensic erasure from interpreter memory.

## Non-Goals

- Adding SecretSpec, 1Password, Vault, keyring, cloud-secret, or password-manager
  SDK support to danvas;
- implementing a generic secret-provider plugin interface;
- accepting a resolver command, shell snippet, callback module, or executable
  path from project or user configuration;
- writing, rotating, revoking, synchronizing, importing, exporting, or listing
  secrets;
- creating or parsing `.env` files;
- accepting a raw token through argv, a TOML value, stdin, or a general JSON
  document;
- claiming protection from a compromised danvas process, host administrator,
  debugger, or memory dump;
- implementing Canvas OAuth, dynamic credentials, leases, workload identity,
  or automatic token rotation;
- changing Canvas URL discovery for commands that never resolve credentials;
- changing mutation, evidence, artifact, source-layout, gradebook, or Panopto
  content behavior beyond the already scheduled roster compatibility removal;
- implementing Sprint 22 help, guide, describe, or skill features;
- editing the external personal teaching skill without separate authorization;
  or
- performing a live Canvas mutation.

## Resolved Design Decisions

- Danvas owns credential consumption but not durable provider selection.
- Environment and single-purpose file inputs are the only first-party
  transports in this release.
- Environment delivery is supported for portability but is not called secure
  storage.
- Credential-file delivery is preferred when a platform can provide an
  ephemeral, access-controlled mount.
- Direct provider retrieval is not justified for the current short-lived CLI.
- SecretSpec is a recommended example for declarative provider portability, not
  a dependency or privileged default.
- SecretSpec's Python SDK is not used because it would move provider resolution
  back inside the application.
- SecretPath and implicit dotenv loading leave the runtime dependency set.
- The `0.18.0` notice, loud migration failures, and exact-tag rollback are
  sufficient pre-1.0 notice; no compatibility adapter retains SecretPath.
- Raw tokens remain forbidden in CLI arguments and danvas configuration.
- Course projects cannot select credential inputs.
- Explicit source selection never falls back to another token.
- Selected environment values are removed before downstream code, without a
  false memory-zeroization claim.
- Projected credential-file symlinks are supported through single-open
  descriptor validation; project-contained credential files are rejected.
- Profile/effective-origin mismatch becomes a pre-credential error with no
  bypass flag.
- The routine source notice remains, but reports only the transport danvas
  observed rather than an inferred provider.
- Provider diagnostics leave `auth doctor`; it diagnoses only danvas input and
  Canvas reachability.
- `danvas-auth-doctor-v1` is an intentional clean schema break; no deprecated
  provider-shaped compatibility view remains.
- No arbitrary resolver-command escape hatch enters configuration.
- SecretSpec and 1Password are the two optional workstation examples; platform
  mounts and generic CI injection cover organizational delivery without an
  endorsed provider.
- The roster `legacy-v1` option is removed on its existing `0.19.0` schedule so
  resequencing does not weaken an accepted compatibility promise.
- Sprint 21.5 targets `0.19.0`; Sprint 22 retains its accepted interface scope,
  consumes the neutral released surface, and moves to `0.20.0`.

## Resolved Review Questions

1. The release sequence is accepted: Sprint 21.5 owns `0.19.0`, including the
   due roster removal, and Sprint 22 moves to `0.20.0`.
2. The `0.18.0` notice, migration guide, loud failures, and exact-tag rollback
   are adequate for this pre-1.0 break. No compatibility adapter ships.
3. Project-only origins are rejected before credential access. A warning is
   insufficient for the credential-redirection threat, and no bypass is added.
4. Trusted-path symlinks remain supported for projected secret volumes through
   single-open descriptor validation and project-root containment.
5. Ordinary commands retain the one provider-neutral transport notice.
6. `danvas-auth-doctor-v1` is a clean schema break with an explicit
   compatibility fixture rather than a deprecated dual view.
7. SecretSpec and 1Password remain optional workstation examples; platform
   mounts and generic CI examples cover organizational deployment.

## Definition Of Done

- Danvas can authenticate through one selected environment variable or one
  selected external credential file without a secret-provider package.
- Provider choice and provider credentials remain outside the danvas process.
- Implicit `.env` discovery is gone.
- Selected source and Canvas origin are validated before the token is read.
- The selected token is never logged, persisted, placed in argv/TOML, or
  inherited by a danvas-launched child.
- Course-project configuration cannot select or redirect a credential source.
- Auth doctor truthfully diagnoses the danvas boundary without claiming to
  diagnose the external provider.
- Every provider-specific public option, profile key, environment control,
  dependency, import, and routine output is removed or fails with an exact
  migration path.
- Public documentation lets individuals and organizations choose SecretSpec,
  1Password, another broker, CI injection, or a platform credential mount.
- Roster compatibility reaches its previously announced `LoginID`-only
  `0.19.0` state.
- Existing Canvas operation, mutation, privacy, and evidence tests remain green.
- Sprint 22 begins from the released provider-neutral surface.

## Release Contract

The accepted target is `0.19.0` after `v0.18.0` has shipped. The release
candidate requires independent
security-boundary review, the complete supported Python/Linux/macOS matrix,
dependency and secret audits, exact package metadata inspection, anonymous
candidate installation, and the normal branch/tag gates.

No external provider installation or account is required for release. Fixtures
fully exercise environment and file delivery. A real Canvas doctor check is
read-only, optional, bounded, and separately authorized; it must not print or
retain the credential.

No push, tag, GitHub Release, package-registry publication, global CLI
replacement, external provider configuration, user secret migration, personal
skill edit, or Canvas access is implied by this design.
