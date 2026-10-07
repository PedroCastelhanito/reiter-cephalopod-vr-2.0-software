"""Explicit Uno image validation and the narrow upload-tool boundary (A11)."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cephvr.control.v1 import types_pb2 as control

if TYPE_CHECKING:
    from cephvr.controller.microcontroller.firmware_source import FirmwareSketch


@dataclass(frozen=True)
class FirmwareImage:
    path: Path
    payload: bytes
    digest: str


def read_uno_image(path: str, expected_digest: str = "") -> FirmwareImage:
    """Pin a compiled, checksummed Uno application image before touching serial."""
    source = Path(path)
    if not source.is_absolute() or source.suffix.lower() != ".hex":
        raise ValueError("Select an absolute path to a compiled Uno .hex file.")
    with source.open("rb") as stream:
        payload = stream.read(1_048_577)
    if not payload or len(payload) > 1_048_576:
        raise ValueError("Firmware image must be nonempty and no larger than 1 MiB.")
    digest = sha256(payload).hexdigest()
    if expected_digest and digest != expected_digest:
        raise ValueError("Firmware changed after selection; select the file again.")
    base = 0
    eof = False
    data_found = False
    written: set[int] = set()
    for line in payload.decode("ascii").splitlines():
        if not line.strip():
            continue
        if eof or not line.startswith(":"):
            raise ValueError("Invalid Intel HEX record or data after EOF.")
        record = bytes.fromhex(line[1:])
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) % 256:
            raise ValueError("Firmware Intel HEX length/checksum is invalid.")
        count, address, kind = record[0], int.from_bytes(record[1:3]), record[3]
        if kind == 0:
            if base + address + count > 32_256:
                raise ValueError("Firmware extends beyond the Uno application flash.")
            addresses = set(range(base + address, base + address + count))
            if written & addresses:
                raise ValueError("Firmware contains overlapping application records.")
            written.update(addresses)
            data_found |= count > 0
        elif kind == 1 and count == 0 and address == 0:
            eof = True
        elif kind in (2, 4) and count == 2 and address == 0:
            base = int.from_bytes(record[4:6]) << (4 if kind == 2 else 16)
        else:
            raise ValueError("Unsupported Uno Intel HEX record.")
    if not eof or not data_found:
        raise ValueError("Firmware needs application data and a terminal EOF record.")
    return FirmwareImage(source, payload, digest)


class FirmwareUploadPort(Protocol):
    """Own contained compile/upload tools, pinned inputs and confirmed cleanup."""

    @property
    def cleanup_complete(self) -> bool: ...

    def reset_cancel(self) -> None: ...

    def prepare(self, image: FirmwareImage) -> None: ...

    def compile(
        self,
        sketch: "FirmwareSketch",
        operation: control.OperationContext,
        *,
        deadline_ns: int,
    ) -> FirmwareImage: ...

    def upload(
        self, port: str, operation: control.OperationContext, *, deadline_ns: int
    ) -> None: ...

    def cancel(self) -> None: ...

    def close(self, *, deadline_ns: int) -> None: ...
