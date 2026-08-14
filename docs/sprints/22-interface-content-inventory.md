# Sprint 22 Interface Content Inventory

Status: Characterization baseline for the released 0.19.0 interface.

This inventory separates information that belongs in danvas's public interface
from policy that belongs to a maintainer's private workspace. It is an input to
Sprint 22, not a runtime dependency. The external files named below remain
outside this repository and are never imported, read, or required by danvas.

## Classification

- **Public command truth** describes executable syntax, options, effects,
  identity rules, output, verification, or recovery behavior.
- **Public workflow guidance** explains how any operator can combine public
  commands safely.
- **Private maintainer policy** names a person's directories, provider wrapper,
  escalation rules, course filing conventions, or other workspace-specific
  instructions.

## Repository-Owned Public Sources

- `README.md`: public orientation, installation, setup, safety, common workflows,
  and documentation map. Classification: public truth and workflow guidance.
- `docs/authentication.md`: neutral credential transport, selection, origin
  binding, external-runner examples, and diagnosis. Classification: public
  truth and workflow guidance.
- `docs/configuration.md`, `docs/course-yaml.md`: profiles, projects, layouts,
  inventory, Panopto selectors, and course policy. Classification: public truth.
- `docs/privacy.md`, `docs/mutation-safety.md`, `docs/compatibility.md`: artifact
  classes, plan/apply, evidence/recovery, support, and known bounds.
  Classification: public truth and workflow guidance.
- `docs/authored-sources.md`: layouts, source schemas, linting, provenance, and
  safe source-to-Canvas workflow. Classification: public truth and workflow
  guidance.
- `docs/migrations/*.md`: version-specific compatibility history.
  Classification: public truth, but not default help content.

The public documents are authoritative for product-wide concepts. Sprint 22 may
move concise workflow material into default help, guides, machine description,
and the packaged skill, but those rendered surfaces must continue to derive
effects and privacy from the typed registries.

## External Personal Sources

Point-in-time inputs reviewed for this baseline:

- `~/.codex/skills/teaching-danvas/SKILL.md`: 99 lines. It mixes public workflow
  guidance with private maintainer policy. The reusable public portions include
  plan/apply, status/refresh, private artifacts, bounded diagnostics, and the
  rule that discussion scoring produces a grade plan. The private portions
  include Auburn workspace paths, `danvas-op`, 1Password escalation and timeout
  policy, course-local instruction discovery, and transcript filing choices.
- `~/.codex/skills/teaching-danvas/references/danvas-commands.md`: 1,097 lines.
  Its command-tree, safety tiers, and command-family recipes are public truth or
  workflow guidance. Any concrete workspace paths, institution assumptions,
  provider wrapper, agent approval instructions, and personal filing policy are
  private maintainer policy.

These files are migration inputs only. The generic skill must not copy their
name, path trigger, provider wrapper, escalation rules, or private filing
policy. The personal `teaching-danvas` overlay may continue to point at the
public danvas skill after a separately authorized post-release update.

## Family Routing

- Setup and authentication: root `init`, `auth`, `courses`, `refresh`; public
  truth comes from README, authentication, and configuration. Provider-specific
  personal invocation stays private.
- Discovery and local comparison: `status`, `reports`, `sources`, `gradebook`,
  and `quiz analysis`; public truth and reusable workflow guidance.
- Authored Canvas content: `assignments`, `pages`, `announcements`,
  `discussions`, and `quiz import-qti`; public truth plus plan/apply workflow.
- Private student work: `roster`, `submissions`, `grades`, and discussion
  scoring; public truth plus privacy, evidence, stop, and recovery guidance.
- Files and recordings: `files` and `recordings`; public truth plus sensitivity
  warnings. Personal transcript destinations remain private policy.

## Implementation Boundary

Help and guides should contain the shortest useful public layer. The machine
description should expose the same command facts structurally. The packaged
skill should teach an agent how to discover and combine those surfaces without
embedding the complete command reference. No Sprint 22 test may depend on the
external personal files after this inventory is committed.
