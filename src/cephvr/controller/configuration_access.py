"""Focused access to acquisition entries; validation remains with each owner."""

from cephvr.control.v1 import types_pb2 as pb


def acquisition_backends(
    configuration: pb.ExperimentConfiguration,
) -> list[pb.BackendSettings]:
    """Preserve order, duplicate entries and dormant/malformed settings for validation."""
    return [
        item for item in configuration.backends if item.backend_name == "acquisition"
    ]
