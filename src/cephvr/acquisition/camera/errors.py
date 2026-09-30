"""Stable adapter-boundary failures for the lazy Basler SDK implementation."""

from __future__ import annotations


class CameraAdapterError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, field_path: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path
