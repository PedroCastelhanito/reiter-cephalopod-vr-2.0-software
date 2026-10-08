# MP4/frame-log recording identity

Derived from [A07/A08](../../docs/architecture/acquisition.md) and
[E04](../../docs/architecture/supervisor.md#e04). Identity binds files to existing work;
it is not a checksum, content-validity certificate or crash-integrity proof.

## One identity from existing context

The camera worker constructs the identity from its validated Setup device and
scheduled trial context/output plans. Never parse a filename to manufacture it.
Require exact session and trial UUIDs, camera role (`behavioral` or `tracking`) and
confirmed physical device ID, consistent with the enabled role in session metadata.
Camera role is not a device serial; trial number alone is not trial identity. No new
recording UUID or sidecar.

| MP4 container metadata key | Frame-log header `identity` field | Value |
| --- | --- | --- |
| cephvr_identity_version | recording_identity_version | Decimal `1` in MP4; JSON integer 1. |
| cephvr_session_id | session_id | Existing canonical session UUID. |
| cephvr_trial_id | trial_id | Existing canonical trial UUID. |
| cephvr_camera_role | camera_role | Exact existing role token. |
| cephvr_device_id | device_id | Exact confirmed device identifier, not a display name. |

Use complete nonempty UTF-8 values without NULs, never truncation or case-folded
identity comparison. Existing canonical UUID/role rules apply. Device ID is capped
at 1,024 UTF-8 bytes; a longer assigned identifier is an explicit preparation error,
not permission to substitute a shorter name. The frame-log header line carries identity
from creation (also `trial_number` and `session_config_reference`, per
[frame_log_schema.toml](frame_log_schema.toml)); frame lines repeat none of it.

## Writer binding

At the existing A08 pre-T FFmpeg launch (ScheduleTrial acceptance), pass these five
output-container metadata tags with acquisition-owned `-metadata:g key=value`
arguments, alongside the existing hybrid-fragmented MP4 mode plus
`use_metadata_tags`. Build argument tokens directly, without shell interpolation or a
metadata sidecar. Identity values were prepared before Ready; no file is opened before
T. The raw stdin input carries no metadata; still disable global metadata copying with
owned `-map_metadata -1` and supply the explicit tags.

The common argument builder owns these keys, metadata-copy policy and muxer flags.
Reject operator attempts to set reserved keys in any scope, remove/suppress metadata,
change global mapping or override flags. Existing permitted per-stream title/comment/
description options remain separate. Validate installed muxer flag support during
Setup; known incompatibility blocks preparation rather than silently omitting identity.
No runtime full-file reread is added. Known write/muxer/finalization failures retain
normal failure handling; successful creation/closure alone does not prove all tags
survived or their associated video is intact.

## Post hoc pairing

There is no recovery tool. External post hoc work that pairs files should read the MP4
tags and the frame-log header identity, require exact agreement and cross-check the
owning session metadata, never guessing from filenames, chronology or frame counts.
Metadata may be missing from a crash-truncated MP4 or stripped by a tool; CephVR runtime
does not scan, repair or relabel files.

Reference: [FFmpeg MOV/MP4 options](https://ffmpeg.org/ffmpeg-formats.html).
Actual metadata survival through hybrid finalization/crashes/remuxing remains a rig
verification item, not established by the declaration or advertised flag support.
