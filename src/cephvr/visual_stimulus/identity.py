"""Visual Stimulus renderer child-process roles, distinct from acquisition FFmpeg roles (E08)."""

FFMPEG_ROLE = "visual_stimulus_ffmpeg"
FFMPEG_PROBE_ROLE = "visual_stimulus_ffmpeg_probe"
FFMPEG_ROLES = frozenset((FFMPEG_ROLE, FFMPEG_PROBE_ROLE))
