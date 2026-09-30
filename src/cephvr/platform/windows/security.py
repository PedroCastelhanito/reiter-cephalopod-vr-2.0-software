"""Owner-only Windows ACLs for local generation credentials (E08)."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import Any

SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 0x1
DACL_SECURITY_INFORMATION = 0x4
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
SE_DACL_PROTECTED = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_USER = 1
ACL_REVISION = 2
ACCESS_ALLOWED_ACE_TYPE = 0
FILE_ALL_ACCESS = 0x1F01FF
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
SECURITY_DESCRIPTOR_REVISION = 1
GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
CREATE_NEW = 1
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
FILE_SHARE_DELETE = 0x4
ERROR_FILE_EXISTS = 80
ERROR_ALREADY_EXISTS = 183
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class WindowsSecurityError(RuntimeError):
    pass


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


class _ACL(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_byte),
        ("Sbz1", ctypes.c_byte),
        ("AclSize", wintypes.WORD),
        ("AceCount", wintypes.WORD),
        ("Sbz2", wintypes.WORD),
    ]


class _ACE_HEADER(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_byte),
        ("AceFlags", ctypes.c_byte),
        ("AceSize", wintypes.WORD),
    ]


class _SECURITY_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("Revision", ctypes.c_ubyte),
        ("Sbz1", ctypes.c_ubyte),
        ("Control", wintypes.WORD),
        ("Owner", ctypes.c_void_p),
        ("Group", ctypes.c_void_p),
        ("Sacl", ctypes.c_void_p),
        ("Dacl", ctypes.c_void_p),
    ]


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


SecurityAttributes = _SECURITY_ATTRIBUTES


class _FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


@lru_cache(maxsize=1)
def _apis() -> tuple[Any, Any]:
    if sys.platform != "win32":
        raise WindowsSecurityError("Windows ACL verification requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.CreateDirectoryW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
    ]
    kernel.CreateDirectoryW.restype = wintypes.BOOL
    kernel.WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.WriteFile.restype = wintypes.BOOL
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.FlushFileBuffers.restype = wintypes.BOOL
    kernel.DeleteFileW.argtypes = [wintypes.LPCWSTR]
    kernel.DeleteFileW.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi.GetLengthSid.restype = wintypes.DWORD
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.EqualSid.restype = wintypes.BOOL
    advapi.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi.InitializeAcl.restype = wintypes.BOOL
    advapi.AddAccessAllowedAceEx.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi.AddAccessAllowedAceEx.restype = wintypes.BOOL
    advapi.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetSecurityInfo.restype = wintypes.DWORD
    advapi.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetAce.restype = wintypes.BOOL
    advapi.InitializeSecurityDescriptor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    advapi.InitializeSecurityDescriptor.restype = wintypes.BOOL
    advapi.SetSecurityDescriptorOwner.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
    ]
    advapi.SetSecurityDescriptorOwner.restype = wintypes.BOOL
    advapi.SetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_void_p,
        wintypes.BOOL,
    ]
    advapi.SetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.SetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        wintypes.WORD,
        wintypes.WORD,
    ]
    advapi.SetSecurityDescriptorControl.restype = wintypes.BOOL
    return kernel, advapi


def _checked_path(path: Path, kernel: Any) -> str:
    path = Path(path)
    if path.is_symlink():
        raise WindowsSecurityError("credential path is a link")
    attrs = kernel.GetFileAttributesW(str(path))
    if attrs == INVALID_FILE_ATTRIBUTES:
        raise WindowsSecurityError(
            f"GetFileAttributesW failed: {ctypes.get_last_error()}"
        )
    if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
        raise WindowsSecurityError("credential path is a reparse point")
    return str(path)


def _user_sid(kernel: Any, advapi: Any) -> tuple[int, object, int]:
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(
        kernel.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)
    ):
        raise WindowsSecurityError(
            f"OpenProcessToken failed: {ctypes.get_last_error()}"
        )
    try:
        length = wintypes.DWORD()
        advapi.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(length))
        buffer = ctypes.create_string_buffer(length.value)
        if not advapi.GetTokenInformation(
            token, TOKEN_USER, buffer, length, ctypes.byref(length)
        ):
            raise WindowsSecurityError(
                f"GetTokenInformation failed: {ctypes.get_last_error()}"
            )
        sid = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents.User.Sid
        return sid, buffer, int(advapi.GetLengthSid(sid))
    finally:
        kernel.CloseHandle(token)


def _creation_security(
    kernel: Any, advapi: Any, access_mask: int = FILE_ALL_ACCESS
) -> tuple[_SECURITY_ATTRIBUTES, tuple[object, ...]]:
    """Build an owner-only protected DACL before the object becomes visible."""
    sid, token_buffer, sid_length = _user_sid(kernel, advapi)
    acl_size = ctypes.sizeof(_ACL) + 8 + sid_length
    acl_buffer = ctypes.create_string_buffer(acl_size)
    acl = ctypes.cast(acl_buffer, ctypes.c_void_p)
    if not advapi.InitializeAcl(acl, acl_size, ACL_REVISION):
        raise WindowsSecurityError(f"InitializeAcl failed: {ctypes.get_last_error()}")
    if access_mask <= 0:
        raise WindowsSecurityError("native object access mask must be positive")
    if not advapi.AddAccessAllowedAceEx(acl, ACL_REVISION, 0, access_mask, sid):
        raise WindowsSecurityError(
            f"AddAccessAllowedAceEx failed: {ctypes.get_last_error()}"
        )
    descriptor = _SECURITY_DESCRIPTOR()
    descriptor_ptr = ctypes.cast(ctypes.byref(descriptor), ctypes.c_void_p)
    if not advapi.InitializeSecurityDescriptor(
        descriptor_ptr, SECURITY_DESCRIPTOR_REVISION
    ):
        raise WindowsSecurityError(
            f"InitializeSecurityDescriptor failed: {ctypes.get_last_error()}"
        )
    if not advapi.SetSecurityDescriptorOwner(descriptor_ptr, sid, False):
        raise WindowsSecurityError(
            f"SetSecurityDescriptorOwner failed: {ctypes.get_last_error()}"
        )
    if not advapi.SetSecurityDescriptorDacl(descriptor_ptr, True, acl, False):
        raise WindowsSecurityError(
            f"SetSecurityDescriptorDacl failed: {ctypes.get_last_error()}"
        )
    if not advapi.SetSecurityDescriptorControl(
        descriptor_ptr, SE_DACL_PROTECTED, SE_DACL_PROTECTED
    ):
        raise WindowsSecurityError(
            f"SetSecurityDescriptorControl failed: {ctypes.get_last_error()}"
        )
    attrs = _SECURITY_ATTRIBUTES(
        ctypes.sizeof(_SECURITY_ATTRIBUTES), descriptor_ptr, False
    )
    return attrs, (token_buffer, acl_buffer, descriptor)


def owner_only_security_attributes(
    access_mask: int, *, inheritable: bool = False
) -> tuple[SecurityAttributes, tuple[object, ...]]:
    """Create typed, protected owner-only attributes for an exact native access mask."""
    kernel, advapi = _apis()
    attributes, backing = _creation_security(kernel, advapi, access_mask)
    attributes.bInheritHandle = inheritable
    return attributes, backing


def owner_only_inheritable_security_attributes() -> tuple[
    SecurityAttributes, tuple[object, ...]
]:
    """Owner-only creation security for a deliberately inherited pipe handle."""
    return owner_only_security_attributes(FILE_ALL_ACCESS, inheritable=True)


def create_owner_only_directory(path: Path) -> None:
    """Create a new directory with the private ACL applied atomically."""
    kernel, advapi = _apis()
    attrs, backing = _creation_security(kernel, advapi)
    _ = backing
    if not kernel.CreateDirectoryW(str(path), ctypes.byref(attrs)):
        raise WindowsSecurityError(
            f"CreateDirectoryW failed: {ctypes.get_last_error()}"
        )
    verify_owner_only(path)


def create_owner_only(path: Path, payload: bytes) -> None:
    """Exclusively create and flush a private credential file without an ACL gap."""
    if not isinstance(payload, bytes):
        raise TypeError("credential payload must be bytes")
    kernel, advapi = _apis()
    attrs, backing = _creation_security(kernel, advapi)
    _ = backing
    handle = kernel.CreateFileW(
        str(path),
        GENERIC_WRITE,
        0,
        ctypes.byref(attrs),
        CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle == INVALID_HANDLE_VALUE or handle is None:
        raise WindowsSecurityError(f"CreateFileW failed: {ctypes.get_last_error()}")
    try:
        offset = 0
        while offset < len(payload):
            chunk = payload[offset : offset + 65536]
            buffer = ctypes.create_string_buffer(chunk)
            written = wintypes.DWORD()
            if not kernel.WriteFile(
                handle, buffer, len(chunk), ctypes.byref(written), None
            ):
                raise WindowsSecurityError(
                    f"WriteFile failed: {ctypes.get_last_error()}"
                )
            if written.value == 0:
                raise WindowsSecurityError("WriteFile made no progress")
            offset += written.value
        if not kernel.FlushFileBuffers(handle):
            raise WindowsSecurityError(
                f"FlushFileBuffers failed: {ctypes.get_last_error()}"
            )
    except BaseException:
        kernel.CloseHandle(handle)
        kernel.DeleteFileW(str(path))
        raise
    else:
        kernel.CloseHandle(handle)
    verify_owner_only(path)


def ensure_owner_only(path: Path) -> None:
    """Set a protected one-ACE DACL for the current token user, then verify it."""
    kernel, advapi = _apis()
    name = _checked_path(path, kernel)
    sid, token_buffer, sid_length = _user_sid(kernel, advapi)
    _ = token_buffer  # Keep token memory alive through the ACL call.
    acl_size = ctypes.sizeof(_ACL) + 8 + sid_length
    acl_buffer = ctypes.create_string_buffer(acl_size)
    acl = ctypes.cast(acl_buffer, ctypes.c_void_p)
    if not advapi.InitializeAcl(acl, acl_size, ACL_REVISION):
        raise WindowsSecurityError(f"InitializeAcl failed: {ctypes.get_last_error()}")
    if not advapi.AddAccessAllowedAceEx(acl, ACL_REVISION, 0, FILE_ALL_ACCESS, sid):
        raise WindowsSecurityError(
            f"AddAccessAllowedAceEx failed: {ctypes.get_last_error()}"
        )
    result = advapi.SetNamedSecurityInfoW(
        name,
        SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION
        | DACL_SECURITY_INFORMATION
        | PROTECTED_DACL_SECURITY_INFORMATION,
        sid,
        None,
        acl,
        None,
    )
    if result:
        raise WindowsSecurityError(f"SetNamedSecurityInfoW failed: {result}")
    verify_owner_only(path)


def verify_owner_only(path: Path) -> None:
    """Reject reparse points, another owner, inherited/extra ACEs or broad access."""
    kernel, advapi = _apis()
    name = _checked_path(path, kernel)
    sid, token_buffer, _ = _user_sid(kernel, advapi)
    _ = token_buffer
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    result = advapi.GetNamedSecurityInfoW(
        name,
        SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result:
        raise WindowsSecurityError(f"GetNamedSecurityInfoW failed: {result}")
    try:
        _verify_descriptor(advapi, owner, dacl, descriptor, sid)
    finally:
        kernel.LocalFree(descriptor)


def _verify_descriptor(
    advapi: Any,
    owner: ctypes.c_void_p,
    dacl: ctypes.c_void_p,
    descriptor: ctypes.c_void_p,
    sid: int,
) -> None:
    if not owner.value or not advapi.EqualSid(owner, sid):
        raise WindowsSecurityError("credential owner is not current user")
    if not dacl.value:
        raise WindowsSecurityError("credential DACL is absent")
    control, revision = wintypes.WORD(), wintypes.DWORD()
    if not advapi.GetSecurityDescriptorControl(
        descriptor, ctypes.byref(control), ctypes.byref(revision)
    ):
        raise WindowsSecurityError(
            f"GetSecurityDescriptorControl failed: {ctypes.get_last_error()}"
        )
    if not control.value & SE_DACL_PROTECTED:
        raise WindowsSecurityError("credential DACL permits inheritance")
    acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
    if acl.AceCount != 1:
        raise WindowsSecurityError("credential DACL has extra ACEs")
    ace = ctypes.c_void_p()
    if not advapi.GetAce(dacl, 0, ctypes.byref(ace)):
        raise WindowsSecurityError(f"GetAce failed: {ctypes.get_last_error()}")
    header = ctypes.cast(ace, ctypes.POINTER(_ACE_HEADER)).contents
    if header.AceType != ACCESS_ALLOWED_ACE_TYPE or header.AceFlags:
        raise WindowsSecurityError("credential ACE is not explicit allow")
    if ace.value is None:
        raise WindowsSecurityError("credential ACE pointer is absent")
    mask = ctypes.c_uint32.from_address(ace.value + 4).value
    ace_sid = ctypes.c_void_p(ace.value + 8)
    if mask != FILE_ALL_ACCESS or not advapi.EqualSid(ace_sid, sid):
        raise WindowsSecurityError("credential ACE grants another or incomplete access")


def _verify_owner_only_handle(handle: int, kernel: Any, advapi: Any) -> None:
    attributes = _FILE_ATTRIBUTE_TAG_INFO()
    if not kernel.GetFileInformationByHandleEx(
        handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)
    ):
        raise WindowsSecurityError(
            f"GetFileInformationByHandleEx failed: {ctypes.get_last_error()}"
        )
    if attributes.FileAttributes & (
        FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY
    ):
        raise WindowsSecurityError("lock path is not a regular file")
    sid, token_buffer, _ = _user_sid(kernel, advapi)
    _ = token_buffer
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    result = advapi.GetSecurityInfo(
        handle,
        SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result:
        raise WindowsSecurityError(f"GetSecurityInfo failed: {result}")
    try:
        _verify_descriptor(advapi, owner, dacl, descriptor, sid)
    finally:
        kernel.LocalFree(descriptor)


def open_owner_only_lock(path: Path) -> tuple[int, bool]:
    """Open a private lock file without following a reparse point.

    The returned CRT descriptor owns the HANDLE. FILE_SHARE_DELETE permits the
    reservation owner to tombstone a newly created lock while its byte lock is held.
    """
    if sys.platform != "win32":
        raise WindowsSecurityError("Windows lock opening requires Windows")
    import msvcrt

    kernel, advapi = _apis()
    attrs, backing = _creation_security(kernel, advapi)
    _ = backing
    share = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
    flags = FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT
    handle = kernel.CreateFileW(
        str(path),
        GENERIC_READ | GENERIC_WRITE,
        share,
        ctypes.byref(attrs),
        CREATE_NEW,
        flags,
        None,
    )
    created = handle != INVALID_HANDLE_VALUE and handle is not None
    if not created:
        error = ctypes.get_last_error()
        if error not in (ERROR_FILE_EXISTS, ERROR_ALREADY_EXISTS):
            raise WindowsSecurityError(f"CreateFileW failed: {error}")
        handle = kernel.CreateFileW(
            str(path),
            GENERIC_READ | GENERIC_WRITE,
            share,
            None,
            OPEN_EXISTING,
            flags,
            None,
        )
        if handle == INVALID_HANDLE_VALUE or handle is None:
            raise WindowsSecurityError(
                f"CreateFileW existing lock failed: {ctypes.get_last_error()}"
            )
    try:
        _verify_owner_only_handle(handle, kernel, advapi)
        return msvcrt.open_osfhandle(int(handle), os.O_RDWR), created
    except BaseException:
        kernel.CloseHandle(handle)
        raise
