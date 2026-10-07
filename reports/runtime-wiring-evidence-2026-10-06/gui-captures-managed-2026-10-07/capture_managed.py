"""Offscreen managed-page captures from a synchronized controller Snapshot."""
from pathlib import Path
import sys
from uuid import uuid4

root = Path("/Users/pedrocastelhanito/Dev/reiter-software/reiter-cephalopod-vr-2.0-software")
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "tests" / "visual_stimulus"))

from PyQt6.QtWidgets import QApplication
from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as control_pb
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.camera_inventory import CameraDraft
from cephvr.gui.main import ManagedGui
from cephvr.gui.managed_window import ManagedDashboardWindow
from cephvr.gui.theme import apply_theme
from cephvr.shared.auth import Principal
from cephvr.synchronization.v1 import spikeglx_pb2
from support import valid_display_json


class InertSignal:
    def connect(self, _callback):
        pass


class InertBridge:
    def __init__(self, generation: str):
        self.principal = Principal("gui", generation, "inert-review-token")
        self.connection_epoch = 1
        self.max_message_bytes = 16 * 1024 * 1024
        self.rpc_timeout_s = 1
        self._signals = {}

    def __getattr__(self, name):
        if (
            name.endswith("_received")
            or name.endswith("_changed")
            or name.endswith("_accepted")
            or name in {
            "command_finished",
            "command_admitted",
            "operation_finished",
            "attachment_received",
            "tracking_frame_received",
            }
        ):
            return self._signals.setdefault(name, InertSignal())
        raise AttributeError(name)

    def start(self):
        pass

    def request(self, _action, **_options):
        return False


app = QApplication([])
apply_theme(app)
output = Path(__file__).parent
for width, name in ((720, "720"), (1440, "wide")):
    window = ManagedDashboardWindow(sample=False)
    # Avoid native device/display discovery in this UI-only capture; the managed
    # manager still receives a complete synchronized controller Snapshot below.
    window.devices.cameras.refresh_inventory = lambda: None
    window.devices.microcontroller.scan_ports = lambda: None
    window.devices.projectors.discover_displays = lambda: None
    generation = str(uuid4())
    bridge = InertBridge(generation)
    manager = ManagedGui(window, bridge)
    manager.connection_changed(True, "", 1, generation)

    window.devices.cameras.drafts = [
        CameraDraft("behavior-1", "Behavior cam", "BEH-SERIAL", "Basler"),
        CameraDraft("tracking-1", "Tracking cam", "TRACK-SERIAL", "Basler"),
    ]
    window.devices.cameras.populate_inventory()
    window.devices.cameras.drafts_changed.emit()

    state = control_pb.Snapshot(controller_generation=generation)
    state.session.phase = control_pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 1
    state.configuration_values.revision = 1
    state.control.holder_client_id = bridge.principal.generation
    state.control.control_generation = "accepted-lease"
    config = state.configuration_values.current
    config.mode = control_pb.SESSION_MODE_CLOSED_LOOP
    config.subject = "Review subject"
    config.subject_metadata.species = "Cephalopod"
    config.subject_metadata.age_dph = 0
    config.asset_root = str(output)

    acquisition = config.backends.add(backend_name="acquisition", enabled=True)
    acquisition.acquisition.behavioral.enabled = True
    acquisition.acquisition.behavioral.device.device_id = "BEH-SERIAL"
    acquisition.acquisition.tracking.enabled = True
    acquisition.acquisition.tracking.device.device_id = "TRACK-SERIAL"
    acquisition.acquisition.tracking.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    stimulus = config.backends.add(backend_name="visual_stimulus", enabled=True)
    stimulus.visual_stimulus.display.profile_json = valid_display_json()
    tracking = config.backends.add(backend_name="tracking", enabled=False)
    tracking.tracking.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    config.backends.add(backend_name="synchronization", enabled=True).synchronization.SetInParent()

    manager.install_snapshot(1, generation, state.SerializeToString())
    channels = (
        spikeglx_pb2.PulseChannel(
            role=spikeglx_pb2.PULSE_ROLE_BEHAVIORAL_CAMERA,
            family=spikeglx_pb2.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=1,
        ),
        spikeglx_pb2.PulseChannel(
            role=spikeglx_pb2.PULSE_ROLE_TRACKING_CAMERA,
            family=spikeglx_pb2.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=2,
        ),
    )
    inventory = rpc.SpikeGLXInventorySnapshot(
        configuration_revision=1,
        file_sha256="review-only-digest",
        pulse_channels=channels,
        backend_enabled=True,
        address="169.254.240.108",
        command_port=4142,
    )
    manager.install_spikeglx_inventory(1, generation, inventory.SerializeToString())
    window.resize(width, 900)
    window.show()
    app.processEvents()
    for label, page_index, device_index in (
        ("dashboard", 0, None),
        ("protocol", 1, None),
        ("tracking", 3, None),
        ("projectors", 2, 2),
        ("spikeglx", 2, 3),
    ):
        window.page_buttons[page_index].click()
        if device_index is not None:
            window.devices.tabs.setCurrentIndex(device_index)
        app.processEvents()
        window.grab().save(str(output / f"managed-{label}-{name}.png"))
    if width == 720:
        # The managed page is vertically scrollable; this taller view preserves
        # the same narrow width while exposing the inventory editor rows.
        window.resize(width, 1300)
        app.processEvents()
        window.grab().save(str(output / "managed-spikeglx-720-tall.png"))
    manager.tracking_diagnostics.timer.stop()
    window._close_after_save = True
    window.close()
    window.deleteLater()
    app.processEvents()
print("Rendered through ManagedGui.install_snapshot with inert RPC/device discovery and an authoritative-shaped Snapshot.")
