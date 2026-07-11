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
