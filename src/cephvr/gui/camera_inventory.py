"""Serial-keyed discovery records; enumeration never opens a camera."""

from dataclasses import dataclass
from dataclasses import field as data_field

from cephvr.acquisition.camera.basler import BaslerCameraAdapter


@dataclass
class CameraDraft:
    key: str
    role: str
    serial: str
    model: str
    enabled: bool = True
    connected: bool = False
    capture_running: bool = False
    values: dict[str, str] = data_field(default_factory=dict)


def discover_drafts(
    adapter: BaslerCameraAdapter, drafts: list[CameraDraft], *, managed: bool
) -> list[CameraDraft]:
    try:
        pylon = adapter._sdk()
        found = tuple(
            (str(info.GetSerialNumber()), str(info.GetModelName()))
            for info in pylon.TlFactory.GetInstance().EnumerateDevices()
        )
        if any(not serial or not model for serial, model in found):
            raise ValueError("incomplete camera identity")
        if len({serial for serial, _ in found}) != len(found):
            raise ValueError("duplicate camera serial")
    finally:
        adapter.close()
    previous = {draft.serial: draft for draft in drafts}
    serials = {serial for serial, _ in found}
    roles = {draft.role for serial, draft in previous.items() if serial in serials}
    result = []
    for serial, model in found:
        draft = previous.get(serial)
        if draft is None:
            role = next(
                (
                    role
                    for role in ("Behavior cam", "Tracking cam")
                    if role not in roles
                ),
                "Unassigned",
            )
            draft = CameraDraft(f"camera-{serial}", role, serial, model)
            roles.add(role)
        if managed:
            draft.role, draft.enabled = "Unassigned", False
        result.append(draft)
    return result
