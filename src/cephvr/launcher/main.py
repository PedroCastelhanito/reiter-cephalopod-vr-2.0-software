"""Persistent Windows application-job owner and final shutdown backstop (E08)."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import queue
import secrets
import sys
import threading
import time
import tomllib
from pathlib import Path
from uuid import uuid4

from cephvr.controller.configuration import load_controller_configuration
from cephvr.launcher.decisions import (
    LOST_KEY,
    MAX_LINE_BYTES,
    LauncherDecisions,
    parse_notification_line,
)
from cephvr.platform.windows.bootstrap import (
    close_handle,
    create_bootstrap_pipe,
    create_control_pipe,
    write_bootstrap,
)
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.platform.windows.jobs import WindowsJobs, WindowsLaunchError
from cephvr.shared.clock import host_time_ns
from cephvr.shared.credentials import default_runtime_root
from cephvr.shared.recovery import ApplicationExitReceipt, RecoveryStore


def _read_notifications(
    handle: int, output: queue.Queue[dict[str, object]], channel: str
) -> None:
    """Forward notifications; any EOF or protocol violation retires the channel."""
    import msvcrt

    def emit(notification: dict[str, object]) -> bool:
        notification["_channel"] = channel
        try:
            output.put_nowait(notification)
        except queue.Full:
            return False
        return True

    def lost(reason: str) -> None:
        marker: dict[str, object] = {"kind": "channel_lost", LOST_KEY: reason}
        while not emit(marker):
            try:
                output.get_nowait()  # The loss marker outranks any queued note.
            except queue.Empty:
                pass

    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    with os.fdopen(fd, "rb", buffering=0) as stream:
        while True:
            parsed = parse_notification_line(stream.readline(MAX_LINE_BYTES + 1))
            if isinstance(parsed, str):
                lost(parsed)
                return
            if not emit(parsed):
                lost("notification queue overflow")
                return


def _retain_until_empty(
    native: WindowsJobs, job_name: str, deadline_ns: int, verify_timeout_ns: int
) -> None:
    """Keep the sole job handle and guard until OS membership is provably empty."""
    terminated = False
    warned = False
    while True:
        try:
            if not native.inspect_launch_job(job_name):
                return
        except WindowsLaunchError:
            pass  # Unknown membership cannot release the application guard.
        now = host_time_ns()
        if now >= deadline_ns and not terminated:
            try:
                native.terminate_job(job_name)
            except WindowsLaunchError:
                pass
            else:
                terminated = True
        if now >= deadline_ns + verify_timeout_ns and not warned:
            sys.stderr.write(
                "CephVR application job absence remains unverified; retaining guard and job handle.\n"
            )
            warned = True
        time.sleep(0.05)


def run_launcher(
    *, software_root: Path, supervisor_config: Path, interpreter: Path
) -> None:
    if sys.platform != "win32":
        raise WindowsLaunchError("CephVR managed launch requires Windows")
    required_modules = {
        "acquisition": "cephvr.acquisition.main",
        "vr": "cephvr.vr.main",
        "tracking": "cephvr.tracking.main",
        "gui": "cephvr.gui.main",
    }
    missing = []
    for role, module in required_modules.items():
        try:
            present = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            present = False
        if not present:
            missing.append(role)
    if missing:
        raise WindowsLaunchError(
            "required managed bootstrap modules are unavailable: " + ", ".join(missing)
        )
    if (
        supervisor_config.resolve()
        != (software_root / "config/backends/supervisor_config.toml").resolve()
    ):
        raise ValueError("supervisor config must belong to the selected software root")
    resolved = load_controller_configuration(software_root)
    policy_root = supervisor_config.parents[2] / "contracts" / "policy"
    backend_ports: dict[str, int] = {}
    for role in ("acquisition", "vr", "tracking"):
        with (supervisor_config.parent / f"{role}_config.toml").open("rb") as stream:
            backend_config = tomllib.load(stream)
        with (policy_root / f"{role}_policy.toml").open("rb") as stream:
            backend_policy = tomllib.load(stream)
        if type(backend_config.get("policy_version")) is not int or backend_config[
            "policy_version"
        ] != backend_policy.get("policy_version"):
            raise ValueError(f"{role} config/policy version mismatch")
        backend_port = backend_config["rpc"]["port"]
        if type(backend_port) is not int or not 1 <= backend_port <= 65535:
            raise ValueError(f"{role} rpc.port must be an integer in 1..65535")
        backend_ports[role] = backend_port
    if (
        len(
            {
                resolved.controller_port,
                resolved.supervisor_startup.port,
                *backend_ports.values(),
            }
        )
        != 5
    ):
        raise ValueError("backend/controller/supervisor service ports collide")
    startup = resolved.supervisor_startup
    backstop_ns = startup.application_backstop_ns
    port = startup.port
    supervisor_generation = str(uuid4())
    controller_generation = str(uuid4())
    supervisor_token = secrets.token_urlsafe(48)
    controller_token = secrets.token_urlsafe(48)
    native = WindowsJobs()
    with SingleInstanceGuard("application"):
        application_job = native.create_application_job()
        decisions: LauncherDecisions | None = None
        try:
            bootstrap_read, bootstrap_write = create_bootstrap_pipe()
            control_read, control_write = create_control_pipe()
            controller_control_read, controller_control_write = create_control_pipe()
            ack_read, ack_write = create_bootstrap_pipe()
            child = native.launch_suspended(
                str(interpreter),
                [
                    "-m",
                    "cephvr.supervisor.main",
                    "--bootstrap-handle",
                    str(bootstrap_read),
                    "--launcher-control-handle",
                    str(control_write),
                    "--launcher-controller-control-handle",
                    str(controller_control_write),
                    "--launcher-ack-handle",
                    str(ack_read),
                ],
                [application_job],
                (bootstrap_read, control_write, controller_control_write, ack_read),
            )
            members = native.inspect_launch_job(application_job)
            if len(members) != 1 or members[0][:2] != (
                child.pid,
                child.creation_time_100ns,
            ):
                native.terminate_exact(child.pid, child.creation_time_100ns)
                raise WindowsLaunchError("supervisor not contained at creation")
            native.resume(child)
            close_handle(bootstrap_read)
            close_handle(control_write)
            close_handle(controller_control_write)
            close_handle(ack_read)
            bootstrap_descriptor = {
                "software_root": str(software_root),
                "supervisor_generation": supervisor_generation,
                "controller_generation": controller_generation,
                "supervisor_token": supervisor_token,
                "controller_token": controller_token,
                "supervisor_port": port,
                "controller_port": resolved.controller_port,
                "backend_ports": backend_ports,
                "max_message_bytes": resolved.max_message_bytes,
                "max_retained_incidents": resolved.max_retained_incidents,
                "command_retention_ns": resolved.policies.command_retention_after_finalization_ns,
                # Reuse the controller's single resolved policy instance for
                # acquisition sessionless configuration-worker startup.
                "control_policies": base64.b64encode(
                    resolved.policies.SerializeToString(deterministic=True)
                ).decode("ascii"),
                "silence_timeout_ns": startup.silence_timeout_ns,
                "heartbeat_interval_ns": startup.heartbeat_interval_ns,
                "emergency_timeout_ns": startup.emergency_timeout_ns,
                "graceful_exit_ns": startup.graceful_exit_ns,
                "terminate_exit_ns": startup.terminate_exit_ns,
                "application_backstop_ns": startup.application_backstop_ns,
                "supervisor_config": str(supervisor_config),
                "interpreter": str(interpreter),
                "supervisor_pid": child.pid,
                "supervisor_creation_time_100ns": child.creation_time_100ns,
            }
            decisions = LauncherDecisions(
                supervisor_generation=supervisor_generation,
                controller_generation=controller_generation,
                backstop_ns=backstop_ns,
                registration_window_ns=startup.silence_timeout_ns,
                launched_ns=host_time_ns(),
            )
            bootstrap_done = threading.Event()
            bootstrap_seen = False
            bootstrap_error: list[BaseException] = []

            def send_bootstrap() -> None:
                try:
                    write_bootstrap(bootstrap_write, bootstrap_descriptor)
                except BaseException as exc:
                    bootstrap_error.append(exc)
                finally:
                    bootstrap_done.set()

            threading.Thread(
                target=send_bootstrap, daemon=True, name="cephvr-bootstrap"
            ).start()
            notifications: queue.Queue[dict[str, object]] = queue.Queue(maxsize=64)
            threading.Thread(
                target=_read_notifications,
                args=(control_read, notifications, "supervisor"),
                daemon=True,
            ).start()
            threading.Thread(
                target=_read_notifications,
                args=(controller_control_read, notifications, "controller"),
                daemon=True,
            ).start()
            while True:
                now = host_time_ns()
                if not bootstrap_seen and bootstrap_done.is_set():
                    bootstrap_seen = True
                    decisions.bootstrap_finished(now, ok=not bootstrap_error)
                decisions.tick(now)
                for _ in range(64):
                    try:
                        note = notifications.get_nowait()
                    except queue.Empty:
                        break
                    kind = note.get("kind")
                    if kind == "register_controller":
                        accepted = decisions.on_register_controller(now, note)
                        if accepted is not None:
                            pid, created = accepted
                            native.retain_exact(pid, created, str(interpreter))
                            decisions.controller_acknowledged(pid, created)
                            import msvcrt

                            ack_fd = msvcrt.open_osfhandle(ack_write, os.O_WRONLY)
                            os.write(ack_fd, b"A")
                            os.close(ack_fd)
                            ack_write = 0
                    elif kind == "channel_lost":
                        channel = str(note.get("_channel"))
                        reason = str(note.get(LOST_KEY))
                        decisions.on_channel_lost(now, channel, reason)
                        # The controller reason also goes into the exit receipt.
                        sys.stderr.write(
                            f"CephVR launcher {channel} channel lost: {reason}\n"
                        )
                    elif kind == "shutdown":
                        decisions.on_shutdown(now, note)
                if not native.process_running(child.pid, child.creation_time_100ns):
                    decisions.arm(now)
                if decisions.controller is not None and not native.process_running(
                    *decisions.controller
                ):
                    decisions.arm(now)
                if decisions.shutdown_deadline_ns is not None:
                    members = native.inspect_launch_job(application_job)
                    if not members:
                        return
                    if now >= decisions.shutdown_deadline_ns:
                        native.terminate_job(application_job)
                        absence_deadline = host_time_ns() + 2_000_000_000
                        while (
                            native.inspect_launch_job(application_job)
                            and host_time_ns() < absence_deadline
                        ):
                            time.sleep(0.05)
                        if native.inspect_launch_job(application_job):
                            raise WindowsLaunchError(
                                "application job termination did not prove member absence"
                            )
                        return
                time.sleep(0.1)
        finally:
            _retain_until_empty(
                native,
                application_job,
                (decisions and decisions.shutdown_deadline_ns)
                or host_time_ns() + backstop_ns,
                startup.terminate_exit_ns,
            )
            try:
                # The launcher alone owns the outer Job handle. Its empty OS
                # membership is the only evidence this receipt can assert.
                RecoveryStore(default_runtime_root()).write_exit_receipt(
                    ApplicationExitReceipt(
                        controller_generation=controller_generation,
                        supervisor_generation=supervisor_generation,
                        observed_monotonic_ns=host_time_ns(),
                        all_owned_processes_absent=True,
                        controller_channel_loss=(
                            decisions.lost_channels.get("controller", "")[:256]
                            if decisions
                            else ""
                        ),
                    )
                )
            finally:
                native.close_launch_job(application_job)


def main() -> None:
    parser = argparse.ArgumentParser(description="CephVR Windows application launcher")
    parser.add_argument("--software-root", type=Path, required=True)
    parser.add_argument("--supervisor-config", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    run_launcher(
        software_root=args.software_root.resolve(),
        supervisor_config=args.supervisor_config.resolve(),
        interpreter=args.python.resolve(),
    )


if __name__ == "__main__":
    main()
