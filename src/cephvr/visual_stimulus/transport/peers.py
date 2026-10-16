"""Backend-owned service selection for the shared E08 unary transport."""

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.shared.auth import Principal
from cephvr.shared.unary_peer import UnaryPeer
from cephvr.visual_stimulus.v1 import services_pb2_grpc as visual_stimulus_rpc


class Peer(UnaryPeer):
    def __init__(
        self, endpoint: str, principal: Principal, maximum: int, *, kind: str
    ) -> None:
        stub_factory = {
            "worker": visual_stimulus_rpc.VisualStimulusWorkerServiceStub,
            "coordinator": visual_stimulus_rpc.VisualStimulusCoordinatorServiceStub,
            "controller": rpc.ExperimentControllerServiceStub,
            "supervisor": rpc.SupervisorServiceStub,
        }[kind]
        super().__init__(
            endpoint,
            principal,
            maximum,
            stub_factory=stub_factory,
            label="Visual Stimulus",
        )
