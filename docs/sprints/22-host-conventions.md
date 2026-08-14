# Sprint 22 Agent Skill Convention Verification

Status: implementation evidence recorded 2026-08-14. These conventions remain
time-sensitive and must be checked again at the release gate.

## Portable format

The canonical package resource follows the open Agent Skills specification:

- one skill directory named `danvas` with `SKILL.md` at its root;
- required `name` and `description` fields;
- optional `license`, `compatibility`, and string-valued `metadata` fields;
- one-level relative links from `SKILL.md` into `references/`; and
- no `scripts/` directory or experimental `allowed-tools` grant.

Primary source: [Agent Skills specification](https://agentskills.io/specification).
The `skills-ref` validator was resolved from the official
[`agentskills/agentskills`](https://github.com/agentskills/agentskills)
repository at commit `69ef37e9424c0a7ea9dd2293b559e43ec8176379`. The
packaged skill passed:

```text
skills-ref validate src/danvas/_skill/danvas
Valid skill
```

The older locally bundled quick validator rejected the specification's current
`compatibility` field. The pinned authoritative validator and current published
specification therefore control this implementation decision.

## Discovery locations

The allowlist was compared with each host's current primary documentation:

- OpenAI Codex: user `$HOME/.agents/skills`; repository
  `$REPO_ROOT/.agents/skills`. Source: [Build skills](https://developers.openai.com/codex/skills).
- Claude Code: user `~/.claude/skills`; project `.claude/skills`. Source:
  [Extend Claude with skills](https://code.claude.com/docs/en/skills).
- Gemini CLI: user `~/.gemini/skills` or `~/.agents/skills`; workspace
  `.gemini/skills` or `.agents/skills`. Source:
  [Managing Agent Skills](https://geminicli.com/docs/cli/using-agent-skills/).
- GitHub Copilot: personal `~/.copilot/skills` or `~/.agents/skills`; project
  `.github/skills`, `.claude/skills`, or `.agents/skills`. Source:
  [About agent skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills).

The `shared` and `codex` targets intentionally resolve to the same portable
`.agents/skills` location. Vendor targets write only their named vendor path.
No target guesses from installed executables.

OpenAI's current documentation recommends plugins for broadly reusable skill
distribution. Sprint 22 deliberately ships only a bounded, local package-resource
installer; marketplace or plugin publication remains deferred. The installer
does not fetch third-party content or claim to replace a host's general skill
manager.

## Implementation consequence

`danvas skill install` requires an explicit agent, defaults to user scope, and
requires an explicit root for project scope. It classifies and atomically writes
only the `danvas` child beneath the allowlisted root. `danvas skill doctor` reads
all allowlisted locations by default and performs no agent login, network,
Canvas, or credential check.
