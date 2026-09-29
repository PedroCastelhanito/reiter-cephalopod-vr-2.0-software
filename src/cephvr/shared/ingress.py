"""Bounded controller ingress with a reserved safety-interruption lane."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar

from cephvr.shared.clock import host_time_ns, require_int64_ns

T = TypeVar("T")


class IngressOverload(RuntimeError):
    """Essential evidence or the reserved interruption lane could not be admitted."""


@dataclass(frozen=True)
class IngressItem(Generic[T]):
    event: T
    payload: bytes
    ingress_ns: int


class BoundedEventIngress(Generic[T]):
    """Count serialized immutable payload bytes, not Python object memory."""

    def __init__(
        self,
        max_events: int,
        max_payload_bytes: int,
        *,
        max_interruption_payload_bytes: int,
    ) -> None:
        if max_events < 2 or not 0 < max_interruption_payload_bytes < max_payload_bytes:
            raise ValueError(
                "ingress must reserve one event and bytes for interruption"
            )
        self.max_events = max_events
        self.max_payload_bytes = max_payload_bytes
        self.max_interruption_payload_bytes = max_interruption_payload_bytes
        self._ordinary: deque[IngressItem[T]] = deque()
        self._interruption: IngressItem[T] | None = None
        self._ordinary_bytes = 0
        self._lock = Lock()

    def put(
        self,
        payload: bytes,
        event: T,
        *,
        essential: bool = False,
        ingress_ns: int | None = None,
    ) -> bool:
        """Reject ordinary overload; signal essential-evidence loss explicitly."""
        if not isinstance(payload, bytes):
            raise ValueError("payload must be immutable serialized bytes")
        ingress = host_time_ns() if ingress_ns is None else require_int64_ns(ingress_ns)
        with self._lock:
            if (
                len(self._ordinary) >= self.max_events - 1
                or self._ordinary_bytes + len(payload)
                > self.max_payload_bytes - self.max_interruption_payload_bytes
            ):
                if essential:
                    raise IngressOverload("essential evidence ingress exhausted")
                return False
            self._ordinary.append(IngressItem(event, payload, ingress))
            self._ordinary_bytes += len(payload)
            return True

    def put_interruption(
        self, payload: bytes, event: T, *, ingress_ns: int | None = None
    ) -> bool:
        """Admit one safety event within total bounds; exact retries are no-ops.

        A different cause while occupied raises. The owner must immediately fence
        execution on that explicit overflow and retain the cause in its error path.
        """
        if not isinstance(payload, bytes):
            raise ValueError("payload must be immutable serialized bytes")
        if len(payload) > self.max_interruption_payload_bytes:
            raise IngressOverload("interruption exceeds reserved byte budget")
        ingress = host_time_ns() if ingress_ns is None else require_int64_ns(ingress_ns)
        with self._lock:
            if self._interruption is not None:
                if self._interruption.payload == payload:
                    return False
                raise IngressOverload("reserved interruption slot occupied")
            self._interruption = IngressItem(event, payload, ingress)
            return True

    def take(self) -> IngressItem[T] | None:
        """Take safety work first without losing ordinary byte accounting."""
        with self._lock:
            if self._interruption is not None:
                item = self._interruption
                self._interruption = None
                return item
            if not self._ordinary:
                return None
            item = self._ordinary.popleft()
            self._ordinary_bytes -= len(item.payload)
            return item

    @property
    def pending_payload_bytes(self) -> int:
        with self._lock:
            return self._ordinary_bytes + (
                len(self._interruption.payload) if self._interruption else 0
            )

    @property
    def pending_events(self) -> int:
        with self._lock:
            return len(self._ordinary) + int(self._interruption is not None)
