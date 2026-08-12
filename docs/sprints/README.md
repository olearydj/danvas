# Danvas Sprint Specifications

These are the lightweight implementation specifications used for bounded,
testable Danvas feature and remediation slices without introducing a separate
specification framework.

They were implemented and locally verified in this order on 2026-07-10:

- Sprint 1: [Transaction-Safe Grade Patching And Cleanup](01-transaction-safe-grades.md)
- Sprint 2: [Override-Aware Assignment Snapshots And Status](02-override-aware-assignments.md)
- Sprint 3: [Submission Evidence And Metadata Exports](03-submission-evidence.md)
- Sprint 4: [Canvas Pages V1](04-canvas-pages-v1.md)
- Sprint 4.5: [Canvas Pages V2: Styled Update Workflow](04-5-canvas-pages-v2.md)
- Sprint 5: [Canvas-Facing Source Linting](05-source-lint.md)

## Dependency Notes

- All slices build on the existing auth, mutation-banner, report, and error-sanitizing
  conventions.
- Sprint 2 changes the course snapshot schema but does not block Sprint 1.
- Sprint 3 provides useful primitives for future exam reconciliation, but neither
  Sprint 1 nor Sprint 2 depends on it.
- Sprint 4 reuses source-map and report-run helpers already delivered for
  assignments and announcements; it does not depend on Sprint 3.
- Sprint 4.5 builds on the Page source, renderer, create, readback, and verify
  contracts established in Sprint 4.
- Sprint 5 follows Sprint 4.5 so the linter can support the settled Page source
  and restricted CSS contracts from its first release.

Each sprint updated `README.md`, `docs/backlog.md`, and the external
teaching-danvas command reference when its command surface shipped. Completion
required the standard Ruff, ty, and pytest checks to pass.

The combined implementation passed all three checks and was published as
`v0.6.0` at commit `05201fa`. Release status is recorded in
`docs/backlog.md`.

## Pages Follow-Ons

The selected follow-on work continues the bounded Pages workflow:

- Sprint 6: [Canvas Pages Discovery, Snapshot, And Status](06-canvas-pages-status.md)
- Sprint 7: [Canvas Pages Source Sync And Conversion](07-canvas-pages-sync.md)

Sprints 6 and 7 are implemented and verified. Sprint 6 adds the read-only schema
and comparison foundation; Sprint 7 uses it for project-wide identity matching
and is the only one of the two that writes local course sources. The
non-normative Sprint 7 field case passed in sandbox course 1576638 on 2026-07-10,
including browser inspection and cleanup of its temporary draft Page. Neither
sprint broadens Canvas mutation behavior.

The combined implementation was published as `v0.7.0` at commit `5988c93`.

## 0.7.1 Remediation

A comprehensive post-0.7.0 audit identified a smaller set of behavioral defects
alongside test gaps, documentation drift, and complexity debt. The patch-release
work is split by invariant rather than treating all audit findings as equivalent:

- Sprint 8: [Privacy And Filesystem Safety Hardening](08-privacy-filesystem-safety.md)
- Sprint 9: [Correctness And Resilience Remediation](09-correctness-resilience.md)

Sprint 8 owns private report permissions, untrusted download-path containment,
and leakage-safe diagnostics. Sprint 9 owns Page diff/identity/update correctness,
source-scan resilience, assignment-audit edge cases, and directly related test
gaps. They may be implemented independently except where both touch Page plan or
report behavior; those overlaps must preserve Sprint 8's stricter output-safety
boundary.

Both sprints are implemented and locally verified. Complexity-only refactors,
cosmetic documentation findings, and unrelated broad coverage work remain
deferred unless a small extraction is necessary to make a remediation safely
testable. A final audit-cleanup pass also added Panopto timestamp resilience,
corrected documentation drift, and replaced brittle/implicit tests. Ruff, ty,
and all 312 tests pass for the combined implementation released as `v0.7.1`.

## 0.8.0 Grade Evidence Development Line

The implemented development-line follow-on is:

- Sprint 10: [Truthful Grade Posting And Release Evidence](10-truthful-grade-posting.md)

Sprint 10 combines field-observed backlog items 6 and 10. It fixes the
production exact-comment replacement path, replaces binary per-row failure
reporting with authoritative readback classification, adds bounded private
recovery evidence, and records a conservative targeted-student release-state
conclusion in private post/clear/verify receipts. It deliberately excludes
grade-posting-policy mutations and live gradebook export. Ruff, ty, and all 360
tests pass locally. Its bounded live Canvas field acceptance passed on
2026-08-11 after the user explicitly authorized the sandbox enrollment. The
production exact-comment fallback returned `verified_applied`, explicit
verification reported `verified_visible`, a stable-ID rerun returned
`already_applied`, restoration was independently confirmed, and the disposable
assignment was removed. The field case also established that this Canvas
instance rejects grade updates on an unpublished assignment even when the
enrollment is gradeable and the caller reports `manage_grades`. This previously
untagged development line shipped in the consolidated `v0.10.0` release.

## 0.9.0 Assignment Release Development Line

The implemented next feature slice is:

- Sprint 11: [Safe Assignment Release Evidence](11-safe-assignment-release.md)

Sprint 11 refines field-observed backlog item 8 around the gaps still present in
the current tree: stable file-upload links, duplicate-action dry-run evidence,
`allowed_extensions` and exact file-ID verification, complete-versus-partial
status semantics, and safe assignment report/export projections. The design
recognizes that `unlock_at` and `group_category_id` verification already ship
and treats the previously observed numeric date enrichment as a regression
invariant because that behavior is not present in the current source.
It is locally verified with Ruff, ty, and all 381 tests. Its bounded live Canvas
field case passed on 2026-08-11, including create/overwrite/rename planning,
stable upload evidence, positive and negative exact-file verification, artifact
scanning, and cleanup. This previously untagged development line shipped in the
consolidated `v0.10.0` release.

## 0.10.0 Authorization-Resilient Snapshot Follow-On

The implemented next feature slice is:

- Sprint 12: [Authorization-Resilient Partial Snapshots](12-authorization-resilient-snapshots.md)

Sprint 12 addresses field-observed backlog item 9. A same-credential read-only
check on 2026-08-11 confirmed that group-category enumeration is forbidden for
one historical course while remaining available and empty in the sandbox
course. The implementation introduces schema-v5 collection authority metadata so
`init`, `refresh --diff`, and `status` can distinguish a genuinely empty
collection from an unavailable, failed, or partially collected one. Design is
implemented and locally verified with Ruff, ty, and all 395 tests. Its bounded
read-only Canvas field case passed on 2026-08-11: the historical course produced
an explicit partial/forbidden group-category state with no diff removal claims,
while the sandbox produced an authoritative empty state. Release close-out
completed in `v0.10.0`: the exact commit passed CI, the tag is published, and an
isolated tagged installation passed version, help, and local auth diagnostics.

## 0.10.1 Installed CLI Health Follow-On

The implemented maintenance slice is:

- Sprint 13: [Installed CLI And Release Health](13-installed-cli-release-health.md)

Sprint 13 turns the manual `v0.10.0` build, isolated-wheel install, tagged
install, and startup checks into a reusable local script and CI contract. It
also aligns the uv build-backend range, upgrades the workflow to Node.js 24
action generations, validates package/tag version equality, and documents
editable versus exact-tag installation and scoped uv recovery. It adds no
Canvas command or Python package module. It was originally targeted for 0.10.1;
the untagged line is included in the 0.10.2 maintenance release.
Frozen sync, Ruff, ty, all 400 tests, and the complete local editable/wheel
smoke passed on 2026-08-11. The published v0.10.2 tag passed both CI jobs on the
exact release commit; replacing and checking the user's global installation
remains an explicitly authorized acceptance step.

## 0.10.2 Assignment Release Maintenance

The 0.10.1 version was consumed by the public Sprint 13 commit but was not
tagged. The next maintenance release is therefore 0.10.2. It retains Sprint
13's installed-CLI checks and repairs two evidence-integrity defects found in a
post-implementation review:

- assignment update/upsert comparison retains declared assignment-group aliases
  and canonical Canvas URLs through no-change planning and live readback
- file upload evidence records Canvas mutation outcome separately from stable-URL
  completeness, so a successful upload cannot be reported as failed or invite
  an unsafe retry

The patch also passes the configured Canvas origin into assignment mutation
projections and rejects an explicitly empty release-smoke expected version.
Every supported fix has focused regression coverage. The frozen suite, Ruff,
ty, isolated installed-CLI smoke, and tag CI passed on the exact v0.10.2 commit.

## 0.11.0 Authored Discussion Follow-On

The implemented feature slice is:

- Sprint 14: [Authored Discussion Creation And Safe Updates](14-discussion-source-workflows.md)

Sprint 14 adds one Markdown contract for a root discussion topic and explicit
`--- reply ---` instructor prompts, graded-discussion assignment metadata,
offline create planning, stable topic/assignment/entry provenance, readback
verification, and declared-field or body-only update scopes. The new
`danvas.discussion_sources` module owns these mutation and evidence concerns;
the existing `danvas.discussions` module remains focused on export, local prompt
sync, scoring, and grade upload. Released in 0.11.0 after bounded sandbox Canvas
acceptance passed create/readback, verify, duplicate prevention, body-only
update, seed preservation, and guarded cleanup. Ruff, ty, all 439 tests, and
isolated editable/wheel release smoke pass locally. A
post-review evidence hardening pass also rejects malformed nonblank grade rows
and duplicate normalized Canvas IDs before Canvas access.
