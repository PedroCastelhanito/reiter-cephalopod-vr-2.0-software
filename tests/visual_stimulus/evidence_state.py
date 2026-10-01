"""Test-only checks that experiment evidence retains required prepared inputs."""

from __future__ import annotations

import math
import struct

from tests.visual_stimulus.evidence_reader import EvidenceFile, EvidenceValidationError

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial


def _validate_recipe_states(recipe: PreparedTrial, evidence: EvidenceFile) -> None:
    resources = {
        item.fingerprint.resource_id: item for item in recipe.manifest.resources
    }
    layouts = {item.binding_id: item for item in recipe.uniform_layouts}
    if len(layouts) != len(recipe.uniform_layouts):
        raise EvidenceValidationError("prepared recipe repeats a uniform binding")
    expected_ids = set(evidence.header.required_output_ids)
    scenes = {item.scene_id: item for item in recipe.source.scenes}
    for group in evidence.groups:
        state = group.state
        if state.epoch_occurrence >= len(recipe.epochs):
            raise EvidenceValidationError(
                "render state references an unknown prepared epoch"
            )
        epoch = recipe.epochs[state.epoch_occurrence]
        if state.scene_id != epoch.scene_id:
            raise EvidenceValidationError(
                "render state scene differs from prepared epoch"
            )
        settings_by_id = {item.instance_id: item for item in epoch.settings}
        active_ids = set(state.active_instance_ids)
        if len(active_ids) != len(state.active_instance_ids):
            raise EvidenceValidationError("render state repeats an active instance")
        if active_ids != set(settings_by_id):
            raise EvidenceValidationError(
                "render state active instances do not match its prepared epoch"
            )
        scene = scenes.get(state.scene_id)
        if scene is None:
            raise EvidenceValidationError("render state references an unknown scene")
        if set(settings_by_id) != set(scene.layer_instance_ids) | (
            {scene.arena_instance_id} if scene.arena_instance_id is not None else set()
        ):
            raise EvidenceValidationError(
                "prepared epoch settings do not cover every scene rendering instance"
            )
        if {submission.output_id for submission in group.submissions} != expected_ids:
            raise EvidenceValidationError(
                "render group must retain one observation per required output"
            )
        binding_ids = [item.binding_id for item in state.uniforms]
        if len(set(binding_ids)) != len(binding_ids) or any(
            item not in layouts for item in binding_ids
        ):
            raise EvidenceValidationError(
                "render state has duplicate or unknown uniform bindings"
            )
        required_bindings: set[str] = set()
        video_asset_ids: dict[str, str] = {}
        for instance_id, setting in settings_by_id.items():
            asset_id: str | None = None
            if setting.kind == "video":
                candidate_asset_id = setting.asset_id
                expected_kind = "video"
            elif setting.kind == "arena":
                candidate_asset_id = setting.asset_id
                expected_kind = "arena"
            elif setting.kind == "image":
                candidate_asset_id = setting.asset_id
                expected_kind = "image"
            elif setting.kind == "texture" and setting.pattern.kind == "image_tile":
                candidate_asset_id = setting.pattern.asset_id
                expected_kind = "image"
            else:
                candidate_asset_id = None
                expected_kind = None
            if candidate_asset_id is not None:
                if not isinstance(candidate_asset_id, str):
                    raise EvidenceValidationError(
                        f"prepared instance {instance_id} retains an unresolved asset reference"
                    )
                asset_id = candidate_asset_id
                if setting.kind == "video":
                    video_asset_ids[instance_id] = asset_id
            if asset_id is not None:
                resource = resources.get(asset_id)
                if resource is None or resource.kind != expected_kind:
                    raise EvidenceValidationError(
                        f"prepared instance {instance_id} references an incompatible resource"
                    )
            instance_layouts = tuple(
                item
                for item in recipe.uniform_layouts
                if item.instance_id == instance_id
            )
            required_bindings.update(
                item.binding_id
                for item in instance_layouts
                if item.output_id is None and not item.name.startswith("clip_vertices_")
            )
            if setting.kind == "arena":
                continue
            if setting.space.kind == "physical_surface":
                surfaces = {item.surface_id for item in setting.space.mappings}
            else:
                surfaces = set(setting.space.surfaces)
            for mapping in recipe.display.mappings:
                if mapping.surface_id not in surfaces:
                    continue
                layout = next(
                    (
                        item
                        for item in instance_layouts
                        if item.output_id == mapping.output_id
                        and item.name == f"clip_vertices_{mapping.mapping_id}"
                    ),
                    None,
                )
                if layout is None:
                    raise EvidenceValidationError(
                        f"prepared uniform layout omits mapping {mapping.mapping_id}"
                    )
                required_bindings.add(layout.binding_id)
        if set(binding_ids) != required_bindings:
            missing = sorted(required_bindings - set(binding_ids))
            extra = sorted(set(binding_ids) - required_bindings)
            raise EvidenceValidationError(
                "render state uniform coverage differs from required shader inputs"
                f" (missing={missing}, extra={extra})"
            )
        for value in state.uniforms:
            layout = layouts[value.binding_id]
            scalar_words = 2 if layout.scalar_type == "float64" else 1
            expected_words = scalar_words
            for dimension in layout.shape:
                expected_words *= dimension
            if len(value.words) != expected_words:
                raise EvidenceValidationError(
                    f"uniform {value.binding_id} has the wrong number of words"
                )
            if layout.scalar_type in ("float32", "float64"):
                if layout.scalar_type == "float32":
                    values = tuple(
                        struct.unpack("<f", struct.pack("<I", word))[0]
                        for word in value.words
                    )
                else:
                    values = tuple(
                        struct.unpack(
                            "<d",
                            struct.pack("<II", *value.words[index : index + 2]),
                        )[0]
                        for index in range(0, len(value.words), 2)
                    )
                if any(not math.isfinite(item) for item in values):
                    raise EvidenceValidationError(
                        f"uniform {value.binding_id} contains nonfinite values"
                    )
        media_by_instance = {item.instance_id: item for item in state.media}
        if len(media_by_instance) != len(state.media):
            raise EvidenceValidationError("render state repeats a media selection")
        if set(media_by_instance) != set(video_asset_ids):
            raise EvidenceValidationError(
                "render state media selections do not match active video instances"
            )
        for instance_id, selection in media_by_instance.items():
            if selection.asset_id != video_asset_ids[instance_id]:
                raise EvidenceValidationError(
                    f"video selection for {instance_id} references the wrong asset"
                )
        if any(pose.instance_id not in active_ids for pose in state.effective_poses):
            raise EvidenceValidationError(
                "render state pose references an inactive instance"
            )
