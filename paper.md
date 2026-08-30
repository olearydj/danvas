---
title: "danvas: Reproducible and Safety-Focused Canvas Course Operations"
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
date: 30 August 2026
bibliography: paper.bib
---

# Summary

`danvas` is an open-source command-line tool, built on the CanvasAPI Python
client, for instructors who manage course content, assessment, files, and
grades in Canvas. It consolidates repeated operations into project-based
workflows while keeping consequential changes subject to explicit review.
Canvas-changing commands produce a plan by default and require `--apply` before
mutation. The same workflows retain source bindings, readback results, and
recovery evidence, with separate handling for student-identifying artifacts.
`danvas` has been used in seven course workspaces across Summer and Fall 2026.
Version 0.21.1 is available under the MIT license from
[PyPI](https://pypi.org/project/danvas-cli/), with source and documentation on
[GitHub](https://github.com/olearydj/danvas).

# Statement of Need

Learning-management systems mediate recurring instructor work involving course
materials, assignments, communication, and assessment. Early analysis of
course-management work identified both the range of instructor tasks and their
time implications [@nijhuis2003coursemanagement]. A later study of Canvas logs
examined instructor and student interactions across more than 33,000 courses,
showing the scale at which these systems carry everyday teaching activity
[@lee2015canvasinteractions]. The current Canvas API exposes resources for
assignments, announcements, Pages, files, quizzes, submissions, and grades, and
allows external programs to modify them [@instructure2026canvasapi]. These
operations have different consequences, ranging from a stale announcement to an
unintended publication or grade change that is visible to students.

The Canvas API provides programmatic access, and CanvasAPI, which `danvas` uses,
exposes its resources as Python objects for managing courses, users, gradebooks,
and related data [@ucfopen2026canvasapi]. `danvas` retains a reusable local record
around the immediate API task by placing the instructor's source, reviewed
intent, and post-change evidence in one operational workflow. Its scope also
differs from systems centered on Jupyter assignment lifecycles
[@jupyter2019nbgrader], online mastery and assessment
[@west2015prairielearn], reusable source-based teaching materials
[@ro2019orgcoursepack], or automatic programming assessment
[@ihantola2010automaticassessment]. `danvas` operates across an existing Canvas
course and couples source-driven changes to planning, privacy, verification,
and recovery. The comparison locates `danvas` at the course-operations layer and
supports no claim of priority or superiority over adjacent tools.

# Software Design and Functionality

`danvas` organizes work around an initialized local course project. The project
records an institution-neutral Canvas profile, timezone, course identity, and
versioned source layout. Assignments, announcements, discussions, and Pages
remain ordinary Markdown or HTML files. A source map binds those files to stable
Canvas identities, allowing status, lint, create, update, verification, and sync
operations to use the same authored material without rewriting it.

Read-only commands audit course state, compare local sources with Canvas,
download permitted artifacts, and inspect gradebook or quiz data. Commands that
change Canvas follow a different contract: they plan by default, report the
target and intended effects, and require explicit `--apply` authorization.
Apply paths use expected-state checks and readback where the Canvas endpoint
supports them, while results distinguish planned, applied, verified, partial,
unverified, and indeterminate states. A partial or uncertain result stops later
writes and directs the operator to inspect retained evidence before retrying.
This preserves the difference between a failed request and a request that may
have succeeded but cannot yet be proved.

Student-identifying outputs default to a managed private root, making privacy
part of the operational workflow. On Linux and macOS, `danvas` creates private
directories with mode `0700` and files with mode `0600`, rejects
protected-boundary symlinks, and avoids overwriting existing evidence. These
controls define a local artifact boundary, while institutional rules still
govern access, retention, sharing, and disposal.

# Use in Teaching

The author used `danvas` across seven course workspaces during Summer and Fall
2026. The count requires durable source bindings or report history, so an eighth
initialized workspace without comparable evidence was excluded. Operational
use included course-state audits, local-to-Canvas comparisons, assignment and
announcement updates, Page creation, file handling, Classic Quiz imports,
gradebook checks, and grade-related workflows. The retained records include
successful operations as well as failures and detected mismatches.

This use exposed a practical distinction between completing a request and
knowing the resulting course state. Content and grade operations can encounter
partial application, unavailable readback, stale expected values, or a response
that confirms acceptance without confirming the final effect. `danvas` therefore
records mutation and evidence states separately and treats uncertain outcomes
as reconciliation work. The teaching record establishes maintainer use across
several course surfaces, but it does not establish independent adoption,
measured time savings, fewer errors, or improved student learning.

# Secondary Benefits

Deterministic JSON descriptions expose each command's effects, privacy class,
plan/apply contract, and recovery guidance. A version-matched portable Agent
Skill packages the same instructions for supervised software agents. Because
machine-readable guidance neither grants authorization nor makes model behavior
deterministic, agents use the same explicit mutation path as a human operator.

Retained evidence also supports later course revision: dated comparisons,
verification reports, and source checks record the inputs, software version,
and intermediate results, following reproducibility principles developed for
computational work [@sandve2013reproducible]. `danvas` applies those principles to
course operations rather than research analyses. Plans, stable identities,
request results, readback, and reconciliation preserve a time-bounded record of
what was intended, attempted, observed, and left uncertain. The record supports
human supervision and recovery, concerns that remain relevant even when routine
steps are automated [@bainbridge1983ironies]. Canvas remains the external system
of record, while `danvas` preserves bounded local evidence, not a permanent
course-history or student-data ledger.

# Adoption and Limitations

`danvas` 0.21.1 supports Python 3.12 through 3.14 on Linux and macOS. A new user
can install `danvas-cli` from PyPI, configure a Canvas origin and timezone,
initialize a course project, inspect offline guidance, and plan supported
operations before supplying mutation authorization. Live work still requires
institutional Canvas access, suitable permissions, locally managed credentials,
and an approved approach to private data.

Canvas deployments vary in endpoints, feature flags, permissions, and response
behavior, and the current gradebook profile is tested against English Canvas
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
