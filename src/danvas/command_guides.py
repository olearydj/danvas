"""Typed semantic guidance layered over executable and policy registries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from danvas.access import ACCESS_POLICIES


class IdentityKind(StrEnum):
    NONE = "none"
    PROJECT = "project"
    PROFILE = "profile"
    CANVAS_ID = "canvas_id"
    CANVAS_URL = "canvas_url"
    SOURCE_PROVENANCE = "source_provenance"
    LOCAL_PATH = "local_path"
    REPORT_SELECTOR = "report_selector"


class ExampleStage(StrEnum):
    INSPECT = "inspect"
    PLAN = "plan"
    APPLY = "apply"
    VERIFY = "verify"
    LOCAL_WRITE = "local_write"


class RecoveryCategory(StrEnum):
    CORRECT_INPUT = "correct_input"
    INSPECT_EVIDENCE = "inspect_evidence"
    REFRESH_AND_REPLAN = "refresh_and_replan"
    DO_NOT_BLINDLY_RETRY = "do_not_blindly_retry"
    MOVE_ASIDE = "move_aside"


@dataclass(frozen=True)
class IdentityRule:
    kind: IdentityKind
    description: str


@dataclass(frozen=True)
class CommandExample:
    label: str
    argv: tuple[str, ...]
    stage: ExampleStage

    def __post_init__(self) -> None:
        if not self.argv or self.argv[0] != "danvas":
            raise ValueError(f"Guide example must begin with danvas: {self.argv!r}")


@dataclass(frozen=True)
class CommandWorkflow:
    title: str
    steps: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError(f"Guide workflow must have at least one step: {self.title}")
        if any(not step or step[0] != "danvas" for step in self.steps):
            raise ValueError(f"Guide workflow steps must begin with danvas: {self.title}")


@dataclass(frozen=True)
class ExitStatus:
    code: int
    meaning: str


@dataclass(frozen=True)
class CommandGuide:
    command: str
    purpose: str
    identities: tuple[IdentityRule, ...] = ()
    workflows: tuple[CommandWorkflow, ...] = ()
    examples: tuple[CommandExample, ...] = ()
    outputs: tuple[str, ...] = ()
    guards: tuple[str, ...] = ()
    exits: tuple[ExitStatus, ...] = ()
    recovery: tuple[RecoveryCategory, ...] = ()
    related_commands: tuple[str, ...] = ()
    guide_topics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.purpose.strip():
            raise ValueError(f"Guide purpose cannot be blank: {self.command or '<root>'}")


ROOT_GUIDE = CommandGuide(
    command="",
    purpose=(
        "Operate Canvas courses from a local project with explicit privacy, "
        "planning, verification, and recovery boundaries."
    ),
    workflows=(
        CommandWorkflow(
            "Start a course project",
            (
                ("danvas", "auth", "doctor"),
                ("danvas", "init", "12345", "--profile", "example"),
                ("danvas", "refresh", "--diff"),
                ("danvas", "status"),
            ),
        ),
    ),
    examples=(
        CommandExample("Inspect command families", ("danvas", "--help"), ExampleStage.INSPECT),
        CommandExample("List task guides", ("danvas", "guide", "list"), ExampleStage.INSPECT),
        CommandExample(
            "Describe a command",
            (
                "danvas",
                "describe",
                "assignments",
                "create",
                "--format",
                "json",
            ),
            ExampleStage.INSPECT,
        ),
        CommandExample(
            "Inspect the bundled skill",
            ("danvas", "skill", "show"),
            ExampleStage.INSPECT,
        ),
    ),
    outputs=("Command output is stdout-first unless a command declares retained artifacts.",),
    recovery=(RecoveryCategory.CORRECT_INPUT,),
    related_commands=(
        "auth doctor",
        "init",
        "refresh",
        "status",
        "guide",
        "describe",
        "skill show",
    ),
    guide_topics=("setup", "safety", "privacy", "agents"),
)


def _workflow(title: str, *steps: tuple[str, ...]) -> CommandWorkflow:
    return CommandWorkflow(title, tuple(("danvas", *step) for step in steps))


GROUP_GUIDES: tuple[CommandGuide, ...] = (
    CommandGuide(
        "assignments",
        "Inspect, create, update, verify, and audit assignments from stable Markdown sources.",
        identities=(
            IdentityRule(
                IdentityKind.SOURCE_PROVENANCE,
                "Uses explicit IDs, source front matter, or project provenance; update and verify do not silently title-match.",
            ),
        ),
        workflows=(
            _workflow(
                "Create",
                ("sources", "lint", "SOURCE"),
                ("assignments", "create", "SOURCE"),
                ("assignments", "create", "SOURCE", "--apply"),
                ("assignments", "verify", "SOURCE"),
            ),
            _workflow(
                "Update",
                ("assignments", "update", "SOURCE"),
                ("assignments", "update", "SOURCE", "--apply"),
                ("assignments", "verify", "SOURCE"),
            ),
        ),
        outputs=("Assignment evidence is course-internal; override membership is private.",),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.REFRESH_AND_REPLAN),
        related_commands=("sources lint", "files upload", "status"),
        guide_topics=("assignments", "safety"),
    ),
    CommandGuide(
        "auth",
        "Inspect neutral Canvas origin and credential transport without printing secrets.",
        identities=(
            IdentityRule(
                IdentityKind.PROFILE,
                "Resolves Canvas origin and credential selectors without exposing credential values.",
            ),
        ),
        workflows=(
            _workflow("Diagnose", ("auth", "doctor"), ("auth", "doctor", "--check-canvas")),
        ),
        recovery=(RecoveryCategory.CORRECT_INPUT,),
        related_commands=("init",),
        guide_topics=("setup", "agents"),
    ),
    CommandGuide(
        "gradebook",
        "Inspect local gradebook CSV structure and final-score setup without Canvas access.",
        identities=(
            IdentityRule(
                IdentityKind.LOCAL_PATH,
                "Uses the explicit gradebook CSV path and configured heading aliases.",
            ),
        ),
        workflows=(
            _workflow(
                "Check then audit",
                ("gradebook", "check", "GRADEBOOK.csv"),
                ("gradebook", "audit", "GRADEBOOK.csv"),
            ),
        ),
        recovery=(RecoveryCategory.CORRECT_INPUT,),
        related_commands=("grades verify",),
        guide_topics=("grades",),
    ),
    CommandGuide(
        "quiz",
        "Acquire and analyze Classic Quiz reports or plan and apply QTI imports.",
        identities=(
            IdentityRule(
                IdentityKind.LOCAL_PATH,
                "Exports use stable course/quiz/report/file IDs; local analysis uses an "
                "explicit CSV; import uses an explicit QTI package and project course.",
            ),
        ),
        workflows=(
            _workflow(
                "Export then analyze",
                ("quiz", "export-analysis", "--quiz-id", "123"),
                ("quiz", "export-analysis", "--quiz-id", "123", "--apply"),
                (
                    "quiz",
                    "analysis",
                    ".danvas/private/quizzes/quiz-123/student-analysis.csv",
                ),
            ),
            _workflow(
                "Import QTI",
                ("quiz", "import-qti", "PACKAGE.zip"),
                ("quiz", "import-qti", "PACKAGE.zip", "--apply"),
            ),
        ),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE,),
        related_commands=("reports list",),
        guide_topics=("content", "safety"),
    ),
    CommandGuide(
        "submissions",
        "Export private submission evidence, download media, and plan or apply feedback.",
        identities=(
            IdentityRule(
                IdentityKind.CANVAS_ID,
                "Uses assignment and Canvas user IDs; retained artifacts remain private.",
            ),
        ),
        workflows=(
            _workflow("Export", ("submissions", "export", "--assignment-id", "123")),
            _workflow(
                "Feedback",
                (
                    "submissions",
                    "feedback",
                    "--assignment-id",
                    "123",
                    "--roster",
                    "roster.csv",
                    "--feedback-dir",
                    "feedback",
                ),
                (
                    "submissions",
                    "feedback",
                    "--assignment-id",
                    "123",
                    "--roster",
                    "roster.csv",
                    "--feedback-dir",
                    "feedback",
                    "--apply",
                ),
            ),
        ),
        outputs=("Student-identifying outputs default beneath .danvas/private in a project.",),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.DO_NOT_BLINDLY_RETRY),
        related_commands=("roster", "grades verify"),
        guide_topics=("grades", "privacy"),
    ),
    CommandGuide(
        "grades",
        "Plan, apply, clear, inspect, and verify grades/comments with private evidence.",
        identities=(
            IdentityRule(
                IdentityKind.CANVAS_ID,
                "Uses an assignment ID plus stable Canvas user IDs from the CSV.",
            ),
        ),
        workflows=(
            _workflow(
                "Post and verify",
                ("grades", "post", "--assignment-id", "123", "--grades-csv", "grades.csv"),
                (
                    "grades",
                    "post",
                    "--assignment-id",
                    "123",
                    "--grades-csv",
                    "grades.csv",
                    "--apply",
                ),
                ("grades", "verify", "--assignment-id", "123", "--grades-csv", "grades.csv"),
            ),
        ),
        outputs=("Plans, rollback data, results, and readback evidence are private.",),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.DO_NOT_BLINDLY_RETRY),
        related_commands=("discussions score", "submissions grades"),
        guide_topics=("grades", "safety", "privacy"),
    ),
    CommandGuide(
        "discussions",
        "Create and maintain authored discussions, export posts, or prepare grade plans.",
        identities=(
            IdentityRule(
                IdentityKind.SOURCE_PROVENANCE,
                "Authored commands use explicit IDs, source front matter, or project provenance; exports and scoring accept a Canvas discussion URL.",
            ),
        ),
        workflows=(
            _workflow(
                "Create",
                ("discussions", "create", "SOURCE"),
                ("discussions", "create", "SOURCE", "--apply"),
                ("discussions", "verify", "SOURCE"),
            ),
            _workflow(
                "Score",
                ("discussions", "score", "DISCUSSION_URL", "1", "0.5", "2", "4"),
                ("grades", "post", "--assignment-id", "123", "--grades-csv", "PLAN.csv"),
            ),
        ),
        outputs=(
            "Post exports and grade plans are private; authored prompt sources are course-internal.",
        ),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.REFRESH_AND_REPLAN),
        related_commands=("grades post", "sources lint"),
        guide_topics=("content", "grades", "local-sync"),
    ),
    CommandGuide(
        "announcements",
        "Create, export, sync, update, and verify authored course announcements.",
        identities=(
            IdentityRule(
                IdentityKind.SOURCE_PROVENANCE,
                "Update and verify use explicit IDs, front matter, or project provenance; they do not title-match.",
            ),
        ),
        workflows=(
            _workflow(
                "Sync locally", ("announcements", "sync", "--dry-run"), ("announcements", "sync")
            ),
            _workflow(
                "Update",
                ("announcements", "update", "SOURCE"),
                ("announcements", "update", "SOURCE", "--apply"),
                ("announcements", "verify", "SOURCE"),
            ),
        ),
        outputs=("Exports that can include participant replies are private.",),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.REFRESH_AND_REPLAN),
        related_commands=("sources lint", "status"),
        guide_topics=("content", "local-sync"),
    ),
    CommandGuide(
        "pages",
        "Render, inspect, sync, create, update, and verify authored Canvas Pages.",
        identities=(
            IdentityRule(
                IdentityKind.SOURCE_PROVENANCE,
                "Update and verify use explicit IDs, front matter, or project provenance; they do not title-match.",
            ),
        ),
        workflows=(
            _workflow(
                "Check locally", ("pages", "render", "SOURCE"), ("pages", "css-check", "STYLE.css")
            ),
            _workflow(
                "Update",
                ("pages", "update", "SOURCE"),
                ("pages", "update", "SOURCE", "--apply"),
                ("pages", "verify", "SOURCE"),
            ),
        ),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.REFRESH_AND_REPLAN),
        related_commands=("sources lint", "status"),
        guide_topics=("content", "local-sync"),
    ),
    CommandGuide(
        "files",
        "Inventory, download, compare, and safely upload Canvas course Files.",
        identities=(
            IdentityRule(
                IdentityKind.CANVAS_ID,
                "Target files by stable Canvas file ID or exact Canvas path; uploads resolve an existing folder.",
            ),
        ),
        workflows=(
            _workflow(
                "Compare",
                ("files", "inventory"),
                ("files", "compare", "--file-id", "123", "--local", "FILE"),
            ),
            _workflow(
                "Upload", ("files", "upload", "FILE"), ("files", "upload", "FILE", "--apply")
            ),
        ),
        outputs=("Downloaded course files may be sensitive even when classified course-internal.",),
        recovery=(RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.DO_NOT_BLINDLY_RETRY),
        related_commands=("assignments verify",),
        guide_topics=("files", "privacy", "safety"),
    ),
    CommandGuide(
        "recordings",
        "Discover and download recording captions through configured course integrations.",
        identities=(
            IdentityRule(
                IdentityKind.CANVAS_ID,
                "Uses configured integration selectors and stable recording session IDs.",
            ),
        ),
        workflows=(
            _workflow(
                "Plan then download",
                ("recordings", "panopto-captions", "--dry-run"),
                ("recordings", "panopto-captions"),
            ),
        ),
        outputs=("Caption bundles are private and committed with a manifest marker.",),
        recovery=(RecoveryCategory.MOVE_ASIDE, RecoveryCategory.INSPECT_EVIDENCE),
        related_commands=("reports list",),
        guide_topics=("integrations", "privacy"),
    ),
    CommandGuide(
        "reports",
        "Discover and inspect retained danvas report runs without Canvas access.",
        identities=(
            IdentityRule(
                IdentityKind.REPORT_SELECTOR,
                "Selects report runs by storage scope, relative run directory, and optional slug.",
            ),
        ),
        workflows=(_workflow("Find evidence", ("reports", "list"), ("reports", "latest")),),
        recovery=(RecoveryCategory.CORRECT_INPUT,),
        guide_topics=("privacy", "safety"),
    ),
    CommandGuide(
        "sources",
        "Validate Canvas-facing authored sources locally before any Canvas plan.",
        identities=(
            IdentityRule(
                IdentityKind.LOCAL_PATH,
                "Uses configured project source layouts and contained local paths.",
            ),
        ),
        workflows=(_workflow("Lint before planning", ("sources", "lint"), ("status",)),),
        recovery=(RecoveryCategory.CORRECT_INPUT,),
        related_commands=("status", "assignments", "pages", "announcements", "discussions"),
        guide_topics=("assignments", "content", "local-sync"),
    ),
    CommandGuide(
        "skill",
        "Inspect, install, and diagnose the version-matched portable danvas Agent Skill.",
        identities=(
            IdentityRule(
                IdentityKind.NONE,
                "Uses the installed package resource and explicit allowlisted agent targets.",
            ),
        ),
        workflows=(
            _workflow("Inspect bundled content", ("skill", "show")),
            _workflow(
                "Preview and install",
                ("skill", "install", "--agent", "shared", "--dry-run"),
                ("skill", "install", "--agent", "shared"),
                ("skill", "doctor"),
            ),
        ),
        recovery=(RecoveryCategory.CORRECT_INPUT,),
        related_commands=("guide", "describe"),
        guide_topics=("agents",),
    ),
)


_LEAF_PURPOSES = {
    "guide": "Render a packaged offline task guide or list every available topic.",
    "describe": "Describe the public command tree as deterministic text or versioned JSON.",
    "skill show": "Show the bundled danvas Agent Skill and deterministic file hashes.",
    "skill install": "Install or update the bundled skill at one allowlisted agent location.",
    "skill doctor": "Inspect the executable and allowlisted user and project skill locations offline.",
    "init": "Create project configuration and an initial Canvas course snapshot.",
    "refresh": "Refresh the project course snapshot with explicit partial-evidence handling.",
    "status": "Compare the saved Canvas snapshot with configured local authored sources.",
    "courses": "Export active courses visible to the authenticated Canvas user.",
    "roster": "Export active enrollments using CanvasID and LoginID for private matching workflows.",
    "assignments export": "Export sanitized assignment evidence for review.",
    "assignments overrides": "Export one assignment's private override windows and membership.",
    "assignments overrides-sync": "Plan or apply assignment override reconciliation from a source file.",
    "assignments create": "Plan or create one assignment from Markdown with verified readback.",
    "assignments verify": "Verify declared assignment fields and exact current-course file targets.",
    "assignments update": "Plan or update one assignment resolved by stable identity.",
    "assignments upsert": "Plan create-versus-update and apply only with an action-specific confirmation.",
    "assignments audit": "Compare a saved assignment export with local course policy.",
    "auth doctor": "Diagnose Canvas origin binding and neutral credential delivery without exposing secrets.",
    "gradebook check": "Check a local gradebook CSV for recognized headings, variants, and missing cells.",
    "gradebook audit": "Audit final-score setup from a local gradebook and optional course evidence.",
    "quiz analysis": "Summarize a local Classic Quiz or Survey student-analysis CSV.",
    "quiz export-analysis": (
        "Plan or request Canvas's official identified Classic Quiz student-analysis report, "
        "then privately download and verify its CSV."
    ),
    "quiz import-qti": "Plan or apply a Classic Quiz QTI import and verify the created object.",
    "submissions export": "Export private submission metadata without downloading attachments.",
    "submissions grades": "Export private current-grade and submission-comment evidence.",
    "submissions media": "Download a protected attachment and media-comment bundle for one assignment.",
    "submissions feedback": "Plan or apply per-student feedback and classify authoritative readback.",
    "grades post": "Plan or post CSV grades/comments with rollback and private result evidence.",
    "grades clear": "Plan or clear targeted grades/comments with rollback and private result evidence.",
    "grades comments": "Inspect one submission's comments and current-user ownership.",
    "grades verify": "Verify CSV grades/comments and targeted release-state evidence.",
    "discussions export": "Export visible posts from one discussion to a private artifact.",
    "discussions create": "Plan or create an authored discussion with bounded seed handling.",
    "discussions verify": "Verify authored discussion metadata, body, and known seed entries.",
    "discussions update": "Plan or apply a bounded root-topic discussion update.",
    "discussions sync-prompts": "Plan or create missing local discussion prompt sources without overwriting.",
    "discussions score": "Score activity into a private CSV plan consumed by grades post.",
    "announcements create": "Plan or create one authored announcement.",
    "announcements export": "Export announcements and selected replies to a private artifact.",
    "announcements latest": "Export the latest announcement as course-internal Markdown or JSON.",
    "announcements sync": "Plan or create missing local announcement sources without overwriting.",
    "announcements update": "Plan or update one announcement resolved by stable identity.",
    "announcements verify": "Verify one local announcement source against Canvas by ID.",
    "pages list": "List Canvas Pages without retaining local output.",
    "pages export": "Export all Page metadata or one Page body to an explicit artifact.",
    "pages sync": "Plan or create missing local Page sources without overwriting.",
    "pages render": "Render one local Page source to Canvas-compatible HTML.",
    "pages css-check": "Validate restricted Canvas CSS and optionally show its inline plan.",
    "pages create": "Plan or create one Page and verify Canvas readback.",
    "pages update": "Plan or apply bounded Page body, publication, role, or schedule changes.",
    "pages verify": "Verify a rendered Page and publication state against Canvas.",
    "files inventory": "Write Canvas Files inventory and local comparison evidence.",
    "files download": "Download the Canvas Files tree with a retained manifest.",
    "files download-one": "Download exactly one Canvas file to an explicit destination.",
    "files compare": "Compare one Canvas file identity with a local file and retain evidence.",
    "files upload": "Plan or upload files with explicit duplicate policy and stable-ID evidence.",
    "recordings panopto-captions": "Plan or download caption bundles through the configured Panopto LTI tool.",
    "reports list": "List report runs across public and private project storage scopes.",
    "reports latest": "Show the newest valid report run, optionally filtered by slug.",
    "sources lint": "Lint configured authored sources locally without Canvas access.",
}


_BASE_EXAMPLES: Mapping[str, tuple[str, ...]] = {
    "guide": ("guide", "list"),
    "describe": ("describe", "assignments", "create", "--format", "json"),
    "skill show": ("skill", "show"),
    "skill install": ("skill", "install", "--agent", "shared", "--dry-run"),
    "skill doctor": ("skill", "doctor"),
    "init": ("init", "12345", "--profile", "example"),
    "refresh": ("refresh", "--diff"),
    "status": ("status",),
    "courses": ("courses",),
    "roster": ("roster",),
    "assignments export": ("assignments", "export"),
    "assignments overrides": ("assignments", "overrides", "--assignment-id", "123"),
    "assignments overrides-sync": ("assignments", "overrides-sync", "SOURCE"),
    "assignments create": ("assignments", "create", "SOURCE"),
    "assignments verify": ("assignments", "verify", "SOURCE"),
    "assignments update": ("assignments", "update", "SOURCE"),
    "assignments upsert": ("assignments", "upsert", "SOURCE"),
    "assignments audit": ("assignments", "audit", "assignments.json"),
    "auth doctor": ("auth", "doctor"),
    "gradebook check": ("gradebook", "check", "GRADEBOOK.csv"),
    "gradebook audit": ("gradebook", "audit", "GRADEBOOK.csv"),
    "quiz analysis": ("quiz", "analysis", "STUDENT_ANALYSIS.csv"),
    "quiz export-analysis": ("quiz", "export-analysis", "--quiz-id", "123"),
    "quiz import-qti": ("quiz", "import-qti", "PACKAGE.zip"),
    "submissions export": ("submissions", "export", "--assignment-id", "123"),
    "submissions grades": ("submissions", "grades", "--assignment-id", "123"),
    "submissions media": ("submissions", "media", "--assignment-id", "123"),
    "submissions feedback": (
        "submissions",
        "feedback",
        "--assignment-id",
        "123",
        "--roster",
        "roster.csv",
        "--feedback-dir",
        "feedback",
    ),
    "grades post": ("grades", "post", "--assignment-id", "123", "--grades-csv", "grades.csv"),
    "grades clear": ("grades", "clear", "--assignment-id", "123", "--grades-csv", "grades.csv"),
    "grades comments": ("grades", "comments", "--assignment-id", "123", "--canvas-id", "456"),
    "grades verify": ("grades", "verify", "--assignment-id", "123", "--grades-csv", "grades.csv"),
    "discussions export": ("discussions", "export", "DISCUSSION_URL"),
    "discussions create": ("discussions", "create", "SOURCE"),
    "discussions verify": ("discussions", "verify", "SOURCE"),
    "discussions update": ("discussions", "update", "SOURCE"),
    "discussions sync-prompts": ("discussions", "sync-prompts"),
    "discussions score": ("discussions", "score", "DISCUSSION_URL", "1", "0.5", "2", "4"),
    "announcements create": ("announcements", "create", "SOURCE"),
    "announcements export": ("announcements", "export"),
    "announcements latest": ("announcements", "latest"),
    "announcements sync": ("announcements", "sync"),
    "announcements update": ("announcements", "update", "SOURCE"),
    "announcements verify": ("announcements", "verify", "SOURCE"),
    "pages list": ("pages", "list"),
    "pages export": ("pages", "export", "--output", "pages.json"),
    "pages sync": ("pages", "sync"),
    "pages render": ("pages", "render", "SOURCE"),
    "pages css-check": ("pages", "css-check", "STYLE.css"),
    "pages create": ("pages", "create", "SOURCE"),
    "pages update": ("pages", "update", "SOURCE"),
    "pages verify": ("pages", "verify", "SOURCE"),
    "files inventory": ("files", "inventory"),
    "files download": ("files", "download"),
    "files download-one": ("files", "download-one", "--file-id", "123", "--output", "FILE"),
    "files compare": ("files", "compare", "--file-id", "123", "--local", "FILE"),
    "files upload": ("files", "upload", "FILE"),
    "recordings panopto-captions": ("recordings", "panopto-captions"),
    "reports list": ("reports", "list"),
    "reports latest": ("reports", "latest"),
    "sources lint": ("sources", "lint"),
}


_SOURCE_COMMANDS = {
    "assignments overrides-sync",
    "assignments create",
    "assignments verify",
    "assignments update",
    "assignments upsert",
    "discussions create",
    "discussions verify",
    "discussions update",
    "announcements create",
    "announcements update",
    "announcements verify",
    "pages create",
    "pages update",
    "pages verify",
}
_LOCAL_PATH_COMMANDS = {
    "assignments audit",
    "gradebook check",
    "gradebook audit",
    "quiz analysis",
    "pages render",
    "pages css-check",
    "sources lint",
}
_CANVAS_URL_COMMANDS = {"discussions export", "discussions score"}
_NO_IDENTITY_COMMANDS = {
    "guide",
    "describe",
    "skill show",
}
_CANVAS_ID_COMMANDS = {
    "assignments overrides",
    "quiz export-analysis",
    "submissions export",
    "submissions grades",
    "submissions media",
    "submissions feedback",
    "grades post",
    "grades clear",
    "grades comments",
    "grades verify",
    "files download-one",
    "files compare",
}
_NO_BLIND_RETRY = {
    "quiz export-analysis",
    "submissions feedback",
    "grades post",
    "grades clear",
    "files upload",
}
_LOCAL_SYNC = {
    "discussions sync-prompts",
    "announcements sync",
    "pages sync",
    "recordings panopto-captions",
}
_CONFIRM_GUARDS: Mapping[str, tuple[str, ...]] = {
    "assignments overrides-sync": ("--confirm", "apply"),
    "assignments upsert": ("--confirm", "update"),
}
_RELATED: Mapping[str, tuple[str, ...]] = {
    "guide": ("describe",),
    "describe": ("guide",),
    "skill show": ("guide", "describe"),
    "skill install": ("skill doctor", "skill show"),
    "skill doctor": ("skill install", "skill show"),
    "refresh": ("status",),
    "status": ("refresh", "sources lint"),
    "roster": ("submissions feedback", "grades post"),
    "assignments create": ("assignments verify",),
    "assignments update": ("assignments verify",),
    "assignments upsert": ("assignments verify",),
    "quiz export-analysis": ("quiz analysis", "reports list"),
    "quiz analysis": ("quiz export-analysis",),
    "submissions feedback": ("roster", "grades verify"),
    "grades post": ("grades verify",),
    "grades clear": ("grades verify",),
    "discussions score": ("grades post",),
    "announcements sync": ("announcements verify",),
    "pages sync": ("pages verify",),
    "files upload": ("files inventory", "files compare"),
    "recordings panopto-captions": ("reports list",),
}


def _identity_for(command: str) -> tuple[IdentityRule, ...]:
    if command == "skill install":
        return (
            IdentityRule(
                IdentityKind.LOCAL_PATH,
                "Resolves one explicit agent and scope to an allowlisted skill directory; "
                "project scope also requires an explicit project root.",
            ),
        )
    if command == "skill doctor":
        return (
            IdentityRule(
                IdentityKind.LOCAL_PATH,
                "Inspects only allowlisted user and explicit project skill locations for the "
                "selected agent set.",
            ),
        )
    if command in _NO_IDENTITY_COMMANDS:
        return (
            IdentityRule(
                IdentityKind.NONE,
                "Uses only the installed command model and packaged resources.",
            ),
        )
    if command in _SOURCE_COMMANDS:
        return (
            IdentityRule(
                IdentityKind.SOURCE_PROVENANCE,
                "Uses the explicit target ID, source front matter, or project source-map provenance.",
            ),
        )
    if command in _LOCAL_PATH_COMMANDS:
        return (
            IdentityRule(
                IdentityKind.LOCAL_PATH,
                "Uses explicit local paths contained by the selected project where required.",
            ),
        )
    if command in _CANVAS_URL_COMMANDS:
        return (
            IdentityRule(
                IdentityKind.CANVAS_URL,
                "Uses the explicit Canvas discussion URL and the configured course context.",
            ),
        )
    if command in _CANVAS_ID_COMMANDS:
        return (
            IdentityRule(
                IdentityKind.CANVAS_ID,
                "Uses explicit stable Canvas object or user IDs rather than display names.",
            ),
        )
    if command.startswith("reports "):
        return (
            IdentityRule(
                IdentityKind.REPORT_SELECTOR,
                "Uses storage scope, relative run directory, and optional report slug.",
            ),
        )
    if command == "auth doctor":
        return (
            IdentityRule(
                IdentityKind.PROFILE,
                "Uses explicit, project, profile, and environment origin/credential selection rules.",
            ),
        )
    if command == "courses":
        return (
            IdentityRule(
                IdentityKind.PROFILE,
                "Uses the selected Canvas instance without a course project requirement.",
            ),
        )
    return (
        IdentityRule(
            IdentityKind.PROJECT,
            "Uses the explicit course option or initialized project course context.",
        ),
    )


def _examples_for(command: str) -> tuple[CommandExample, ...]:
    policy = ACCESS_POLICIES[command]
    base = ("danvas", *_BASE_EXAMPLES[command])
    if command == "skill install":
        install = ("danvas", "skill", "install", "--agent", "shared")
        return (
            CommandExample(
                "Preview the bounded local write",
                (*install, "--dry-run"),
                ExampleStage.INSPECT,
            ),
            CommandExample("Install the reviewed skill", install, ExampleStage.LOCAL_WRITE),
        )
    if policy.canvas_mutation:
        apply = (*base, "--apply", *_CONFIRM_GUARDS.get(command, ()))
        return (
            CommandExample("Plan without changing Canvas", base, ExampleStage.PLAN),
            CommandExample("Apply the reviewed plan", apply, ExampleStage.APPLY),
        )
    if command in _LOCAL_SYNC:
        return (
            CommandExample("Preview local writes", (*base, "--dry-run"), ExampleStage.PLAN),
            CommandExample("Create missing local files", base, ExampleStage.LOCAL_WRITE),
        )
    if command == "discussions score":
        return (CommandExample("Write a private grade plan", base, ExampleStage.PLAN),)
    stage = ExampleStage.LOCAL_WRITE if command == "init" else ExampleStage.INSPECT
    return (CommandExample("Run the command", base, stage),)


def _recovery_for(command: str) -> tuple[RecoveryCategory, ...]:
    if command in _NO_BLIND_RETRY:
        return (RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.DO_NOT_BLINDLY_RETRY)
    if ACCESS_POLICIES[command].canvas_mutation:
        return (RecoveryCategory.INSPECT_EVIDENCE, RecoveryCategory.REFRESH_AND_REPLAN)
    if command in _LOCAL_SYNC:
        return (RecoveryCategory.CORRECT_INPUT, RecoveryCategory.MOVE_ASIDE)
    return (RecoveryCategory.CORRECT_INPUT,)


def _leaf_guides() -> tuple[CommandGuide, ...]:
    guides: list[CommandGuide] = []
    group_topics = {guide.command: guide.guide_topics for guide in GROUP_GUIDES}
    for command, purpose in _LEAF_PURPOSES.items():
        policy = ACCESS_POLICIES[command]
        guards: tuple[str, ...] = ()
        if policy.canvas_mutation:
            guards = ("Omission plans; --apply alone authorizes Canvas mutation.",)
            if command == "quiz export-analysis":
                guards += (
                    "Anonymous Surveys are refused before report creation.",
                    "A report request is a Canvas mutation even though quiz content and grades do not change.",
                )
            if command in _CONFIRM_GUARDS:
                guards += ("Apply also requires the command-specific --confirm value.",)
        elif command in _LOCAL_SYNC:
            guards = (
                "--dry-run previews local creation; omission may write locally but never mutates Canvas.",
            )
        guides.append(
            CommandGuide(
                command=command,
                purpose=purpose,
                identities=_identity_for(command),
                examples=_examples_for(command),
                outputs=(
                    (
                        "Verified private student-analysis CSV plus a SHA-256 artifact sidecar; "
                        "private plan/result report evidence when enabled."
                    ),
                )
                if command == "quiz export-analysis"
                else (),
                guards=guards,
                exits=(
                    ExitStatus(0, "Completed with the command's documented result."),
                    ExitStatus(2, "Invocation or preflight validation failed."),
                ),
                recovery=_recovery_for(command),
                related_commands=_RELATED.get(
                    command, (command.split()[0],) if " " in command else ()
                ),
                guide_topics=("agents",)
                if command in _NO_IDENTITY_COMMANDS
                else group_topics.get(command.split()[0], ("setup",)),
            )
        )
    return tuple(guides)


LEAF_GUIDES = _leaf_guides()
COMMAND_GUIDES: Mapping[str, CommandGuide] = {
    guide.command: guide for guide in (ROOT_GUIDE, *GROUP_GUIDES, *LEAF_GUIDES)
}


def command_guide(command: str) -> CommandGuide:
    try:
        return COMMAND_GUIDES[command]
    except KeyError as exc:
        raise ValueError(f"No command guide declared for: {command or '<root>'}") from exc
