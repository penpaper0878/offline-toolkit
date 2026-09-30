"""Errors that carry a stable code and a message written for the user."""

from __future__ import annotations


class ToolkitError(Exception):
    """An expected failure. `message` is shown to the user as-is."""

    code = "error"

    def __init__(self, message: str, *, code: str | None = None, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class InputError(ToolkitError):
    code = "input"


class UnsupportedFormat(ToolkitError):
    code = "unsupported_format"


class Cancelled(ToolkitError):
    code = "cancelled"

    def __init__(self, message: str = "Cancelled"):
        super().__init__(message)
