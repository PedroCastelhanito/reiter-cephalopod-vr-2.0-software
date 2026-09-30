"""Errors shared by the supervised FFmpeg launcher and owned process."""


class EncoderLaunchError(RuntimeError):
    """An FFmpeg launch could not reach exact registered process ownership."""
