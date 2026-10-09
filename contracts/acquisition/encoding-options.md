# Encoding argument validation and keyframe scheduling

Implementation contract under [A08](../../docs/architecture/acquisition.md#a08).
[Pixel processing](pixel-processing.md) owns native preparation and precision;
[recording lifecycle](recording-lifecycle.md) owns launch and cutoffs. This is a
specified validator/command builder, not an implemented or rig-tested encoder.

## Parsing and ownership

Consume each camera's complete token list directly, without a shell. Each supported
option below takes exactly one following token. Reject positional tokens, missing
values, NULs, option files, unknown names and unknown stream selectors. Parse aliases
to one semantic key before duplicate checks. For the single output video, absent
selectors, `:v` and `:v:0` overlap; only spellings applicable to that option are valid.
Do not silently discard, merge, reorder effective filters or override user settings.

The table is the complete initial operator option inventory. Adding an option requires
a code/table change defining its aliases, value parser, scope, duplicate behavior and
cross-checks. Installed FFmpeg help supplies capability/range evidence for known
options, never permission to forward arbitrary new options. Unsupported installed
versions/options fail with camera, token index, canonical setting and reason.

| Canonical option | Accepted aliases / value checks |
| --- | --- |
| `-c:v` | `-codec:v`, `-vcodec`, `-c:v:0`, `-codec:v:0`; one of `h264_nvenc`, `hevc_nvenc`, `av1_nvenc`, only if advertised by installed build/device and compatible with the prepared representation and MP4. Required. |
| `-pix_fmt` | Applicable video selectors; require `+<explicit-format>`, not bare `+`. Validate descriptor/component depth, chroma, codec support and exact terminal filter representation. Required. |
| `-vf` | `-filter:v`, `-filter:v:0`; single chain parsed as below, not an opaque forwarded graph. |
| `-preset`, `-tune`, `-profile:v`, `-level:v`, `-rc` | Known encoder option enums/symbolic levels; validate against selected encoder's advertised values and combinations. `-profile:v:0` and `-level:v:0` allowed. No implicit codec switch. |
| `-cq`, `-qp` | Finite numeric value of advertised type/range. `cq` requires compatible variable-rate control; `qp` requires constant-QP control. Mutually incompatible modes fail rather than silently ignoring quality. |
| `-b:v`, `-maxrate:v`, `-minrate:v`, `-bufsize:v` | Also corresponding `:v:0` spellings and `-vb` for bitrate; nonnegative decimal values with FFmpeg decimal `k`, `M`, `G` suffixes. Unqualified maxrate/minrate/bufsize apply to the sole video. Validate mode, min <= max when both active, and buffer requirements. Zero is allowed only where the selected encoder defines it. |
| `-rc-lookahead`, `-surfaces` | Nonnegative integers within advertised bounds; buffers add to memory/latency. Reject unsupported profile/codec combinations. |
| `-spatial-aq`, `-temporal-aq`, `-zerolatency` | Explicit `0` or `1`, advertised support and rate-control compatibility required. |
| `-aq-strength` | Advertised numeric range, only when spatial AQ is enabled. |
| `-multipass` | Advertised NVENC mode within one encoder process. Does not authorize file-based two-pass encoding or extra pass logs. |
| `-color_range`, `-colorspace`, `-color_primaries`, `-color_trc` | Applicable video selectors; known metadata enums. Range/matrix must agree with actual transforms. Primaries/transfer labels describe supplied settings, never establish camera calibration. |
| `-metadata:s:v:0` | Repeatable only for distinct keys `title`, `comment`, `description`, in `key=value` form. Reject duplicate keys and all structural/orientation/timing metadata. |

Single-valued options reject duplicates even when equal. Numeric parsers reject
NaN/Inf, trailing material and unsupported suffixes. Defaults are the actual installed
encoder defaults for omitted tunable options; inspect them where correctness depends
on them. Lossless tuning is accepted only if supported by the selected encoder and
consistent with rate-control/format settings; full chroma and high depth alone do
not mean lossless. The table supplies no new tuning defaults or preset abstraction.

Acquisition alone builds the raw stdin input (`-f rawvideo -pix_fmt <fmt> -s <W>x<H>
-framerate <nominal rate> -i -`, from the resolved input layout and the applied MCU or
free-running rate), stream mapping, output paths, overwrite behavior, MP4
mode/fragment flags, progress/diagnostic pipes, keyframe forcing and frame
synchronization. Inject fixed `-bf 0` from acquisition policy exactly once; validate
installed support. Injected arguments are included in effective logged arguments.
Under [SYS-002](../../architecture.md#sys-002), the backend also injects `-gpu`
exactly once using the encoder ordinal resolved to the adopted physical RTX 2080 Ti.
Validate encoder capabilities against that device, not the rendering GPU or the
first enumerated NVIDIA adapter. Retain resolved physical identity and effective
ordinal with encoding provenance. Reject operator `-gpu` overrides and aliases;
missing/unavailable hardware is a preparation failure, with no automatic adapter
fallback. This is a command-builder requirement, not a working device resolver.
Reject them and all applicable aliases/selectors in operator lists, even with equal
values. Reject user alternatives, including `-framerate`, `-s`, `-r`, `-fpsmax`, `-vsync`, `-fps_mode`, `-t`, `-to`, `-ss`, `-frames`, `-shortest`,
`-copyts`, `-itsoffset`, `-enc_time_base`, `-force_key_frames`, `-g`, `-movflags`,
`-f`, `-filter_complex`, extra streams and file-writing filter/codec options.
Acquisition also owns the output-container identity tags, global metadata-copy
suppression and `use_metadata_tags` flag under [recording identity](recording-identity.md).
Reject reserved `cephvr_*` identity keys in any operator metadata scope and attempts
to replace metadata mapping/muxer flags. The permitted stream title/comment/description
keys remain separate; no input-metadata inheritance may supply identity.
Native helpers receive only their registered inherited handles. No extra output files.

## Filters and format negotiation

Parse FFmpeg's escaping/quoting grammar into a single ordered chain. Reject graph
labels, semicolons, multi-input/output filters, commands, timeline `enable`, unknown
parameters and duplicate keys. Positional spellings map to the same parameter names
before validation. Repeated permitted filters are allowed; their order matters.

| Filter | Supported parameters and checks |
| --- | --- |
| `format` | `pix_fmts`: one explicit supported format, no fallback list; output depth >= resolved recording depth; terminal depth equals the resolved target. |
| `scale` | `w`/`width`, `h`/`height`, `flags`, `in_range`, `out_range`, `in_color_matrix`, `out_color_matrix`; fixed positive dimensions, recognized scaler flags, explicit range/matrix for color-space changes. No interlaced/dynamic modes. |
| `crop` | `w`/`out_w`, `h`/`out_h`, `x`, `y`, `exact`, `keep_aspect`; bounds, chroma alignment and constant output geometry. |
| `pad` | `w`/`width`, `h`/`height`, `x`, `y`, `color`; bounds and literal color, no dynamic evaluation. |
| `hflip`, `vflip` | No parameters. |

Dimension expressions admit finite constants, `iw`/`in_w`, `ih`/`in_h`, `ow`/`out_w`,
`oh`/`out_h`, parentheses, arithmetic and `min`, `max`, `floor`, `ceil`, `trunc`.
Resolve aliases against that stage's dimensions; reject cyclic references, division
by zero, nonintegral dimensions, invalid offsets, `n`/`t`, external state and all
unrecognized syntax. There is no general Python `eval`. Resolve the dimensions once;
validate FFmpeg's equivalent expression result rather than silently rounding sizes.
Color names/flags/enums use explicit FFmpeg tables from the supported build, not
expressions. A format conversion must have an explicit converter (`scale`) and
explicit result (`format`) when the input representation differs. With `+pix_fmt`,
FFmpeg cannot silently insert an unvalidated conversion. Fail incompatible chains.

Track dimensions, channel/chroma layout, sample depth/alignment and range/matrix at
every stage, including scaler working/output formats. A reduced-depth intermediate
below the resolved recording depth is invalid even if widened later. Match terminal
format and component depth to `+pix_fmt` and CameraSessionSettings.recording_bit_depth
(or preserved source depth when absent). The recording consumer performs the one
explicit source-to-target quantization under pixel-processing.md before FFmpeg input;
filters cannot authorize a second reduction. The shipped 8-bit argument list requires
an explicit 8-bit setting for a deeper source; 10-bit recording needs compatible edited
arguments. Reject mismatches, never rewrite one setting to fit the other. Setup validates
actual codec/build/device support, not an assumed codec-name-to-depth table.

A depth/representation mismatch blocks Setup and reports an actionable warning to
GUI/headless clients: camera role/device, native source depth, requested recording
depth (or preserve-source intent), prepared input, selected codec/output format and
the unsupported combination. Explain which explicit settings need correction; never
apply them automatically. Warning acknowledgement is not an override or Ready.
Retain the chosen precision policy until the operator changes settings and reruns
Setup. This is a preparation rejection, not an E06 in-session Continue decision.

Check the resolved post-filter width/height, codec, profile and representation against
the selected encoding adapter's capabilities. FFmpeg's compiled-in encoder/pixel-format
list does not prove that device supports them. Apply known device/build restrictions
before Ready without a test encode; retain initialization failures as failures even
after capability checks. The
[rig encoder matrix](../../reports/rig-handoff-2026-09-29/evidence/encoder-matrix.json)
documents rejection of 4112-wide H.264, H.264 10-bit and AV1 on the tested RTX 2080 Ti
path. Its successful three-frame cases are bounded evidence, not universal limits or
production validation. Do not automatically crop, resize, change depth/codec or move
encoding to another GPU. The generic codec inventory remains device-dependent.

## Fragment scheduling and runtime evidence

Build keyframe forcing from the resolved fragment interval F, in elapsed video time:
force the first retained frame and then the first available retained frame at or
after previous forced time + F (`expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+F))`).
Use locale-independent decimal seconds. This avoids a burst of catch-up keyframes
after a gap. Request independently decodable IDR boundaries where the selected codec
uses them, and fragment on keyframes with hybrid-fragmented MP4. Additional encoder
keyframes are permitted. Fragment scheduling does not create source images; F is a
target, not a loss bound. A08's explicit duplicate slots remain part of prepared input.

Use passthrough frame synchronization so FFmpeg neither duplicates nor drops input
frames: input frame n is video frame n at n / nominal rate (A08). The deferred rig
check of input format and throughput still determines whether the path sustains this;
these flags do not prove it. No capability probe performs a test encode or creates files.

At launch, detect initialization or negotiated-format disagreement as failure; before
T this is a required failure before release under A08, never a late start.
Normal closure uses online accounting and encoder finalization/exit, sync and close
under E05/A07. Do not inspect MP4 indexes/sample tables or reread video/frame-log
contents in runtime; file validation is external post hoc and there is no recovery
tool. No success claim follows merely from valid arguments or process exit zero.

API references: [FFmpeg option semantics](https://ffmpeg.org/ffmpeg.html),
[filter grammar/parameters](https://ffmpeg.org/ffmpeg-filters.html),
[NVENC option definitions](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/nvenc_h264.c).
References inform the contract; installed-build validation and rig evidence remain required.
