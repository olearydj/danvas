#!/usr/bin/env python3
"""Validate repository-local Markdown links and anchors without network access."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

PUBLIC_MARKDOWN = (
    "README.md",
    "docs/configuration.md",
    "docs/authentication.md",
    "docs/privacy.md",
    "docs/compatibility.md",
    "docs/authored-sources.md",
    "docs/mutation-safety.md",
    "docs/course-yaml.md",
    "docs/migrations/0.18.0.md",
    "docs/migrations/0.19.0.md",
    "docs/migrations/0.20.0.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)

INLINE_LINK_RE = re.compile(r"\[[^\]]*]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_LINK_TEXT_RE = re.compile(r"\[([^\]]+)]\([^)]+\)")
CODE_SPAN_RE = re.compile(r"`([^`]*)`")


def markdown_without_fenced_code(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        marker = stripped[:3]
        if fence is None and marker in {"```", "~~~"}:
            fence = marker
            continue
        if fence is not None:
            if marker == fence:
                fence = None
            continue
        lines.append((number, line))
    return lines


def heading_slug(text: str) -> str:
    text = HTML_TAG_RE.sub("", text)
    text = MARKDOWN_LINK_TEXT_RE.sub(r"\1", text)
    text = CODE_SPAN_RE.sub(r"\1", text)
    text = text.casefold().strip()
    kept = "".join(character for character in text if character.isalnum() or character in " _-")
    return re.sub(r"\s+", "-", kept)


def markdown_anchors(path: Path) -> set[str]:
    counts: Counter[str] = Counter()
    anchors: set[str] = set()
    for _number, line in markdown_without_fenced_code(path.read_text(encoding="utf-8")):
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = heading_slug(match.group(1))
        suffix = counts[base]
        counts[base] += 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def link_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def validate_markdown(root: Path, relative_source: str) -> list[str]:
    source = (root / relative_source).resolve()
    if not source.is_file():
        return [f"{relative_source}: missing public Markdown source"]

    errors: list[str] = []
    for line_number, line in markdown_without_fenced_code(source.read_text(encoding="utf-8")):
        for match in INLINE_LINK_RE.finditer(line):
            destination = link_destination(match.group(1))
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc:
                continue

            path_text = unquote(parsed.path)
            target = source if not path_text else (source.parent / path_text).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(
                    f"{relative_source}:{line_number}: local link escapes repository: "
                    f"{destination}"
                )
                continue
            if not target.is_file():
                errors.append(
                    f"{relative_source}:{line_number}: missing local link target: {destination}"
                )
                continue
            if parsed.fragment:
                if target.suffix.casefold() != ".md":
                    errors.append(
                        f"{relative_source}:{line_number}: anchor targets non-Markdown file: "
                        f"{destination}"
                    )
                    continue
                anchor = unquote(parsed.fragment).casefold()
                if anchor not in markdown_anchors(target):
                    errors.append(
                        f"{relative_source}:{line_number}: missing Markdown anchor: {destination}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to the script's parent repository).",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        default=list(PUBLIC_MARKDOWN),
        help="Root-relative Markdown sources to validate.",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    errors = [
        error
        for relative_source in args.files
        for error in validate_markdown(root, relative_source)
    ]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"documentation check passed: {len(args.files)} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
