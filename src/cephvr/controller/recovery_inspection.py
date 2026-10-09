"""Bounded read-only inspection of unfinished E04 administrative records."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import StorageError


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"invalid JSON number {value}")


def _classify_recovery_event(
    event: dict[str, Any],
    trials: dict[int, str | None],
    started: set[int],
    finished: set[int],
    session_started: bool,
    session_ended: bool,
) -> tuple[str, tuple[int, str] | None]:
    """Validate one known reconciliation record or the final startup repair."""
    details = event.get("details")
    if not isinstance(details, dict):
        raise ValueError("recovery event details are unconfirmed")
    if (
        details.get("component") == "Finished"
        and details.get("action") == "reconcile exact output closure"
    ):
        number = event.get("trial_number")
        backend = details.get("backend")
        outputs = details.get("outputs")
        trial_id = details.get("trial_id")
        if (
            event.get("outcome") != "completed"
            or type(number) is not int
            or number not in started
            or number not in trials
            or not isinstance(trial_id, str)
            or not trial_id
            or trials[number] != trial_id
            or not isinstance(backend, str)
            or not backend
            or type(details.get("initial_deadline_ns")) is not int
            or details["initial_deadline_ns"] < 0
            or not isinstance(outputs, list)
        ):
            raise ValueError("Finished reconciliation is unconfirmed")
        output_keys: set[str] = set()
        for output in outputs:
            closure = output.get("closure") if isinstance(output, dict) else None
            if (
                not isinstance(output, dict)
                or set(output) != {"output_key", "closure"}
                or not isinstance(output.get("output_key"), str)
                or not output["output_key"]
                or output["output_key"] in output_keys
                or not isinstance(closure, str)
                or closure not in pb.OutputClosure.keys()
                or closure == pb.OutputClosure.Name(pb.OUTPUT_CLOSURE_UNSPECIFIED)
            ):
                raise ValueError("Finished output reconciliation is invalid")
            output_keys.add(output["output_key"])
        return "finished", (number, backend)
    if (
        isinstance(details.get("incident_id"), str)
        and details["incident_id"]
        and isinstance(details.get("resolved_by"), str)
        and details["resolved_by"]
        and type(details.get("recovered_monotonic_ns")) is int
        and details["recovered_monotonic_ns"] >= 0
        and session_started
        and not session_ended
        and event.get("outcome") is None
    ):
        return "incident", None
    if (
        details.get("component") == "controller"
        and details.get("action") == "startup_recovery"
        and isinstance(details.get("recovery_controller_generation"), str)
        and details["recovery_controller_generation"]
        and details.get("event_clock") == "current_recovery_application"
        and details.get("scientific_output_closure") == "unconfirmed"
        and event.get("outcome") == "completed"
        and session_ended
        and started == finished
    ):
        return "terminal", None
    raise ValueError("recovery event is malformed or out of order")


def read_recovery_file(path: Path, limit: int) -> tuple[bytes, os.stat_result]:
    if type(limit) is not int or limit < 1:
        raise StorageError("recovery input has no positive inspection byte budget")
    before = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_file_attributes", 0) & 0x400
    ):
        raise StorageError("recovery input is not a regular, non-reparse file")
    with os.fdopen(
        os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        ),
        "rb",
    ) as stream:
        actual = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(actual.st_mode)
            or getattr(actual, "st_file_attributes", 0) & 0x400
            or (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino)
            or actual.st_size > limit
        ):
            raise StorageError("recovery input changed or exceeds the inspection bound")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise StorageError("recovery input exceeds the inspection bound")
    return raw, actual


@dataclass(frozen=True)
class RecoveryInspection:
    marker_digest: str
    marker_bytes: bytes
    log_identity: tuple[int, int, int] | None
    log_digest: str | None
    config_digest: str | None
    zone: str
    session_started: bool
    session_ended: bool
    recovery_recorded: bool
    unfinished_trials: tuple[int, ...]
    spikeglx_stop_unconfirmed: bool
    spikeglx_endpoint: tuple[str, int] | None
    spikeglx_run: str | None
    issue: str | None


def inspect_recovery(
    reservation: OutputReservation, max_bytes: int
) -> RecoveryInspection:
    """Inspect bounded administrative evidence without inferring scientific closure."""
    if type(max_bytes) is not int or max_bytes <= 4096:
        raise StorageError("recovery inspection byte budget is too small")
    if not reservation.held:
        raise StorageError("recovery inspection requires held reservation")
    marker, _ = read_recovery_file(reservation.marker, 4096)
    digest = hashlib.sha256(marker).hexdigest()
    if reservation.marker_issue in {
        "reservation marker identity mismatch",
        "reservation marker already complete",
    }:
        raise StorageError(reservation.marker_issue)
    known_run: str | None = None
    known_endpoint: tuple[str, int] | None = None
    known_paired: bool | None = None
    try:
        config_raw, _ = read_recovery_file(
            reservation.protocol_directory / "SESSION_CONFIG.json", max_bytes
        )
        config = json.loads(
            config_raw, object_pairs_hook=_pairs, parse_constant=_constant
        )
        if (
            not isinstance(config, dict)
            or type(config.get("schema_version")) is not int
            or config["schema_version"] != 1
            or config.get("session_id") != reservation.session_id
            or config.get("controller_generation") != reservation.generation
        ):
            raise ValueError("session configuration identity/schema is unconfirmed")
        zone = config["local_timezone"]
        if not isinstance(zone, str):
            raise ValueError("session timezone is invalid")
        ZoneInfo(zone)
        if not isinstance(config.get("trials"), list):
            raise ValueError("session trial plan is invalid")
        trial_contexts = [item["context"] for item in config["trials"]]
        trial_numbers = [item["trial_number"] for item in trial_contexts]
        if (
            not trial_numbers
            or any(type(number) is not int or number < 1 for number in trial_numbers)
            or len(set(trial_numbers)) != len(trial_numbers)
        ):
            raise ValueError("session trial plan numbers are invalid")
        trials = {item["trial_number"]: item.get("trial_id") for item in trial_contexts}
        configuration = config.get("configuration")
        if not isinstance(configuration, dict) or not isinstance(
            configuration.get("backends"), list
        ):
            raise ValueError("session backend configuration is invalid")
        spikeglx = config.get("spikeglx")
        run = spikeglx.get("run_name") if isinstance(spikeglx, dict) else None
        paired = any(
            item.get("backend_name") == "synchronization"
            and item.get("enabled") is True
            for item in configuration["backends"]
        )
        known_paired = paired
        if paired and (not isinstance(run, str) or not run):
            raise ValueError("paired SpikeGLX run identity is unavailable")
        endpoint: tuple[str, int] | None = None
        endpoint_data = spikeglx
        if paired and isinstance(endpoint_data, dict):
            address, port = endpoint_data.get("address"), endpoint_data.get("port")
            if (
                isinstance(address, str)
                and address
                and type(port) is int
                and 1 <= port <= 65535
            ):
                endpoint = (address, port)
        known_run = run if isinstance(run, str) and run else None
        known_endpoint = endpoint
        remaining = max_bytes - len(config_raw)
        if remaining < 1:
            raise ValueError("session log has no remaining inspection byte budget")
        raw, info = read_recovery_file(
            reservation.protocol_directory / "SESSION_LOG.jsonl",
            remaining,
        )
        if not raw or not raw.endswith(b"\n"):
            raise ValueError("session log is empty or its final line is incomplete")
        started: set[int] = set()
        finished: set[int] = set()
        reconciled_finished: set[tuple[int, str]] = set()
        session_started = session_ended = recovery_recorded = False
        stopped_remote = False
        catalog = {
            "session_started",
            "trial_started",
            "trial_finished",
            "session_ended",
            "command_accepted",
            "setup_override",
            "error",
            "recovery",
            "spikeglx_started",
            "spikeglx_stopped",
            "incident_decision",
        }
        for line in raw.splitlines():
            if recovery_recorded:
                raise ValueError("session log contains data after final recovery")
            event = json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant)
            if (
                not isinstance(event, dict)
                or event.get("event_type") not in catalog
                or type(event.get("monotonic_ns")) is not int
                or event["monotonic_ns"] < 0
                or not isinstance(event.get("source"), str)
                or event.get("details") is not None
                and not isinstance(event["details"], dict)
            ):
                raise ValueError("session log event shape is unconfirmed")
            wall = datetime.fromisoformat(event["wall_time"])
            if wall.tzinfo is None:
                raise ValueError("session log wall time lacks an offset")
            kind = event["event_type"]
            if kind == "session_started":
                if session_started or session_ended:
                    raise ValueError("session log repeats activation")
                session_started = True
            elif kind == "session_ended":
                if not session_started or session_ended or started != finished:
                    raise ValueError("session log terminal outcome is inconsistent")
                session_ended = True
            elif kind in {"trial_started", "trial_finished"}:
                number = event.get("trial_number")
                if (
                    type(number) is not int
                    or number not in trials
                    or not session_started
                ):
                    raise ValueError("session log trial identity is unconfirmed")
                if kind == "trial_started":
                    if number in started or session_ended or started != finished:
                        raise ValueError("session log repeats a trial start")
                    started.add(number)
                else:
                    if number not in started or number in finished:
                        raise ValueError("session log trial completion is inconsistent")
                    finished.add(number)
            elif kind == "spikeglx_stopped" and run:
                details = event.get("details") or {}
                if details.get("run_name") == run:
                    stopped_remote = True
            elif kind == "recovery":
                category, key = _classify_recovery_event(
                    event, trials, started, finished, session_started, session_ended
                )
                if category == "finished":
                    assert key is not None
                    if key in reconciled_finished:
                        raise ValueError("duplicate Finished reconciliation")
                    reconciled_finished.add(key)
                elif category == "terminal":
                    recovery_recorded = True
        if not session_started or session_ended and started != finished:
            raise ValueError("session lifecycle is incomplete or out of order")
        return RecoveryInspection(
            digest,
            marker,
            (info.st_dev, info.st_ino, info.st_size),
            hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(config_raw).hexdigest(),
            zone,
            session_started,
            session_ended,
            recovery_recorded,
            tuple(sorted(started - finished)),
            paired and not stopped_remote,
            endpoint,
            run,
            reservation.marker_issue,
        )
    except (
        OSError,
        StorageError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        # The original files remain byte-for-byte untouched. No outcome is inferred.
        return RecoveryInspection(
            digest,
            marker,
            None,
            None,
            None,
            "UTC",
            False,
            False,
            False,
            (),
            known_paired is not False,
            known_endpoint,
            known_run,
            f"administrative log/configuration inspection unconfirmed: {exc}",
        )
