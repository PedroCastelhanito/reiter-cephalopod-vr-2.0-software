"""Preview restart ordering and exact viewer-transfer release."""

from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator import manual_preview_pulse as pulse_module
from cephvr.acquisition.coordinator import manual_preview_start as start_module
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_preview import ManualPreview
from cephvr.acquisition.coordinator.manual_preview_evidence import ManualPreviewEvidence
from cephvr.acquisition.coordinator.manual_preview_pulse import (
    ManualPreviewPulseLifecycle,
)
from cephvr.acquisition.coordinator.manual_preview_setup import (
    build_preview_payload,
    new_worker_preview,
)
from cephvr.acquisition.coordinator.manual_preview_start import ManualPreviewStart
from cephvr.acquisition.coordinator.manual_preview_transfer import (
    ManualPreviewTransferOwner,
)
from cephvr.acquisition.ports import (
    ControllerPort,
    ResourcePort,
    SerialOwnerPort,
    WorkerPort,
)
from cephvr.acquisition.state import (
    ChildOperation,
    ConfigurationRecord,
    CoordinatorIdentity,
    LaunchRecord,
    PausedPreview,
    PulseRecord,
    ResourceRecord,
    WorkerPreview,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.acquisition.worker.function_scopes import validate_camera_function_scopes
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.controller.device.tracking_diagnostic import TrackingDiagnosticController
from cephvr.platform.windows.resource_ledger import NativeResourceLedger, ResourceKey
from cephvr.shared.commands import CommandLedger


@pytest.mark.parametrize("width,height", [(80, 40), (40, 80), (40, 40)])
def test_square_viewport_preserves_source_and_padding(width: int, height: int) -> None:
    import cv2
    import numpy as np

    from cephvr.acquisition.preview.viewport import SquareViewport

    source = np.full((height, width, 3), (19, 87, 203), dtype=np.uint8)
    viewport = SquareViewport(width, height, 80)
    image = viewport.render(source, cv2, np)
    assert image.shape == (80, 80, 3)
    fitted_width, fitted_height = int(width * viewport.fit), int(height * viewport.fit)
    x, y = int(viewport.tx), int(viewport.ty)
    assert np.all(image[y : y + fitted_height, x : x + fitted_width] == source[0, 0])
    assert np.count_nonzero(image[:, :, 0]) == fitted_width * fitted_height
    assert np.all(source == (19, 87, 203))


def test_square_viewport_pointer_zoom_fractional_wheel_bounds_and_reset() -> None:
    from cephvr.acquisition.preview.viewport import SquareViewport

    viewport = SquareViewport(80, 80, 80)
    viewport.wheel(20, 30, 120 << 16)
    assert viewport.zoom == pytest.approx(1.2)
    assert (20 - viewport.tx) / (viewport.fit * viewport.zoom) == pytest.approx(20)
    assert (30 - viewport.ty) / (viewport.fit * viewport.zoom) == pytest.approx(30)
    viewport.wheel(20, 30, 60 << 16)
    assert viewport.zoom == pytest.approx(1.2**1.5)
    for _ in range(40):
        viewport.wheel(0, 0, 120 << 16)
    assert viewport.zoom == 16
    for _ in range(80):
        viewport.wheel(80, 80, (-120 & 0xFFFF) << 16)
    assert viewport.zoom == 1
    assert (viewport.tx, viewport.ty) == (0, 0)
    viewport.wheel(20, 30, 120 << 16)
    viewport.reset()
    assert viewport.zoom == 1 and viewport.dirty
    assert (viewport.tx, viewport.ty) == (0, 0)


@pytest.mark.parametrize(
    "message_type", [wire.CameraCommandRequest, wire.AcquisitionCameraCommand]
)
@pytest.mark.parametrize(
    "side,kind,expected",
    [
        (128, 8, True),
        (2048, 8, True),
        (127, 8, False),
        (2049, 8, False),
        (640, 9, False),
    ],
)
def test_preview_placement_admission_bounds(
    message_type: object, side: int, kind: int, expected: bool
) -> None:
    from cephvr.shared.preview_placement import valid_preview_placement

    request = message_type(kind=kind)
    assert valid_preview_placement(request)
    request.preview_placement.CopyFrom(
        wire.PreviewWindowPlacement(x=-1920, y=20, side=side)
    )
    assert valid_preview_placement(request) is expected
    request.preview_placement.x = 1_000_001
    assert not valid_preview_placement(request)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Win32 HighGUI windows")
def test_native_highgui_windows_read_latest_and_close_without_stopping_producer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes
    import threading

    from cephvr.acquisition.buffers.layout import allocation_size
    from cephvr.acquisition.buffers.records import FrameRecord
    from cephvr.acquisition.buffers.ring import SharedRing
    from cephvr.acquisition.camera.native_formats import pylon_pixel_format
    from cephvr.acquisition.preview import highgui
    from cephvr.platform.windows.events import event_name
    from cephvr.shared.pixels.types import PixelLayout

    pytest.importorskip("pypylon")
    images: dict[str, bytes] = {}
    changed = threading.Event()
    zoomed, reset = threading.Event(), threading.Event()
    original = highgui.display_array
    render = highgui.SquareViewport.render

    def native_render(
        viewport: object, frame: object, cv: object, numpy: object
    ) -> object:
        result = render(viewport, frame, cv, numpy)
        assert result.shape == (256, 256)
        if viewport.zoom > 1:
            zoomed.set()
        elif zoomed.is_set():
            reset.set()
        return result

    monkeypatch.setattr(highgui.SquareViewport, "render", native_render)

    def display(image: object, numpy: object) -> object:
        result = original(image, numpy)
        images[threading.current_thread().name] = bytes(result)
        changed.set()
        return result

    monkeypatch.setattr(highgui, "display_array", display)
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    layout = PixelLayout(2, 2, pylon_pixel_format("Mono8"), 2, 4)
    resources: list[tuple[object, object, object]] = []
    try:
        for role in (1, 2):
            allocation, run_id = uuid4(), uuid4()
            producer = control.ProcessIdentity(
                role="camera_worker", generation=str(uuid4())
            )
            descriptor = acq.FrameBufferDescriptor(
                allocation_id=str(allocation),
                owner=owner,
                producer=producer,
                camera=role,
                kind=acq.FRAME_BUFFER_KIND_PREVIEW,
                layout_version=2,
                capacity_frames=1,
                shared_memory_name=f"Local\\cephvr-{allocation}-frames",
                configuration_revision=1,
                allocation_bytes=allocation_size(1, 4),
            )
            descriptor.preview.acquisition_run_id = str(run_id)
            descriptor.image.CopyFrom(
                camera.CameraImageLayout(
                    width=2,
                    height=2,
                    pixel_format="Mono8",
                    row_stride_bytes=2,
                    image_payload_bytes=4,
                )
            )
            attachment = acq.FrameBufferAttachment(buffer=descriptor)
            attachment.sync.transfer_id = str(uuid4())
            attachment.sync.target.CopyFrom(owner)
            attachment.sync.event_name = event_name(allocation)
            ring = SharedRing.create(attachment, layout, owner)
            ring.reset_quiescent(run_id, prior_completion_confirmed=True)
            attachment.sync.target.CopyFrom(producer)
            producer_ring = SharedRing.attach(attachment, layout, producer)
            producer_ring.open_admission(run_id)
            producer_ring.publish(
                FrameRecord(1, 1, None, None, True, None),
                memoryview(b"\x00\x40\x80\xff"),
            )
            producer_ring.publish(
                FrameRecord(2, 2, None, None, True, None),
                memoryview(b"\xff\x80\x40\x00"),
            )
            attachment.sync.target.CopyFrom(owner)
            reader = highgui.HighGuiPreview(
                attachment,
                8,
                f"CephVR isolated preview {role} {uuid4()}",
                lambda _reader: None,
                placement=wire.PreviewWindowPlacement(
                    x=100 + role * 300, y=100, side=256
                ),
            )
            resources.append((ring, producer_ring, reader))
            reader.start()
            reader.ready.result(timeout=5)
            # Both windows display their newest ring value on their own threads.
            deadline = time.monotonic() + 3
            while reader.title not in images and time.monotonic() < deadline:
                changed.wait(0.02)
                changed.clear()
            assert images.get(reader.title) == b"\xff\x80\x40\x00", reader.failure
            assert not reader.done.done()
        # Send native X close to one window; the other remains alive.
        native = ctypes.WinDLL("user32", use_last_error=True)
        native.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        native.FindWindowW.restype = ctypes.c_void_p
        native.PostMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        native.PostMessageW.restype = ctypes.c_bool
        first, second = resources[0][2], resources[1][2]
        handle = native.FindWindowW(None, first.title)
        native.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        native.GetWindow.restype = ctypes.c_void_p
        native.GetWindowRect.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.wintypes.RECT),
        ]
        child = native.GetWindow(handle, 5)
        rect = ctypes.wintypes.RECT()
        assert child and native.GetWindowRect(child, ctypes.byref(rect))
        assert (rect.right - rect.left, rect.bottom - rect.top) == (256, 256)
        frame = ctypes.wintypes.RECT()
        assert native.GetWindowRect(handle, ctypes.byref(frame))
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmGetWindowAttribute.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        visible = ctypes.wintypes.RECT()
        assert (
            dwm.DwmGetWindowAttribute(
                handle, 9, ctypes.byref(visible), ctypes.sizeof(visible)
            )
            == 0
        )
        assert (visible.left, visible.top) == (400, 100)
        from cephvr.platform.windows.window_coordinates import operator_window_geometry

        anchor, work_area, scale = operator_window_geometry(handle)
        assert anchor[:2] == (400, 100)
        assert work_area[2] > 0 and work_area[3] > 0 and scale >= 1
        point = ((rect.top + 128) & 0xFFFF) << 16 | ((rect.left + 128) & 0xFFFF)
        assert native.PostMessageW(child, 0x020A, 120 << 16, point)
        assert zoomed.wait(3), (
            "Native mouse wheel did not reach the owning viewer thread"
        )
        assert native.PostMessageW(child, 0x0203, 0, (128 << 16) | 128)
        assert reset.wait(3), "Native double-click did not restore the fitted view"
        assert resources[0][1].published_count == 2
        assert handle and native.PostMessageW(handle, 0x0010, 0, 0)
        assert first.done.result(timeout=5), first.failure
        assert not second.done.done()
        for ring, producer_ring, _reader in resources:
            assert not ring.retired and not producer_ring.input_sealed
        second.stop()
        assert second.done.result(timeout=5), second.failure
    finally:
        for ring, producer_ring, reader in reversed(resources):
            reader.stop()
            assert reader.done.result(timeout=5), reader.failure
            producer_ring.close()
            ring.close()


@pytest.mark.parametrize("failure", ["", "display", "release"])
def test_highgui_private_latest_frame_thread_and_x_close(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import threading

    import numpy as np

    from cephvr.acquisition.preview import highgui
    from cephvr.shared.pixels.preparer import PreparedImage

    calls: list[tuple[str, int]] = []
    sequences: list[int] = []
    native = b"\x11\x22\x33"
    closed = threading.Event()

    class CV:
        import cv2 as native_cv

        warpAffine = staticmethod(native_cv.warpAffine)
        INTER_LINEAR = native_cv.INTER_LINEAR
        BORDER_REPLICATE = native_cv.BORDER_REPLICATE
        WINDOW_NORMAL = 0
        WND_PROP_VISIBLE = 0
        error = RuntimeError
        images: list[object] = []
        destroyed = False

        def __getattr__(self, name: str) -> object:
            def operation(*args: object) -> object:
                calls.append((name, threading.get_ident()))
                if name == "getWindowProperty":
                    return 1 if len(self.images) < 3 and not self.destroyed else 0
                if name == "destroyWindow":
                    self.destroyed = True
                if name == "imshow":
                    if failure == "display" and len(self.images) == 1:
                        raise ValueError("display failed")
                    self.images.append(args[1])
                return -1

            return operation

    cv = CV()

    class Ring:
        published_count = 3
        retired = False
        released = False

        def read_into(
            self, sequence: int, pixels: bytearray, **_kwargs: object
        ) -> object:
            sequences.append(sequence)
            pixels[:] = native
            self.published_count = 6
            return SimpleNamespace(status="frame")

        def wait(self, _timeout: int) -> None:
            pass

        def close(self) -> None:
            if failure == "release":
                raise RuntimeError("mapping still owned")
            self.released = True

    ring = Ring()

    class Preparer:
        def __init__(self, _layout: object) -> None:
            pass

        def prepare_preview(self, pixels: bytearray, _bits: int) -> PreparedImage:
            assert bytes(pixels) == native
            return PreparedImage(memoryview(pixels), 1, 1, 3, "RGB", 8, 8, 8, "full", 3)

    original_import = highgui.importlib.import_module
    monkeypatch.setattr(
        highgui.importlib,
        "import_module",
        lambda name: cv if name == "cv2" else original_import(name),
    )
    monkeypatch.setattr(highgui.SharedRing, "attach", lambda *_args: ring)
    monkeypatch.setattr(highgui, "PixelPreparer", Preparer)
    attachment = acq.FrameBufferAttachment()
    attachment.buffer.preview.acquisition_run_id = str(uuid4())
    attachment.buffer.image.CopyFrom(
        camera.CameraImageLayout(
            width=1,
            height=1,
            pixel_format="RGB8packed",
            row_stride_bytes=3,
            image_payload_bytes=3,
        )
    )
    reader = highgui.HighGuiPreview(attachment, 8, "test", lambda _reader: closed.set())
    reader.start()
    if failure == "display":
        with pytest.raises(RuntimeError, match="display failed"):
            reader.ready.result(timeout=3)
    else:
        reader.ready.result(timeout=3)
    assert reader.done.result(timeout=3) == (failure != "release")
    assert closed.wait(3)
    assert sequences == ([2] if failure == "display" else [2, 5])
    assert ring.released == (failure != "release")
    assert len({identity for _, identity in calls}) == 1
    assert calls[0][1] != threading.get_ident()
    if not failure:
        assert np.array_equal(
            cv.images[-1], np.full((640, 640, 3), [0x33, 0x22, 0x11], dtype=np.uint8)
        )
        assert reader.failure == ""
    else:
        assert reader.failure


@pytest.mark.asyncio
@pytest.mark.parametrize("released", [False, True])
async def test_backend_window_release_gates_native_owner(
    monkeypatch: pytest.MonkeyPatch, released: bool
) -> None:
    from concurrent.futures import Future

    from cephvr.acquisition.coordinator import preview_windows as module
    from cephvr.platform.windows.resource_ledger import ResourceKey

    identity = SimpleNamespace(
        process=control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    )
    allocation = str(uuid4())
    key = ResourceKey(allocation, identity.process.generation)
    ledger = NativeResourceLedger(max_resources=2, max_transfers_per_resource=3)
    ledger.register(key, kind="preview")
    resource = ResourceRecord(acq.FrameBufferAttachment(), None, key)
    previews = []

    class Reader:
        def __init__(
            self,
            attachment: object,
            bits: int,
            title: str,
            callback: object,
            *,
            placement: object = None,
        ) -> None:
            self.ready: Future[None] = Future()
            self.done: Future[bool] = Future()
            self.failure = "" if released else "native release unconfirmed"
            self.visible = not released
            previews.append(self)

        def start(self) -> None:
            self.ready.set_result(None)

        def stop(self) -> None:
            self.done.set_result(released)

    monkeypatch.setattr(module, "HighGuiPreview", Reader)
    state = SimpleNamespace(set_preview_visibility=lambda *_args: None)
    owner = module.PreviewWindows(
        identity=identity,
        resources={allocation: resource},
        ledger=ledger,
        status=state,
        clock=lambda: 1,
        report_timeout_ns=10,
    )
    preview = WorkerPreview(
        run_id=str(uuid4()),
        configuration_revision=1,
        allocation_id=allocation,
        started=True,
        preview_output_bit_depth=8,
    )
    await owner.show(1, preview, deadline_ns=1_000_000_000)
    assert not ledger.may_close_owner(key)
    assert ledger.snapshot(key).transfers[0].attached
    if released:
        await owner.close(1, preview.run_id, deadline_ns=1_000_000_000)
        assert ledger.may_close_owner(key)
        assert not owner.owns(1)
    else:
        with pytest.raises(RuntimeError, match="release unconfirmed"):
            await owner.close(1, preview.run_id, deadline_ns=1_000_000_000)
        assert not ledger.may_close_owner(key)
        assert owner.owns(1)
    assert preview.started


@pytest.mark.asyncio
async def test_preview_window_rejects_stale_run_and_preserves_capture() -> None:
    from cephvr.acquisition.coordinator.manual_preview_window import (
        execute_preview_window,
    )

    preview = WorkerPreview(run_id=str(uuid4()), configuration_revision=1, started=True)
    windows = SimpleNamespace(show=AsyncMock(), close=AsyncMock())
    results = SimpleNamespace(
        complete=AsyncMock(
            return_value=control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED
            )
        ),
        report_failure=AsyncMock(),
    )
    request = wire.AcquisitionCameraCommand(
        camera=1,
        kind=wire.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
        preview_run_id=str(uuid4()),
    )
    outcome = await execute_preview_window(
        request, preview, windows, results, deadline_ns=100
    )
    assert outcome.result == control.COMMAND_RESULT_REJECTED
    windows.show.assert_not_awaited()
    request.preview_run_id = preview.run_id
    request.preview_placement.CopyFrom(
        wire.PreviewWindowPlacement(x=-700, y=20, side=640)
    )
    outcome = await execute_preview_window(
        request, preview, windows, results, deadline_ns=100
    )
    assert outcome.result == control.COMMAND_RESULT_ACCEPTED
    windows.show.assert_awaited_once_with(
        1, preview, deadline_ns=100, placement=request.preview_placement
    )
    assert preview.started

    request.kind = wire.CAMERA_COMMAND_KIND_HIDE_PREVIEW
    outcome = await execute_preview_window(
        request, preview, windows, results, deadline_ns=100
    )
    assert outcome.result == control.COMMAND_RESULT_REJECTED
    windows.close.assert_not_awaited()
    request.ClearField("preview_placement")
    outcome = await execute_preview_window(
        request, preview, windows, results, deadline_ns=100
    )
    assert outcome.result == control.COMMAND_RESULT_ACCEPTED
    windows.close.assert_awaited_once_with(1, preview.run_id, deadline_ns=100)
    assert preview.started
    windows.show.side_effect = RuntimeError("OpenCV unavailable")
    request.kind = wire.CAMERA_COMMAND_KIND_SHOW_PREVIEW
    outcome = await execute_preview_window(
        request, preview, windows, results, deadline_ns=100
    )
    assert outcome.result == control.COMMAND_RESULT_REJECTED
    results.report_failure.assert_awaited_once()
    assert preview.started


async def test_closed_window_observation_cannot_mutate_reopened_window() -> None:
    from concurrent.futures import Future

    from cephvr.acquisition.coordinator.preview_windows import PreviewWindows

    run_id = str(uuid4())
    controller = SimpleNamespace(
        report_acquisition_device_status=AsyncMock(
            return_value=control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        )
    )
    status = ManualDeviceStatusReporter(
        identity=SimpleNamespace(
            backend=control.BackendContext(
                backend_name="acquisition", backend_generation=str(uuid4())
            )
        ),
        controller=controller,
        commands=CommandLedger(
            str(uuid4()),
            retention_ns=10,
            max_records=4,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        ),
        pulse=PulseRecord(),
        clock=lambda: 10,
    )
    status._views[1].preview_run_id = run_id
    status._views[1].preview_running = True
    status.set_preview_visibility(1, run_id, True)
    done: Future[bool] = Future()
    done.set_result(True)
    reader = SimpleNamespace(done=done, visible=False, failure="")
    owner = PreviewWindows.__new__(PreviewWindows)
    owner._windows = {1: SimpleNamespace(reader=reader, run_id=run_id)}
    owner._notifications = set()
    owner._release = lambda _window: None
    owner.status = status
    owner.clock = lambda: 10
    owner.report_timeout_ns = 100
    owner._closed(1, reader)
    # Observation is captured before the delivery coroutine runs.
    assert not status._views[1].preview_visible
    assert status._views[1].preview_visibility_revision == 2
    owner._windows[1] = SimpleNamespace(reader=object(), run_id=run_id)
    status.set_preview_visibility(1, run_id, True)
    owner._closed(1, reader)
    await asyncio.gather(*tuple(owner._notifications))
    assert status._views[1].preview_visible
    assert status._views[1].preview_visibility_revision == 3
    observed = controller.report_acquisition_device_status.call_args.args[
        0
    ].preview_visibility
    assert not observed.visible and observed.revision == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer_role", ["gui", "cli"])
async def test_controller_viewer_attachment_uses_existing_policy_and_client_identity(
    consumer_role: str,
) -> None:
    owner = ManualPreview.__new__(ManualPreview)
    controller = control.ProcessIdentity(role="controller", generation=str(uuid4()))
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=str(uuid4())
    )
    owner.identity = SimpleNamespace(controller=controller, backend=backend)
    policy = runtime.AcquisitionFilePolicies()
    policy.cameras.add(camera=1, frame_silence_timeout_ns=1_000_000_000)
    owner.configuration = ConfigurationRecord(control.AcquisitionSettings(), policy, 2)
    owner.clock = lambda: 1
    owner.session_slot = SimpleNamespace(current=None)
    preview = WorkerPreview(
        run_id=str(uuid4()),
        configuration_revision=2,
        allocation_id=str(uuid4()),
        started=True,
    )
    owner.workers = SimpleNamespace(workers={1: SimpleNamespace(preview=preview)})
    owner.device_status = SimpleNamespace(reserve=lambda _command: None)
    owner.transfers = SimpleNamespace(attach=AsyncMock())
    owner.windows = SimpleNamespace(owns=lambda _role: False)
    owner.results = SimpleNamespace(
        complete=AsyncMock(
            return_value=control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
            )
        )
    )
    request = wire.AcquisitionCameraCommand(
        camera=1,
        kind=wire.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        configuration_revision=2,
        preview_run_id=preview.run_id,
        preview_consumer=control.ProcessIdentity(
            role=consumer_role,
            generation=str(uuid4()),
        ),
    )
    request.command.command_id = str(uuid4())
    request.command.issuer.CopyFrom(controller)
    request.command.target.CopyFrom(backend)
    request.command.parent_operation.command_id = str(uuid4())

    result = await owner.execute(request, deadline_ns=100)

    assert result.result == control.COMMAND_RESULT_ACCEPTED, result.failure
    owner.transfers.attach.assert_awaited_once_with(request, preview, deadline_ns=100)
    owner.results.complete.assert_awaited_once()
    assert owner.configuration.file_policies == policy
    # Omission uses the current policy; supplied conflicting policy stays invalid.
    request.file_policies.cameras.add(camera=1, frame_silence_timeout_ns=2)
    assert not owner._valid(request, 100)
    request.ClearField("file_policies")
    request.configuration_revision = 1
    assert not owner._valid(request, 100)
    request.configuration_revision = 2
    preview.viewer = control.ProcessIdentity.FromString(
        request.preview_consumer.SerializeToString()
    )
    rejected = await owner.execute(request, deadline_ns=100)
    assert rejected.result == control.COMMAND_RESULT_REJECTED
    assert rejected.failure.code == "PREVIEW_VIEWER_BUSY"
    assert owner.transfers.attach.await_count == 1
    assert owner.results.complete.await_count == 1
    preview.viewer = None
    request.preview_consumer.role = "preview_viewer"
    rejected = await owner.execute(request, deadline_ns=100)
    assert rejected.result == control.COMMAND_RESULT_REJECTED
    assert owner.transfers.attach.await_count == 1


@pytest.mark.parametrize(
    "role", [camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING]
)
def test_manual_preview_declares_exact_non_saving_capture_scope(role: int) -> None:
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    worker = control.ProcessIdentity(role="camera_worker", generation=str(uuid4()))
    attachment = acq.FrameBufferAttachment(
        buffer=acq.FrameBufferDescriptor(owner=owner, producer=worker, camera=role)
    )
    payload = build_preview_payload(
        camera.CameraSessionSettings(sdk_buffer_count=10),
        runtime.CameraFilePolicy(frame_silence_timeout_ns=1_000_000_000),
        camera.CameraResolvedState(),
        attachment,
    )
    scopes = validate_camera_function_scopes(
        payload, acq.WorkerContext(owner=owner, worker=worker, camera=role)
    )
    assert len(scopes) == 1
    assert not payload.HasField("recording")
    assert tuple(scopes[0].affected_closure_resource_ids) == (scopes[0].resource_id,)


class _TransferOwner:
    def __init__(self) -> None:
        self.retired = asyncio.Event()

    def retire(self, preview: WorkerPreview) -> None:
        _ = preview
        self.retired.set()

    async def retire_and_release(
        self, preview: WorkerPreview, *, deadline_ns: int
    ) -> None:
        _ = deadline_ns
        self.retire(preview)
        if preview.viewer is not None:
            await preview.viewer_released_event.wait()
        if preview.tracking_viewer is not None:
            await preview.tracking_viewer_released_event.wait()
        if preview.viewer is not None or preview.tracking_viewer is not None:
            raise RuntimeError("exact preview consumer release is incomplete")

    def close_retired_resource(self, preview: WorkerPreview) -> None:
        _ = preview


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [False, True])
async def test_preview_resolution_preserves_sdk_failure_and_requires_evidence(
    monkeypatch: pytest.MonkeyPatch, succeeded: bool
) -> None:
    class Status:
        pending = False

        def begin_device_access(self, role: int, serial: str) -> None:
            self.pending = True

    status = Status()

    class Resolution:
        async def begin(self, *args: object, **kwargs: object) -> None:
            pass

    class Port:
        async def resolve_camera_configuration(
            self, *args: object, **kwargs: object
        ) -> control.CommandAdmission:
            assert status.pending
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    child = ChildOperation(
        command_id=str(uuid4()),
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        work=control.WorkContext(),
        parent_operation=control.OperationContext(),
        kind="resolve_camera",
    )
    monkeypatch.setattr(
        start_module,
        "retain_worker_command",
        lambda *a, **k: (acq.WorkerCommand(), child, Port()),
    )

    async def completed(*args: object, **kwargs: object) -> control.OperationState:
        result = control.OperationState(complete=True, succeeded=succeeded)
        if not succeeded:
            result.failure.message = "SDK ROI Width violates current limits"
        return result

    monkeypatch.setattr(start_module, "wait_child_operation", completed)
    flow = object.__new__(ManualPreviewStart)
    flow.resolution = cast(start_module.ConfigurationResolution, Resolution())
    flow.device_status = cast(ManualDeviceStatusReporter, status)
    flow.lock = asyncio.Lock()
    flow.clock = lambda: 1
    expected = "successful SDK evidence" if succeeded else "SDK ROI Width"
    with pytest.raises(RuntimeError, match=expected):
        await flow._resolve_camera_and_pulses(
            wire.AcquisitionCameraCommand(configuration_revision=1),
            cast(WorkerRecord, object()),
            camera.CameraSessionSettings(),
            runtime.CameraFilePolicy(),
            (),
            100,
        )
    assert status.pending


class _Status:
    def resolve_camera(self, *args: object, **kwargs: object) -> None:
        _ = args, kwargs


class _Port:
    def __init__(self, preview: WorkerPreview) -> None:
        self.preview = preview

    async def stop_preview(
        self, request: acq.WorkerStopPreview, *, deadline_ns: int
    ) -> control.CommandAdmission:
        _ = request, deadline_ns
        self.preview.stopped_event.set()
        self.preview.cleanup_event.set()
        return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)


class _PulseLifecycle:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    async def pause_for_pulse_change(
        self, roles: tuple[int, ...], *, deadline_ns: int
    ) -> tuple[PausedPreview, ...]:
        _ = deadline_ns
        self.events.append(("pause_existing", roles))
        return (PausedPreview(roles[0], camera.CameraResolvedState(), 8),)

    async def resume_after_pulse_change(
        self, token: tuple[PausedPreview, ...], *, deadline_ns: int
    ) -> None:
        _ = token, deadline_ns
        self.events.append("resume_existing")


class _StartFlow(ManualPreviewStart):
    def __init__(self, events: list[object], lifecycle: _PulseLifecycle) -> None:
        self.events = events
        self.pulse_lifecycle = lifecycle
        self.device_status = cast(ManualDeviceStatusReporter, _Status())

    async def _resolve_camera_and_pulses(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        external_roles: tuple[int, ...],
        deadline_ns: int,
    ) -> tuple[camera.CameraResolvedState, int]:
        _ = request, worker, setting, policy, external_roles, deadline_ns
        self.events.append("configure_and_confirm")
        return camera.CameraResolvedState(), 4

    async def _prepare_preview_run(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        resolved: camera.CameraResolvedState,
        run_id: str,
        configuration_revision: int,
        deadline_ns: int,
    ) -> WorkerPreview:
        _ = (
            request,
            worker,
            setting,
            policy,
            resolved,
            run_id,
            configuration_revision,
            deadline_ns,
        )
        self.events.append("prepare_new_role")
        return WorkerPreview(run_id="run-2", configuration_revision=4)

    async def _start_prepared_preview(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        preview: WorkerPreview,
        external_roles: tuple[int, ...],
        deadline_ns: int,
    ) -> None:
        _ = request, worker, preview, deadline_ns
        self.events.append(("start_new_role", external_roles))


@pytest.mark.asyncio
async def test_second_external_preview_pauses_existing_role_before_configuration() -> (
    None
):
    events: list[object] = []
    flow = _StartFlow(events, _PulseLifecycle(events))
    request = wire.AcquisitionCameraCommand(camera=camera.CAMERA_ROLE_TRACKING)

    await flow.start(
        request,
        cast(WorkerRecord, object()),
        camera.CameraSessionSettings(),
        runtime.CameraFilePolicy(),
        (camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING),
        str(uuid4()),
        100,
    )

    assert events == [
        ("pause_existing", (camera.CAMERA_ROLE_BEHAVIORAL,)),
        "configure_and_confirm",
        "resume_existing",
        "prepare_new_role",
        ("start_new_role", (camera.CAMERA_ROLE_TRACKING,)),
    ]


@pytest.mark.asyncio
async def test_pause_with_attached_viewer_waits_for_exact_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview = WorkerPreview(
        run_id=str(uuid4()),
        configuration_revision=2,
        allocation_id=str(uuid4()),
        resolved_camera=camera.CameraResolvedState(),
        viewer=control.ProcessIdentity(role="preview_viewer", generation=str(uuid4())),
        viewer_transfer_id=str(uuid4()),
        started=True,
    )
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=str(uuid4())
        ),
        owner=control.ProcessIdentity(role="acquisition", generation=str(uuid4())),
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
    )
    port = _Port(preview)
    worker = WorkerRecord(
        context=context,
        port=cast(WorkerPort, port),
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=context.worker,
            owner=context.owner,
            work=control.WorkContext(),
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            parent_operation=control.OperationContext(command_id=str(uuid4())),
            planned_ns=1,
        ),
        preview=preview,
    )

    def retained_command(
        *args: object, **kwargs: object
    ) -> tuple[acq.WorkerCommand, ChildOperation, WorkerPort]:
        _ = args, kwargs
        return (
            acq.WorkerCommand(),
            ChildOperation(
                command_id=str(uuid4()),
                camera=context.camera,
                work=control.WorkContext(),
                parent_operation=control.OperationContext(),
                kind="stop_preview",
            ),
            cast(WorkerPort, port),
        )

    async def child_complete(*args: object, **kwargs: object) -> control.OperationState:
        _ = args, kwargs
        return control.OperationState(complete=True, succeeded=True)

    monkeypatch.setattr(pulse_module, "retain_worker_command", retained_command)
    monkeypatch.setattr(pulse_module, "wait_child_operation", child_complete)
    settings = control.AcquisitionSettings()
    settings.behavioral.enabled = True
    settings.behavioral.device.frame_timing = camera.FRAME_TIMING_EXTERNAL_TRIGGER
    transfers = _TransferOwner()
    lifecycle = ManualPreviewPulseLifecycle(
        identity=cast(CoordinatorIdentity, object()),
        configuration=ConfigurationRecord(
            settings, runtime.AcquisitionFilePolicies(), 2
        ),
        workers={camera.CAMERA_ROLE_BEHAVIORAL: worker},
        pulse=PulseRecord(),
        serial=cast(SerialOwnerPort, object()),
        resources={},
        resource_ledger=cast(NativeResourceLedger, object()),
        resource_port=cast(ResourcePort, object()),
        transfers=cast(ManualPreviewTransferOwner, transfers),
        device_status=cast(ManualDeviceStatusReporter, _Status()),
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )

    task = asyncio.create_task(
        lifecycle.pause_for_pulse_change(
            (camera.CAMERA_ROLE_BEHAVIORAL,), deadline_ns=1_000_000_010
        )
    )
    await asyncio.wait_for(transfers.retired.wait(), 1)
    assert not task.done()
    preview.viewer = None
    preview.viewer_transfer_id = None
    preview.viewer_released_event.set()
    paused = await task
    assert len(paused) == 1
    assert worker.preview is None


def test_release_receipt_lifetime_starts_at_release_not_attach_completion() -> None:
    owner_identity = control.ProcessIdentity(
        role="acquisition", generation=str(uuid4())
    )
    controller_identity = control.ProcessIdentity(
        role="controller", generation=str(uuid4())
    )
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=owner_identity.generation
        ),
        process=owner_identity,
        controller=controller_identity,
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=control.ProcessIdentity(role="tracking", generation=str(uuid4())),
    )
    commands = CommandLedger(
        owner_identity.generation,
        retention_ns=100,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    attach_command = str(uuid4())
    attach_work = str(uuid4())
    commands.admit(attach_command, b"attach", 0, work_key=attach_work)
    commands.complete(attach_command, b"accepted", 1)
    commands.finalize_work(attach_work, 1)
    now = [1]
    owner = ManualPreviewTransferOwner(
        identity=identity,
        resources={},
        resource_ledger=cast(NativeResourceLedger, object()),
        resource_port=cast(ResourcePort, object()),
        controller=cast(ControllerPort, object()),
        commands=commands,
        find_preview=lambda _run_id: None,
        clock=lambda: now[0],
    )
    key = (str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()))

    owner._reserve_release_receipt(key)
    reservation = owner._receipt_reservations[key]
    now[0] = 102
    commands.prune(now[0])
    assert commands.get(attach_command) is None
    assert commands.has_payload(reservation)

    release = wire.PreviewConsumerReport(
        preview_run_id=key[0],
        allocation_id=key[1],
        transfer_id=key[2],
        consumer=control.ProcessIdentity(role="viewer", generation=key[3]),
        controller_generation=controller_identity.generation,
        client_id=key[3],
        result=wire.PREVIEW_CONSUMER_RESULT_RELEASED,
    )
    serialized = release.SerializeToString(deterministic=True)
    owner._retain_release_receipt(key, serialized)
    now[0] = 150
    retry = owner.report_consumer(release)

    assert retry.result == control.COMMAND_RESULT_ACCEPTED
    assert commands.has_payload(reservation)


def test_retired_tracking_preview_waits_for_both_rings_in_either_release_order() -> (
    None
):
    released: list[str] = []
    owner_identity = control.ProcessIdentity(
        role="acquisition", generation=str(uuid4())
    )
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=owner_identity.generation
        ),
        process=owner_identity,
        controller=control.ProcessIdentity(role="controller", generation=str(uuid4())),
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=control.ProcessIdentity(role="tracking", generation=str(uuid4())),
    )

    class Ledger:
        allowed: set[str]

        def may_close_owner(self, key: str) -> bool:
            return key in self.allowed

        def confirm_owner_release(self, _key: str) -> None:
            pass

        def remove_completed_resource(self, _key: str) -> None:
            pass

    class Port:
        def release_ring(self, allocation_id: str) -> None:
            released.append(allocation_id)

    def setup(allowed: set[str]):
        preview_id, tracking_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
        ledger = Ledger()
        ledger.allowed = allowed
        resources = {
            preview_id: cast(
                ResourceRecord,
                type("R", (), {"ledger_key": preview_id, "ring": None})(),
            ),
            tracking_id: cast(
                ResourceRecord,
                type("R", (), {"ledger_key": tracking_id, "ring": None})(),
            ),
        }
        owner = ManualPreviewTransferOwner(
            identity=identity,
            resources=resources,
            resource_ledger=cast(NativeResourceLedger, ledger),
            resource_port=cast(ResourcePort, Port()),
            controller=cast(ControllerPort, object()),
            commands=cast(CommandLedger, object()),
            find_preview=lambda _run: None,
        )
        preview = WorkerPreview(
            run_id=run_id,
            configuration_revision=4,
            allocation_id=preview_id,
            tracking_allocation_id=tracking_id,
        )
        owner._retired[run_id] = preview
        return owner, preview, resources, ledger, preview_id, tracking_id

    owner, preview, resources, ledger, preview_id, tracking_id = setup(set())
    # Main GUI ring releases first; retired ownership remains for Tracking.
    ledger.allowed = {preview_id, tracking_id}
    owner.close_retired_resource(preview)
    assert preview_id in resources and preview.run_id in owner._retired
    owner._close_tracking_resource(preview)
    owner.close_retired_resource(preview)
    assert released == [tracking_id, preview_id]
    assert preview.run_id not in owner._retired

    released.clear()
    owner, preview, resources, ledger, preview_id, tracking_id = setup(set())
    # Tracking releases first; the GUI ring remains retained until its owner releases.
    ledger.allowed = {tracking_id}
    owner._close_tracking_resource(preview)
    owner.close_retired_resource(preview)
    assert released == [tracking_id]
    assert preview.run_id in owner._retired and preview_id in resources
    ledger.allowed.add(preview_id)
    owner.close_retired_resource(preview)
    assert released == [tracking_id, preview_id]
    assert preview.run_id not in owner._retired


def _manual_preview_evidence_case(tracking):
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    worker = control.ProcessIdentity(
        role="acquisition_tracking_worker", generation=str(uuid4())
    )
    ledger = NativeResourceLedger(max_resources=4, max_transfers_per_resource=2)
    resources = {}
    attachments = []
    for kind in ("preview", "tracking") if tracking else ("preview",):
        allocation = str(uuid4())
        attachment = acq.FrameBufferAttachment(
            buffer=acq.FrameBufferDescriptor(
                allocation_id=allocation, owner=owner, producer=worker
            ),
            sync=acq.RingSyncNames(target=worker, transfer_id=str(uuid4())),
        )
        key = ResourceKey(allocation, owner.generation)
        ledger.register(key, kind=kind)
        ledger.expect_attachment(
            key,
            peer_instance_id=worker.generation,
            transfer_id=attachment.sync.transfer_id,
        )
        resources[allocation] = SimpleNamespace(attachment=attachment, ledger_key=key)
        attachments.append(attachment)
    preview = WorkerPreview(
        run_id=str(uuid4()),
        configuration_revision=1,
        allocation_id=attachments[0].buffer.allocation_id,
        worker_attachment=attachments[0],
        tracking_allocation_id=attachments[1].buffer.allocation_id
        if tracking
        else None,
        tracking_worker_attachment=attachments[1] if tracking else None,
    )
    record = SimpleNamespace(
        preview=preview, launch=SimpleNamespace(worker=worker, owner=owner)
    )
    reports = ManualPreviewEvidence(resources, ledger)
    return reports, record, attachments, ledger, resources, worker


@pytest.mark.parametrize("tracking", (False, True))
@pytest.mark.parametrize(
    "case",
    (
        "valid",
        "missing",
        "extra",
        "duplicate",
        "wrong_transfer",
        "wrong_worker",
        "attached",
        "released",
    ),
)
def test_manual_preview_ready_requires_all_exact_pending_transfers(tracking, case):
    reports, record, attachments, ledger, resources, worker = (
        _manual_preview_evidence_case(tracking)
    )
    ready = acq.WorkerReadyEvidence()
    for attachment in attachments:
        ready.attached_resources.add(
            resource_id=attachment.buffer.allocation_id,
            transfer_id=attachment.sync.transfer_id,
        )
    if case == "missing":
        del ready.attached_resources[-1]
    elif case == "extra":
        ready.attached_resources.add(resource_id=str(uuid4()), transfer_id=str(uuid4()))
    elif case == "duplicate":
        ready.attached_resources.add().CopyFrom(ready.attached_resources[0])
    elif case == "wrong_transfer":
        ready.attached_resources[-1].transfer_id = str(uuid4())
    elif case == "wrong_worker":
        attachments[-1].buffer.producer.generation = str(uuid4())
    elif case in {"attached", "released"}:
        attachment = attachments[-1]
        key = resources[attachment.buffer.allocation_id].ledger_key
        action = (
            ledger.confirm_attachment if case == "attached" else ledger.confirm_release
        )
        action(
            key,
            peer_instance_id=worker.generation,
            transfer_id=attachment.sync.transfer_id,
        )
    assert reports.attachments_match(record, ready) == (case == "valid")


@pytest.mark.parametrize("tracking", (False, True))
@pytest.mark.parametrize("exact", (False, True))
@pytest.mark.parametrize(
    "case",
    (
        "valid",
        "missing",
        "extra",
        "duplicate",
        "unreleased",
        "failed",
        "path",
        "wrong_transfer",
    ),
)
def test_manual_preview_cleanup_confirms_both_rings_only_after_complete_proof(
    tracking, exact, case
):
    reports, record, attachments, ledger, resources, worker = (
        _manual_preview_evidence_case(tracking)
    )
    cleanup = acq.WorkerCleanupEvidence()
    for attachment in attachments:
        cleanup.resources.add(resource=attachment.buffer.allocation_id, released=True)
        ledger.confirm_attachment(
            resources[attachment.buffer.allocation_id].ledger_key,
            peer_instance_id=worker.generation,
            transfer_id=attachment.sync.transfer_id,
        )
    if case == "missing":
        del cleanup.resources[-1]
    elif case == "extra":
        cleanup.resources.add(
            resource=f"camera-device:{worker.generation}", released=True
        )
    elif case == "duplicate":
        cleanup.resources.add().CopyFrom(cleanup.resources[0])
    elif case == "unreleased":
        cleanup.resources[-1].released = False
    elif case == "failed":
        cleanup.resources[-1].failure.code = "RELEASE_FAILED"
    elif case == "path":
        cleanup.resources[-1].path = "unexpected-file"
    elif case == "wrong_transfer":
        attachments[-1].sync.transfer_id = str(uuid4())
    valid = case == "valid" or case == "extra" and not exact
    if valid:
        reports.confirm_cleanup(record, cleanup, exact=exact)
    else:
        with pytest.raises(ValueError):
            reports.confirm_cleanup(record, cleanup, exact=exact)
    for resource in resources.values():
        assert all(
            item.released == valid
            for item in ledger.snapshot(resource.ledger_key).transfers
        )


def test_tracking_worker_attachment_preserves_resource_ledger_transfer_id() -> None:
    worker = control.ProcessIdentity(role="camera_worker", generation=str(uuid4()))
    tracking = control.ProcessIdentity(role="tracking", generation=str(uuid4()))
    producer = acq.FrameBufferAttachment(
        buffer=acq.FrameBufferDescriptor(
            allocation_id=str(uuid4()),
            producer=worker,
            consumer=tracking,
            kind=acq.FRAME_BUFFER_KIND_TRACKING,
        ),
        sync=acq.RingSyncNames(transfer_id=str(uuid4()), target=worker),
    )
    consumer = acq.FrameBufferAttachment.FromString(
        producer.SerializeToString(deterministic=True)
    )
    consumer.sync.transfer_id = str(uuid4())
    consumer.sync.target.CopyFrom(tracking)
    preview = new_worker_preview(
        str(uuid4()),
        4,
        acq.FrameBufferAttachment(buffer=acq.FrameBufferDescriptor()),
        camera.CameraResolvedState(),
        8,
        tracking_attachment=consumer,
        tracking_worker_attachment=producer,
    )
    assert preview.tracking_worker_attachment is not None
    assert (
        preview.tracking_worker_attachment.sync.transfer_id == producer.sync.transfer_id
    )
    assert preview.tracking_worker_attachment.sync.target == worker


@pytest.mark.asyncio
async def test_tracking_attach_reserves_release_receipt_before_reporting_transfer() -> (
    None
):
    acquisition = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    controller = control.ProcessIdentity(role="controller", generation=str(uuid4()))
    tracking = control.ProcessIdentity(role="tracking", generation=str(uuid4()))
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=acquisition.generation
        ),
        process=acquisition,
        controller=controller,
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=tracking,
    )
    run_id, allocation_id, command_id = str(uuid4()), str(uuid4()), str(uuid4())
    commands = CommandLedger(
        acquisition.generation,
        retention_ns=10_000,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    commands.admit(command_id, b"attach tracking", 1, work_key=run_id)
    commands.complete(command_id, b"accepted", 2)
    commands.finalize_work(run_id, 2)

    class Ledger:
        released: list[tuple[object, object, object]] = []

        def expect_attachment(self, *_args, **_kwargs):
            pass

        def confirm_release(self, key, *, peer_instance_id, transfer_id):
            self.released.append((key, peer_instance_id, transfer_id))

        def may_close_owner(self, _key):
            return True

        def confirm_owner_release(self, *_args, **_kwargs):
            pass

        def remove_completed_resource(self, *_args, **_kwargs):
            pass

    ring = acq.FrameBufferAttachment(
        buffer=acq.FrameBufferDescriptor(
            allocation_id=allocation_id,
            producer=control.ProcessIdentity(
                role="camera_worker", generation=str(uuid4())
            ),
            kind=acq.FRAME_BUFFER_KIND_TRACKING,
        ),
        sync=acq.RingSyncNames(transfer_id=str(uuid4())),
    )
    resource = type("Resource", (), {"ledger_key": allocation_id, "attachment": ring})()
    preview = WorkerPreview(
        run_id=run_id,
        configuration_revision=3,
        allocation_id=str(uuid4()),
        tracking_allocation_id=allocation_id,
        tracking_attachment=ring,
    )

    class Controller:
        async def report_preview_attachment(self, _report, *, deadline_ns):
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    class ResourcePort:
        def release_ring(self, _allocation_id):
            pass

    owner = ManualPreviewTransferOwner(
        identity=identity,
        resources={allocation_id: cast(ResourceRecord, resource)},
        resource_ledger=cast(NativeResourceLedger, Ledger()),
        resource_port=cast(ResourcePort, ResourcePort()),
        controller=cast(ControllerPort, Controller()),
        commands=commands,
        find_preview=lambda run: preview if run == run_id else None,
    )
    request = wire.AcquisitionTrackingDiagnosticAttachmentCommand(
        command=wire.BackendCommand(command_id=command_id),
        tracking_consumer=tracking,
    )

    attachment = await owner.attach_tracking(request, preview, deadline_ns=10_000)
    assert preview.tracking_viewer == tracking
    assert not preview.tracking_viewer_released_event.is_set()
    key = (run_id, allocation_id, attachment.sync.transfer_id, tracking.generation)
    assert key in owner._receipt_reservations

    class AcquisitionPeer:
        async def report_preview_consumer_state(self, report):
            return owner.report_consumer(report)

    class SupervisorPeer:
        async def report_preview_consumer_state(self, report):
            assert report.result == wire.PREVIEW_CONSUMER_RESULT_RELEASED
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    controller_owner = TrackingDiagnosticController.__new__(
        TrackingDiagnosticController
    )
    controller_owner.generation = controller.generation
    controller_owner.clock = lambda: 1
    controller_owner.lifecycle = SimpleNamespace(lock=asyncio.Lock())
    controller_owner.projections = SimpleNamespace(preview_result=lambda _report: None)
    controller_owner.backends = {"acquisition": AcquisitionPeer()}
    controller_owner.supervisor_peer = SupervisorPeer()
    await controller_owner._report_release(
        tracking, run_id, attachment, deadline=10_000
    )
    assert preview.tracking_viewer is None
    assert preview.tracking_viewer_transfer_id is None
    assert preview.tracking_viewer_released_event.is_set()
    assert owner.resources.get(allocation_id) is None
    assert owner.resource_ledger.released == [
        (allocation_id, tracking.generation, attachment.sync.transfer_id)
    ]


@pytest.mark.parametrize("remaining_external", [False, True])
async def test_preview_disconnect_releases_only_last_external_camera_claim(
    monkeypatch, remaining_external
):
    from unittest.mock import MagicMock

    from cephvr.acquisition.coordinator import manual_preview as module
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    stopped, cleanup = asyncio.Event(), asyncio.Event()
    stopped.set()
    cleanup.set()
    preview = SimpleNamespace(
        run_id="run",
        started=True,
        stopping=False,
        configuration_revision=1,
        stop_operation=None,
        stopped_event=stopped,
        cleanup_event=cleanup,
        resolved_camera=camera.CameraResolvedState(),
        viewer=None,
        tracking_viewer=None,
        allocation_id="released",
        tracking_allocation_id=None,
    )
    worker = SimpleNamespace(preview=preview)
    pulse = PulseRecord(
        observation=mcu.MicrocontrollerObservation(connection_id="connection")
    )
    pulse.observation.state.behavioral.running = True
    pulse.observation.state.tracking.running = remaining_external
    result_state = mcu.MicrocontrollerState()
    result_state.behavioral.running = False
    result_state.tracking.running = False
    evidence = mcu.PulseCommandEvidence(
        connection_id="connection",
        request_id="connection-1",
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
        applied=True,
        dispatched_monotonic_ns=10,
        acknowledged_monotonic_ns=20,
        resulting_state=result_state,
    )
    serial = AsyncMock()
    serial.off.return_value = evidence
    serial.on.return_value = mcu.PulseCommandEvidence.FromString(
        evidence.SerializeToString()
    )
    serial.on.return_value.resulting_state.tracking.running = True
    events = []

    async def worker_done(*args):
        events.append("camera stopped")
        preview.started = False
        return control.OperationState(succeeded=True)

    async def close_claim(**kwargs):
        events.append("claim released")
        assert kwargs["deadline_ns"] == 1000

    serial.close.side_effect = close_claim
    port = AsyncMock()
    port.stop_preview.return_value = control.CommandAdmission(
        result=control.COMMAND_RESULT_ACCEPTED
    )
    monkeypatch.setattr(
        module,
        "retain_worker_command",
        lambda *args, **kwargs: (
            acq.WorkerCommand(),
            SimpleNamespace(command_id="stop"),
            port,
        ),
    )
    monkeypatch.setattr(module, "wait_child_operation", worker_done)
    flow = SimpleNamespace(
        workers=SimpleNamespace(workers={1: worker}),
        _external_roles=lambda _: (1, 2) if remaining_external else (1,),
        serial=serial,
        pulse=pulse,
        clock=lambda: 1,
        lock=asyncio.Lock(),
        resolution=SimpleNamespace(retire_failed_if_quiescent=AsyncMock()),
        windows=SimpleNamespace(close=AsyncMock()),
        device_status=SimpleNamespace(resolve_camera=MagicMock()),
        transfers=SimpleNamespace(
            retire_and_release=AsyncMock(),
            retire=MagicMock(),
            close_retired_resource=MagicMock(),
        ),
        resources={},
        results=SimpleNamespace(
            complete=AsyncMock(
                return_value=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED
                )
            )
        ),
    )
    request = wire.AcquisitionCameraCommand(
        camera=1, preview_run_id="run", command=wire.BackendCommand(command_id="stop")
    )
    result = await ManualPreview._stop(flow, request, 1000)
    assert result.result == control.COMMAND_RESULT_ACCEPTED
    assert serial.close.await_count == (0 if remaining_external else 1)
    assert serial.on.await_count == (1 if remaining_external else 0)
    assert (pulse.observation is None) == (not remaining_external)
    assert events == (
        ["camera stopped"]
        if remaining_external
        else ["camera stopped", "claim released"]
    )


async def test_uncertain_preview_stop_switches_external_output_off_before_cleanup():
    from cephvr.acquisition.coordinator.configuration_resolution import (
        ConfigurationResolution,
    )
    from cephvr.acquisition.coordinator.manual_device_recovery import (
        ManualDeviceRecovery,
    )
    from cephvr.acquisition.coordinator.manual_preview import ManualPreview
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    events: list[str] = []
    preview = SimpleNamespace(
        run_id="late-start-run",
        started=False,
        stopping=False,
        configuration_revision=1,
        resolved_camera=camera.CameraResolvedState(),
        viewer=None,
        tracking_viewer=None,
        allocation_id="ring",
        tracking_allocation_id=None,
    )
    worker = SimpleNamespace(preview=preview)
    workers = SimpleNamespace(workers={camera.CAMERA_ROLE_BEHAVIORAL: worker})

    close_calls = 0

    async def off(roles, *, scheduled_boundary_ns, stop_issued_ns, deadline_ns):
        assert roles == (camera.CAMERA_ROLE_BEHAVIORAL,)
        assert scheduled_boundary_ns is None
        assert stop_issued_ns is not None
        assert deadline_ns == 1000
        events.append("external-output-off")
        state = mcu.MicrocontrollerState()
        state.behavioral.running = False
        state.tracking.running = False
        return mcu.PulseCommandEvidence(
            connection_id="connection",
            request_id="off",
            outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
            applied=True,
            dispatched_monotonic_ns=10,
            acknowledged_monotonic_ns=20,
            resulting_state=state,
        )

    async def close(*, deadline_ns):
        nonlocal close_calls
        assert deadline_ns == 1000
        close_calls += 1
        events.append("claim-close")
        if close_calls == 1:
            raise RuntimeError("serial close response was lost")

    class _Workers:
        def __init__(self):
            self.workers = workers.workers

        async def retire_sessionless_worker(self, role, *, deadline_ns):
            assert role == camera.CAMERA_ROLE_BEHAVIORAL
            assert deadline_ns == 1000
            assert events[0] == "external-output-off"
            events.append("worker-cleanup")
            self.workers.pop(role)

    settings = control.AcquisitionSettings()
    settings.behavioral.device.device_id = "CAM-1"
    settings.behavioral.device.frame_timing = camera.FRAME_TIMING_EXTERNAL_TRIGGER
    pulse = PulseRecord(
        observation=mcu.MicrocontrollerObservation(connection_id="connection")
    )
    workers_owner = _Workers()
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=str(uuid4())
    )
    controller = control.ProcessIdentity(role="controller", generation=str(uuid4()))
    identity = CoordinatorIdentity(
        backend=backend,
        process=control.ProcessIdentity(role="acquisition", generation=str(uuid4())),
        controller=controller,
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=control.ProcessIdentity(role="tracking", generation=str(uuid4())),
    )
    configuration = ConfigurationRecord(
        settings, runtime.AcquisitionFilePolicies(), revision=1
    )

    class _Controller:
        pass

    resolution = ConfigurationResolution(
        identity=identity,
        configuration=configuration,
        controller=cast(ControllerPort, _Controller()),
        lock=asyncio.Lock(),
        clock=lambda: 5,
    )
    serial = SimpleNamespace(off=off, close=close)
    recovery = ManualDeviceRecovery(
        workers=workers_owner,  # type: ignore[arg-type]
        resolution=resolution,
        pulse=pulse,
        serial=cast(SerialOwnerPort, serial),
        clock=lambda: 6,
    )
    old_id = str(uuid4())
    old_operation = await resolution.begin(
        wire.BackendCommand(
            command_id=old_id,
            issuer=controller,
            target=backend,
            parent_operation=control.OperationContext(command_id=old_id),
        ),
        expected_cameras={camera.CAMERA_ROLE_BEHAVIORAL},
        request_revision=1,
        deadline_ns=1000,
        expected_pulses=True,
        requested_pulses=camera.CameraPulseConfiguration(),
        device_work_quiescent=lambda: recovery.device_work_quiescent(
            required_pulse_roles={
                camera.CAMERA_ROLE_BEHAVIORAL,
                camera.CAMERA_ROLE_TRACKING,
            }
        ),
    )
    await resolution.cancel(old_operation)
    flow = SimpleNamespace(
        workers=workers_owner,
        configuration=SimpleNamespace(settings=settings),
        pulse=pulse,
        serial=serial,
        clock=lambda: 5,
        windows=SimpleNamespace(close=AsyncMock()),
        transfers=SimpleNamespace(
            retire=lambda _preview: events.append("viewer-retire"),
            close_retired_resource=lambda _preview: events.append("ring-release"),
        ),
        device_status=SimpleNamespace(
            resolve_camera=lambda *_args, **_kwargs: events.append("status"),
            update_camera_state=lambda *_args, **_kwargs: events.append(
                "closed-camera-cleanup-pending"
            ),
        ),
        resources={},
        resolution=resolution,
        results=SimpleNamespace(
            report_failure=AsyncMock(),
            complete=AsyncMock(
                return_value=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED
                )
            ),
        ),
    )
    flow._external_roles = lambda adding_role: ManualPreview._external_roles(
        flow, adding_role
    )
    request = wire.AcquisitionCameraCommand(
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        preview_run_id=preview.run_id,
        command=wire.BackendCommand(command_id="stop-late-run"),
    )

    failed = await ManualPreview._stop(flow, request, 1000)
    assert failed.result == control.COMMAND_RESULT_REJECTED
    assert events == [
        "external-output-off",
        "viewer-retire",
        "worker-cleanup",
        "ring-release",
        "claim-close",
        "closed-camera-cleanup-pending",
    ]
    assert camera.CAMERA_ROLE_BEHAVIORAL not in flow.workers.workers
    assert worker.preview is preview and preview.stopping
    assert pulse.claim_release_pending
    assert pulse.observation is not None

    assert not recovery.device_work_quiescent(
        required_pulse_roles={
            camera.CAMERA_ROLE_BEHAVIORAL,
            camera.CAMERA_ROLE_TRACKING,
        }
    )
    await recovery.retry_pending_claim_release(deadline_ns=1000)

    assert events[-1] == "claim-close"
    assert close_calls == 2
    assert not pulse.claim_release_pending
    assert pulse.observation is None
    assert pulse.released_idle_connection_id == "connection"
    assert pulse.released_idle_state is not None
    assert not pulse.released_idle_state.behavioral.running
    assert not pulse.released_idle_state.tracking.running
    assert await resolution.retire_failed_if_quiescent(old_operation)
    new_id = str(uuid4())
    await resolution.begin(
        wire.BackendCommand(
            command_id=new_id,
            issuer=controller,
            target=backend,
            parent_operation=control.OperationContext(command_id=new_id),
        ),
        expected_cameras={camera.CAMERA_ROLE_BEHAVIORAL},
        request_revision=1,
        accepted_base_revision=1,
        accepted_base_settings=settings,
        deadline_ns=1000,
        device_work_quiescent=lambda: True,
        preexisting_work_quiescent=recovery.prior_device_work_quiescent,
    )


async def test_failed_idle_claim_release_retains_camera_cleanup_evidence():
    from cephvr.acquisition.coordinator.manual_pulse_observation import (
        release_idle_claim,
    )
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    serial = AsyncMock()
    serial.close.side_effect = RuntimeError("controller release unconfirmed")
    pulse = PulseRecord(
        observation=mcu.MicrocontrollerObservation(connection_id="connection")
    )
    pulse.observation.state.behavioral.running = False
    pulse.observation.state.tracking.running = False
    with pytest.raises(RuntimeError, match="unconfirmed"):
        await release_idle_claim(pulse, serial, deadline_ns=1000)
    assert (
        pulse.observation is not None
        and pulse.observation.connection_id == "connection"
    )


@pytest.mark.asyncio
async def test_normal_stop_reports_camera_closed_when_claim_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.acquisition.coordinator import manual_preview as preview_module
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    events: list[object] = []
    preview = WorkerPreview(
        run_id="normal-stop-run",
        configuration_revision=3,
        allocation_id="ring",
        resolved_camera=camera.CameraResolvedState(),
        started=True,
    )
    role = camera.CAMERA_ROLE_BEHAVIORAL
    worker = SimpleNamespace(context=SimpleNamespace(camera=role), preview=preview)

    class Port:
        async def stop_preview(self, request, *, deadline_ns):
            assert request.release_device
            assert deadline_ns == 1000
            preview.started = False
            preview.stopped_event.set()
            preview.cleanup_event.set()
            events.append("worker-stop-release-device")
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    port = Port()
    child = ChildOperation(
        command_id="stop-child",
        camera=role,
        work=control.WorkContext(),
        parent_operation=control.OperationContext(),
        kind="stop_preview",
    )
    monkeypatch.setattr(
        preview_module,
        "retain_worker_command",
        lambda *_args, **_kwargs: (acq.WorkerCommand(), child, port),
    )

    async def completed(*_args, **_kwargs):
        return control.OperationState(complete=True, succeeded=True)

    monkeypatch.setattr(preview_module, "wait_child_operation", completed)

    async def close(*, deadline_ns):
        assert deadline_ns == 1000
        events.append("claim-close-failed")
        raise RuntimeError("serial close response was lost")

    pulse = PulseRecord(
        observation=mcu.MicrocontrollerObservation(connection_id="connection")
    )
    pulse.observation.state.behavioral.running = False
    pulse.observation.state.tracking.running = False
    worker_registry = SimpleNamespace(workers={role: worker})
    states: list[dict[str, object]] = []

    def update_camera_state(_role: int, **state: object) -> None:
        events.append("status")
        states.append(state)

    async def _release_retired(target_events: list[object], deadline_ns: int) -> None:
        assert deadline_ns == 1000
        target_events.extend(("viewer-retire", "ring-release"))

    flow = SimpleNamespace(
        workers=worker_registry,
        configuration=SimpleNamespace(settings=control.AcquisitionSettings()),
        pulse=pulse,
        serial=SimpleNamespace(close=close),
        clock=lambda: 10,
        lock=asyncio.Lock(),
        windows=SimpleNamespace(
            close=AsyncMock(side_effect=lambda *_a, **_k: events.append("window-close"))
        ),
        transfers=SimpleNamespace(
            retire_and_release=lambda _preview, *, deadline_ns: _release_retired(
                events, deadline_ns
            ),
        ),
        device_status=SimpleNamespace(
            resolve_camera=lambda *_a, **_k: events.append("resolved-closed"),
            update_camera_state=update_camera_state,
        ),
        resources={},
        resolution=SimpleNamespace(retire_failed_if_quiescent=AsyncMock()),
        results=SimpleNamespace(
            report_failure=AsyncMock(),
            complete=AsyncMock(),
        ),
    )
    flow._external_roles = lambda _adding_role: []
    request = wire.AcquisitionCameraCommand(
        camera=role,
        preview_run_id=preview.run_id,
        command=wire.BackendCommand(command_id="stop-normal-run"),
    )

    result = await ManualPreview._stop(flow, request, 1000)

    assert result.result == control.COMMAND_RESULT_REJECTED
    assert events == [
        "worker-stop-release-device",
        "window-close",
        "viewer-retire",
        "ring-release",
        "claim-close-failed",
        "status",
    ]
    assert states == [
        {
            "device_open": False,
            "preview_prepared": False,
            "preview_running": False,
            "preview_run_id": preview.run_id,
            "cleanup_pending": True,
        }
    ]
    assert worker_registry.workers[role] is worker
    assert worker.preview is preview and preview.stopping
    assert pulse.claim_release_pending


@pytest.mark.asyncio
async def test_failed_pulse_restart_retains_exact_cleanup_run_for_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.acquisition.coordinator import manual_preview_pulse as pulse_module
    from cephvr.acquisition.coordinator.manual_preview import ManualPreview

    role = camera.CAMERA_ROLE_BEHAVIORAL
    resolved = camera.CameraResolvedState()
    worker = SimpleNamespace(context=SimpleNamespace(camera=role), preview=None)
    status: dict[int, dict[str, object]] = {}
    events: list[object] = []

    class Status:
        def resolve_camera(self, target_role: int, _resolved, **values: object) -> None:
            status[target_role] = values
            events.append(("status", values.copy()))

        def update_camera_state(self, target_role: int, **values: object) -> None:
            status[target_role].update(values)
            events.append(("status", values.copy()))

    async def allocate(**_kwargs):
        return acq.FrameBufferAttachment(), object()

    monkeypatch.setattr(pulse_module, "allocate_manual_preview_slot", allocate)
    monkeypatch.setattr(
        pulse_module,
        "new_worker_preview",
        lambda run_id, revision, _attachment, camera_state, _bits, **_kwargs: (
            WorkerPreview(
                run_id=run_id,
                configuration_revision=revision,
                allocation_id="new-ring",
                resolved_camera=camera_state,
            )
        ),
    )
    monkeypatch.setattr(
        pulse_module,
        "build_preview_payload",
        lambda *_args, **_kwargs: acq.CameraWorkerSetupPayload(),
    )

    children: dict[str, ChildOperation] = {}

    def retain(_worker, *, kind, deadline_ns, **_kwargs):
        command_id = f"{kind}-child"
        child = ChildOperation(
            command_id=command_id,
            camera=role,
            work=control.WorkContext(),
            parent_operation=control.OperationContext(command_id="pulse-edit"),
            kind=kind,
            deadline_ns=deadline_ns,
        )
        children[kind] = child
        return acq.WorkerCommand(), child, port

    class Port:
        async def prepare_preview(self, _request, *, deadline_ns):
            assert deadline_ns == 1000
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

        async def start_preview(self, request, *, deadline_ns):
            assert deadline_ns == 1000
            assert request.preview_run_id == worker.preview.run_id
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    port = Port()

    async def wait_child(child, *_args):
        if child.kind == "start_preview":
            return control.OperationState(complete=True, succeeded=False)
        return control.OperationState(complete=True, succeeded=True)

    monkeypatch.setattr(pulse_module, "retain_worker_command", retain)
    monkeypatch.setattr(pulse_module, "wait_child_operation", wait_child)

    settings = control.AcquisitionSettings()
    settings.behavioral.device.device_id = "CAM-1"
    settings.behavioral.sdk_buffer_count = 4
    settings.behavioral.enabled = True
    policy = runtime.AcquisitionFilePolicies()
    policy.cameras.add().camera = role
    worker_map = {role: worker}
    lifecycle = ManualPreviewPulseLifecycle(
        identity=cast(
            CoordinatorIdentity,
            SimpleNamespace(
                controller=control.ProcessIdentity(
                    role="controller", generation="controller"
                )
            ),
        ),
        configuration=ConfigurationRecord(settings, policy, revision=7),
        workers=worker_map,
        pulse=PulseRecord(),
        serial=cast(SerialOwnerPort, object()),
        resources={},
        resource_ledger=cast(NativeResourceLedger, object()),
        resource_port=cast(ResourcePort, object()),
        transfers=cast(ManualPreviewTransferOwner, object()),
        device_status=cast(ManualDeviceStatusReporter, Status()),
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )
    paused = PausedPreview(role, resolved, 8)

    with pytest.raises(RuntimeError, match="preview restart failed"):
        await lifecycle._prepare_restart(
            worker,
            paused,
            1000,
            control.OperationContext(command_id="pulse-edit"),
        )

    preview = worker.preview
    assert preview is not None and preview.run_id
    exact_run_id = preview.run_id
    assert status[role] == {
        "device_open": True,
        "preview_prepared": True,
        "preview_running": False,
        "preview_run_id": exact_run_id,
        "cleanup_pending": True,
        "configuration_revision": 7,
    }
    assert not preview.started

    async def retire_worker(target_role: int, *, deadline_ns: int) -> None:
        assert target_role == role and deadline_ns == 1000
        events.append(("cleanup", worker.preview.run_id))
        worker_map.pop(target_role)

    flow = SimpleNamespace(
        workers=SimpleNamespace(
            workers=worker_map, retire_sessionless_worker=retire_worker
        ),
        configuration=SimpleNamespace(settings=settings),
        pulse=lifecycle.pulse,
        serial=SimpleNamespace(),
        clock=lambda: 10,
        windows=SimpleNamespace(
            close=AsyncMock(
                side_effect=lambda target_role, run_id, **_kwargs: events.append(
                    ("window-close", target_role, run_id)
                )
            )
        ),
        transfers=SimpleNamespace(
            retire=lambda _preview: events.append(("viewer-retire", exact_run_id)),
            close_retired_resource=lambda _preview: None,
        ),
        device_status=Status(),
        resources={},
        resolution=SimpleNamespace(retire_failed_if_quiescent=AsyncMock()),
        results=SimpleNamespace(
            report_failure=AsyncMock(),
            complete=AsyncMock(
                return_value=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED
                )
            ),
        ),
    )
    flow._external_roles = lambda _adding_role: []
    stop = wire.AcquisitionCameraCommand(
        camera=role,
        preview_run_id=exact_run_id,
        command=wire.BackendCommand(command_id="stop-restarted-run"),
    )

    result = await ManualPreview._stop(flow, stop, 1000)

    assert result.result == control.COMMAND_RESULT_ACCEPTED
    assert ("window-close", role, exact_run_id) in events
    assert ("cleanup", exact_run_id) in events


@pytest.mark.asyncio
async def test_pulse_pause_retains_stopping_preview_until_tracking_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.acquisition.coordinator import manual_preview_pulse as pulse_module
    from cephvr.acquisition.coordinator import (
        manual_preview_transfer as transfer_module,
    )
    from cephvr.acquisition.coordinator.configuration_resolution import (
        ConfigurationResolution,
    )
    from cephvr.acquisition.coordinator.manual_device_recovery import (
        ManualDeviceRecovery,
    )
    from cephvr.acquisition.coordinator.workers import WorkerRegistry
    from cephvr.platform.windows.resource_ledger import ResourceKey

    role = camera.CAMERA_ROLE_BEHAVIORAL
    primary_id = str(uuid4())
    tracking_id = str(uuid4())
    tracking_transfer_id = str(uuid4())
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    controller = control.ProcessIdentity(role="controller", generation=str(uuid4()))
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=owner.generation
        ),
        process=owner,
        controller=controller,
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=control.ProcessIdentity(role="tracking", generation=str(uuid4())),
    )
    preview = WorkerPreview(
        run_id=str(uuid4()),
        configuration_revision=2,
        allocation_id=primary_id,
        tracking_allocation_id=tracking_id,
        resolved_camera=camera.CameraResolvedState(),
        tracking_viewer=control.ProcessIdentity(
            role="tracking_viewer", generation=str(uuid4())
        ),
        tracking_viewer_transfer_id=tracking_transfer_id,
        started=True,
    )
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=str(uuid4())
        ),
        owner=owner,
        camera=role,
    )

    class Port:
        async def stop_preview(self, request, *, deadline_ns):
            assert request.preview_run_id == preview.run_id
            assert not request.release_device
            assert deadline_ns == 100_000_010
            preview.started = False
            preview.stopped_event.set()
            preview.cleanup_event.set()
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    port = Port()
    worker = WorkerRecord(
        context=context,
        port=cast(WorkerPort, port),
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=context.worker,
            owner=owner,
            work=control.WorkContext(),
            camera=role,
            parent_operation=control.OperationContext(command_id=str(uuid4())),
            planned_ns=1,
        ),
        preview=preview,
    )
    worker_map = {role: worker}

    def retained_command(*_args, **_kwargs):
        return (
            acq.WorkerCommand(),
            ChildOperation(
                command_id="pause-child",
                camera=role,
                work=control.WorkContext(),
                parent_operation=control.OperationContext(command_id="pause-edit"),
                kind="stop_preview",
            ),
            port,
        )

    async def completed(*_args, **_kwargs):
        return control.OperationState(complete=True, succeeded=True)

    monkeypatch.setattr(pulse_module, "retain_worker_command", retained_command)
    monkeypatch.setattr(pulse_module, "wait_child_operation", completed)

    ledger = NativeResourceLedger(max_resources=3, max_transfers_per_resource=2)
    resources: dict[str, ResourceRecord] = {}
    for allocation_id in (primary_id, tracking_id):
        key = ResourceKey(allocation_id, owner.generation)
        ledger.register(key, kind="preview")
        resources[allocation_id] = ResourceRecord(
            acq.FrameBufferAttachment(), None, key
        )
    tracking_key = resources[tracking_id].ledger_key
    ledger.expect_attachment(
        tracking_key,
        peer_instance_id=preview.tracking_viewer.generation,
        transfer_id=preview.tracking_viewer_transfer_id,
    )

    class ResourcePort:
        def release_ring(self, _allocation_id: str) -> None:
            raise AssertionError("unreleased tracking consumer must retain both rings")

    release_waiting = asyncio.Event()
    original_wait_release = transfer_module._wait_release_event

    async def wait_tracking_release(event, deadline_ns, clock):
        release_waiting.set()
        await original_wait_release(event, deadline_ns, clock)

    monkeypatch.setattr(transfer_module, "_wait_release_event", wait_tracking_release)
    transfers = ManualPreviewTransferOwner(
        identity=identity,
        resources=resources,
        resource_ledger=ledger,
        resource_port=cast(ResourcePort, ResourcePort()),
        controller=cast(ControllerPort, object()),
        commands=CommandLedger(
            str(uuid4()),
            retention_ns=10,
            max_records=8,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        ),
        find_preview=lambda run_id: (
            worker.preview
            if worker.preview is not None and worker.preview.run_id == run_id
            else None
        ),
        clock=lambda: 10,
    )
    settings = control.AcquisitionSettings()
    settings.behavioral.enabled = True
    file_policies = runtime.AcquisitionFilePolicies()
    file_policies.cameras.add().camera = role
    configuration = ConfigurationRecord(settings, file_policies, revision=2)
    resolution = ConfigurationResolution(
        identity=identity,
        configuration=configuration,
        controller=cast(ControllerPort, object()),
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )
    pulse = PulseRecord()
    recovery = ManualDeviceRecovery(
        workers=cast(WorkerRegistry, SimpleNamespace(workers=worker_map)),
        resolution=resolution,
        pulse=pulse,
        serial=cast(SerialOwnerPort, object()),
        clock=lambda: 10,
    )
    status: dict[str, object] = {}

    class Status:
        def resolve_camera(self, _role, _resolved, **values):
            status.update(values)

    lifecycle = ManualPreviewPulseLifecycle(
        identity=identity,
        configuration=configuration,
        workers=worker_map,
        pulse=pulse,
        serial=cast(SerialOwnerPort, object()),
        resources=resources,
        resource_ledger=ledger,
        resource_port=cast(ResourcePort, ResourcePort()),
        transfers=transfers,
        device_status=cast(ManualDeviceStatusReporter, Status()),
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )
    task = asyncio.create_task(
        lifecycle.pause_for_pulse_change((role,), deadline_ns=100_000_010)
    )
    await release_waiting.wait()

    assert not task.done()
    assert worker.preview is preview and preview.stopping
    assert status == {
        "device_open": True,
        "preview_prepared": False,
        "preview_running": False,
        "preview_run_id": preview.run_id,
        "cleanup_pending": True,
        "configuration_revision": 2,
    }
    assert tracking_id in resources
    assert not recovery.prior_device_work_quiescent()

    command_id = str(uuid4())
    backend_command = wire.BackendCommand(
        command_id=command_id,
        issuer=controller,
        target=identity.backend,
        parent_operation=control.OperationContext(command_id=command_id),
    )
    with pytest.raises(RuntimeError, match="prior camera device work"):
        await resolution.begin(
            backend_command,
            expected_cameras={role},
            request_revision=2,
            deadline_ns=1000,
            accepted_base_revision=2,
            accepted_base_settings=settings,
            preexisting_work_quiescent=recovery.prior_device_work_quiescent,
        )

    with pytest.raises(TimeoutError):
        await task
    assert worker.preview is preview and preview.stopping
    assert tracking_id in resources
