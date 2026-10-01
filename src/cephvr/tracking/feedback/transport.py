"""A06 direct result and credit pipes; no per-frame controller communication."""

from __future__ import annotations

import threading
from collections.abc import Callable

from cephvr.platform.windows.message_server import MessageListener
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.feedback.delivery import FeedbackDelivery
from cephvr.visual_stimulus.v1 import data_pb2 as data
from cephvr.visual_stimulus.v1 import runtime_pb2 as wire


class FeedbackTransport:
    def __init__(
        self,
        attachment: wire.FeedbackAttachment,
        consumer: str,
        delivery: FeedbackDelivery,
        deadline: int,
        io_timeout: int,
        *,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.attachment, self.consumer, self.delivery = attachment, consumer, delivery
        self.deadline, self.io_timeout, self.clock = deadline, io_timeout, clock
        self.listeners: list[MessageListener] = []
        self.threads: list[threading.Thread] = []
        self.stop = threading.Event()
        self.ready = [threading.Event(), threading.Event()]
        self.failure: BaseException | None = None

    def prepare(self) -> None:
        for name in (self.attachment.result_pipe, self.attachment.credit_pipe):
            # Retain the partially constructed listener before any native creation.
            listener = MessageListener.__new__(MessageListener)
            self.listeners.append(listener)
            MessageListener.__init__(
                listener, name, self.attachment.maximum_message_bytes
            )
        for index in range(2):
            thread = threading.Thread(
                target=self._run,
                args=(index,),
                name="tracking-feedback-" + str(index),
                daemon=False,
            )
            self.threads.append(thread)
            thread.start()

    @property
    def connected(self) -> bool:
        return all(event.is_set() for event in self.ready) and self.failure is None

    def _run(self, index: int) -> None:
        try:
            pipe = self.listeners[index].accept(
                self.attachment.source_process_instance_id,
                self.consumer,
                self.attachment.startup_nonce,
                self.deadline,
            )
            self.ready[index].set()
            while not self.stop.is_set():
                if index == 0:
                    entry = self.delivery.take(0.05)
                    if entry is None:
                        self.stop.wait(0.01)
                        continue
                    pipe.send_bytes(
                        entry.SerializeToString(deterministic=True),
                        deadline_ns=self.clock() + self.io_timeout,
                    )
                    self.delivery.written(entry)
                else:
                    # An idle stream need not return credits. Wait only while slots
                    # are outstanding; new admissions never reset an in-flight deadline.
                    with self.delivery.gate.lock:
                        outstanding = (
                            self.delivery.credits.available
                            < self.delivery.credits.capacity
                        )
                    if not outstanding:
                        self.stop.wait(0.01)
                        continue
                    payload = pipe.recv_bytes(
                        deadline_ns=self.clock() + self.io_timeout
                    )
                    self.delivery.credit(data.FeedbackCredit.FromString(payload))
        except BaseException as exc:
            if not self.stop.is_set():
                self.failure = exc

    def close(self, deadline: int) -> bool:
        self.stop.set()
        for listener in self.listeners:
            if hasattr(listener, "api"):
                listener.cancel()
        for thread in self.threads:
            thread.join(max(0, (deadline - self.clock()) / 1e9))
        if any(thread.is_alive() for thread in self.threads):
            return False
        for listener in self.listeners:
            listener.close(deadline)
        return True
