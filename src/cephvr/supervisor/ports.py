"""Supervisor outbound side-effect interface (E08)."""

from __future__ import annotations

from typing import Protocol

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


class SupervisorOutbound(Protocol):
    async def report_interruption(self, report: wire.InterruptionReport) -> None: ...
    async def report_status(self, report: wire.SupervisorStatusReport) -> None: ...
    async def interrupt_backend(
        self,
        target: types.BackendContext,
        request: wire.InterruptSessionRequest,
        *,
        deadline_ns: int,
    ) -> None: ...
    async def shutdown_backend(
        self,
        target: types.BackendContext,
        request: wire.BackendCommand,
        *,
        deadline_ns: int,
    ) -> None: ...
    async def cleanup_backend(
        self,
        target: types.BackendContext,
        request: wire.BackendCommand,
        *,
        deadline_ns: int,
    ) -> None: ...
    async def interrupt_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerInterrupt,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission: ...
    async def cleanup_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission: ...
    async def shutdown_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission: ...
    async def get_worker_state(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerState: ...
    async def get_worker_retained_result(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerRetainedResultQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerRetainedResult: ...
    async def interrupt_visual_stimulus_worker(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerStop,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission: ...
    async def cleanup_visual_stimulus_worker(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission: ...
    async def shutdown_visual_stimulus_worker(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission: ...
    async def get_visual_stimulus_worker_state(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerQuery,
        *,
        deadline_ns: int,
    ) -> visual_stimulus.WorkerState: ...
    async def confirm_tracking_cleanup(
        self, request: wire.TrackingInputConfirmation, *, deadline_ns: int
    ) -> types.CommandAdmission: ...
    async def notify_launcher_shutdown(self, deadline_ns: int, cause: str) -> None: ...
    async def report_heartbeat(self, report: types.HeartbeatReport) -> None: ...
    async def retire_worker_generation(self, role: str, generation: str) -> None: ...
    async def close(self) -> None: ...
