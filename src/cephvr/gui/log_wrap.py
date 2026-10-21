"""Display-only hanging wraps for log rows; the unwrapped row is always recoverable.

A wrap replaces one space with a line separator plus padding to the message column,
so each entry stays one text block and unwrapping restores the exact row.
"""

LINE_SEPARATOR = " "


def wrap_marker(indent: int) -> str:
    return LINE_SEPARATOR + " " * indent


def unwrap_row(text: str, indent: int) -> str:
    return text.replace(wrap_marker(indent), " ") if indent else text


def wrap_row(row: str, columns: int, indent: int) -> str:
    """Break at spaces so continuation lines start at `indent`; long words stay."""
    if columns <= indent + 8 or len(row) <= columns:
        return row
    lines: list[str] = []
    rest = row
    while len(rest) > columns:
        # Never break inside the stamp/source prefix.
        cut = rest.rfind(" ", indent, columns + 1)
        if cut <= indent:
            break
        lines.append(rest[:cut])
        rest = " " * indent + rest[cut + 1 :]
    lines.append(rest)
    return LINE_SEPARATOR.join(lines)
