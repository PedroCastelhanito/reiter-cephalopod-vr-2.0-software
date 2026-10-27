"""V22 submission pattern shared by trial and placement rendering."""

from cephvr.visual_stimulus.config.models.display_profile import PhotodiodeMode


def photodiode_level(index: int, mode: PhotodiodeMode = "landmarks") -> bool:
    """Selected submission pattern; both modes start bright."""
    if index < 0:
        raise ValueError("submission index cannot be negative")
    if mode == "every_frame":
        return index % 2 == 0
    if mode != "landmarks":
        raise ValueError("Unsupported photodiode mode")
    position = index % 60
    if position < 3:
        return True
    if position < 6:
        return False
    return position % 2 == 0
