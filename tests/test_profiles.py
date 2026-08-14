from __future__ import annotations

from collections.abc import Iterator, Mapping
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


def test_project_instance_outranks_environment_when_profile_binds_same_origin(
    tmp_path: Path,
) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        """
[canvas]
profile = "institution-a"
api_url = "https://profile.canvas.example/"
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
    assert context.api_url == "https://profile.canvas.example/"
    assert context.api_url_source == ".danvas/config.toml"
    assert context.origin_binding_source == "profile 'institution-a'"
    assert context.secret_name == "canvas-institution-a"
    assert context.secret_provider == "env"
    assert context.api_key_env == "INSTITUTION_A_CANVAS_TOKEN"


def test_explicit_profile_mismatch_is_rejected(tmp_path: Path) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example/"\ncourse_id = 101\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Canvas origin conflict"):
        resolve_canvas_context(
            explicit_profile="institution-b",
            start=project,
            profiles_path=profiles_path,
            environ={},
        )


def test_project_selected_profile_mismatch_is_rejected(tmp_path: Path) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        """
[canvas]
profile = "institution-b"
api_url = "https://project.canvas.example/"
course_id = 101
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Canvas origin conflict"):
        resolve_canvas_context(
            start=project,
            profiles_path=profiles_path,
            environ={},
        )


def test_profile_selection_and_instance_precedence(tmp_path: Path) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)

    explicit = resolve_canvas_context(
        explicit_profile="institution-b",
        explicit_api_url="https://other.canvas.example/",
        profiles_path=profiles_path,
        environ={"DANVAS_PROFILE": "institution-a"},
    )
    selected_by_environment = resolve_canvas_context(
        profiles_path=profiles_path,
        environ={"DANVAS_PROFILE": "institution-b"},
    )

    assert explicit.profile == "institution-b"
    assert explicit.api_url == "https://other.canvas.example/"
    assert explicit.api_url_source == "--api-url"
    assert explicit.origin_binding_source == "profile 'institution-b'"
    assert explicit.profile_timezone == "America/New_York"
    assert explicit.secret_name == "canvas-institution-b"
    assert explicit.api_key_env == "CANVAS_API_KEY"
    assert selected_by_environment.profile == "institution-b"
    assert selected_by_environment.api_url == "https://other.canvas.example/"
    assert selected_by_environment.origin_binding_source == "profile 'institution-b'"


def test_environment_url_is_last_resort(tmp_path: Path) -> None:
    context = resolve_canvas_context(
        profiles_path=tmp_path / "missing.toml",
        environ={"CANVAS_API_URL": "https://shell.canvas.example/"},
    )

    assert context.api_url == "https://shell.canvas.example/"
    assert context.origin_binding_source == "CANVAS_API_URL"
    assert context.secret_name == "canvas"
    assert context.secret_provider == "auto"
    assert context.api_key_env == "CANVAS_API_KEY"


def test_matching_environment_url_binds_a_project_origin(tmp_path: Path) -> None:
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example/"\n',
        encoding="utf-8",
    )

    context = resolve_canvas_context(
        start=project,
        profiles_path=tmp_path / "missing.toml",
        environ={"CANVAS_API_URL": "https://project.canvas.example/"},
    )

    assert context.api_url_source == ".danvas/config.toml"
    assert context.origin_binding_source == "CANVAS_API_URL"


def test_origin_binding_normalizes_trailing_slash_host_case_and_default_port(
    tmp_path: Path,
) -> None:
    profiles_path = tmp_path / "user.toml"
    profiles_path.write_text(
        '[profiles.custom]\napi_url = "https://custom.example.edu"\n',
        encoding="utf-8",
    )

    context = resolve_canvas_context(
        explicit_profile="custom",
        explicit_api_url="https://CUSTOM.EXAMPLE.EDU:443/",
        profiles_path=profiles_path,
        environ={},
    )

    assert context.origin_binding_source == "profile 'custom'"


@pytest.mark.parametrize(
    "effective",
    [
        "https://other.example.edu/",
        "https://custom.example.edu:444/",
        "http://custom.example.edu/",
    ],
)
def test_origin_binding_rejects_host_port_and_scheme_changes(
    tmp_path: Path, effective: str
) -> None:
    profiles_path = tmp_path / "user.toml"
    profiles_path.write_text(
        '[profiles.custom]\napi_url = "https://custom.example.edu/"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        resolve_canvas_context(
            explicit_profile="custom",
            explicit_api_url=effective,
            profiles_path=profiles_path,
            environ={},
        )


def test_explicit_custom_canvas_domain_binds_without_hostname_assumption(tmp_path: Path) -> None:
    context = resolve_canvas_context(
        explicit_api_url="https://learning.example.org/",
        profiles_path=tmp_path / "missing.toml",
        environ={},
    )

    assert context.origin_binding_source == "--api-url"


@pytest.mark.parametrize("selector", ["environment", "default"])
def test_every_implicit_profile_selection_path_enforces_origin_match(
    tmp_path: Path, selector: str
) -> None:
    profiles_path = tmp_path / "user.toml"
    write_profiles(profiles_path)
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example/"\n',
        encoding="utf-8",
    )
    environment = {"DANVAS_PROFILE": "institution-a"} if selector == "environment" else {}

    with pytest.raises(SystemExit, match="Canvas origin conflict"):
        resolve_canvas_context(
            start=project,
            profiles_path=profiles_path,
            environ=environment,
        )


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


@pytest.mark.parametrize(
    "key",
    [
        "api_key_env",
        "api_key_file",
        "secret_name",
        "secret_provider",
        "op_reference",
        "credential_command",
        "token",
    ],
)
def test_course_project_cannot_select_credential_input(tmp_path: Path, key: str) -> None:
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        f'[canvas]\napi_url = "https://canvas.example/"\n{key} = "value"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=rf"\[canvas\]\.{key}"):
        resolve_canvas_context(
            explicit_api_url="https://canvas.example/",
            start=project,
            profiles_path=tmp_path / "missing.toml",
            environ={},
        )


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
    assert context.credential_input is None


def test_neutral_profile_file_is_selected_without_reading_it(tmp_path: Path) -> None:
    credential_path = tmp_path / "not-created-yet"
    profiles_path = tmp_path / "config.toml"
    profiles_path.write_text(
        (
            '[profiles.neutral]\napi_url = "https://canvas.example/"\n'
            f'api_key_file = "{credential_path}"\n'
        ),
        encoding="utf-8",
    )

    context = resolve_canvas_context(
        explicit_profile="neutral",
        profiles_path=profiles_path,
        environ={},
    )

    assert context.credential_input is not None
    assert context.credential_input.kind.value == "file"
    assert context.credential_input.locator == str(credential_path)


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ('api_key_env = "9INVALID"', "environment-variable name"),
        ('api_key_file = "relative/token"', "must be an absolute path"),
        (
            'api_key_env = "PROFILE_TOKEN"\napi_key_file = "/run/secrets/token"',
            "selects both",
        ),
        (
            'api_key_file = "/run/secrets/token"\nsecret_provider = "env"',
            "cannot combine",
        ),
    ],
)
def test_profile_credential_locators_are_validated(
    tmp_path: Path, settings: str, message: str
) -> None:
    profiles_path = tmp_path / "config.toml"
    profiles_path.write_text(
        f'[profiles.neutral]\napi_url = "https://canvas.example/"\n{settings}\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=message):
        load_user_profiles(profiles_path)


def test_explicit_neutral_environment_overrides_legacy_profile(tmp_path: Path) -> None:
    profiles_path = tmp_path / "config.toml"
    write_profiles(profiles_path)

    context = resolve_canvas_context(
        explicit_profile="institution-a",
        explicit_api_key_env="CLI_CANVAS_TOKEN",
        profiles_path=profiles_path,
        environ={"CANVAS_SECRET_PROVIDER": "1password"},
    )

    assert context.credential_input is not None
    assert context.credential_input.locator == "CLI_CANVAS_TOKEN"
    assert context.credential_input.selection_source.value == "cli"


def test_origin_failure_does_not_read_default_credential_value(tmp_path: Path) -> None:
    class NoCredentialReads(Mapping[str, str]):
        def __init__(self, values: dict[str, str]) -> None:
            self._items = values

        def __getitem__(self, key: str) -> str:
            if key == "CANVAS_API_KEY":
                raise AssertionError("credential value must not be inspected")
            return self._items[key]

        def __iter__(self) -> Iterator[str]:
            return iter(self._items)

        def __len__(self) -> int:
            return len(self._items)

    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example/"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="not bound to user intent"):
        resolve_canvas_context(
            start=project,
            profiles_path=tmp_path / "missing.toml",
            environ=NoCredentialReads({"CANVAS_API_KEY": "must-not-read"}),
        )


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
