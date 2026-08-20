"""Fail-closed reads for analyst-owned local configuration and secrets."""

import os
import stat
import sys
from pathlib import Path
from typing import Any


class SecureFileError(Exception):
    """A deliberately detail-free local-file policy failure."""


def read_secure_file(path: Path) -> bytes:
    """Read one user-only regular file without following its final symlink."""

    if sys.platform == "win32":
        return _read_secure_file_windows(path)

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise SecureFileError

    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | no_follow)
        metadata = os.fstat(descriptor)
        permissions = stat.S_IMODE(metadata.st_mode)
        allowed_permissions = stat.S_IRUSR | stat.S_IWUSR
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or not permissions & stat.S_IRUSR
            or permissions & ~allowed_permissions
        ):
            raise SecureFileError

        with os.fdopen(descriptor, "rb") as file:
            descriptor = None
            return file.read()
    except (OSError, SecureFileError) as error:
        raise SecureFileError from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_secure_file_windows(path: Path) -> bytes:
    """Apply the equivalent owner, ACL, and no-reparse-point policy on Windows."""

    # Imports stay inside the platform branch because WinDLL and msvcrt are unavailable
    # on POSIX hosts.
    import ctypes
    import ctypes.wintypes as wintypes
    import msvcrt
    from ctypes import POINTER, Structure, byref, c_ubyte, c_void_p, cast

    class FileInformation(Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("last_access_time", wintypes.FILETIME),
            ("last_write_time", wintypes.FILETIME),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    class Acl(Structure):
        _fields_ = [
            ("revision", c_ubyte),
            ("sbz1", c_ubyte),
            ("size", wintypes.WORD),
            ("ace_count", wintypes.WORD),
            ("sbz2", wintypes.WORD),
        ]

    class AceHeader(Structure):
        _fields_ = [
            ("ace_type", c_ubyte),
            ("ace_flags", c_ubyte),
            ("ace_size", wintypes.WORD),
        ]

    windows_ctypes: Any = ctypes
    win_dll = windows_ctypes.WinDLL
    get_last_error = windows_ctypes.get_last_error
    kernel32 = win_dll("kernel32", use_last_error=True)
    advapi32 = win_dll("advapi32", use_last_error=True)

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, POINTER(FileInformation)]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.LocalFree.argtypes = [c_void_p]
    kernel32.LocalFree.restype = c_void_p

    advapi32.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        POINTER(c_void_p),
        c_void_p,
        POINTER(c_void_p),
        c_void_p,
        POINTER(c_void_p),
    ]
    advapi32.GetSecurityInfo.restype = wintypes.DWORD
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        c_void_p,
        wintypes.DWORD,
        POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.EqualSid.argtypes = [c_void_p, c_void_p]
    advapi32.EqualSid.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [c_void_p, wintypes.DWORD, POINTER(c_void_p)]
    advapi32.GetAce.restype = wintypes.BOOL
    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, POINTER(c_void_p)]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL

    generic_read = 0x80000000
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_attribute_directory = 0x10
    file_attribute_reparse_point = 0x400
    invalid_handle = c_void_p(-1).value
    owner_and_dacl = 0x00000001 | 0x00000004
    se_file_object = 1
    token_query = 0x0008
    token_user = 1
    access_allowed_ace_types = {0, 4, 5, 9, 11}
    access_denied_ace_types = {1, 6, 10, 12}

    handle: int | None = None
    token = wintypes.HANDLE()
    security_descriptor = c_void_p()
    privileged_sids: list[c_void_p] = []
    try:
        handle = kernel32.CreateFileW(
            str(path),
            generic_read,
            0,
            None,
            open_existing,
            file_flag_open_reparse_point,
            None,
        )
        if handle == invalid_handle:
            raise OSError(get_last_error())

        information = FileInformation()
        if not kernel32.GetFileInformationByHandle(handle, byref(information)):
            raise OSError(get_last_error())
        if information.file_attributes & (file_attribute_directory | file_attribute_reparse_point):
            raise SecureFileError

        owner = c_void_p()
        dacl = c_void_p()
        result = advapi32.GetSecurityInfo(
            handle,
            se_file_object,
            owner_and_dacl,
            byref(owner),
            None,
            byref(dacl),
            None,
            byref(security_descriptor),
        )
        if result or not owner.value or not dacl.value:
            raise SecureFileError

        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), token_query, byref(token)):
            raise OSError(get_last_error())
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, token_user, None, 0, byref(required))
        token_buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token, token_user, token_buffer, required, byref(required)
        ):
            raise OSError(get_last_error())
        current_user = c_void_p.from_buffer(token_buffer).value
        if not current_user or not advapi32.EqualSid(owner, current_user):
            raise SecureFileError

        # SYSTEM and the local Administrators group are the Windows equivalents of
        # privileged root access; no unprivileged account or group may have an allow ACE.
        for sid_text in ("S-1-5-18", "S-1-5-32-544"):
            sid = c_void_p()
            if not advapi32.ConvertStringSidToSidW(sid_text, byref(sid)):
                raise OSError(get_last_error())
            privileged_sids.append(sid)

        acl = cast(dacl, POINTER(Acl)).contents
        for index in range(acl.ace_count):
            ace = c_void_p()
            if not advapi32.GetAce(dacl, index, byref(ace)):
                raise OSError(get_last_error())
            header = cast(ace, POINTER(AceHeader)).contents
            if header.ace_type in access_denied_ace_types:
                continue
            if header.ace_type not in access_allowed_ace_types:
                raise SecureFileError
            # Object and callback allow ACEs have variable SID offsets. Reject them
            # rather than risk accepting access granted to another principal.
            if header.ace_type != 0 or header.ace_size < 8:
                raise SecureFileError
            if ace.value is None:
                raise SecureFileError
            ace_sid = c_void_p(ace.value + 8)
            allowed_principal = advapi32.EqualSid(ace_sid, current_user) or any(
                advapi32.EqualSid(ace_sid, sid) for sid in privileged_sids
            )
            if not allowed_principal:
                raise SecureFileError

        windows_msvcrt: Any = msvcrt
        open_osfhandle = windows_msvcrt.open_osfhandle
        descriptor = open_osfhandle(handle, os.O_RDONLY)
        handle = None
        with os.fdopen(descriptor, "rb") as file:
            return file.read()
    except (OSError, SecureFileError) as error:
        raise SecureFileError from error
    finally:
        for sid in privileged_sids:
            kernel32.LocalFree(sid)
        if security_descriptor.value:
            kernel32.LocalFree(security_descriptor)
        if token.value:
            kernel32.CloseHandle(token)
        if handle is not None and handle != invalid_handle:
            kernel32.CloseHandle(handle)
