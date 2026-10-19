"""Read-only CAPS/STATUS and flash comparison after the owner's failed GUI verify."""

import hashlib
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import serial

from cephvr.controller.microcontroller.protocol import parse_reply, request_line


def hex_data(path):
    result = {}
    base = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = bytes.fromhex(line[1:])
        assert sum(record) % 256 == 0
        count, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
        if kind == 0:
            result.update(
                (base + address + index, value)
                for index, value in enumerate(record[4 : 4 + count])
            )
        elif kind in (2, 4):
            base = int.from_bytes(record[4:6], "big") << (4 if kind == 2 else 16)
    return result


folder = Path(__file__).resolve().parent
repo = folder.parents[2]
image = folder.parent / "camera-connect-continuity/avr-build/cephvr2_mcu.ino.hex"
backup = folder / "flash-before-avrdude8.hex"
expected, actual = hex_data(image), hex_data(backup)
mismatches = [address for address, value in expected.items() if actual.get(address) != value]
result = {
    "date": "2026-10-19",
    "timezone": "Asia/Tokyo",
    "base_revision": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip(),
    "source_tree_dirty": True,
    "port": "COM8",
    "method": "AVRDUDE8 read-only flash backup; compare every application-image address; CAPS/STATUS only",
    "application_bytes": len(expected),
    "mismatch_count": len(mismatches),
    "sha256": {
        str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (image, backup, repo / "firmware/uno/cephvr2_mcu/cephvr2_mcu.ino")
    },
    "replies": {},
    "limits": "No upload, CONFIGURE, ON, diagnostics or electrical/timing acceptance in this check. Original GUI upload command/complete output unavailable; screenshot documents failure.",
}
with serial.Serial("COM8", 115200, timeout=0.1, write_timeout=1) as port:
    time.sleep(2)
    port.reset_input_buffer()
    for command in ("CAPS", "STATUS"):
        request_id = str(uuid4())
        port.write(request_line(command, request_id))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            line = port.readline()
            if not line:
                continue
            reply = parse_reply(line)
            if reply.request_id == request_id:
                assert reply.ok
                result["replies"][command] = reply.fields
                break
        else:
            raise TimeoutError(command)
assert result["replies"]["CAPS"]["protocol"] == "5"
assert not mismatches
(folder / "board-check.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result["replies"], indent=2))
