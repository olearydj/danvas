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

## 0.8.0 Grade Evidence Follow-On

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
enrollment is gradeable and the caller reports `manage_grades`.

## 0.9.0 Assignment Release Follow-On

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
scanning, and cleanup. The earlier 0.8.0 live gate is now complete; consolidated
release close-out remains pending.

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
remains pending.
