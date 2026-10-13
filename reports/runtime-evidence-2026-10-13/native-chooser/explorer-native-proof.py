"""Verify the native shell window belonging only to this probe process."""
import ctypes
import json
import os
import threading
import time
from uuid import uuid4
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget
from cephvr.gui.file_dialogs import file_dialog, open_file_dialog
from cephvr.gui.theme import apply_theme

app = QApplication([])
apply_theme(app)
user32 = ctypes.WinDLL('user32', use_last_error=True)
callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows.argtypes = [callback_type, ctypes.c_void_p]
user32.EnumChildWindows.argtypes = [ctypes.c_void_p, callback_type, ctypes.c_void_p]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
results = []
for mode in ('open', 'save', 'directory'):
    parent = QWidget()
    parent.show()
    app.processEvents()
    title = 'CephVR native proof ' + str(uuid4())
    dialog = file_dialog(parent, title)
    if mode == 'save':
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    elif mode == 'directory':
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)
    else:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    evidence = {'mode': mode, 'native_window': False, 'qt_timer_fired': False}
    stop = threading.Event()
    def close_owned_window():
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not stop.is_set():
            @callback_type
            def inspect(hwnd, _):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != os.getpid():
                    return True
                caption = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, caption, 512)
                if caption.value != title or not user32.IsWindowVisible(hwnd):
                    return True
                classes = []
                @callback_type
                def child(child_hwnd, _):
                    name = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(child_hwnd, name, 256)
                    classes.append(name.value)
                    return True
                user32.EnumChildWindows(hwnd, child, None)
                evidence['native_window'] = 'DirectUIHWND' in classes
                evidence['child_classes'] = sorted(set(classes))
                time.sleep(0.3)
                user32.PostMessageW(hwnd, 0x0010, 0, 0)
                stop.set()
                return False
            user32.EnumWindows(inspect, None)
            time.sleep(0.01)
    worker = threading.Thread(target=close_owned_window, daemon=True)
    worker.start()
    timer = QTimer(dialog)
    timer.setSingleShot(True)
    def observe():
        evidence['qt_timer_fired'] = True
        evidence['native_attribute'] = dialog.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    timer.timeout.connect(observe)
    timer.start(100)
    dialog.finished.connect(lambda _: stop.set())
    open_file_dialog(dialog)
    app.processEvents()
    worker.join(timeout=9)
    results.append(evidence)
    print(json.dumps(evidence), flush=True)
    assert evidence['native_window'], evidence
    dialog.deleteLater()
    parent.deleteLater()
    app.processEvents()
print('all native shell modes verified', flush=True)
