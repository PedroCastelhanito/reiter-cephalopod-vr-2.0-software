import asyncio
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).with_suffix('.json')

async def snapshot():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            return await HeadlessClient(channel, principal).get_snapshot()
    finally:
        store.remove_client(principal)

state = asyncio.run(snapshot())
from PyQt6.QtWidgets import QApplication
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.main import ManagedGui
from cephvr.gui.managed_window import ManagedDashboardWindow
from cephvr.shared.auth import Principal

app = QApplication([])
bridge = ControllerBridge(Principal('gui', state.control.holder_client_id, 'unused'), 50051, 1024, (0,))
bridge.start = lambda: None
bridge.request = lambda *args, **kwargs: True
window = ManagedDashboardWindow(sample=False)
manager = ManagedGui(window, bridge, gui_history_path=Path('config/runtime_gui.json'))
manager.control_ready = True
manager.auto_control_attempted = True
manager._connection_identity = (1, state.controller_generation)
manager.install_snapshot(1, state.controller_generation, state.SerializeToString())
mcu = window.devices.microcontroller
result = {'method': 'read-only authenticated snapshot projected into isolated Qt GUI; no hardware commands',
          'generation': state.controller_generation, 'revision': state.configuration.revision,
          'configuration_error': manager.configuration.last_error,
          'configuration_stale': manager.configuration.stale,
          'port_enabled': mcu.port.isEnabled(), 'scan_enabled': mcu.scan_button.isEnabled(),
          'test_connection_enabled': mcu.test_connection_button.isEnabled(),
          'mcu_files_available': mcu.snapshots.available(),
          'gui_files_available': window.snapshots.available()}
OUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result), flush=True)
manager.tracking_diagnostics.timer.stop()
window.deleteLater()
