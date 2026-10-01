"""Explicit generated-service adapters; all admission remains at Boundary."""

from __future__ import annotations

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import services_pb2_grpc as visual_stimulus_rpc

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


class ConfigurationService(rpc.VisualStimulusConfigurationServiceServicer):
    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def InitializeDisplay(
        self,
        request: wire.VisualStimulusDisplayInitializationRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.CommandAdmission:
        return await self.boundary.command("InitializeDisplay", request, context)


class WorkerService(visual_stimulus_rpc.VisualStimulusWorkerServiceServicer):
    async def ConfirmRecipePublication(
        self,
        request: visual_stimulus.WorkerRecipePublication,
        context: grpc.aio.ServicerContext,
    ) -> pb.CommandAdmission:
        return await self.boundary.command("ConfirmRecipePublication", request, context)

    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def InitializeDisplay(
        self,
        request: visual_stimulus.InitializeDisplay,
        context: grpc.aio.ServicerContext,
    ) -> pb.CommandAdmission:
        return await self.boundary.command("InitializeDisplay", request, context)

    async def SetupSession(
        self, request: visual_stimulus.WorkerSetup, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("SetupSession", request, context)

    async def CancelSetup(
        self, request: visual_stimulus.WorkerCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("CancelSetup", request, context)

    async def PrepareTrial(
        self,
        request: visual_stimulus.WorkerPrepareTrial,
        context: grpc.aio.ServicerContext,
    ) -> pb.CommandAdmission:
        return await self.boundary.command("PrepareTrial", request, context)

    async def ScheduleTrial(
        self, request: visual_stimulus.WorkerSchedule, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("ScheduleTrial", request, context)

    async def ReleaseTrial(
        self, request: visual_stimulus.WorkerRelease, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("ReleaseTrial", request, context)

    async def StopTrial(
        self, request: visual_stimulus.WorkerStop, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("StopTrial", request, context)

    async def InterruptSession(
        self, request: visual_stimulus.WorkerStop, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("InterruptSession", request, context)

    async def Cleanup(
        self, request: visual_stimulus.WorkerCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("Cleanup", request, context)

    async def Shutdown(
        self, request: visual_stimulus.WorkerCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        return await self.boundary.command("Shutdown", request, context)

    async def GetState(
        self, request: visual_stimulus.WorkerQuery, context: grpc.aio.ServicerContext
    ) -> visual_stimulus.WorkerState:
        result = await self.boundary.query("GetState", request, context)
        assert isinstance(result, visual_stimulus.WorkerState)
        return result


class CoordinatorService(visual_stimulus_rpc.VisualStimulusCoordinatorServiceServicer):
    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def ReportWorkerOperation(
        self,
        request: visual_stimulus.WorkerOperation,
        context: grpc.aio.ServicerContext,
    ) -> pb.ReportReceipt:
        return await self.boundary.report("ReportWorkerOperation", request, context)

    async def ReportWorkerLifecycle(
        self,
        request: visual_stimulus.WorkerLifecycle,
        context: grpc.aio.ServicerContext,
    ) -> pb.ReportReceipt:
        return await self.boundary.report("ReportWorkerLifecycle", request, context)

    async def ReportDisplay(
        self, request: pb.VisualStimulusDisplayView, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        return await self.boundary.report("ReportDisplay", request, context)

    async def ReportWorkerHeartbeat(
        self, request: pb.HeartbeatReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        return await self.boundary.report("ReportWorkerHeartbeat", request, context)
