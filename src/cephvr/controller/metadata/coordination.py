"""E04 serialized metadata admission, late completion and trial log records."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.types import (
    MetadataCompletion,
    MetadataWrite,
    StorageError,
)
from cephvr.controller.metadata.writer import MetadataWriter
from cephvr.controller.state import (
    Attempt,
    ControlState,
    LifecycleState,
    LimitsState,
    MetadataState,
)


class MetadataCoordinator:
    """One event-loop owner for accepted writes and retained completion evidence."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        metadata_state: MetadataState,
        limits: LimitsState,
        clock: Callable[[], int],
        publish: Callable[[], None],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.metadata_state = metadata_state
        self.limits = limits
        self.clock = clock
        self.publish = publish
        self.spawn = spawn

    async def persist(
        self,
        attempt: Attempt,
        name: str,
        action: Literal["create_json", "replace_json", "append_jsonl_record"],
        document: dict[str, object],
    ) -> MetadataCompletion:
        writer = attempt.writer
        if writer is None:
            raise StorageError("metadata writer unavailable")
        payload = json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        now = self.clock()
        command_id = str(uuid.uuid4())
        path = writer.root / name
        work = pb.WorkContext(session=attempt.context)
        if name.endswith("_LOG.json") and attempt.trial_index >= 0:
            work.trial.CopyFrom(attempt.prepared.trials[attempt.trial_index].context)
        request = MetadataWrite(
            command_id,
            work,
            pb.OperationContext(command_id=command_id),
            path,
            action,
            payload,
            now,
            now + self.limits.current.metadata_ns,
        )
        async with self.lifecycle.lock:
            if (
                len(self.metadata_state.results)
                >= self.limits.current.max_metadata_operations
            ):
                raise StorageError("metadata result retention capacity exhausted")
            future = writer.submit(request)
            self.metadata_state.results[command_id] = pb.MetadataResult(
                operation=pb.OperationContext(command_id=command_id),
                state=pb.METADATA_PERSISTENCE_PENDING,
                path=str(path),
            )
            self.publish()
        try:
            completion = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(future)),
                max(0, (request.deadline_ns - self.clock()) / 1e9),
            )
            terminal = True
        except (TimeoutError, asyncio.CancelledError) as exc:
            cancelled = isinstance(exc, asyncio.CancelledError)
            completion = MetadataCompletion(
                command_id,
                path,
                "unconfirmed",
                self.clock(),
                "metadata wait cancelled" if cancelled else "metadata deadline expired",
                False,
            )
            loop = asyncio.get_running_loop()
            future.add_done_callback(
                lambda f: loop.call_soon_threadsafe(
                    self.enqueue_late_metadata, f, writer, command_id, path
                )
            )
            if cancelled:
                # PENDING must never persist after cancellation; late sync is reconciled.
                await self.record_metadata(completion, writer, terminal=False)
                raise
            terminal = False
        except Exception as exc:
            completion = MetadataCompletion(
                command_id, path, "failed", self.clock(), str(exc), False
            )
            terminal = True
        await self.record_metadata(completion, writer, terminal=terminal)
        if completion.state != "synced" or not completion.deadline_met:
            raise StorageError(
                f"metadata {name} {completion.state}: {completion.error}"
            )
        return completion

    def enqueue_late_metadata(
        self,
        future: Future[MetadataCompletion],
        writer: MetadataWriter,
        command_id: str,
        path: Path,
    ) -> None:
        try:
            self.metadata_state.completion_queue.put_nowait(
                (future, writer, command_id, path)
            )
        except asyncio.QueueFull as exc:
            raise RuntimeError(
                "accepted metadata completion exceeded its reserved queue capacity"
            ) from exc
        if (
            self.metadata_state.drain_task is None
            or self.metadata_state.drain_task.done()
        ):
            self.metadata_state.drain_task = self.spawn(
                self.drain_metadata_completions()
            )

    async def drain_metadata_completions(self) -> None:
        while True:
            try:
                future, writer, command_id, path = (
                    self.metadata_state.completion_queue.get_nowait()
                )
            except asyncio.QueueEmpty:
                return
            try:
                completion = future.result()
            except Exception as exc:
                completion = MetadataCompletion(
                    command_id, path, "failed", self.clock(), str(exc), False
                )
            await self.record_metadata(completion, writer, terminal=True)

    async def record_metadata(
        self, completion: MetadataCompletion, writer: MetadataWriter, *, terminal: bool
    ) -> None:
        enum = {
            "synced": pb.METADATA_PERSISTENCE_SYNCED,
            "failed": pb.METADATA_PERSISTENCE_FAILED,
            "unconfirmed": pb.METADATA_PERSISTENCE_UNCONFIRMED,
        }[completion.state]
        async with self.lifecycle.lock:
            result = self.metadata_state.results.get(completion.command_id)
            if result is None:
                if terminal:
                    writer.retire(completion.command_id)
                return
            if not terminal and result.state != pb.METADATA_PERSISTENCE_PENDING:
                return
            if (
                result.state == pb.METADATA_PERSISTENCE_UNCONFIRMED
                and enum == pb.METADATA_PERSISTENCE_UNCONFIRMED
            ):
                if terminal:
                    writer.retire(completion.command_id)
                return
            prior_unconfirmed = result.state == pb.METADATA_PERSISTENCE_UNCONFIRMED
            prior_failure = result.failure.message if result.HasField("failure") else ""
            result.state = enum
            if enum == pb.METADATA_PERSISTENCE_SYNCED:
                result.ClearField("failure")
                if prior_unconfirmed or not completion.deadline_met:
                    reason = (
                        prior_failure
                        or "metadata completion missed its original deadline"
                    )
                    self.control.warnings.append(
                        pb.Warning(
                            warning_id=str(uuid.uuid4()),
                            component="metadata",
                            message=f"{completion.path.name}: late verified sync; original timeout retained: {reason}",
                        )
                    )
                    self.control.warnings = self.control.warnings[-256:]
            elif completion.error:
                result.failure.CopyFrom(
                    pb.Failure(code="METADATA_WRITE", message=completion.error)
                )
            if terminal and enum == pb.METADATA_PERSISTENCE_SYNCED:
                path_key = str(completion.path)
                previous = self.metadata_state.latest_synced.get(path_key)
                if previous is not None and previous != completion.command_id:
                    prior = self.metadata_state.results.get(previous)
                    if (
                        prior is not None
                        and prior.state == pb.METADATA_PERSISTENCE_SYNCED
                    ):
                        self.metadata_state.results.pop(previous)
                self.metadata_state.latest_synced[path_key] = completion.command_id
            self.publish()
            if terminal:
                writer.retire(completion.command_id)

    async def retire_completed_trial_metadata(
        self, attempt: Attempt, trial_log: str
    ) -> None:
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt:
                return
            path_key = str(attempt.reservation.protocol_directory / trial_log)
            command_id = self.metadata_state.latest_synced.get(path_key)
            if command_id is None:
                return
            result = self.metadata_state.results.get(command_id)
            if result is not None and result.state == pb.METADATA_PERSISTENCE_SYNCED:
                self.metadata_state.results.pop(command_id)
                self.metadata_state.latest_synced.pop(path_key, None)
                self.publish()

    def event(
        self,
        attempt: Attempt,
        event_type: str,
        *,
        at_ns: int | None = None,
        trial_number: int | None = None,
        outcome: str | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event_ns = self.clock() if at_ns is None else at_ns
        anchor = datetime.fromisoformat(attempt.prepared.anchor_wall_time)
        from datetime import timedelta

        wall = anchor + timedelta(
            microseconds=(event_ns - attempt.prepared.anchor_monotonic_ns) / 1000
        )
        event: dict[str, object] = {
            "monotonic_ns": event_ns,
            "wall_time": wall.isoformat(),
            "event_type": event_type,
            "source": "controller",
        }
        if trial_number is not None:
            event["trial_number"] = trial_number
        if outcome is not None:
            event["outcome"] = outcome
        if details is not None:
            event["details"] = details
        return event

    async def log_event(
        self,
        attempt: Attempt,
        event_type: str,
        *,
        at_ns: int | None = None,
        trial_number: int | None = None,
        outcome: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        await self.persist(
            attempt,
            "SESSION_LOG.jsonl",
            "append_jsonl_record",
            self.event(
                attempt,
                event_type,
                at_ns=at_ns,
                trial_number=trial_number,
                outcome=outcome,
                details=details,
            ),
        )
