from pathlib import Path

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.tracking.configuration import resolve_settings

ROOT = Path(__file__).resolve().parents[2]


def manual_settings() -> pb.TrackingSettings:
    settings = pb.TrackingSettings(
        pose_mode=pb.TRACKING_POSE_MODE_MANUAL,
        input_camera_role=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        save_tracking_data=False,
    )
    settings.manual_pose.image_width_px = 100
    settings.manual_pose.image_height_px = 100
    settings.image_scale.image_width_px = 100
    settings.image_scale.image_height_px = 100
    settings.image_scale.distance_start.x_px = 0
    settings.image_scale.distance_start.y_px = 0
    settings.image_scale.distance_end.x_px = 20
    settings.image_scale.distance_end.y_px = 0
    settings.image_scale.distance_mm = 10
    settings.image_scale.pixels_per_mm = 2
    for name, xy in (
        ("tip", (20.0, 50.0)),
        ("left_base", (70.0, 30.0)),
        ("right_base", (70.0, 70.0)),
    ):
        point = getattr(settings.manual_pose.landmarks, name)
        point.x_px, point.y_px = xy
    return resolve_settings(ROOT, settings)
