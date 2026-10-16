"""Check the real controller port/supervisor terminal handoff locally."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.backend import GrpcSupervisorPort
from cephvr.shared.auth import Principal
from tests.supervisor.support import Context, make_runtime


async def run() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temporary:
        runtime, _, _, _ = make_runtime(Path(temporary))
        consumer = pb.ProcessIdentity(role="gui", generation=str(uuid4()))
        runtime.credentials[(consumer.role, consumer.generation)] = "probe-consumer"
        runtime.registration.source_registered = lambda *args, **kwargs: True
        report = wire.PreviewConsumerReport(
            client_id=consumer.generation, controller_generation=runtime.controller.generation,
            consumer=consumer, preview_run_id=str(uuid4()), allocation_id=str(uuid4()),
            transfer_id=str(uuid4()), result=wire.PREVIEW_CONSUMER_RESULT_RELEASED,
        )

        class Stub:
            async def ReportPreviewConsumerState(self, request, *, metadata):
                context = Context("controller", runtime.controller.generation, "controller-secret")
                context.metadata = metadata
                return await runtime.service.ReportPreviewConsumerState(request, context)

        port = GrpcSupervisorPort(Stub(), Principal("controller", runtime.controller.generation, "controller-secret"))
        result: dict[str, object] = {"method": "Production GrpcSupervisorPort metadata and SupervisorService authentication, local in-process RPC boundary. Registered consumer check isolated; no sockets/devices/native handles.", "controller_forwarding": {}}
        for kind in (wire.PREVIEW_CONSUMER_RESULT_ATTACHED, wire.PREVIEW_CONSUMER_RESULT_RELEASED):
            report.result = kind
            try:
                receipt = await port.report_preview_consumer_state(report)
            except PermissionError as exc:
                observed = {"exception": type(exc).__name__, "reason": str(exc)}
            else:
                observed = {"result": pb.CommandResult.Name(receipt.result)}
            result["controller_forwarding"][wire.PreviewConsumerResult.Name(kind)] = observed
        report.result = wire.PREVIEW_CONSUMER_RESULT_RELEASED
        direct = await runtime.service.ReportPreviewConsumerState(report, Context("gui", consumer.generation, "probe-consumer"))
        result["direct_consumer_release"] = pb.CommandResult.Name(direct.result)
        result["assessment"] = "Owner-approved current-controller terminal relay and independent consumer delivery succeed; supervisor rejects ATTACHED. Original mismatch retained in preview_auth_handoff_probe.before.json. This in-process probe is supplemented by authenticated loopback tests."
        runtime.stop_background()
        await runtime.close_outbound()
        return result


if __name__ == "__main__":
    result = asyncio.run(run())
    output = Path(__file__).with_suffix(".json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
