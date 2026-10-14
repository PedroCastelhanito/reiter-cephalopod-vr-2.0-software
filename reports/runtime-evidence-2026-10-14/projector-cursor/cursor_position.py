"""Read-only desktop cursor position for native projector-transition evidence."""
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path
api = ctypes.WinDLL("user32", use_last_error=True)
api.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
api.GetCursorPos.restype = wintypes.BOOL
point = wintypes.POINT()
if not api.GetCursorPos(ctypes.byref(point)):
    raise ctypes.WinError(ctypes.get_last_error())
record = {"x": point.x, "y": point.y}
(Path(__file__).parent / (sys.argv[1] + ".json")).write_text(json.dumps(record) + "\n", encoding="utf-8")
print(json.dumps(record))
