"""Mutable top-level state joining focused coordinator records."""

from __future__ import annotations

from dataclasses import dataclass, field

from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger

from .base import (
    ConfigurationRecord,
    CoordinatorIdentity,
    LaunchRecord,
    PulseRecord,
    ResourceRecord,
)
from .sessions import SessionSlot
from .workers import WorkerRecord


@dataclass
class CoordinatorState:
    identity: CoordinatorIdentity
    configuration: ConfigurationRecord
    session_slot: SessionSlot = field(default_factory=SessionSlot)
    pulse: PulseRecord = field(default_factory=PulseRecord)
    state_revision: int = 0
    workers: dict[int, WorkerRecord] = field(default_factory=dict)
    launches: dict[str, LaunchRecord] = field(default_factory=dict)
    resources: dict[str, ResourceRecord] = field(default_factory=dict)
    resource_ledger: NativeResourceLedger | None = None
    commands: CommandLedger | None = None
    control_policies: control.ControlPolicies | None = None

    def changed(self) -> int:
        self.state_revision += 1
        return self.state_revision
