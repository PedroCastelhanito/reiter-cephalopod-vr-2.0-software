"""Contained, read-only FFmpeg help probe for Setup capability discovery."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from cephvr.acquisition.identity import FFMPEG_PROBE_ROLE
from cephvr.acquisition.recording.capabilities import ProbeResult
from cephvr.acquisition.recording.encoder import SupervisedEncoderLauncher
from cephvr.acquisition.recording.encoder_errors import EncoderLaunchError
from cephvr.acquisition.recording.encoder_process import WindowsEncoderProcess
from cephvr.control.v1 import types_pb2 as types


class SupervisedCapabilityProbe:
    """Run FFmpeg help commands under the exact Setup worker/job identity.

    `resource_released` is the worker-owned lifecycle reporter. It reports only
    after the process, pipe and job handles are locally reconciled; the
    supervisor separately proves the exact job is empty.
    """

    def __init__(
        self,
        launcher: SupervisedEncoderLauncher,
        work: types.WorkContext,
        parent_operation: types.OperationContext,
        resource_released: Callable[[str, bool], None],
    ) -> None:
        self.launcher = launcher
        self.work = types.WorkContext.FromString(work.SerializeToString())
        self.parent_operation = types.OperationContext.FromString(
            parent_operation.SerializeToString()
        )
        self.resource_released = resource_released
        self._unresolved: list[WindowsEncoderProcess] = []

    def run(
        self, executable: str, args: Sequence[str], *, deadline_ns: int
    ) -> ProbeResult:
        if self._unresolved:
            raise EncoderLaunchError(
                "prior FFmpeg capability helper cleanup remains unresolved"
            )
        self.launcher.bind_operation(self.work, self.parent_operation)
        try:
            process = self.launcher.launch(
                (executable, *args),
                deadline_ns=deadline_ns,
                role=FFMPEG_PROBE_ROLE,
                output_path=None,
                capture_stdout=True,
            )
        except BaseException:
            self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
            raise
        self._unresolved.append(process)
        process.close_stdin(deadline_ns=deadline_ns)
        exit_code = process.wait(deadline_ns=deadline_ns)
        result = ProbeResult(
            returncode=exit_code,
            stdout=process.stdout_text,
            stderr="\n".join(process.diagnostic_tail),
        )
        self.resource_released(f"ffmpeg:{process.launch_id}", True)
        self._unresolved.remove(process)
        return result

    def retry_cleanup(self, *, deadline_ns: int) -> None:
        """Bounded cleanup retry; unresolved processes remain explicitly owned."""
        self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        for process in tuple(self._unresolved):
            process.terminate(deadline_ns=deadline_ns)
            self.resource_released(f"ffmpeg:{process.launch_id}", True)
            self._unresolved.remove(process)
