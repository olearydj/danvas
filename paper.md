---
title: "danvas: Command-Line Course Operations for Canvas Instructors"
tags:
  - Python
  - Canvas LMS
  - learning management systems
  - course operations
  - educational software
authors:
  - name: "Danny J. O'Leary"
    orcid: "0009-0003-0501-1913"
    affiliation: 1
affiliations:
  - name: "Department of Industrial and Systems Engineering, Auburn University, Auburn, Alabama, United States"
    index: 1
date: 31 August 2026
bibliography: paper.bib
---

# Summary

`danvas` is an open-source command-line alternative to the Canvas web interface
for recurring day-to-day instructor tasks involving content, assignments,
files, quizzes, and grades. Built on the
[CanvasAPI Python client](https://github.com/ucfopen/canvasapi), it organizes
this work into local course projects that let instructors review changes before
applying them and retain evidence of the resulting Canvas state. Supervised
agentic systems are also first-class users of the documented interface, although
its guidance does not authorize course changes. The author has used `danvas` in
seven course workspaces across Summer and Fall 2026. Version 0.21.1 is available
under the MIT license from
[PyPI](https://pypi.org/project/danvas-cli/), with source and documentation on
[GitHub](https://github.com/olearydj/danvas).

# Statement of Need

Instructors use learning-management systems throughout a term to publish course
materials, revise assignments, communicate with students, manage assessments,
and maintain grades. Studies of course-management work document the range of
these tasks and their time implications [@nijhuis2003coursemanagement]. An
analysis of Canvas activity across more than 33,000 courses illustrates the
scale of this everyday teaching work [@lee2015canvasinteractions]. Consequences
vary: an outdated announcement may cause confusion, while an unintended
publication or grade change becomes visible to students.

The Canvas web interface supports this work directly. Repeating a change across
items or courses, comparing the online course with locally authored materials,
or preserving a reviewable account of a change can require a different
workflow. Canvas makes assignments, announcements, Pages, files, quizzes,
submissions, and grades available to external programs through its API
[@instructure2026canvasapi]. The CanvasAPI client represents those resources in
Python [@ucfopen2026canvasapi]. `danvas` builds on that client to provide an
instructor-facing command line. It groups supported operations into course
projects and keeps local teaching materials, planned changes, and the results
observed afterward together.

Related educational software covers other parts of the teaching workflow.
nbgrader manages Jupyter assignment lifecycles
[@jupyter2019nbgrader], PrairieLearn provides online mastery and assessment
[@west2015prairielearn], Org-Coursepack develops reusable teaching materials
from source [@ro2019orgcoursepack], and automatic-assessment systems evaluate
programming work [@ihantola2010automaticassessment]. `danvas` instead works
across an existing Canvas course. This comparison locates it at the
course-operations layer and supports no claim of priority or superiority over
adjacent tools.

# Instructor Workflows

An instructor begins with a local project for a Canvas course. Assignments,
announcements, discussions, and Pages can remain ordinary Markdown or HTML
files linked to their Canvas counterparts. From the same project, the
instructor can audit course state, compare local material with Canvas, create or
revise content, download or upload files, import Classic Quizzes, and inspect
gradebook or quiz data. This makes recurring work repeatable without making
Canvas changes automatic.

Before a command changes Canvas, `danvas` shows the target and intended effects.
The instructor must then provide `--apply` to authorize the reviewed operation.
Where Canvas supports the necessary checks, `danvas` compares the expected state
before writing and reads the result afterward. If a result is partial or cannot
be confirmed, the tool stops later writes and directs the operator to inspect
the retained evidence before retrying. A request that failed and a request that
may have succeeded but cannot yet be proved therefore remain distinct.

Downloads and reports that may identify students go to a private local
directory managed by `danvas`. On Linux and macOS, the tool restricts access,
refuses unsafe paths, and avoids overwriting existing evidence. These controls
provide a local privacy boundary. Institutional rules still govern access,
retention, sharing, and disposal.

# Use in Teaching

The author developed `danvas` for recurring Canvas work and used it across seven
course workspaces during Summer and Fall 2026. Operational use included
course-state audits, local-to-Canvas comparisons, assignment and announcement
updates, Page creation, file handling, Classic Quiz imports, gradebook checks,
and grade-related workflows.

This use exposed a practical distinction between sending a successful request
and knowing the resulting course state. A content or grade request may be
accepted even when the final effect cannot be confirmed. `danvas` therefore
records the attempted change separately from the evidence available afterward
and treats uncertain outcomes as work for the instructor to inspect and
reconcile. The teaching record establishes maintainer use across several course
surfaces, but it does not establish independent adoption, measured time savings,
fewer errors, or improved student learning.

# Secondary Benefits

Machine-readable descriptions state what each command can read or change,
whether it handles private information, how it must be reviewed, and how to
recover from an uncertain result. A portable, version-matched instruction
bundle, called an Agent Skill, packages this guidance for supervised agentic
systems. It grants no authorization and does not make model behavior
deterministic. Agents use the same explicit mutation path as human operators.

Retained evidence also supports later course revision. Dated comparisons,
verification reports, and source checks record inputs, software versions, and
intermediate results, following reproducibility principles developed for
computational work [@sandve2013reproducible]. `danvas` applies those principles
to course operations rather than research analyses. Its local record preserves
time-bounded evidence of what was intended, attempted, observed, or left
uncertain. This evidence supports human supervision and recovery, concerns that
remain relevant when routine steps are automated [@bainbridge1983ironies].
Canvas remains the system of record. The local evidence is not a permanent
course-history or student-data ledger.

# Adoption and Limitations

`danvas` is intended for instructors and course teams comfortable with a
command line or working with technical support. Version 0.21.1 supports Python
3.12 through 3.14 on Linux and macOS. A new user can install `danvas-cli` from
PyPI, configure the institution's Canvas address and timezone, initialize a
course project, read the guidance, and preview a supported operation
before authorizing a change. Live work still requires institutional Canvas
access, permissions, locally managed credentials, and an approved
approach to private data.

Canvas deployments vary in endpoints, feature flags, permissions, and response
behavior, and the gradebook profile is tested against English Canvas
headings, with explicit aliases available for known exports. Classic Quizzes are
supported within documented limits, New Quizzes are not supported, and Panopto
caption acquisition remains experimental and deployment-dependent. Windows is
excluded because `danvas` cannot enforce its POSIX private-file contract there.
The software is an unofficial public beta and is neither affiliated with nor
endorsed by Instructure.

# Acknowledgments

This work received no specific grant from any funding agency in the public,
commercial, or not-for-profit sectors. The author declares no competing
interests.

Claude Code assisted with `danvas` software development, review, testing, and
documentation. OpenAI Codex assisted with publication planning, manuscript
infrastructure, and manuscript preparation. Danny J. O'Leary determined the
architecture, requirements, claims, and acceptance criteria, reviewed proposed
changes, and verified the software and manuscript. The author accepts
responsibility for the work.

# References
