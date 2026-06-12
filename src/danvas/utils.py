"""Shared utility helpers."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def clean_filename(name: object, limit: int = 100) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name))
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned[:limit] or "untitled"


def canvas_object_to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return {str(k): normalize_json(v) for k, v in obj.items()}
    out: dict[str, Any] = {}
    for key, value in getattr(obj, "__dict__", {}).items():
        if key.startswith("_") or callable(value):
            continue
        out[key] = normalize_json(value)
    return out


def normalize_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    return str(value)


def html_to_text(html: str | None) -> str:
    parser = TextExtractor()
    parser.feed(html or "")
    return parser.text()


def slugify(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or fallback


def write_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def print_mutation_banner(action: str, fields: dict[str, Any]) -> None:
    """Consistent preamble before any live Canvas write."""
    print(f"== Canvas write: {action} ==")
    for name, value in fields.items():
        print(f"  {name}: {value}")
