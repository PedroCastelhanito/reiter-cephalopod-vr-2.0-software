"""Contained FFmpeg child and exact Windows review-file durability owner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.platform.windows.file_sync import WindowsVideoSync, WindowsVideoSyncFactory
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher
from cephvr.visual_stimulus.identity import FFMPEG_ROLE
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


class EncoderInputBinder(Protocol):
    def bind_process(self, process: WindowsEncoderProcess) -> None: ...


@dataclass(frozen=True, slots=True)
class EncoderFinalization:
    exit_code: int
    output_identity: object | None
    artifact_present: bool
    artifact_created_by_session: bool
    file_sync_and_close_confirmed: bool


class EncoderTrialOwner:
    """Own one contained child, output file identity, sync handle, and cleanup."""

    def __init__(
        self,
        launcher: SupervisedEncoderLauncher,
        video_sync_factory: WindowsVideoSyncFactory,
        *,
        clock_ns: Callable[[], int],
    ) -> None:
        self.launcher = launcher
        self.video_sync_factory = video_sync_factory
        self.clock_ns = clock_ns
        self.process: WindowsEncoderProcess | None = None
        self.video_sync: WindowsVideoSync | None = None
        self.last_sync_ns = 0
        self.launch_attempted = False
        self.cleanup_confirmed = True

    def start(
        self,
        argv: list[str],
        request: visual_stimulus.WorkerSchedule,
        output_path: Path,
        input_adapter: EncoderInputBinder,
    ) -> None:
        self.launch_attempted = True
        self.cleanup_confirmed = False
        process = self.launcher.launch(
            argv,
            deadline_ns=request.command.deadline_monotonic_ns,
            role=FFMPEG_ROLE,
            output_path=output_path,
        )
        self.process = process
        input_adapter.bind_process(process)

    def periodic_sync(
        self,
        output_path: Path,
        *,
        interval_ns: int,
    ) -> None:
        if self.clock_ns() - self.last_sync_ns < interval_ns:
            return
        process = self.process
        if process is None:
            return
        identity = process.output_identity()
        if identity is None:
            return
        if self.video_sync is None:
            self.video_sync = self.video_sync_factory.open(output_path, identity)
        elif self.video_sync.file_identity != identity:
            raise RuntimeError(
                "FFmpeg review-video file identity changed during recording"
            )
        self.video_sync.sync()
        self.last_sync_ns = self.clock_ns()

    def finalize(self, output_path: Path, deadline_ns: int) -> EncoderFinalization:
        process = self.process
        if process is None:
            raise RuntimeError("review encoder child ownership is absent")
        process.output_identity()
        process.close_stdin(deadline_ns=deadline_ns)
        exit_code = process.wait(deadline_ns=deadline_ns)
        identity = process.output_identity()
        synced = False
        if identity is not None:
            sync = self.video_sync or self.video_sync_factory.open(
                output_path, identity
            )
            try:
                sync.sync()
                synced = True
            finally:
                sync.close()
                self.video_sync = None
        self.cleanup_confirmed = process.cleanup_complete
        return EncoderFinalization(
            exit_code=exit_code,
            output_identity=identity,
            artifact_present=identity is not None,
            artifact_created_by_session=process.output_creation_identity is not None,
            file_sync_and_close_confirmed=synced,
        )

    def cleanup(self, deadline_ns: int) -> None:
        if self.video_sync is not None:
            try:
                self.video_sync.close()
            finally:
                self.video_sync = None
        if self.process is not None:
            if not self.process.cleanup_complete:
                self.process.terminate(deadline_ns=deadline_ns)
            self.cleanup_confirmed = self.process.cleanup_complete
            return
        if self.launch_attempted and not self.cleanup_confirmed:
            self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
            self.cleanup_confirmed = True

    def reset(self) -> None:
        if not self.cleanup_complete:
            raise RuntimeError("cannot reset an unconfirmed FFmpeg child owner")
        self.process = None
        self.video_sync = None
        self.last_sync_ns = 0
        self.launch_attempted = False
        self.cleanup_confirmed = True

    @property
    def cleanup_complete(self) -> bool:
        return (
            self.process.cleanup_complete
            if self.process is not None
            else self.cleanup_confirmed
        )
