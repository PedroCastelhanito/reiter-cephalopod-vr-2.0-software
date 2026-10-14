"""Per-application Windows graphics preferences, applied before process creation."""

from pathlib import Path

from cephvr.platform.windows.jobs import WindowsLaunchError

_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"


def preference_value(previous: str, *, high_performance: bool) -> str:
    """Replace only GPU preference, preserving other per-application options."""
    options = [
        part
        for part in previous.split(";")
        if part and part.partition("=")[0].casefold() != "gpupreference"
    ]
    options.append(f"GpuPreference={2 if high_performance else 1}")
    return ";".join(options) + ";"


def configure_graphics_preference(executable: Path, *, high_performance: bool) -> None:
    """Set/read back only this verified managed image's current-user preference."""
    import winreg

    name = str(executable.resolve())
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_READ | winreg.KEY_WRITE
        ) as key:
            try:
                previous, kind = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                previous, kind = "", winreg.REG_SZ
            if kind != winreg.REG_SZ or not isinstance(previous, str):
                raise WindowsLaunchError("managed graphics preference is not a string")
            value = preference_value(previous, high_performance=high_performance)
            if previous != value:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            if winreg.QueryValueEx(key, name) != (value, winreg.REG_SZ):
                raise WindowsLaunchError(
                    "managed graphics preference read-back differs"
                )
    except OSError as exc:
        raise WindowsLaunchError(
            f"cannot configure graphics preference for {name}: {exc}"
        ) from exc
