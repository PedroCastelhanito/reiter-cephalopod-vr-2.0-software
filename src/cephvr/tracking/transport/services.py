"""Thin generated service bindings; admission is owned by Boundary."""

from __future__ import annotations

import grpc

from cephvr.control.v1 import (
    services_pb2 as wire,
)
from cephvr.control.v1 import (
    services_pb2_grpc as rpc,
)
from cephvr.control.v1 import (
    types_pb2 as pb,
)
from cephvr.tracking.v1 import (
    preparation_pb2,
)
from cephvr.tracking.v1 import (
    services_pb2 as tracking,
)
from cephvr.tracking.v1 import (
    services_pb2_grpc as tracking_rpc,
)

from .boundary import Boundary


class BackendService(rpc.BackendServiceServicer):
    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def ApplyIncidentScope(
        self, request: wire.IncidentScopeRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("ApplyIncidentScope", request, context)

    async def SetupSession(
        self, request: wire.SetupSessionRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("SetupSession", request, context)

    async def CancelSetup(
        self, request: wire.BackendCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("CancelSetup", request, context)

    async def PrepareTrial(
        self, request: wire.PrepareTrialRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("PrepareTrial", request, context)

    async def ScheduleTrial(
        self, request: wire.ScheduleTrialRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("ScheduleTrial", request, context)

    async def ReleaseTrial(
        self, request: wire.ReleaseTrialRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("ReleaseTrial", request, context)

    async def StopTrial(
        self, request: wire.StopTrialRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("StopTrial", request, context)

    async def AbortTrial(
        self, request: wire.StopTrialRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("AbortTrial", request, context)

    async def InterruptSession(
        self, request: wire.InterruptSessionRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("InterruptSession", request, context)

    async def Cleanup(
        self, request: wire.BackendCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("Cleanup", request, context)

    async def Shutdown(
        self, request: wire.BackendCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("Shutdown", request, context)

    async def GetState(
        self, request: wire.BackendQuery, context: grpc.aio.ServicerContext
    ) -> pb.ParticipantState:
        result = await self.boundary.query("GetState", request, context)
        assert isinstance(result, pb.ParticipantState)
        return result

    async def GetRetainedResult(
        self, request: wire.RetainedResultQuery, context: grpc.aio.ServicerContext
    ) -> wire.RetainedResult:
        result = await self.boundary.query("GetRetainedResult", request, context)
        assert isinstance(result, wire.RetainedResult)
        return result


class PreparationService(tracking_rpc.TrackingPreparationServiceServicer):
    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def BindData(
        self, request: tracking.TrackingDataBinding, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("BindData", request, context)

    async def GetPreparation(
        self,
        request: tracking.TrackingPreparationQuery,
        context: grpc.aio.ServicerContext,
    ) -> preparation_pb2.TrackingPreparationState:
        result = await self.boundary.query("GetPreparation", request, context)
        assert isinstance(result, preparation_pb2.TrackingPreparationState)
        return result
