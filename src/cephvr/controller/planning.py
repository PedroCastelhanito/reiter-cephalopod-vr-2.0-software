"""E04 output reservations from resolved Ready settings and writer schemas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cephvr.control.v1 import types_pb2 as pb


class PlanningError(ValueError):
    """A prepared session lacks an exact output or writer-schema binding."""


@dataclass(frozen=True)
class WriterSchema:
    """Supplied by the owning writer from the definition used to encode its file."""

    schema_version: int
    format: str
    fields: Mapping[str, str]
    units: Mapping[str, str]
    clocks: Mapping[str, str]


WriterSchemaKey = tuple[str, str, str]  # backend, output_tag, extension


def _save_flag(message: object, field: str) -> bool:
    if not message.HasField(field):  # type: ignore[attr-defined]
        raise PlanningError(f"resolved {field} is missing")
    return bool(getattr(message, field))


def _tags(
    backend_name: str, settings: pb.BackendSettings
) -> tuple[tuple[str, str], ...]:
    if backend_name == "visual_stimulus":
        if settings.WhichOneof("settings") != "visual_stimulus":
            raise PlanningError(
                "Visual Stimulus Ready lacks resolved Visual Stimulus settings"
            )
        tags = [("stimulus_LOG", "json")]
        if _save_flag(settings.visual_stimulus, "save_visual_stimulus_data"):
            tags.extend((("stimulus_frames", "jsonl"), ("stimulus", "mp4")))
        return tuple(tags)
    if backend_name == "acquisition":
        if settings.WhichOneof("settings") != "acquisition":
            raise PlanningError("acquisition Ready lacks resolved camera settings")
        tags = []
        for camera_role in ("behavioral", "tracking"):
            camera = getattr(settings.acquisition, camera_role)
            if _save_flag(camera, "enabled") and _save_flag(camera, "save_video"):
                tag = f"{camera_role}_cam"
                tags.extend(((tag, "mp4"), (f"{tag}_frames", "jsonl")))
        return tuple(tags)
    if backend_name == "tracking":
        if settings.WhichOneof("settings") != "tracking":
            raise PlanningError("tracking Ready lacks resolved tracking settings")
        return (
            (("tracking", "jsonl"),)
            if _save_flag(settings.tracking, "save_tracking_data")
            else ()
        )
    if backend_name == "synchronization":
        return ()  # Native SpikeGLX files belong to its separate computer.
    raise PlanningError(f"unsupported backend output owner: {backend_name}")


def plan_outputs(
    prepared: pb.PreparedSession, ready: Mapping[str, pb.ReadyReport]
) -> list[pb.OutputPlan]:
    """Reserve deterministic E04 file identities; T later supplies actual filenames."""
    if not prepared.HasField("context") or not prepared.context.session_id:
        raise PlanningError("prepared session identity is missing")
    configured = {
        item.backend_name: item
        for item in prepared.configuration.backends
        if item.enabled and item.backend_name != "synchronization"
    }
    if "visual_stimulus" not in configured or set(ready) != set(configured):
        raise PlanningError("exact enabled backend Ready set is required")
    if len(configured) != sum(
        item.enabled and item.backend_name != "synchronization"
        for item in prepared.configuration.backends
    ):
        raise PlanningError("duplicate enabled backend settings")
    tags_by_backend: dict[str, tuple[tuple[str, str], ...]] = {}
    for name, report in ready.items():
        if (
            report.context.backend.backend_name != name
            or not report.context.backend.backend_generation
            or report.context.work.WhichOneof("work") != "session"
            or report.context.work.session != prepared.context
            or report.configuration_revision != prepared.configuration_revision
            or not report.required_checks_passed
        ):
            raise PlanningError(f"{name} Ready is not bound to this prepared session")
        settings = report.resolved_settings
        if settings.backend_name != name or not settings.enabled:
            raise PlanningError(f"{name} resolved settings are missing or disabled")
        tags_by_backend[name] = _tags(name, settings)
    outputs: list[pb.OutputPlan] = []
    seen: set[str] = set()
    for trial_number, trial in enumerate(prepared.trials, 1):
        if (
            trial.context.session != prepared.context
            or trial.context.trial_number != trial_number
            or not trial.context.trial_id
            or not trial.HasField("resolved_duration_ns")
            or trial.resolved_duration_ns < 60_000_000_000
        ):
            raise PlanningError("trial identity or resolved duration is invalid")
        for name in sorted(configured):
            for tag, extension in tags_by_backend[name]:
                key = f"{trial.context.trial_id}:{name}:{tag}"
                if key in seen:
                    raise PlanningError("duplicate reserved output key")
                seen.add(key)
                outputs.append(
                    pb.OutputPlan(
                        backend=ready[name].context.backend,
                        output_key=key,
                        trial=trial.context,
                        output_tag=tag,
                        extension=extension,
                    )
                )
    if not outputs:
        raise PlanningError("no required output was planned")
    return outputs


def build_schema(
    prepared: pb.PreparedSession,
    writer_schemas: Mapping[WriterSchemaKey, WriterSchema] | None = None,
) -> dict[str, object]:
    """Emit SCHEMA only from exact installed writer definitions for every output.

    Current contract declarations alone do not prove a runtime writer uses them.
    Until writer modules supply definitions, Start fails explicitly.
    """
    schemas = writer_schemas or {}
    if not prepared.outputs:
        raise PlanningError("prepared output reservation is empty")
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for output in prepared.outputs:
        if not output.output_key or output.output_key in seen:
            raise PlanningError("output reservation key is missing or repeated")
        seen.add(output.output_key)
        if output.trial.session != prepared.context or output.HasField("path"):
            raise PlanningError("output path is premature or session identity differs")
        key = (output.backend.backend_name, output.output_tag, output.extension)
        definition = schemas.get(key)
        if definition is None:
            raise PlanningError(f"writer schema unavailable for {key}")
        if (
            definition.schema_version <= 0
            or not definition.format
            or not definition.fields
            or not definition.clocks
        ):
            raise PlanningError(f"writer schema for {key} is incomplete")
        entries.append(
            {
                "output_key": output.output_key,
                "backend": key[0],
                "output_tag": key[1],
                "extension": key[2],
                "schema_version": definition.schema_version,
                "format": definition.format,
                "fields": dict(definition.fields),
                "units": dict(definition.units),
                "clocks": dict(definition.clocks),
            }
        )
    return {"schema_version": 1, "outputs": entries}
