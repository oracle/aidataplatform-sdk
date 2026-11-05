"""Platform file privacy and locking primitives; standard library only."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import uuid

WINDOWS = os.name == "nt"


def _win():
    # Import only on Windows so POSIX installations need no Windows dependency.
    import ctypes as c
    from ctypes import wintypes as w

    class SecurityAttributes(c.Structure):
        _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]

    class AclSize(c.Structure):
        _fields_ = [("count", w.DWORD), ("used", w.DWORD), ("free", w.DWORD)]

    class AttributeTag(c.Structure):
        _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    security = c.WinDLL("advapi32", use_last_error=True)
    signatures = [
        (kernel, "GetCurrentProcess", [], w.HANDLE),
        (kernel, "CloseHandle", [w.HANDLE], w.BOOL),
        (kernel, "LocalFree", [c.c_void_p], c.c_void_p),
        (kernel, "CreateFileW", [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
        (kernel, "CreateDirectoryW", [w.LPCWSTR, c.c_void_p], w.BOOL),
        (kernel, "GetFileInformationByHandleEx", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
        (security, "OpenProcessToken", [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL),
        (security, "GetTokenInformation", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
        (security, "ConvertSidToStringSidW", [c.c_void_p, c.POINTER(c.c_void_p)], w.BOOL),
        (security, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p], w.BOOL),
        (security, "GetSecurityInfo", [w.HANDLE, c.c_int, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p, c.POINTER(c.c_void_p), c.c_void_p, c.POINTER(c.c_void_p)], w.DWORD),
        (security, "SetKernelObjectSecurity", [w.HANDLE, w.DWORD, c.c_void_p], w.BOOL),
        (security, "GetAclInformation", [c.c_void_p, c.c_void_p, w.DWORD, c.c_int], w.BOOL),
        (security, "GetAce", [c.c_void_p, w.DWORD, c.POINTER(c.c_void_p)], w.BOOL),
    ]
    for library, name, args, result in signatures:
        function = getattr(library, name)
        function.argtypes, function.restype = args, result

    def checked(value):
        if not value:
            raise c.WinError(c.get_last_error())
        return value

    def sid_string(pointer):
        output = c.c_void_p()
        checked(security.ConvertSidToStringSidW(pointer, c.byref(output)))
        try:
            return c.wstring_at(output)
        finally:
            kernel.LocalFree(output)

    def current_sid():
        token, size = w.HANDLE(), w.DWORD()
        checked(security.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)))
        try:
            security.GetTokenInformation(token, 1, None, 0, c.byref(size))
            buffer = c.create_string_buffer(size.value)
            checked(security.GetTokenInformation(token, 1, buffer, size, c.byref(size)))
            return sid_string(c.cast(buffer, c.POINTER(c.c_void_p))[0])
        finally:
            kernel.CloseHandle(token)

    @contextmanager
    def descriptor(directory=False):
        sid, pointer = current_sid(), c.c_void_p()
        inheritance = "OICI" if directory else ""
        sddl = f"O:{sid}D:P(A;{inheritance};FA;;;{sid})"
        checked(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(pointer), None))
        try:
            yield pointer
        finally:
            kernel.LocalFree(pointer)

    def no_reparse(handle):
        info = AttributeTag()
        checked(kernel.GetFileInformationByHandleEx(handle, 9, c.byref(info), c.sizeof(info)))
        if info.attributes & 0x400:
            raise PermissionError("Reparse points are not supported for private files")

    def open_handle(path, access, disposition=3, share=0):
        with descriptor() as sd:
            attributes = SecurityAttributes(c.sizeof(SecurityAttributes), sd, False)
            handle = kernel.CreateFileW(str(Path(path).absolute()), access, share, c.byref(attributes),
                                        disposition, 0x00200000 | 0x02000000, None)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            no_reparse(handle)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        return handle

    def verify(handle):
        owner, acl, sd = c.c_void_p(), c.c_void_p(), c.c_void_p()
        error = security.GetSecurityInfo(handle, 1, 1 | 4, c.byref(owner), None, c.byref(acl), None, c.byref(sd))
        if error:
            raise c.WinError(error)
        try:
            sid = current_sid()
            if not owner or sid_string(owner) != sid or not acl:
                raise PermissionError("Private file owner or DACL is invalid")
            info = AclSize()
            checked(security.GetAclInformation(acl, c.byref(info), c.sizeof(info), 2))
            for index in range(info.count):
                ace = c.c_void_p()
                checked(security.GetAce(acl, index, c.byref(ace)))
                kind = c.c_ubyte.from_address(ace.value).value
                # Standard deny ACEs grant nothing. Reject unknown/object/callback
                # ACEs rather than guessing their access semantics.
                if kind == 1:
                    continue
                if kind != 0 or sid_string(c.c_void_p(ace.value + 8)) != sid:
                    raise PermissionError("Private file grants access to another principal")
        finally:
            kernel.LocalFree(sd)

    return c, kernel, security, checked, descriptor, open_handle, verify, SecurityAttributes


def private_open(path, flags, mode=0o600):
    """Create/open a private file. Windows applies an owner-only DACL atomically."""
    if not WINDOWS:
        return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    import msvcrt
    c, kernel, _, _, _, open_handle, verify, _ = _win()
    access = 0x00020000 | (0xC0000000 if flags & os.O_RDWR else 0x40000000)
    handle = open_handle(path, access, 1 if flags & os.O_EXCL else 4,
                         share=0 if flags & os.O_EXCL else 3)
    try:
        verify(handle)
        fd = msvcrt.open_osfhandle(handle, (flags & (os.O_RDWR | os.O_WRONLY)) | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    os.set_inheritable(fd, False)
    return fd


def readonly_open(path, private=False, share_delete=False):
    """Open without following links; optionally validate owner-only access.

    Context readers share deletion so Windows atomic replacement can proceed
    while the reader finishes consuming its original file handle.
    """
    if not WINDOWS:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        if private:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                os.close(fd)
                raise PermissionError("Result must be an owner-only regular file owned by this user")
        return fd
    import msvcrt
    _, kernel, _, _, _, open_handle, verify, _ = _win()
    handle = open_handle(path, 0x80000000 | 0x00020000,
                         share=7 if share_delete else 0)
    try:
        if private:
            verify(handle)
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def restrict_directory(path):
    if not WINDOWS:
        os.chmod(path, 0o700)
        return
    c, kernel, security, checked, descriptor, open_handle, verify, _ = _win()
    handle = open_handle(path, 0x00040000 | 0x00080000 | 0x00020000, share=7)
    try:
        with descriptor(directory=True) as sd:
            checked(security.SetKernelObjectSecurity(handle, 1 | 4 | 0x80000000, sd))
        verify(handle)
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def private_directory(prefix="aidp-private-"):
    if not WINDOWS:
        with tempfile.TemporaryDirectory(prefix=prefix) as directory:
            yield directory
        return
    c, kernel, _, checked, descriptor, open_handle, verify, Attributes = _win()
    path = Path(tempfile.gettempdir()) / (prefix + uuid.uuid4().hex)
    with descriptor(directory=True) as sd:
        attrs = Attributes(c.sizeof(Attributes), sd, False)
        checked(kernel.CreateDirectoryW(str(path), c.byref(attrs)))
    try:
        handle = open_handle(path, 0x00020000)
        try:
            verify(handle)
        finally:
            kernel.CloseHandle(handle)
        yield str(path)
    finally:
        shutil.rmtree(path)


@contextmanager
def exclusive_lock(stream, timeout=30):
    if not WINDOWS:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return
    import msvcrt
    # Windows byte-range locks may extend past EOF. Acquire before writing
    # the initial byte so concurrent first writers cannot race initialization.
    stream.seek(0)
    deadline = time.monotonic() + timeout
    while True:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for the AIDP context lock")
            time.sleep(0.05)
    try:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write("\0")
            stream.flush()
        yield
    finally:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
