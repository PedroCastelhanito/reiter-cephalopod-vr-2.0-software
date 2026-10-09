"""Explicit E04 recovery of one known unfinished session after verified exit.

No output is scanned or certified. Intact administrative logs receive missing
terminal outcomes; incomplete logs are preserved and a separate report records
the uncertainty. A lost write result is never retried in this process.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import threading
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import MetadataWrite, StorageError
from cephvr.controller.metadata.writer import MetadataWriter
from cephvr.controller.recovery_inspection import (
    RecoveryInspection,
    inspect_recovery,
)
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.shared.clock import host_time_ns, require_int64_ns
from cephvr.shared.deadlines import remaining_seconds
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import RecoveryStore, UnfinishedSessionPointer


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


def _settle_cancelled_namespace(directory: Path) -> bool:
    """True when a crashed Setup cancel left no session namespace, removing leftovers.

    A remaining quarantine that holds a reservation marker or anything but the lock
    is not ours to judge: return False and keep today's strict blocking.
    """
    if directory.is_symlink() or directory.exists():
        return False
    parent = directory.parent
    if parent.is_symlink() or not parent.is_dir():
        return not parent.exists() and not parent.is_symlink()
    pattern = re.compile(rf"\.{re.escape(directory.name)}\.[0-9a-f-]{{36}}\.cleanup")
    leftovers = [p for p in parent.iterdir() if pattern.fullmatch(p.name)]
    for leftover in leftovers:
        if leftover.is_symlink() or not leftover.is_dir():
            return False
        if {item.name for item in leftover.iterdir()} - {".cephvr.lock"}:
            return False
    for leftover in leftovers:
        (leftover / ".cephvr.lock").unlink(missing_ok=True)
        leftover.rmdir()
    return True


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
        self.notice: str | None = None
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
            remaining_seconds(deadline, clock=host_time_ns),
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
        directory = Path(pointer.session_directory)
        if await run_pipe_io_daemon(
            lambda: _settle_cancelled_namespace(directory),
            timeout_s=remaining_seconds(deadline, clock=host_time_ns),
        ):
            # Crash between cancelled-Setup namespace removal and pointer clear.
            await run_pipe_io_daemon(
                lambda: self.store.clear_pointer(pointer),
                timeout_s=remaining_seconds(deadline, clock=host_time_ns),
            )
            self.notice = "cancelled Setup cleanup completed at recovery"
            logging.getLogger(__name__).warning(self.notice)
            return None
        self.reservation = await _open_existing_bounded(
            Path(pointer.session_directory),
            pointer.session_id,
            pointer.controller_generation,
            remaining_seconds(deadline, clock=host_time_ns),
        )
        reservation = self.reservation
        if reservation.marker_issue == "reservation marker already complete":
            # A crash can happen after durable marker completion but before pointer clear.
            try:
                await run_pipe_io_daemon(
                    lambda: self.store.clear_pointer(pointer),
                    timeout_s=remaining_seconds(deadline, clock=host_time_ns),
                )
            finally:
                reservation.release()
                self.reservation = None
            return None
        try:
            self.inspection = await run_pipe_io_daemon(
                lambda: inspect_recovery(reservation, self.max_bytes),
                timeout_s=remaining_seconds(deadline, clock=host_time_ns),
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
                timeout_s=remaining_seconds(deadline, clock=host_time_ns),
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
                remaining_seconds(deadline, clock=host_time_ns),
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
                lambda: writer.seal(remaining_seconds(deadline, clock=host_time_ns)),
                timeout_s=remaining_seconds(deadline, clock=host_time_ns),
            )
            if not sealed:
                raise StorageError("recovery writer closure is unconfirmed")
            await run_pipe_io_daemon(
                lambda: reservation.finish_recovery(inspection.marker_digest),
                timeout_s=remaining_seconds(deadline, clock=host_time_ns),
            )
            await run_pipe_io_daemon(
                lambda: self.store.clear_pointer(pointer),
                timeout_s=remaining_seconds(deadline, clock=host_time_ns),
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
