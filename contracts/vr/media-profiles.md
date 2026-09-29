# VR source media profiles

Governing scope: [V04](../../docs/architecture/vr.md#v04). Use this focused catalogue
for stimulus inputs, independently of acquisition encoding and VR review recordings.
The identifiers below are versioned interpretation contracts, not a claim that
importers/decoders are implemented or rig throughput is verified. Unsupported input
must be exported externally to a supported profile; no automatic transcoding stage.

## Image and video catalogue

| Profile ID | Required content profile |
| --- | --- |
| png_uint_v1 | One static PNG image; unsigned 8/16-bit grayscale, grayscale-alpha, RGB or RGBA. Indexed PNG may expand its palette/transparency losslessly to 8-bit channels. Reject animated PNG and unsupported sample profiles. |
| tiff_uint_v1 | One TIFF image/page; unsigned 8/16-bit grayscale or RGB, with absent or explicitly described alpha. Support uncompressed, LZW or Deflate storage, tiled or stripped; reject float/signed samples, ambiguous extra samples, CMYK and multipage/stack inputs. Lossless predictor decoding must preserve values. |
| jpeg8_v1 | One baseline/progressive 8-bit photographic JPEG, grayscale or three-component color decoded to RGB. Reject CMYK/YCCK, unusual precision and multi-image content. JPEG is a lossy source; decoded samples are not an original-lossless claim. |
| mp4_h264_sdr8_v1 | A finite, local MP4 with one H.264/AVC video stream: Baseline/Main/High family, progressive 8-bit 4:2:0 SDR. Constant or variable frame timing is allowed if explicit presentation intervals/endpoints can be resolved. Reject encrypted, interlaced, HDR, unsupported profiles and changing resolution/representation. |
| matroska_ffv1_v3_uint_v1 | A finite Matroska file with one FFV1 version 3 video stream. Unsigned 8/16-bit grayscale or full-resolution RGB/RGBA channels; no unsupported subsampling, signed/float samples or changing representation. Lossless refers to encoded source samples, not later display or GPU reproduction. |

For FFV1, map decoder formats gray/gray16, bgr0/bgra, gbrp and gbrp16/gbrap16 to their
explicit channel/depth/stride descriptions, accepting the decoder's declared byte
order. Ignore only documented padding channels; preserve actual alpha. Do not
identify precision from storage width alone or route 16-bit data through 8-bit RGB.
Additional decoder representations require a verified mapping before admission.

Recognize the actual container, codec/profile and decoded representation, not merely
a suffix. The selected implementation/build must provide the declared profile;
library support for another format does not automatically extend CephVR's catalogue.
Decode failure or unavailable required support blocks preparation with the asset,
profile and reason. Preserve corrupt-frame/error signals; decoder concealment must
not silently turn a known damaged stimulus into accepted content.

Non-video tracks do not become stimuli: explicitly report ignored audio/subtitle/data
tracks in preparation diagnostics; no audio playback or automatic stream selection
among several video streams. A video asset must identify exactly one supported video
stream. Validate ordered, nonoverlapping positive presentation intervals; reject
missing/ambiguous timing instead of replacing it with nominal FPS. Do not infer its duration from audio, nominal FPS or container duration alone.
V09's endpoint rules remain required; timestamp indexing/resolution is Setup work on
the protected source, not a per-trial file scan or full-clip decoded-frame cache.
The concrete timestamp/index adapter must reject unresolved endpoints before Ready.

## Pixel interpretation and dependencies

Decode image orientation and video display transforms into an explicit prepared
mapping once. Retain coded dimensions, effective dimensions, sample aspect/orientation
and any supported transform. No silent crop, stretch, channel swap, dynamic contrast
normalization or guessed fallback FPS. An unsupported transform blocks preparation.
Logical texture coordinates and GPU row orientation must have one documented mapping;
image-library defaults cannot determine scientific coordinate signs.

Retain source depth, channel/plane layout, row strides, alpha declaration and color
metadata before conversion. ICC/transfer/primaries/range/matrix/chroma-location data
must not be silently discarded or replaced with guessed values. Resolve interpretation
through the common color contract; unsupported or ambiguous color data blocks Ready
until explicitly resolved. The [color pipeline](color-pipeline.md) binds the working interpretation and
composition; [output precision](output-precision.md) binds explicit per-output RGB8/RGB10 selection.
In particular, 16-bit input support is not a promise of 16-bit
projector output or proof of calibrated luminance.

Use [protected sources](asset-lifetime.md) for every read, including embedded or
external arena textures. Retain effective importer/decoder identity, profile ID and
interpretation under V13's existing provenance scope. No extra per-frame central log,
asset archive or normal output-file validator is introduced.

## Static arena profile

`glb2_static_unlit_v1` uses GLB/glTF 2.0 scene/node transforms and indexed or nonindexed
triangle meshes, POSITION, TEXCOORD_0 and optional COLOR_0. Resolve the declared scene
and static transforms at preparation; preserve winding, culling/double-sided intent
and UVs rather than repairing them from guessed inside/outside geometry. The instance
still moves under V16/V27; static means no imported skeletal/morph animation system.

Use base-color factor/texture and supported vertex-color multipliers under V17.
Support unlit materials, including KHR_materials_unlit; glTF base-color texture RGB
has its specified sRGB interpretation and alpha is coverage. Support OPAQUE and MASK
material coverage with the authored cutoff; initial arena profile rejects BLEND
materials rather than silently flattening them or promising general transparency
sorting. This restriction does not reject alpha in supported 2D image stimuli.

Support standard glTF sampler wrap/filter choices with prepared mipmaps where needed.
Textures use glTF's PNG/JPEG profiles; their image bytes also pass the catalogue's
sample checks. Buffer views and local external dependencies must use the protected
resolver. Embedded resources keep container identity plus stable subresource identity.
Bounds/accessors/indices and finite transforms are checked before GPU allocation.

Reject unsupported required extensions, compression schemes, skins, morph targets,
imported animation, extra UV sets required by materials, and appearance requiring
lit/PBR terms. Ordinary glTF PBR defaults do not introduce lighting; the importer
reports its explicit base-color-only interpretation. Nontrivial normal/occlusion/
emissive/metallic-roughness textures or extensions requiring a different appearance
must be baked externally or rejected, never silently approximated. Unused descriptive
metadata may be ignored; it cannot set protocol movement boundaries or observer pose.
No full glTF feature-parity claim is made.

## Remaining implementation and verification

[Native adapter/resource bindings](runtime-bindings.md) and [typed provider interfaces](resource_types.pyi) now declare these mappings, with manifest/interpretation schemas in artifact_models.py. Their provider implementation and explicit numeric capacities remain required. Linear composition and measured correction are now bound in the
[color pipeline](color-pipeline.md) and [photometric contract](photometric-calibration.md). The catalogue
binds support boundaries; it does not deliver those implementations. C14's selected
video path is declared in [decoder ownership](decoder-ownership.md).
Verification must cover exact high-depth sample preservation, profiles/unsupported
features, orientation and channel mapping, VFR/reordering/loops/endpoints, damaged
input, independent instances and the actual four-output workload. Runtime and rig
verification remain outstanding, with hardware measurements deferred under E15.
Acquisition's encoder/input-container deferral remains unchanged.

Format references: [PNG specification](https://www.w3.org/TR/png-3/),
[glTF 2.0](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html),
[FFV1](https://www.rfc-editor.org/rfc/rfc9043.html).
