import pytest


@pytest.fixture(autouse=True)
def _wide_cli_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render Typer/Rich --help at a fixed wide width.

    Typer's rich help is a width-dependent table. With no TTY (CI), Rich falls
    back to a narrow width and wraps long option flags across lines, breaking
    substring assertions like `"--match-title" in result.output`. Force a wide,
    deterministic console so help output is stable on every platform.
    """
    monkeypatch.setenv("COLUMNS", "200")
