# Sprint 9: Correctness And Resilience Remediation

Status: implemented and locally verified for 0.7.1 alongside Sprint 8. This
sprint remediates the behavioral correctness and targeted
resilience defects confirmed by the post-0.7.0 codebase audit at commit
`5988c93`.

## Objective

Restore the intended Page diff/status/update contracts, make source discovery
isolate malformed files, and correct assignment-audit edge cases. Add regression
tests for the failure paths that define these commands' value without turning
the patch release into a general refactor.

No new Canvas mutation family is introduced. Existing commands should become
more accurate and fail more locally.

## Page Snapshot Diff

`danvas refresh --diff` must identify Page additions, removals, and comparable
field changes. The generic snapshot diff currently assumes every row has `id`,
while Page rows use `page_id`.

- Define section identity explicitly rather than relying on one implicit key for
  every snapshot section.
- Use stable Page identity, preferring `page_id`; do not key Page diffs by title.
- Preserve existing identity behavior for non-Page sections.
- Compare Page `body_sha256` only when both snapshots declare the running Page
  body normalizer and the versions match.
- When normalizers are missing or differ, continue comparing safe Page metadata
  but report body comparison as unavailable/refresh-required rather than as a
  body change or no change.
- Do not expose full Page bodies or volatile URL values in terminal or persisted
  refresh-diff output.

The terminal, JSON, and Markdown forms must derive from the same diff payload.

## Page Status Identity

Title-only Page matching remains provisional collision evidence, never
provenance.

- A probable title match requires exactly one unbound local source with that
  normalized title and exactly one eligible Canvas Page with that title.
- Exclude Canvas Pages already claimed by a stable front-matter or source-map
  identity before evaluating title candidates.
- Duplicate local titles or duplicate eligible Canvas titles produce an
  unsupported/ambiguous classification with no binding recommendation.
- One Canvas Page cannot be matched independently to multiple local sources.
- Stable identity matching remains authoritative and survives title changes.
- Keep `compare_pages` consistent with the stricter identity rules already used
  by `build_pages_sync_plan`.

## Page Update And Verification Fields

Make the bounded Page mutation contract explicit for `front_page`,
`editing_roles`, and `publish_at`.

- `pages create` readback verification compares every supported field actually
  sent in the creation payload: body, title, publication state, front-page state,
  editing roles, and publish scheduling when declared.
- `pages verify` compares the same locally authoritative fields and reports each
  mismatch by name.
- `pages update` must not silently omit a locally declared supported field.
- Preserve the existing rule that title/slug changes and unsupported lifecycle
  operations are blocked rather than smuggled into an update.
- If Canvas does not support a requested field transition through the bounded
  update API, reject it explicitly with a useful message instead of producing a
  successful partial update.
- Write source-map provenance only after readback satisfies the complete
  supported-field contract.

Before implementation, settle whether changing `front_page` belongs in the
bounded update surface or remains an explicitly blocked lifecycle operation.
Whichever rule is chosen must agree across planning, payload construction,
verification, tests, README, and the existing Sprint 6/7 deferred boundaries.

## Source Discovery Error Isolation

Malformed YAML or TOML front matter in one discovered local source must not crash
the entire course scan.

- Convert parser-specific YAML and TOML errors into concise per-file source
  diagnostics.
- Preserve the filename and source kind without echoing an unsafe or excessively
  large source line.
- Continue scanning independent sources and status sections.
- Direct single-source write commands may still exit nonzero for malformed input;
  the isolation requirement applies to inventory/status discovery.
- Avoid duplicating parsing logic between discovery and mutation commands.

Sprint 8 owns removal of private content from override parser diagnostics. This
sprint owns ordinary front-matter parser resilience.

## Assignment Audit Corrections

### Snapshot file shape

When `load_assignment_snapshot()` receives a JSON object as a file, honor both
its top-level `assignments` and top-level `assignment_groups`. Derive groups from
embedded assignment metadata only for legacy/list inputs that do not provide a
top-level group collection.

Directory input and direct `course.json` file input must produce equivalent
assignment/group audit data for the same snapshot.

### Zero-weight groups

Preserve an explicit `group_weight: 0` or `weight: 0`. Use key/presence checks
rather than truthiness fallbacks so legitimate practice/ungraded groups are not
reported as missing.

## Targeted Test Hardening

Add regression coverage for the corrected contracts:

- Page add, remove, metadata change, and body change in `refresh --diff`
- Page body comparison with matching, missing, and mismatched normalizers
- duplicate local Page titles, duplicate Canvas titles, and Canvas Pages already
  claimed by stable identity
- Page create/update/verify drift for each supported optional field
- explicit blocked behavior for any optional field intentionally outside update
  scope
- malformed YAML and TOML among otherwise valid discovered sources, proving the
  remaining inventory is returned
- assignment audit equivalence for directory and object-file snapshots
- explicit zero-weight assignment groups
- a gradebook fixture whose reconstructed weighted score deliberately differs
  from the posted score, plus unmatched or ambiguous group-column behavior

The gradebook tests close a confirmed blind spot but do not change gradebook
calculation semantics unless they expose a separate reproducible defect.

## Acceptance Criteria

- `refresh --diff` reports real Page additions, removals, and comparable changes
  using stable Page identity.
- Page body hashes are never compared across incompatible normalizer profiles.
- Status never offers the same Canvas Page as a probable match for duplicate or
  already-bound local sources.
- Page create/update/verify either covers every declared supported field or
  clearly blocks an unsupported transition; no field is silently dropped.
- Source discovery records malformed YAML/TOML as a per-file error and continues
  with unrelated sources.
- Direct-file and directory assignment snapshots preserve the same top-level
  assignment-group weights.
- Explicit zero-weight groups remain present in audit results.
- Gradebook mismatch detection and ambiguous group mapping have direct tests.
- Existing stable Page identity, rendering, source-map, and no-clobber sync
  behavior remain compatible.
- Ruff, ty, and the complete pytest suite pass.
- README, backlog, project context, and external teaching-danvas guidance are
  reconciled where behavior changes.

## Deferred

- Page rename, deletion, general upsert, module integration, asset rewriting,
  and two-way synchronization.
- Broad Page compatibility profiles or Pandoc conversion.
- Refactoring `compare_pages` or `build_pages_sync_plan` solely to improve a
  complexity score. Small behavior-preserving extractions are encouraged when
  they make the corrected identity rules independently testable.
- Panopto out-of-range timestamp tolerance; track as a small resilience item
  unless it becomes part of an active recording workflow.
- General front-matter API redesign and exhaustive utility-module coverage.
- Cosmetic documentation ordering, help-text wording tests, and complexity-only
  findings in unrelated modules.
