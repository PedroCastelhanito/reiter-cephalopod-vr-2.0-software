"""Presence-preserving codecs for managed experiment metadata fields."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any

from cephvr.control.v1 import types_pb2 as pb


def subject_metadata_from_fields(dashboard: Any) -> pb.SubjectMetadata:
    """Build typed subject metadata while retaining meaningful numeric zero."""
    metadata = pb.SubjectMetadata()
    for field_name in ("species", "condition"):
        value = getattr(dashboard, field_name).text()
        if value:
            setattr(metadata, field_name, value)
    sex = dashboard.sex.currentText()
    if sex != "Not specified":
        metadata.sex = sex
    for field_name, target, positive in (
        ("age", "age_dph", False),
        ("subject_size", "size_mm", True),
    ):
        value = getattr(dashboard, field_name).text().strip()
        if not value:
            continue
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{target} must be a number") from exc
        if not number.is_finite() or number < 0 or (positive and number == 0):
            qualifier = "positive" if positive else "nonnegative"
            raise ValueError(f"{target} must be finite and {qualifier}")
        converted = float(number)
        if not isfinite(converted):
            raise ValueError(f"{target} is outside the supported numeric range")
        setattr(metadata, target, converted)
    return metadata


def install_subject_metadata(
    dashboard: Any, configuration: pb.ExperimentConfiguration
) -> None:
    """Install authoritative subject fields without guessing absent values."""
    dashboard.subject_id.setText(configuration.subject)
    dashboard.experiment.setText(configuration.experiment)
    dashboard.output_root.setText(configuration.recording_root)
    metadata = configuration.subject_metadata
    dashboard.species.setText(metadata.species if metadata.HasField("species") else "")
    sex = metadata.sex if metadata.HasField("sex") else "Not specified"
    if dashboard.sex.findText(sex) < 0:
        dashboard.sex.addItem(sex)
    dashboard.sex.setCurrentText(sex)
    dashboard.age.setText(str(metadata.age_dph) if metadata.HasField("age_dph") else "")
    dashboard.subject_size.setText(
        str(metadata.size_mm) if metadata.HasField("size_mm") else ""
    )
    dashboard.condition.setText(
        metadata.condition if metadata.HasField("condition") else ""
    )


def install_metadata(
    configuration: pb.ExperimentConfiguration, metadata: pb.SubjectMetadata
) -> None:
    """Replace only the optional typed metadata submessage on a cloned config."""
    configuration.ClearField("subject_metadata")
    if metadata.ListFields():
        configuration.subject_metadata.CopyFrom(metadata)
