"""Contained Arduino CLI compile/upload; controller owns handoff and outcome."""

import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.controller.microcontroller.firmware import FirmwareImage, read_uno_image
from cephvr.controller.microcontroller.firmware_source import FirmwareSketch
from cephvr.controller.microcontroller.identity import FIRMWARE_UPLOAD_ROLE
from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.platform.windows.security import (
    create_owner_only,
    create_owner_only_directory,
)
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher
from cephvr.shared.transport_deadlines import deadline_metadata


def arduino_cli() -> Path:
    """Resolve an installed tool; upload never installs cores or dependencies."""
    found = shutil.which("arduino-cli")
    candidates = ([Path(found)] if found else []) + [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe"
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "Arduino CLI was not found. Install Arduino IDE with its Uno AVR core, or add arduino-cli to PATH."
    )


class WindowsFirmwareUpload:
    """Reuse registered native-child/pipe ownership without encoding an output."""

    def __init__(self, launcher: SupervisedEncoderLauncher) -> None:
        self.launcher = launcher
        self._cancel = threading.Event()
        self._directory: Path | None = None
        self._image: Path | None = None
        self._cli: Path | None = None
        self._process: WindowsEncoderProcess | None = None
        self._plans: dict[str, wire.PlanLaunchRequest] = {}
        self._release_commands: dict[str, str] = {}
        launcher.registered_plan = self._retain_plan

    def _retain_plan(self, plan: wire.PlanLaunchRequest) -> None:
        self._plans[plan.command_id] = plan

    @property
    def cleanup_complete(self) -> bool:
        return not (
            self._directory
            or self._process
            or self._plans
            or self.launcher.pending_plans
        )

    def reset_cancel(self) -> None:
        if not self.cleanup_complete:
            raise RuntimeError("Previous firmware cleanup is unconfirmed.")
        self._cancel.clear()

    def _begin(self) -> None:
        if not self.cleanup_complete:
            raise RuntimeError("Previous firmware upload cleanup is unconfirmed.")
        if self._cancel.is_set():
            raise RuntimeError(
                "Firmware update cancelled before preparing native files."
            )
        self._cli = arduino_cli()
        self._directory = Path(tempfile.gettempdir()) / f"cephvr-firmware-{uuid4()}"
        create_owner_only_directory(self._directory)

    def prepare(self, image: FirmwareImage) -> None:
        self._begin()
        assert self._directory is not None
        self._image = self._directory / "firmware.hex"
        create_owner_only(self._image, image.payload)

    def upload(
        self, port: str, operation: control.OperationContext, *, deadline_ns: int
    ) -> None:
        if (
            not re.fullmatch(r"COM[1-9][0-9]*", port)
            or not self._image
            or not self._cli
        ):
            raise ValueError(
                "Firmware upload needs a prepared Uno image and available COM port."
            )
        try:
            self._run(
                [
                    "upload",
                    "--port",
                    port,
                    "--fqbn",
                    "arduino:avr:uno",
                    "--input-file",
                    str(self._image),
                    "--verify",
                ],
                operation,
                deadline_ns=deadline_ns,
                phase="upload/verification",
            )
        finally:
            self.close(deadline_ns=deadline_ns)

    def compile(
        self,
        sketch: FirmwareSketch,
        operation: control.OperationContext,
        *,
        deadline_ns: int,
    ) -> FirmwareImage:
        """Compile pinned source without serial access; retain only the validated image."""
        try:
            self._begin()
            assert self._directory is not None
            project = self._directory / sketch.path.stem
            create_owner_only_directory(project)
            for relative, payload in sketch.files:
                destination = project / relative
                for parent in reversed(relative.parents):
                    folder = project / parent
                    if not folder.exists():
                        create_owner_only_directory(folder)
                create_owner_only(destination, payload)
            build = self._directory / "build"
            output = self._directory / "output"
            create_owner_only_directory(build)
            create_owner_only_directory(output)
            self._run(
                [
                    "compile",
                    "--fqbn",
                    "arduino:avr:uno",
                    "--clean",
                    "--build-path",
                    str(build),
                    "--output-dir",
                    str(output),
                    str(project),
                ],
                operation,
                deadline_ns=deadline_ns,
                phase="compilation",
            )
            # Arduino CLI also exports a with-bootloader image; never select it.
            return read_uno_image(str(output / f"{sketch.path.name}.hex"))
        finally:
            self.close(deadline_ns=deadline_ns)

    def _run(
        self,
        arguments: list[str],
        operation: control.OperationContext,
        *,
        deadline_ns: int,
        phase: str,
    ) -> None:
        assert self._cli is not None
        if self._cancel.is_set():
            raise RuntimeError(f"Firmware {phase} cancelled before native launch.")
        self.launcher.bind_operation(control.WorkContext(), operation)
        self._process = self.launcher.launch(
            [str(self._cli), *arguments],
            deadline_ns=deadline_ns,
            role=FIRMWARE_UPLOAD_ROLE,
            capture_stdout=True,
        )
        process = self._process
        process.close_stdin(deadline_ns=deadline_ns)
        # Both phases retain the original deadline and reserve time for native closure.
        while self.launcher.windows_jobs.process_running(
            process.child.pid, process.child.creation_time_100ns
        ):
            if self._cancel.wait(0.05):
                raise RuntimeError(
                    f"Firmware {phase} cancelled; "
                    + (
                        "board image may be incomplete."
                        if phase == "upload/verification"
                        else "no upload attempted."
                    )
                )
            if self.launcher.clock_ns() >= deadline_ns - 2_000_000_000:
                raise TimeoutError(f"Firmware {phase} exceeded its operation budget.")
        code = process.wait(deadline_ns=deadline_ns)
        if code:
            details = (
                "\n".join(process.diagnostic_tail)[-2048:]
                or process.stdout_text[-2048:]
            )
            raise RuntimeError(f"Arduino {phase} failed (exit {code}): {details}")

    def cancel(self) -> None:
        self._cancel.set()

    def close(self, *, deadline_ns: int) -> None:
        process = self._process
        if process is not None and not process.cleanup_complete:
            self.launcher.windows_jobs.terminate_job(process.job_name)
            process.close_stdin(deadline_ns=deadline_ns)
            process.wait(deadline_ns=deadline_ns)
        for plan in self.launcher.pending_plans:
            self._plans[plan.command_id] = plan
        self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        # Private source/build/image removal is part of the native cleanup receipt.
        if self._image is not None:
            self._image.unlink(missing_ok=True)
            self._image = None
        if self._directory is not None:
            if self._directory.exists():
                shutil.rmtree(self._directory)
            self._directory = None
        for launch_id in tuple(self._plans):
            self._release(launch_id, deadline_ns, self._plans[launch_id])
            self._plans.pop(launch_id)
            self._release_commands.pop(launch_id, None)
        self._process = None

    def _release(
        self,
        launch_id: str,
        deadline_ns: int,
        expected: wire.PlanLaunchRequest | None = None,
    ) -> None:
        metadata = (*self.launcher.owner.metadata(), deadline_metadata(deadline_ns))
        timeout = max(0, (deadline_ns - self.launcher.clock_ns()) / 1e9)
        if timeout <= 0:
            raise TimeoutError("Firmware native cleanup missed its original deadline.")
        state = self.launcher.supervisor.GetLaunchState(
            wire.LaunchQuery(
                requester=self.launcher.owner_identity, launch_command_id=launch_id
            ),
            metadata=metadata,
            timeout=timeout,
        )
        if expected is not None and state.plan != expected:
            raise RuntimeError("Firmware cleanup resolves to a different launch.")
        process = self._process
        if (
            process is not None
            and launch_id == process.launch_id
            and (
                state.pid != process.child.pid
                or state.creation_time_100ns != process.child.creation_time_100ns
            )
        ):
            raise RuntimeError(
                "Firmware cleanup resolves to a different native process."
            )
        if state.phase == wire.LAUNCH_PHASE_RELEASED:
            return
        request = wire.ConfirmLaunchRequest(
            command_id=self._release_commands.setdefault(launch_id, str(uuid4())),
            launch_command_id=launch_id,
            owner=self.launcher.owner_identity,
            child=state.plan.child,
            native_cleanup_complete=True,
        )
        if state.HasField("pid"):
            request.pid = state.pid
            request.creation_time_100ns = state.creation_time_100ns
        receipt = self.launcher.supervisor.ConfirmLaunch(
            request,
            metadata=metadata,
            timeout=max(0, (deadline_ns - self.launcher.clock_ns()) / 1e9),
        )
        if (
            receipt.admission.result != control.COMMAND_RESULT_ACCEPTED
            or receipt.state.phase != wire.LAUNCH_PHASE_RELEASED
        ):
            raise RuntimeError(
                "Firmware native cleanup was not confirmed by the supervisor."
            )
