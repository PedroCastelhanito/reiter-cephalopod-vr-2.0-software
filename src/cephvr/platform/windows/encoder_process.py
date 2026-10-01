"""Owned FFmpeg process pipes, progress readers, exact exit, and cleanup."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.byte_stream import OverlappedPipe
from cephvr.platform.windows.file_sync import WindowsFileIdentity, WindowsFileSyncOwner
from cephvr.platform.windows.jobs import (
    SuspendedProcess,
    WindowsJobs,
)
from cephvr.shared.auth import Principal
from cephvr.shared.encoder_errors import EncoderLaunchError


class WindowsEncoderProcess:
    """Exact child handle, byte streams, bounded diagnostics, and progress reader."""

    def __init__(
        self,
        *,
        supervisor: services_pb2_grpc.SupervisorServiceStub,
        owner: Principal,
        owner_identity: types.ProcessIdentity,
        windows_jobs: WindowsJobs,
        launch_id: str,
        child: SuspendedProcess,
        job_name: str,
        input_pipe: OverlappedPipe,
        progress_pipe: OverlappedPipe,
        stderr_pipe: OverlappedPipe,
        output_path: Path | None,
        output_absent_before_launch: bool,
        capture_stdout: bool = False,
        negotiation: Any | None = None,
        stdout_max_bytes: int = 2 * 1024 * 1024,
        file_sync_owner: WindowsFileSyncOwner,
        diagnostic_tail_max_lines: int,
        diagnostic_tail_max_bytes: int,
        clock_ns: Callable[[], int],
    ) -> None:
        self.supervisor = supervisor
        self.owner = owner
        self.owner_identity = owner_identity
        self.windows_jobs = windows_jobs
        self.launch_id = launch_id
        self.child = child
        self.job_name = job_name
        self.input_pipe = input_pipe
        self.progress_pipe = progress_pipe
        self.stderr_pipe = stderr_pipe
        self.output_path = output_path
        self.output_absent_before_launch = output_absent_before_launch
        self.capture_stdout = capture_stdout
        self._negotiation = negotiation
        self.stdout_max_bytes = stdout_max_bytes
        self.file_sync_owner = file_sync_owner
        self.tail_max_lines = diagnostic_tail_max_lines
        self.tail_max_bytes = diagnostic_tail_max_bytes
        self.clock_ns = clock_ns
        self._lock = threading.Lock()
        self._progress_frame: int | None = None
        self._stderr = deque[tuple[str, int]]()
        self._stderr_bytes = 0
        self._stderr_partial = bytearray()
        self._threads: tuple[threading.Thread, ...] = ()
        self._exit_code: int | None = None
        self._cleanup_complete = False
        self._reader_error: BaseException | None = None
        self._output_identity: WindowsFileIdentity | None = None
        self._output_creation_identity: WindowsFileIdentity | None = None
        self._stdout = bytearray()
        self._stdin_closed = False
        self._reader_drain_deadline_ns: int | None = None

    @property
    def cleanup_complete(self) -> bool:
        return self._cleanup_complete

    @property
    def created_output(self) -> bool:
        return self.output_creation_identity is not None

    @property
    def output_creation_identity(self) -> WindowsFileIdentity | None:
        # A path that appears after launch is not proof that this child created it.
        # Keep the explicit slot for a future native creator receipt; absent that
        # evidence pre-T cleanup must preserve the artifact as unconfirmed.
        return self._output_creation_identity

    @property
    def progress_frame(self) -> int | None:
        with self._lock:
            return self._progress_frame

    @property
    def diagnostic_tail(self) -> tuple[str, ...]:
        with self._lock:
            lines = [item[0] for item in self._stderr]
            if self._stderr_partial:
                lines.append(self._stderr_partial.decode("utf-8", "replace"))
            return tuple(lines)

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    @property
    def stdout_text(self) -> str:
        with self._lock:
            return self._stdout.decode("utf-8", "replace")

    @property
    def reader_error(self) -> BaseException | None:
        with self._lock:
            return self._reader_error

    @property
    def negotiated(self) -> bool:
        with self._lock:
            return bool(
                self._negotiation is not None
                and getattr(self._negotiation, "complete", False)
            )

    def start_readers(self) -> None:
        progress = threading.Thread(
            target=self._read_progress, name="ffmpeg-progress", daemon=True
        )
        stderr = threading.Thread(
            target=self._read_stderr, name="ffmpeg-stderr", daemon=True
        )
        self._threads = (progress, stderr)
        for thread in self._threads:
            thread.start()

    def write(self, frame: memoryview | bytes, *, deadline_ns: int) -> None:
        self.input_pipe.write(frame, deadline_ns=deadline_ns)

    def begin_write(self, frame: memoryview | bytes, *, deadline_ns: int) -> None:
        """Start an overlapped stdin write without waiting for encoder capacity."""
        self.input_pipe.begin_write(frame, deadline_ns=deadline_ns)

    def poll_write(self) -> int | None:
        """Return transferred bytes, or None while the kernel still owns the write."""
        return self.input_pipe.poll_write()

    def check_negotiation(self) -> None:
        negotiation = self._negotiation
        if negotiation is None:
            raise EncoderLaunchError(
                "FFmpeg launch has no negotiated-format expectation"
            )
        with self._lock:
            if self._reader_error is not None:
                raise EncoderLaunchError(
                    f"FFmpeg pipe reader failed: {self._reader_error}"
                )
            error = getattr(negotiation, "error", None)
            if error is not None:
                raise EncoderLaunchError(str(error))

    def close_stdin(self, *, deadline_ns: int) -> None:
        if not self._stdin_closed:
            self.input_pipe.observe_cancelled(deadline_ns=deadline_ns)
            self.input_pipe.close()
            self._stdin_closed = True

    def wait(self, *, deadline_ns: int) -> int:
        if self._cleanup_complete and self.clock_ns() > deadline_ns:
            raise TimeoutError("FFmpeg cleanup completed after its original deadline")
        if not self._stdin_closed:
            raise EncoderLaunchError(
                "FFmpeg stdin must be closed before exit can prove local release"
            )
        if self._exit_code is None:
            self._exit_code = _wait_process(self.child, deadline_ns, self.clock_ns)
        if self._cleanup_complete:
            return self._exit_code
        if self.windows_jobs.inspect_launch_job(self.job_name):
            raise EncoderLaunchError(
                "FFmpeg launch job still owns descendants after encoder exit"
            )
        # Process/job absence should produce real pipe EOF. Let readers consume
        # buffered terminal progress and diagnostics before requesting cancellation.
        self._reader_drain_deadline_ns = deadline_ns
        for thread in self._threads:
            thread.join(_remaining(self.clock_ns, deadline_ns))
            if thread.is_alive():
                raise EncoderLaunchError(
                    "FFmpeg progress/diagnostic pipe cleanup is unconfirmed"
                )
        self.progress_pipe.observe_cancelled(deadline_ns=deadline_ns)
        self.stderr_pipe.observe_cancelled(deadline_ns=deadline_ns)
        self.progress_pipe.close()
        self.stderr_pipe.close()
        reader_error = self._reader_error
        self.windows_jobs.release_process(
            self.child.pid, self.child.creation_time_100ns
        )
        self.windows_jobs.close_launch_job(self.job_name)
        self._cleanup_complete = True
        if self.clock_ns() > deadline_ns:
            raise TimeoutError("FFmpeg cleanup completed after its original deadline")
        if reader_error is not None:
            raise EncoderLaunchError(f"FFmpeg pipe reader failed: {reader_error}")
        return self._exit_code

    def terminate(self, *, deadline_ns: int) -> None:
        if self._exit_code is None:
            self.windows_jobs.terminate_exact(
                self.child.pid, self.child.creation_time_100ns
            )
            self._exit_code = _wait_process(self.child, deadline_ns, self.clock_ns)
        if not self._stdin_closed:
            self.close_stdin(deadline_ns=deadline_ns)
        self.wait(deadline_ns=deadline_ns)

    def output_identity(self) -> object | None:
        if self.output_path is None:
            return None
        if self._output_identity is not None:
            return self._output_identity
        if not self.output_path.exists():
            return None
        self._output_identity = self.file_sync_owner.identity_for_path(self.output_path)
        # Capture the Windows file ID while this exact suspended-process owner is
        # still alive. Successful `-n` launch plus the pre-launch absence receipt
        # makes the first observed identity the child-created reserved artifact.
        if self.output_absent_before_launch and self._exit_code is None:
            self._output_creation_identity = self._output_identity
        return self._output_identity

    def _read_progress(self) -> None:
        pending = bytearray()
        while True:
            try:
                chunk = self.progress_pipe.read(
                    deadline_ns=self._reader_read_deadline()
                )
            except TimeoutError:
                if self._reader_deadline_expired():
                    self._record_reader_error(
                        EncoderLaunchError("FFmpeg progress pipe did not reach EOF")
                    )
                    return
                continue
            except Exception as exc:
                self._record_reader_error(exc)
                break
            if chunk is None:
                self._consume_progress_line(pending)
                break
            if self.capture_stdout:
                with self._lock:
                    if len(self._stdout) + len(chunk) > self.stdout_max_bytes:
                        self._reader_error = EncoderLaunchError(
                            "FFmpeg capability output exceeded its bounded capture"
                        )
                        return
                    self._stdout.extend(chunk)
                continue
            pending.extend(chunk)
            while b"\n" in pending:
                line, _, remainder = pending.partition(b"\n")
                pending[:] = remainder
                key, separator, value = line.strip().partition(b"=")
                if separator and key == b"frame":
                    try:
                        parsed = int(value)
                    except ValueError:
                        continue
                    with self._lock:
                        if (
                            self._progress_frame is None
                            or parsed > self._progress_frame
                        ):
                            self._progress_frame = parsed
            if len(pending) > 4096:
                self._record_reader_error(
                    EncoderLaunchError("FFmpeg progress line exceeded 4 KiB")
                )
                return

    def _read_stderr(self) -> None:
        while True:
            try:
                chunk = self.stderr_pipe.read(deadline_ns=self._reader_read_deadline())
            except TimeoutError:
                if self._reader_deadline_expired():
                    self._record_reader_error(
                        EncoderLaunchError("FFmpeg stderr pipe did not reach EOF")
                    )
                    return
                continue
            except Exception as exc:
                self._record_reader_error(exc)
                break
            if chunk is None:
                with self._lock:
                    final_line = bytes(self._stderr_partial)
                    self._stderr_partial.clear()
                    if final_line:
                        self._append_stderr(final_line)
                if final_line:
                    self._feed_negotiation(final_line)
                break
            lines: list[bytes] = []
            with self._lock:
                self._stderr_partial.extend(chunk)
                while b"\n" in self._stderr_partial:
                    line, _, remainder = self._stderr_partial.partition(b"\n")
                    self._stderr_partial[:] = remainder
                    raw_line = bytes(line)
                    if len(raw_line) > 16 * 1024:
                        self._reader_error = EncoderLaunchError(
                            "FFmpeg diagnostic line exceeded 16 KiB"
                        )
                        continue
                    self._append_stderr(raw_line)
                    lines.append(raw_line)
                if len(self._stderr_partial) > 16 * 1024:
                    self._reader_error = EncoderLaunchError(
                        "FFmpeg diagnostic line exceeded 16 KiB"
                    )
                    del self._stderr_partial[
                        : len(self._stderr_partial) - self.tail_max_bytes
                    ]
                self._trim_stderr()
            for diagnostic_line in lines:
                self._feed_negotiation(diagnostic_line)

    def _append_stderr(self, line: bytes) -> None:
        text = line.decode("utf-8", "replace")
        raw_bytes = len(line) + 1
        self._stderr.append((text, raw_bytes))
        self._stderr_bytes += raw_bytes
        self._trim_stderr()

    def _trim_stderr(self) -> None:
        while self._stderr and (
            len(self._stderr) > self.tail_max_lines
            or self._stderr_bytes > self.tail_max_bytes
        ):
            _, raw_bytes = self._stderr.popleft()
            self._stderr_bytes -= raw_bytes

    def _record_reader_error(self, error: BaseException) -> None:
        with self._lock:
            if self._reader_error is None:
                self._reader_error = error

    def _reader_read_deadline(self) -> int:
        return self._reader_drain_deadline_ns or self.clock_ns() + 1_000_000_000

    def _reader_deadline_expired(self) -> bool:
        deadline_ns = self._reader_drain_deadline_ns
        return deadline_ns is not None and self.clock_ns() >= deadline_ns

    def _consume_progress_line(self, pending: bytearray) -> None:
        if not pending:
            return
        key, separator, value = bytes(pending).strip().partition(b"=")
        if not separator or key != b"frame":
            return
        try:
            parsed = int(value)
        except ValueError:
            return
        with self._lock:
            if self._progress_frame is None or parsed > self._progress_frame:
                self._progress_frame = parsed

    def _feed_negotiation(self, line: bytes) -> None:
        negotiation = self._negotiation
        if negotiation is None:
            return
        try:
            decoded = line.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return
        with self._lock:
            negotiation.feed(decoded)
            if negotiation.error is not None:
                if self._reader_error is None:
                    self._reader_error = EncoderLaunchError(negotiation.error)


def _remaining(clock_ns: Callable[[], int], deadline_ns: int) -> float:
    remaining = deadline_ns - clock_ns()
    if remaining <= 0:
        raise TimeoutError("registered FFmpeg operation missed its original deadline")
    return remaining / 1_000_000_000


def _wait_process(
    child: SuspendedProcess, deadline_ns: int, clock_ns: Callable[[], int]
) -> int:
    import ctypes
    from ctypes import wintypes

    kernel = cast(Any, ctypes).WinDLL("kernel32", use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    remaining = deadline_ns - clock_ns()
    if remaining <= 0:
        raise TimeoutError("exact FFmpeg process exit missed its original deadline")
    timeout_ms = min((remaining + 999_999) // 1_000_000, 0xFFFFFFFE)
    result = kernel.WaitForSingleObject(child.process_handle, timeout_ms)
    if result != 0:
        raise TimeoutError("exact FFmpeg process exit missed its original deadline")
    if clock_ns() > deadline_ns:
        raise TimeoutError("FFmpeg process completed after its original deadline")
    exit_code = wintypes.DWORD()
    if not kernel.GetExitCodeProcess(child.process_handle, exit_code):
        raise EncoderLaunchError(
            f"GetExitCodeProcess failed: {cast(Any, ctypes).get_last_error()}"
        )
    return int(exit_code.value)
