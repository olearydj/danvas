---
name: danvas
description: >-
  Use when an operator asks an agent to work with Canvas through the danvas CLI:
  inspect or compare course state, initialize or refresh a project, manage
  authored assignments/Pages/announcements/discussions, export private rosters
  or submissions, prepare or apply grades and feedback, handle Files or
  recordings, diagnose authentication, or explain danvas safety and recovery.
  Use only for the installed danvas command, not as general Canvas API guidance
  or institution-specific policy.
license: MIT
compatibility: >-
  Requires the danvas command from the danvas-cli 0.21.x distribution on a POSIX
  platform. Canvas-backed operations require operator-configured neutral
  credential delivery and network access.
metadata:
  danvas-cli-distribution: danvas-cli
  danvas-cli-version: "0.21.1"
  skill-version: "1"
---

# Danvas

Use the installed `danvas` command as the authority for Canvas course
operations. Keep provider, institution, workspace, and approval policy outside
this generic skill.

## Start With Discovery

1. Run `danvas --version` when compatibility matters.
2. Start at `danvas --help`, then inspect the relevant family and leaf help.
3. Use `danvas guide list` and a task guide for multi-command workflows.
4. Use `danvas describe COMMAND --format json` for structured command facts.

Do not rely on a remembered option when installed help or description differs.
Do not inspect a source checkout merely to recover ordinary command syntax.

## Classify The Requested Effect

Before running anything, distinguish:

- local inspection with no Canvas access;
- Canvas read with stdout or retained local evidence;
- local source/report/download creation that never changes Canvas; and
- a Canvas mutation that requires a reviewed plan and explicit authorization.

Help and `describe` derive those effects from the shipped access registry. A
local write is not a Canvas mutation, but it still needs an appropriate output
location and no-clobber review.

## Use The Safe Workflow

1. Locate the course project from explicit user context or `.danvas/`.
2. Read project instructions that govern the workspace.
3. Refresh only when current Canvas evidence is needed; `status` itself uses the
   saved snapshot and local sources.
4. For a Canvas-changing command, run the bare command or `--dry-run` to plan.
5. Review target identity, expected state, privacy, visibility, and evidence.
6. Add `--apply` only when the user has authorized that Canvas mutation. Preserve
   any additional `--confirm` guard shown by help.
7. Inspect authoritative verification or retained results after apply.

Never drop `--apply` to make an outdated example work. Never add `--apply` to a
local sync command. Never infer mutation authorization from a request to inspect,
compare, prepare, download, export, or explain.

Missing danvas command coverage does not authorize direct Canvas API calls,
browser automation, or provider-specific fallback. Classify the proposed effect
and ask the operator before leaving the supported interface. A Classic Quiz
analysis report request is a Canvas mutation even though it changes no quiz
content or grades.

## Preserve Identity And Evidence

Prefer stable Canvas IDs, explicit URLs where required, source front matter, and
project provenance. Do not silently title-match or substitute a display name for
a stable identity.

Treat partial snapshots, conflicts, rejected writes, accepted-unverified writes,
and indeterminate outcomes as different states. Do not blindly retry a write
whose acceptance is uncertain. Read the private result/recovery artifact and the
leaf help before proposing the next action.

## Protect Retained Data

Respect `shareable`, `course_internal`, and `private` classifications. Student
identifiers, rosters, submissions, grades, comments, discussion posts, feedback,
and recording captions commonly require private handling. In an initialized
project, private defaults live beneath `.danvas/private/` with protected POSIX
permissions.

An explicit path does not change the data classification. Do not paste raw
private artifacts, token values, reusable protected URLs, or full large payloads
into the conversation. Prefer aggregate terminal output, report summaries,
manifests, and bounded excerpts.

## Keep Credentials Provider-Neutral

Danvas accepts an environment-variable name or an absolute credential-file path.
It does not own a password-manager integration. Follow operator or organization
policy for external injection; never print, resolve, copy, or retain the token.

Use `danvas auth doctor` for offline origin and transport diagnosis. Use
`danvas auth doctor --check-canvas` only when a bounded live Canvas check is
authorized and credential delivery is available.

## Load Focused References Only As Needed

- Read [references/discovery.md](references/discovery.md) when command selection
  or machine-readable introspection is the main task.
- Read [references/workflows.md](references/workflows.md) for common course,
  authored-content, grades, Files, and local-sync sequences.
- Read [references/safety-and-recovery.md](references/safety-and-recovery.md) for
  mutation guards, evidence states, or uncertain outcomes.
- Read [references/privacy-and-auth.md](references/privacy-and-auth.md) for
  artifact handling and neutral credential boundaries.

Use `danvas guide TOPIC` for details that may change with the installed CLI.
