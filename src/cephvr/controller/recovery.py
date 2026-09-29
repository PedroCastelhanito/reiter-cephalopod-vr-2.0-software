"""Explicit E04 recovery of one known unfinished session after verified exit.

No output is scanned or certified. Intact administrative logs receive missing
terminal outcomes; incomplete logs are preserved and a separate report records
the uncertainty. A lost write result is never retried in this process.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import stat
import threading
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.storage import (
    MetadataWrite,
    MetadataWriter,
    OutputReservation,
    StorageError,
)
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.shared.clock import host_time_ns, require_int64_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import RecoveryStore, UnfinishedSessionPointer


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"invalid JSON number {value}")


def _read_file(path: Path, limit: int) -> tuple[bytes, os.stat_result]:
    if type(limit) is not int or limit < 1:
        raise StorageError("recovery input has no positive inspection byte budget")
    before = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_file_attributes", 0) & 0x400
    ):
        raise StorageError("recovery input is not a regular, non-reparse file")
    with os.fdopen(
        os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        ),
        "rb",
    ) as stream:
        actual = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(actual.st_mode)
            or getattr(actual, "st_file_attributes", 0) & 0x400
            or (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino)
            or actual.st_size > limit
        ):
            raise StorageError("recovery input changed or exceeds the inspection bound")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise StorageError("recovery input exceeds the inspection bound")
    return raw, actual


async def _open_existing_bounded(
    directory: Path, session_id: str, generation: str, timeout_s: float
) -> OutputReservation:
    """A late lock acquisition after timeout must release its own OS handle."""
    if timeout_s <= 0:
        raise TimeoutError("startup recovery lock deadline expired")
    result: Future[OutputReservation] = Future()

    def worker() -> None:
        try:
            reservation = OutputReservation.open_existing(
                directory, session_id, generation
            )
        except BaseException as exc:
            result.set_exception(exc)
        else:
            result.set_result(reservation)

    threading.Thread(target=worker, daemon=True, name="cephvr-recovery-lock").start()
    try:
        return await asyncio.wait_for(
            asyncio.shield(asyncio.wrap_future(result)), timeout_s
        )
    except BaseException:

        def release_late(completed: Future[OutputReservation]) -> None:
            try:
                reservation = completed.result()
            except BaseException:
                return  # Failed opens have no reservation handle.
            try:
                reservation.release()
            except Exception:
                logging.getLogger(__name__).exception(
                    "late startup recovery lock release failed"
                )

        result.add_done_callback(release_late)
        raise


@dataclass(frozen=True)
class RecoveryInspection:
    marker_digest: str
    marker_bytes: bytes
    log_identity: tuple[int, int, int] | None
    log_digest: str | None
    config_digest: str | None
    zone: str
    session_started: bool
    session_ended: bool
    recovery_recorded: bool
    unfinished_trials: tuple[int, ...]
    spikeglx_stop_unconfirmed: bool
    spikeglx_endpoint: tuple[str, int] | None
    spikeglx_run: str | None
    issue: str | None


def inspect_recovery(
    reservation: OutputReservation, max_bytes: int
) -> RecoveryInspection:
    if type(max_bytes) is not int or max_bytes <= 4096:
        raise StorageError("recovery inspection byte budget is too small")
    if reservation._lock_fd is None:
        raise StorageError("recovery inspection requires held reservation")
    marker, _ = _read_file(reservation.marker, 4096)
    digest = hashlib.sha256(marker).hexdigest()
    if reservation.marker_issue in {
        "reservation marker identity mismatch",
        "reservation marker already complete",
    }:
        raise StorageError(reservation.marker_issue)
    known_run: str | None = None
    known_endpoint: tuple[str, int] | None = None
    known_paired: bool | None = None
    try:
        config_raw, _ = _read_file(
            reservation.protocol_directory / "SESSION_CONFIG.json", max_bytes
        )
        config = json.loads(
            config_raw, object_pairs_hook=_pairs, parse_constant=_constant
        )
        if (
            not isinstance(config, dict)
            or type(config.get("schema_version")) is not int
            or config["schema_version"] != 1
            or config.get("session_id") != reservation.session_id
            or config.get("controller_generation") != reservation.generation
        ):
            raise ValueError("session configuration identity/schema is unconfirmed")
        zone = config["local_timezone"]
        if not isinstance(zone, str):
            raise ValueError("session timezone is invalid")
        ZoneInfo(zone)
        if not isinstance(config.get("trials"), list):
            raise ValueError("session trial plan is invalid")
        trial_numbers = [item["context"]["trial_number"] for item in config["trials"]]
        if (
            not trial_numbers
            or any(type(number) is not int or number < 1 for number in trial_numbers)
            or len(set(trial_numbers)) != len(trial_numbers)
        ):
            raise ValueError("session trial plan numbers are invalid")
        trials = set(trial_numbers)
        remaining = max_bytes - len(config_raw)
        if remaining < 1:
            raise ValueError("session log has no remaining inspection byte budget")
        raw, info = _read_file(
            reservation.protocol_directory / "SESSION_LOG.jsonl",
            remaining,
        )
        if not raw or not raw.endswith(b"\n"):
            raise ValueError("session log is empty or its final line is incomplete")
        started: set[int] = set()
        finished: set[int] = set()
        session_started = session_ended = recovery_recorded = False
        configuration = config.get("configuration")
        if not isinstance(configuration, dict) or not isinstance(
            configuration.get("backends"), list
        ):
            raise ValueError("session backend configuration is invalid")
        spikeglx = config.get("spikeglx")
        run = spikeglx.get("run_name") if isinstance(spikeglx, dict) else None
        paired = any(
            item.get("backend_name") == "synchronization"
            and item.get("enabled") is True
            for item in configuration["backends"]
        )
        if paired and (not isinstance(run, str) or not run):
            raise ValueError("paired SpikeGLX run identity is unavailable")
        endpoint: tuple[str, int] | None = None
        endpoint_data = spikeglx
        if paired and isinstance(endpoint_data, dict):
            address, port = endpoint_data.get("address"), endpoint_data.get("port")
            if (
                isinstance(address, str)
                and address
                and type(port) is int
                and 1 <= port <= 65535
            ):
                endpoint = (address, port)
        known_paired = paired
        known_run = run if isinstance(run, str) and run else None
        known_endpoint = endpoint
        stopped_remote = False
        catalog = {
            "session_started",
            "trial_started",
            "trial_finished",
            "session_ended",
            "command_accepted",
            "setup_override",
            "error",
            "recovery",
            "spikeglx_started",
            "spikeglx_stopped",
            "incident_decision",
        }
        for line in raw.splitlines():
            if recovery_recorded:
                raise ValueError("session log contains data after final recovery")
            event = json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant)
            if (
                not isinstance(event, dict)
                or event.get("event_type") not in catalog
                or type(event.get("monotonic_ns")) is not int
                or event["monotonic_ns"] < 0
                or not isinstance(event.get("source"), str)
                or event.get("details") is not None
                and not isinstance(event["details"], dict)
            ):
                raise ValueError("session log event shape is unconfirmed")
            wall = datetime.fromisoformat(event["wall_time"])
            if wall.tzinfo is None:
                raise ValueError("session log wall time lacks an offset")
            kind = event["event_type"]
            if kind == "session_started":
                if session_started or session_ended:
                    raise ValueError("session log repeats activation")
                session_started = True
            elif kind == "session_ended":
                if not session_started or session_ended or started != finished:
                    raise ValueError("session log terminal outcome is inconsistent")
                session_ended = True
            elif kind in {"trial_started", "trial_finished"}:
                number = event.get("trial_number")
                if (
                    type(number) is not int
                    or number not in trials
                    or not session_started
                ):
                    raise ValueError("session log trial identity is unconfirmed")
                if kind == "trial_started":
                    if number in started or session_ended or started != finished:
                        raise ValueError("session log repeats a trial start")
                    started.add(number)
                else:
                    if number not in started or number in finished:
                        raise ValueError("session log trial completion is inconsistent")
                    finished.add(number)
            elif kind == "spikeglx_stopped" and run:
                stopped_remote = event.get("details", {}).get("run_name") == run
            elif kind == "recovery":
                if (
                    event.get("outcome") != "completed"
                    or not session_ended
                    or started != finished
                ):
                    raise ValueError("prior recovery has no completed outcome")
                recovery_recorded = True
        if not session_started or session_ended and started != finished:
            raise ValueError("session lifecycle is incomplete or out of order")
        return RecoveryInspection(
            digest,
            marker,
            (info.st_dev, info.st_ino, info.st_size),
            hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(config_raw).hexdigest(),
            zone,
            session_started,
            session_ended,
            recovery_recorded,
            tuple(sorted(started - finished)),
            paired and not stopped_remote,
            endpoint,
            run,
            reservation.marker_issue,
        )
    except (
        OSError,
        StorageError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        # The original files remain byte-for-byte untouched. No outcome is inferred.
        return RecoveryInspection(
            digest,
            marker,
            None,
            None,
            None,
            "UTC",
            False,
            False,
            False,
            (),
            known_paired is not False,
            known_endpoint,
            known_run,
            f"administrative log/configuration inspection unconfirmed: {exc}",
        )


class StartupRecovery:
    """One held reservation and one explicit, bounded operator recovery attempt."""

    def __init__(
        self,
        store: RecoveryStore,
        *,
        current_generation: str,
        timeout_ns: int,
        max_operations: int,
        max_bytes: int,
    ):
        self.current_generation = require_uuid4(current_generation)
        require_int64_ns(timeout_ns)
        if timeout_ns <= 0 or max_operations < 1 or max_bytes <= 4096:
            raise ValueError("startup recovery time/capacity bounds are invalid")
        self.store = store
        self.timeout_ns = timeout_ns
        self.max_operations = max_operations
        self.max_bytes = max_bytes
        self.pointer: UnfinishedSessionPointer | None = None
        self.reservation: OutputReservation | None = None
        self.inspection: RecoveryInspection | None = None
        self.writer: MetadataWriter | None = None
        self.attempted = False
        self.operation_id = str(uuid.uuid4())

    async def prepare(
        self, query: Callable[[str], Awaitable[svc.RecoverySnapshot]]
    ) -> pb.Prompt | None:
        if self.reservation is not None or self.attempted:
            raise StorageError("startup recovery was already prepared or attempted")
        deadline = host_time_ns() + self.timeout_ns
        self.pointer = await run_pipe_io_daemon(
            self.store.read_pointer, timeout_s=self.timeout_ns / 1e9
        )
        pointer = self.pointer
        if pointer is None:
            return None
        proof = await asyncio.wait_for(
            query(pointer.controller_generation),
            max(0, (deadline - host_time_ns()) / 1e9),
        )
        receipt = proof.prior_application_exit
        if (
            not proof.HasField("prior_application_exit")
            or receipt.controller_generation != pointer.controller_generation
            or receipt.supervisor_generation != pointer.supervisor_generation
            or receipt.format_version != 1
            or not receipt.all_owned_processes_absent
            or receipt.observed_monotonic_ns <= 0
        ):
            raise StorageError(
                "prior application process absence is unconfirmed; old files are preserved and Setup is blocked"
            )
        self.reservation = await _open_existing_bounded(
            Path(pointer.session_directory),
            pointer.session_id,
            pointer.controller_generation,
            max(0, (deadline - host_time_ns()) / 1e9),
        )
        reservation = self.reservation
        if reservation.marker_issue == "reservation marker already complete":
            # A crash can happen after durable marker completion but before pointer clear.
            try:
                await run_pipe_io_daemon(
                    lambda: self.store.clear_pointer(pointer),
                    timeout_s=max(0, (deadline - host_time_ns()) / 1e9),
                )
            finally:
                reservation.release()
                self.reservation = None
            return None
        try:
            self.inspection = await run_pipe_io_daemon(
                lambda: inspect_recovery(reservation, self.max_bytes),
                timeout_s=max(0, (deadline - host_time_ns()) / 1e9),
            )
        except BaseException:
            reservation.release()
            self.reservation = None
            raise
        details = (
            self.inspection.issue
            or "Intact administrative logs can receive evidence-based terminal recovery events."
        )
        endpoint = self.inspection.spikeglx_endpoint
        remote = ""
        if self.inspection.spikeglx_stop_unconfirmed:
            remote = (
                " SpikeGLX stopping remains unconfirmed for endpoint "
                + (f"{endpoint[0]}:{endpoint[1]}" if endpoint else "unknown")
                + f", run {self.inspection.spikeglx_run or 'unknown'}; inspect/stop"
                " that exact remote run manually before another paired session."
            )
        return pb.Prompt(
            prompt_id=str(uuid.uuid4()),
            setup=pb.SessionContext(
                controller_generation=pointer.controller_generation,
                session_id=pointer.session_id,
            ),
            operation=pb.OperationContext(command_id=self.operation_id),
            permitted_choices=["continue", "cancel"],
            explanation=f"Recover unfinished session at {pointer.session_directory}. {details} Continue preserves scientific files, writes a recovery report and completes only the reservation marker; it does not certify unknown outputs or resume the experiment. Cancel preserves the blocker.{remote}",
        )

    async def recover(self) -> None:
        pointer, reservation, inspection = (
            self.pointer,
            self.reservation,
            self.inspection,
        )
        if pointer is None or reservation is None or inspection is None:
            raise StorageError("startup recovery proof/held reservation unavailable")
        if self.attempted:
            raise StorageError(
                "this recovery write may already have occurred; do not retry an uncertain append, restart for inspection"
            )
        self.attempted = True
        deadline = host_time_ns() + self.timeout_ns
        refreshed = await run_pipe_io_daemon(
            lambda: inspect_recovery(reservation, self.max_bytes),
            timeout_s=self.timeout_ns / 1e9,
        )
        if refreshed != inspection:
            raise StorageError("recovery inputs changed since the operator choice")
        writer = MetadataWriter(
            reservation.protocol_directory,
            max_operations=self.max_operations,
            max_bytes=self.max_bytes,
            clock=host_time_ns,
            session_id=pointer.session_id,
        )
        self.writer = writer
        if inspection.log_identity is not None:
            dev, ino, size = inspection.log_identity
            await run_pipe_io_daemon(
                lambda: writer.adopt_recovery_log(
                    reservation, expected_dev=dev, expected_ino=ino, expected_size=size
                ),
                timeout_s=max(0, (deadline - host_time_ns()) / 1e9),
            )
        work = pb.WorkContext(
            session=pb.SessionContext(
                controller_generation=pointer.controller_generation,
                session_id=pointer.session_id,
            )
        )

        async def persist(
            name: str,
            action: Literal["create_json", "append_jsonl_record"],
            document: dict[str, object],
        ) -> None:
            command_id = str(uuid.uuid4())
            request = MetadataWrite(
                command_id=command_id,
                path=writer.root / name,
                action=action,
                payload_utf8=json.dumps(
                    document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ).encode(),
                submitted_ns=host_time_ns(),
                deadline_ns=deadline,
                work=work,
                operation=pb.OperationContext(command_id=command_id),
            )
            completion = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(writer.submit(request))),
                max(0, (deadline - host_time_ns()) / 1e9),
            )
            writer.retire(command_id)
            if completion.state != "synced" or not completion.deadline_met:
                raise StorageError(
                    "recovery persistence failed or completed after its original deadline"
                )

        def event(
            kind: str, *, trial: int | None = None, outcome: str | None = None
        ) -> dict[str, object]:
            result: dict[str, object] = {
                "monotonic_ns": host_time_ns(),
                "wall_time": datetime.now(ZoneInfo(inspection.zone)).isoformat(),
                "event_type": kind,
                "source": "controller",
            }
            if trial is not None:
                result["trial_number"] = trial
            if outcome is not None:
                result["outcome"] = outcome
            details: dict[str, object] = {
                "component": "controller",
                "action": "startup_recovery",
                "recovery_controller_generation": self.current_generation,
                "event_clock": "current_recovery_application",
                "scientific_output_closure": "unconfirmed",
            }
            if kind in {"trial_finished", "session_ended"}:
                details["actual_end_monotonic_ns"] = None
                details["end_observed_during_recovery"] = True
            result["details"] = details
            return result

        try:
            if inspection.log_identity is not None:
                for number in inspection.unfinished_trials:
                    await persist(
                        "SESSION_LOG.jsonl",
                        "append_jsonl_record",
                        event("trial_finished", trial=number, outcome="interrupted"),
                    )
                if inspection.session_started and not inspection.session_ended:
                    await persist(
                        "SESSION_LOG.jsonl",
                        "append_jsonl_record",
                        event("session_ended", outcome="interrupted"),
                    )
                if not inspection.recovery_recorded:
                    await persist(
                        "SESSION_LOG.jsonl",
                        "append_jsonl_record",
                        event("recovery", outcome="completed"),
                    )
            report_name = f"RECOVERY-{self.operation_id}.json"
            writer.reserve_recovery_report(report_name)
            await persist(
                report_name,
                "create_json",
                {
                    "schema_version": 1,
                    "session_id": pointer.session_id,
                    "prior_controller_generation": pointer.controller_generation,
                    "recovery_controller_generation": self.current_generation,
                    "observed_wall_time": datetime.now(UTC).isoformat(),
                    "old_process_absence": "supervisor_verified_launcher_receipt",
                    "original_marker_base64": base64.b64encode(
                        inspection.marker_bytes
                    ).decode(),
                    "administrative_log_issue": inspection.issue,
                    "missing_terminal_trials": list(inspection.unfinished_trials),
                    "scientific_output_closure": "unconfirmed; existing confirmed file results are preserved",
                    "spikeglx_stop_unconfirmed": inspection.spikeglx_stop_unconfirmed,
                    "expected_spikeglx_endpoint": (
                        {
                            "address": inspection.spikeglx_endpoint[0],
                            "port": inspection.spikeglx_endpoint[1],
                        }
                        if inspection.spikeglx_endpoint
                        else None
                    ),
                    "expected_spikeglx_run": inspection.spikeglx_run,
                    "automatic_session_resumption": False,
                },
            )
            sealed = await run_pipe_io_daemon(
                lambda: writer.seal(max(0, (deadline - host_time_ns()) / 1e9)),
                timeout_s=max(0, (deadline - host_time_ns()) / 1e9),
            )
            if not sealed:
                raise StorageError("recovery writer closure is unconfirmed")
            await run_pipe_io_daemon(
                lambda: reservation.finish_recovery(inspection.marker_digest),
                timeout_s=max(0, (deadline - host_time_ns()) / 1e9),
            )
            await run_pipe_io_daemon(
                lambda: self.store.clear_pointer(pointer),
                timeout_s=max(0, (deadline - host_time_ns()) / 1e9),
            )
        except BaseException:
            # Seal admission once; never retry a failed/uncertain file operation.
            writer.seal(0)
            raise

    def close(self) -> None:
        if self.reservation is not None and (
            self.writer is None or self.writer.seal(0)
        ):
            self.reservation.release()
