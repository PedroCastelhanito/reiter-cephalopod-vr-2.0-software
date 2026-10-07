"""Build the project-local launcher command for normal start or GUI relaunch."""

from pathlib import Path


def launcher_command(root: Path, python: Path, *, reopen_gui: bool) -> list[str]:
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
    ]
