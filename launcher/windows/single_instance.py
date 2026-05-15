from __future__ import annotations

import ctypes


class SingleInstanceGuard:
    def __init__(self, name: str) -> None:
        self._kernel32 = ctypes.windll.kernel32
        self._kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        self._kernel32.CreateMutexW.restype = ctypes.c_void_p
        self._kernel32.GetLastError.restype = ctypes.c_ulong
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_bool
        self._handle = self._kernel32.CreateMutexW(None, True, name)
        self.already_running = self._kernel32.GetLastError() == 183

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __del__(self) -> None:
        self.close()

