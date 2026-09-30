"""Narrow control operations needed by device workflows."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.state import Attempt


class Admission(Protocol):
    def __call__(
        self, command_id: str, *, error: str = "", code: str = "REJECTED"
    ) -> pb.CommandAdmission: ...


class Authorized(Protocol):
    def __call__(
        self,
        command: svc.OperatorCommand,
        *,
        safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
        targets_work: bool = False,
    ) -> str: ...


class Operation(Protocol):
    def __call__(
        self,
        command_id: str,
        name: str,
        *,
        attempt: Attempt | None = None,
        progress: str = "accepted",
        complete: bool = False,
        succeeded: bool | None = None,
        safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
    ) -> pb.OperationState: ...


class CompleteOperation(Protocol):
    def __call__(
        self,
        command_id: str,
        *,
        success: bool,
        progress: str,
        error: str = "",
    ) -> None: ...


@dataclass(frozen=True)
class DeviceHooks:
    admission: Admission
    authorized: Authorized
    operation: Operation
    complete_operation: CompleteOperation
    prune_operations: Callable[[], None]
    publish: Callable[[], None]
    spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]]
