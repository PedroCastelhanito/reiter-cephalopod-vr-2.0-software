"""Versioned random-access sampling, independent of evaluation/visit order."""

import json
from hashlib import sha256
from random import Random

from pydantic import TypeAdapter

from .models.program_model import Settings
from .models.repetition import AssetRepetitionRule, Repetition
from .parameter_edits import patch_setting
from .random_grid import random_values

_SETTINGS = TypeAdapter(tuple[Settings, ...])


def sample_at(rule: Repetition, repetition: int) -> str:
    index = repetition * rule.stride + rule.offset
    sampler = (
        "uniform-asset" if isinstance(rule, AssetRepetitionRule) else "uniform-grid"
    )
    key = f"cephvr.{sampler}.v1:{rule.seed}:{rule.stream}:{index}"
    rng = Random(int.from_bytes(sha256(key.encode()).digest(), "big"))
    if isinstance(rule, AssetRepetitionRule):
        return rule.asset_ids[rng.randrange(len(rule.asset_ids))]
    return random_values(
        rule.minimum, rule.maximum, rule.precision, "1", rng.randrange
    )[0]


def resolve_repetition(
    settings: tuple[Settings, ...], rules: tuple[Repetition, ...], repetition: int
) -> tuple[Settings, ...]:
    if not rules:
        return settings
    patches: dict[str, dict[str, str]] = {}
    for rule in rules:
        patches.setdefault(rule.instance_id, {})[rule.parameter] = sample_at(
            rule, repetition
        )
    frames: dict[str, tuple[bool, int]] = {}
    for rule in rules:
        if not isinstance(rule, AssetRepetitionRule) and rule.parameter in (
            "Speed",
            "Direction",
            "Orientation",
        ):
            frame = (
                rule.rig_coordinates,
                rule.rig_angle_version if rule.rig_coordinates else 1,
            )
            previous = frames.setdefault(rule.instance_id, frame)
            if previous != frame:
                raise ValueError(
                    "Speed and direction rules must use the same coordinates"
                )
    data = [setting.model_dump(mode="json") for setting in settings]
    for setting in data:
        if setting["instance_id"] in patches:
            values = patches.pop(setting["instance_id"])
            asset_id = values.pop("Asset", None)
            if asset_id is not None:
                if (
                    setting["kind"] == "texture"
                    and setting["pattern"]["kind"] == "image_tile"
                ):
                    setting["pattern"]["asset_id"] = asset_id
                    if setting.get("grating", False):
                        rule = next(
                            r
                            for r in rules
                            if isinstance(r, AssetRepetitionRule)
                            and r.instance_id == setting["instance_id"]
                        )
                        if len(rule.grating_periods_mm) != len(rule.asset_ids):
                            raise ValueError(
                                "Grating Asset choices require their spatial periods"
                            )
                        period = rule.grating_periods_mm[rule.asset_ids.index(asset_id)]
                        for axis in ("x", "y"):
                            setting["pattern"][f"period_{axis}"] = dict(
                                kind="constant", value=period
                            )
                elif setting["kind"] in ("image", "video"):
                    setting["asset_id"] = asset_id
                else:
                    raise ValueError(
                        "Asset variations require an image, video or image-tile texture"
                    )
            patch_setting(
                setting,
                values,
                rig_coordinates=frames.get(setting["instance_id"], (False, 1))[0],
                rig_angle_version=frames.get(setting["instance_id"], (False, 1))[1],
            )
    if patches:
        raise ValueError("Random rule references an inactive instance")
    return _SETTINGS.validate_json(json.dumps(data, allow_nan=False))
