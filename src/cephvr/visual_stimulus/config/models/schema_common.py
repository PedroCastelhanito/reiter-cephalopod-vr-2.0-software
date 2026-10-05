"""Shared lightweight schema primitives and one strict bounded JSON boundary.

No GUI, file, SDK or renderer imports. Setup and offline readers supply their own
byte budgets. JSON input is preserved for Pydantic's strict JSON/tuple semantics.
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal, NoReturn, TypeVar

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

DEFAULT_DOCUMENT_BYTES = 16_777_216


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        validate_default=True,
        frozen=True,
    )


Name = Annotated[str, Field(min_length=1, max_length=128)]
OutputId = Name  # Opaque stable ID; never interpreted as a file path or normalized.
FrameId = Name
DeviceIdentity = Name  # Native device IDs may contain punctuation/backslashes.
ProgramId = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$", max_length=128)]
NonEmpty = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
NonnegativeInt = Annotated[int, Field(ge=0)]
U32 = Annotated[int, Field(ge=0, le=(1 << 32) - 1)]
U64 = Annotated[int, Field(ge=0, le=(1 << 64) - 1)]
NS = Annotated[int, Field(ge=0, le=(1 << 63) - 1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
UnitValue = Annotated[float, Field(ge=0, le=1)]
Vec3 = tuple[float, float, float]
SurfaceId = Literal["front", "left", "right", "bottom"]
# E05 fixed policy protocol.minimum_trial_duration_s (contracts/policy/experiment_policy.toml).
MINIMUM_TRIAL_DURATION_NS = 60_000_000_000


def unit_quaternion(
    value: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if abs(math.hypot(*value) - 1.0) > 1e-9:
        raise ValueError(
            "orientation quaternion must have unit length (tolerance 1e-9)"
        )
    return value


UnitQuaternion = Annotated[
    tuple[float, float, float, float], AfterValidator(unit_quaternion)
]


def exact_integer(value: object) -> object:
    if type(value) is not int:
        raise ValueError(
            "integer required; Boolean, float and string are not integer literals"
        )
    return value


Version1 = Annotated[Literal[1], BeforeValidator(exact_integer)]
Version2 = Annotated[Literal[2], BeforeValidator(exact_integer)]
RGBBits = Annotated[Literal[8, 10], BeforeValidator(exact_integer)]
SwapInterval = Annotated[Literal[0, 1], BeforeValidator(exact_integer)]
OrientationDegrees = Annotated[Literal[0, 90, 180, 270], BeforeValidator(exact_integer)]
NanosecondDenominator = Annotated[Literal[1000000000], BeforeValidator(exact_integer)]


def portable_path(value: str) -> str:
    if (
        ":" in value
        or "\\" in value
        or "\x00" in value
        or any(p in ("", ".", "..") for p in value.split("/"))
    ):
        raise ValueError("path must be portable, relative and traversal-free")
    return value


T = TypeVar("T", bound=BaseModel)


def parse_json(
    model: type[T], source: str, *, max_bytes: int, max_depth: int = 64
) -> T:
    if (
        type(max_bytes) is not int
        or type(max_depth) is not int
        or min(max_bytes, max_depth) <= 0
    ):
        raise ValueError("positive integer JSON limits required")
    if not isinstance(source, str):
        raise ValueError("UTF-8 JSON text required")
    if len(source.encode("utf8")) > max_bytes:
        raise ValueError("document exceeds byte budget")
    depth = 0
    quoted = False
    escaped = False
    for ch in source:
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "[{":
            depth += 1
            if depth > max_depth:
                raise ValueError("document exceeds nesting budget")
        elif ch in "]}":
            depth -= 1

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value: str) -> NoReturn:
        raise ValueError(f"nonfinite JSON constant: {value}")

    # This preflight checks duplicate keys; it is not a second schema definition.
    json.loads(source, object_pairs_hook=unique, parse_constant=invalid)
    return model.model_validate_json(source, strict=True)
