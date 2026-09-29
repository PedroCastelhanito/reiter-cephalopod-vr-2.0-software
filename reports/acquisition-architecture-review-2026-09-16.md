# Acquisition design review and references

This supporting note points to the current decision record; it does not define
additional accepted behavior. See [architecture.md](../architecture.md), A01–A11,
and the [2026-09-20 simplification review](architecture-simplification-review-2026-09-20.md).
The old camera implementation is not a constraint on the redesign.

## Current work

Use the [single acquisition worklist](../contracts/acquisition/README.md#remaining-decisions-and-implementation-work)
for status. Camera/buffer/worker/MCU declarations now have owning contracts; their
existence does not prove implementation or rig behavior. This historical review
maintains references only and does not reopen settled decisions.

## Reference material

These sources informed the review; they do not override CephVR decisions.

- [Stytra paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC6472806/) and
  [tracking process source](https://portugueslab.com/stytra/_modules/stytra/tracking/tracking_process.html).
- [Basler feature persistence](https://docs.baslerweb.com/knowledge/saving-camera-features-or-user-sets-as-a-file-on-hard-disk)
  and [pylon persistence API](https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_feature_persistence).
- [Braid saved-video processing](https://strawlab.github.io/strand-braid/processing-saved-videos.html).
- [Unity interpolation](https://docs.unity3d.com/Manual/rigidbody-interpolation.html).
- [NVIDIA FFmpeg guide](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html).
- [FFmpeg formats and fragmentation](https://ffmpeg.org/ffmpeg-formats.html#Fragmentation)
  and [MP4 muxer source](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c).
