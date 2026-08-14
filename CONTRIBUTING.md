# Contributing

Contributions are welcome for bounded defects, documentation, tests, and
features that preserve danvas's privacy and mutation contracts.

This project is an unofficial public beta. Do not use a pull request or public
issue to share tokens, student information, private course artifacts, protected
URLs, or raw Canvas responses. Follow [SECURITY.md](SECURITY.md) for suspected
vulnerabilities.

## Development Setup

Clone over HTTPS and synchronize the frozen environment:

```bash
git clone https://github.com/olearydj/danvas.git
cd danvas
uv sync --frozen
uv run danvas --help
```

The project supports Python 3.12 through 3.14. Ruff targets Python 3.12 syntax.
Use the project-managed environment rather than manually assembling
`PYTHONPATH`.

## Local Gate

Run the same core checks as CI:

```bash
uv lock --check
uv run ruff check .
uv run ty check
uv run pip-audit --skip-editable
uv run pytest --cov=danvas --cov-branch --cov-report=term-missing \
  --cov-report=json:/tmp/danvas-coverage.json --cov-fail-under=82
uv run python scripts/check-module-coverage.py \
  /tmp/danvas-coverage.json src/danvas/authored_assets.py 82
uv run python scripts/check-docs.py
```

For package and startup changes, also run:

```bash
scripts/release-smoke.sh
```

The documentation checker validates repository-relative files and anchors
without network access. External links receive a bounded release-time review
rather than making ordinary CI depend on third-party availability.

## Tests Must Be Offline By Default

The normal test suite must not call a real Canvas or Panopto deployment. Use
fixtures and fakes for HTTP/client behavior. A live probe requires separate,
explicit authorization with:

- one changed remote semantic that fixtures cannot establish;
- a disposable target;
- a bounded private evidence path;
- an exact cleanup plan; and
- no student-identifying data.

Never make a contributor's ambient token, profile, course repository, or agent
configuration a test prerequisite.

## Safe Fixtures

Reusable fixtures and examples use:

- `https://canvas.example.edu/` for a Canvas host;
- small internally consistent IDs such as `101`, `202`, and `303`;
- project-relative paths or neutral temporary paths; and
- synthetic names and content that cannot be mistaken for student data.

Do not add real institution hosts, course IDs, user IDs, maintainer home paths,
signed URLs, verifier tokens, or copied API payloads merely for realism.
Historical acceptance notes may retain bounded institutional context when it is
necessary to explain field evidence.

## Architecture Gates

The CLI leaf inventory has two owned foundations:

- `danvas.access.ACCESS_POLICIES` classifies Canvas reads, Canvas mutation,
  local writes, dry-run axis, consequence, and verification; and
- `danvas.artifacts.ARTIFACT_POLICIES` classifies retained-output sensitivity.

Exact-tree tests require new commands to be classified. Do not introduce a
parallel effects or privacy registry.

Canvas write call sites and common pre-write assertion sites are inventoried by
AST-based architecture tests. Adding or renaming a write primitive must force a
reviewed baseline update. Every Canvas mutation still needs the fail-closed
assertion immediately before the write.

Private artifacts must use the creation-time helpers in `danvas.artifacts`.
Writing a permissive file and tightening it afterward violates the contract.
No-clobber, symlink, containment, sidecar, and manifest-last behavior need
failure-path tests.

Keep modules acyclic. If a dependency change introduces a cycle, fix the
ownership boundary rather than weakening the import-cycle gate.

Credential delivery is deliberately provider-neutral. Production code may read
only the selected environment variable or bounded credential file through the
shared resolver. Do not add a password-manager SDK, provider executable,
dotenv loader, raw-token option, or unreviewed process-spawn path. Tests use
synthetic values and temporary files; they must never depend on an ambient
credential or external provider login.

## Documentation

Public user instructions belong in README, the public guide set, command help,
or a migration guide. Sprint notes and the backlog are design/history records,
not the public authority chain.

Use repository-relative links. State beta status, unsupported boundaries, and
privacy or mutation consequences plainly. Do not promise support established
only by one institution's deployment.

## Pull Requests

Keep changes scoped and commit them in logical groups. A pull request should
state:

- the user-visible outcome;
- privacy, mutation, compatibility, and migration effects;
- tests and exact local gates run;
- any unverified deployment assumption; and
- whether documentation or evidence schemas changed.

Do not update release tags, global installations, repository security settings,
or external publication state as an incidental implementation step.
