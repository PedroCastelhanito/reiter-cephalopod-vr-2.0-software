"""Bounded tracking-to-renderer result and exact-credit pipe consumer (A06/E08)."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any, Protocol

from google.protobuf.message import DecodeError

from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import remaining_seconds
from cephvr.visual_stimulus.feedback.consumer import FeedbackResult
from cephvr.visual_stimulus.feedback.wire import decode_entry
from cephvr.visual_stimulus.v1 import data_pb2 as data
from cephvr.visual_stimulus.v1 import runtime_pb2 as runtime


class MessagePipe(Protocol):
    def send_bytes(self, payload: bytes, *, deadline_ns: int) -> None: ...
    def recv_bytes(self, *, deadline_ns: int) -> bytes: ...
    def request_cancel(self) -> None: ...
    def close_after_io(self, *, deadline_ns: int) -> None: ...


PipeOpener = Callable[..., MessagePipe]


class FeedbackPipeConstructionError(RuntimeError):
    """Construction failed while a partially opened pipe remains owned."""

    def __init__(self, consumer: FeedbackPipeConsumer, cause: BaseException) -> None:
        super().__init__("feedback pipe setup failed with an outstanding pipe")
        self.consumer = consumer
        self.__cause__ = cause


class FeedbackPipeConsumer:
    """Open authenticated endpoints, retain a finite result queue and return credits.

    Pipe I/O stays on two bounded data threads. The GL owner takes a finite batch
    without waiting; credit is queued only when an entry enters that captured batch.
    """

    def __init__(
        self,
        attachment: runtime.FeedbackAttachment,
        *,
        local_process_instance_id: str,
        resource_key_factory: Callable[[str, str], Any],
        open_pipe: PipeOpener,
        announce: Callable[[str], None],
        selected_stream_ids: tuple[str, ...],
        deadline_ns: int,
        clock_ns: Callable[[], int] = host_time_ns,
    ) -> None:
        self._attachment = runtime.FeedbackAttachment.FromString(
            attachment.SerializeToString(deterministic=True)
        )
        self._clock_ns = clock_ns
        self._local_process_instance_id = local_process_instance_id
        self._capacity = int(attachment.queue_capacity)
        self._max_bytes = int(attachment.maximum_message_bytes)
        if (
            not local_process_instance_id
            or local_process_instance_id == attachment.source_process_instance_id
            or not attachment.attachment_generation
            or not attachment.source_process_instance_id
            or not attachment.startup_nonce
            or self._capacity <= 0
            or self._max_bytes <= 0
        ):
            raise ValueError(
                "feedback attachment lacks its exact bounded pipe descriptor"
            )
        selected = set(selected_stream_ids)
        advertised = set(attachment.stream_ids)
        if (
            not selected
            or len(selected) != len(selected_stream_ids)
            or not selected <= advertised
        ):
            raise ValueError(
                "program feedback streams differ from the protected attachment"
            )
        self._selected_streams = selected
        self._result_pipe: MessagePipe | None = None
        self._credit_pipe: MessagePipe | None = None
        self._reader: threading.Thread | None = None
        self._writer: threading.Thread | None = None
        self._result_closed = False
        self._credit_closed = False
        self._results: queue.Queue[FeedbackResult] = queue.Queue(self._capacity)
        self._credits: queue.Queue[bytes] = queue.Queue(self._capacity)
        self._stop = threading.Event()
        self._failure: BaseException | None = None
        self._entry_sequence = 0
        self._reset_generation = 0
        self._result_pipe = self._open_one(
            attachment.result_pipe,
            "result",
            resource_key_factory,
            open_pipe,
            announce,
            deadline_ns,
        )
        try:
            self._credit_pipe = self._open_one(
                attachment.credit_pipe,
                "credit",
                resource_key_factory,
                open_pipe,
                announce,
                deadline_ns,
            )
        except BaseException as exc:
            if self._result_pipe is not None:
                try:
                    self._result_pipe.close_after_io(deadline_ns=deadline_ns)
                except BaseException as close_error:
                    raise FeedbackPipeConstructionError(self, close_error) from exc
                self._result_closed = True
                self._result_pipe = None
            raise
        self._reader = threading.Thread(
            target=self._read_loop, name="visual-stimulus-feedback-reader", daemon=False
        )
        self._writer = threading.Thread(
            target=self._write_loop,
            name="visual-stimulus-feedback-credit-writer",
            daemon=False,
        )
        self._reader.start()
        self._writer.start()

    def _open_one(
        self,
        name: str,
        kind: str,
        key_factory: Callable[[str, str], Any],
        opener: PipeOpener,
        announce: Callable[[str], None],
        deadline_ns: int,
    ) -> MessagePipe:
        if not name:
            raise ValueError(f"feedback {kind} pipe name is required")
        announce("feedback-" + kind + "-pipe")
        resource_key = key_factory(kind, self._local_process_instance_id)
        return opener(
            resource_key,
            name=name,
            role="client",
            expected_peer_instance_id=self._attachment.source_process_instance_id,
            startup_nonce=self._attachment.startup_nonce,
            maximum_message_bytes=self._max_bytes,
            deadline_ns=deadline_ns,
        )

    @property
    def failure(self) -> BaseException | None:
        return self._failure

    @property
    def selected_stream_ids(self) -> frozenset[str]:
        return frozenset(self._selected_streams)

    @property
    def closed(self) -> bool:
        return (self._result_pipe is None or self._result_closed) and (
            self._credit_pipe is None or self._credit_closed
        )

    def capture_batch(
        self, *, maximum_results: int | None = None
    ) -> tuple[FeedbackResult, ...]:
        if self._failure is not None:
            raise RuntimeError("feedback pipe consumer failed") from self._failure
        limit = min(
            self._capacity,
            self._capacity if maximum_results is None else maximum_results,
        )
        if limit <= 0:
            raise ValueError("captured feedback batch limit must be positive")
        captured: list[FeedbackResult] = []
        for _ in range(limit):
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                break
            captured.append(result)
            credit = data.FeedbackCredit(
                attachment_generation=result.attachment_generation,
                stream_id=result.stream_id,
                reset_generation=str(result.reset_generation),
                entry_sequence=result.entry_sequence,
            ).SerializeToString(deterministic=True)
            try:
                self._credits.put_nowait(credit)
            except queue.Full as exc:
                self._set_failure(exc)
                raise RuntimeError(
                    "feedback credit writer exceeded its prepared capacity"
                ) from exc
        return tuple(captured)

    def _read_loop(self) -> None:
        try:
            while not self._stop.is_set():
                assert self._result_pipe is not None
                try:
                    payload = self._result_pipe.recv_bytes(
                        deadline_ns=self._clock_ns() + 100_000_000
                    )
                except TimeoutError:
                    continue
                if not payload or len(payload) > self._max_bytes:
                    raise ValueError(
                        "feedback result message is empty or exceeds its bound"
                    )
                entry = data.FeedbackEntry()
                try:
                    entry.ParseFromString(payload)
                except DecodeError as exc:
                    raise ValueError("malformed FeedbackEntry pipe message") from exc
                result = decode_entry(
                    entry,
                    attachment_generation=self._attachment.attachment_generation,
                )
                if (
                    result.source_generation
                    != self._attachment.source_process_instance_id
                ):
                    raise ValueError(
                        "feedback result came from another tracking generation"
                    )
                if result.stream_id not in self._selected_streams:
                    raise ValueError("feedback result uses an unattached stream")
                if entry.entry_sequence <= self._entry_sequence:
                    raise ValueError("feedback entry sequence did not increase")
                generation = int(result.reset_generation)
                if generation < self._reset_generation:
                    # Keep the entry visible to the renderer, which records the
                    # retired-generation discard before returning its exact credit.
                    pass
                elif generation > self._reset_generation:
                    self._reset_generation = generation
                self._entry_sequence = entry.entry_sequence
                try:
                    self._results.put(result, timeout=0.1)
                except queue.Full as exc:
                    raise BufferError(
                        "tracking exceeded the shared pending-result credit budget"
                    ) from exc
        except BaseException as exc:
            if not self._stop.is_set():
                self._set_failure(exc)

    def _write_loop(self) -> None:
        try:
            while not self._stop.is_set() or not self._credits.empty():
                try:
                    payload = self._credits.get(timeout=0.1)
                except queue.Empty:
                    continue
                if len(payload) > self._max_bytes:
                    raise ValueError("FeedbackCredit exceeds its pipe message bound")
                assert self._credit_pipe is not None
                self._credit_pipe.send_bytes(
                    payload, deadline_ns=self._clock_ns() + 1_000_000_000
                )
        except BaseException as exc:
            if not self._stop.is_set():
                self._set_failure(exc)

    def _set_failure(self, error: BaseException) -> None:
        if self._failure is None:
            self._failure = error
            self._stop.set()
            if self._result_pipe is not None and not self._result_closed:
                self._result_pipe.request_cancel()
            if self._credit_pipe is not None and not self._credit_closed:
                self._credit_pipe.request_cancel()

    def close(self, *, deadline_ns: int) -> None:
        self._stop.set()
        if self._result_pipe is not None and not self._result_closed:
            self._result_pipe.request_cancel()
        remaining = remaining_seconds(deadline_ns, clock=self._clock_ns)
        if self._reader is not None:
            self._reader.join(remaining)
        if self._writer is not None:
            self._writer.join(remaining_seconds(deadline_ns, clock=self._clock_ns))
        if (self._reader is not None and self._reader.is_alive()) or (
            self._writer is not None and self._writer.is_alive()
        ):
            raise TimeoutError(
                "feedback pipe I/O remains unconfirmed; resources retained"
            )
        if self._credit_pipe is not None and not self._credit_closed:
            self._credit_pipe.request_cancel()
        if self._result_pipe is not None and not self._result_closed:
            self._result_pipe.close_after_io(deadline_ns=deadline_ns)
            self._result_closed = True
            self._result_pipe = None
        if self._credit_pipe is not None and not self._credit_closed:
            self._credit_pipe.close_after_io(deadline_ns=deadline_ns)
            self._credit_closed = True
            self._credit_pipe = None
        if self._failure is not None:
            raise RuntimeError("feedback pipe failed before cleanup") from self._failure
