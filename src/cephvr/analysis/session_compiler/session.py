"""E04 session discovery: central metadata, trial logs and per-trial file names."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from .jsonl import JsonlFile, read_json
from .tables import JSON

PROTOCOL_DIRNAME = "protocol-data"
SPIKEGLX_DIRNAME = "spikeglx-data"
CAMERA_SUFFIX = "_cam_frames.jsonl"


@dataclass
class Trial:
    number: int
    prefix: str
    log: JSON
    start_ns: int | None = None  # SESSION_LOG trial_started = boundary T (E04).
    stop_ns: int | None = None
    outcome: str = ""

    def file(self, protocol: Path, tag: str) -> Path | None:
        path = protocol / f"{self.prefix}_{tag}"
        return path if path.is_file() else None

    def camera_roles(self, protocol: Path) -> list[str]:
        start = len(self.prefix) + 1
        return sorted(
            path.name[start : -len(CAMERA_SUFFIX)]
            for path in protocol.glob(f"{self.prefix}_*{CAMERA_SUFFIX}")
        )


@dataclass
class Session:
    directory: Path
    config: JSON
    events: list[JSON]
    schema: JSON | None
    trials: list[Trial]
    recovery_files: list[str] = field(default_factory=list)

    @property
    def protocol(self) -> Path:
        return self.directory / PROTOCOL_DIRNAME

    @property
    def name(self) -> str:
        return self.directory.name


def is_session(folder: Path) -> bool:
    return (Path(folder) / PROTOCOL_DIRNAME / "SESSION_CONFIG.json").is_file()


def discover_sessions(root: Path) -> list[Path]:
    root = Path(root)
    if is_session(root):
        return [root]
    found = []
    # os.walk skips unreadable folders; never descend into a session, whose
    # spikeglx-data may hold huge sorting trees with over-long paths.
    for folder, children, _ in os.walk(root):
        if is_session(Path(folder)):
            found.append(Path(folder))
            children.clear()
    return sorted(found)


def recorded_files(session_dir: Path) -> list[Path]:
    """Provenance inventory: protocol-data files and native SpikeGLX bin/meta files."""
    files = [p for p in (Path(session_dir) / PROTOCOL_DIRNAME).iterdir() if p.is_file()]
    for folder, _, names in os.walk(Path(session_dir) / SPIKEGLX_DIRNAME):
        files += [Path(folder, n) for n in names if n.endswith((".bin", ".meta"))]
    return sorted(files)


def load_session(directory: Path, warnings: list[str]) -> Session:
    directory = Path(directory)
    protocol = directory / PROTOCOL_DIRNAME
    config = read_json(protocol / "SESSION_CONFIG.json")
    events: list[JSON] = []
    log_path = protocol / "SESSION_LOG.jsonl"
    if log_path.is_file():
        lines = JsonlFile(log_path)
        events = list(lines)
        if lines.truncated:
            warnings.append("SESSION_LOG.jsonl: incomplete final line discarded")
    else:
        warnings.append("SESSION_LOG.jsonl missing")
    schema_path = protocol / "SCHEMA.json"
    schema = read_json(schema_path) if schema_path.is_file() else None
    trials: dict[int, Trial] = {}
    for path in sorted(protocol.glob("*_LOG.json")):
        if path.name.endswith("_stimulus_LOG.json"):
            continue
        log = read_json(path)
        number = log.get("trial_number")
        if type(number) is not int or number < 1:
            raise ValueError(f"{path.name}: invalid trial_number")
        if number in trials:
            raise ValueError(f"duplicate trial_number {number}")
        trials[number] = Trial(number, path.name[: -len("_LOG.json")], log)
    for event in events:
        trial = trials.get(event.get("trial_number"))  # type: ignore[arg-type]
        if trial is None:
            continue
        if event.get("event_type") == "trial_started":
            trial.start_ns = event.get("monotonic_ns")
        elif event.get("event_type") == "trial_finished":
            trial.stop_ns = event.get("monotonic_ns")
            trial.outcome = str(event.get("outcome", ""))
    for trial in trials.values():
        if not trial.log.get("complete"):
            warnings.append(f"Trial {trial.number}: trial LOG is incomplete (crash)")
        trial.outcome = trial.outcome or str(trial.log.get("outcome", ""))
    recovery = sorted(path.name for path in protocol.glob("RECOVERY-*.json"))
    return Session(
        directory,
        config,
        events,
        schema,
        sorted(trials.values(), key=_number),
        recovery,
    )


def _number(trial: Trial) -> int:
    return trial.number


def indexed_outputs(trial: Trial) -> dict[str, JSON]:
    """Trial LOG output index keyed by file name; stored paths name the recording host."""
    return {
        PureWindowsPath(str(item.get("path", ""))).name: item
        for item in trial.log.get("outputs", ())
    }
