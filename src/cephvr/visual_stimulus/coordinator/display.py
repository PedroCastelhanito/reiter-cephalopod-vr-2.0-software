"""Exact display evidence and recoverable startup rejection (V19/E08)."""

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.rendering.native_display import (
    DisplayAssetUnavailableError,
    DisplayUnavailableError,
)
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .ports import PeerPort
from .state import CommandLink, Identity, State


def recovered_startup_rejection(
    state: State, link: CommandLink, result: pb.OperationState
) -> bool:
    display = state.display
    return (
        link.method == "InitializeDisplay"
        and state.setup is None
        and link.parent.work.WhichOneof("work") is None
        and result.failure.code
        in {DisplayUnavailableError.code, DisplayAssetUnavailableError.code}
        and display is not None
        and display.command_id == link.parent.command_id
        and display.complete
        and not display.HasField("applied_revision")
        and any(issue.failure.code == result.failure.code for issue in display.issues)
        and bool(display.resources)
        and all(item.released for item in display.resources)
    )


def rejected_calibration_update(
    identity: Identity, state: State, link: CommandLink, result: pb.OperationState
) -> bool:
    display = state.display
    if (
        link.method != "UpdateDisplayCalibration"
        or result.command != link.method
        or state.setup is not None
        or link.parent.work.WhichOneof("work") is not None
        or result.failure.code != "CALIBRATION_ADJUSTMENT_REJECTED"
        or display is None
        or not display.HasField("calibration")
    ):
        return False
    evidence = display.calibration
    return (
        display.command_id == link.parent.command_id
        and display.complete
        and display.source == identity.process
        and display.backend == identity.backend
        and display.controller == identity.controller
        and display.requested_revision == link.child.target.configuration_revision
        and evidence.diagnostic_id == link.diagnostic_id
        and evidence.configuration_revision == link.child.target.configuration_revision
        and evidence.renderer_generation == identity.worker.generation
        and evidence.controller_generation == identity.controller.generation
        and evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        and evidence.presented
        and evidence.failure_code == "CALIBRATION_ADJUSTMENT_REJECTED"
        and evidence.adjustment_sequence < link.adjustment_sequence
    )


async def accept_display_report(
    identity: Identity,
    state: State,
    controller: PeerPort,
    report: pb.VisualStimulusDisplayView,
) -> None:
    link = state.links.get(report.command_id)
    if (
        link is None
        or link.method
        not in {
            "InitializeDisplay",
            "OpenDisplayCalibration",
            "CloseDisplayCalibration",
            "UpdateDisplayCalibration",
            "Cleanup",
            "Shutdown",
            "InterruptSession",
            "CancelSetup",
        }
        or report.source != identity.worker
        or report.backend != identity.backend
        or report.controller != identity.controller
        or report.requested_revision != link.child.target.configuration_revision
    ):
        raise ValueError("display evidence identity/revision mismatch")
    if link.method in {
        "OpenDisplayCalibration",
        "CloseDisplayCalibration",
        "UpdateDisplayCalibration",
    }:
        evidence = report.calibration
        outputs = {item.output_id for item in report.outputs}
        active_evidence = state.display
        expected_diagnostic = link.diagnostic_id
        if (
            not expected_diagnostic
            and active_evidence is not None
            and active_evidence.HasField("calibration")
        ):
            expected_diagnostic = active_evidence.calibration.diagnostic_id
        if (
            not report.HasField("calibration")
            or evidence.diagnostic_id != expected_diagnostic
            or evidence.controller_generation != identity.controller.generation
            or evidence.renderer_generation != identity.worker.generation
            or evidence.configuration_revision
            != link.child.target.configuration_revision
            or outputs != link.output_ids
            or len(report.outputs) != len(outputs)
        ):
            raise ValueError("calibration evidence identity differs from its command")
        if link.method in {"OpenDisplayCalibration", "UpdateDisplayCalibration"} and (
            evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
            and (not evidence.HasField("presented") or not evidence.presented)
        ):
            raise ValueError("Active calibration lacks presentation evidence")
        if (
            link.method == "UpdateDisplayCalibration"
            and evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        ):
            expected_sequence = link.adjustment_sequence
            if evidence.failure_code == "CALIBRATION_ADJUSTMENT_REJECTED":
                if active_evidence is None or not active_evidence.HasField(
                    "calibration"
                ):
                    raise ValueError(
                        "Rejected update lacks prior presentation evidence"
                    )
                expected_sequence = active_evidence.calibration.adjustment_sequence
            if evidence.adjustment_sequence != expected_sequence:
                raise ValueError(
                    "Live calibration update evidence has a stale sequence"
                )
        if link.method == "CloseDisplayCalibration" and (
            evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
            and (
                not evidence.HasField("idle")
                or not evidence.idle
                or not evidence.HasField("resources_closed")
                or not evidence.resources_closed
            )
        ):
            raise ValueError("Idle calibration lacks resource-closure evidence")
        if evidence.state not in {
            vp.DISPLAY_CALIBRATION_STATE_ACTIVE,
            vp.DISPLAY_CALIBRATION_STATE_IDLE,
            vp.DISPLAY_CALIBRATION_STATE_UNKNOWN,
        }:
            raise ValueError("calibration evidence is not a terminal diagnostic state")
    elif link.method in {
        "Cleanup",
        "Shutdown",
        "InterruptSession",
        "CancelSetup",
    } and report.HasField("calibration"):
        evidence = report.calibration
        outputs = {item.output_id for item in report.outputs}
        prior = state.display
        if (
            prior is None
            or not prior.HasField("calibration")
            or evidence.diagnostic_id != prior.calibration.diagnostic_id
            or evidence.controller_generation != identity.controller.generation
            or evidence.renderer_generation != identity.worker.generation
            or evidence.configuration_revision
            != link.child.target.configuration_revision
            or outputs != link.output_ids
            or len(report.outputs) != len(outputs)
            or evidence.state
            not in {
                vp.DISPLAY_CALIBRATION_STATE_IDLE,
                vp.DISPLAY_CALIBRATION_STATE_UNKNOWN,
            }
        ):
            raise ValueError("safety-close calibration evidence is not exact")
        if evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE and (
            not evidence.HasField("idle")
            or not evidence.idle
            or not evidence.HasField("resources_closed")
            or not evidence.resources_closed
        ):
            raise ValueError("safety-close Idle lacks resource-closure evidence")
    forwarded = pb.VisualStimulusDisplayView.FromString(report.SerializeToString())
    forwarded.command_id = link.parent.command_id
    forwarded.source.CopyFrom(identity.process)
    state.display = forwarded
    await controller.receipt(
        "ReportVisualStimulusDisplay", forwarded, deadline_ns=link.deadline_ns
    )
