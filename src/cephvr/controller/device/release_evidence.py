"""Shared camera release evidence predicates and acquisition file-policy loading."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

from google.protobuf.message import Message

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.acquisition.v1 import runtime_pb2 as acquisition_pb
from cephvr.control.v1 import types_pb2 as pb


def camera_view(camera: int, views: pb.AcquisitionDeviceViews) -> pb.CameraDeviceView:
    return (
        views.behavioral
        if camera == camera_pb.CAMERA_ROLE_BEHAVIORAL
        else views.tracking
    )


def manual_state_open(view: pb.CameraDeviceView) -> bool:
    """Open device, running preview or prepared preview slot: owner cleanup releases it."""
    return bool(view.device_open or view.preview_running or view.preview_prepared)


def stop_preview_confirmed(view: pb.CameraDeviceView, stopped_run_id: str) -> bool:
    """Release requires a closed device, no preview, no cleanup and a new run slot."""
    return bool(
        view.HasField("device_open")
        and not view.device_open
        and view.HasField("preview_running")
        and not view.preview_running
        and not view.preview_prepared
        and view.HasField("cleanup_pending")
        and not view.cleanup_pending
        and view.HasField("preview_run_id")
        and view.preview_run_id != stopped_run_id
    )


def finish_editing_confirmed(
    view: pb.CameraDeviceView, *, require_closed: bool
) -> bool:
    """Editing ownership is released; a release additionally requires closure."""
    if not view.HasField("cleanup_pending") or view.cleanup_pending:
        return False
    if require_closed:
        return view.HasField("device_open") and not view.device_open
    return view.preview_running or not view.device_open


async def load_file_policies(
    loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
    timeout_s: float,
) -> acquisition_pb.AcquisitionFilePolicies:
    if loader is None:
        raise RuntimeError("acquisition file policies unavailable")
    loaded = await asyncio.wait_for(
        asyncio.to_thread(loader, frozenset({"acquisition"})), max(0.0, timeout_s)
    )
    raw = loaded.get("acquisition")
    if (
        raw is None
        or raw.DESCRIPTOR != acquisition_pb.AcquisitionFilePolicies.DESCRIPTOR
    ):
        raise RuntimeError("acquisition file policies unavailable")
    return acquisition_pb.AcquisitionFilePolicies.FromString(raw.SerializeToString())


def camera_policy(
    policies: acquisition_pb.AcquisitionFilePolicies, camera: camera_pb.CameraRole
) -> acquisition_pb.CameraFilePolicy:
    matching = [item for item in policies.cameras if item.camera == camera]
    if len(matching) != 1:
        raise ValueError("camera transport policy is not unique")
    return matching[0]
