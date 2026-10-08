# Shared pixel conversion and processing

Governing decisions: [A01/A03/A08/A10](../../docs/architecture/acquisition.md) and
[T01](../../docs/architecture/tracking.md#t01). These are implementation contracts;
no converter, processing runtime or encoding compatibility is implemented/verified.

## Acquisition and reuse

One camera worker receives, timestamps, identifies and validates each source frame.
Distribute its native packing, stride, color layout and effective bit depth through
A03's independent consumer buffers. Do not demosaic, normalize or reduce bit depth
in capture to produce a common display image. No new conversion process, converted
shared-frame cache or camera owner is introduced.

Recording, tracking and preview import the same Python conversion/pixel-processing
module. Reuse native format interpretation, unpacking, channel/layout handling,
Bayer reconstruction, RGB/grayscale conversion and explicit depth/range conversion
where needed. This is code reuse: each consumer performs only the operations its
purpose requires, in its existing process, on its private copy after slot release.
An already suitable representation needs no unnecessary conversion. Concurrent
consumers never share mutable working images or converter state.

Use the Basler SDK converter through this module for supported native recording
and preview conversions. Identical tracking preparation uses that same binding;
tracking-specific algorithms remain with tracking. Do not add an alternate unpacker
or demosaicing provider, or fall back silently. The [SDK mapping](sdk-mappings.md)
defines formats, private-buffer binding and precision/edge handling. Image-only
SDK calls are permitted in consumers; camera opening, configuration, grabbing and
PFS operations remain exclusively with the camera worker's adapter. Libraries do
not acquire a camera merely to convert an existing image.

## Consumer requirements

| Consumer | Prepared image | Precision |
| --- | --- | --- |
| Preview | RGB for color/Bayer sources; grayscale for mono | Configurable output bit depth (default 8), fixed full-source-range scaling under A10 |
| Recording | RGB for color/Bayer sources; grayscale for mono | Preserve source depth unless explicit recording_bit_depth authorizes the fixed conversion below |
| Tracking | RGB or grayscale as declared by the selected method | Retain source effective bit depth; no display scaling |

Grayscale preparation for a tracking method is intentional channel conversion, not
permission to reduce sample precision. Exact tracking normalization/features remain
algorithm-owned and undecided. Validate the method's declared input path rather
than silently substituting a different representation.

Effective bit depth is separate from storage width and packing. A 12-bit source may
use a 16-bit array after unpacking; it remains 12-bit source precision. Keep the
representation's channel order, effective depth, alignment/range, dimensions and
stride explicit in local format descriptors. Never interpret all storage bits as
sensor signal, confuse MSB/LSB alignment, or label an 8-bit-reduced image original-depth
merely because it was widened to a 16-bit array afterward.

Conversions preserve source frame identity and timestamps. Bayer reconstruction
creates color values from mosaic samples; retaining bit depth does not mean that
this is a bit-identical copy of raw sensor data. Preview and explicitly depth-converted recording use the fixed full-range mapping
below, independently in their own consumers; neither uses per-frame histogram adjustment.

## Prepared alignment and preview scaling

Native shared descriptors always describe unchanged SDK bytes. Separately resolve
consumer descriptors before Ready/viewer use: original source effective depth N,
container width W, channel order, packing, byte order, alignment, dimensions, stride
and valid numeric range. Source-depth mono/RGB preparation uses 8-bit containers
for 8-bit sources and MSB-aligned 16-bit containers for supported higher depths.
The latter retains N; W=16 does not make a 10/12-bit source a 16-bit measurement.
SDK mapping/converter settings establish the representation; never inspect observed
image minima/maxima to guess it. An unknown mapping fails preparation.

For an unsigned integer N-bit sample s, MSB storage is `u = s << (W-N)`;
LSB storage is `u = s`. Interpret byte order and unpack through the selected SDK
binding first. In an integer-aligned representation, source-value extraction is
`u >> (W-N)` for MSB and `u` for LSB, with range 0..(2^N-1). Do not shift again if
the descriptor already identifies an LSB/full-width value. An original 12-bit value
2048 becomes 32768 in prepared MSB uint16; its 8-bit preview is 128.

Preview maps interpreted source values to `Q = 2^M-1` with nearest-integer rounding:
`floor((s * Q + floor((2^N-1)/2)) / (2^N-1))`. Use wide arithmetic without overflow.
Fuse alignment interpretation and scaling into one consumer-local pass where
practical; no mandatory LSB intermediate image, frame queue or conversion service.
Equivalently, scale the declared stored range directly. If color reconstruction
retains fractional/interpolated values in the wider output, preserve those values
through this final rounding rather than truncating them with an integer right shift;
the SDK mapping must declare their range. This never changes native source-depth
provenance or authorizes guessed range/automatic contrast.

Tracking retains its prepared high-depth representation. Recording first prepares
that representation, then applies its independently resolved recording-depth conversion
below when needed; neither receives preview pixels. Tracking methods must interpret the declared alignment
and range; algorithm-specific normalization remains tracking-owned. Skip conversion
only when the full input representation matches the required output, including
alignment/range. Reuse conversion code and private buffers as above; no extra capture
work or mutable cross-consumer cache. Under A03/A10 the preview pass exists only in
explicit manual Configuration preview, never in a session.

## Validation and execution

Resolve the input format and each consumer's requested representation before required
Ready or optional viewer attachment. Validate native packing, sample alignment,
channel/Bayer pattern, row padding and conversion support. Allocate private working
storage for the resolved representation and reuse it under A03. Preserve native
shared pixels; finish each private copy before processing. Unknown mappings
fail with the format, consumer and reason; do not guess or silently reduce precision.

The common methods own image interpretation; callers own their device-independent
conversion instances and working storage. Preserve existing capture-health, consumer
overload and required-failure rules. Reuse the same implementation for an identical
conversion requested by two consumers; this does not promise a single execution of
that conversion across processes.

## Recording boundary

Native unpacking and preparation into original-depth RGB/grayscale occur in the
recording consumer through these shared methods. Resolve an appropriate FFmpeg input
pixel format for that RGB/grayscale representation with explicit channel order,
alignment and layout. Resolve optional per-camera `recording_bit_depth` to 8 or 10;
when absent use source effective depth N, which must itself be 8 or 10 for the initial
recording path. An N-bit source deeper than the target requires the explicit setting.
Before writing raw input to FFmpeg, map the source range to target M using the same fixed
full-range nearest-integer formula above, with no dithering or image-dependent scaling.
This is a recording-local pass, reusable/fusible with native preparation; unchanged
depth needs no quantization pass. Preserve source-depth provenance separately from M;
apply declared target alignment for its storage format. Tracking/native buffers stay
unchanged. Log resolved N, M and mapping `full_range_nearest_v1` (or `identity` for N=M). Do not submit Bayer mosaics or
uninterpreted packed camera pixels to FFmpeg. Avoid redundant RGB/BGR swaps, mandatory
8-bit intermediates or unnecessary mono-to-RGB expansion. The recording thread writes
these prepared raw frames to FFmpeg stdin at the nominal rate; FFmpeg/NVENC performs the selected encoding and MP4 writing. Additional encoder pixel-
format conversion and filters remain explicit in per-camera ffmpeg_args, subject to
A08's resolved recording-depth requirement. Do not use the preview image as the recording input.
No second editable quality/conversion scheme or custom FFmpeg-option syntax is added.

Validate the full input-to-codec/output representation, rather than only the array
given to the encoder. Require terminal component depth M to match the resolved setting and codec/device
capabilities; any intermediate below M or incompatible path fails Setup. An explicit
setting authorizes only this declared conversion, never an additional silent reduction
or automatic codec switch. Source-depth representation
is not a lossless-compression requirement and does not promise exact decoded samples.
The configured lossy/lossless encoding choices remain distinct.

Select the saved pixel format explicitly in each camera's `ffmpeg_args`. Compatible
YUV or RGB/grayscale storage is permitted; RGB input does not require RGB storage.
The selected format declares output depth and chroma layout. Concrete codec, pixel-
format, range and matrix defaults live only in the camera argument lists. The terminal
depth must equal resolved recording_bit_depth; a deeper source requires explicit
reduction consent as above. Select matching format/codec arguments before Setup,
without substitution.
Validate conversion range/matrix and output metadata together: metadata flags alone
do not transform samples. Do not infer camera color calibration, primaries or transfer
characteristics from the chosen encoding matrix.
Retain the resolved recording depth even when YUV is chosen; chroma subsampling and
lossy compression remain separate from the explicit source-depth conversion. Full color sampling is not lossless
compression and does not imply native sensor samples are preserved bit-for-bit.

Validate the requested output against the actual codec/GPU and the prepared input.
Reject missing format selection, precision-reducing filters, incompatible formats
or conflicting filter/output declarations before Ready; no silently negotiated
replacement. Initialization must also fail on a detected format substitution.
Successful advertised-capability checks are not proof of actual encoded output: rig
verification must inspect the saved stream's format, bit depth and chroma layout.
The raw-input format/throughput path retains its rig verification requirement.
See [NVIDIA's FFmpeg guide](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html)
and the [rig verification list](../../reports/rig-verification.md).
