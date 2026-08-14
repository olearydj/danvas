"""Offline task guides assembled from package resources and command metadata."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from importlib.resources import files
from typing import Final

from danvas.command_guides import COMMAND_GUIDES, CommandGuide


@dataclass(frozen=True)
class GuideTopic:
    name: str
    summary: str
    resource: str
    command_paths: tuple[str, ...]


GUIDE_TOPICS: Final[tuple[GuideTopic, ...]] = (
    GuideTopic(
        "setup",
        "Configure authentication and initialize a project.",
        "setup.txt",
        ("auth", "init", "refresh"),
    ),
    GuideTopic(
        "status",
        "Refresh evidence and compare local sources with Canvas.",
        "status.txt",
        ("refresh", "status", "reports"),
    ),
    GuideTopic(
        "safety",
        "Plan, apply, verify, stop, and recover safely.",
        "safety.txt",
        ("", "assignments update", "grades post", "files upload"),
    ),
    GuideTopic(
        "local-sync",
        "Preview and create missing local sources without overwrite.",
        "local-sync.txt",
        ("pages sync", "announcements sync", "discussions sync-prompts"),
    ),
    GuideTopic(
        "privacy",
        "Classify and protect retained course and student artifacts.",
        "privacy.txt",
        ("submissions", "grades", "reports"),
    ),
    GuideTopic(
        "assignments",
        "Create, update, verify, and audit authored assignments.",
        "assignments.txt",
        ("assignments",),
    ),
    GuideTopic(
        "grades",
        "Use grades, feedback, discussion scoring, and recovery evidence.",
        "grades.txt",
        ("grades", "submissions", "discussions score"),
    ),
    GuideTopic(
        "files", "Distinguish inventory, download, compare, and upload.", "files.txt", ("files",)
    ),
    GuideTopic(
        "content",
        "Work with Pages, announcements, and discussions.",
        "content.txt",
        ("pages", "announcements", "discussions"),
    ),
    GuideTopic(
        "integrations",
        "Use optional integrations within tested compatibility bounds.",
        "integrations.txt",
        ("recordings", "auth doctor"),
    ),
    GuideTopic(
        "agents",
        "Discover commands and operate safely from an agent.",
        "agents.txt",
        ("guide", "describe"),
    ),
)
GUIDE_TOPIC_MAP: Final = {topic.name: topic for topic in GUIDE_TOPICS}


def _command_section(guide: CommandGuide) -> str:
    title = "danvas" if not guide.command else f"danvas {guide.command}"
    lines = [title, "-" * len(title), guide.purpose]
    for workflow in guide.workflows:
        lines.extend(("", f"{workflow.title}:"))
        lines.extend(f"  {' '.join(step)}" for step in workflow.steps)
    if not guide.workflows:
        lines.extend(("", "Examples:"))
        lines.extend(f"  {' '.join(example.argv)}" for example in guide.examples)
    return "\n".join(lines)


def guide_list_text() -> str:
    width = max(len(topic.name) for topic in GUIDE_TOPICS)
    lines = ["Offline danvas guides:"]
    lines.extend(f"  {topic.name:<{width}}  {topic.summary}" for topic in GUIDE_TOPICS)
    lines.extend(("", "Read one with: danvas guide TOPIC"))
    return "\n".join(lines) + "\n"


def render_guide(topic_name: str) -> str:
    if topic_name == "list":
        return guide_list_text()
    topic = GUIDE_TOPIC_MAP.get(topic_name)
    if topic is None:
        suggestions = get_close_matches(topic_name, GUIDE_TOPIC_MAP, n=3, cutoff=0.5)
        hint = f" Close matches: {', '.join(suggestions)}." if suggestions else ""
        raise ValueError(
            f"Unknown guide topic {topic_name!r}.{hint} Run 'danvas guide list' for every topic."
        )
    narrative = files("danvas._guides").joinpath(topic.resource).read_text(encoding="utf-8").strip()
    sections = [topic.name.replace("-", " ").title(), "=" * len(topic.name), narrative]
    sections.extend(_command_section(COMMAND_GUIDES[path]) for path in topic.command_paths)
    return "\n\n".join(sections) + "\n"
