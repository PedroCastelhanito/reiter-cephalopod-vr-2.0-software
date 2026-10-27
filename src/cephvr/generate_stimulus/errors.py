"""Concise validation messages that survive the worker boundary as plain text."""

import re

from pydantic import ValidationError

from .fields import SURFACE_NAMES, humanize, label_for

LOCATED = re.compile(r"^(\w+(?:\.\w+)*): (.+)$")


def describe_error(error: Exception) -> str:
    """One `path: message` line per pydantic issue; no URLs, inputs or type tags."""
    if not isinstance(error, ValidationError):
        return str(error)
    lines = []
    for item in error.errors():
        message = item["msg"].removeprefix("Value error, ")
        path = ".".join(str(part) for part in item["loc"])
        lines.append(f"{path}: {message}" if path else message)
    return "\n".join(lines)


def error_items(text: str) -> list[tuple[str, str]]:
    """Split described text into (field path, message); the path is empty if unknown."""
    result = []
    for line in filter(None, text.splitlines()):
        match = LOCATED.match(line)
        result.append((match[1], match[2]) if match else ("", line))
    return result


def status_line(text: str) -> str:
    """Single status-bar sentence naming the first offending field."""
    items = error_items(text)
    path, message = items[0] if items else ("", text)
    parts = path.split(".") if path else []
    surface = ""
    if parts[:1] == ["surfaces"] and len(parts) > 1:
        surface = SURFACE_NAMES.get(parts[1], humanize(parts[1]))
        parts = parts[2:]
    names = [surface, *(label_for(p) for p in parts[-1:] if not p.isdigit())]
    subject = " › ".join(name for name in names if name)
    more = f" (+{len(items) - 1} more)" if len(items) > 1 else ""
    return f"Preview not updated. {subject + ': ' if subject else ''}{message}{more}"
