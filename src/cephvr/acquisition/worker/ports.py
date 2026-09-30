"""Request access and focused operations at the private worker boundary."""

from __future__ import annotations

from typing import Protocol

from cephvr.acquisition.v1 import messages_pb2 as acq


class WorkerOperationTicket(Protocol):
    """Reserved queue slot; commit is nonblocking and wakes the capture owner."""

    def commit(self) -> None: ...

    def cancel(self) -> None: ...


class WorkerOperationOwner(Protocol):
    """Serialize camera, capture and lifecycle effects on the camera owner thread."""

    def reserve(
        self,
        operation: str,
        request: object,
        deadline_ns: int,
    ) -> WorkerOperationTicket: ...


def command_from(request: object) -> acq.WorkerCommand:
    """Require the shared command envelope before worker operation dispatch."""
    command = getattr(request, "command", None)
    if not isinstance(command, acq.WorkerCommand):
        raise TypeError("worker operation has no WorkerCommand")
    return command
