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
date: 1 September 2026
bibliography: paper.bib
---

# Summary

`danvas` is an open-source command-line alternative to the Canvas web interface for recurring day-to-day instructor tasks involving content, assignments, files, quizzes, and grades. Built on the [CanvasAPI Python client](https://github.com/ucfopen/canvasapi), it organizes this work into local course projects that let instructors work from local files, review changes before applying them, and retain evidence of the resulting Canvas state. The same documented interface is designed for instructors and supervised software agents. Agent use does not itself authorize a course change. The author has used `danvas` across seven course projects during Summer and Fall 2026. Version 0.21.1 is available under the MIT license from [PyPI](https://pypi.org/project/danvas-cli/), with source and documentation on [GitHub](https://github.com/olearydj/danvas).

# Statement of Need

Instructors use learning-management systems throughout a term to publish course materials, revise assignments, communicate with students, manage assessments, and maintain grades. An evaluation of instructor work in a web-based course-management system documents the range of these tasks and their time implications [@nijhuis2003coursemanagement]. An analysis of Canvas activity across more than 33,000 courses illustrates the scale of this everyday teaching work [@lee2015canvasinteractions]. Consequences vary: an outdated announcement may cause confusion, while an unintended publication or grade change becomes visible to students.

The Canvas web interface supports this work directly. Applying a consistent edit across many assignments can require repeating the same form, while comparing a live course with locally authored material requires inspecting the two side by side. The web interface does not preserve the intended change and later observed state together as a local record. Canvas makes assignments, announcements, Pages, files, quizzes, submissions, and grades available to external programs through its API [@instructure2026canvasapi]. The CanvasAPI client represents those resources in Python [@ucfopen2026canvasapi]. `danvas` builds on that client to provide an instructor-facing command line. It groups supported operations into course projects that hold local teaching materials, planned changes, and results observed afterward.

Related educational software addresses adjacent parts of the workflow. nbgrader manages Jupyter assignment lifecycles [@jupyter2019nbgrader], and Org-Coursepack develops reusable teaching materials from source [@ro2019orgcoursepack]. Several command-line tools also work against Canvas directly, taking different approaches: `canvaslms` emphasizes POSIX composition for instructor workflows [@bosk2026canvaslms], while other projects expose broad API surfaces or agent-oriented command sets [@jjuanrivvera2026canvascli; @weng2026canvascli]. `danvas` focuses on a local course project. It binds supported local sources to Canvas objects, plans Canvas-changing commands by default, and retains local evidence about attempted changes.

# Instructor Workflows

An instructor begins with a local project for a Canvas course. Assignments, announcements, and discussions can remain ordinary Markdown files linked to their Canvas counterparts. Pages may use Markdown or native HTML. From the same project, the instructor can audit course state, compare local material with Canvas, create or revise content, download or upload files, import Classic Quizzes, and inspect gradebook or quiz data. This makes recurring work repeatable without making Canvas changes automatic.

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

The author developed `danvas` incrementally in response to course-administration needs encountered during Summer and Fall 2026. Its present scope covers recurring work in course preparation, content maintenance, assessment, and grade-related checks.

Teaching use also showed that a successful Canvas request does not always provide enough evidence to confirm the resulting course state. `danvas` therefore records the attempted change separately from the evidence available afterward and treats an uncertain result as work to inspect and reconcile rather than blindly retry. This teaching record establishes maintainer use across several parts of a course, but it does not establish independent adoption, measured time savings, fewer errors, or improved student learning.

# Secondary Benefits

For supervised agent-assisted administration, `danvas` provides machine-readable descriptions of what each command reads or changes, whether it handles private information, and how an uncertain result should be reviewed and recovered. A portable, version-matched Agent Skill packages these descriptions for supported agent hosts. The bundle does not grant permission or control model behavior. A supervised agent uses the same plan-then-apply interface as a human operator, but course changes still require operator authorization.

Retained evidence also supports later course revision. Dated comparisons, verification reports, and source checks record inputs, software versions, and intermediate results, following reproducibility principles developed for computational work [@sandve2013reproducible]. `danvas` applies those principles to course operations rather than research analyses. Its local record preserves time-bounded evidence of what was intended, attempted, observed, or left uncertain. By analogy with human-supervision concerns in industrial automation [@bainbridge1983ironies], these records support inspection and recovery when routine course operations are automated. Canvas remains the system of record. The local evidence is not a permanent course-history or student-data ledger.

# Adoption and Limitations

`danvas` is intended for instructors and course teams comfortable with a command line or working with technical support. Version 0.21.1 supports Python 3.12 through 3.14 on Linux and macOS. A new user can install `danvas-cli` from PyPI using `uv`, configure the institution's Canvas address and timezone, initialize a course project, read the guidance, and preview a supported operation before authorizing a change. Live work still requires institutional Canvas access, permissions, locally managed credentials, and an approved approach to private data.

Canvas deployments vary in endpoints, feature flags, permissions, and response behavior. The gradebook profile is tested against English Canvas headings, with explicit aliases available for known exports. Classic Quizzes are supported within documented limits. Version 0.21.1 does not support New Quizzes. Windows is excluded because `danvas` cannot enforce its POSIX private-file contract there. The software is an unofficial public beta and is neither affiliated with nor endorsed by Instructure.

# Acknowledgments

This work received no specific grant from any funding agency in the public,
commercial, or not-for-profit sectors. The author declares no competing
interests.

Generative AI tools supported the design, development, testing, and
documentation of `danvas`, as well as preparation of this manuscript. Danny J.
O'Leary determined the architecture, requirements, claims, and acceptance
criteria, reviewed proposed changes, and verified the software and manuscript.
The author accepts responsibility for the work.

# References
