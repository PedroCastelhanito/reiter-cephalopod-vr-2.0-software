"""Apply matched pulse-command state without inventing fresh MCU capabilities."""

from __future__ import annotations

from cephvr.acquisition.state import PulseRecord
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu


def retain_applied_pulse_state(
    pulse: PulseRecord,
    evidence: mcu.PulseCommandEvidence,
    *,
    deadline_ns: int,
) -> None:
    """Update only state from exact APPLIED/ACK evidence on the same connection."""
    current = pulse.observation
    if (
        current is None
        or not current.connection_id
        or evidence.connection_id != current.connection_id
        or not evidence.request_id
        or evidence.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED
        or not evidence.HasField("applied")
        or not evidence.applied
        or not evidence.HasField("dispatched_monotonic_ns")
        or not evidence.HasField("acknowledged_monotonic_ns")
        or evidence.dispatched_monotonic_ns <= 0
        or evidence.acknowledged_monotonic_ns < evidence.dispatched_monotonic_ns
        or evidence.acknowledged_monotonic_ns > deadline_ns
        or not evidence.HasField("resulting_state")
    ):
        raise RuntimeError("pulse command lacks exact timely APPLIED/ACK evidence")
    updated = mcu.MicrocontrollerObservation.FromString(
        current.SerializeToString(deterministic=True)
    )
    updated.state.CopyFrom(evidence.resulting_state)
    pulse.observation = updated
