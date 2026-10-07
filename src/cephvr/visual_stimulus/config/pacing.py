"""File-owned pacing overlays for bounded display profiles."""

from __future__ import annotations

import json
import math
from typing import Any

from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    parse_display_json,
)


def apply_pacing_settings(
    display: DisplayProfile,
    *,
    refresh_hz: float | None,
    output_id: str | None,
) -> DisplayProfile:
    """Overlay file-owned V20 pacing selection and validate its native target."""
    values = display.model_dump()
    if output_id is not None:
        values["pacing_output_id"] = output_id
    resolved = DisplayProfile.model_validate(values)
    selected_id = resolved.selected_pacing_output_id
    if selected_id is None:
        raise ValueError("mixed pacing requires a configured pacing output")
    selected = next(
        (
            output
            for output in resolved.active_outputs
            if output.output_id == selected_id
        ),
        None,
    )
    if selected is None:
        raise ValueError("configured pacing output is unavailable or disabled")
    if refresh_hz is not None:
        if not math.isfinite(refresh_hz) or not refresh_hz.is_integer():
            raise ValueError(
                "V20 pacing refresh must match an integer native display mode"
            )
        native_rate = (
            2 * selected.refresh_numerator + selected.refresh_denominator
        ) // (2 * selected.refresh_denominator)
        if native_rate != int(refresh_hz):
            raise ValueError(
                f"pacing output {selected_id} profile refresh {native_rate:g} Hz "
                f"does not match configured target {refresh_hz:g} Hz"
            )
    return resolved


def resolve_pacing_profile(
    profile_json: str,
    *,
    max_bytes: int,
    refresh_hz: float | None,
    output_id: str | None,
) -> DisplayProfile:
    """Apply the file-owned ID before canonical validation of a bounded profile."""
    if len(profile_json.encode("utf-8")) > max_bytes:
        raise ValueError("document exceeds byte budget")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant: {value}")

    document = json.loads(
        profile_json,
        object_pairs_hook=unique,
        parse_constant=invalid_constant,
    )
    if not isinstance(document, dict):
        raise ValueError("display profile must be a JSON object")
    if output_id is not None:
        document["pacing_output_id"] = output_id
    source = json.dumps(document, allow_nan=False, separators=(",", ":"))
    return apply_pacing_settings(
        parse_display_json(source, max_bytes=max_bytes),
        refresh_hz=refresh_hz,
        output_id=None,
    )
