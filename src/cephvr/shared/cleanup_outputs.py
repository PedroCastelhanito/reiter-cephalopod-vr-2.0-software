"""Shared cleanup-only output closure predicate (E06/E08)."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as control


def cleanup_output_discharged(result: control.OutputResult) -> bool:
    """Accept closure evidence for cleanup, including proven never-started plans.

    NOT_STARTED is valid only with explicit artifact absence and no reported failure.
    The caller must already have matched the output key to its registered plan and
    proved that the cleanup command fenced every possible writer.
    """
    if result.closure in (
        control.OUTPUT_CLOSURE_CLOSED,
        control.OUTPUT_CLOSURE_FAILED,
    ):
        return True
    return (
        result.closure == control.OUTPUT_CLOSURE_NOT_STARTED
        and result.HasField("artifact_present")
        and not result.artifact_present
        and not result.failure.code
        and not result.failure.message
    )
