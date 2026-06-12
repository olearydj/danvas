"""Unified operational Canvas tooling."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("danvas")
except PackageNotFoundError:  # running from a source tree without an installed package
    __version__ = "0+unknown"
