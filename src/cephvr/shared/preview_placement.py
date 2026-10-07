"""Bound display-only hints at both authenticated command boundaries."""

from cephvr.control.v1 import services_pb2 as rpc


def valid_preview_placement(
    request: rpc.CameraCommandRequest | rpc.AcquisitionCameraCommand,
) -> bool:
    if not request.HasField("preview_placement"):
        return True
    hint = request.preview_placement
    return (
        request.kind == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
        and 128 <= hint.side <= 2048
        and abs(hint.x) <= 1_000_000
        and abs(hint.y) <= 1_000_000
    )
