# Sprint 13: Installed CLI And Release Health

Status: shipped in v0.10.2 on 2026-08-11. Main CI, exact-tag CI, and both
isolated install lanes passed; replacing and checking the user's global
installation remains an explicitly authorized acceptance step. The originally
targeted 0.10.1 version was consumed by the public development commit but was
never tagged.

## Objective

Turn the manually successful `v0.10.0` close-out into a reproducible release
check that proves danvas can be built and started from an isolated tool
environment, not merely imported from the repository virtual environment.

The sprint must distinguish two useful guarantees:

1. the locked development environment still passes lint, typecheck, and tests
2. a fresh resolver can install the authored package metadata into an isolated
   tool environment and start the resulting CLI

This is release engineering, not a new Canvas workflow. It must not contact
Canvas, replace the user's global tool installation during routine checks, or
weaken machine-wide uv freshness policy.

## Why This Is Next

This implements field-observed backlog item 11, now the first open priority
after the consolidated `v0.10.0` release.

The original failure occurred outside the repository: an editable global
launcher held an incompatible `secretpath` dependency and failed before command
parsing even though the project environment worked. The manual `v0.10.0`
release proved a viable recovery path by building artifacts, installing the
wheel in an isolated tool directory, publishing an exact Git tag, and then
installing and checking that tag globally. None of that installed-package path
is encoded in CI today.

The same close-out exposed two current maintenance warnings:

- local uv 0.12.1 is newer than the declared
  `uv_build>=0.11.0,<0.12.0` build-backend range
- GitHub Actions reports that `actions/checkout@v4` and
  `astral-sh/setup-uv@v5` target deprecated Node.js 20 while the runner forces
  Node.js 24

As of 2026-08-11, the official current releases are
[`actions/checkout` v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1),
[`astral-sh/setup-uv` v9.0.0](https://github.com/astral-sh/setup-uv/releases/tag/v9.0.0),
and [uv 0.12.3](https://github.com/astral-sh/uv/releases/tag/0.12.3).
Both action releases declare the Node.js 24 action runtime.

## Current-State Audit

- `.github/workflows/ci.yml` runs frozen sync, Ruff, ty, and pytest only.
- CI runs on pushes to `main` and pull requests, but not tag pushes.
- CI does not build a wheel/sdist or install danvas outside `.venv`.
- `README.md` documents editable installation but does not distinguish
  development checkout, isolated artifact smoke testing, and tagged release
  installation.
- `danvas auth doctor` is already a suitable non-Canvas startup diagnostic when
  supplied a dummy environment-backed token and run without `--check-canvas`.
- `secretpath` and CanvasAPI are required runtime dependencies imported by the
  CLI. Making `auth doctor` start when required dependencies cannot import would
  require a broad lazy-import/bootstrap redesign and is not justified by the
  current evidence.

## Design Decisions

### No New Danvas Module Or Command

Do not add `danvas release`, `danvas install`, or a Python package module. The
failure surface is the external build/resolve/install process, so testing it
from inside the already-imported CLI would be circular.

Add one small repository-native POSIX shell entry point,
`scripts/release-smoke.sh`. Shell is appropriate here because the script only
orchestrates uv, the built executable, temporary directories, and exit codes.
Keep policy and product behavior out of the script.

The script accepts an optional `--expected-version X.Y.Z`. Without it, the
expected version comes from `pyproject.toml`; tag CI passes the version derived
from `GITHUB_REF_NAME`. Supplying a mismatching expected version must fail before
any build or install begins.

### Isolated Smoke Contract

The script must:

1. resolve the repository root from its own location and require a cleanly
   readable `pyproject.toml`
2. create a unique temporary root with `mktemp -d` and remove only that exact
   resolved directory on exit
3. build both sdist and wheel into the temporary root
4. install the local checkout in editable mode into one isolated uv tool
   directory
5. install the built wheel into a second isolated uv tool directory, forcing a
   fresh package-metadata resolution rather than using the project lock
6. run `danvas --version`, `danvas --help`, and non-network
   `danvas auth doctor --secret-provider env` from both installations
7. provide the doctor check a clearly fake task-specific environment token and
   a task-specific `XDG_CONFIG_HOME` beneath the temporary root, and never pass
   `--check-canvas`; apply the XDG override only to the doctor process so uv
   still honors the operator's normal command/config policy during installation
8. verify that both executables report the version declared in
   `pyproject.toml`
9. leave the user's global `UV_TOOL_DIR`, executable links, and existing danvas
   installation untouched

Use task-specific `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` values beneath the
temporary root. Do not repurpose `HOME`, use the default global tool directory,
or delete a path that was not created by the script. Do not disable uv config or
freshness rules inside the smoke script; a local policy conflict should fail
truthfully and lead to the documented command-scoped recovery path.

### CI Contract

Update the existing workflow rather than introducing a publishing workflow:

- move to the current Node.js 24 action generations, initially pinned to the
  investigated `actions/checkout@v7.0.1` and
  `astral-sh/setup-uv@v9.0.0` releases
- pin the tested uv release instead of silently taking an arbitrary future uv
  in release checks
- continue frozen sync, Ruff, ty, and the full pytest suite
- add an install-smoke job that runs `scripts/release-smoke.sh` outside the
  project environment assumptions
- trigger validation on pull requests, `main`, and `v*` tag pushes
- on a tag run, require `refs/tags/vX.Y.Z` to match the version in
  `pyproject.toml` before the smoke check can pass

The workflow validates release contents but does not publish to PyPI, create a
GitHub Release, push tags, or modify any global installation.

### Build Metadata

Align the `uv_build` requirement with the tested uv 0.12 generation, using a
bounded compatible range rather than deleting the upper bound. Regenerate the
lock only if project dependency metadata changes require it. The implementation
must prove that the warning is gone during both local and CI builds.

### Installation And Recovery Guidance

Revise the README to describe three distinct modes:

- editable development install from a trusted checkout
- isolated artifact smoke test through `scripts/release-smoke.sh`
- tagged release install from an exact Git tag

Document a diagnostic sequence of `uv tool list`, `danvas --version`,
`danvas --help`, and `danvas auth doctor`. Document command-scoped uv recovery
options for `exclude-newer` conflicts without asking users to disable or loosen
their global policy. A forced reinstall must preserve an exact source or tag and
must be followed by the startup checks.

Do not claim that `auth doctor` can repair an environment whose imports fail; in
that case the documented remedy is an isolated reinstall followed by the
diagnostic.

## Implementation Order

1. Add the isolated release-smoke script and exercise both editable and wheel
   installs locally.
2. Add tag/package version matching and negative tests for mismatched expected
   versions.
3. Align the bounded `uv_build` range and confirm artifact builds are warning-
   free with the pinned uv version.
4. Upgrade and pin the GitHub Actions/uv toolchain, add tag triggers, and add the
   install-smoke job.
5. Update README installation, diagnostic, and scoped recovery guidance.
6. Run frozen sync, Ruff, ty, pytest, the release-smoke script, and a clean CI
   run before release close-out.

## Implementation Result

The implemented slice follows the design without adding a danvas module or
command:

- `scripts/release-smoke.sh` validates an optional expected version before any
  build, creates guarded temporary directories, builds wheel and sdist, installs
  separate editable and wheel tool environments, and runs non-network version,
  help, and environment-backed auth-doctor checks
- focused tests cover executable/shell validity, running outside the checkout,
  missing arguments, pre-build version rejection, and cleanup after a forced
  build failure
- package and lock metadata are synchronized at 0.11.0, with the build backend
  aligned to `uv_build>=0.12.0,<0.13.0`
- CI uses `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v9.0.0`, and pinned uv
  0.12.3; it now runs on version tags and adds a dependent isolated-install job
- README guidance now separates editable development, isolated smoke, exact-tag
  installation, startup diagnostics, and command-scoped freshness recovery

Local verification on 2026-08-11 passed frozen sync, Ruff, ty, all 400 tests,
warning-free wheel/sdist builds, both isolated tool installations, both startup
diagnostic sequences, and success/failure temporary cleanup checks. The full
script also passed when invoked from `/private/tmp`, outside the checkout. The
real global danvas receipt and executable were not modified.

## Automated Acceptance

- The existing full suite passes in the frozen project environment.
- The smoke script succeeds from a path outside the repository working
  directory.
- Editable and wheel installations use different temporary tool directories
  and both report the expected version.
- The wheel lane resolves runtime dependencies without using the project lock
  or importing the checkout.
- `--help` and environment-backed `auth doctor` pass with no Canvas request.
- A package/tag version mismatch exits nonzero before any release publication.
- A failing build, install, version, help, or doctor command propagates a
  nonzero script result.
- Temporary directories are cleaned on success and ordinary failure.
- The script never changes the real global uv receipt or executable link.
- CI runs both project checks and isolated install checks on pull requests,
  `main`, and version tags.
- CI no longer emits the observed Node.js 20 or uv-build range warnings.

## Operational Acceptance

For an exact tagged release:

1. Run `scripts/release-smoke.sh` from a clean checkout and retain the concise
   terminal result.
2. Confirm the exact main commit passes both CI jobs.
3. Create the tag only after those checks pass.
4. Confirm the tag-triggered workflow validates tag/package version equality
   and the isolated install path.
5. With explicit authorization, replace the global danvas installation from
   the exact tag and verify version, help, and local auth doctor outside the
   repository.

No live Canvas call or course mutation is required for this sprint.

Steps 1 through 4 passed for `v0.10.2` on 2026-08-11. Its pending global-install
check was superseded by the explicitly authorized exact-tag `v0.11.0`
installation and startup validation on 2026-08-12. A `--force`-only invocation
exited successfully but retained the existing 0.10.0 tool; the verified
replacement required `--upgrade --reinstall`, and the README now records that
exact-tag upgrade form plus the mandatory installed-version check.

## Exclusions

- PyPI publication or a new package registry
- automatic tag creation, pushing, or GitHub Release creation
- changes to Canvas commands or authentication semantics
- lazy-import or dependency-free CLI bootstrap redesign
- dependency-vulnerability scanning or broad multi-platform matrices
- replacing the user's global tool during normal local or CI smoke tests
- general-purpose environment repair outside the documented danvas install path

## Definition Of Done

- A release cannot pass CI solely because `.venv` works; the built wheel must
  install and start in an isolated uv tool environment.
- Tag/version drift is rejected automatically.
- The supported editable, artifact-smoke, and exact-tag workflows are documented
  with scoped recovery guidance.
- The build backend and GitHub Actions runtime warnings observed during 0.10.0
  close-out are resolved.
- The user-facing command surface and Canvas behavior remain unchanged.
- Ruff, ty, the full pytest suite, local release smoke, main CI, tag CI, and the
  explicitly authorized tagged global-install check all pass.
