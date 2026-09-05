# Related Canvas Tools

A bounded survey of other command-line and agent-facing tools for Instructure Canvas, and an account of where `danvas` sits among them.

This document exists to keep the project honest about its own positioning. It records what was actually observed, when, by what method, and - just as importantly - what the method cannot establish. It is a working reference for design decisions, documentation wording, and publication related-work sections. It is not a competitive comparison, and nothing here is intended as criticism of the projects described.

## Status and scope

Survey performed 2026-08-31 and 2026-09-01. It is current only as of those dates; see [Staleness and maintenance](#staleness-and-maintenance).

What this survey is:

- a bounded search of public GitHub repositories and PyPI packages
- a reading of published READMEs, documentation, and safety models
- a characterization of design intent, command surface, safety posture, agent posture, and maturity

What this survey is not, and what it therefore cannot support:

- it is not exhaustive, and no claim of completeness should be drawn from it
- it did not install, run, or read the source of any tool other than `danvas`
- it cannot establish that any feature is absent from a tool, only that the tool's documentation did not describe it
- it cannot support any claim that `danvas` is first, only, unique, or superior

Every negative statement in this document is phrased as "not found in the documentation reviewed" rather than "does not exist." That phrasing is deliberate and should be preserved in edits.

### Method

Two GitHub Search API queries, each sorted by most recently pushed, with the top forty results inspected:

```text
canvas-lms cli in:name,description,topics
  retrieved 2026-08-31, total_count 86

canvas instructure cli OR mcp in:name,description,topics pushed:>2026-01-01
  retrieved 2026-09-01, total_count 65
```

Package metadata came from the PyPI JSON API for `canvaslms`, `clanvas`, `canvas-cmd`, `canvasapi`, and `danvas-cli`. Repository metadata came from the GitHub REST API. READMEs and documentation were read directly from `raw.githubusercontent.com`.

Not covered, and therefore blind spots:

- non-GitHub forges: GitLab, Codeberg, and institutional or private hosting
- package registries other than PyPI: crates.io, npm, and the Go module proxy were not swept
- non-English project descriptions, except where they surfaced incidentally
- institutional tooling that is never published
- anything created or renamed after the retrieval dates

### Correction history

An earlier internal pass on 2026-08-31 concluded that there were "exactly two real peers" and that several `danvas` properties were "unmatched anywhere in the field." Both conclusions were wrong. The pass missed `thedavidweng/canvas-cli`, which documents plan-then-confirm gating, per-mutation audit logging, and partial-failure signaling - three of the properties that had been called unmatched.

The root cause was not the missed repository. It was writing absolute negatives from a documentary search and then appending a caveat conceding the search was incomplete. A caveat that contradicts the body does not repair the body.

This is recorded because the failure mode is easy to repeat: this field is crowded, fast-moving, and mostly unstarred, so keyword search reliably under-reports it. Any uniqueness claim about `danvas` is one search away from being falsified by a project that did not exist last month.

### Relationship to the published record

This document is living and informal. It is revised whenever the field shifts or a new peer surfaces, and its history is expected to accumulate corrections rather than read cleanly. Being wrong here and saying so is cheap.

The project's publication record is the opposite kind of artifact: a frozen statement of what was known, cited, and claimed at one moment, which does not change afterward. The JOSE manuscript and its related-work bibliography are prepared on the [`jose-paper` branch](https://github.com/olearydj/danvas/tree/jose-paper) and become public with the submission.

Where the two differ, each is authoritative for its own purpose. The published record governs what the project has claimed in print about related work, bounded by the date it was submitted. This document governs the underlying survey evidence and the project's current design positioning, and it changes freely. A revision here does not amend anything already published; it changes only what the project would say next time.

## How the field is layered

The tools that surfaced fall into four groups. Only the third is a peer group for `danvas`.

Client libraries: `canvasapi` (UCF Open) is the Python wrapper both `danvas` and `canvaslms` build on. It is a dependency, not an alternative. Others include `longhornopen/php-canvas-api`, `harvard-edtech/caccl` (TypeScript), and `RobertConde/canvas-lms-api` (Rust).

Student tools: submit assignments, download files, check grades. `clanvas`, `mbund/canvas-cli`, `canvas-cmd`, and several MCP servers built around student workflows. Different users, different risk profile, not comparable.

Instructor-facing command-line tools: tools that read and change course state on behalf of whoever teaches the course. This is the peer group. Three projects were examined in detail; several more were observed but not profiled.

Agent bridges: MCP servers and agent skills that expose Canvas to a model without being a general-purpose CLI. Adjacent to the agent-facing part of `danvas` but not to its workflow model.

## Direct peers

### canvaslms

Repository: `dbosk/canvaslms`. Author: Daniel Bosk, Lecturer in Computer Science, KTH Royal Institute of Technology (ORCID `0000-0003-3865-212X`). MIT. Default branch is `master`.

The published title is "canvaslms: A CLI to Canvas LMS."

Maturity: repository created 2020-09-08; 94 PyPI releases from `1.0` on 2021-09-27 to `6.20` on 2026-08-19; pushed 2026-08-31; 6 stars, 2 forks, 48 open issues. Requires Python 3.10 or later. Depends on `canvasapi` 3.4 or later. Some subcommands require `pandoc`. Written as a literate program using noweb (`.nw` sources).

Design intent: emit records that other POSIX tools can consume. The README's canonical example composes `canvaslms users`, `cut`, `ssh`, `sort`, `uniq`, and `grep` into a grading loop that ends in `canvaslms grade`. The tool deliberately does not own the workflow; the shell does. Composition is the product.

Command surface, by source module: `assignments`, `cache`, `calendar`, `content`, `courses`, `discussions`, `grade`, `login`, `modules`, `pages`, `quizzes`, `results`, `submissions`, `syllabus`, `users`. Mutating operations include setting grades and comments, editing quiz content and quiz bank items, editing announcements and discussions, and editing pages.

Also usable as a Python library, sharing the CLI's credential sources (system keyring, `CANVAS_SERVER`/`CANVAS_TOKEN`, config file) and its encrypted cache.

Notable adjacency: an optional `llm` extra pulls in provider plugins for OpenAI, Anthropic, Gemini, and Azure, used to summarize free-text quiz and survey responses.

Safety posture: no dry-run, preview, confirmation, or read-only mode appears in the README. Writes execute on invocation. The safety model is the operator's care and the shell's own idioms.

Overlap with `danvas`: this is the closest functional overlap of any tool surveyed. Both are instructor-facing, both build on `canvasapi`, and both cover assignments, announcements and discussions, pages, quizzes, submissions, and grading.

### canvas-cli (Go, jjuanrivvera)

Repository: `jjuanrivvera/canvas-cli`. MIT. No personal name is published on the maintainer's GitHub profile, so the handle is the only verifiable attribution.

Maturity: repository created 2026-01-09; 29 releases from `v1.0.0` on 2026-01-10 to `v1.13.0` on 2026-08-06; pushed 2026-08-19; 11 stars, 2 forks. Requires Go 1.25 or later to build from source.

Design intent: coverage. The project reports 876 of Canvas's 1086 documented endpoints implemented in its service layer, exposed through 93 command groups and more than 540 commands, with endpoint paths validated against Canvas's official API spec in CI. It reaches beyond course operations into account administration, SIS imports, developer keys, blueprint courses, enrollment terms, and analytics. It is a typed shell over the Canvas API for anyone who would otherwise reach for `curl`.

Authentication and distribution: OAuth 2.0 with PKCE, system keyring, multi-instance profiles, adaptive rate limiting. Output as table, JSON, YAML, or CSV. A REPL mode. Distributed via Homebrew tap, Scoop, `go install`, and a distroless image on GHCR, with cosign-signed release checksums and SBOMs.

Safety posture: `--dry-run` previews, opt-in per command. The default remains execute.

Agent posture: an MCP server mode, with sensitive flags such as `--show-token` and `--config` excluded from MCP exposure. A bundled agent skill installable via `canvas skills install --global` or `--agent <host>`, via `npx skills add`, or as a native Claude Code plugin.

Agent safety: `canvas agent guard --host claude-code|codex|opencode` generates permission rules and a PreToolUse hook derived from the live command tree, in three tiers. Irreversible verbs (`delete`, `remove`, `conclude`, `crosslist`, `uncrosslist`, `deactivate`, `unpublish`, `unlink`, `clear`, `abort`, `reset`, `void`, `cancel`, `close`, `merge`, `split`) are hard-blocked before execution. Writes (`create`, `update`, `publish`, `grade`, `upload`, `add`, `sync`) require human approval. Reads are ungated. Classification is fail-safe: an unrecognized verb defaults to requiring approval rather than passing as a read. `sis-imports create` is hard-blocked despite its verb because it can conclude or delete many records at once.

Two documented limits are worth recording. Enforcement lives in the agent host rather than in the tool, and the project's own guide concedes obfuscation caveats and recommends MCP-only operation for that reason. The config must be regenerated after each upgrade to cover new commands. And `canvas api <METHOD> <PATH>` bypasses verb classification entirely, covered only partially by deny patterns on the Bash surface.

### canvas-cli (Go, Weng)

Repository: `thedavidweng/canvas-cli`. Author: David Weng, Vancouver. The name is published on the linked project site at `thedavidweng.github.io`; the GitHub profile name field reads only "Davy." Apache-2.0.

Maturity: repository created 2026-06-13; pushed 2026-08-22; 0 stars. The README H1 is `canvas-cli` with the tagline "Agent-friendly CLI for Canvas LMS."

Design intent: stable JSON output, automatic pagination, mutation safety gates, and audit logging, aimed at agent-driven use.

Safety posture, from `docs/safety-model.md`, is the most developed of the peers and the closest in spirit to `danvas`. Three tiers:

- reads run normally with token authentication
- low-risk writes, meaning operations affecting the authenticated user's own workflow (inbox message, discussion reply, assignment submission, self comment), must support `--dry-run`, require explicit content input, emit an audit log, and reject an empty body unless explicitly allowed
- high-risk writes, meaning anything affecting students, grades, course content, publication state, dates, or many records, must default to dry-run preview where feasible, require `--confirm`, require operation-count confirmation for bulk operations, support a `--read-only` hard block, emit an audit log, preserve Canvas response metadata, and show partial failures clearly

There is no separate destructive tier because the CLI ships no dedicated `delete` subcommands; deletes go through `canvas api delete` and are gated as high-risk writes.

Global flags are `--dry-run`, `--confirm`, and `--read-only`, plus a `CANVAS_READ_ONLY=1` environment variable that overrides command flags. With no flags, the tool prompts interactively. Under `--read-only`, a write command exits immediately with code 7 and the message `operation blocked by read-only mode`; `--read-only` overrides `--confirm`, while `--dry-run` remains allowed.

Every remote mutation appends a JSONL event to a local audit log, under `~/.local/state/canvas-cli/` on Linux, `~/Library/Application Support/canvas-cli/` on macOS, and `%LOCALAPPDATA%` on Windows. The event carries timestamp, command, profile, base URL, HTTP method and path, resource identifiers, a SHA-256 request hash, response status, the Canvas request ID, and whether the run was a dry run. The model states that tokens and full sensitive message bodies are not logged by default; hashes and metadata are logged instead.

Bulk write commands must generate a plan first, then execute with `--confirm`. High-risk bulk operations stop on the first write failure unless `--continue-on-error` is set, and the final JSON carries `ok: false` with category `partial_failure` when any item fails.

One caveat on all of the above: `safety-model.md` reads in places as a specification of required behavior rather than a description of confirmed shipped behavior. Nothing was executed to verify it.

## Comparison

### Intent

| Tool | The CLI is fundamentally | Unit of work |
| --- | --- | --- |
| `canvaslms` | a data source for the shell | a command in a pipeline |
| `canvas-cli` (jjuanrivvera) | a typed interface to the API | an endpoint call |
| `canvas-cli` (Weng) | an agent-safe mutation interface | a gated operation |
| `danvas` | a workflow over local sources | a course project |

### Surface

| Tool | Command surface | Reach |
| --- | --- | --- |
| `canvaslms` | ~15 subcommand modules | course level |
| `canvas-cli` (jjuanrivvera) | 93 groups, 540+ commands, ~80% of endpoints | course, account, SIS, admin |
| `canvas-cli` (Weng) | grading, content, discussions, inbox, raw API | course level |
| `danvas` | 16 Canvas-mutating commands plus read and audit families | course level |

`danvas` has the narrowest mutating surface of the group. That follows from design rather than from immaturity: every mutating command carries plan and apply modes, expected-state guards, readback, and evidence retention, and that per-command cost bounds how many commands can exist.

### Safety default

| Tool | Default on bare invocation | Where enforcement lives |
| --- | --- | --- |
| `canvaslms` | executes | operator practice |
| `canvas-cli` (jjuanrivvera) | executes; `--dry-run` opt-in | agent host, via generated hooks and permission rules |
| `canvas-cli` (Weng) | interactive prompt; dry-run default for high-risk writes where feasible | in the tool, via flags and env |
| `danvas` | plans and exits; never mutates | in the tool, asserted at each write primitive |

The axis that separates `danvas` is not whether a preview exists but whether the safe path is the default and whether the guarantee survives the caller. In `danvas`, omitting `--apply` cannot mutate Canvas, an assertion verifies normalized mode immediately before each write primitive, and no user or project configuration can restore mutation-on-omission. That guarantee holds identically for a person, a script, a scheduled job, or an agent, on any host, with nothing to install and nothing to regenerate after an upgrade.

Weng's model is the nearest neighbor: in-tool, flag-driven, with a hard read-only override, and dry-run-by-default for the high-risk tier "where feasible." The difference is scope and unconditionality rather than kind.

### Agent posture

| Tool | Machine-readable output | Agent skill | MCP | Agent-specific gating |
| --- | --- | --- | --- | --- |
| `canvaslms` | POSIX-friendly records | no | no | no; optional LLM extra for summarization |
| `canvas-cli` (jjuanrivvera) | JSON, YAML, CSV | yes | yes | yes, host-side |
| `canvas-cli` (Weng) | stable JSON | not documented | not documented | same gates as human use |
| `danvas` | `danvas-command-guide-v1` per-command JSON | yes, version-matched | no | same gates as human use |

Agent-aware Canvas tooling is an established category as of 2026, not an opening. Beyond the peers, `treerobin06/canvas-cli-skill`, `johnnyrobot/canvas-accessible-content`, `vivekp-05/canvasctl`, `hughsibbele/Canvas-Agent`, `JohannsenLum/canvas-api-mcp`, and `Shoberman2/schoolbridge` all target agent use of Canvas in some form. The `danvas` contribution here is narrower and more specific than shipping a skill: deterministic per-command descriptions of what a command reads or changes, whether it handles private information, how it must be reviewed, and how to recover from an uncertain result, version-matched to the release.

### Local record

| Tool | Retains a local record | Shape |
| --- | --- | --- |
| `canvaslms` | not documented | - |
| `canvas-cli` (jjuanrivvera) | not documented | - |
| `canvas-cli` (Weng) | yes | append-only JSONL audit log, one event per mutation |
| `danvas` | yes | plans, report manifests, source maps, integrity sidecars, readback and recovery artifacts |
| `Knn8787/canvas-ledger` | yes, per its description | durable local metadata ledger |

Both `danvas` and Weng's tool preserve unsuccessful and uncertain outcomes rather than only successes. The difference is that Weng's log records the request and the transport response, while `danvas` additionally records an authoritative readback and classifies the resulting state.

### Maturity

| Tool | Repo created | Public distribution | Signals |
| --- | --- | --- | --- |
| `canvasapi` | 2016-11-15 | 29 PyPI releases, `3.6.0` | 674 stars, 192 forks |
| `clanvas` | 2018-02-11 | 8 PyPI releases, last 2019-05-01 | 54 stars; pins `canvasapi==0.12.0`; dormant |
| `canvaslms` | 2020-09-08 | 94 PyPI releases since 2021 | 6 stars, 48 open issues, pushed daily |
| `canvas-cli` (jjuanrivvera) | 2026-01-09 | 29 releases in 8 months | 11 stars, Homebrew, Scoop, GHCR, signed |
| `canvas-cli` (Weng) | 2026-06-13 | GitHub only | 0 stars |
| `danvas` | 2026-05-13 | 3 PyPI releases across two days | 0 stars, public beta |

The honest reading: `danvas` is among the youngest of the instructor-facing tools and had a seventeen-day public distribution history when this survey was taken. It cannot differentiate on maturity, breadth, or adoption, and should not try. Its case rests on design. Note also that star counts are a weak signal here - the most-starred CLI in the field has been dormant since 2019, and the most actively maintained peer has six stars.

## Where danvas differs

Stated as findings of this survey, not as properties of the field. Each means "not found in the documentation reviewed."

A local course project as the unit of work, with a source map binding authored local files to specific Canvas objects, so that local sources are the thing an instructor edits and Canvas is reconciled against them. No peer documents a project model or source binding.

Plan-by-default enforced inside the tool at the write primitive, unconditioned on host configuration, caller identity, or user settings.

Authoritative readback after a write, with an explicit vocabulary separating transport acceptance from confirmed state: `already_applied`, `applied_verified`, `unchanged_failure`, `partially_applied`, `applied_unverified`, `accepted_unverified`, `indeterminate`, `skipped_after_stop`. Weng's tool signals `partial_failure` and preserves Canvas response metadata; a readback-and-compare step with a named indeterminate state was not found elsewhere.

An enforced private-artifact boundary for student-identifying output: `0700` directories and `0600` files from creation including temporary files, symlink rejection at protected boundaries, no-clobber, and integrity sidecars. Across the peers, the only comparable provision found was Weng's rule against logging tokens and sensitive bodies.

Per-command machine-readable contracts stating effect, privacy class, review requirement, and recovery procedure, version-matched to the release.

## Where danvas is not distinctive

Recorded deliberately, and to be maintained with the same care as the section above.

Being a Canvas command-line tool at all. Being instructor-facing. Building on `canvasapi`. Shipping an agent skill. Offering a preview before a write. Keeping a local record of mutations. Distinguishing partial from complete failure. Avoiding logging secrets. MIT licensing. Being maintained by one person alongside teaching.

Several peers arrived at plan-then-confirm, local audit records, and agent packaging independently and, in at least one case, earlier.

## Claim boundaries

The following must not be inferred from this document, and must not appear in project documentation, release notes, or publications on its basis:

- that `danvas` is first, only, novel, or unique in any respect
- that any other tool lacks a capability, is unsafe, or is poorly designed
- that the surveyed set is complete or representative of all Canvas tooling
- that documented behavior in another project has been verified

The open question of whether existing Canvas clients and scripts lack a comparable operational safety model remains unresolved and unclaimed. This survey does not resolve it, and resolving it would require installing and exercising the tools, which was not done.

Where the project cites these tools, it should do so descriptively and representatively: naming a few projects that take genuinely different approaches, and describing what `danvas` does rather than what others do not.

## Broader field observed

Instructor-facing or agent-facing Canvas tooling active in 2026, surfaced by the two queries but not profiled. Listed to document that the field is larger than the peer set, not as a directory.

| Project | Language | License | Stars | Last push | Description as published |
| --- | --- | --- | ---: | --- | --- |
| `edulinq/lms-toolkit` | Python | MIT | 15 | 2026-08-30 | suite of tools and Python interface for Canvas |
| `caphefalumi/Canvas-CLI` | TypeScript | MIT | 4 | 2026-08-16 | a simple CLI for interacting with Canvas LMS |
| `francojc/dauber` | Python | MIT | 1 | 2026-08-24 | Canvas CLI |
| `justinmiller87/canvas-tools` | Python | MIT | 0 | 2026-08-31 | CLI toolkit for managing courses via REST/GraphQL |
| `Knn8787/canvas-ledger` | Python | MIT | 0 | 2026-08-31 | durable local ledger of Canvas metadata and history |
| `johnnyrobot/canvas-pp-cli` | Go | Apache-2.0 | 0 | 2026-08-24 | full 1042-endpoint surface plus roster and standings commands |
| `johnnyrobot/canvas-accessible-content` | Python | - | 0 | 2026-08-24 | Agent Skill for authoring and remediating course content |
| `jakeryderv/canvaskit` | Python | none | 0 | 2026-08-24 | CLI and Python toolkit to access, sync, query, automate course data |
| `guipaiva/canvas-cli` | Python | MIT | 0 | 2026-08-08 | generic Canvas LMS CLI for teachers |
| `vivekp-05/canvasctl` | Python | MIT | 0 | 2026-07-19 | local vault, Claude chat agent, and MCP server |
| `treerobin06/canvas-cli-skill` | Shell | MIT | 0 | 2026-05-05 | atomic CLI built for AI agents, bilingual docs |
| `hughsibbele/Canvas-Agent` | TypeScript | - | 1 | 2026-08-18 | MCP server connecting Claude to Canvas |
| `JohannsenLum/canvas-api-mcp` | Python | - | 2 | 2026-08-15 | Canvas MCP server, curated student tools |
| `Shoberman2/schoolbridge` | TypeScript | - | 0 | 2026-08-18 | MCP server bridging Canvas and other platforms to agents |
| `kc0506/ntucool` | Rust | - | 10 | 2026-07-10 | NTU COOL CLI and MCP server on a Canvas base |

Student-facing tools, excluded from the peer comparison: `clanvas`, `mbund/canvas-cli` (Rust, submit and download), `canvas-cmd`, `soffits/canvas-student-cli`, `ryansigdel/push2canvas`, `crafterten/canvas-cli-for-ai-and-students`.

## Staleness and maintenance

This survey has a short half-life. Between the two query dates, one day apart, the result sets differed and new repositories appeared. Treat any statement here as an observation with a date attached.

Refresh triggers:

- before any publication or release note that positions `danvas` against other tools
- before responding to peer review that raises related work
- when a design decision turns on what peers do
- annually, if none of the above has occurred

When refreshing, re-run both queries verbatim, record the new `total_count` values, and diff the peer set. Add new peers rather than rewriting history: the correction record above is more useful than a tidy document.

Do not convert this into a comparison chart for promotional use, and do not strengthen any "not found" phrasing into an assertion of absence without installing and exercising the tool in question.
