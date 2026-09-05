"""Bounded external credential retrieval for trusted user profiles."""

from __future__ import annotations

import os
import re
import selectors
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

COMMAND_TIMEOUT_SECONDS = 60.0
MAX_DIAGNOSTIC_BYTES = 16 * 1024
MAX_CREDENTIAL_BYTES = 16 * 1024


class CredentialCommandError(ValueError):
    """Safe failure with no command, output, or provider details."""


def _failure(message: str) -> CredentialCommandError:
    return CredentialCommandError(message)


def read_command(argv: tuple[str, ...]) -> str:
    """Read one token without a shell, terminal input, or persisted output."""
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path.home(),
            start_new_session=True,
        )
    except OSError:
        raise _failure("Canvas credential command could not start.") from None
    try:
        content = _collect(process)
    except OSError:
        raise _failure("Canvas credential command output could not be read.") from None
    finally:
        # Descendants may hold pipe descriptors even after the helper exits.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
    try:
        value = content.decode("utf-8").removesuffix("\n").removesuffix("\r")
    except UnicodeError:
        raise _failure("Canvas credential command returned invalid text.") from None
    if (
        not value
        or re.match(r"[A-Za-z][A-Za-z0-9+.-]*://", value)
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _failure(
            "Canvas credential command must return one token, not a reference or whitespace."
        )
    return value


def _collect(process: subprocess.Popen[bytes]) -> bytes:
    output = bytearray()
    diagnostic_size = 0
    deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
    with selectors.DefaultSelector() as selector:
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _failure("Canvas credential command timed out.")
            for event, _ in selector.select(min(remaining, 0.1)):
                chunk = os.read(event.fd, 4096)
                if not chunk:
                    selector.unregister(event.fileobj)
                elif event.fileobj is process.stdout:
                    output.extend(chunk)
                    if len(output) > MAX_CREDENTIAL_BYTES:
                        raise _failure("Canvas credential command output is too large.")
                else:
                    diagnostic_size += len(chunk)
                    if diagnostic_size > MAX_DIAGNOSTIC_BYTES:
                        raise _failure("Canvas credential command diagnostics are too large.")
    try:
        code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        raise _failure("Canvas credential command timed out.") from None
    if code:
        raise _failure("Canvas credential command failed.")
    return bytes(output)
