"""Lightweight declaration of Tracking-owned scientific output for the controller."""

from cephvr.controller.planning import WriterSchema, WriterSchemaKey
from cephvr.tracking.config.models.records import TrackingRecord

__all__ = ["TrackingRecord", "get_writer_schemas"]


def get_writer_schemas() -> dict[WriterSchemaKey, WriterSchema]:
    return {
        ("tracking", "tracking", "jsonl"): WriterSchema(
            schema_version=1,
            format="jsonl",
            fields={
                "line": "TrackingRecord(record: Header|PoseObservation|MovementResult|Reset|Discard|Completion)",
                "source": "acquisition frame identity and host receipt; no image or dense-flow payload",
                "feedback_result": "exact serialized FeedbackResult with source/reset/pose lineage",
            },
            units={
                "host_time": "host monotonic ns",
                "forward_drive": "px/s",
                "sideways_drive": "px/s",
                "turn_drive": "1/s",
            },
            clocks={
                "host": "cephvr.host.perf_counter_ns.v1",
                "source": "acquisition host receipt",
            },
        )
    }
