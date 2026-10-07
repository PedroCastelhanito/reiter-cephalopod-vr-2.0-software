"""Concrete controller device and native-tool assembly; no device opened at startup."""

from pathlib import Path

import grpc

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.config import load_serial_policies
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.microcontroller.firmware_upload import WindowsFirmwareUpload
from cephvr.controller.microcontroller.identity import FIRMWARE_UPLOAD_ROLE
from cephvr.controller.microcontroller.lazy_owner import LazySerialOwner
from cephvr.platform.windows.file_sync import WindowsFileSyncOwner
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher


def create_microcontroller(
    root: Path,
    principal: Principal,
    native: WindowsJobs,
    supervisor_endpoint: str,
    max_message_bytes: int,
    configuration: pb.ExperimentConfiguration,
) -> tuple[MicrocontrollerDevice, grpc.Channel]:
    settings = pb.AcquisitionSettings()
    for item in configuration.backends:
        if item.backend_name == "acquisition" and item.HasField("acquisition"):
            settings.CopyFrom(item.acquisition)
    policies = load_serial_policies(root)
    serial = LazySerialOwner(settings, policies, lambda _bridge: None)
    channel = grpc.insecure_channel(
        supervisor_endpoint,
        options=(
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        ),
    )
    uploader = WindowsFirmwareUpload(
        SupervisedEncoderLauncher(
            supervisor=rpc.SupervisorServiceStub(channel),  # type: ignore[no-untyped-call]
            owner=principal,
            owner_identity=pb.ProcessIdentity(
                role=principal.role, generation=principal.generation
            ),
            windows_jobs=native,
            file_sync_owner=WindowsFileSyncOwner(),
            allowed_roles=frozenset((FIRMWARE_UPLOAD_ROLE,)),
            probe_roles=frozenset((FIRMWARE_UPLOAD_ROLE,)),
            stop_method="owner_job_terminate",
        )
    )
    return MicrocontrollerDevice(
        serial,
        settings,
        policies,
        host_time_ns,
        uploader,
        policy_loader=lambda: load_serial_policies(root),
    ), channel
