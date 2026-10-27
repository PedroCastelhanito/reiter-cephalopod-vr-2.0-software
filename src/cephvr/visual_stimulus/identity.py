"""Visual Stimulus child-process roles (distinct from acquisition FFmpeg roles, E08)
and the file-policy contract version the controller must echo at Setup (E14)."""

CONTRACT_VERSION = 1

FFMPEG_ROLE = "visual_stimulus_ffmpeg"
FFMPEG_PROBE_ROLE = "visual_stimulus_ffmpeg_probe"
FFMPEG_ROLES = frozenset((FFMPEG_ROLE, FFMPEG_PROBE_ROLE))
# Contained Python helper owned like FFmpeg: pipes, stdin-EOF stop, no output (V04).
SPARSE_NOISE_ROLE = "visual_stimulus_sparse_noise"
HELPER_ROLES = FFMPEG_ROLES | {SPARSE_NOISE_ROLE}
