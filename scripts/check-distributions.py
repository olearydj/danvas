#!/usr/bin/env python3
"""Verify the public distribution identity and retained package contents."""

from __future__ import annotations

import argparse
import configparser
import re
import sys
import tarfile
import zipfile
from email.message import Message
from email.parser import Parser
from pathlib import Path, PurePosixPath

DIST_NAME = "danvas-cli"
MODULE_NAME = "danvas"
COMMAND_NAME = "danvas"
EXPECTED_REQUIRES_PYTHON = ">=3.12, <3.15"
REQUIRED_CLASSIFIERS = {
    "Development Status :: 4 - Beta",
    "Operating System :: MacOS",
    "Operating System :: POSIX",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
}
REQUIRED_PROJECT_URLS = {"Repository", "Issues", "Documentation", "Changelog"}
FORBIDDEN_REQUIREMENTS = {"python-dotenv", "secretpath"}


class DistributionError(ValueError):
    """Raised when a built distribution violates the public package contract."""


def safe_archive_names(names: list[str], *, label: str) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise DistributionError(f"{label} contains unsafe archive path: {name}")


def only_match(names: list[str], *, suffix: str, label: str) -> str:
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise DistributionError(
            f"{label} must contain exactly one {suffix}; found {len(matches)}"
        )
    return matches[0]


def parse_metadata(raw: bytes) -> Message:
    return Parser().parsestr(raw.decode("utf-8"))


def verify_metadata(metadata: Message, *, expected_version: str) -> None:
    expected_scalars = {
        "Name": DIST_NAME,
        "Version": expected_version,
        "License-Expression": "MIT",
        "Requires-Python": EXPECTED_REQUIRES_PYTHON,
        "Author": "Dan O'Leary",
        "Maintainer": "Dan O'Leary",
    }
    for key, expected in expected_scalars.items():
        observed = metadata.get(key)
        if observed != expected:
            raise DistributionError(f"METADATA {key} is {observed!r}; expected {expected!r}")

    classifiers = set(metadata.get_all("Classifier", []))
    missing_classifiers = sorted(REQUIRED_CLASSIFIERS - classifiers)
    if missing_classifiers:
        raise DistributionError(f"METADATA is missing classifiers: {missing_classifiers}")
    if any(value.startswith("License ::") for value in classifiers):
        raise DistributionError("METADATA must use SPDX License-Expression, not a license classifier")

    project_url_labels = {
        value.split(",", 1)[0].strip() for value in metadata.get_all("Project-URL", [])
    }
    if project_url_labels != REQUIRED_PROJECT_URLS:
        raise DistributionError(
            "METADATA Project-URL labels are "
            f"{sorted(project_url_labels)}; expected {sorted(REQUIRED_PROJECT_URLS)}"
        )

    requirements = {
        re.split(r"[\s\[<>=!~;]", value, maxsplit=1)[0].casefold()
        for value in metadata.get_all("Requires-Dist", [])
    }
    forbidden = sorted(requirements.intersection(FORBIDDEN_REQUIREMENTS))
    if forbidden:
        raise DistributionError(
            f"METADATA retains removed credential dependencies: {forbidden}"
        )


def verify_wheel(path: Path, *, expected_version: str) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        safe_archive_names(names, label="wheel")
        metadata_path = only_match(names, suffix=".dist-info/METADATA", label="wheel")
        dist_info = metadata_path.removesuffix("METADATA")
        verify_metadata(parse_metadata(archive.read(metadata_path)), expected_version=expected_version)

        required = {
            f"{MODULE_NAME}/__init__.py",
            f"{dist_info}licenses/LICENSE",
            f"{dist_info}entry_points.txt",
        }
        missing = sorted(required - set(names))
        if missing:
            raise DistributionError(f"wheel is missing required files: {missing}")

        entry_points = configparser.ConfigParser()
        entry_points.read_string(archive.read(f"{dist_info}entry_points.txt").decode("utf-8"))
        console_scripts = dict(entry_points.items("console_scripts"))
        expected_scripts = {COMMAND_NAME: f"{MODULE_NAME}.cli:main"}
        if console_scripts != expected_scripts:
            raise DistributionError(
                f"wheel console scripts are {console_scripts}; expected {expected_scripts}"
            )


def verify_sdist(path: Path, *, expected_version: str) -> None:
    with tarfile.open(path, mode="r:gz") as archive:
        names = archive.getnames()
        safe_archive_names(names, label="sdist")
        roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
        if len(roots) != 1:
            raise DistributionError(f"sdist must have one root directory; found {sorted(roots)}")
        root = next(iter(roots))
        expected_root = f"danvas_cli-{expected_version}"
        if root != expected_root:
            raise DistributionError(f"sdist root is {root!r}; expected {expected_root!r}")

        metadata_path = only_match(names, suffix="/PKG-INFO", label="sdist")
        member = archive.extractfile(metadata_path)
        if member is None:
            raise DistributionError("sdist PKG-INFO is unreadable")
        verify_metadata(parse_metadata(member.read()), expected_version=expected_version)

        required = {
            f"{root}/LICENSE",
            f"{root}/README.md",
            f"{root}/pyproject.toml",
            f"{root}/src/{MODULE_NAME}/__init__.py",
        }
        missing = sorted(required - set(names))
        if missing:
            raise DistributionError(f"sdist is missing required files: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()

    try:
        verify_wheel(args.wheel, expected_version=args.expected_version)
        verify_sdist(args.sdist, expected_version=args.expected_version)
    except (DistributionError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"distribution check failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"distribution check passed: {DIST_NAME} {args.expected_version} installs "
        f"the {MODULE_NAME} package and {COMMAND_NAME} command"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
