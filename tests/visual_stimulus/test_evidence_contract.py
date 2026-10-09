from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError
from tests.visual_stimulus.evidence_reader import EvidenceValidationError, read_evidence
from tests.visual_stimulus.evidence_state import _validate_recipe_states

from cephvr.visual_stimulus.config.models.evidence_model import (
    ArtifactRef,
    Clipping,
    EvidenceRecord,
    Header,
    Identity,
    RenderGroup,
    State,
    Submission,
    UniformValue,
)


def _header() -> Header:
    return Header(
        kind="header",
        format_version=3,
        identity=Identity(
            session_id="session",
            trial_id="trial",
            configuration_revision=1,
            prepared_generation="prepared",
            renderer_generation="renderer",
            resource_generation="resources",
        ),
        writer_generation="writer",
        recipe=ArtifactRef(
            relative_path="trial_stimulus_LOG.json",
            sha256=hashlib.sha256(b"recipe").hexdigest(),
            byte_length=6,
            schema_id="prepared-v2",
        ),
        trial_start_host_ns=10,
        required_output_ids=("front",),
        renderer_compatibility="renderer-v1",
    )


def _group(group_id: int = 0) -> RenderGroup:
    return RenderGroup(
        kind="render_group",
        group_id=group_id,
        state=State(
            epoch_occurrence=0,
            scene_id="scene",
            evaluation_host_ns=10 + group_id,
            active_instance_ids=(),
            uniforms=(),
            media=(),
            effective_poses=(),
        ),
        submissions=(
            Submission(
                output_id="front",
                attempt_index=0,
                phase="returned",
                entry_host_ns=11 + group_id,
                return_host_ns=12 + group_id,
                swap_interval=1,
                marker_index=0,
                marker_high=True,
                failure_code=None,
            ),
        ),
        captures=(),
    )


def _line(payload: object) -> bytes:
    return EvidenceRecord(payload=payload).model_dump_json().encode() + b"\n"


def test_reader_discards_incomplete_tail_and_marks_partial(tmp_path: Path) -> None:
    path = tmp_path / "frames.jsonl"
    path.write_bytes(_line(_header()) + _line(_group()) + b'{"payload":')
    parsed = read_evidence(path, max_line_bytes=4096)
    assert parsed.completion is None
    assert parsed.discarded_partial_tail
    assert parsed.last_group_id == 0


def test_reader_rejects_group_gaps(tmp_path: Path) -> None:
    path = tmp_path / "frames.jsonl"
    path.write_bytes(_line(_header()) + _line(_group(1)))
    with pytest.raises(EvidenceValidationError, match="begin at zero"):
        read_evidence(path, max_line_bytes=4096)


def test_reader_rejects_missing_header(tmp_path: Path) -> None:
    path = tmp_path / "frames.jsonl"
    path.write_bytes(_line(_group()))
    with pytest.raises(EvidenceValidationError, match="begin with exactly one Header"):
        read_evidence(path, max_line_bytes=4096)


def _clipping(
    *,
    group_id: int = 0,
    output_id: str = "front",
    occurrence_index: int = 0,
    observation_host_ns: int = 10,
    stages: tuple[str, ...] = (),
) -> Clipping:
    return Clipping(
        kind="clipping",
        group_id=group_id,
        output_id=output_id,
        occurrence_index=occurrence_index,
        observation_host_ns=observation_host_ns,
        stages=stages,
    )


def test_reader_accepts_empty_stage_clipping_as_covered_output(tmp_path: Path) -> None:
    path = tmp_path / "frames.jsonl"
    path.write_bytes(_line(_header()) + _line(_group()) + _line(_clipping()))
    parsed = read_evidence(path, max_line_bytes=4096)
    assert parsed.clippings[(0, "front")].stages == ()


@pytest.mark.parametrize(
    "diagnostic, message",
    [
        (_clipping(group_id=1), "group not yet written"),
        (_clipping(output_id="side"), "output absent"),
        (_clipping(occurrence_index=1), "epoch or timestamp differs"),
        (_clipping(observation_host_ns=11), "epoch or timestamp differs"),
    ],
)
def test_reader_rejects_clipping_with_invalid_reference(
    tmp_path: Path, diagnostic: Clipping, message: str
) -> None:
    path = tmp_path / "frames.jsonl"
    path.write_bytes(_line(_header()) + _line(_group()) + _line(diagnostic))
    with pytest.raises(EvidenceValidationError, match=message):
        read_evidence(path, max_line_bytes=4096)


def test_reader_rejects_duplicate_clipping_for_group_output(tmp_path: Path) -> None:
    path = tmp_path / "frames.jsonl"
    path.write_bytes(
        _line(_header()) + _line(_group()) + _line(_clipping()) + _line(_clipping())
    )
    with pytest.raises(EvidenceValidationError, match="duplicate Clipping"):
        read_evidence(path, max_line_bytes=4096)


def _validation_fixture(
    *, kind: str = "image", active_ids=("layer",), uniform_omission=None
):
    names = (
        ("opacity", ()),
        ("contrast", ()),
        ("mean_rgb", (3,)),
        ("modulation_rgb", (3,)),
        ("frequency", (2,)),
        ("phase", (2,)),
        ("period", (2,)),
        ("clip_vertices_screen-map", (4, 2)),
    )
    layouts = tuple(
        NS(
            binding_id=f"layer-{name}",
            instance_id="layer",
            output_id="front" if name.startswith("clip_vertices_") else None,
            name=name,
            scalar_type="float32",
            shape=shape,
        )
        for name, shape in names
    )
    space = NS(kind="visual_angle", surfaces=("screen",))
    setting = NS(
        instance_id="layer",
        kind=kind,
        asset_id="clip" if kind == "video" else "image",
        space=space,
    )
    epoch = NS(occurrence_index=0, scene_id="scene", settings=(setting,))
    scene = NS(scene_id="scene", layer_instance_ids=("layer",), arena_instance_id=None)
    mapping = NS(mapping_id="screen-map", output_id="front", surface_id="screen")
    state = _group().state.model_copy(update={"active_instance_ids": active_ids})
    values = tuple(
        UniformValue(
            binding_id=layout.binding_id,
            words=(0,)
            * (1 if not layout.shape else __import__("math").prod(layout.shape)),
        )
        for layout in layouts
        if layout.binding_id != uniform_omission
    )
    state = state.model_copy(update={"uniforms": values})
    group = _group().model_copy(update={"state": state})
    resource = NS(
        fingerprint=NS(resource_id=setting.asset_id),
        kind="video" if kind == "video" else "image",
    )
    recipe = NS(
        epochs=(epoch,),
        uniform_layouts=layouts,
        source=NS(scenes=(scene,)),
        manifest=NS(resources=(resource,)),
        display=NS(mappings=(mapping,)),
    )
    evidence = NS(header=NS(required_output_ids=("front",)), groups=(group,))
    return recipe, evidence


def test_evidence_rejects_missing_active_instance_state() -> None:
    recipe, evidence = _validation_fixture(active_ids=())
    with pytest.raises(EvidenceValidationError, match="active instances do not match"):
        _validate_recipe_states(recipe, evidence)


def test_evidence_rejects_missing_required_shader_uniform() -> None:
    recipe, evidence = _validation_fixture(uniform_omission="layer-phase")
    with pytest.raises(EvidenceValidationError, match="uniform coverage"):
        _validate_recipe_states(recipe, evidence)


def test_evidence_requires_media_selection_for_every_active_video_instance() -> None:
    recipe, evidence = _validation_fixture(kind="video")
    with pytest.raises(EvidenceValidationError, match="media selections do not match"):
        _validate_recipe_states(recipe, evidence)


def test_published_recipe_retains_analysis_inputs_without_source_file(
    tmp_path: Path,
) -> None:
    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.config.models.artifact_models import (
        ComponentProvenance,
        Fingerprint,
        PreparedTrial,
        Resource,
        ResourceManifest,
    )
    from cephvr.visual_stimulus.recording.recipe import prepare_recipe, publish_recipe
    from cephvr.visual_stimulus.resources.uniforms import build_uniform_layouts

    artifact = make_prepared_trial()
    geometry = Resource(
        fingerprint=Fingerprint(
            resource_id="geometry-front",
            logical_path="geometry/front.json",
            subresource=None,
            sha256=hashlib.sha256(b"external calibration bytes").hexdigest(),
            bytes=26,
        ),
        kind="geometry",
        profile_id="geometry-v1",
        dependencies=(),
        interpretation=None,
        cpu_bytes=26,
        gpu_bytes=32,
        provider_compatibility="geometry-v1",
    )
    artifact = artifact.model_copy(
        update={
            "uniform_layouts": build_uniform_layouts(artifact.source, artifact.display),
            "manifest": ResourceManifest(
                format_version=1,
                resources=(geometry,),
                provenance=(
                    ComponentProvenance(
                        role="renderer",
                        implementation="test-renderer",
                        version="1",
                        content_sha256=None,
                    ),
                ),
            ),
        }
    )
    recipe = prepare_recipe(artifact, max_bytes=1_000_000)
    path = tmp_path / "trial_stimulus_LOG.json"
    reference = publish_recipe(
        path,
        path.name,
        recipe,
        expected_sha256=recipe.sha256,
        expected_byte_length=recipe.byte_length,
        trial_start_host_ns=10,
        now_host_ns=10,
    )
    # The only file available to this consumer is the published trial recipe.
    restored = PreparedTrial.model_validate_json(path.read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == reference.sha256
    assert restored == artifact
    assert restored.source.sequence and restored.epochs and restored.boundaries
    assert restored.seed_decimal == "17"
    assert restored.display.mappings and restored.uniform_layouts
    assert restored.manifest.resources[0].fingerprint == geometry.fingerprint
    assert restored.manifest.provenance[0].implementation == "test-renderer"
    assert restored.renderer_compatibility == artifact.renderer_compatibility


def test_evidence_writer_preserves_exact_inputs_when_review_frame_drops(
    tmp_path: Path,
) -> None:
    from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
    from cephvr.visual_stimulus.recording.evidence_records import (
        build_render_group_record,
    )
    from cephvr.visual_stimulus.rendering.types import (
        EvidenceStateSnapshot,
        MediaSnapshot,
        PoseSnapshot,
        SubmissionSnapshot,
        UniformSnapshot,
    )

    # Values differ from a fresh evaluation: a held video frame, a feedback pose
    # and an exact float32 bit pattern must survive independently of review pixels.
    state = EvidenceStateSnapshot(
        epoch_occurrence=0,
        scene_id="scene",
        evaluation_host_ns=10,
        active_instance_ids=("video", "arena"),
        uniforms=(UniformSnapshot("video-phase", (0x3DCCCCCD, 0x80000000)),),
        media=(
            MediaSnapshot(
                instance_id="video",
                asset_id="clip",
                stream_index=0,
                source_frame_index=7,
                source_pts=233,
                time_base_numerator=1,
                time_base_denominator=1000,
                playback_generation=2,
                loop_index=1,
                target_media_numerator=280,
                target_media_denominator=1000,
                disposition="starvation_hold",
            ),
        ),
        effective_poses=(
            PoseSnapshot("arena", "world", (1.25, -2.5, 3.0), (0.0, 0.0, 0.0, 1.0)),
        ),
    )
    submission = SubmissionSnapshot("front", 0, "returned", 11, 12, 1, 0, True, None)
    group = build_render_group_record(
        0,
        state,
        (submission,),
        (("capacity_drop", None, None),),
        "rgba8_bottom_up",
        "yuv420p",
    )
    path = tmp_path / "trial_stimulus_frames.jsonl"
    header = _header()
    writer = EvidenceWriter(max_pending_bytes=8192)
    writer.open_after_recipe(path, header, header.recipe)
    writer.enqueue(group)
    writer.enqueue(_clipping())
    writer.close()
    parsed = read_evidence(path, max_line_bytes=8192)
    saved = parsed.groups[0]
    assert saved == group
    assert saved.state.uniforms[0].words == (0x3DCCCCCD, 0x80000000)
    assert saved.state.media[0].source_frame_index == 7
    assert saved.state.media[0].target_media_numerator == 280
    assert saved.state.media[0].disposition == "starvation_hold"
    assert saved.state.effective_poses[0].position_mm == (1.25, -2.5, 3.0)
    assert saved.submissions[0].phase == "returned"
    assert saved.captures[0].disposition == "capacity_drop"
    assert parsed.completion is None  # Closing a file cannot imply trial completion.


def test_cadence_header_rejects_legacy_evidence_version_and_keeps_recipe_v2() -> None:
    from cephvr.visual_stimulus.recording_schema import get_writer_schemas

    header = _header().model_dump()
    assert header["format_version"] == 3
    header["format_version"] = 2
    with pytest.raises(ValidationError):
        Header.model_validate(header)
    schemas = get_writer_schemas()
    assert schemas["visual_stimulus", "stimulus_frames", "jsonl"].schema_version == 3
    assert schemas["visual_stimulus", "stimulus_LOG", "json"].schema_version == 2
