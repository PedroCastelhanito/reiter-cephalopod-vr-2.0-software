"""Hardware-free acquisition worker process and camera role mapping (A02)."""

from __future__ import annotations

from cephvr.acquisition.v1 import camera_pb2

CAMERA_NAME_BY_ROLE: dict[camera_pb2.CameraRole, str] = {
    camera_pb2.CAMERA_ROLE_BEHAVIORAL: "behavioral",
    camera_pb2.CAMERA_ROLE_TRACKING: "tracking",
    camera_pb2.CAMERA_ROLE_EYE_TRACKING: "eye_tracking",
}
CAMERA_NAMES = tuple(CAMERA_NAME_BY_ROLE.values())

WORKER_ROLE_BY_CAMERA: dict[camera_pb2.CameraRole, str] = {
    camera_pb2.CAMERA_ROLE_BEHAVIORAL: "acquisition_behavioral_worker",
    camera_pb2.CAMERA_ROLE_TRACKING: "acquisition_tracking_worker",
    camera_pb2.CAMERA_ROLE_EYE_TRACKING: "acquisition_eye_tracking_worker",
}
FFMPEG_ROLE = "acquisition_ffmpeg"
FFMPEG_PROBE_ROLE = "acquisition_ffmpeg_probe"
FFMPEG_ROLES = frozenset((FFMPEG_ROLE, FFMPEG_PROBE_ROLE))
CAMERA_BY_WORKER_ROLE: dict[str, camera_pb2.CameraRole] = {
    role: camera for camera, role in WORKER_ROLE_BY_CAMERA.items()
}
ACQUISITION_WORKER_ROLES = frozenset(WORKER_ROLE_BY_CAMERA.values())


def camera_role_name(role: int) -> str:
    """Resolve an explicit role; unknown roles never alias another camera."""
    for camera, name in CAMERA_NAME_BY_ROLE.items():
        if camera == role:
            return name
    raise ValueError(f"unsupported acquisition camera role: {role}")


def process_role_for_camera(camera: camera_pb2.CameraRole) -> str:
    """Return the one accepted child process role for a camera role."""
    try:
        return WORKER_ROLE_BY_CAMERA[camera]
    except KeyError as exc:
        raise ValueError(f"unsupported acquisition camera role: {camera}") from exc


def camera_for_process_role(role: str) -> camera_pb2.CameraRole:
    """Resolve a registered worker role to its exact camera enum."""
    try:
        return CAMERA_BY_WORKER_ROLE[role]
    except KeyError as exc:
        raise ValueError(f"unsupported acquisition worker role: {role}") from exc
