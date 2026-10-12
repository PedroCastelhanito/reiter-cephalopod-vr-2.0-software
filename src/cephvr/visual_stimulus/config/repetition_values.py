"""Versioned random-access sampling, independent of evaluation/visit order."""

import json
from hashlib import sha256
from random import Random

from pydantic import TypeAdapter

from .models.program_model import Settings
from .models.repetition import RepetitionRule
from .parameter_edits import patch_setting
from .random_grid import random_values

_SETTINGS = TypeAdapter(tuple[Settings, ...])


def sample_at(rule: RepetitionRule, repetition: int) -> str:
    index = repetition * rule.stride + rule.offset
    key = f"cephvr.uniform-grid.v1:{rule.seed}:{rule.stream}:{index}"
    rng = Random(int.from_bytes(sha256(key.encode()).digest(), "big"))
    return random_values(
        rule.minimum, rule.maximum, rule.precision, "1", rng.randrange
    )[0]


def resolve_repetition(
    settings: tuple[Settings, ...], rules: tuple[RepetitionRule, ...], repetition: int
) -> tuple[Settings, ...]:
    if not rules:
        return settings
    patches: dict[str, dict[str, str]] = {}
    for rule in rules:
        patches.setdefault(rule.instance_id, {})[rule.parameter] = sample_at(
            rule, repetition
        )
    data = [setting.model_dump(mode="json") for setting in settings]
    for setting in data:
        if setting["instance_id"] in patches:
            patch_setting(setting, patches.pop(setting["instance_id"]))
    if patches:
        raise ValueError("Random rule references an inactive instance")
    return _SETTINGS.validate_json(json.dumps(data, allow_nan=False))
