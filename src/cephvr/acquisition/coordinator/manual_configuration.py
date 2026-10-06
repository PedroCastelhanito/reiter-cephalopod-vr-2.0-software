"""Install accepted Configuration drafts before manual commands, without applying hardware."""

from collections.abc import Callable

from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_configuration_available,
)
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    SessionSlot,
)
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control


class ManualConfiguration:
    def __init__(
        self,
        configuration: ConfigurationRecord,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        devices: ManualDeviceStatusReporter,
        clock: Callable[[], int],
    ) -> None:
        self.configuration = configuration
        self.identity = identity
        self.session_slot = session_slot
        self.devices = devices
        self.clock = clock

    def install(
        self,
        request: wire.AcquisitionCameraCommand | wire.AcquisitionMicrocontrollerCommand,
        deadline_ns: int,
    ) -> control.CommandAdmission | None:
        command = request.command
        # Release/attachment requests also serve already-owned session work. They
        # must never install a new draft while cleaning or attaching that work.
        if (
            isinstance(request, wire.AcquisitionCameraCommand)
            and (
                not request.HasField("settings")
                or command.work.WhichOneof("work") is not None
            )
            and request.kind
            in {
                wire.CAMERA_COMMAND_KIND_STOP_PREVIEW,
                wire.CAMERA_COMMAND_KIND_FINISH_EDITING,
                wire.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
            }
        ):
            return None
        error = ""
        if (
            self.clock() >= deadline_ns
            or command.issuer != self.identity.controller
            or command.target != self.identity.backend
            or not command.command_id
            or not command.parent_operation.command_id
            or command.work.WhichOneof("work") is not None
            or not request.HasField("settings")
            or not request.HasField("configuration_revision")
            or request.configuration_revision < self.configuration.revision
            or not manual_configuration_available(self.session_slot)
        ):
            error = "Manual command configuration is missing, stale or outside Configuration"
        elif (
            isinstance(request, wire.AcquisitionCameraCommand)
            and request.kind != wire.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
            and request.file_policies != self.configuration.file_policies
        ):
            error = "Manual command file policy differs from loaded policy"
        elif (
            isinstance(request, wire.AcquisitionMicrocontrollerCommand)
            and request.requested != request.settings.pulses
        ):
            error = "MCU command differs from the accepted pulse configuration"
        elif request.settings != self.configuration.settings and (
            request.configuration_revision == self.configuration.revision
            or self.devices.owns_hardware()
        ):
            error = "Release camera/MCU ownership before changing manual configuration"
        if error:
            return control.CommandAdmission(
                command_id=command.command_id,
                result=control.COMMAND_RESULT_REJECTED,
                failure=control.Failure(code="MANUAL_CONFIGURATION", message=error),
            )
        self.configuration.settings.CopyFrom(request.settings)
        self.configuration.revision = request.configuration_revision
        return None
