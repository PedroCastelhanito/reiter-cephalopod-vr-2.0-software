"""V22 submission pattern shared by trial and placement rendering."""


def photodiode_level(index: int) -> bool:
    """Three bright, three dark, then alternation in each 60 submissions."""
    if index < 0:
        raise ValueError("submission index cannot be negative")
    position = index % 60
    if position < 3:
        return True
    if position < 6:
        return False
    return position % 2 == 0
