"""Outbound loopback RPC and launcher notifications for the supervisor."""

from __future__ import annotations

import asyncio
import json
import os
from functools import partial
from typing import cast

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds
from cephvr.supervisor.worker_outbound import GrpcWorkerOutbound


class GrpcOutbound(GrpcWorkerOutbound):
    def __init__(
        self,
        identity: types.ProcessIdentity,
        token: str,
        controller_port: int,
        control_handle: int,
        max_message_bytes: int,
        backend_ports: dict[str, int],
    ) -> None:
        super().__init__(
            supervisor=identity, token=token, max_message_bytes=max_message_bytes
        )
        self.identity = identity
        self.controller_channel = grpc.aio.insecure_channel(
            f"127.0.0.1:{controller_port}", options=self.options
        )
        self.controller = services_pb2_grpc.ExperimentControllerServiceStub(
            self.controller_channel
        )  # type: ignore[no-untyped-call]
        self.backend_ports = backend_ports
        self.backend_channels: dict[str, grpc.aio.Channel] = {}
        self.control_handle = control_handle
        self.control_lock = asyncio.Lock()

    async def close(self) -> None:
        """Close every gRPC channel; idempotent."""
        channels = [self.controller_channel, *self.backend_channels.values()]
        self.backend_channels.clear()
        await asyncio.gather(
            super().close(),
            *(channel.close() for channel in channels),
            return_exceptions=True,
        )

    @staticmethod
    def _require_accepted(receipt: types.CommandAdmission, what: str) -> None:
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(f"{what}: {receipt.failure.code}")

    def _backend_call_options(self, deadline_ns: int) -> dict[str, object]:
        return {
            "metadata": (*self.metadata, deadline_metadata(deadline_ns)),
            "timeout": self._deadline_timeout(deadline_ns),
        }

    @staticmethod
    def _deadline_timeout(deadline_ns: int) -> float:
        timeout = remaining_seconds(deadline_ns)
        if timeout <= 0:
            raise TimeoutError("supervisor RPC deadline expired")
        return timeout

    async def report_interruption(self, report: wire.InterruptionReport) -> None:
        receipt = await self.controller.ReportInterruption(
            report, metadata=self.metadata, timeout=5
        )
        self._require_accepted(receipt, "controller rejected interruption")

    async def confirm_tracking_cleanup(
        self, request: wire.TrackingInputConfirmation, *, deadline_ns: int
    ) -> types.CommandAdmission:
        target = request.command.target
        channel = self._backend_channel(target.backend_name)
        stub = services_pb2_grpc.AcquisitionConfigurationServiceStub(channel)  # type: ignore[no-untyped-call]
        try:
            receipt = cast(
                types.CommandAdmission,
                await stub.ConfirmTrackingInput(
                    request, **self._backend_call_options(deadline_ns)
                ),
            )
        except grpc.aio.AioRpcError as exc:
            # The caller retries OSError until the original deadline.
            raise OSError(
                f"acquisition ConfirmTrackingInput failed: {exc.code().name}"
            ) from exc
        return receipt

    async def report_status(self, report: wire.SupervisorStatusReport) -> None:
        receipt = await self.controller.ReportSupervisorStatus(
            report, metadata=self.metadata, timeout=5
        )
        self._require_accepted(receipt, "controller rejected status")

    async def report_heartbeat(self, report: types.HeartbeatReport) -> None:
        receipt = await self.controller.ReportHeartbeat(
            report, metadata=self.metadata, timeout=5
        )
        self._require_accepted(receipt, "controller rejected supervisor heartbeat")

    def _backend(
        self, target: types.BackendContext
    ) -> services_pb2_grpc.BackendServiceStub:
        return services_pb2_grpc.BackendServiceStub(
            self._backend_channel(target.backend_name)
        )  # type: ignore[no-untyped-call]

    def _backend_channel(self, backend_name: str) -> grpc.aio.Channel:
        if backend_name not in self.backend_ports:
            raise RuntimeError(f"no declared backend endpoint for {backend_name}")
        channel = self.backend_channels.get(backend_name)
        if channel is None:
            channel = grpc.aio.insecure_channel(
                f"127.0.0.1:{self.backend_ports[backend_name]}",
                options=self.options,
            )
            self.backend_channels[backend_name] = channel
        return channel

    async def interrupt_backend(
        self,
        target: types.BackendContext,
        request: wire.InterruptSessionRequest,
        *,
        deadline_ns: int,
    ) -> None:
        receipt = await self._backend(target).InterruptSession(
            request, **self._backend_call_options(deadline_ns)
        )
        self._require_accepted(
            receipt, f"backend {target.backend_name} rejected interruption"
        )

    async def shutdown_backend(
        self,
        target: types.BackendContext,
        request: wire.BackendCommand,
        *,
        deadline_ns: int,
    ) -> None:
        receipt = await self._backend(target).Shutdown(
            request, **self._backend_call_options(deadline_ns)
        )
        self._require_accepted(
            receipt, f"backend {target.backend_name} rejected shutdown"
        )

    async def cleanup_backend(
        self,
        target: types.BackendContext,
        request: wire.BackendCommand,
        *,
        deadline_ns: int,
    ) -> None:
        receipt = await self._backend(target).Cleanup(
            request, **self._backend_call_options(deadline_ns)
        )
        self._require_accepted(
            receipt, f"backend {target.backend_name} rejected cleanup"
        )

    async def notify_launcher_shutdown(self, deadline_ns: int, cause: str) -> None:
        document = {
            "kind": "shutdown",
            "supervisor_generation": self.identity.generation,
            "deadline_monotonic_ns": deadline_ns,
            "cause": cause,
        }
        await self._notify(document)

    async def register_controller(
        self, controller: types.ProcessIdentity, pid: int, created: int
    ) -> None:
        await self._notify(
            {
                "kind": "register_controller",
                "supervisor_generation": self.identity.generation,
                "controller_generation": controller.generation,
                "pid": pid,
                "creation_time_100ns": created,
            }
        )

    async def register_gui_launch(
        self,
        child: types.ProcessIdentity,
        launch_command_id: str,
        pid: int,
        creation_time_100ns: int,
    ) -> None:
        """Give the persistent application owner exact initial GUI absence identity."""
        await self._notify(
            {
                "kind": "register_gui_launch",
                "supervisor_generation": self.identity.generation,
                "child_generation": child.generation,
                "launch_command_id": launch_command_id,
                "pid": pid,
                "creation_time_100ns": creation_time_100ns,
            }
        )

    async def _notify(self, document: dict[str, object]) -> None:
        encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > 8192:
            raise RuntimeError("launcher notification too large")
        async with self.control_lock:
            offset = 0
            while offset < len(encoded):
                written = await run_pipe_io_daemon(
                    partial(os.write, self.control_handle, encoded[offset:]),
                    timeout_s=5,
                )
                if written <= 0:
                    raise RuntimeError("launcher control pipe closed")
                offset += written
