"""E04 active configuration and Protobuf metadata document construction."""

from __future__ import annotations

from copy import deepcopy

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb


def message_dict(message: Message) -> dict[str, object]:
    return MessageToDict(message, preserving_proto_field_name=True)


def active_configuration_document(
    configuration: pb.ExperimentConfiguration,
) -> dict[str, object]:
    """Persist effective active settings without reusable PFS payloads or dormant values."""
    public = deepcopy(configuration)
    selected = [deepcopy(item) for item in public.backends if item.enabled]
    public.ClearField("backends")
    for setting in selected:
        if setting.backend_name == "acquisition":
            for camera in (
                setting.acquisition.behavioral,
                setting.acquisition.tracking,
            ):
                if not camera.HasField("enabled") or not camera.enabled:
                    camera.ClearField("device")
                    camera.ClearField("ffmpeg_args")
                    camera.ClearField("sdk_buffer_count")
                    camera.ClearField("recording_bit_depth")
                    camera.ClearField("save_video")
                else:
                    camera.device.ClearField("pfs_baseline")
        public.backends.add().CopyFrom(setting)
    return message_dict(public)
