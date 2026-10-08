from pathlib import Path
import re

root = Path.cwd()
revisions = {}

def edit(name, pairs, ids=()):
    path = root / name
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            raise RuntimeError(f"Missing amendment anchor in {name}: {old[:90]}")
        text = text.replace(old, new, 1)
    for decision in ids:
        pattern = rf"(### {decision} — .*?\*\*Revision:\*\* )(\d+)"
        match = re.search(pattern, text, re.S)
        if not match:
            raise RuntimeError(decision)
        revision = int(match.group(2)) + 1
        text = text[:match.start(2)] + str(revision) + text[match.end(2):]
        revisions[decision] = revision
    path.write_text(text, encoding="utf-8")

edit("docs/architecture/tracking.md", [
    ("- Header schema version 2 identifies T15's decoded feedback/stage format. Keep",
     "- Header schema version 3 identifies decoded feedback/stage objects with T38's\n  calibrated output units and pipeline version 2. Retain pixel-space stage evidence. Keep"),
    ("- Optional two-endpoint distance calibration retains exact acquired-image dimensions,\n  endpoints and positive known millimetres; derived image-plane scale is metadata\n  independent of downscale. It does not calibrate swimming speed or change T35/T38\n  output units. Source changes require revalidation, never silently reused scale.",
     "- Enabled experiment Tracking and locomotion diagnostics require two distinct\n  camera-image distance endpoints, positive known millimetres and exact source\n  dimensions. Validate the derived acquired-image px/mm against the endpoints and\n  prepared source, independently of crop/downscale. T38 uses it for linear outputs;\n  it does not establish physical swimming velocity. Earlier diagnostic stages may\n  run without scale. Source changes require revalidation, never guessed scale."),
    ("- Target relative locomotion-control signals for closed-loop Visual Stimulus, mapped to virtual\n  movement by configurable gains; never label them measured physical swimming velocities\n  or infer calibration from camera flow or body dimensions.",
     "- Publish camera-scale-calibrated locomotion-control proxies in mm/s for forward\n  and sideways and deg/s for turning, mapped to virtual movement by explicit gains.\n  They remain image-plane flow-derived controls, not measured animal swimming\n  velocities. Never infer calibration from camera flow or body dimensions."),
    ("### T38 — Direct estimator units through existing Visual Stimulus gains",
     "### T38 — Calibrated estimator outputs through existing Visual Stimulus gains"),
    ("- Feed each relative drive in its declared estimator units directly into the compatible\n  Visual Stimulus feedback binding; no reference normalization, session activity rescaling, fixed\n  [-1,1] range or adaptive gain normalization before the Visual Stimulus gain.",
     "- Pipeline version 2 converts the filtered pixel-space forward/sideways controls\n  once by dividing by T20's acquired-image px/mm, and converts filtered angular\n  radians/s to degrees/s. Publish mm/s and deg/s through the existing Visual Stimulus\n  feedback binding. Preserve raw/filter intermediates in px/s and rad/s for evidence;\n  no activity rescaling, fixed [-1,1] range or adaptive gain normalization."),
    ("  gains; changing method never silently remaps units, reuses incompatible bindings or\n  converts to physical speed.",
     "  gains. Require matching program input units/quantity/body frame before preparation;\n  old px/s or 1/s bindings must be edited explicitly with their gains. Never rewrite\n  old recordings or silently reinterpret their units."),
    ("- Turning is an angular rate in 1/s (radians per second): the signed area-weighted",
     "- The estimator's internal turning rate is in rad/s (1/s), converted to deg/s\n  at T38's output boundary: the signed area-weighted"),
], ("T19", "T20", "T35", "T38", "T43"))

edit("docs/architecture/gui.md", [
    ("  source-image px/mm and mm/px independently of downscale; this is not physical swimming-speed calibration\n  or a change to T35/T38 output units. Source/image changes invalidate annotations;",
     "  source-image px/mm and mm/px independently of downscale, required for enabled\n  Tracking/locomotion diagnostics under T20. T38 declares mm/s and deg/s outputs;\n  gain controls show mm/mm and deg/deg. Source/image changes invalidate annotations;"),
    ("  projector distance and throw ratio, with an unlabeled row-name column and wrapped\n  headers.",
     "  derived read-only projector distance and effective throw ratio, with wrapped\n  headers. Per-screen measured horizontal/vertical reference bars retain native output\n  pixels and known millimetres, derive independent X/Y mm/px and full projected\n  image dimensions; full projected width times throw ratio estimates ideal throw\n  distance (Bottom: total folded path). Subject-to-screen distances stay independent.\n  Measurements from another assigned projector are cleared; imported historical\n  distances remain visible until measurements are supplied. Missing or partial\n  measured pairs cannot produce a calibrated mapping."),
    ("authority and cancel pickers on authority loss. Version 3 merges the former runtime",
     "authority and cancel pickers on authority loss. Version 4 retains reference\n  measurements and their native output dimensions alongside the former runtime"),
    ("  fail without guessing. Numeric-only versions 1/2 preserve other settings, and legacy",
     "  fail without guessing. Legacy full version 3 and numeric-only versions 1/2\n  load with unset measurements; numeric version 3 retains them. Legacy"),
    ("  pixel offset and inverse-axis drafts, defaulting unset values to diagnostic\n  identity; reject corrections extending outside the output.",
     "  pixel offset and inverse-axis drafts, applying measured physical screen/image\n  ratios when supplied and defaulting unmeasured values to diagnostic identity;\n  reject corrections extending outside the output. Submission publishes new\n  content-addressed measured affine assets for GUI-owned 2×2 profiles, preserves\n  originals and rejects replacing imported nonlinear/masked/weighted calibration."),
    ("  These profiles are uncalibrated optical placeholders and do not set experiment\n  defaults.",
     "  Unmeasured profiles are diagnostic placeholders; measured affine mappings\n  still require optical acceptance and do not set experiment defaults."),
], ("G01",))

edit("docs/architecture/visual_stimulus.md", [
    ("  and resource closure; uncertain cleanup blocks Setup.",
     "  and resource closure; uncertain cleanup blocks Setup. Calibration-only orange\n  horizontal and green vertical reference bars span rounded native pixel boundaries\n  at 3/8 and 5/8 of each output dimension. Draw them after geometric/color output\n  correction so their measured lengths refer to raw device pixels; no trial timing,\n  recording or extra persistent GPU resource is added."),
    ("  subject position and projector-to-screen distances are distinct inputs.",
     "  subject position and derived ideal projector throw distance remain distinct.\n  G01's measured raw-pixel bars derive X/Y scale and generate static affine mapping\n  assets for GUI-owned profiles using physical screen/full-image ratios and existing\n  offsets/inversions. Preserve imported warps, masks, weights and overlap ownership;\n  this does not solve nonlinear optics or change runtime projection ownership."),
    ("by movement integration to that arena's yaw (1/s, deg per radian)",
     "by movement integration to that arena's yaw (deg/s, deg per deg)"),
], ("V01", "V15", "V24"))

path = root / "architecture.md"
text = path.read_text(encoding="utf-8")
for decision, revision in revisions.items():
    pattern = rf"(^\| .*?\[{decision}\].*?\| Accepted \| )\d+( \|$)"
    text, count = re.subn(pattern, rf"\g<1>{revision}\2", text, flags=re.M)
    if count != 1:
        raise RuntimeError(f"Register {decision}: {count}")
text = text.replace("| Direct estimator units through existing Visual Stimulus gains |",
                    "| Calibrated estimator outputs through existing Visual Stimulus gains |")
path.write_text(text, encoding="utf-8")

edit("contracts/tracking/records.md", [
    ("Header with `schema_version: 2`. Version 1 used\nbase64 feedback and escaped stage payloads; readers reject unsupported schemas and",
     "Header with `schema_version: 3`. Version 1 used\nbase64 feedback/escaped stage payloads; version 2 decoded them but published pixel/radian\nunits. Version 3 keeps decoded objects and identifies calibrated mm/s and deg/s output\nwith pipeline implementation version 2. Readers reject unsupported schemas and"),
    ("valid filtered_average channel to the paired FeedbackResult, including quantity, units,\nsource interval and validity.",
     "valid filtered_average channel to the paired FeedbackResult after T38 conversion:\nforward/sideways divided by Header's validated TrackingSettings.image_scale.pixels_per_mm,\nturn multiplied by 180/pi. Pixel-space evidence remains px/s and rad/s; feedback declares\nmm/s and deg/s. Verify quantity, source interval and validity as well as converted values."),
])
edit("contracts/tracking/recording.md", [("`schema_version=2`", "`schema_version=3`")])
edit("contracts/tracking/pipeline-catalogue.md", [
    ("both implementation version 1", "both implementation version 2"),
    ("6. Map filtered_average's three named channels into the existing FeedbackResult.",
     "6. Convert filtered_average's linear channels from acquired-image px/s to mm/s\n   using the required camera pixels_per_mm, and angular rad/s to deg/s, then map\n   them into the existing FeedbackResult. Keep stage evidence in original pixel units."),
    ("sideways_drive in px/s; turn_drive in 1/s (radians per second).",
     "sideways_drive in mm/s; turn_drive in deg/s. Full settings validation requires\nmatching acquired-image dimensions, distinct camera distance endpoints and a positive\nknown millimetre length. Pure pipeline composition does not invent a camera scale."),
    ("The host uses filtered_average directly in feedback and evidence so their values agree.",
     "The host retains filtered_average in pixel-space evidence and applies T38 conversion\nto feedback; cross-record comparisons use the retained camera scale and 180/pi."),
])
edit("contracts/tracking/locomotion-output.md", [
    ("as Visual Stimulus input units: forward/sideways px/s bind together through heading_relative_planar_integration\nto arena x/y (mm per px); turn 1/s binds by movement_integration to arena yaw (deg per radian).",
     "as Visual Stimulus input units: forward/sideways mm/s bind together through heading_relative_planar_integration\nto arena x/y (virtual mm per input mm); turn deg/s binds by movement_integration to arena yaw\n(virtual deg per input deg). T20 camera endpoints/known mm are mandatory for enabled\nTracking. T38 divides pixel-space filtered translation by acquired-image pixels_per_mm\nand converts angular radians/s by 180/pi exactly once before feedback publication.\nRetain original estimator evidence. Old input declarations and gains require explicit\noperator edits; no gain migration or historical-file relabeling occurs."),
])
edit("contracts/tracking/water-flow-proxy.md", [
    ("Forward/sideways units are px/s (acquired-image pixels/s). Turning units are 1/s",
     "Internal raw/filter evidence forward/sideways units are px/s (acquired-image pixels/s). Turning units are 1/s"),
    ("conversion to virtual speed: linear gain is virtual mm per input px and turn gain is\nvirtual deg per radian, each integrated once over the source interval in Visual Stimulus.",
     "conversion to virtual speed after T38's output boundary: divide filtered translation\nby the required acquired-image pixels_per_mm and multiply filtered turn by 180/pi.\nFeedback is mm/s and deg/s; gains are virtual mm per input mm and virtual deg per input\ndeg, each integrated once over the source interval in Visual Stimulus. Equations and\ncompact raw/filter evidence above remain pixel-space quantities."),
])
edit("contracts/gui-calibration.md", [
    ("resolution/refresh properties and display-to-projector assignments are excluded.",
     "current display inventory/refresh properties and display-to-projector assignments\nare excluded. Reference measurements retain their native pixel dimensions as measurement\nprovenance; they do not assign an output."),
    ("- `version`: integer `3`.", "- `version`: integer `4`."),
    ("Numeric-only versions 1/2 remain loadable and leave synchronization, participation",
     "Numeric-only versions 1/2/3 remain loadable and leave synchronization, participation"),
    ("numeric GUI values and physical assignments. Save always writes the merged version 3.",
     "numeric GUI values and physical assignments. Legacy full version 3 and numeric\nversions 1/2 acquire unset reference fields. Save writes merged version 4; numeric\ncalibration snapshots use version 3. Legacy inventories reject unknown new fields."),
    ("`offset_x`, `offset_y`, `flip_x`, `flip_y` |",
     "`offset_x`, `offset_y`, `flip_x`, `flip_y`, `reference_width_px`, `reference_height_px`, `reference_x_mm`, `reference_y_mm` |"),
    ("Lengths are millimetres except pixel offsets; scale, throw ratio and orthogonality",
     "In managed calibration, orange horizontal and green vertical bars run between\nrounded 3/8 and 5/8 native-output pixel boundaries, after output correction. Measure\ntheir full spans in mm. X/Y mm/px are measured length divided by their corresponding\npixel span; full projected image dimensions multiply those scales by output dimensions.\nRead-only `distance` is projected image width × effective `throw`, with Bottom using\nthe folded total path. Subject-to-screen distances remain independent. Old unmeasured\ndistances remain historical display values; no scale is inferred from them.\n\nBoth measured axes and matching native output dimensions are required when applying\nmeasurements. The exporter multiplies existing scale_u/v by physical screen width/height\ndivided by full projected image width/height, preserving offsets/inversions. Submission\ncreates content-addressed 2×2 assets for GUI affine profiles and preserves source assets;\nimported nonlinear/masked/weighted profiles require their existing calibration workflow.\nThis local affine approximation requires optical verification, especially distortion/depth.\n\nLengths are millimetres except pixel offsets/reference dimensions; scale, throw ratio and orthogonality"),
])

edit("contracts/tracking/pose.md", [
    ("## Common landmark coordinates",
     "## Required camera distance calibration\n\nT20 requires TrackingSettings.image_scale for enabled experiment Tracking and locomotion\ndiagnostics: positive acquired-image width/height, two distinct finite in-bounds endpoints,\npositive known distance_mm and pixels_per_mm equal to endpoint separation/distance_mm\n(1e-9 relative, 1e-12 absolute tolerance). Dimensions must match pose/reference and prepared\nsource. It stays independent of crop/downscale and projector bars. Earlier diagnostic\nstages may omit scale. T38 uses this local image-plane scale for mm/s outputs; calibrated\nflow proxies do not establish animal swimming velocity or depth/distortion correction.\n\n## Common landmark coordinates"),
])

with (root / "LOG.md").open("a", encoding="utf-8") as stream:
    stream.write("\n### 2026-10-08 [gui] [tracking] [visual_stimulus] Implement measured reference calibration\n\n"
                 "- Owner authorizes `physical-reference-calibration`. Amend G01/V01/V15/V24 and T19/T20/T35/T38/T43/register: per-screen native-pixel bars and measured X/Y mm derive affine scale and ideal read-only throw distance; subject screen distances stay independent. Required camera endpoint scale gates experiment Tracking/locomotion diagnostics, with mm/s and deg/s output conversion, pipeline version 2, file header 3 and Tracking policy 43. Preserve pixel/radian stage evidence and reject incompatible legacy stimulus unit/frame/quantity bindings rather than changing gains or old files.\n"
                 "- ARCH-002 uses focused measurement/profile/unit/bar helpers without dependencies, processes or whole-runtime references; projector orchestration retains existing state ownership. Export/submission creates content-addressed GUI affine assets, preserving source profiles and refusing imported optical warps. Shared preview uses the exporter mapping. Portable full JSON 4/numeric 3 migrate old inventories with unset measurements and fail atomically on unknown keys. Extend existing owner tests.\n"
                 "- Focused Tracking passes 79, rendering 19, Win32 mypy 322 sources. Correct initial policy digest parsing to Decimal, stale policy fixture and a misplaced GUI assertion; repair a Windows cp1252-to-UTF-8 scripted read roundtrip before continuing. Current affected integration run is in progress. Native/optical/scientific/full-load acceptance remains open; no runtime restart or hardware session is claimed.\n")
print(revisions)
