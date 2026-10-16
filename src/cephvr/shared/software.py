"""Installed CephVR distribution version reported by its owning process."""

from functools import cache
from importlib.metadata import PackageNotFoundError, version


@cache
def software_version() -> str:
    try:
        return version("cephvr")
    except PackageNotFoundError:
        return ""
