from __future__ import annotations

from pathlib import Path

import pytest

from danvas.profiles import load_user_profiles, resolve_canvas_context
from danvas.timezones import normalize_timezone


def write_profiles(path: Path) -> None:
    path.write_text(
        """
default_profile = "institution-a"

[profiles.institution-a]
api_url = "https://profile.canvas.example/"
timezone = "Central Time (US & Canada)"
secret_name = "canvas-institution-a"
secret_provider = "env"
api_key_env = "INSTITUTION_A_CANVAS_TOKEN"

[profiles.institution-b]
api_url = "https://other.canvas.example/"
timezone = "America/New_York"
secret_name = "canvas-institution-b"
""".lstrip(),
        encoding="utf-8",
    )


def test_load_user_profiles_normalizes_timezone(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_profiles(path)

    config = load_user_profiles(path)

    assert config.default_profile == "institution-a"
    assert config.profiles["institution-a"].timezone == "America/Chicago"


def test_project_instance_outranks_profile_and_environment(tmp_path: Path) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        """
[canvas]
profile = "institution-a"
api_url = "https://project.canvas.example/"
course_id = 101
""".lstrip(),
        encoding="utf-8",
    )

    context = resolve_canvas_context(
        start=project,
        profiles_path=profiles_path,
        environ={"CANVAS_API_URL": "https://shell.canvas.example/"},
    )

    assert context.profile == "institution-a"
    assert context.api_url == "https://project.canvas.example/"
    assert context.api_url_source == ".danvas/config.toml"
    assert context.secret_name == "canvas-institution-a"
    assert context.secret_provider == "env"
    assert context.api_key_env == "INSTITUTION_A_CANVAS_TOKEN"


def test_profile_selection_and_instance_precedence(tmp_path: Path) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)

    explicit = resolve_canvas_context(
        explicit_profile="institution-b",
        explicit_api_url="https://explicit.canvas.example/",
        profiles_path=profiles_path,
        environ={"DANVAS_PROFILE": "institution-a"},
    )
    selected_by_environment = resolve_canvas_context(
        profiles_path=profiles_path,
        environ={"DANVAS_PROFILE": "institution-b"},
    )

    assert explicit.profile == "institution-b"
    assert explicit.api_url == "https://explicit.canvas.example/"
    assert explicit.api_url_source == "--api-url"
    assert explicit.profile_timezone == "America/New_York"
    assert explicit.secret_name == "canvas-institution-b"
    assert explicit.api_key_env == "CANVAS_API_KEY"
    assert selected_by_environment.profile == "institution-b"
    assert selected_by_environment.api_url == "https://other.canvas.example/"


def test_environment_url_is_last_resort(tmp_path: Path) -> None:
    context = resolve_canvas_context(
        profiles_path=tmp_path / "missing.toml",
        environ={"CANVAS_API_URL": "https://shell.canvas.example/"},
    )

    assert context.api_url == "https://shell.canvas.example/"
    assert context.secret_name == "canvas"
    assert context.secret_provider == "auto"
    assert context.api_key_env == "CANVAS_API_KEY"


def test_missing_instance_fails_before_authentication(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Canvas API URL required"):
        resolve_canvas_context(
            profiles_path=tmp_path / "missing.toml",
            environ={"CANVAS_API_KEY": "must-not-matter"},
        )


def test_auth_doctor_can_resolve_context_without_instance(tmp_path: Path) -> None:
    context = resolve_canvas_context(
        profiles_path=tmp_path / "missing.toml",
        environ={},
        allow_missing_api_url=True,
    )

    assert context.api_url is None
    assert context.api_url_source is None


def test_profile_rejects_raw_secret_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[profiles.unsafe]\napi_url = "https://canvas.example/"\ntoken = "secret"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="cannot store secret values"):
        load_user_profiles(path)


def test_user_config_rejects_top_level_raw_secret_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('token = "secret"\n', encoding="utf-8")

    with pytest.raises(SystemExit, match="cannot store secret values"):
        load_user_profiles(path)


def test_explicit_secret_references_outrank_profile_and_environment(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_profiles(path)

    context = resolve_canvas_context(
        explicit_profile="institution-a",
        explicit_secret_name="explicit-canvas",
        explicit_secret_provider="1password",
        explicit_op_reference="op://Explicit/Canvas/credential",
        explicit_api_key_env="EXPLICIT_CANVAS_TOKEN",
        profiles_path=path,
        environ={
            "CANVAS_SECRET_PROVIDER": "auto",
            "CANVAS_API_KEY_OP_REFERENCE": "op://Environment/Canvas/credential",
            "CANVAS_API_KEY_ENV": "ENVIRONMENT_CANVAS_TOKEN",
        },
    )

    assert context.secret_name == "explicit-canvas"
    assert context.secret_provider == "1password"
    assert context.op_reference == "op://Explicit/Canvas/credential"
    assert context.api_key_env == "EXPLICIT_CANVAS_TOKEN"


def test_unknown_profile_is_actionable(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_profiles(path)

    with pytest.raises(SystemExit, match="not defined"):
        resolve_canvas_context(
            explicit_profile="missing",
            profiles_path=path,
            environ={},
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Central Time (US & Canada)", "America/Chicago"),
        ("America/New_York", "America/New_York"),
        ("Not A Real Zone", None),
        (None, None),
    ],
)
def test_normalize_timezone(value: str | None, expected: str | None) -> None:
    assert normalize_timezone(value) == expected
