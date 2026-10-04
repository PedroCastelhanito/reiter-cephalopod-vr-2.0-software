"""Read trigger hints from a PFS text snapshot without applying camera settings."""

import re
from pathlib import Path


def trigger_hint(path: str) -> tuple[str, str]:
    with Path(path).open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("PFS exceeds the 1 MiB preview limit")
    text = raw.decode("utf-8-sig")
    if "GenApi persistence file" not in text:
        raise ValueError("Not a recognized GenApi PFS snapshot")
    selector = ""
    values: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "TriggerSelector" and len(parts) == 2:
            selector = parts[1]
        elif parts[0] in ("TriggerMode", "TriggerSource") and len(parts) >= 2:
            match = re.search(r"TriggerSelector=([^}\s]+)", line)
            target = match.group(1) if match else selector
            if target == "FrameStart":
                value = parts[-1]
                if parts[0] in values and values[parts[0]] != value:
                    raise ValueError("Ambiguous FrameStart trigger values")
                values[parts[0]] = value
    mode, source = values.get("TriggerMode"), values.get("TriggerSource", "")
    if mode == "Off":
        return "Internal clock", source
    if mode == "On" and re.fullmatch(r"Line\d+", source):
        return "External controller", source
    raise ValueError("FrameStart trigger mode/source is missing or unsupported")
