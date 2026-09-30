"""Acquisition camera adapter and its SDK-independent contracts."""

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.camera.types import CameraAdapter

__all__ = ["BaslerCameraAdapter", "CameraAdapter"]
