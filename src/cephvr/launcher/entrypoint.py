"""Build the project-local launcher command for normal start or GUI relaunch."""

from pathlib import Path


def launcher_command(
    root: Path, python: Path, *, reopen_gui: bool, no_tracking: bool = False
) -> list[str]:
    if reopen_gui and no_tracking:
        raise ValueError("--no-tracking requires a fresh application launch")
    command = [str(python), "-m", "cephvr.launcher.main"]
    if reopen_gui:
        return [*command, "--reopen-gui"]
    return [
        *command,
        "--software-root",
        str(root),
        "--supervisor-config",
        str(root / "config" / "backends" / "supervisor_config.toml"),
        "--python",
        str(python),
        *(["--no-tracking"] if no_tracking else []),
    ]
