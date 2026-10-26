"""Bounded native-follow versus Qt GPU presentation probe; no backend commands.

Generated RGB frames isolate presentation cost, not scientific workload acceptance.
Run each mode in a fresh GUI-interpreter process; use the renderer interpreter for
readback. JSON records actual GL identity, CPU cost and observed callback timing.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import sys
import time
from pathlib import Path

import numpy as np


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "mean_ms": float(np.mean(values)) if values else 0.0,
        "p95_ms": float(np.percentile(values, 95)) if values else 0.0,
        "max_ms": max(values, default=0.0),
    }


def motion_frame(
    pixels: int, sequence: int, channels: int = 3, frame: np.ndarray | None = None
) -> np.ndarray:
    if frame is None:
        frame = np.empty((pixels, pixels, channels), dtype=np.uint8)
    frame.fill(32)
    frame[::64, :, :] = 96
    frame[:, ::64, :] = 96
    x = (sequence * 8) % (pixels - 32)
    frame[:, x : x + 32, :] = 220
    frame[:8, :, :] = 200
    frame[-8:, :, :] = 80
    return frame


def native_viewer(connection, args, identity, placements) -> None:
    """Keep HighGUI separate from Qt, as in the managed application."""
    import cv2

    from cephvr.platform.windows.preview_owner import WindowsPreviewOwner
    from cephvr.platform.windows.window_coordinates import (
        blank_preview_caption,
        physical_coordinates,
        position_preview_frame,
        preview_window_handle,
    )
    from cephvr.shared.preview_geometry import PreviewGeometryGuard

    windows = []
    samples: list[float] = []
    intervals: list[float] = []
    frames = [motion_frame(args.pixels, 0, args.channels) for _ in range(args.streams)]
    try:
        with physical_coordinates():
            for i, (x, y, side) in enumerate(placements):
                title = f"Isolated native preview {i}"
                cv2.namedWindow(title, cv2.WINDOW_NORMAL)
                cv2.imshow(title, cv2.resize(frames[i], (side, side)))
                cv2.resizeWindow(title, side, side)
                cv2.waitKey(1)
                handle = preview_window_handle(title)
                position_preview_frame(handle, x, y, topmost=False)
                owner = (
                    WindowsPreviewOwner(title, *identity)
                    if args.mode == "native-follow"
                    else None
                )
                blank_preview_caption(handle)
                cv2.resizeWindow(title, side, side)
                guard = PreviewGeometryGuard()
                if owner:
                    owner.sync()
                    guard.arranged(owner.geometry(), owner.placement_revision())
                windows.append((title, handle, owner, guard))
            connection.send("ready")
            cpu = time.process_time()
            next_frame = previous = time.perf_counter()
            count = 0
            while True:
                begin = time.perf_counter()
                pending = None
                stop = False
                while connection.poll():
                    command, payload = connection.recv()
                    if command == "stop":
                        stop = True
                    elif command == "measure":
                        cpu = time.process_time()
                        samples.clear()
                        intervals.clear()
                    else:
                        pending = payload
                if stop:
                    connection.send(
                        {
                            "cpu_seconds": time.process_time() - cpu,
                            "poll": summary(samples),
                            "frame_intervals": summary(intervals),
                        }
                    )
                    break
                cv2.waitKey(1)
                for i, (title, handle, owner, guard) in enumerate(windows):
                    if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                        raise RuntimeError("Native probe viewer unexpectedly closed")
                    if owner:
                        owner.sync()
                        automatic = guard.observe(
                            owner.geometry(), owner.placement_revision()
                        )
                        if pending and automatic and pending[i] != placements[i]:
                            x, y, side = pending[i]
                            cv2.resizeWindow(title, side, side)
                            cv2.waitKey(1)
                            position_preview_frame(handle, x, y, topmost=False)
                            guard.arranged(owner.geometry(), owner.placement_revision())
                if pending:
                    placements = pending
                now = time.perf_counter()
                if now >= next_frame:
                    intervals.append((now - previous) * 1000)
                    previous = now
                    for i, (title, _, _, _) in enumerate(windows):
                        frame = motion_frame(
                            args.pixels, count + i * 9, args.channels, frames[i]
                        )
                        side = placements[i][2]
                        cv2.imshow(title, cv2.resize(frame, (side, side)))
                    count += 1
                    next_frame += 0.05
                    if next_frame < now:
                        next_frame = now + 0.05
                samples.append((time.perf_counter() - begin) * 1000)
                time.sleep(max(0, 0.01 - (time.perf_counter() - begin)))
    finally:
        for title, _, owner, _ in windows:
            cv2.destroyWindow(title)
            if owner:
                owner.close()
        cv2.waitKey(1)
        connection.close()


def readback(args: argparse.Namespace) -> dict:
    import glfw
    import moderngl

    if not glfw.init():
        raise RuntimeError("GLFW initialization failed")
    window = None
    try:
        glfw.window_hint(glfw.VISIBLE, False)
        window = glfw.create_window(64, 64, "Preview transfer probe", None, None)
        if not window:
            raise RuntimeError("GLFW context creation failed")
        glfw.make_context_current(window)
        ctx = moderngl.create_context()
        framebuffer = ctx.simple_framebuffer((args.pixels, args.pixels), components=3)
        framebuffer.use()
        samples = []
        cpu = time.process_time()
        start = time.perf_counter()
        count = 0
        while time.perf_counter() - start < args.seconds:
            begin = time.perf_counter()
            for stream in range(args.streams):
                framebuffer.clear((count % 255) / 255, stream / args.streams, 0.5)
                pixels = framebuffer.read(components=3, alignment=1)
                assert len(pixels) == args.pixels * args.pixels * 3
            samples.append((time.perf_counter() - begin) * 1000)
            count += 1
            time.sleep(max(0, 0.05 - (time.perf_counter() - begin)))
        result = {
            "renderer": ctx.info["GL_RENDERER"],
            "vendor": ctx.info["GL_VENDOR"],
            "batch_readback": summary(samples),
            "cpu_core_percent": 100
            * (time.process_time() - cpu)
            / (time.perf_counter() - start),
            "scope": "Synchronous RGB readback only; no IPC/upload or scene load",
        }
        framebuffer.release()
        ctx.release()
        return result
    finally:
        if window:
            glfw.destroy_window(window)
        glfw.terminate()


def presentation(args: argparse.Namespace) -> dict:
    from PyQt6.QtCore import QPoint, Qt, QTimer
    from PyQt6.QtGui import QSurfaceFormat
    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget
    from tools.preview_benchmark_widgets import (
        BaselineCanvas,
        RasterCanvas,
        TextureCanvas,
        verify_owned_frames,
    )

    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.platform.windows.preview_owner import gui_window_identity

    fmt = QSurfaceFormat()
    fmt.setSwapInterval(0)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication([])
    verify_owned_frames()
    result: dict = {"renderer": None, "vendor": None, "errors": []}
    paints: list[float] = []
    callbacks: list[float] = []
    intervals: list[float] = []
    motion_intervals: list[float] = []

    host = QWidget()
    host.setWindowTitle(f"CephVR isolated preview cost probe: {args.mode}")
    layout = QHBoxLayout(host)
    if args.mode in {"raster", "texture"}:
        canvas = (
            RasterCanvas(args.streams, args.pixels, args.channels, paints)
            if args.mode == "raster"
            else TextureCanvas(args.streams, args.pixels, args.channels, paints, result)
        )
        slots = [canvas]
    else:
        slots = [
            BaselineCanvas(paints, result) if args.mode == "embedded" else QWidget()
            for _ in range(args.streams)
        ]
    embedded = args.mode in {"embedded", "raster", "texture"}
    sources = [motion_frame(args.pixels, 0, args.channels) for _ in range(args.streams)]
    for slot in slots:
        slot.setMinimumSize(128, 128)
        layout.addWidget(slot)
    host.setGeometry(80, 80, 1150, 420)
    host.show()
    app.processEvents()

    def measure_placement(key: str) -> rpc.PreviewWindowPlacement:
        slot = slots[int(key)]
        point = slot.mapToGlobal(QPoint(0, 0))
        scale = slot.devicePixelRatioF()
        # This probe rejects mixed/high DPI instead of guessing desktop transforms.
        if scale != 1:
            raise RuntimeError("Probe requires 100% GUI monitor scaling")
        return rpc.PreviewWindowPlacement(
            x=point.x(), y=point.y(), side=min(slot.width(), slot.height())
        )

    placements = {str(i): measure_placement(str(i)) for i in range(len(slots))}

    def refresh_placements() -> None:
        for key in placements:
            placements[key] = measure_placement(key)
        if native and native.is_alive():
            connection.send(("placement", placement_values()))

    def placement_values() -> list:
        return [(p.x, p.y, p.side) for p in placements.values()]

    layout_timer = QTimer()
    layout_timer.timeout.connect(refresh_placements)
    if args.mode == "native-follow":
        layout_timer.start(200)

    native = None

    def wait_with_events(predicate, seconds: float) -> bool:
        deadline = time.perf_counter() + seconds
        while not predicate() and time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.001)
        return predicate()

    if args.mode.startswith("native"):
        # The managed image name has no matching base-environment executable.
        multiprocessing.set_executable(
            str(Path(sys.executable).with_name("python.exe"))
        )
        connection, child_connection = multiprocessing.Pipe()
        native = multiprocessing.Process(
            target=native_viewer,
            args=(
                child_connection,
                args,
                gui_window_identity(int(host.winId())),
                placement_values(),
            ),
            daemon=True,
        )
        native.start()
        child_connection.close()
        if not wait_with_events(connection.poll, 15) or connection.recv() != "ready":
            raise RuntimeError("Native probe child did not become ready")
    start = time.perf_counter()
    cpu = time.process_time()
    measured_start = start
    warmed = False
    previous = start
    count = 0
    last_motion = start

    def move_host() -> None:
        nonlocal last_motion
        now = time.perf_counter()
        motion_intervals.append((now - last_motion) * 1000)
        last_motion = now
        phase = (now - start) * 2
        host.setGeometry(
            80 + round(25 * math.sin(phase)),
            80 + round(25 * math.cos(phase)),
            1150 + round(60 * math.sin(phase)),
            420 + round(35 * math.sin(phase)),
        )

    def tick() -> None:
        nonlocal previous, count, warmed, cpu, measured_start
        begin = time.perf_counter()
        if not warmed and begin - start >= 2:
            paints.clear()
            callbacks.clear()
            intervals.clear()
            motion_intervals.clear()
            if embedded:
                for slot in slots:
                    slot.metrics.reset()
            cpu = time.process_time()
            measured_start = begin
            warmed = True
            if native:
                connection.send(("measure", None))
        intervals.append((begin - previous) * 1000)
        previous = begin
        if embedded:
            for i, source in enumerate(sources):
                motion_frame(args.pixels, count + i * 9, args.channels, source)
            if args.mode == "embedded":
                for slot, source in zip(slots, sources, strict=True):
                    slot.submit([source], count, begin)
            else:
                canvas.submit(sources, count, begin)
        count += 1
        callbacks.append((time.perf_counter() - begin) * 1000)
        if warmed and begin - measured_start >= args.seconds:
            elapsed = time.perf_counter() - measured_start
            result["elapsed_seconds"] = elapsed
            result["cpu_core_percent"] = 100 * (time.process_time() - cpu) / elapsed
            frame_timer.stop()
            layout_timer.stop()
            motion_timer.stop()
            if native:
                connection.send(("stop", None))
                if not wait_with_events(connection.poll, 5):
                    raise RuntimeError("Native probe child did not report measurements")
                child_result = connection.recv()
                result["native_process"] = child_result
                result["cpu_core_percent"] += (
                    100 * child_result["cpu_seconds"] / elapsed
                )
                wait_with_events(lambda: not native.is_alive(), 5)
                native.join(0)
                if native.exitcode != 0:
                    raise RuntimeError(f"Native child exit: {native.exitcode}")
                connection.close()
            app.quit()

    frame_timer = QTimer()
    frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
    frame_timer.timeout.connect(tick)
    frame_timer.start(50)
    motion_timer = QTimer()
    motion_timer.setTimerType(Qt.TimerType.PreciseTimer)
    motion_timer.timeout.connect(move_host)
    if args.moving:
        motion_timer.start(16)
    app.exec()
    result.update(
        frame_callbacks=summary(callbacks),
        frame_intervals=summary(intervals),
        motion_intervals=summary(motion_intervals),
        qt_presentation=[
            {
                "age": summary(slot.metrics.ages),
                "intervals": summary(slot.metrics.swap_intervals),
                "skipped": slot.metrics.skipped,
            }
            for slot in slots
        ]
        if embedded
        else [],
        paint_cpu_submission=summary(paints),
        scope="Generated images; separate HighGUI process using production Win32 "
        "owner/geometry helpers; summed GUI and viewer process CPU; "
        "200ms placement sampling, 10ms native polling, 16ms geometry timer; "
        "age ends at raster paint completion or Qt frameSwapped, not screen scanout; "
        "no camera conversion, RPC, shared-memory IPC, recording or Tracking; "
        "GPU paint timing is CPU submission, not GPU completion",
    )
    frame_timer.stop()
    if args.verify and embedded:
        from tools.preview_benchmark_widgets import rectangles

        for index, slot in enumerate(slots):
            uploads_before = getattr(slot, "uploads", None)
            captured = (
                slot.grab().toImage()
                if args.mode == "raster"
                else slot.grabFramebuffer()
            )
            if uploads_before is not None:
                # The final queued source may need one upload; a second grab must not.
                uploads_after = slot.uploads
                slot.grabFramebuffer()
                assert slot.uploads == uploads_after
            rects = rectangles(
                slot.width(),
                slot.height(),
                1 if args.mode == "embedded" else args.streams,
            )
            for i, rect in enumerate(rects):
                x = round(rect.center().x())
                assert abs(captured.pixelColor(x, 1).red() - 200) <= 6
                assert (
                    abs(captured.pixelColor(x, int(rect.bottom()) - 2).red() - 80) <= 6
                )
                stream = index if args.mode == "embedded" else i
                bar_x = ((count - 1 + stream * 9) * 8) % (args.pixels - 32) + 16
                x = int(rect.x() + bar_x * rect.width() / args.pixels)
                assert (
                    abs(captured.pixelColor(x, int(rect.height() / 2)).red() - 220) <= 6
                )
            assert captured.save(str(args.output.with_suffix(f".{index}.png")))
        result["pixel_verification"] = (
            "orientation, stream content and redraw upload reuse passed"
        )
        if args.mode == "texture":
            uploads_before = canvas.uploads
            canvas.submit(sources, count + 1, time.perf_counter())
            canvas.submit(sources, count + 2, time.perf_counter())
            canvas.grabFramebuffer()
            assert canvas.uploaded == count + 2
            assert canvas.uploads - uploads_before == args.streams
            result["coalescing_verification"] = (
                "two pending submissions produce one latest upload"
            )
    if args.mode == "texture":
        result["texture_uploads"] = canvas.uploads
        result["source_batches"] = count
        canvas.release()
    result["presentation_endpoint"] = (
        "paint end"
        if args.mode == "raster"
        else "Qt frameSwapped or native imshow submission"
    )
    host.close()
    app.processEvents()
    if result["errors"]:
        raise RuntimeError(str(result["errors"]))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            "off",
            "native-fixed",
            "native-follow",
            "embedded",
            "raster",
            "texture",
            "readback",
        ],
        required=True,
    )
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--pixels", type=int, default=640)
    parser.add_argument("--streams", type=int, default=3)
    parser.add_argument("--moving", action="store_true")
    parser.add_argument("--channels", type=int, choices=[1, 3], default=3)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (
        1 <= args.seconds <= 120
        and 128 <= args.pixels <= 2048
        and 1 <= args.streams <= 4
    ):
        parser.error("duration 1..120s, pixels 128..2048, streams 1..4 required")
    assert summary([1.0, 2.0, 3.0])["mean_ms"] == 2.0
    result = readback(args) if args.mode == "readback" else presentation(args)
    result.update(
        mode=args.mode,
        moving=args.moving,
        pixels=args.pixels,
        streams=args.streams,
        channels=args.channels,
        interpreter=sys.executable,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
