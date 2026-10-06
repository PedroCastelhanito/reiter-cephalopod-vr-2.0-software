"""One-time owner-only inheritance repair after private-record migration."""

import ctypes
import os
from pathlib import Path

from cephvr.platform.windows import security
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.shared.credentials import _check_private, default_runtime_root

with SingleInstanceGuard("application"):
    private_root = default_runtime_root()
    for entry in private_root.rglob("*"):
        _check_private(entry, directory=entry.is_dir())
    legacy_root = Path(os.environ["LOCALAPPDATA"]) / "CephVR" / "runtime"
    if any(entry.name == "recovery" or len(entry.name) == 36 for entry in legacy_root.iterdir()):
        raise RuntimeError("private records remain in legacy namespace")
    kernel, advapi = security._apis()
    name = security._checked_path(legacy_root, kernel)
    sid, token_buffer, sid_length = security._user_sid(kernel, advapi)
    buffer = ctypes.create_string_buffer(ctypes.sizeof(security._ACL) + 8 + sid_length)
    acl = ctypes.cast(buffer, ctypes.c_void_p)
    if not advapi.InitializeAcl(acl, len(buffer), security.ACL_REVISION):
        raise ctypes.WinError(ctypes.get_last_error())
    # Allow only the current owner, inherited by legacy subdirectories and files.
    if not advapi.AddAccessAllowedAceEx(acl, security.ACL_REVISION, 3, security.FILE_ALL_ACCESS, sid):
        raise ctypes.WinError(ctypes.get_last_error())
    result = advapi.SetNamedSecurityInfoW(
        name, security.SE_FILE_OBJECT,
        security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None,
    )
    if result:
        raise ctypes.WinError(result)
    for entry in private_root.rglob("*"):
        _check_private(entry, directory=entry.is_dir())
    with (legacy_root / "controller" / "controller.log").open("a", encoding="utf-8"):
        pass
    print("Legacy controller log writable; migrated CephVR2.0 records remain owner-only")
