"""Configuration, process, pulse and native allocation records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cephvr.acquisition.buffers.ring import PartialRingOwnership, SharedRing
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import ResourceKey


@dataclass(frozen=True)
class CoordinatorIdentity:
    backend: control.BackendContext
    process: control.ProcessIdentity
    controller: control.ProcessIdentity
    supervisor: control.ProcessIdentity
    tracking: control.ProcessIdentity


@dataclass
class ConfigurationRecord:
    """One accepted settings/policy revision used by acquisition features."""

    settings: control.AcquisitionSettings
    file_policies: runtime.AcquisitionFilePolicies
    revision: int = 0


@dataclass
class PulseRecord:
    """Last full typed observation from the serialized serial owner port."""

    observation: mcu.MicrocontrollerObservation | None = None


@dataclass
class LaunchRecord:
    """Retained PlanLaunch intent/outcome, including partial launches."""

    command_id: str
    worker: control.ProcessIdentity
    owner: control.ProcessIdentity
    work: control.WorkContext
    camera: int
    parent_operation: control.OperationContext
    planned_ns: int
    process_confirmed: bool = False
    endpoint_confirmed: bool = False
    pid: int | None = None
    creation_time_100ns: int | None = None
    endpoint: str | None = None
    failure: control.Failure | None = None
    terminal_ns: int | None = None


@dataclass
class ResourceRecord:
    """Coordinator ring allocation; the native transfer ledger owns lifetimes."""

    attachment: acq.FrameBufferAttachment
    ring: SharedRing | None
    ledger_key: ResourceKey
    partial: PartialRingOwnership | SharedRing | None = None
    native_state: Literal["planned", "allocated", "partial", "absent", "released"] = (
        "planned"
    )
