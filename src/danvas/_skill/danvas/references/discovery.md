# Danvas Discovery

Use the installed interface as the current authority:

1. `danvas --help` explains navigation, effects, plan/apply, and privacy.
2. `danvas assignments --help` illustrates family workflows and identity rules.
3. `danvas assignments update --help` illustrates exact options, outputs,
   verification, and recovery boundaries for a leaf.
4. `danvas guide list` lists stable offline task topics.
5. `danvas describe assignments update --format json` emits the versioned
   `danvas-command-guide-v1` machine description.

The JSON description derives arguments/options from Click, effects from
`CommandAccessPolicy`, privacy from `ArtifactPolicy`, and workflow semantics from
the command-guide registry. It contains no current profile, course ID, origin,
credential value/reference, or absolute project path.

For a large result, describe only the relevant subtree or leaf. Do not scrape
Rich borders or dump the full command tree when a bounded query answers the
question.

If the installed command differs from this skill's `danvas-cli-version`
metadata, trust installed help and stop before mutation until compatibility is
understood.
