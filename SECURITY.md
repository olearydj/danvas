# Security Policy

Danvas handles Canvas credentials, course configuration, grades, submissions,
comments, rosters, and protected artifacts. Please report suspected security or
privacy vulnerabilities privately.

## Supported Releases

Security fixes target the latest signed `0.18.x` public-beta release only.

| Version | Supported |
| --- | --- |
| Latest signed `0.18.x` | Yes |
| `0.17.x` and earlier | No |
| Unreleased branches and commits | No release-support guarantee |

Upgrade to the latest signed patch release before assuming a reported issue is
still present. A source checkout that has not completed the signed-tag release
gates is a candidate, not a supported release.

## Report A Vulnerability Privately

Use GitHub's
[private vulnerability-reporting form](https://github.com/olearydj/danvas/security/advisories/new).
The report is delivered through the repository security-advisory workflow and
is not a public issue.

Do not report a vulnerability in a public issue, pull request, discussion,
commit message, or copied terminal transcript.

Include, when available:

- the affected signed danvas version;
- operating system and Python version;
- the affected command and whether it was plan, apply, or local-write mode;
- the security or privacy impact;
- minimal reproduction steps using synthetic data;
- whether Canvas, Panopto, the local filesystem, or retained evidence is
  involved;
- any known mitigation; and
- sanitized logs that contain no tokens, student information, protected URLs,
  or private artifact contents.

If a live token may have been exposed, revoke or rotate it immediately through
Canvas and follow institutional incident-response policy. Do not wait for the
software report to be triaged before containing credential exposure.

## What Happens Next

Maintainers will triage the private report, request additional bounded evidence
when necessary, and coordinate remediation and disclosure through the private
advisory. Acceptance of a report does not automatically publish it.

Response timing depends on maintainer availability and the report's severity;
this beta does not promise a fixed security-response service level. Reporters
should avoid public disclosure while reasonable private coordination is active.

## Scope Notes

Relevant reports include, but are not limited to:

- credential disclosure or resolution against the wrong Canvas instance;
- private artifacts created with unsafe permissions or outside their declared
  boundary;
- symlink, traversal, overwrite, or temporary-file boundary failures;
- student-identifying data in terminal output, manifests, sidecars, or
  course-internal output;
- a Canvas mutation occurring without explicit `--apply` authorization;
- unsafe retry behavior after an uncertain remote outcome; and
- retained protected URLs, verifier values, launch state, or raw API payloads.

Canvas or Panopto availability, institutional permissions, unsupported Windows
behavior, and ordinary feature requests are not vulnerabilities by themselves.
Use a public issue for non-sensitive defects only after removing private course
and credential information.
