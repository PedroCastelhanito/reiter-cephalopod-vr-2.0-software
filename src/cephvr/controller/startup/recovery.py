"""Prior-session recovery admission during controller startup."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, cast

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.recovery import StartupRecovery
from cephvr.shared.auth import Principal


class InstallRecovery(Protocol):
    async def __call__(
        self,
        *,
        prompt: pb.Prompt | None,
        handler: Callable[[], Awaitable[None]] | None,
        blocker: str | None,
        completion_warning: str | None = None,
        notice: str | None = None,
    ) -> None: ...


async def prepare_recovery(
    recovery: StartupRecovery,
    stub: rpc.SupervisorServiceStub,
    principal: Principal,
    supervisor_generation: str,
    install: InstallRecovery,
) -> None:
    async def query(prior_generation: str) -> svc.RecoverySnapshot:
        result = cast(
            svc.RecoverySnapshot,
            await stub.GetRecoveryState(
                svc.RecoveryQuery(
                    expected_supervisor=pb.ProcessIdentity(
                        role="supervisor", generation=supervisor_generation
                    ),
                    prior_controller_generation=prior_generation,
                ),
                metadata=principal.metadata(),
            ),
        )
        if result.supervisor != pb.ProcessIdentity(
            role="supervisor", generation=supervisor_generation
        ):
            raise RuntimeError("startup recovery response has a foreign supervisor")
        return result

    try:
        prompt = await recovery.prepare(query)
    except Exception as exc:
        await install(
            prompt=None,
            handler=None,
            blocker=f"Startup recovery remains blocked: {exc}",
        )
    else:
        inspection = recovery.inspection
        completion_warning = None
        if inspection is not None and inspection.spikeglx_stop_unconfirmed:
            endpoint = (
                f"{inspection.spikeglx_endpoint[0]}:{inspection.spikeglx_endpoint[1]}"
                if inspection.spikeglx_endpoint is not None
                else "unknown endpoint"
            )
            completion_warning = (
                "Recovery preserved an unconfirmed SpikeGLX stop: "
                f"{endpoint}, run {inspection.spikeglx_run or 'unknown'}. "
                "Inspect the remote run before another paired session; local "
                "recovery does not establish remote stopping or scientific file closure."
            )
        await install(
            prompt=prompt,
            handler=recovery.recover if prompt is not None else None,
            blocker=prompt.explanation if prompt is not None else None,
            completion_warning=completion_warning,
            notice=recovery.notice,
        )
