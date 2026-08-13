# Sprint 17: Typed Transaction State And Quality Ratchets

Status: released as `v0.14.0` following the 0.13.1 dependency-maintenance patch
and an independent correction review.

## Outcome

Make the safety properties behind assignment asset deployment easier to preserve
and harder to accidentally bypass before the transaction is adapted to another
authored-content family.

For an operator, this sprint should be deliberately uneventful. Existing
assignment, Page, announcement, discussion, file, snapshot, and report commands
retain their inputs, outputs, exit statuses, mutation order, and retry guidance.
The improvement is that future changes are checked against explicit transaction
states, an acyclic module boundary, branch coverage, supported Python versions,
complexity limits, and a frozen dependency audit.

## Why This Sprint Comes Next

Sprint 16 shipped a useful but stateful transaction across local files, Canvas
Files, source-map provenance, authored HTML, assignment mutation, readback, and
durable reports. Three review rounds found defects at the seams between those
states even though the growing test suite remained green. The corrected release
is safe, but the implementation still encodes its state in mutable
`dict[str, Any]` values and several long orchestration functions.

A repository-wide quality review after 0.13.0 established this baseline:

- 565 tests pass in about four seconds;
- statement coverage is 86 percent and branch-aware coverage is 83 percent;
- Ruff, ty, lock validation, local documentation links, editable smoke, and
  wheel smoke pass;
- `authored_assets` has 77 percent branch-aware coverage;
- Ruff identifies 23 functions above its default complexity threshold of 10;
- `prepare_asset_plan` has complexity 23 and 75 statements;
- `execute_asset_plan` has 77 statements;
- one strongly connected import component contains `assignments`,
  `authored_assets`, `config`, `snapshot_collections`, `pages`, and `sources`;
- `cli.py` is large, but most of its parameter-count findings are a normal
  consequence of explicit Typer command signatures rather than transaction
  complexity; and
- a current dependency audit found vulnerable frozen `idna` and `soupsieve`
  versions. That lock correction and a permanent audit job belong to 0.13.1,
  before this sprint begins.

The next Page asset adapter would touch most of the existing import component
and reuse the asset transaction. Adding it first would make both structural
problems more expensive to correct.

## Scope

Sprint 17 includes:

1. characterization tests for every existing asset transaction conclusion;
2. typed internal asset-plan, asset-result, runtime, and evidence records;
3. smaller pure planning and transition helpers behind the existing public
   assignment integration;
4. dependency-light project-configuration and Page-source modules;
5. removal of the six-module import cycle, including the local imports that
   currently hide parts of it;
6. branch-coverage and complexity ratchets;
7. explicit minimum/current Python CI lanes; and
8. preservation tests for public JSON, Markdown, stdout, source-map, and exit
   status contracts.

Sprint 17 does not include:

- Page, announcement, or discussion asset deployment;
- a new Canvas command or CLI option;
- a new evidence-schema version;
- a new source-map schema version;
- changes to local-reference classification or supported asset types;
- changes to overwrite, rename, folder-creation, deletion, or publishing
  policy;
- a broad split of every Typer command into separate CLI modules;
- a blanket replacement of every broad exception handler;
- a general Page/status complexity rewrite;
- a target of 100 percent coverage; or
- Canvas mutation or another bounded live acceptance case.

## Durable Compatibility Contract

This is an internal structural release. Given the same source tree, source map,
Canvas fixtures, CLI arguments, and simulated API outcomes, pre- and
post-refactor behavior must agree on:

- whether Canvas is contacted;
- the order and count of Canvas mutations;
- every upload and assignment payload;
- source-map file and assignment entries;
- stable file IDs, folder IDs, hashes, and occurrence counts;
- public JSON and Markdown report fields;
- mutation, content, evidence, and verification statuses;
- recovery guidance;
- sanitized diagnostics and stdout; and
- process exit status.

Formatting that is already explicitly unordered may be canonicalized, but no
field may be added, removed, or reclassified merely because the internal state
becomes typed.

The public asset evidence schema remains `authored-assets-v1`. Existing report
readers and source-map readers require no migration.

## 0.13.1 Prerequisite (Satisfied)

Sprint 17 begins from the bounded 0.13.1 patch that:

- upgrades frozen `idna` from 3.13 to at least 3.15;
- upgrades frozen `soupsieve` from 2.8.3 to at least 2.8.4;
- adds `pip-audit` to the development dependency group;
- runs `uv run pip-audit --skip-editable` in the frozen CI environment;
- keeps all application code and command behavior unchanged; and
- passes the normal frozen tests, Ruff, ty, lock check, and editable/wheel
  release smoke.

The dependency patch was versioned and released separately so the security
update did not wait for a structural refactor.

## Typed Asset Transaction

### Separate serializable state from live runtime handles

The current plan dictionary contains both durable values and private live
objects under underscore-prefixed keys. Replace that convention with two
explicit layers:

- `AssetPlan`: typed, serializable transaction intent and accumulated result;
- `AssetRuntime`: non-serializable handles and local paths used only during the
  current process.

`AssetRuntime` may hold the Canvas client, course, folder, resolved source path,
project root, and original source HTML. It must never be accepted by a public
evidence serializer or source-map writer.

`AssetPlan` should contain typed records for:

- course and source identity;
- source and deployed body hashes;
- destination evidence;
- ordered assets and blocked references;
- mutation, content, evidence, and verification conclusions;
- bounded recovery guidance; and
- sanitized verification detail.

Use dataclasses for records with behavior and `StrEnum` or closed `Literal`
types for externally serialized status values. `TypedDict` is acceptable for
the final public JSON projection, but not as the only internal state model.

### Minimum internal records

The implementation should define cohesive equivalents of:

- `AssetOccurrence`;
- `LocalAssetIdentity`;
- `CanvasFileIdentity`;
- `AssetDestination`;
- `AssetItem`;
- `AssetPlan`;
- `AssetRuntime`;
- `AssetVerification`; and
- `AssetPublicEvidence`.

Names may change during implementation, but these concerns must not collapse
back into one unconstrained dictionary.

### Preserve an explicit projection boundary

`public_asset_evidence` remains the only complete public projection of the
transaction. It must build a new allowlisted object and must not serialize a
dataclass recursively with `asdict`, because recursive serialization could
expose future private fields or runtime handles.

The projection continues to omit:

- absolute source paths;
- live Canvas objects;
- raw upload responses;
- authored bodies;
- signed or verifier-bearing URLs;
- credential values; and
- exception messages that have not passed the shared sanitizer.

### State vocabulary

Existing serialized values remain unchanged. The typed model should distinguish
at least these dimensions rather than merging them into one status:

- plan: `blocked`, `planned`, `would_reuse`, `deployed`, `failed`,
  `indeterminate`, `created`, `updated`, `readback_mismatch`, and
  `readback_indeterminate` where currently emitted;
- asset action/result: `blocked`, `conflict`, `would_reuse`, `would_upload`,
  `would_rename`, `reused`, `uploaded`, `renamed`, `failed`, and existing
  indeterminate upload classifications;
- mutation: `not_started`, `not_needed`, `in_progress`, `succeeded`, `failed`,
  `partial`, and `indeterminate` where currently emitted;
- content mutation: the current not-started/in-progress/succeeded/failed/
  indeterminate vocabulary; and
- evidence and verification: their current complete, failed, not-checked,
  matches, mismatch, and indeterminate values.

Do not infer one dimension from another in report code. A successful Canvas
mutation with incomplete evidence remains distinct from a failed mutation.

## Transaction Decomposition

Keep the existing module entry points used by assignments while decomposing
their internals.

### Planning phases

`prepare_asset_plan` should orchestrate small helpers for:

1. detecting local intent without Canvas access;
2. resolving and classifying references;
3. validating source/project containment;
4. loading and validating source-map course identity;
5. resolving the optional existing Canvas Files destination;
6. resolving each mapped file identity;
7. planning uploads through the one shared file duplicate classifier; and
8. finalizing blocked, planned, or all-reuse conclusions.

The pure phases accept serializable inputs and return typed values. Canvas
lookups remain isolated in explicitly named boundary helpers.

### Execution phases

`execute_asset_plan` should orchestrate helpers for:

1. revalidating the source and complete local intent;
2. revalidating one local asset immediately before its mutation;
3. rechecking the point-in-time destination plan;
4. uploading exactly one asset with Canvas overwrite disabled;
5. classifying the upload response;
6. recording immediate file provenance;
7. stopping safely after mutation or evidence uncertainty;
8. rewriting the Canvas-bound HTML only after every asset has a stable ID; and
9. finalizing deployed hashes and conclusions.

The per-asset executor returns a typed transition result. It must not mutate the
next asset or the assignment.

### Complexity target

After decomposition:

- `prepare_asset_plan` must be at or below complexity 15;
- no new function may exceed complexity 15;
- `execute_asset_plan` should remain at or below complexity 15 and should no
  longer exceed 50 statements; and
- transaction helper names should describe the phase or boundary rather than
  generic `process` or `handle` actions.

## Characterization And Transition Tests

Write behavior-pinning tests before moving implementation.

### Transaction matrix

Generate a matrix across the meaningful dimensions:

- mapped reuse, new upload, explicit rename, and planning conflict;
- source unchanged or changed after planning;
- destination unchanged or changed after planning;
- upload succeeded, rejected, or indeterminate;
- stable Canvas file identity present or missing;
- source-map write succeeded or failed;
- assignment mutation succeeded, rejected, or indeterminate;
- readback matched, mismatched, unavailable, or indeterminate; and
- report write succeeded or failed where that boundary is recoverable.

Not every Cartesian-product cell is reachable. Encode allowed combinations and
assert that invalid transitions cannot be constructed silently.

For every reachable cell, assert:

- each Canvas mutation attempt appears exactly once;
- intent and returned identity remain paired;
- mutation and evidence statuses are independent and truthful;
- unsafe retries are discouraged after any possible mutation;
- no rollback deletion is attempted;
- the next upload or content mutation does not run after a stopping condition;
- public evidence contains no private/runtime fields; and
- source Markdown bytes and modification time remain unchanged.

### Golden compatibility fixtures

Retain focused golden or structural fixtures for:

- no-local-asset assignment create/update/upsert/verify;
- blocked local references before project or Canvas initialization;
- all-reuse plans without a destination;
- upload and explicit rename plans;
- partial upload failure with immediate first-file provenance;
- content failure followed by reuse on retry;
- signed/verifier readback rejection;
- current-course root-relative content links;
- same-basename planning;
- assignment source-map fields; and
- JSON, Markdown, manifest, and stdout sanitization.

Prefer semantic object assertions over whole-file snapshots when timestamps,
run directories, or argument vectors are intentionally variable.

## Acyclic Module Boundaries

### `project_config.py`

Create a dependency-light project configuration module containing:

- `.danvas` and config-file constants;
- project/config path resolution;
- `find_config_dir`;
- TOML loading and table validation;
- direct canvas course ID, API URL, and timezone lookups that do not depend on
  snapshot collectors or feature modules; and
- any shared config-only helpers required by reports, files, assets, and source
  discovery.

`config.py` remains the command and snapshot orchestration module. It may import
and re-export established helper names temporarily so in-repository callers do
not all need to change atomically.

Move the duplicate `reports.find_config_dir` implementation onto this module.
`project_config.py` must not import `pages`, `sources`, assignments, snapshot
collectors, reports, or Canvas mutation modules.

Assignment-group name resolution may remain in `config.py` because it consumes
snapshot authority metadata. The low-level project module must not gain that
dependency merely to absorb every helper with “config” in its name.

### `page_sources.py`

Create a Page source/normalization module that owns the Page functions needed by
both snapshot collection and local source discovery:

- `BODY_NORMALIZER_VERSION`;
- the Page source record type;
- source loading and front-matter normalization;
- canonical Page URL and HTML normalization;
- stable Page record projection used by snapshots; and
- related pure validation helpers needed by those operations.

`pages.py` remains responsible for Page commands, CSS application, sync
planning/execution, report writing, and Canvas mutation. It imports the shared
Page-source primitives rather than defining a second copy.

`snapshot_collections.py` and `sources.py` import `page_sources`, not `pages`.
This prevents read-only source/snapshot infrastructure from depending on the
Page command module.

### Shared assignment date expansion

Move date-only expansion used by both assignment loading and generic source
discovery into `authored_content.py` or another dependency-light authored-source
module. `sources.py` must not import `assignments`, even lazily, to parse an
assignment source.

### Required final import direction

The intended high-level direction is:

```text
project_config   authored_content   page_sources   canvas_links
       \              |                 /               /
        \             |                /               /
         config   sources   snapshot_collections   authored_assets
              \      |             /                 /
               pages/status       assignments/files
                         \          /
                              cli
```

The diagram is directional guidance, not permission for every shown module to
import every module below it. Low-level modules must remain unaware of command
registration and mutation orchestration.

### Architecture assertion

Add a small static test that parses in-package imports, including imports inside
functions, and fails when a strongly connected component contains more than one
`danvas` module. Also assert the specific forbidden edges:

- `sources -> assignments`;
- `sources -> pages`;
- `snapshot_collections -> pages`;
- `project_config ->` any command/feature module; and
- `authored_assets -> config`.

The test should use the standard library and must not import the modules it is
analyzing.

## Quality Ratchets

### Branch coverage

Add `pytest-cov` to the development dependency group and configure branch
coverage. CI should run the suite with a global branch-aware floor of 82
percent, leaving a small platform margin below the measured 83 percent baseline.

The sprint should raise `authored_assets` branch-aware coverage from 77 percent
to at least 82 percent through transaction-state and boundary tests. Do not add
coverage exclusions for real error, privacy, evidence, or recovery paths.

### Complexity

Enable Ruff `C901` with a maximum complexity of 15. Refactor
`prepare_asset_plan` below that threshold.

The current functions still above 15 outside the sprint's behavioral scope are:

- `authored_content.comparable_value`;
- `page_sources.check_css`, moved intact from `pages`;
- `pages.build_pages_sync_plan`; and
- `status.compare_pages`.

Mark only those exact legacy functions with documented `noqa: C901` annotations
and backlog references. Do not ignore C901 for an entire file. No new exception
may be added without a named follow-on.

Do not enable Ruff's parameter-count rule globally. Explicit Typer parameters
are part of the user-facing command contract, and internal context objects should
be introduced based on cohesion rather than to satisfy a mechanical count.

### Supported Python versions

Run the normal frozen checks on Python 3.12, the declared minimum, and Python
3.14, the current stable line for this release cycle. Keep one install-smoke job
after the matrix succeeds rather than duplicating the artifact smoke in every
lane.

Both lanes must use the same frozen lock and must pass Ruff, ty, tests, and the
dependency audit. If a development tool is not compatible with one supported
runtime, resolve or explicitly narrow that tool boundary rather than silently
dropping the runtime lane.

### Dependency audit

The audit job is delivered in 0.13.1 and remains a required Sprint 17 gate. It
audits the frozen environment with the editable danvas distribution skipped; the
project's own code remains covered by Ruff, ty, tests, evidence invariants, and
review.

## Broad Exception Boundaries

The baseline contains 50 broad exception handlers. Many intentionally convert
Canvas SDK, network, filesystem, or report failures into bounded evidence.
Sprint 17 does not replace them mechanically.

For every broad handler touched by the refactor:

- retain the original mutation uncertainty;
- sanitize before persistence or display;
- preserve the original exception as the cause when exiting;
- avoid retry advice that assumes a mutation did not happen; and
- add a focused test for the classification.

Unexpected programming errors outside an external boundary must not be newly
converted into a normal transaction status.

## Implementation Order

1. Record pre-refactor transaction and output characterizations.
2. Add `project_config.py`, migrate low-level config consumers, and remove the
   duplicate report config finder.
3. Add `page_sources.py` and move only shared Page source/normalization code.
4. Move assignment date-only expansion to the authored-content foundation.
5. Add the static acyclic-import assertion and prove the current component is
   gone.
6. Introduce typed asset records plus explicit public projections without
   changing orchestration.
7. Split asset planning and execution into bounded phases.
8. Add the independent transition contract and reachable execution matrix, then
   raise asset branch coverage.
9. Enable branch coverage, C901, and supported-Python CI ratchets.
10. Re-run the complete compatibility suite and isolated release smoke.
11. Update repository documentation and revalidate the external teaching-danvas
    skill; no skill text should change unless operator behavior changed.
12. Complete an independent verification review before push or tag.

## Automated Acceptance

Local implementation verification currently establishes:

- all 602 tests pass under frozen Python 3.12 and 3.14 environments;
- Ruff, ty, lock validation, and the dependency audit pass;
- the package import graph is acyclic and every forbidden edge is absent;
- an implementation-independent transition contract pins plan, asset, mutation,
  content-mutation, evidence, and verification state transitions;
- real execution cases cover upload success, rejection and uncertainty,
  destination drift, provenance failure, partial stable evidence, successful
  reuse, and stale reuse;
- `prepare_asset_plan` and `execute_asset_plan` pass the complexity-15 gate;
  their orchestration bodies contain 20 and 12 statements respectively;
- global branch-aware coverage is 83.75 percent and `authored_assets` coverage
  is 88.84 percent;
- the four named legacy functions are the only `C901` suppressions;
- lock validation, isolated editable/wheel smoke for 0.14.0, local Markdown-link
  validation, and sprint-document lint pass; and
- the external teaching-danvas skill and command reference were revalidated
  without edits because no operator-facing behavior changed.

Independent review completed before push and tag.

The independent review found that a self-derived matrix could not expose
a missing `would_reuse -> failed` edge. The corrected implementation restores
the pre-refactor stale-reuse failure evidence, replaces the self-referential
matrix, and expands the architecture parser to cover relative imports and async
function suppressions. The correction passed the same release gates before
commit.

- The full pre-refactor suite remains green without rewriting expectations to
  accept behavior drift.
- The independent transition contract and real execution matrix cover every
  reachable asset-plan conclusion named in this design.
- No `danvas` import cycle remains when function-local imports are included.
- No forbidden architecture edge remains.
- `public_asset_evidence` and source-map projections are allowlisted and contain
  no runtime handles or absolute source paths.
- Existing asset JSON and Markdown schemas remain `authored-assets-v1`.
- No-local-asset assignment workflows retain their payloads, reports, offline
  behavior, and verification conclusions.
- Canvas mutation ordering remains banner, file uploads with immediate
  provenance, content mutation, readback, and final evidence.
- Asset source Markdown remains byte-for-byte unchanged.
- Ruff passes with C901 at 15 and only the four documented legacy function
  exceptions.
- Ty passes with the new typed transaction model.
- Branch-aware coverage is at least 82 percent globally and at least 82 percent
  for `authored_assets`.
- Frozen tests and dependency audit pass on Python 3.12 and 3.14.
- Lock validation and editable/wheel smoke pass for 0.14.0.
- Local Markdown links and sprint-document lint pass.

## Live Acceptance

No Canvas mutation is required. Sprint 17 deliberately preserves behavior that
already passed bounded live assignment acceptance in Sprint 16.

If implementation reveals a necessary Canvas-observable change, stop and amend
this design before performing a live probe. Do not treat a structural sprint as
implicit authorization for another Canvas mutation.

## Release Contract

Target version: 0.14.0.

The release commit should contain the version bump and final documentation state
and should be tagged `v0.14.0` only after pushed main CI passes. Tag CI must pass
before the exact tagged global installation is updated.

`PROJECT_CONTEXT.md` is updated during handoff, not used as an implementation
scratchpad. The external teaching-danvas skill and command reference are
revalidated; because Sprint 17 changes no operator contract, no wording change
is expected.
