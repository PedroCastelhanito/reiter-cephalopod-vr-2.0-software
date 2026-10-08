from pathlib import Path
import hashlib
import json
import subprocess

root = Path.cwd()
evidence = root / "reports/tracking-evidence-2026-10-08"
scope = [
    "src/cephvr/gui/projector_measurements.py", "src/cephvr/gui/projector_measured_profiles.py",
    "src/cephvr/gui/projectors.py", "src/cephvr/gui/calibration_files.py", "src/cephvr/gui/projector_files.py",
    "src/cephvr/gui/calibration_profile.py", "src/cephvr/gui/trial_preview_surfaces.py",
    "src/cephvr/gui/arena_movement.py", "src/cephvr/gui/feedback_signals.py",
    "src/cephvr/gui/tracking_spatial.py", "src/cephvr/gui/review_draft.py",
    "src/cephvr/tracking/processing/physical_units.py", "src/cephvr/tracking/processing/movement.py",
    "src/cephvr/tracking/processing/session.py", "src/cephvr/tracking/config/pipeline.py",
    "src/cephvr/tracking/config/validation.py", "src/cephvr/tracking/config/diagnostics.py",
    "src/cephvr/tracking/config/files.py", "src/cephvr/tracking/config/models/records.py",
    "src/cephvr/tracking/recording_schema.py", "src/cephvr/tracking/coordinator/trials.py",
    "src/cephvr/visual_stimulus/config/calibration_bars.py",
    "src/cephvr/visual_stimulus/rendering/reference_bars.py",
    "src/cephvr/visual_stimulus/rendering/display_calibration.py",
    "contracts/policy/tracking_policy.toml", "config/backends/tracking_config.toml",
    "tests/tracking/test_configuration.py", "tests/tracking/test_processing.py",
    "tests/tracking/test_recording.py", "tests/tracking/support.py",
    "tests/gui/test_dashboard.py", "tests/visual_stimulus/test_rendering.py",
    "contracts/tracking/tracking-record.schema.json",
]
context = dict(
    date="2026-10-08", timezone="Asia/Tokyo", task="physical-reference-calibration",
    source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    source_scope="Shared dirty Windows workspace with concurrent dummy-experiment repairs and temporary Visual Stimulus pacing. HEAD is not the full tested source snapshot.",
    source_sha256={name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in scope},
    checks=[
        dict(command='python -m pytest tests/tracking tests/gui tests/visual_stimulus tests/controller/test_planning.py tests/controller/test_configuration_transactions.py -q -m "not rig" --basetemp=.tmp/physical-reference-all --tb=short --junitxml=reports/tracking-evidence-2026-10-08/physical-reference-tests.xml',
             outcome="656 passed, 3 failed, 1 skipped, 1 rig deselected in 166.85 s. One stale GUI conflict fixture corrected. Two assertions depend on repository pacing remaining unset, while another chat deliberately sets calibration_front for a native dummy run."),
        dict(command='python -m pytest tests/tracking tests/gui tests/visual_stimulus tests/controller/test_planning.py tests/controller/test_configuration_transactions.py -q -m "not rig" -k "not default_and_file_policy_values_are_typed and not installed_visual_stimulus_policy_is_shared_by_edit_and_setup" --basetemp=.tmp/physical-reference-final --tb=short --junitxml=reports/tracking-evidence-2026-10-08/physical-reference-final-tests.xml',
             outcome="658 passed, 1 skipped, 3 deselected in 190.04 s. QT_QPA_PLATFORM=offscreen; authenticated local loopback permitted. Two pacing-dependent cases excluded plus one rig case."),
        dict(command='python -m pytest tests/tracking/test_configuration.py tests/tracking/test_recording.py -q -m "not rig" --basetemp=.tmp/physical-reference-post-policy --tb=short',
             outcome="57 passed in 2.18 s after final policy digest and active-Visual-Stimulus-only unit validation."),
        dict(command='python -m pytest tests/gui/test_dashboard.py -q -k "reference_measurements or old_projector_snapshot or measured_affine or custom_feedback_is_preserved" --basetemp=.tmp/physical-reference-last-gui --tb=short --junitxml=reports/tracking-evidence-2026-10-08/physical-reference-post-review-gui.xml',
             outcome="4 passed, 336 deselected in 1.89 s after final bounded generated-asset read/path validation."),
        dict(command="python -m unittest discover -s contracts/tracking -p 'test_*.py' -q", outcome="48 contract checks pass"),
        dict(command="python contracts/tracking/schema_check.py", outcome="19 schema definitions match; only changed record header declaration regenerated"),
        dict(command="python contracts/visual_stimulus/generate_schemas.py --check", outcome="11 schemas checked, zero drift"),
        dict(command="python -m ruff check src/cephvr/tracking src/cephvr/gui src/cephvr/visual_stimulus tests/tracking tests/gui tests/visual_stimulus", outcome="Pass"),
        dict(command="python -m ruff format --check src/cephvr/tracking src/cephvr/gui src/cephvr/visual_stimulus tests/tracking tests/gui tests/visual_stimulus", outcome="348 files formatted after correcting calibration_arena formatting"),
        dict(command="python -m mypy --platform win32 src/cephvr/tracking src/cephvr/gui src/cephvr/visual_stimulus", outcome="322 sources pass"),
        dict(command="python tools/check_backend_boundaries.py", outcome="625 backend modules, zero boundary violations; existing cohesion advisories reviewed"),
        dict(command="QT_QPA_PLATFORM=offscreen python .tmp/physical_reference_gui_qa.py", outcome="760×374 measurement card rendered/read visually; offscreen Segoe UI loaded explicitly for QA. No native Windows/DPI acceptance claimed."),
    ],
    limitations=["Two default/pacing-dependent cases remain affected by a concurrent temporary setting; it was preserved.",
                 "No hardware projector launch, camera calibration session, optical alignment, native DPI, swimming-speed accuracy, full-load, or durability acceptance run.",
                 "Measured mapping is local affine GUI calibration. Imported nonlinear/masked/weighted assets are preserved and rejected for automatic replacement.",
                 "Two projected axes assume the measured screen plane/optics; inferred throw distance is an ideal estimate requiring the effective throw ratio. Camera and projector scale are independent.",
                 "No legacy gain conversion or recording rewrite; video cadence padding remains separate open work."],
)
(evidence / "physical-reference-context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")

def prepend_after_title(name, title, body):
    path = root / name
    text = path.read_text(encoding="utf-8")
    assert text.startswith(title + "\n\n")
    text = text.replace(title + "\n\n", title + "\n\n" + body + "\n\n", 1)
    path.write_text(text, encoding="utf-8")

prepend_after_title("reports/tracking.md", "# Tracking status", """Current measured-reference implementation (2026-10-08, `physical-reference-calibration`)
follows [T19/T20](../docs/architecture/tracking.md#t20),
[T35/T38](../docs/architecture/tracking.md#t38) and
[T08](../docs/architecture/tracking.md#t08). Enabled experiment Tracking and runnable
locomotion diagnostics require complete camera distance endpoints/known mm with
matching source dimensions. Pipeline version 2 divides filtered pixel translation
by acquired-image px/mm and converts filtered radians/s to degrees/s before both
record admission and feedback publication. Header/output schema 3 identifies mm/s,
mm/s and deg/s; pixel-space stage evidence, exact settings (including calibration),
timing, lineage, ordering and original writer/resource ownership are preserved.
Tracking policy/config version is 43. Active Visual Stimulus input units/quantity/body
frame must match, with explicit old declaration/gain edits; disabled consumers do not
validate stale stimulus programs. No old recording or gain is silently converted.

ARCH-002 adds a focused numerical unit adapter without changing estimator math,
filter/quality state, dependencies, processes or deadlines. Extend existing behavior
tests for required scale, diagnostic independence, exact admission/publication
conversion and preserved raw evidence. Session/diagnostic size advisories remain
cohesive preparation/execution owners; only one scale value is added to MovementPorts.
Affected Tracking/GUI/Visual Stimulus/controller tests pass **658 / one skip / three
deselections**; two default/pacing assertions are excluded because another chat's
temporary native dummy setting selects calibration_front. The first broad run retains
their failures and a corrected stale GUI unit-conflict fixture. Post-review checks
pass 57 configuration/recording and four GUI cases. All 48 Tracking contract checks,
19 Tracking and 11 Visual Stimulus schema checks, lint/format (348 files), Win32 mypy
(322 sources) and boundaries (625 modules, zero violations) pass.
[Raw JUnit, commands and source hashes](tracking-evidence-2026-10-08/physical-reference-context.json).
Camera image-plane scale does not establish swimming velocity or depth/distortion
correction. No native/hardware/scientific/full-load acceptance ran; see the
[rig checklist](rig-verification.md). Earlier decoded-schema-2 evidence below retains
its historical source/unit scope.""")

prepend_after_title("reports/visual_stimulus.md", "# Visual Stimulus status", """Measured-reference implementation (2026-10-08, `physical-reference-calibration`)
follows [G01](../docs/architecture/gui.md#g01),
[V01/V15](../docs/architecture/visual_stimulus.md#v15) and
[V24](../docs/architecture/visual_stimulus.md#v24). Untimed calibration draws orange
horizontal and green vertical native-pixel bars after geometric/color correction.
Their measured mm spans derive X/Y scale and full image dimensions; the GUI derives
ideal read-only throw distance from width × effective throw ratio. Physical screen
dimensions and subject-to-screen distances remain independent. Portable full JSON 4
and numeric 3 retain measurements/native dimensions; legacy files load with unset
measurements. Output-mode mismatch invalidates scale without changing provenance.
Export/submission applies physical screen/full-image ratios with existing offsets/
inversions, creating new content-addressed 2×2 GUI affine assets. Original assets and
imported nonlinear/masked/weighted calibration are preserved; automatic replacement
of those imported corrections rejects explicitly. Planning preview shares the mapping.

ARCH-002 extracts focused bar/measurement/profile helpers; the 806-line projector
panel remains orchestration with existing draft ownership, while new numeric/file
responsibilities live outside it. No new dependency, process or persistent GPU resource.
Affected tests pass 658 plus the post-review checks described in the
[Tracking assessment](tracking.md); two concurrent temporary-pacing assertions remain
excluded and raw failures retained. Lint/format, Win32 mypy, schema drift and boundary
checks pass. [Offscreen card preview](tracking-evidence-2026-10-08/physical-reference-gui.png)
is visually inspected; [methods/source context](tracking-evidence-2026-10-08/physical-reference-context.json)
records limits. Local affine scale/ideal throw estimates require optical rig acceptance,
including current zoom/keystone/fold and depth/distortion. No projector or hardware
session is launched by this task. [Remaining acceptance](rig-verification.md).""")

path = root / "reports/runtime.md"
text = path.read_text(encoding="utf-8")
anchor = "## Current scope and review\n\n"
assert anchor in text
text = text.replace(anchor, anchor + """Current calibration/output-unit work (2026-10-08, `physical-reference-calibration`):
the [Tracking](tracking.md) and [Visual Stimulus](visual_stimulus.md) assessments own
G01/T20/T38/V15 implementation and evidence. Per-screen raw-pixel bars replace editable
throw distance with measured X/Y scale and a derived estimate; Tracking requires camera
scale and publishes mm/s/deg/s proxies. Explicit old input/gain editing and versioned
files prevent silent reinterpretation. Affected checks pass 658 (one skip; two concurrent
temporary-pacing checks excluded plus one rig deselection), with post-review owning
checks passing. The [offscreen card](tracking-evidence-2026-10-08/physical-reference-gui.png)
is visually checked. No managed runtime restart or physical calibration is claimed;
native/DPI/optical/scientific/full-load acceptance remains in the rig checklist.

""", 1)
path.write_text(text, encoding="utf-8")

path = root / "reports/rig-verification.md"
text = path.read_text(encoding="utf-8")
text = text.replace("Check all assigned outputs and per-face corrections optically; local rendered checks do not establish alignment.",
                    "Check all assigned outputs and per-face corrections optically. Under G01/V15, measure both native-pixel bar spans per screen, confirm X/Y mm/px and ideal throw estimate with current zoom/keystone/Bottom fold, compare measured affine mapping against physical screen dimensions, and invalidate changed modes/optics. Verify imported nonlinear/masked/weighted corrections are preserved. Local rendered checks do not establish alignment.")
text = text.replace("Verify no scientific files or Visual Stimulus feedback arise from diagnostics. Scientific accuracy/full-load acceptance remains separate.",
                    "Verify no scientific files or Visual Stimulus feedback arise from diagnostics. Under T20/T38, confirm missing/invalid camera calibration blocks experiment/runnable locomotion, early diagnostics still run, acquired-image scale survives crop/downscale, and known motion produces correctly converted mm/s/deg/s feedback/file values with retained pixel-space evidence. Verify explicit old gain/unit rejection; scale is not animal swimming-speed validation. Scientific accuracy/full-load acceptance remains separate.")
path.write_text(text, encoding="utf-8")
print("Updated owning reports, retained raw context and optical acceptance worklist")
