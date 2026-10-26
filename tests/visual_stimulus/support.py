"""Shared Visual Stimulus compiler fixtures used by compiler and lifecycle tests."""

from __future__ import annotations

import json
import struct
from copy import deepcopy
from pathlib import Path

from cephvr.visual_stimulus.compiler import CompileContext, compile_trial
from cephvr.visual_stimulus.config.models.artifact_models import (
    GeometricProfile,
    PreparedTrial,
    ResourceManifest,
)
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    parse_display_json,
)
from cephvr.visual_stimulus.config.models.evidence_model import Identity, State
from cephvr.visual_stimulus.config.models.program_model import (
    Program,
    TrialArenaBoundaries,
    parse_program_json,
)
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    DisplayInitialization,
    OutputActivity,
    RenderGroup,
    RenderUpdate,
    ResourceReleaseReport,
)

_ROOT = Path(__file__).resolve().parents[2]
_PROGRAM_FIXTURE = (
    _ROOT / "contracts" / "visual_stimulus" / "examples" / "drift-hold.json"
)


def glb_fixture(*, texture=False, external=False):
    """Return a compact GLB document and binary payload for resource tests."""
    binary = struct.pack("<9f3H", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 3},
            {"bufferView": 1, "componentType": 5123, "type": "SCALAR", "count": 3},
        ],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}
                ]
            }
        ],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "extensionsRequired": ["KHR_materials_unlit"],
        "materials": [
            {
                "extensions": {"KHR_materials_unlit": {}},
                "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.25, 1, 1]},
            }
        ],
    }
    if texture:
        document["images"] = [{"uri": "textures/fish.png"}]
        document["textures"] = [{"source": 0, "sampler": 0}]
        document["samplers"] = [{"wrapS": 33648, "minFilter": 9987}]
    if external:
        document["buffers"][0]["uri"] = "mesh.bin"
    return document, binary


def pack_glb(document, binary):
    """Pack the fixture JSON and binary chunks into a GLB 2.0 byte string."""
    data = json.dumps(document).encode()
    data += b" " * (-len(data) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(data), 0x4E4F534A) + data
    chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def _linked_texture_fixture():
    """Unequal observer distances and inward-facing rectangular screen axes."""
    from cephvr.visual_stimulus.config.models.display_profile import Geometry
    from cephvr.visual_stimulus.config.models.program_model import TextureSettings

    geometry = Geometry.model_validate_json(
        json.dumps(
            {
                "frame_id": "rig-mm",
                "observer_mm": [0, 0, 0],
                "near_mm": 1,
                "far_mm": 1000,
                "positional_tolerance_mm": 0.01,
                "orthogonality_tolerance": 0.001,
                "surfaces": [
                    {
                        "surface_id": face,
                        "bottom_left_mm": bl,
                        "bottom_right_mm": br,
                        "top_right_mm": tr,
                        "top_left_mm": tl,
                    }
                    for face, bl, br, tr, tl in (
                        (
                            "bottom",
                            [-100, -100, -30],
                            [100, -100, -30],
                            [100, 100, -30],
                            [-100, 100, -30],
                        ),
                        (
                            "front",
                            [100, -100, -30],
                            [-100, -100, -30],
                            [-100, -100, 100],
                            [100, -100, 100],
                        ),
                        (
                            "left",
                            [-40, -100, -30],
                            [-40, 100, -30],
                            [-40, 100, 100],
                            [-40, -100, 100],
                        ),
                        (
                            "right",
                            [60, 100, -30],
                            [60, -100, -30],
                            [60, -100, 100],
                            [60, 100, 100],
                        ),
                    )
                ],
            }
        )
    )
    base = make_program().sequence[0].settings[0].model_dump(mode="json")
    settings = []
    for face, period in (("bottom", 100), ("front", 50), ("left", 80), ("right", 120)):
        data = deepcopy(base)
        data.update(
            instance_id=face,
            linked_to=None if face == "bottom" else "bottom",
            pattern={
                "kind": "image_tile",
                "asset_id": face,
                "period_x": {"kind": "constant", "value": period},
                "period_y": {"kind": "constant", "value": period},
                "sampling": "nearest",
            },
            space={
                "kind": "physical_surface",
                "frame_id": "rig-mm",
                "mappings": [{"surface_id": face, "matrix": [[1, 0, 0], [0, 1, 0]]}],
            },
            motion={k: {"kind": "hold"} for k in ("x", "y", "rotation")},
            phase_x={"kind": "hold"},
            phase_y={"kind": "hold"},
            reset=False,
        )
        settings.append(TextureSettings.model_validate_json(json.dumps(data)))
    return geometry, settings


def _texture_rate(value):
    from cephvr.visual_stimulus.config.models.program_model import Constant, Rate

    return Rate(kind="rate", function=Constant(kind="constant", value=float(value)))


def valid_display_json() -> str:
    """Return a valid small display profile that needs no measured device state."""
    surface = {
        "bottom_left_mm": [-10.0, 10.0, 100.0],
        "bottom_right_mm": [10.0, 10.0, 100.0],
        "top_right_mm": [10.0, -10.0, 100.0],
        "top_left_mm": [-10.0, -10.0, 100.0],
    }
    profile = {
        "format_version": 1,
        "geometry": {
            "frame_id": "frame",
            "observer_mm": [0.0, 0.0, 0.0],
            "near_mm": 1.0,
            "far_mm": 1000.0,
            "positional_tolerance_mm": 0.1,
            "orthogonality_tolerance": 0.01,
            "surfaces": [
                {"surface_id": name, **surface}
                for name in ("front", "left", "right", "bottom")
            ],
        },
        "outputs": [
            {
                "output_id": "projector/main",
                "device_identity": "edid:one",
                "width_px": 100,
                "height_px": 100,
                "refresh_numerator": 60,
                "refresh_denominator": 1,
                "rgb_bits_per_channel": 8,
            }
        ],
        "mappings": [
            {
                "mapping_id": f"map-{name}",
                "surface_id": name,
                "output_id": "projector/main",
                "viewport": {"x": 0, "y": 0, "width": 100, "height": 100},
                "geometric_profile": {"logical_path": f"geometry/{name}.json"},
            }
            for name in ("front", "left", "right", "bottom")
        ],
        "photometric_mode": "uncalibrated",
        "idle_linear_rgb": [0.0, 0.0, 0.0],
        "photodiode_output_id": "projector/main",
        "photodiode_patch": {
            "rect": {"x": 0, "y": 0, "width": 10, "height": 10},
            "high_linear_rgb": [1.0, 1.0, 1.0],
            "low_linear_rgb": [0.0, 0.0, 0.0],
        },
    }
    return json.dumps(profile)


def _geometric_profiles(display: DisplayProfile) -> dict[str, object]:
    profiles = {}
    for mapping in display.active_mappings:
        output = next(
            item
            for item in display.active_outputs
            if item.output_id == mapping.output_id
        )
        profiles[mapping.mapping_id] = GeometricProfile.model_validate(
            {
                "format_version": 1,
                "calibration_id": "diagnostic_test",
                "mapping_id": mapping.mapping_id,
                "surface_id": mapping.surface_id,
                "output_id": output.output_id,
                "output_width": output.width_px,
                "output_height": output.height_px,
                "viewport": mapping.viewport,
                "rows": 2,
                "columns": 2,
                "vertices": (
                    {"uv": (0, 0), "xy": (0, 0)},
                    {"uv": (1, 0), "xy": (1, 0)},
                    {"uv": (0, 1), "xy": (0, 1)},
                    {"uv": (1, 1), "xy": (1, 1)},
                ),
                "orientation": "preserving",
                "diagonal": "bottom_left_to_top_right",
                "mask": None,
                "weight": None,
                "overlap_group": None,
                "intended_coverage": ((0, 0), (1, 0), (1, 1), (0, 1)),
                "coverage_tolerance": 0.01,
                "triangle_area_tolerance": 0.0001,
            }
        )
    return profiles


def fixture_source() -> str:
    """Return the canonical source program used for small runtime tests."""
    return _PROGRAM_FIXTURE.read_text(encoding="utf-8")


def make_program(source_json: str | None = None) -> Program:
    source = fixture_source() if source_json is None else source_json
    return parse_program_json(source, max_bytes=1_000_000)


def make_compile_context(
    source_json: str | None = None,
    *,
    seed_decimal: str = "17",
    session_id: str = "session",
    trial_id: str = "trial",
) -> CompileContext:
    source = fixture_source() if source_json is None else source_json
    display = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    return CompileContext(
        identity=Identity(
            session_id=session_id,
            trial_id=trial_id,
            configuration_revision=1,
            prepared_generation="prepared",
            renderer_generation="renderer",
            resource_generation="resources",
        ),
        display=display,
        arena_boundaries=TrialArenaBoundaries(format_version=1, bindings=()),
        manifest=ResourceManifest(format_version=1, resources=(), provenance=()),
        seed_decimal=seed_decimal,
        source_json=source,
    )


def make_prepared_trial(
    source_json: str | None = None,
    *,
    seed_decimal: str = "17",
    session_id: str = "session",
    trial_id: str = "trial",
) -> PreparedTrial:
    source = fixture_source() if source_json is None else source_json
    program = make_program(source)
    context = make_compile_context(
        source,
        seed_decimal=seed_decimal,
        session_id=session_id,
        trial_id=trial_id,
    )
    return compile_trial(
        program,
        context,
        max_expanded_epochs=8,
        max_prepared_plan_bytes=1_000_000,
    )


class Clock:
    value = 1_000_000_000

    def __call__(self):
        return self.value


class Graphics:
    def service_display(self):
        return False

    def __init__(self, clock, artifact):
        self.clock, self.artifact = clock, artifact
        self.begun = False
        self.groups = 0
        self.fail_idle = False
        self.diagnostic_queue = []
        self.display_active = False
        self.released_resources = []
        self.retired_resource_catalogues = 0

    @property
    def diagnostics_pending(self):
        return bool(self.diagnostic_queue)

    def poll_diagnostics(self):
        records = tuple(self.diagnostic_queue)
        self.diagnostic_queue.clear()
        return records

    def activity(self):
        return (OutputActivity("projector/main", self.clock(), self.clock() + 1, 1),)

    def initialize_display(self, display):
        self.display_active = True
        return DisplayInitialization(
            ("projector/main",),
            (("projector/main", 8, 8, 8),),
            (("projector/main", 100, 100),),
            (("projector/main", 1),),
            self.activity(),
        )

    def prepare_trial(self, artifact):
        self.artifact = artifact

    def set_feedback_applier(self, applier):
        self.feedback_applier = applier

    def begin_trial(self, trial_id, start_ns):
        self.begun = True
        self.start = start_ns
        self.groups = 0

    def render_tick(self, now_ns, feedback_batch=()):
        assert self.begun
        self.groups += 1
        self.diagnostic_queue.extend(
            DiagnosticSnapshot(self.groups - 1, output.output_id, 0, now_ns, ())
            for output in self.artifact.display.outputs
        )
        return RenderUpdate(
            RenderGroup(
                self.groups - 1,
                self.artifact.identity.trial_id,
                now_ns - self.start,
                0,
                self.artifact.epochs[0].scene_id,
                (),
                self.activity(),
            ),
            (),
            State(
                epoch_occurrence=0,
                scene_id=self.artifact.epochs[0].scene_id,
                evaluation_host_ns=now_ns,
                active_instance_ids=(),
                uniforms=(),
                media=(),
                effective_poses=(),
            ),
            (),
        )

    def stop_trial(self, cutoff_ns=None):
        self.begun = False
        return () if self.fail_idle else self.activity()

    def cleanup(self, deadline_ns=None):
        if self.display_active:
            self.released_resources.append("display:projector/main")
            self.display_active = False
        return ResourceReleaseReport(tuple(self.released_resources))

    def retire_released_resources(self):
        """Forget release proofs after the worker catalogue retires them."""
        self.released_resources.clear()
        self.retired_resource_catalogues += 1


class Preparation:
    def prepare_display(self, request, announce, deadline_ns):
        from cephvr.visual_stimulus.resources.calibration import PreparedCalibration

        return parse_display_json(
            request.display.profile_json, max_bytes=request.limits.max_document_bytes
        ), PreparedCalibration((), (), {})

    def initialize_display(self, display, calibration):
        from cephvr.shared.clock import host_time_ns

        return Graphics(host_time_ns, self.artifact).initialize_display(display)

    def prepare_graphics(self, artifacts):
        return artifacts

    def __init__(self, artifact):
        self.artifact = artifact
        self.retired_resource_catalogues = 0

    def prepare_trials(
        self, request, announce, deadline_ns, *, announce_batch=None, progress=None
    ):
        return (self.artifact,)

    def cleanup(self, deadline_ns):
        return ResourceReleaseReport(())

    def retire_released_resources(self):
        self.retired_resource_catalogues += 1


class Recorder:
    def __init__(self):
        self.calls = []
        self.results = None
        self.diagnostic_records = []
        self.retired_resource_catalogues = 0

    def diagnostics(self, records):
        self.diagnostic_records.extend(records)

    def cleanup(self, deadline_ns):
        return ResourceReleaseReport(())

    def retire_released_resources(self):
        self.retired_resource_catalogues += 1

    def configure(self, request, announce, deadline_ns):
        self.calls.append("configure")

    def prepare_artifacts(self, artifacts, deadline_ns):
        pass

    def schedule(self, request, artifact):
        self.calls.append("schedule")

    def publication(self, report):
        self.calls.append("publication")

    def before_render(self):
        self.calls.append("before_render")

    def rendered(self, update):
        self.calls.append("rendered")

    def begin_finish(self, cutoff_ns, deadline_ns):
        self.calls.append("finish")
        self.deadline = deadline_ns

    def begin_cancel(self, deadline_ns):
        self.calls.append("cancel")
        self.deadline = deadline_ns

    def review_summary(self):
        return None

    def poll_finished(self):
        return self.results


class Reports:
    def __init__(self):
        self.records = []

    def send(self, method, message, deadline_ns, *, required=True):
        self.records.append(
            (method, type(message).FromString(message.SerializeToString()), deadline_ns)
        )

    confirm = send

    def lifecycle(self, kind):
        return [
            (getattr(message.report, kind), deadline)
            for method, message, deadline in self.records
            if method == "ReportWorkerLifecycle"
            and message.report.WhichOneof("report") == kind
        ]
