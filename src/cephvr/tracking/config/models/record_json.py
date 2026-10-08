"""Decoded file objects backed by immutable JSON text in admitted records."""

from __future__ import annotations

import json
import math
from typing import Annotated

from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
from google.protobuf.message import Message
from pydantic import (
    AfterValidator,
    BeforeValidator,
    PlainSerializer,
    ValidationInfo,
    WithJsonSchema,
)

from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult


def _object_text(value: object, info: ValidationInfo) -> str:
    if isinstance(value, str) and info.mode == "python":
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("decoded JSON object required")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


JsonObject = Annotated[
    str,
    BeforeValidator(_object_text),
    PlainSerializer(json.loads, return_type=dict[str, object]),
    WithJsonSchema({"type": "object"}),
]


def _check_values(message: Message) -> None:
    for field, value in message.ListFields():
        values = value if field.is_repeated else (value,)
        for item in values:
            if field.message_type is not None:
                _check_values(item)
            elif field.enum_type is not None:
                if item not in field.enum_type.values_by_number:
                    raise ValueError("unknown feedback enum value")
            elif isinstance(item, float) and not math.isfinite(item):
                raise ValueError("nonfinite feedback value")


def feedback_object(message: FeedbackResult) -> dict[str, object]:
    """Use the owning descriptor's JSON mapping without losing wire fields."""
    clean = FeedbackResult()
    clean.CopyFrom(message)
    clean.DiscardUnknownFields()
    if clean.SerializeToString(deterministic=True) != message.SerializeToString(
        deterministic=True
    ):
        raise ValueError("unknown feedback wire fields")
    _check_values(message)
    return MessageToDict(message)


def feedback_json(message: FeedbackResult) -> str:
    """Freeze a descriptor-owned object before recording admission."""
    return json.dumps(feedback_object(message), separators=(",", ":"), allow_nan=False)


def _feedback_text(source: str) -> str:
    value = json.loads(source)
    try:
        message = ParseDict(value, FeedbackResult(), ignore_unknown_fields=False)
    except ParseError as exc:
        raise ValueError("invalid decoded FeedbackResult") from exc
    canonical = feedback_object(message)
    # Compare text to distinguish numeric types and reject permissive ProtoJSON
    # aliases, null/default spellings and numeric 64-bit fields before normalization.
    if json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) != json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False):
        raise ValueError("canonical Protobuf JSON required")
    return source


FeedbackJSON = Annotated[JsonObject, AfterValidator(_feedback_text)]
