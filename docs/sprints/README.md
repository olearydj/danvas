# Danvas Sprint Specifications

These are the lightweight implementation specifications used for the Danvas
0.6.0 feature slices. They turned the broader backlog into bounded, testable
work without introducing a separate specification framework.

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

The combined implementation passed all three checks. Release push, CI
confirmation, and any 0.6.0 tag are tracked separately in `docs/backlog.md`.
