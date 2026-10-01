"""Visual Stimulus trial recipe, evidence, capture, and review-recording support."""

from .recipe import PreparedRecipe, prepare_recipe, publish_recipe
from .session import RecordingSession, WindowsEncoderInputAdapter

__all__ = [
    "PreparedRecipe",
    "NativeRecording",
    "RecordingSession",
    "WindowsEncoderInputAdapter",
    "prepare_recipe",
    "publish_recipe",
]


def __getattr__(name: str) -> object:
    if name == "NativeRecording":
        from .native import NativeRecording

        return NativeRecording
    raise AttributeError(name)
