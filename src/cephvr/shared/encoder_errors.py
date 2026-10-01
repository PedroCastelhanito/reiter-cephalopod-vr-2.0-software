"""Errors from registered encoder-process ownership."""


class EncoderLaunchError(RuntimeError):
    """A supervised encoder did not reach exact registered process ownership."""
