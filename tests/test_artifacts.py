from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import danvas.artifacts as artifact_module
from danvas.artifacts import (
    ARTIFACT_POLICIES,
    ArtifactClass,
    commit_private_staged_pair,
    ensure_private_directory,
    private_staged_file,
    resolve_private_path,
    verify_private_sidecar,
    write_private_pair,
    write_private_text,
)


def write_config(root: Path) -> None:
    config_dir = root / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\napi_url = "https://canvas.example.edu/"\n',
        encoding="utf-8",
    )


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_private_creation_ignores_permissive_umask(tmp_path: Path) -> None:
    previous = os.umask(0)
    try:
        directory = ensure_private_directory(tmp_path / "private")
        path = write_private_text(directory / "artifact.txt", "private")
    finally:
        os.umask(previous)

    assert mode(directory) == 0o700
    assert mode(path) == 0o600


def test_private_staged_file_removes_partial_after_writer_failure(tmp_path: Path) -> None:
    partial = tmp_path / "artifact.part"

    with (
        pytest.raises(RuntimeError, match="injected failure"),
        private_staged_file(partial) as handle,
    ):
        handle.write(b"private prefix")
        raise RuntimeError("injected failure")

    assert not partial.exists()


def test_no_clobber_preserves_existing_private_file(tmp_path: Path) -> None:
    path = tmp_path / "artifact.txt"
    write_private_text(path, "first")

    with pytest.raises(FileExistsError):
        write_private_text(path, "second")

    assert path.read_text(encoding="utf-8") == "first"


def test_private_overwrite_replaces_atomically_with_private_mode(tmp_path: Path) -> None:
    path = tmp_path / "artifact.txt"
    write_private_text(path, "first")
    path.chmod(0o644)

    write_private_text(path, "second", overwrite=True)

    assert path.read_text(encoding="utf-8") == "second"
    assert mode(path) == 0o600


def test_explicit_private_file_does_not_chmod_existing_parent(tmp_path: Path) -> None:
    parent = tmp_path / "external"
    parent.mkdir(mode=0o755)

    path = write_private_text(parent / "artifact.txt", "private")

    assert mode(parent) == 0o755
    assert mode(path) == 0o600


def test_private_pair_has_integrity_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"

    _, sidecar = write_private_pair(path, b"CanvasID,Name\n1,Example\n", command="roster")

    assert verify_private_sidecar(path, sidecar)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["artifact_class"] == "private"
    assert payload["command"] == "roster"
    assert mode(path) == 0o600
    assert mode(sidecar) == 0o600


def test_private_pair_tampering_is_detectably_invalid(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    _, sidecar = write_private_pair(path, b"first", command="roster")

    write_private_text(path, "changed", overwrite=True)

    assert not verify_private_sidecar(path, sidecar)


def test_overwrite_interrupted_between_pair_commits_is_detectably_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "roster.csv"
    _, sidecar = write_private_pair(path, b"old", command="roster")
    staged = tmp_path / "roster.csv.part"
    with private_staged_file(staged) as handle:
        handle.write(b"new")
    original_commit = artifact_module._commit_staged
    calls = 0

    def interrupt_second_commit(temporary: Path, target: Path, *, overwrite: bool) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        original_commit(temporary, target, overwrite=overwrite)

    monkeypatch.setattr(artifact_module, "_commit_staged", interrupt_second_commit)

    with pytest.raises(KeyboardInterrupt):
        commit_private_staged_pair(
            staged,
            path,
            command="roster",
            overwrite=True,
            sidecar_path=sidecar,
        )

    assert path.read_bytes() == b"new"
    assert not verify_private_sidecar(path, sidecar)


def test_private_pair_refuses_preexisting_sidecar_without_writing_data(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    sidecar = tmp_path / "roster.csv.artifact.json"
    write_private_text(sidecar, "prior")

    with pytest.raises(FileExistsError):
        write_private_pair(path, b"new", command="roster")

    assert not path.exists()
    assert sidecar.read_text(encoding="utf-8") == "prior"


def test_staged_pair_collision_removes_only_owned_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_private_text(path, "prior")
    staged = tmp_path / "roster.csv.part"
    with private_staged_file(staged) as handle:
        handle.write(b"new")

    with pytest.raises(FileExistsError):
        commit_private_staged_pair(staged, path, command="roster")

    assert path.read_text(encoding="utf-8") == "prior"
    assert not staged.exists()


def test_private_writer_rejects_symlink_target(tmp_path: Path) -> None:
    actual = tmp_path / "actual.txt"
    actual.write_text("existing", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(actual)

    with pytest.raises(SystemExit, match="symlink"):
        write_private_text(link, "replacement", overwrite=True)

    assert actual.read_text(encoding="utf-8") == "existing"


def test_resolve_private_path_uses_project_default_without_creating_it(tmp_path: Path) -> None:
    write_config(tmp_path)

    resolved = resolve_private_path(
        explicit=None,
        project_root=tmp_path,
        default_relative="submissions/assignment-10/submissions.json",
        option_name="--output",
    )

    assert resolved.path == tmp_path / ".danvas/private/submissions/assignment-10/submissions.json"
    assert resolved.used_project_default is True
    assert not resolved.path.exists()


def test_resolve_private_path_requires_explicit_destination_without_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit, match="Pass --output"):
        resolve_private_path(
            explicit=None,
            project_root=tmp_path,
            default_relative="roster.csv",
            option_name="--output",
        )


def test_private_output_rejects_unsupported_platform_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "artifact.txt"
    monkeypatch.setattr(artifact_module.os, "name", "nt")

    with pytest.raises(SystemExit, match="supported only on POSIX"):
        write_private_text(target, "private")

    assert not target.exists()


def test_resolve_private_path_rejects_symlink_beneath_managed_root(tmp_path: Path) -> None:
    write_config(tmp_path)
    private_root = tmp_path / ".danvas/private"
    private_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (private_root / "submissions").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SystemExit, match="symlink"):
        resolve_private_path(
            explicit=None,
            project_root=tmp_path,
            default_relative="submissions/assignment-10/submissions.json",
            option_name="--output",
        )


def test_output_policy_inventory_names_reviewed_edge_cases() -> None:
    assert ARTIFACT_POLICIES["announcements latest"].artifact_class is ArtifactClass.COURSE_INTERNAL
    assert ARTIFACT_POLICIES["announcements export"].artifact_class is ArtifactClass.PRIVATE
    assert ARTIFACT_POLICIES["files download"].artifact_class is ArtifactClass.COURSE_INTERNAL
    assert ARTIFACT_POLICIES["recordings panopto-captions"].artifact_class is ArtifactClass.PRIVATE
