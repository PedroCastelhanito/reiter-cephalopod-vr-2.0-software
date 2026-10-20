"""Build the lazy registered projector SDK owner without opening hardware."""

import grpc

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.file_sync import WindowsFileSyncOwner
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.platform.windows.projector_brightness import WindowsProjectorBrightness
from cephvr.shared.auth import Principal
from cephvr.shared.native_helper_identity import PROJECTOR_BRIGHTNESS_ROLE
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher


def create_projector_brightness(
    principal: Principal, native: WindowsJobs, channel: grpc.Channel
) -> WindowsProjectorBrightness:
    return WindowsProjectorBrightness(
        SupervisedEncoderLauncher(
            supervisor=rpc.SupervisorServiceStub(channel),  # type: ignore[no-untyped-call]
            owner=principal,
            owner_identity=pb.ProcessIdentity(
                role=principal.role, generation=principal.generation
            ),
            windows_jobs=native,
            file_sync_owner=WindowsFileSyncOwner(),
            allowed_roles=frozenset((PROJECTOR_BRIGHTNESS_ROLE,)),
            probe_roles=frozenset((PROJECTOR_BRIGHTNESS_ROLE,)),
            stop_method="owner_job_terminate",
        )
    )
