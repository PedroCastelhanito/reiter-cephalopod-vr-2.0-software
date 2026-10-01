"""E07/E14 file-owned controller limits and pure proposal validation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.protobuf.json_format import ParseDict, ParseError
from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration_files import load_control_files
from cephvr.shared.config import ConfigurationError
from cephvr.shared.deadlines import duration_ns

BackendValidator = Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
_BACKENDS = frozenset({"acquisition", "visual_stimulus", "tracking", "synchronization"})


@dataclass(frozen=True)
class SupervisorStartup:
    port: int
    heartbeat_interval_ns: int
    silence_timeout_ns: int
    emergency_timeout_ns: int
    graceful_exit_ns: int
    terminate_exit_ns: int
    application_backstop_ns: int


@dataclass(frozen=True)
class ControllerConfiguration:
    configuration: pb.ExperimentConfiguration
    policies: pb.ControlPolicies
    limits_kwargs: dict[str, int]
    supervisor_startup: SupervisorStartup
    controller_port: int
    max_message_bytes: int
    max_pending_events: int
    max_pending_payload_bytes: int
    max_retained_incidents: int
    default_intertrial_gap_ns: int
    history_warning: str | None


def _section(data: Mapping[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        try:
            value = value[key]
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(
                f"required setting {'.'.join(keys)} is missing"
            ) from exc
    return value


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def _port(value: Any, name: str) -> int:
    port = _positive_int(value, name)
    if port > 65_535:
        raise ConfigurationError(f"{name} is outside the TCP port range")
    return port


def _ns(data: Mapping[str, Any], *keys: str, unit: str = "s") -> int:
    value = _section(data, *keys)
    try:
        converted = duration_ns(value, unit)  # type: ignore[arg-type]
    except ValueError as exc:
        raise ConfigurationError(f"{'.'.join(keys)}: {exc}") from exc
    if converted <= 0:
        raise ConfigurationError(f"{'.'.join(keys)} must be positive")
    return converted


def _unique_json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member {key}")
        result[key] = value
    return result


def _load_saved_configuration(
    path: Path, *, max_message_bytes: int
) -> pb.ExperimentConfiguration:
    """Do not guess an unpublished history envelope or silently discard its values."""
    if not path.exists():
        return pb.ExperimentConfiguration()
    try:
        with path.open("rb") as stream:
            raw = stream.read(max_message_bytes + 1)
    except OSError as exc:
        raise ConfigurationError("cannot read saved configuration") from exc
    if len(raw) > max_message_bytes:
        raise ConfigurationError("saved configuration exceeds control message limit")
    try:
        document = json.loads(raw, object_pairs_hook=_unique_json_members)
    except (UnicodeError, ValueError) as exc:
        raise ConfigurationError(f"saved configuration is invalid JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {
        "format_version",
        "configuration",
    }:
        raise ConfigurationError("saved configuration envelope is unsupported")
    if type(document["format_version"]) is not int or document["format_version"] != 1:
        raise ConfigurationError("saved configuration format version is unsupported")
    if not isinstance(document["configuration"], dict):
        raise ConfigurationError("saved configuration value must be an object")
    try:
        return ParseDict(
            document["configuration"],
            pb.ExperimentConfiguration(),
            ignore_unknown_fields=False,
        )
    except ParseError as exc:
        raise ConfigurationError(
            "saved configuration does not match the wire schema"
        ) from exc


def _load_supervisor_startup(
    sc: Mapping[str, Any],
    supervisor_port: int,
    setup_cancel: int,
    trial_finished: int,
    recovery: int,
) -> SupervisorStartup:
    """Load supervisor startup timing and check the derived shutdown backstop."""
    startup = SupervisorStartup(
        port=supervisor_port,
        heartbeat_interval_ns=_ns(sc, "health", "heartbeat_interval_s"),
        silence_timeout_ns=_ns(sc, "health", "silence_timeout_s"),
        emergency_timeout_ns=_ns(sc, "emergency_report", "completion_timeout_s"),
        graceful_exit_ns=_ns(sc, "shutdown", "graceful_process_exit_s"),
        terminate_exit_ns=_ns(sc, "shutdown", "terminate_process_exit_s"),
        application_backstop_ns=_ns(sc, "shutdown", "application_shutdown_backstop_s"),
    )
    if startup.silence_timeout_ns <= startup.heartbeat_interval_ns:
        raise ConfigurationError("health silence must exceed heartbeat interval")
    minimum_backstop = (
        startup.silence_timeout_ns
        + max(setup_cancel, trial_finished)
        + recovery
        + 3 * (startup.graceful_exit_ns + startup.terminate_exit_ns)
    )
    if startup.application_backstop_ns < minimum_backstop:
        raise ConfigurationError("application shutdown backstop is below derived sum")
    return startup


def _load_reusable_configuration(
    root: Path, ec: Mapping[str, Any], max_message: int
) -> tuple[pb.ExperimentConfiguration, str | None]:
    """Load saved history, fill acquisition/tracking defaults and the asset root."""
    history_warning: str | None = None
    try:
        reusable = _load_saved_configuration(
            root / "config/last_configuration.json", max_message_bytes=max_message
        )
    except ConfigurationError as exc:
        # E07 keeps the original file for diagnosis and starts with editable
        # defaults; this never grants Setup or replaces a valid default TOML.
        reusable = pb.ExperimentConfiguration()
        history_warning = str(exc)
    _fill_acquisition_defaults(reusable, root)
    tracking = next(
        (item for item in reusable.backends if item.backend_name == "tracking"), None
    )
    if tracking is not None and tracking.WhichOneof("settings") in (None, "tracking"):
        from cephvr.tracking.configuration import resolve_settings

        tracking.tracking.CopyFrom(resolve_settings(root, tracking.tracking))
    assets = ec.get("assets", {})
    if isinstance(assets, dict) and "asset_root" in assets:
        asset_root = assets["asset_root"]
        if not isinstance(asset_root, str) or not asset_root:
            raise ConfigurationError("assets.asset_root must be a nonempty path")
        if not reusable.HasField("asset_root"):
            reusable.asset_root = asset_root
    return reusable, history_warning


def load_controller_configuration(software_root: Path) -> ControllerConfiguration:
    """Resolve only accepted file-owned values; missing scientific inputs stay unset."""
    root = Path(software_root)
    experiment, supervisor = load_control_files(root)
    ec, sc = experiment.config, supervisor.config
    controller_port = _port(_section(ec, "rpc", "port"), "experiment rpc.port")
    supervisor_port = _port(_section(sc, "rpc", "port"), "supervisor rpc.port")
    if controller_port == supervisor_port:
        raise ConfigurationError("controller and supervisor service ports collide")
    max_message = _positive_int(
        _section(ec, "rpc", "max_message_bytes"), "rpc.max_message_bytes"
    )
    queue_bytes = _positive_int(
        _section(ec, "event_queue", "max_pending_payload_bytes"),
        "event_queue.max_pending_payload_bytes",
    )
    metadata_bytes = _positive_int(
        _section(ec, "metadata", "max_pending_bytes"), "metadata.max_pending_bytes"
    )
    if min(queue_bytes, metadata_bytes) < 4 * max_message:
        raise ConfigurationError("event and metadata budgets require four RPC messages")
    max_events = _positive_int(
        _section(ec, "event_queue", "max_pending_events"),
        "event_queue.max_pending_events",
    )
    if max_events < 2:
        raise ConfigurationError("event queue must reserve an interruption event")
    metadata_operations = _positive_int(
        _section(ec, "metadata", "max_pending_operations"),
        "metadata.max_pending_operations",
    )
    max_incidents = _positive_int(
        _section(ec, "control", "max_retained_incidents"),
        "control.max_retained_incidents",
    )
    history_save_timeout = _ns(ec, "configuration_history", "save_timeout_s")
    space_query_timeout = _ns(ec, "storage", "space_query_timeout_s")
    low_space_warning = _section(ec, "storage", "low_space_warning_bytes")
    if type(low_space_warning) is not int or low_space_warning < 0:
        raise ConfigurationError("storage.low_space_warning_bytes must be nonnegative")
    default_gap_value = _section(ec, "protocol", "default_intertrial_gap_s")
    try:
        default_gap = duration_ns(default_gap_value, "s")
    except ValueError as exc:
        raise ConfigurationError(
            "protocol.default_intertrial_gap_s is invalid"
        ) from exc
    lead = _ns(ec, "timing", "start_lead_time_ms", unit="ms")
    controller_cutoff = _ns(
        ec, "timing", "controller_release_cutoff_before_start_ms", unit="ms"
    )
    backend_cutoff = _ns(
        ec, "timing", "backend_release_cutoff_before_start_ms", unit="ms"
    )
    if not lead > controller_cutoff > backend_cutoff:
        raise ConfigurationError("start lead/release cutoff order is invalid")
    setup_cancel = _ns(ec, "timeouts", "setup_cancel", "initial_s")
    trial_finished = _ns(ec, "timeouts", "trial_finished", "initial_s")
    recovery = _ns(ec, "timeouts", "recovery_s")
    startup = _load_supervisor_startup(
        sc, supervisor_port, setup_cancel, trial_finished, recovery
    )
    retention = _ns(ec, "control", "command_record_retention_after_finalization_s")
    policies = pb.ControlPolicies(
        setup=pb.WaitPolicy(initial_ns=_ns(ec, "timeouts", "setup", "initial_s")),
        setup_cancel=pb.WaitPolicy(initial_ns=setup_cancel),
        trial_ready=pb.WaitPolicy(
            initial_ns=_ns(ec, "timeouts", "trial_ready", "initial_s")
        ),
        trial_finished=pb.WaitPolicy(initial_ns=trial_finished),
        supervisor_registration=pb.WaitPolicy(
            initial_ns=_ns(ec, "timeouts", "supervisor_registration", "initial_s")
        ),
        start_lead_ns=lead,
        controller_release_offset_ns=controller_cutoff,
        backend_release_offset_ns=backend_cutoff,
        start_evidence_allowance_ns=_ns(
            ec, "timing", "start_lateness_tolerance_ms", unit="ms"
        ),
        stop_evidence_allowance_ns=_ns(
            ec, "timing", "stop_report_timeout_ms", unit="ms"
        ),
        trial_command_transport_retries=1,
        metadata_timeout_ns=_ns(ec, "metadata", "completion_timeout_s"),
        command_retention_after_finalization_ns=retention,
        recovery_ns=recovery,
    )
    limits_kwargs = {
        "setup_ns": policies.setup.initial_ns,
        "setup_cancel_ns": setup_cancel,
        "ready_ns": policies.trial_ready.initial_ns,
        "finished_ns": trial_finished,
        "registration_ns": policies.supervisor_registration.initial_ns,
        "recovery_ns": recovery,
        "metadata_ns": policies.metadata_timeout_ns,
        "validation_ns": _ns(ec, "configuration_validation", "timeout_s"),
        "history_ns": history_save_timeout,
        "space_query_ns": space_query_timeout,
        "low_space_bytes": low_space_warning,
        "max_retained_incidents": max_incidents,
        "lead_ns": lead,
        "controller_release_ns": controller_cutoff,
        "backend_release_ns": backend_cutoff,
        "start_evidence_ns": policies.start_evidence_allowance_ns,
        "stop_evidence_ns": policies.stop_evidence_allowance_ns,
        "max_metadata_operations": metadata_operations,
        "max_metadata_bytes": metadata_bytes,
    }
    reusable, history_warning = _load_reusable_configuration(root, ec, max_message)
    return ControllerConfiguration(
        configuration=reusable,
        policies=policies,
        limits_kwargs=limits_kwargs,
        supervisor_startup=startup,
        controller_port=controller_port,
        max_message_bytes=max_message,
        max_pending_events=max_events,
        max_pending_payload_bytes=queue_bytes,
        max_retained_incidents=max_incidents,
        default_intertrial_gap_ns=default_gap,
        history_warning=history_warning,
    )


def _fill_acquisition_defaults(
    configuration: pb.ExperimentConfiguration, software_root: Path
) -> None:
    """Fill absent acquisition fields from its owning TOML without enabling it.

    Optional protobuf presence preserves explicit false/zero values. The
    FfmpegArguments message is an atomic list wrapper, so a present empty wrapper
    deliberately replaces the file default with an empty argument list.
    """
    from cephvr.acquisition.configuration import load_defaults

    defaults = load_defaults(software_root)
    backend = next(
        (item for item in configuration.backends if item.backend_name == "acquisition"),
        None,
    )
    if backend is None:
        backend = configuration.backends.add(backend_name="acquisition")
    if backend.WhichOneof("settings") is None:
        backend.acquisition.CopyFrom(defaults)
        return
    if backend.WhichOneof("settings") != "acquisition":
        return
    _fill_missing_message(backend.acquisition, defaults)


def _fill_missing_message(target: Message, defaults: Message) -> None:
    if target.DESCRIPTOR.full_name != defaults.DESCRIPTOR.full_name:
        raise ConfigurationError("acquisition default message type mismatch")
    for descriptor, default_value in defaults.ListFields():
        name = descriptor.name
        if descriptor.is_repeated:
            # Repeated arrays are replaced as a unit by their containing message.
            continue
        if descriptor.message_type is not None:
            if not target.HasField(name):
                getattr(target, name).CopyFrom(default_value)
            else:
                _fill_missing_message(getattr(target, name), default_value)
            continue
        if descriptor.has_presence:
            if not target.HasField(name):
                setattr(target, name, default_value)
        elif getattr(target, name) == descriptor.default_value:
            setattr(target, name, default_value)


def validate_experiment_candidate(
    candidate: pb.ExperimentConfiguration,
) -> pb.ValidationResult:
    """Pure structural checks; device, assets and backend methods stay backend-owned."""
    issues: list[pb.FieldIssue] = []

    def issue(field: str, reason: str) -> None:
        issues.append(
            pb.FieldIssue(
                component="experiment",
                field_path=field,
                failure=pb.Failure(code="INVALID_CONFIGURATION", message=reason),
            )
        )

    if candidate.HasField("mode") and candidate.mode == pb.SESSION_MODE_UNSPECIFIED:
        issue("mode", "UNSPECIFIED is not a session mode")
    for field in ("subject", "experiment"):
        value = getattr(candidate, field)
        if value and not any(
            character.isalnum() and character.isascii() for character in value
        ):
            issue(field, "name must contain an ASCII letter or digit")
    if candidate.asset_root and not candidate.asset_root.strip():
        issue("asset_root", "asset root cannot be whitespace")
    seen_backends: set[str] = set()
    for index, backend in enumerate(candidate.backends):
        if backend.backend_name not in _BACKENDS:
            issue(f"backends[{index}].backend_name", "unknown backend")
        if backend.backend_name in seen_backends:
            issue(f"backends[{index}].backend_name", "duplicate backend")
        seen_backends.add(backend.backend_name)
        if backend.WhichOneof("settings") not in (None, backend.backend_name):
            issue(f"backends[{index}].settings", "backend settings kind mismatch")
    enabled = {item.backend_name for item in candidate.backends if item.enabled}
    if candidate.HasField("mode") and candidate.mode in (
        pb.SESSION_MODE_OPEN_LOOP,
        pb.SESSION_MODE_CLOSED_LOOP,
    ):
        if "visual_stimulus" not in enabled:
            issue("backends", "Visual Stimulus is required for both session modes")
        if candidate.mode == pb.SESSION_MODE_CLOSED_LOOP and "tracking" not in enabled:
            issue("backends", "closed-loop mode requires tracking")
    for index, trial in enumerate(candidate.trials, 1):
        if trial.trial_number != index:
            issue(
                f"trials[{index - 1}].trial_number",
                "trials must be one-based and ordered",
            )
    seen_gaps: set[int] = set()
    for index, gap in enumerate(candidate.gaps):
        if (
            gap.after_trial_number == 0
            or gap.after_trial_number in seen_gaps
            or gap.after_trial_number >= len(candidate.trials)
        ):
            issue(f"gaps[{index}].after_trial_number", "invalid or duplicate gap")
        if gap.minimum_duration_ns < 0:
            issue(f"gaps[{index}].minimum_duration_ns", "gap cannot be negative")
        seen_gaps.add(gap.after_trial_number)
    result = pb.ValidationResult(
        completed=True,
        valid=not issues,
        component="experiment",
        configuration_module_version="experiment-v1",
    )
    result.issues.extend(issues)
    return result


def controller_validators(
    available_backend_validators: Mapping[str, BackendValidator] | None = None,
) -> dict[str, BackendValidator]:
    """Do not imply that missing backend modules can validate enabled settings."""
    available = dict(available_backend_validators or {})
    unknown = set(available) - _BACKENDS
    if unknown:
        raise ValueError(f"unknown backend validator names: {sorted(unknown)}")

    def for_backend(name: str) -> BackendValidator:
        def validate(candidate: pb.ExperimentConfiguration) -> pb.ValidationResult:
            enabled = any(
                item.backend_name == name and item.enabled
                for item in candidate.backends
            )
            if not enabled:
                return pb.ValidationResult(
                    completed=True,
                    valid=True,
                    component=name,
                    configuration_module_version="inactive",
                )
            provider = available.get(name)
            if provider is None:
                return pb.ValidationResult(
                    completed=False,
                    valid=False,
                    component=name,
                    unavailable_reason=pb.Failure(
                        code="VALIDATOR_UNAVAILABLE",
                        message=f"{name} configuration validator is not installed",
                    ),
                )
            result = provider(candidate)
            if result.component != name or not result.configuration_module_version:
                raise ConfigurationError(f"{name} validator identity/version mismatch")
            return result

        return validate

    return {"experiment": validate_experiment_candidate} | {
        name: for_backend(name) for name in sorted(_BACKENDS)
    }
