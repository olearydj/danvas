# Sprint 22: Agent-Facing Help And Portable Skill

Status: proposed follow-on to the Sprints 18-21 public-readiness program. This
design assumes the 0.18.0 public-beta contracts have shipped and passed their
release gates. It authorizes no implementation, skill installation, external
plugin publication, filesystem change outside the repository, or Canvas access
or mutation.

## Outcome

Make the installed `danvas` command the authoritative, self-describing interface
for both people and software agents.

An unfamiliar operator or agent should be able to start with `danvas --help`,
move to one command-family help screen, inspect an exact leaf command, and learn:

- what the command is for;
- whether it reads Canvas, writes local files, or can mutate Canvas;
- whether its output may contain private course or student data;
- how it resolves stable identity;
- what a normal plan/apply/verify sequence looks like;
- where retained evidence is written; and
- what safe next action follows a failure or indeterminate result.

Longer task guidance remains available without network access, and agents that
need a structured command model can request versioned JSON rather than scrape a
Rich terminal layout. A generic Agent Skill ships with the installed CLI and can
be installed explicitly for common agent hosts without inheriting the
maintainer's institution, filesystem, or private teaching workflow.

The target release is 0.19.0. This is an agent-interface and documentation
release, not a new Canvas feature family.

## Why This Sprint Follows Public Readiness

The existing public-readiness program deliberately changes the facts that an
agent-facing guide would need to teach:

- Sprint 18 / 0.15.0 replaces the Auburn fallback with explicit instance
  profiles and new instance/timezone precedence;
- Sprint 19 / 0.16.0 establishes the private-artifact boundary and safe default
  locations;
- Sprint 20 / 0.17.0 makes Canvas mutations plan by default, reserves `--apply`
  for Canvas writes, separates local-write sync behavior, and reconciles grade
  evidence; and
- Sprint 21 / 0.18.0 generalizes source layouts, schemas, integrations,
  packaging, and public documentation.

Implementing the agent interface before those contracts settle would publish
and install guidance that immediately becomes stale. Sprint 22 begins only from
the released 0.18.0 command surface. It may reuse the command-effect and
private-output inventories established by Sprints 19-20, but it must not weaken
their safety rules or delay their release.

The Page asset adapter or another Canvas feature does not enter this sprint.
Backlog priority after the public-readiness program remains a separate product
decision.

## Current State

### CLI help is accurate but shallow

The current Typer registrations define a useful one-line summary for the root
application and each command family. The same short string is also the complete
introductory prose on the family's own help page. For example,
`danvas assignments --help` says that assignments can be created from Markdown
or exported for review, but it does not explain the ordinary create, update,
verify, identity, privacy, and mutation workflows.

Leaf commands generally have accurate option-level help. The missing layer is
workflow context: agents can discover flags but still need a separate reference
to decide which command to run first and which operations require approval.

Typer already supports separate `short_help`, longer `help`, Rich/Markdown
formatting, and an `epilog` intended for examples. Sprint 22 should use those
capabilities rather than replace the CLI framework or hand-build a parallel help
renderer.

### The external skill is useful but not public product documentation

The current external `teaching-danvas` skill is explicitly scoped to Auburn
teaching workspaces and assumes maintainer-specific course roots, context files,
sandbox escalation behavior, transcript locations, and a globally installed
private workflow. Its main `SKILL.md` is about 2,200 words and its command
reference is about 4,900 words.

That skill already uses the right broad progressive-disclosure shape: a
procedural entry point points to a longer reference. The problem is ownership
and layering. Public danvas command truth lives outside the repository alongside
personal operating rules, so the external reference must be updated whenever a
command ships and a new public user cannot obtain it from the package.

Sprint 22 does not install or publish the existing `teaching-danvas` skill. It
creates a new generic `danvas` skill. The personal skill may later become a thin
overlay that adds course-workspace and agent-host policy without restating the
public command surface.

### Agent Skill conventions are converging

The ecosystem now has a usable common baseline:

- the open [Agent Skills specification](https://agentskills.io/specification)
  defines a skill directory with required `SKILL.md` metadata and optional
  scripts, references, and assets;
- [OpenAI documentation](https://learn.chatgpt.com/docs/build-skills) describes
  the same progressive loading model for ChatGPT and Codex and recognizes
  repository/user `.agents/skills` locations;
- [Claude Code](https://code.claude.com/docs/en/skills) supports Agent Skills in
  `.claude/skills` and supports plugins for versioned distribution;
- [Gemini CLI](https://geminicli.com/docs/cli/using-agent-skills/) supports
  `.gemini/skills`, the shared `.agents/skills` alias, and its own skill
  installer; and
- [GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)
  supports project and user skills, including `.agents/skills`, with current
  GitHub CLI support for previewing and installing skills.

These host conventions remain younger and less stable than danvas's command
contract. The generic skill must follow the portable specification first, keep
host-specific metadata optional, and isolate target-path knowledge inside the
installer so later host changes do not require rewriting command guidance.

Current OpenAI guidance for an agent-facing CLI also emphasizes composable
commands, predictable JSON, bounded exact reads, file outputs for large
payloads, clear setup diagnostics, and draft-before-write behavior. Sprint 22
extends danvas in that direction without turning it into an MCP server or a
general agent runtime.

## Design Principles

1. **The executable CLI is authoritative.** A skill routes work and explains
   safety; it does not become a second command specification.
2. **Default help must be useful.** There is no hidden `--agent-help` mode that
   an unfamiliar agent would need prior knowledge to discover.
3. **Use progressive disclosure.** Root, group, leaf, guide, and machine
   description each add detail appropriate to the question being asked.
4. **Effects are explicit.** Canvas reads, local writes, Canvas writes, private
   outputs, notifications, and grade effects are separate metadata, not one
   overloaded `mutating` boolean.
5. **Help is offline and deterministic.** Rendering help or command metadata
   never resolves a profile, secret, course, project, or Canvas object.
6. **Machines receive structure.** Agents may read prose, but they are not
   required to parse terminal boxes, color, wrapping, or option-table spacing.
7. **Installation is a trust boundary.** The skill installer previews exact
   local changes, writes only to a selected target, and never silently replaces
   user-authored instructions.
8. **Host permissions remain host policy.** The portable skill does not
   pre-approve a shell or bypass an agent's approval and sandbox rules.

## Scope

Sprint 22 includes:

1. bounded workflow-rich default help at root, command-family, and leaf levels;
2. offline `danvas guide` topics for longer task-oriented guidance;
3. versioned `danvas describe` text and JSON command discovery;
4. a typed command-guide registry that supplies semantic metadata to every
   renderer;
5. a generic, spec-valid, repo-owned `danvas` Agent Skill;
6. `danvas skill show`, `skill install`, and `skill doctor` commands;
7. deterministic user/project installation targets for an initial set of agent
   hosts;
8. wheel/sdist inclusion and clean-install verification for the skill artifact;
9. migration guidance for reducing the external personal skill to an overlay;
   and
10. structural, snapshot, installer-safety, and bounded agent-behavior
    acceptance tests.

## 1. Default Help Contract

### Root help

`danvas --help` remains a normal CLI help screen, but its opening section should
answer the first operational questions instead of only listing possible uses.
It contains:

- one short statement of purpose and the archival/history non-goal;
- a generic four-step start path such as `auth doctor`, `init`, `refresh
  --diff`, and `status`;
- an effect legend distinguishing read-only, private/local output, local source
  creation, Canvas plan, and Canvas apply;
- the cross-command rule that bare Canvas-mutating commands plan and `--apply`
  authorizes Canvas writes;
- a concise private-artifact warning;
- the command-family table; and
- pointers to `danvas guide`, `danvas describe`, and `danvas skill show`.

The root screen does not list a recipe for every feature. It teaches navigation
and the global safety vocabulary.

Illustrative content after Sprint 21, subject to exact released syntax:

```text
Start here:
  danvas auth doctor
  danvas init COURSE_ID --profile PROFILE --project-root .
  danvas refresh --diff
  danvas status

Safety:
  Bare Canvas-mutating commands produce a plan. --apply authorizes Canvas
  writes. Local sync commands may create missing files but never overwrite
  authored sources. Private student/course artifacts default beneath
  .danvas/private/ in an initialized project.

More guidance:
  danvas guide list
  danvas describe assignments create --format json
  danvas skill show
```

### Command-family help

Each command family receives a longer purpose statement and bounded common
workflows. A family screen should normally include:

- the supported jobs and important non-goals;
- two to four common command sequences;
- its identity-resolution policy when relevant;
- whether outputs or reports may be private;
- the family-specific plan/apply/verify contract;
- the normal relationship to adjacent families; and
- the existing subcommand table.

For example, the future assignments screen should teach separate inspection,
create, update, verify, and private-override paths:

```text
Common workflows:

  Inspect:
    danvas assignments export --output assignments.json

  Create from Markdown:
    danvas sources lint SOURCE
    danvas assignments create SOURCE
    danvas assignments create SOURCE --apply
    danvas assignments verify SOURCE

  Update:
    danvas assignments update SOURCE
    danvas assignments update SOURCE --apply
    danvas assignments verify SOURCE

Identity:
  Verify and update resolve explicit IDs, source front matter, or project
  provenance. They do not silently match by title.

Privacy and safety:
  Assignment override membership is private. Bare create/update commands plan;
  --apply authorizes Canvas writes.
```

Examples in the final implementation must be derived from the released 0.18.0
surface. They may not preserve legacy flag names merely because they appear in
the pre-public external reference.

### Leaf-command help

Every public leaf command declares its effect in plain language. Where
applicable, the full help includes:

- **Effect:** Canvas read, local write, Canvas plan, or Canvas write;
- **Privacy:** public metadata, course-sensitive, or private student data;
- **Resolution:** how course and target identity are selected;
- **Typical sequence:** the shortest safe command sequence;
- **Outputs:** stdout, explicit output, private default, report run, source map,
  or download tree;
- **Verification:** authoritative readback or other evidence retained after an
  apply; and
- **Failure boundary:** the safe next action after conflict, partial evidence,
  or indeterminate outcome.

Short, obvious read-only commands do not need boilerplate under every heading.
The renderer may omit sections that have no meaningful content, but the command
registry still records their effects.

### Presentation and capture behavior

Help must remain useful when captured by an agent rather than viewed in an
interactive terminal:

- do not rely on color, dim text, icons, or box position to convey safety;
- honor standard no-color behavior and provide clean output when stdout is not a
  TTY;
- choose a bounded content width so a 200-column terminal does not produce
  unreadable single-line prose;
- keep headings and code examples intact after ANSI stripping;
- avoid external hyperlinks as the only path to required usage information;
- use generic hosts, IDs, paths, profiles, and source names; and
- never inspect the environment, project, credential provider, or network while
  building help.

The command table continues to use concise one-line summaries. Longer prose and
examples use separate `help` and `epilog` values rather than making every parent
table row multi-paragraph.

## 2. Offline Task Guides

Default help cannot carry the entire command reference. Add a first-class,
offline guide surface:

```text
danvas guide list
danvas guide safety
danvas guide setup
danvas guide assignments
danvas guide grades
danvas guide local-sync
danvas guide privacy
danvas guide agents
```

The initial topic set should cover at least:

- setup, profiles, authentication diagnostics, and project initialization;
- snapshot refresh and local-vs-Canvas status;
- the global Canvas plan/apply/evidence contract;
- local-writing sync and no-clobber behavior;
- private artifacts, reports, exports, and downloads;
- authored assignment/content create-update-verify workflows;
- grades, feedback, discussion scoring, readback, and recovery;
- Files inventory/download/upload distinctions;
- Pages, announcements, and discussions at the family level;
- optional integrations and compatibility boundaries; and
- agent skill installation and discovery.

Guides are package resources rendered from or validated against the same command
metadata as help. They may contain more narrative and cross-command sequencing
than one leaf command can own. They must not contain raw maintainer notes,
historical Auburn behavior, private filesystem paths, or a copy of stale CLI
option tables.

`guide list` exposes stable topic names and one-line summaries. A missing topic
fails with close-match suggestions and the exact list command. Guide rendering
requires no project and performs no network or secret lookup.

The first release may emit plain terminal text only. A Markdown output option is
acceptable if it reuses the same source; HTML rendering, a documentation server,
and remote content fetching are out of scope.

## 3. Versioned Machine-Readable Discovery

### Public commands

Add:

```text
danvas describe
danvas describe assignments
danvas describe assignments create
danvas describe assignments create --format json
```

With no command path, `describe` returns the entire public command tree. With a
group or leaf path, it returns only that subtree or command. Text output is
concise and readable; JSON is the stable machine interface.

This is intentionally separate from Rich `--help`. Agents may still begin with
help, but automation never needs to parse terminal borders, wrapping, or ANSI
styles to learn the command contract.

### Schema

The initial JSON schema is named `danvas-command-guide-v1` and includes at least:

- `schema_version` and `danvas_version`;
- canonical `command_path`, aliases, summary, and long purpose;
- positional arguments and options, including required state, multiplicity,
  declared choices, safe defaults, and short descriptions;
- effect classification for Canvas reads, Canvas writes, local reads, local
  writes, notifications, and grade-affecting behavior;
- authentication, network, project, and profile requirements;
- privacy/output classification;
- plan/apply behavior and additional guards;
- identity-resolution behavior;
- default and optional outputs/evidence;
- meaningful exit statuses and recovery categories;
- common examples; and
- related commands and guide topics.

Sensitive or runtime-resolved values never appear. The schema describes
configuration sources generically; it does not emit the current API URL,
profile, course ID, token environment-variable contents, project paths, or
secret references.

### Determinism and compatibility

For the same danvas version, command-description JSON is byte-stable apart from
an explicitly documented final newline. Command, option, example, and related
command ordering are deterministic.

Adding a command or additive optional field may retain schema v1. Removing or
renaming a field, changing its type, or changing the meaning of an effect value
requires a new schema version. The installed CLI version is always included so
an agent or installed skill can detect a version mismatch.

The descriptor must derive arguments and options from the executable Typer/Click
command model rather than retype every signature in a second registry. Semantic
metadata augments that model. Tests fail when the executable and described
surface disagree.

## 4. Typed Command-Guide Registry

### Purpose

Introduce a dependency-light typed registry that records facts not represented
by a Typer option signature. Likely records and closed enums include equivalents
of:

- `CommandPath`;
- `CommandGuide`;
- `CommandEffects`;
- `CanvasAccess`;
- `LocalAccess`;
- `DataSensitivity`;
- `OutputContract`;
- `IdentityPolicy`;
- `MutationContract`;
- `CommandExample`; and
- `RecoveryCategory`.

Names may change, but the model must distinguish:

- Canvas read from Canvas write;
- local evidence/report writes from authored-source creation;
- a Canvas plan from an apply;
- a private output from shareable operational evidence;
- grade effects from other content mutations; and
- notification-producing commands from silent changes.

### Source-of-truth boundary

The sources of truth are ordered:

1. Typer command registration and function signatures own executable arguments,
   options, choices, and invocation;
2. the typed command-guide registry owns effects, safety, privacy, identity,
   examples, relationships, and recovery semantics; and
3. renderers produce root/group/leaf help, guides, JSON description, generated
   references, and skill resources.

No renderer owns unique command behavior. A manual guide may add explanatory
prose, but it must reference registry command paths and fail validation if they
do not exist.

### Coverage invariant

Every public leaf command and every public command group has exactly one guide
entry. Tests enumerate the actual Typer command tree and fail on:

- an executable command with no guide entry;
- a guide entry with no executable command;
- an example that names a missing command or option;
- a Canvas-writing command not classified as such;
- a private command not classified as private;
- a local-write command incorrectly described as a Canvas mutation;
- an `--apply` example on a command that cannot mutate Canvas; or
- a mutation example that omits the review/plan step without an explicit reason.

The registry should reuse the central private-command and mutation inventories
from Sprints 19-20 rather than establish competing lists.

### CLI architecture

The current `cli.py` is already large. Sprint 22 may extract help/guide/describe
registration and typed metadata into dependency-light modules. It is not a
license for a repository-wide CLI rewrite.

The design should prefer small registration helpers or a guided-command
decorator over hundreds of repeated literal fields, while preserving explicit
Typer function signatures for type checking and generated option behavior.

## 5. Generic Danvas Agent Skill

### Portable skill contract

Ship a repo-owned Agent Skill named `danvas` that follows the open Agent Skills
format. Its required front matter includes:

- `name: danvas`;
- a concise trigger description naming Canvas course operations and the danvas
  CLI;
- the project license or a reference to it;
- compatibility stating that the matching `danvas` executable must be on
  `PATH`; and
- string metadata identifying the danvas skill/CLI version and source.

The portable skill does not use host-specific invocation-control fields in its
standard front matter. It includes no `allowed-tools` grant. If a future plugin
adds host-specific metadata, that wrapper must not change the portable skill's
approval boundary.

### Skill responsibilities

The main `SKILL.md` teaches:

- when danvas is the appropriate interface;
- to check `danvas --version` and use installed help when exact syntax matters;
- to begin course-difference work with the released refresh/status sequence;
- to distinguish Canvas reads, local writes, plans, and applies;
- that Canvas writes require user authorization in addition to CLI syntax;
- how private artifacts and reports are handled;
- how to keep command output bounded and request JSON/file output when needed;
- how to use `danvas guide` and `danvas describe`; and
- that installed CLI help wins if an independently retained skill copy is
  stale.

It does not duplicate every command recipe. A generated, focused reference may
provide the command tree and common workflows for on-demand loading.

### Progressive disclosure and size

The skill follows the portable specification's loading model:

1. concise name and description for discovery;
2. a focused `SKILL.md`, below the recommended 500 lines and 5,000-token
   instruction budget; and
3. small referenced resources loaded only for a relevant family or task.

Do not replace the current monolithic external reference with one equally large
generated file if family-focused references provide a cleaner boundary. The
initial package may use:

```text
skills/danvas/
├── SKILL.md
└── references/
    ├── safety-and-outputs.md
    ├── authored-content.md
    ├── grades-and-submissions.md
    └── files-and-recordings.md
```

The exact split may change after token/render measurements. References remain
one level deep from `SKILL.md` and point agents back to the matching installed
help/describe commands for exhaustive option details.

### Generic boundary

The public skill and references contain no:

- Auburn host, institution name, or Central Time default;
- `/casa`, `/Volumes/Casa`, user-home, or external private repository path;
- maintainer-only secret name or 1Password vault convention;
- course-specific `AGENTS.md`, handoff, or transcript-filing policy;
- real course, assignment, file, discussion, quiz, or user ID;
- agent-sandbox escalation rule presented as universal behavior; or
- assumption that a particular agent host is installed.

Examples use the generic profile, source-layout, privacy, and mutation contracts
released by 0.18.0.

### Packaging

The canonical skill source lives in the public repository and the exact released
artifact is included in both sdist and wheel distributions. The build must not
maintain an unverified hand-copied package version. If a packaging copy step is
necessary, release tests compare every packaged byte and file hash with the
canonical source.

An editable checkout and an installed wheel expose the same `skill show` output.
The skill version matches `danvas --version`; a stale independently installed
copy is diagnosed rather than silently treated as current.

## 6. Skill Installation Contract

### Public command surface

Add:

```text
danvas skill show
danvas skill install --agent shared --scope user --dry-run
danvas skill install --agent shared --scope user
danvas skill install --agent claude-code --scope user
danvas skill install --agent gemini --scope project --project-root .
danvas skill doctor
```

`skill show` displays the bundled skill version, portable metadata, file tree,
supported targets, and canonical `SKILL.md` without writing. A bounded JSON form
may expose the same metadata for automation.

`skill install` performs one explicit local installation. The word `install` is
itself write intent; it does not use `--apply`, which remains reserved for Canvas
mutation. `--dry-run` previews local directory creation, file creation, update,
or refusal with exact target paths and no writes.

`skill doctor` inspects selected or discoverable danvas-owned installations,
compares version/provenance/hashes, verifies that `danvas` is on `PATH`, and
prints exact repair commands. It performs no network, agent login, Canvas, or
secret check.

### Initial targets

The initial design supports these explicit targets:

| Agent target | User scope | Project scope |
| --- | --- | --- |
| `shared` | `~/.agents/skills/danvas` | `.agents/skills/danvas` |
| `codex` | `~/.agents/skills/danvas` | `.agents/skills/danvas` |
| `claude-code` | `~/.claude/skills/danvas` | `.claude/skills/danvas` |
| `gemini` | `~/.gemini/skills/danvas` | `.gemini/skills/danvas` |
| `copilot` | `~/.copilot/skills/danvas` | `.github/skills/danvas` |

Every host path must be reverified against current primary documentation during
implementation because these conventions are evolving. `shared` deliberately
chooses the portable `.agents/skills` location currently understood by Codex,
Gemini CLI, and Copilot.

An explicit vendor target installs only to that vendor's path, even when the
host also supports the shared alias. This avoids making a Gemini-only request
implicitly affect Codex or Copilot. `shared` is the intentional multi-host
choice.

The first release requires `--agent`; it does not guess from installed binaries
or write to every discovered host. `--scope` defaults to `user`. Project scope
requires an explicit `--project-root` so the installer cannot guess which parent
repository should receive control instructions.

### No-clobber and provenance

The installer classifies the target before writing:

- `absent`: create the exact skill directory atomically;
- `exact`: report already installed and make no change;
- `owned_stale`: show the version/hash difference and permit a bounded update;
- `owned_modified`: refuse and explain which files differ;
- `unowned`: refuse because the target may belong to the user or another
  installer; or
- `unsafe`: refuse symlinks, non-directory parents, path escapes, or another
  containment problem.

The first release does not include a force-overwrite mode for `owned_modified`
or `unowned` targets. The operator may move or remove the conflicting directory
after inspecting it, then rerun installation. This keeps an agent from replacing
standing control instructions merely by adding a force flag.

Owned installations include bounded provenance and content hashes. Provenance
contains no username, home path, course path, host account, token, or secret
reference. An update builds a complete sibling temporary directory, validates
it, and swaps it only after every file is ready. Interruption preserves either
the old complete skill or the new complete skill, never a partially populated
directory.

The installer creates only the exact selected skill directory and missing
parents beneath the selected host's documented skills root. It never edits an
agent's global configuration file, trust settings, permissions, marketplace
catalog, shell profile, or executable path.

### Security boundary

Skills are control instructions and may contain scripts or tool grants. Treat
installation as security-sensitive even though the bundled danvas skill is
repo-owned:

- `skill show` and `install --dry-run` make all files inspectable;
- the portable skill contains no executable scripts in the first release;
- it contains no pre-approved shell or broad tool grant;
- installation requires an explicit host target;
- no remote URL is fetched;
- no third-party skill is accepted by this installer;
- no install happens as a side effect of `init`, package installation, help,
  guide, or doctor; and
- all targets remain confined to allowlisted agent-skill roots.

Generic third-party skill management remains the responsibility of native host
tools such as current Gemini or GitHub skill installers.

## 7. Personal Skill Migration

The external `teaching-danvas` skill remains private and separately maintained.
After Sprint 22 ships, a separately authorized update should reduce it to an
overlay that contains only:

- teaching-workspace discovery and context rules;
- course-local/private filing conventions;
- the maintainer's agent sandbox and escalation policy;
- Auburn-specific observed limitations that remain relevant to that workflow;
- transcript-placement policy; and
- instructions to use installed `danvas` help, guides, and describe output for
  public command syntax.

Before removing material from the external reference, compare every section
against the released CLI help/guides and retain any personal workflow rule that
does not belong in the public product.

The public release does not depend on this migration. No repository test reads
the user's personal skill directory, and `danvas skill install` never modifies
`teaching-danvas`.

## Compatibility And Migration

Sprint 22 is intended to preserve Canvas and course-project behavior.

- Existing command names, options, exit statuses, payloads, output schemas,
  reports, source maps, and mutation behavior remain unchanged unless a separate
  reviewed defect is discovered.
- `--help` output intentionally becomes longer and more structured. Exact
  whitespace, Rich borders, and prose were not a machine API before this sprint;
  `danvas describe --format json` becomes the supported structured discovery
  surface.
- Existing shell completions continue to use concise summaries rather than full
  guides.
- `danvas guide`, `describe`, and `skill show` are read-only and offline.
- `danvas skill install` is an explicit local write and never a Canvas mutation.
- No existing skill directory is replaced unless it is an unmodified,
  provenance-owned older danvas installation.
- The generic public skill is named `danvas`; it does not replace the personal
  `teaching-danvas` skill because the names and scopes differ.
- Skill schema/version metadata changes through an explicit migration test.

The 0.19.0 migration guide explains the richer help, new discovery commands,
supported skill targets, no-clobber behavior, version diagnostics, and the
relationship between public and personal skills.

## Implementation Sequence

### 1. Characterize the released interface

1. Capture the complete 0.18.0 Typer command tree, options, aliases, help output,
   completion summaries, and offline behavior.
2. Inventory current public documentation and the external skill/reference by
   command family and classify each paragraph as public command truth, public
   workflow guidance, or private maintainer policy.
3. Record root, representative group, and representative leaf help at bounded
   terminal widths with color enabled and disabled.
4. Freeze tests proving help construction performs no project, secret, or
   network resolution.

### 2. Establish the command-guide model

1. Reuse the Sprint 19 private-output and Sprint 20 access/mutation inventories.
2. Add typed guide/effect/privacy/identity/output records.
3. Enumerate every actual command/group and require exactly one semantic guide
   entry.
4. Add validation for command paths, options used by examples, effect
   contradictions, and missing safety metadata.

### 3. Render bounded default help

1. Separate short command-table summaries from long family/leaf descriptions.
2. Add root navigation and global safety guidance.
3. Add family workflows, identity, privacy, and mutation sections.
4. Add leaf effect/output/verification/recovery content where applicable.
5. Verify clean non-TTY/no-color output and bounded wrapping.

### 4. Add guides and machine description

1. Implement `guide list` and the bounded initial guide topics.
2. Implement text and deterministic `danvas-command-guide-v1` JSON description.
3. Derive executable arguments/options from Typer/Click and combine them with
   registry semantics.
4. Add schema fixtures and additive/breaking-change tests.

### 5. Package the generic skill

1. Write the portable, institution-neutral `SKILL.md` and focused references.
2. Generate or validate command paths and examples against the registry.
3. Validate the skill against the open Agent Skills specification.
4. Include the exact artifact in editable, sdist, and wheel builds.
5. Verify that `skill show` is byte-consistent inside and outside the source
   checkout.

### 6. Add the bounded installer

1. Implement explicit target/scope resolution and dry-run classification.
2. Add provenance, content hashing, atomic installation/update, and containment.
3. Implement `skill show` and offline `skill doctor` diagnostics.
4. Test every supported user/project target under isolated temporary homes and
   project roots.
5. Reverify current primary host documentation before freezing path behavior.

### 7. Review and release

1. Run an independent command-truth review comparing help, guides, JSON,
   executable behavior, and the skill.
2. Run an adversarial installer review for overwrite, symlink, traversal,
   partial-write, and untrusted-target cases.
3. Run bounded agent-behavior acceptance against fixture projects without live
   Canvas mutation.
4. Publish the 0.19.0 migration guide and complete normal release gates.
5. Update the external personal skill only through a separately authorized
   post-release change.

## Automated Acceptance

### Registry coverage

- Every actual public command group and leaf has exactly one guide entry.
- No guide entry, example command, referenced option, alias, or related command
  points to a missing executable surface.
- Every Canvas-writing command is classified as a Canvas write and documents
  plan/apply behavior.
- Every local-writing command is separately classified and does not misuse
  `--apply`.
- Every private-output command is present in the private inventory and described
  as private in help/JSON.
- Grade-affecting and notification-producing commands are explicitly marked.

### Help

- `danvas --help`, every family help screen, and every leaf help screen render
  successfully without a project, profile, token, secret provider, or network.
- Root help contains the start path, effect legend, plan/apply rule, privacy
  boundary, command table, and discovery pointers.
- Representative family help contains common workflows, identity, privacy, and
  effect guidance.
- Representative Canvas-write leaf help shows plan before apply and names its
  verification/evidence behavior.
- Representative local-write sync help clearly says it does not mutate Canvas
  and does not use `--apply`.
- ANSI-stripped TTY output and native non-TTY/no-color output preserve all
  safety text and command examples.
- Snapshot tests cover at least 80- and 120-column rendering without unbounded
  horizontal prose.
- No public help contains an Auburn host, maintainer path, real course/object ID,
  or private agent-workspace rule.

### Guides

- `guide list` deterministically lists every shipped topic.
- Every guide renders offline and every command/option it names passes registry
  validation.
- Unknown topics fail with suggestions and the exact list command.
- Guides contain the public portions of the retired external command-reference
  inventory without importing its personal portions.

### Machine description

- `danvas describe --format json` emits valid deterministic
  `danvas-command-guide-v1` covering the entire command tree.
- Describing a group or leaf returns only the requested subtree/command.
- Executable argument/option names, required state, choices, and safe defaults
  match the Typer/Click model.
- JSON contains effect, privacy, identity, output, plan/apply, exit, example, and
  related-command metadata where applicable.
- No resolved API URL, profile, course ID, token reference/value, absolute
  project path, or secret-provider result appears.
- A schema compatibility fixture distinguishes additive v1 changes from changes
  that require v2.

### Portable skill

- The skill passes the current open Agent Skills validator and the loaders or
  structural validators chosen for supported hosts.
- `name` matches its directory and all portable front matter satisfies the
  specification.
- The description has clear positive triggers and scope boundaries.
- The main instructions remain below 500 lines and the reviewed instruction
  token budget.
- All references are one level deep, focused, reachable, and named from
  `SKILL.md`.
- The skill contains no scripts, broad tool grants, institution defaults,
  maintainer paths, real IDs, or agent-specific approval bypass.
- Editable, sdist, and wheel installations expose byte-identical skill content
  and matching danvas/skill versions.

### Installer

- Dry-run writes nothing and prints the exact classification, target, file set,
  version, and action.
- User and project targets for each supported agent are confined to an isolated
  temporary home/project and match reverified host documentation.
- Project scope refuses to proceed without an explicit project root.
- Absent targets install atomically; exact targets are idempotent.
- Owned stale targets update only when existing files still match recorded
  provenance/hashes.
- Owned modified, unowned, symlinked, escaped, and otherwise unsafe targets are
  refused without alteration.
- Injected interruption at every write/swap boundary leaves the old complete
  version or new complete version, never a partial skill.
- `skill doctor` distinguishes missing, exact, stale, modified, unowned, and
  executable/version mismatch states and prints exact next commands.
- No installer path reads Canvas, resolves credentials, edits agent settings, or
  fetches remote content.

### Existing quality gates

- Ruff, ty, frozen lock validation, dependency audit, branch coverage, and all
  tests pass on every supported Python/OS lane established by 0.18.0.
- Existing architecture/complexity ratchets do not regress without independent
  review.
- Editable and wheel smoke pass from outside the repository.
- Local documentation-link validation and sprint-document Markdown lint pass.

## Bounded Agent Acceptance

Automated structural tests cannot prove that an agent will select the right
workflow from the skill and help. Before release, run a bounded evaluation using
fixture projects and mocked/no-network danvas commands.

The evaluation set includes prompts equivalent to:

1. determine what differs between local sources and Canvas;
2. prepare but do not apply an assignment update;
3. explain how to apply and verify an already reviewed change;
4. bring Canvas-only Pages or announcements into missing local source files;
5. export a roster or submissions without exposing it in a public path;
6. score a discussion and route the result through the grade plan/post workflow;
7. diagnose authentication without printing secrets;
8. inspect a large result without dumping the full payload into context;
9. distinguish a local report write from a Canvas mutation; and
10. respond safely to an indeterminate grade or upload result.

For each supported host selected for acceptance, record whether the agent:

- discovers or invokes the generic skill;
- calls help/guide/describe when syntax is uncertain;
- identifies the correct effect and private-output class;
- begins Canvas writes with a plan;
- does not treat local sync as Canvas mutation;
- requests user authorization before any apply; and
- keeps outputs bounded and gives the safe next action.

No evaluation performs a live Canvas mutation. A model invocation, marketplace
login, or external agent-host installation requires separate authorization and
is not implied by this design. If not every named host is available for the
release environment, structural path/loader coverage remains required and the
public support statement names which live agent behaviors were actually tested.

## Risks And Mitigations

### Help becomes too large

Long default output can consume the same agent context the skill is meant to
save. Keep root help navigational, group help workflow-oriented, leaf help
command-specific, and move exhaustive narratives into guides. Measure rendered
line and token counts in acceptance fixtures.

### Documentation drifts from behavior

Do not maintain independent option tables. Derive executable parameters from
Typer/Click, validate every example, centralize effects/privacy/identity, and
fail CI when registry and command tree disagree.

### Host conventions change

Keep the skill portable, isolate paths in a small installer target registry,
cite current primary documentation in developer comments/design evidence, and
reverify paths before each release that changes target behavior.

### Skill installation overwrites user control instructions

Require an explicit target, preview writes, track provenance/hashes, refuse
modified or unowned directories, omit force replacement, and install atomically.

### Agent-specific language leaks into the CLI

Help describes danvas facts, not Codex, Claude, Gemini, or Copilot policies.
Host-specific discovery and path logic stays in the installer; agent-specific
approval mechanics stay in each host or personal overlay.

### The skill becomes a duplicate manual

Keep the main skill procedural and small. Use the CLI's help, guide, and
description surfaces for command truth and generate/validate reference content
from the typed registry.

## Non-Goals

- Implementing the Page asset adapter or another Canvas feature;
- changing Canvas payloads, mutation order, readback, retry, or evidence schemas;
- changing the 0.18.0 profile, privacy, source-layout, or plan/apply contracts;
- building an MCP server, language server, daemon, chat UI, or autonomous agent;
- making agents a requirement for human use of danvas;
- adding an `--agent-help` flag instead of improving default help;
- emitting the entire command reference on every help screen;
- universal `--json` support for every existing command output;
- installing third-party skills or executing skill-bundled scripts;
- automatically detecting and modifying every installed agent host;
- editing agent trust, approval, permission, marketplace, or shell settings;
- publishing to an OpenAI, Anthropic, Gemini, GitHub, or other marketplace;
- shipping host-specific plugins, hooks, agents, MCP configuration, or UI assets;
- installing or modifying the external personal `teaching-danvas` skill;
- claiming deterministic model behavior from structural tests alone; or
- performing a live Canvas acceptance mutation.

## Resolved Design Decisions

- This is Sprint 22 / 0.19.0, after the four-release public-readiness program.
- Default help becomes more useful; there is no undiscoverable agent-only help
  mode.
- Root, group, leaf, guide, and JSON description form a progressive interface.
- `danvas describe --format json` is the supported machine command-discovery
  contract; Rich help is not parsed as an API.
- A typed registry owns effects, privacy, identity, workflows, and recovery
  semantics while Typer owns executable signatures.
- The public skill is a new generic `danvas` skill, not a published copy of the
  personal `teaching-danvas` skill.
- The first portable skill contains no scripts or `allowed-tools` grants.
- `danvas skill install` uses an embedded, version-matched artifact and fetches
  no remote content.
- Installation requires an explicit agent target and never silently installs to
  all discovered hosts.
- `--apply` remains reserved for Canvas mutation; skill installation uses its
  explicit verb plus an optional local-write dry-run.
- Modified and unowned skill targets are refused; the first release has no
  force-overwrite path.
- Native plugin/marketplace publication may follow but is not a 0.19.0 gate.

## Remaining Review Questions

1. What exact canonical repository path and build-backend inclusion mechanism
   should hold the portable skill without maintaining duplicate source copies?
2. Should `danvas guide` support Markdown output in 0.19.0 or remain terminal
   text only until there is a concrete consumer?
3. Which initial family guides should be separate topics rather than sections of
   broader authored-content and grading guides?
4. Should `skill doctor` require `--agent`, inspect all allowlisted locations, or
   do both with an explicit `--all` mode?
5. Should an unmodified provenance-owned stale skill update automatically when
   `skill install` is invoked, or require an additional `--update` spelling?
6. Which agent hosts receive actual model-behavior acceptance rather than only
   structural loader/path tests for the first release?
7. Should a later release publish the portable skill through native host tools
   or wrap it in full plugins only after user demand is demonstrated?

## Definition Of Done

- The released CLI is the authoritative public source for command syntax,
  effects, privacy, identity, outputs, and safe workflow sequencing.
- Root, family, and leaf help provide bounded useful guidance without network,
  credentials, a project, color, or an interactive terminal.
- Offline guides cover the common workflows removed from the personal command
  reference.
- `danvas-command-guide-v1` gives agents a deterministic structured command
  model that agrees with executable Typer behavior.
- Every public command is centrally classified and enforced by tests.
- A generic, spec-valid, institution-neutral `danvas` skill ships in editable,
  sdist, and wheel artifacts.
- Explicit dry-run/install/doctor workflows safely support the reviewed agent
  targets without clobbering user instructions or editing host configuration.
- Bounded agent acceptance demonstrates correct discovery, effect
  classification, privacy handling, plan/apply sequencing, and safe next actions
  on fixture workflows.
- Existing Canvas behavior and public evidence schemas remain unchanged.
- No agent host, marketplace, plugin, MCP server, Page asset adapter, live Canvas
  mutation, or external personal skill change has entered scope implicitly.

## Release Contract

The target is 0.19.0 after 0.18.0 has shipped and satisfied the public-beta
threshold. The release candidate must pass the complete supported Python/OS
matrix, independent command-truth review, adversarial installer review,
portable-skill validation, editable/sdist/wheel smoke, and bounded agent
acceptance before an exact tag is created.

Tag CI and anonymous exact-tag installation smoke must verify that:

- help, guide, and description work outside the repository;
- the wheel contains the exact reviewed skill;
- skill show/doctor remain offline;
- dry-run installation writes nothing; and
- a temporary-home install is atomic, confined, and discoverable at the
  documented target.

No push, tag, GitHub Release, package-registry publication, marketplace
submission, global CLI replacement, user/project skill installation, personal
skill edit, external agent invocation, or Canvas access/mutation is implied by
this design.
