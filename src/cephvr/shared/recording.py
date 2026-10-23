"""E04 session output selection shared by controller and backend owners."""

from collections.abc import Iterable

from cephvr.control.v1 import types_pb2 as pb


def recording_enabled(backends: Iterable[pb.BackendSettings]) -> bool:
    """All explicitly disabled active save selections mean a dummy test session.

    Unresolved settings retain the normal validation path; absence is not Off.
    Synchronization participation is the GUI's SpikeGLX recording selection.
    """
    resolved_selection = False
    for backend in backends:
        if not backend.enabled:
            continue
        if backend.backend_name == "synchronization":
            return True
        if backend.backend_name == "visual_stimulus":
            resolved_selection = True
            settings, field = backend.visual_stimulus, "save_visual_stimulus_data"
            if not settings.HasField(field) or getattr(settings, field):
                return True
        elif backend.backend_name == "tracking":
            resolved_selection = True
            if (
                not backend.tracking.HasField("save_tracking_data")
                or backend.tracking.save_tracking_data
            ):
                return True
        elif backend.backend_name == "acquisition":
            resolved_selection = True
            for role in ("behavioral", "tracking", "eye_tracking"):
                camera = getattr(backend.acquisition, role)
                if camera.enabled and (
                    not camera.HasField("save_video") or camera.save_video
                ):
                    return True
    return not resolved_selection
