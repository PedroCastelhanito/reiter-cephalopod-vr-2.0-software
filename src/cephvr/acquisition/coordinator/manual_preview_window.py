"""Configuration-time Show/Hide commands, independent of capture ownership."""

from __future__ import annotations

from cephvr.acquisition.coordinator.manual_operation_results import (
    ManualOperationResults,
)
from cephvr.acquisition.coordinator.manual_preview_transfer import (
    ManualPreviewTransferOwner,
)
from cephvr.acquisition.coordinator.preview_windows import PreviewWindows
from cephvr.acquisition.state import WorkerPreview
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.preview_placement import valid_preview_placement


async def execute_preview_window(
    request: wire.AcquisitionCameraCommand,
    preview: WorkerPreview | None,
    windows: PreviewWindows,
    results: ManualOperationResults,
    *,
    deadline_ns: int,
) -> control.CommandAdmission:
    if (
        not request.HasField("preview_run_id")
        or request.HasField("preview_consumer")
        or request.HasField("path")
        or preview is None
        or not preview.started
        or preview.stopping
        or preview.run_id != request.preview_run_id
        or not valid_preview_placement(request)
    ):
        return control.CommandAdmission(
            command_id=request.command.command_id,
            result=control.COMMAND_RESULT_REJECTED,
            failure=control.Failure(
                code="PREVIEW_WINDOW",
                message="Window requires the exact active preview run",
            ),
        )
    show = request.kind == wire.CAMERA_COMMAND_KIND_SHOW_PREVIEW
    failure = ""
    try:
        if show:
            await windows.show(
                request.camera,
                preview,
                deadline_ns=deadline_ns,
                placement=request.preview_placement
                if request.HasField("preview_placement")
                else None,
            )
        else:
            await windows.close(request.camera, preview.run_id, deadline_ns=deadline_ns)
    except Exception as exc:
        failure = str(exc)
    if failure:
        await results.report_failure(
            request.command,
            command_name="show_preview" if show else "hide_preview",
            deadline_ns=deadline_ns,
            failure=failure,
        )
        return control.CommandAdmission(
            command_id=request.command.command_id,
            result=control.COMMAND_RESULT_REJECTED,
            failure=control.Failure(code="PREVIEW_WINDOW_FAILED", message=failure),
        )
    return await results.complete(
        request.command,
        command_name="show_preview" if show else "hide_preview",
        status_code="PREVIEW_WINDOW_STATUS",
        status_failure="controller rejected preview window state",
        parent_code="PREVIEW_WINDOW_RESULT",
        deadline_ns=deadline_ns,
        parent_failure="controller rejected preview window completion",
    )


async def attach_preview_viewer(
    request: wire.AcquisitionCameraCommand,
    preview: WorkerPreview | None,
    windows: PreviewWindows,
    transfers: ManualPreviewTransferOwner,
    results: ManualOperationResults,
    *,
    deadline_ns: int,
) -> control.CommandAdmission:
    if (
        preview is None
        or not preview.started
        or preview.run_id != request.preview_run_id
        or preview.allocation_id is None
        or request.preview_consumer.role not in {"gui", "cli"}
        or not request.preview_consumer.generation
    ):
        return _rejected(
            request.command.command_id,
            "PREVIEW_VIEWER",
            "viewer does not match a live preview slot",
        )
    if preview.viewer is not None or windows.owns(request.camera):
        return _rejected(
            request.command.command_id,
            "PREVIEW_VIEWER_BUSY",
            "the previous viewer transfer remains active; wait for confirmed release",
        )
    try:
        await transfers.attach(request, preview, deadline_ns=deadline_ns)
    except (RuntimeError, ValueError) as exc:
        return _rejected(request.command.command_id, "PREVIEW_TRANSFER", str(exc))
    return await results.complete(
        request.command,
        command_name="attach_preview_viewer",
        deadline_ns=deadline_ns,
        status_code="DEVICE_STATUS",
        status_failure="controller rejected camera status",
        parent_code="PREVIEW_REPORT",
        parent_failure="controller rejected preview completion",
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        command_id=command_id,
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message),
    )
